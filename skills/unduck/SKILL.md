---
name: unduck
description: Remove i-am-the-duck from this machine, including what an older hand-installed version left behind. Run only when the user asks for it.
disable-model-invocation: true
---

# unduck

The user typed this. Nothing is deleted until they have seen the list and said yes.

1. Find what the older version left behind. Run, from this skill's directory:

   ```
   node uninstall.mjs
   ```

   Without flags it only prints. It reports skill directories carrying a `.rubberduck` marker, the SessionStart hook line that points at `~/.rubberduck/hooks/`, and the `~/.rubberduck` directory. It refuses to continue if a settings file is not valid JSON; report that and stop.

2. Find how the plugin itself is installed. In Claude Code run `claude plugin list` and note the scope shown for `i-am-the-duck`. In Codex run `codex plugin list`.

3. Show the user one list: the plugin and its scope, plus every item from step 1. Wait for a yes.

4. Remove the leftovers:

   ```
   node uninstall.mjs --yes
   ```

   Edited settings files get a backup next to them, named `<file>.bak-<timestamp>`.

5. Remove the plugin, last. Claude Code: `claude plugin uninstall i-am-the-duck@i-am-the-duck --scope <scope from step 2>`. Codex: `codex plugin remove i-am-the-duck@i-am-the-duck`. If the command is refused or fails, print it and ask the user to run it after this session. Do not remove the marketplace and do not pass `--prune`.

6. Run `node uninstall.mjs` once more and confirm it reports nothing left. Tell the user to start a new session; this one still has the rules loaded, which does not mean the removal failed.
