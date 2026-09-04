---
name: unduck
description: Remove i-am-the-duck from this machine, including what an older hand-installed version left behind. Run only when the user asks for it.
disable-model-invocation: true
---

The user typed this. Nothing is deleted until they have seen the list and said yes.

1. Find this skill's directory: the host tells you where it loaded this file from. Check that `uninstall.mjs` sits next to it, then run it with the absolute path:

   ```
   node "<that directory>/uninstall.mjs"
   ```

   Without flags it only prints. It lists skill directories carrying a `.rubberduck` marker, the SessionStart hook line that points at `.rubberduck/hooks/session-start.mjs`, and the known files inside `~/.rubberduck`. If it stops because a settings file is not valid JSON, report that and stop.

2. Find how the plugin itself is installed. Claude Code: `claude plugin list`, note the scope shown for `i-am-the-duck`. Codex: `codex plugin list`.

3. Show the user one list: the plugin and its scope, plus every line from step 1. Wait for a yes.

4. Remove the leftovers:

   ```
   node "<that directory>/uninstall.mjs" --yes
   ```

   It prints what it removed. If that differs from the list the user saw, stop and show the difference. Edited settings files get a backup next to them, named `<file>.bak-<timestamp>`.

5. Remove the plugin, last. Claude Code: `claude plugin uninstall i-am-the-duck@i-am-the-duck --scope <scope from step 2>`. Codex: `codex plugin remove i-am-the-duck@i-am-the-duck`. If the command is refused or fails, print it and ask the user to run it after this session. Do not remove the marketplace and do not pass `--prune`.

6. Run step 1 once more and confirm it reports nothing left. Tell the user to start a new session; this one still has the rules loaded, which does not mean the removal failed.
