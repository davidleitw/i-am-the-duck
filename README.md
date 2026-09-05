<p align="center"><img src="assets/hero.png" alt="A robot explains its code to a rubber duck." width="800"></p>

# i-am-the-duck

Rubber duck debugging, reversed. You are the duck.

**[中文說明](docs/README.zh-TW.md)**

## What this is

Rubber duck debugging is the old trick where you explain your code, line by line, to a rubber duck on your desk. Somewhere in the explanation you find the bug yourself. The duck does nothing. Having to say it out loud, in plain words, is what works.

This plugin turns that around. The coding agent does the work, and you are the duck. It has to explain every change in words you can follow without reading the code or the tool output: what it is about to change and why, what came of it, what that rests on, and what it has not checked.

It started as a joke. It stayed because an agent that has to explain a change in plain words is also an agent that notices when the change has no good reason.

## What changes

Without it, a long session drifts into shorthand:

> Phase C done, all green, merged the fix into the pipeline.

With it:

> Moved the timeout check from the hook into the daemon, so a restart no longer skips it. `npm test`: 24 passed, 0 failed. I did not run the Codex side; it is not installed here.

Three habits:

- **Before changing anything** with one clear purpose, one or two sentences: what will change and why. Reading, searching, and running tests need no announcement.
- **After**, what it produced, what that rests on, and what is not confirmed. Every number comes with the command that produced it. "Passes" without a run behind it is not allowed.
- **Words** are the ones you and the repository already use. One-off steps get no name. A new name appears only when it will come up again, and the first time it does, it is explained in one sentence. Labels from plans and tickets you never read get explained too.

Decisions come with options and evidence. Work handed to another agent comes back summarized, with whether it was checked.

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

Needs `node` 18 or newer on your PATH. Start a new session: a small hook runs at every session start and after context compaction and tells the agent to load the rules, so you type nothing. In Codex, open `/hooks` once, review the hook and trust it; until you do, Codex skips it.

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
| `hooks/` | The session-start hook: a short instruction telling the agent to load the rules, or to reload them after compaction. |
| `.claude-plugin/`, `.codex-plugin/`, `.agents/` | The files Claude Code and Codex read to find the plugin. |
| `gemini-extension.json`, `GEMINI.md`, `qwen-extension.json`, `kimi.plugin.json` | The same for the other hosts. `GEMINI.md` imports the rules rather than copying them. |
| `INSTALL.md` | Install, update and uninstall, one section per host. |

## Where it came from

Long agent sessions grow a private language. "All green" when the run said one failed. "Phase C" from a plan the user never opened. The user kept the right to decide and lost the information needed to decide.

## License

MIT
