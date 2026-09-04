<p align="center"><img src="assets/hero.png" alt="A robot explains its code to a rubber duck." width="800"></p>

# i-am-the-duck

Rubber duck debugging, reversed. You are the duck.

**[中文說明](docs/README.zh-TW.md)**

## What this is

Rubber duck debugging is the old trick where you explain your code, line by line, to a rubber duck on your desk. Somewhere in the explanation you find the bug yourself. The duck does nothing. Having to say it out loud, in plain words, is what works.

This plugin turns that around. The coding agent does the work, and you are the duck. It has to explain every step in words you can follow without reading the code or the tool output: what it is about to change and why, what came of it, what that rests on, and what it has not checked.

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

Start a new session. A small hook runs at every session start and after context compaction and tells the agent to load the rules; you type nothing. Codex may ask you once to trust the hook.

If the agent drifts back into shorthand, type `/duck` in Claude Code or `$duck` in Codex.

## Adjust

Say it in the conversation: shorter, more detail, step by step, or only the result at the end. The agent follows that for the rest of the conversation and saves nothing.

## Uninstall

Type `/unduck` in Claude Code or `$unduck` in Codex. It lists what it will remove, waits for your yes, cleans up anything left by an older hand-installed version, then removes the plugin. Or by hand:

```
claude plugin uninstall i-am-the-duck@i-am-the-duck
codex plugin remove i-am-the-duck@i-am-the-duck
```

## What is inside

| Path | What it is |
|---|---|
| `skills/duck/SKILL.md` | The rules. This is what the agent reads. |
| `skills/unduck/` | The uninstall skill and the script it runs. |
| `hooks/` | The session-start hook: one sentence telling the agent to load the rules. |
| `.claude-plugin/`, `.codex-plugin/`, `.agents/` | The files each host reads to find the plugin. |

## Where it came from

Long agent sessions grow a private language. "All green" when the run said one failed. "Phase C" from a plan the user never opened. The user kept the right to decide and lost the information needed to decide.

## License

MIT
