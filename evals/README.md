# Development evaluator

`run.py` is a small, local-only off/on runner for one case at a time. It can invoke either Codex or Claude Code, but it never chooses a fallback model and never retries a failed run.

This consolidated entry point is a delivery draft assembled from the commands used in the recorded experiments. It has not been end-to-end tested; no additional paid runs were made for this handoff. Use Python 3.11+, or install `tomli` on older Python for Codex configuration reading.

Ask your agent to read [skill/SKILL.md](skill/SKILL.md) to prepare a case, run an authorized comparison, and personally interpret the anonymous replies. This development skill is not installed or loaded by the Duck plugin.

Dry-run the current case:

```sh
python3 -B run.py --engine codex --case cases/job-recovery.json \
  --output /absolute/path/to/new-output --dry-run
```

Run one off/on pair only after explicit authorization:

```sh
python3 -B run.py --engine codex --case cases/job-recovery.json \
  --output /absolute/path/to/new-output
```

Use `--arm off` or `--arm on` to run one arm. Omitting `--arm` keeps the off/on
pair, and `manifest.json` records the arms selected for that invocation. To run
the on arm later with an existing frozen snapshot, pass its directory with
`--plugin` and use a new output directory; the runner does not resume an earlier
run.

Use `--engine claude` for Claude Code. Defaults are Codex `gpt-5.6-luna/max` and Claude `claude-opus-5/high`; pass `--model` and `--effort` explicitly when choosing another supported value. The runner records the requested and observed model rather than silently substituting one.

The case fixture is resolved relative to its JSON file. Each run gets a random, non-arm workspace. `off` has no plugin; `on` receives a frozen copy containing only the selected manifest, Duck/unduck skills, hooks, and referenced logo asset. The runner does not copy `evals`, raw output, auth files, or other repository files into that plugin.

Output includes the case/prompt hash, commands with settings/auth redacted, provider-specific usage and raw cost fields, raw stream/stderr/debug/session files, per-run metadata, a path-anonymized anonymous review, and a private `KEY.json`. Read the anonymous review completely before opening the key. Metrics are for structural checks; quality remains a human judgment.

Codex uses a temporary `CODEX_HOME`, a copied login file that is never saved to output, a local marketplace/cache snapshot, and the existing trusted hook when it can be proven from the real config. Claude keeps the real OAuth/config location, uses local setting sources, disables CLAUDE.md/auto-memory/background/title side effects, and restricts tools to reading plus the README unittest command. Missing auth, trust, model, plugin, result, or required hook evidence is preserved as a failure and stops later runs.

The fixture is a local SQLite stand-in. It has no external services and is not a production reliability claim.

Private cases built from the maintainer's own repositories live under `evals/_private/` (cases, fixtures, design notes, pack tools), which `.gitignore` excludes. Their usage data and reviewer scores are published under `results/`; their fixtures and reply texts are not.
