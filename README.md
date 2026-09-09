<p align="center"><img src="assets/hero.png" alt="A robot explains its code to a rubber duck." width="800"></p>

# i-am-the-duck

Rubber duck debugging, reversed. You are the duck.

**[中文說明](docs/README.zh-TW.md)**

## What this is

Rubber duck debugging is the old trick where you explain your code, line by line, to a rubber duck on your desk. Somewhere in the explanation you find the bug yourself. The duck does nothing. Having to say it out loud, in plain words, is what works.

This plugin turns that around. The coding agent does the work, and you are the duck. It explains meaningful work in words you can follow without reading the code or the tool output: what is happening and why, what came of it, and what the available evidence supports. It calls out an untested or inferred part when it changes what you can rely on.

It started as a joke. It stayed because explaining a change in plain words can expose when the reason is missing.

## Early results

**Across three tasks on Opus 5 (high), Duck cut reply characters and output tokens by roughly a third to a half, and wall-clock time and cost by a fifth to two fifths, with blind reviewers rating the answers as correct as the baseline's.**

![Reply characters and output tokens with and without Duck, by task, on Opus 5 high.](evals/assets/initial-results.svg)

Same findings, less to read. The Duck replies open with the verdict, draw a flow only where a fork decides the outcome, answer the asker's questions in the asker's order, and say which claims were checked in code and which were only read.

The newest task came from a real session where the agent reported a design's status in reviewer finding numbers and spec section codes until the asker had to ask for plain language. Every reply was scored by blind reviewers before the arms were revealed, and the one reply all of them called plain was a Duck reply. [Data and the blind reviews](evals/results/README.md).

## What changes

Without it, a long session drifts into shorthand:

> Phase C done, all green, merged the fix into the pipeline.

With it:

> Restarting the service now resumes the timeout check, so overdue work is still detected. `npm test`: 24 passed, 0 failed. I did not run the Codex side; it is not installed here.

Three habits:

- **Before meaningful work** with one clear purpose, say what will happen and why. Reading, searching, and running tests need no announcement.
- **After meaningful work**, say what happened and the evidence or difference that matters. Call out an untested or inferred part when it changes what you can rely on; do not add checks just to fill out the report.
- **Words** describe concrete actions or results. Names from code, specifications, plans, tickets, or earlier conversation are labels, not explanations. Use an exact name when it helps locate or distinguish something, then say what it does; otherwise replace it with the concrete action or result. Reuse established context after compaction instead of explaining labels again.

Decisions explain the trade-off that matters for each option and, when relevant, whether its evidence is tested or expected. Work handed to another agent comes back as a result summary, with whether it was checked and any limitation that matters.

It does not decide what you approve, how far a task goes, what is risky, or whether the code is right. It only makes the agent explain.

## Install

Claude Code:

```
/plugin marketplace add davidleitw/i-am-the-duck
/plugin install i-am-the-duck@i-am-the-duck
```

Codex:

```
codex plugin marketplace add davidleitw/i-am-the-duck
codex plugin add i-am-the-duck@i-am-the-duck
```

Needs `node` 18 or newer on your PATH. Start a new session: a small hook runs at every session start and after context compaction and includes the complete rules in its instruction, so the agent can apply them without searching or rereading them. In Codex, open `/hooks` once, review the hook and trust it; until you do, Codex skips it.

If the agent drifts back into shorthand, type `/i-am-the-duck:duck` in Claude Code or `$i-am-the-duck:duck` in Codex.

Other hosts, and the update and uninstall commands for each: **[INSTALL.md](INSTALL.md)**.

| Host | Loads the rules for you | Tested by us |
|---|---|---|
| Claude Code | yes, at every session start | yes |
| Codex | yes, once you trust the hook | yes |
| Gemini CLI | yes, through `GEMINI.md` | no |
| Qwen Code | not guaranteed — invoke `duck` yourself | no |
| Kimi Code CLI | not guaranteed — invoke `duck` yourself | no |
| Cursor, Zed, Copilot, Amp, others | no — invoke `duck` yourself | no |

Tested means a real session on the author's machine loaded the rules before the first reply. Reloading after the conversation is compacted has not been tested in a real session on either host; only the hook's answer to that input has.

## Adjust

Say it in the conversation: shorter, more detail, step by step, or only the result at the end. The agent follows that for the rest of the conversation and saves nothing.

## Uninstall

Type `/i-am-the-duck:unduck` in Claude Code or `$i-am-the-duck:unduck` in Codex. It shows you what will go, waits for your yes, then removes the plugin. Or by hand:

```
claude plugin uninstall i-am-the-duck@i-am-the-duck   # add --scope project|local if you installed it there
codex plugin remove i-am-the-duck@i-am-the-duck
```

Removing the plugin by hand leaves the marketplace you added still configured; `/i-am-the-duck:unduck` offers to remove that too. By hand it is `claude plugin marketplace remove i-am-the-duck`, or `codex plugin marketplace remove i-am-the-duck`.

## What is inside

| Path | What it is |
|---|---|
| `skills/duck/SKILL.md` | The rules. This is what the agent reads. |
| `skills/unduck/` | The uninstall skill. |
| `hooks/` | The session-start hook: it includes the complete rules at session start and after compaction. |
| `.claude-plugin/`, `.codex-plugin/`, `.agents/` | The files Claude Code and Codex read to find the plugin. |
| `gemini-extension.json`, `GEMINI.md`, `qwen-extension.json`, `kimi.plugin.json` | The same for the other hosts. `GEMINI.md` imports the rules rather than copying them. |
| `INSTALL.md` | Install, update and uninstall, one section per host. |

## Where it came from

Long agent sessions grow a private language. "All green" when the run said one failed. "Phase C" from a plan the user never opened. The user kept the right to decide and lost the information needed to decide.

## License

MIT

Maintainers: the optional [evaluation workflow](evals/README.md) stays outside the installed skills and hooks.
