---
name: duck-eval
description: Run controlled off/on agent evaluations from the evals folder and conduct a human blind review of the saved replies.
---

# duck-eval

Use this skill only for development evaluations under `evals/`. It is not a general plugin skill and must not be installed, exported, or loaded into a subject session.

## Prepare

- Make one focused case and a small fixture whose code, tests, settings, and operation notes represent the question. Keep fixture paths relative to the case file. Do not put the expected answer in the prompt or fixture notes.
- Pin the engine, model, effort, case, fixture, plugin snapshot, and output directory before starting. The default is one `off` and one `on` run; more repeats need explicit approval.
- Use `run.py`. It creates a fresh workspace per run, rejects an existing output directory, freezes only the needed plugin files, and saves raw provider evidence. Never silently retry a model, add a canary, or run until one arm looks better.
- If authentication, hook trust, model selection, plugin loading, or a required result is not verifiable, stop that run and preserve the failure. A denied optional probe is evidence to record, not a reason to spend another model call.

## Review

1. Read each `review/anonymous.md` or `.json` completely, including progress and final messages, before opening `private/KEY.json`.
2. For each pair, record whether the response is useful, understandable, or leaves an important label/condition unexplained. Record the concrete sentence or omission and the necessary conditions for the reader's decision.
3. Give the same anonymous pack to two blind reviewers at once, Claude Fable 5.1 and GPT-6 Astra (medium effort, read-only, asked to do nothing beyond scoring), and save both reviews before any key is opened.
4. Reveal the key only after the judgment is fixed. Then inspect raw stream/session, model, hook/plugin evidence, tests, usage, and workspace state.

Code names, flow diagrams, and standard technical terms are acceptable when their behavior and consequences are clear. Do not reward Chinese, brevity, or a lower character count; correctness is a separate judgment. Do not replace human reading with regex or a total score.

Keep provider usage and cost fields separate and raw. They are structural evidence, not a quality score or a billing claim. Preserve the complete local records and write only a small public summary when requested.
