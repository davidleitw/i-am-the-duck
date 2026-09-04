# Working in this repo

i-am-the-duck is a Claude Code + Codex plugin: one rule skill (`skills/duck`), one uninstall skill (`skills/unduck`), one SessionStart hook (`hooks/`). Nothing runs except node.

## The rule about the rules

`skills/duck/SKILL.md` is read by the agent at every session start. Every word in it must be one the user would use themselves: no jokes, no project vocabulary, no names invented for this plugin. The duck and the story live in `README.md`. Keep the file under 50 lines; an example is one line.

## Language

`README.md` is English. `docs/README.zh-TW.md` mirrors it; change both in the same commit. `TODO.md` is Traditional Chinese. Code, comments, this file, and commit messages are English.

## Version

`version` is in `.claude-plugin/plugin.json` and `.codex-plugin/plugin.json`. Bump both in the same commit.

## Checks before committing

```
node --check hooks/session-start.mjs skills/unduck/uninstall.mjs
echo '{"source":"compact"}' | node hooks/session-start.mjs
node skills/unduck/uninstall.mjs          # read-only: lists what an older install left behind
for f in .claude-plugin/*.json .codex-plugin/*.json .agents/plugins/*.json hooks/hooks.json; do node -e "JSON.parse(require('fs').readFileSync('$f','utf8'))"; done
```

A change to the hook or a manifest is only verified by a local install: `claude plugin marketplace add <this directory>`, `claude plugin install i-am-the-duck@i-am-the-duck`, then a new session.

## TODO.md

Backlog only. Rules are at the top of the file.
