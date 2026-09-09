#!/usr/bin/env python3
"""Small portable off/on evaluator for the development duck-eval skill."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


def find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / ".claude-plugin" / "plugin.json").is_file() and \
                (candidate / ".codex-plugin" / "plugin.json").is_file():
            return candidate
    return start.parents[2]


ROOT = find_repo_root(Path(__file__).resolve().parent)
ARMS = ("off", "on")
DEFAULTS = {
    "codex": ("gpt-5.6-luna", "max"),
    "claude": ("claude-opus-5", "high"),
}
HOOK_STATE = "i-am-the-duck@i-am-the-duck:hooks/hooks.json:session_start:0:0"
TOKEN_ENV = (
    "OPENAI_API_KEY", "CODEX_API_KEY", "ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN",
    "GOOGLE_API_KEY", "GEMINI_API_KEY", "AZURE_OPENAI_API_KEY",
)


def digest_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def digest_tree(path: Path) -> str:
    h = hashlib.sha256()
    for child in sorted(p for p in path.rglob("*") if p.is_file()):
        h.update(str(child.relative_to(path)).encode())
        h.update(bytes.fromhex(digest_file(child)))
    return h.hexdigest()


def put_json(path: Path, value, mode=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    if mode is not None:
        path.chmod(mode)


def load_case(path: Path):
    data = json.loads(path.read_text())
    if isinstance(data, list):
        if len(data) != 1:
            raise ValueError("case file must contain one case object")
        data = data[0]
    if not isinstance(data, dict) or not isinstance(data.get("id"), str):
        raise ValueError("case needs an id")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", data["id"]):
        raise ValueError("case id contains unsafe path characters")
    if not isinstance(data.get("prompt"), str) or not data["prompt"].strip():
        raise ValueError("case needs a prompt")
    if not isinstance(data.get("fixture"), str) or not data["fixture"].strip():
        raise ValueError("case needs a non-empty fixture path")
    fixture_ref = Path(data["fixture"])
    if fixture_ref.is_absolute() or not str(fixture_ref):
        raise ValueError("fixture must be relative to the case file")
    fixture = (path.parent / fixture_ref).resolve()
    if not fixture.is_dir():
        raise ValueError(f"fixture directory does not exist: {fixture}")
    return data, fixture


def resolve_options(engine, model, effort):
    if engine not in DEFAULTS:
        raise ValueError(f"unknown engine: {engine}")
    default_model, default_effort = DEFAULTS[engine]
    model = model or default_model
    effort = effort or default_effort
    if not isinstance(model, str) or not model.strip():
        raise ValueError("model must be a non-empty explicit value")
    if effort not in {"low", "medium", "high", "max", "xhigh"}:
        raise ValueError(f"unsupported effort: {effort}")
    return model, effort


def build_plan(repeats, arm=None):
    if repeats < 1:
        raise ValueError("repeats must be positive")
    if arm is not None and arm not in ARMS:
        raise ValueError(f"unknown arm: {arm}")
    arms = ARMS if arm is None else (arm,)
    return [{"arm": selected_arm, "repeat": repeat}
            for repeat in range(1, repeats + 1) for selected_arm in arms]


def text_of(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(text_of(v) for v in value)
    if isinstance(value, dict):
        return text_of(value.get("text", value.get("content", "")))
    return ""


def assistant_messages_from_claude(event):
    message = event.get("message") if isinstance(event.get("message"), dict) else event
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return []
    return [block["text"] for block in content
            if isinstance(block, dict) and block.get("type") == "text"
            and isinstance(block.get("text"), str)]


def collect_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from collect_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from collect_strings(child)


def contains_nested_text(event, needle):
    escaped = json.dumps(needle, ensure_ascii=False)[1:-1]
    for text in collect_strings(event):
        if needle in text or escaped in text:
            return True
        try:
            nested = json.loads(text)
        except (TypeError, ValueError):
            continue
        if any(needle in nested_text for nested_text in collect_strings(nested)):
            return True
    return False


def parse_claude_stream(path: Path, skill_text: str = ""):
    events = []
    malformed = 0
    for index, line in enumerate(path.read_text(errors="replace").splitlines()):
        try:
            event = json.loads(line)
        except ValueError:
            malformed += 1
            continue
        if isinstance(event, dict):
            events.append((index, event))
    init = next((e for _, e in events if e.get("type") == "system" and e.get("subtype") == "init"), None)
    result = next((e for _, e in reversed(events) if e.get("type") == "result"), None)
    messages = []
    first_text = None
    skill_tool = False
    permission_denials = []
    for index, event in events:
        if event.get("type") == "assistant":
            for text in assistant_messages_from_claude(event):
                first_text = index if first_text is None else first_text
                messages.append({"event_index": index, "text": text})
            message = event.get("message", {})
            for block in message.get("content", []) if isinstance(message, dict) else []:
                if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Skill":
                    if "duck" in json.dumps(block, ensure_ascii=False).lower():
                        skill_tool = True
        if event.get("type") == "system" and "permission" in str(event.get("subtype", "")):
            permission_denials.append({"line": index, "subtype": event.get("subtype")})
    if not messages and isinstance(result, dict) and isinstance(result.get("result"), str):
        messages.append({"event_index": -1, "text": result["result"]})
    models = []
    if isinstance(init, dict) and isinstance(init.get("model"), str):
        models.append(init["model"])
    if isinstance(result, dict) and isinstance(result.get("model"), str):
        models.append(result["model"])
    session_id = next((e.get("session_id") for e in (init, result)
                       if isinstance(e, dict) and isinstance(e.get("session_id"), str)), None)
    hook_full = any(contains_nested_text(e, skill_text) for _, e in events) if skill_text else False
    first_text = first_text if first_text is not None else float("inf")
    hook_full_before_first = any(
        index <= first_text and contains_nested_text(event, skill_text)
        for index, event in events
    ) if skill_text else False
    return {
        "events": events,
        "messages": messages,
        "init": init,
        "result": result,
        "models": sorted(set(models)),
        "session_id": session_id,
        "skill_tool_seen": skill_tool,
        "hook_full_skill": hook_full,
        "hook_full_skill_before_first": hook_full_before_first,
        "permission_denials": permission_denials,
        "malformed": malformed,
        "usage": result.get("usage") if isinstance(result, dict) else None,
        "cost_usd": result.get("total_cost_usd") if isinstance(result, dict) else None,
    }


def parse_codex_events(path: Path):
    events, messages, usages = [], [], []
    malformed = 0
    for index, line in enumerate(path.read_text(errors="replace").splitlines()):
        try:
            event = json.loads(line)
        except ValueError:
            malformed += 1
            continue
        if not isinstance(event, dict):
            continue
        events.append((index, event))
        if event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
            usages.append(event["usage"])
        payload = event.get("payload", {})
        if event.get("type") == "response_item" and payload.get("type") == "message" and \
                payload.get("role") == "assistant" and payload.get("channel") != "analysis":
            text = text_of(payload.get("content", []))
            if text:
                messages.append({"event_index": index, "text": text})
        item = event.get("item")
        if event.get("type") == "item.completed" and isinstance(item, dict) and \
                item.get("type") in {"assistant_message", "agent_message", "message"}:
            text = text_of(item)
            if text:
                messages.append({"event_index": index, "text": text})
    totals = {}
    for key in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens"):
        values = [u[key] for u in usages if isinstance(u.get(key), (int, float))]
        totals[key] = sum(values) if values else None
    models = sorted({event.get("model") for _, event in events if isinstance(event.get("model"), str)})
    models = sorted(set(models) | {event["payload"]["model"] for _, event in events
                                  if event.get("type") == "turn_context" and
                                  isinstance(event.get("payload", {}).get("model"), str)})
    session_id = next((e.get("session_id") for _, e in events if isinstance(e.get("session_id"), str)), None)
    return {"events": events, "messages": messages, "usages": usages, "totals": totals,
            "models": models, "session_id": session_id, "malformed": malformed}


def plugin_files(source: Path, destination: Path, engine: str):
    manifest_dir = ".codex-plugin" if engine == "codex" else ".claude-plugin"
    selected = (f"{manifest_dir}/plugin.json", "skills/duck/SKILL.md",
                "skills/unduck/SKILL.md", "skills/unduck/agents/openai.yaml",
                "hooks/hooks.json", "hooks/session-start.mjs", "assets/logo.png")
    for relative in selected:
        source_file = source / relative
        if not source_file.is_file():
            raise RuntimeError(f"plugin file missing: {source_file}")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target)
    return {relative: digest_file(source / relative) for relative in selected}


def codex_install_plugin(base: Path, source: Path):
    marketplace = base / "marketplace"
    frozen = marketplace / "plugins" / "i-am-the-duck"
    hashes = plugin_files(source, frozen, "codex")
    marketplace_file = marketplace / ".agents" / "plugins" / "marketplace.json"
    put_json(marketplace_file, {"name": "i-am-the-duck", "plugins": [{
        "name": "i-am-the-duck", "source": {"source": "local", "path": "./plugins/i-am-the-duck"},
        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        "category": "Productivity"}]})
    cache = base / "codex" / "plugins" / "cache" / "i-am-the-duck" / "i-am-the-duck" / "local"
    shutil.copytree(frozen, cache)
    return frozen, hashes


def read_codex_trust():
    try:
        try:
            import tomllib
        except ModuleNotFoundError:
            import tomli as tomllib
        data = tomllib.loads((Path.home() / ".codex" / "config.toml").read_text())
        value = data["hooks"]["state"][HOOK_STATE]["trusted_hash"]
        return value if isinstance(value, str) and value.startswith("sha256:") else None
    except (OSError, KeyError, TypeError, ValueError, ModuleNotFoundError):
        return None


def installed_plugin_ids():
    ids = set()
    settings = Path.home() / ".claude" / "settings.json"
    try:
        data = json.loads(settings.read_text())
        ids.update((data.get("enabledPlugins") or {}).keys())
    except (OSError, ValueError):
        pass
    registry = Path.home() / ".claude" / "plugins" / "installed_plugins.json"
    try:
        data = json.loads(registry.read_text())
        plugins = data.get("plugins", {}) if isinstance(data, dict) else {}
        if isinstance(plugins, dict):
            ids.update(plugins.keys())
    except (OSError, ValueError):
        pass
    return sorted(str(item) for item in ids)


def child_env(base, engine, effort):
    env = os.environ.copy()
    if engine == "codex":
        env.update({"HOME": str(base / "home"), "CODEX_HOME": str(base / "codex"),
                    "TMPDIR": str(base / "home" / "tmp")})
    else:
        env.update({"CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1",
                    "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
                    "CLAUDE_CODE_DISABLE_TERMINAL_TITLE": "1",
                    "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1",
                    "CLAUDE_CODE_EFFORT_LEVEL": effort})
    for key in TOKEN_ENV:
        env.pop(key, None)
    return env


def anonymize(text, replacements):
    for source, target in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        if not source:
            continue
        text = text.replace(source, target)
    return text


def copy_claude_session(session_id, target):
    if not session_id:
        return None
    root = Path.home() / ".claude" / "projects"
    if not root.is_dir():
        return None
    matches = sorted(root.rglob(f"{session_id}.jsonl"))
    if not matches:
        return None
    shutil.copy2(matches[0], target / "session.jsonl")
    return str(target / "session.jsonl")


def build_claude_command(model, effort, settings_json, debug_path, plugin_dir, prompt):
    command = ["claude", "--print", "--model", model, "--effort", effort,
               "--setting-sources", "local", "--settings", settings_json,
               "--permission-mode", "dontAsk", "--permission-prompts", "none",
               "--tools", "Read,Glob,Grep,Bash,Skill",
               "--allowedTools", "Read,Glob,Grep,Skill,Bash(python3 -B -m unittest *)",
               "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
               "--output-format", "stream-json", "--verbose", "--include-hook-events",
               "--debug-file", str(debug_path)]
    if plugin_dir is not None:
        command += ["--plugin-dir", str(plugin_dir)]
    return command + [prompt]


def run_one(engine, arm, repeat, case, fixture, options, plugin_snapshot, trust, output, plugin_hashes):
    run_id = f"{case['id']}--{arm}--r{repeat}"
    run_dir = output / "runs" / run_id
    run_dir.mkdir(parents=True)
    workspace = output / "workspaces" / f"workspace-{uuid.uuid4()}"
    shutil.copytree(fixture, workspace)
    before = digest_tree(workspace)
    started = time.monotonic()
    plugin_dir = None
    settings_json = None
    base = None
    temp_context = None
    anonymize_paths = [str(workspace)]
    try:
        if engine == "codex":
            temp_context = tempfile.TemporaryDirectory(prefix="duck-eval-")
            base = Path(temp_context.name)
            (base / "home" / "tmp").mkdir(parents=True)
            (base / "codex").mkdir(parents=True)
            auth = Path.home() / ".codex" / "auth.json"
            if not auth.is_file():
                raise RuntimeError("Codex auth.json is not available; no model started")
            shutil.copy2(auth, base / "codex" / "auth.json")
            if arm == "on":
                plugin_dir, installed_hashes = codex_install_plugin(base, plugin_snapshot)
                anonymize_paths.extend([str(base / "marketplace"), str(base / "codex" / "plugins")])
                plugin_hashes = installed_hashes
            config = base / "codex" / "config.toml"
            if arm == "on":
                config.write_text(
                    f'model = {json.dumps(options["model"])}\nmodel_reasoning_effort = {json.dumps(options["effort"])}\n\n'
                    '[marketplaces."i-am-the-duck"]\nsource_type = "local"\n'
                    f"source = {json.dumps(str(base / 'marketplace'))}\n\n"
                    '[plugins."i-am-the-duck@i-am-the-duck"]\nenabled = true\n\n'
                    f'[hooks.state."{HOOK_STATE}"]\ntrusted_hash = {json.dumps(trust)}\n'
                )
            else:
                config.write_text(f'model = {json.dumps(options["model"])}\nmodel_reasoning_effort = {json.dumps(options["effort"])}\n')
            env = child_env(base, engine, options["effort"])
            events_path, stderr_path, answer_path = run_dir / "events.jsonl", run_dir / "stderr.log", run_dir / "answer.txt"
            command = ["codex", "exec", "--json", "-o", str(answer_path), "--skip-git-repo-check",
                       "--disable", "apps", "--disable", "memories", "--disable", "unbounded_connection_retries",
                       "-s", "workspace-write", "-c", 'approval_policy="never"', "--cd", str(workspace), case["prompt"]]
            with events_path.open("w") as out, stderr_path.open("w") as err:
                completed = subprocess.run(command, cwd=workspace, env=env, stdout=out, stderr=err, check=False)
            parsed = parse_codex_events(events_path)
            raw_sessions = [parse_codex_events(p) for p in sorted((base / "codex" / "sessions").rglob("*.jsonl"))]
            parsed["models"] = sorted({model for session in raw_sessions for model in session["models"]})
            skill_text = (plugin_source / "skills/duck/SKILL.md").read_text().strip()
            skill_loaded = any(contains_nested_text(event, skill_text)
                               for session in raw_sessions for _, event in session["events"])
            final = answer_path.read_text(errors="replace") if answer_path.is_file() else ""
            reasons = []
            if completed.returncode != 0: reasons.append(f"exit_code={completed.returncode}")
            if not parsed["usages"]: reasons.append("missing turn.completed usage")
            if not final: reasons.append("missing answer")
            if skill_loaded != (arm == "on"):
                reasons.append("Duck context does not match the requested arm")
            if not parsed["models"] or not any(options["model"] in model for model in parsed["models"]):
                reasons.append(f"actual model not confirmed: {parsed['models']}")
            usage = parsed["totals"]
            provider_evidence = {"actual_models": parsed["models"], "codex_usage": parsed["usages"],
                                 "plugin_setup": arm == "on", "full_skill_in_session": skill_loaded}
            session_path = None
            cost = None
        else:
            settings = {"enabledPlugins": {name: False for name in installed_plugin_ids()}}
            settings_json = json.dumps(settings, separators=(",", ":"))
            if arm == "on":
                plugin_dir = plugin_snapshot
                anonymize_paths.append(str(plugin_dir))
            command = build_claude_command(options["model"], options["effort"], settings_json,
                                           run_dir / "debug.log", plugin_dir, case["prompt"])
            env = child_env(Path("."), engine, options["effort"])
            events_path, stderr_path = run_dir / "stream.jsonl", run_dir / "stderr.log"
            with events_path.open("w") as out, stderr_path.open("w") as err:
                completed = subprocess.run(command, cwd=workspace, env=env, stdout=out, stderr=err, check=False)
            skill_text = (plugin_dir / "skills/duck/SKILL.md").read_text() if plugin_dir else ""
            parsed = parse_claude_stream(events_path, skill_text)
            result = parsed["result"] or {}
            init_plugins = parsed["init"].get("plugins", []) if isinstance(parsed["init"], dict) else []
            if not isinstance(init_plugins, list):
                init_plugins = []
            init_plugin_loaded = isinstance(init_plugins, list) and any(
                isinstance(item, dict) and item.get("name") == "i-am-the-duck" for item in init_plugins)
            reasons = []
            if completed.returncode != 0: reasons.append(f"exit_code={completed.returncode}")
            if result.get("subtype") != "success" or result.get("is_error") is not False:
                reasons.append("Claude result is not successful")
            if not parsed["usage"]: reasons.append("missing provider usage")
            if not parsed["messages"]: reasons.append("missing assistant messages")
            if not parsed["models"] or not any(options["model"] in model for model in parsed["models"]):
                reasons.append(f"actual model not confirmed: {parsed['models']}")
            if arm == "off" and init_plugins:
                reasons.append("off init contains plugins")
            if arm == "on" and not init_plugin_loaded:
                reasons.append("plugin not evidenced in init")
            if arm == "on" and not parsed["hook_full_skill_before_first"]:
                reasons.append("full plugin hook context not evidenced before first reply")
            usage = parsed["usage"]
            cost = parsed["cost_usd"]
            provider_evidence = {"actual_models": parsed["models"], "claude_init": parsed["init"],
                                 "plugin_loaded": init_plugin_loaded,
                                 "hook_full_skill_before_first": parsed["hook_full_skill_before_first"],
                                 "skill_tool_seen": parsed["skill_tool_seen"],
                                 "permission_denials": parsed["permission_denials"]}
            session_path = copy_claude_session(parsed["session_id"], run_dir)
        after = digest_tree(workspace)
        messages = parsed["messages"]
        session_files = []
        if engine == "codex" and base is not None and (base / "codex" / "sessions").is_dir():
            shutil.copytree(base / "codex" / "sessions", run_dir / "sessions")
            session_files = [str(p.relative_to(run_dir)) for p in (run_dir / "sessions").rglob("*") if p.is_file()]
            for session_file in sorted((run_dir / "sessions").rglob("*.jsonl")):
                session_messages = parse_codex_events(session_file)["messages"]
                if session_messages:
                    messages = session_messages
                    break
        put_json(run_dir / "assistant_messages.json", messages)
        record = {
            "run_id": run_id, "case_id": case["id"], "engine": engine, "arm": arm, "repeat": repeat,
            "status": "ok" if not reasons else "failed", "returncode": completed.returncode,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "command": ["<case prompt>" if arg == case["prompt"] else ("<child settings>" if arg == settings_json else arg)
                        for arg in command],
            "workspace": str(workspace), "workspace_unchanged": before == after,
            "anonymize_paths": anonymize_paths, "model": options["model"], "effort": options["effort"],
            "failure_reasons": reasons, "warnings": parsed.get("permission_denials", []),
            "assistant_messages": messages, "session_id": parsed.get("session_id"),
            "session_path": session_path, "session_files": session_files,
            "usage": usage, "cost_usd_raw": cost, "provider_evidence": provider_evidence,
            "plugin_hashes": plugin_hashes, "settings_hash": hashlib.sha256((settings_json or "").encode()).hexdigest() if settings_json else None,
            "malformed_stream_lines": parsed.get("malformed", 0),
        }
    except Exception as exc:
        record = {"run_id": run_id, "case_id": case["id"], "engine": engine, "arm": arm, "repeat": repeat,
                  "status": "failed", "failure_reasons": [f"{type(exc).__name__}: {exc}"],
                  "elapsed_seconds": round(time.monotonic() - started, 3), "assistant_messages": [],
                  "anonymize_paths": anonymize_paths}
    finally:
        if temp_context is not None:
            temp_context.cleanup()
    put_json(run_dir / "metadata.json", record)
    return record


def make_review(results, replacements, output):
    review = output / "review"
    review.mkdir(parents=True, exist_ok=True)
    by_repeat = {}
    for row in results:
        by_repeat.setdefault(row["repeat"], []).append(row)
    anonymous, key, markdown = [], {}, ["# Anonymous review\n"]
    for repeat, rows in sorted(by_repeat.items()):
        random.SystemRandom().shuffle(rows)
        markdown.append(f"## Repeat {repeat}\n")
        key_rows = {}
        for index, row in enumerate(rows):
            label = chr(ord("A") + index)
            key_rows[label] = {"arm": row["arm"], "run_id": row["run_id"]}
            messages = [{"event_index": m["event_index"], "text": anonymize(m["text"], replacements)}
                        for m in row.get("assistant_messages", [])]
            anonymous.append({"case_id": row["case_id"], "repeat": repeat, "label": label,
                              "status": row["status"], "assistant_messages": messages})
            markdown.append(f"## {label} ({row['status']})\n")
            markdown.extend(message["text"] + "\n" for message in messages)
        key[f"{results[0]['case_id']}::{repeat}"] = key_rows
    (review / "anonymous.md").write_text("\n".join(markdown))
    put_json(review / "anonymous.json", anonymous)
    put_json(output / "private" / "KEY.json", key, mode=0o600)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Portable off/on agent evaluation runner")
    parser.add_argument("--engine", choices=("codex", "claude"), default="codex")
    parser.add_argument("--model")
    parser.add_argument("--effort")
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--arm", choices=ARMS, default=None,
                        help="run one arm; omit to run the off/on pair")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plugin", type=Path, default=ROOT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    args.model, args.effort = resolve_options(args.engine, args.model, args.effort)
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    if not args.output.is_absolute():
        parser.error("--output must be absolute")
    args.output = args.output.resolve()
    if args.output.exists() or args.output.is_symlink():
        parser.error("--output must be a new directory")
    args.case = args.case.resolve()
    args.plugin = args.plugin.resolve()
    return args


def main(argv=None):
    args = parse_args(argv)
    case, fixture = load_case(args.case)
    try:
        args.output.relative_to(fixture)
    except ValueError:
        pass
    else:
        raise ValueError("output must not be inside the fixture directory")
    plan = build_plan(args.repeats, args.arm)
    if args.dry_run:
        print(json.dumps({"engine": args.engine, "model": args.model, "effort": args.effort,
                          "case": case["id"], "runs": plan, "output": str(args.output)}, ensure_ascii=False, indent=2))
        return 0
    trust = None
    if args.engine == "codex":
        trust = read_codex_trust()
        if not trust:
            raise RuntimeError("Codex hook trust is not provable from the real config; no model started")
    args.output.mkdir(parents=True)
    plugin_snapshot = args.output / "plugin-snapshot"
    plugin_hashes = plugin_files(args.plugin, plugin_snapshot, args.engine)
    selected_arms = list(dict.fromkeys(row["arm"] for row in plan))
    put_json(args.output / "manifest.json", {
        "created_at": datetime.now(timezone.utc).isoformat(), "engine": args.engine,
        "model": args.model, "effort": args.effort, "repeats": args.repeats, "arms": selected_arms,
        "case": {"id": case["id"], "prompt": case["prompt"], "path": str(args.case),
                 "sha256": digest_file(args.case), "fixture": str(fixture), "fixture_sha256": digest_tree(fixture)},
        "plugin": str(args.plugin), "plugin_snapshot": str(plugin_snapshot),
        "plugin_hashes": plugin_hashes, "codex_hook_trust_present": bool(trust),
        "commands": "per-run metadata contains redacted argv; auth is never copied to output",
    })
    results = []
    replacements = {}
    for plan_row in plan:
        record = run_one(args.engine, plan_row["arm"], plan_row["repeat"], case, fixture,
                         {"model": args.model, "effort": args.effort}, plugin_snapshot, trust, args.output, plugin_hashes)
        results.append(record)
        for path in record.get("anonymize_paths", []):
            replacements[path] = "/plugin" if "plugin" in path or "marketplace" in path else "/workspace"
        put_json(args.output / "results.json", results)
        if record["status"] != "ok":
            put_json(args.output / "private" / "STOP.json", {"after": record["run_id"], "reasons": record["failure_reasons"]}, mode=0o600)
            break
    make_review(results, replacements, args.output)
    failures = sum(row["status"] != "ok" for row in results)
    put_json(args.output / "summary.json", {"runs_started": len(results), "ok": len(results) - failures,
                                             "failed": failures, "output": str(args.output)})
    return 1 if failures or len(results) != len(plan) else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"run.py: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(2)
