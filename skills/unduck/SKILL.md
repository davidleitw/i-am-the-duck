---
name: unduck
description: Remove i-am-the-duck from this machine. Run only when the user asks for it.
disable-model-invocation: true
---

The user typed this. Nothing is removed until they have seen what will go and said yes.

1. Find how it is installed, using the plugin commands of the host you are running in.

   - Claude Code: `claude plugin list`. Note the scope shown for `i-am-the-duck`, and say so if it is listed at more than one.
   - Codex: `codex plugin list`. Note the marketplace it came from.
   - Any other host: find its own plugin commands (`<its command> plugin --help`, or its documentation) and use those. If it has no way to manage plugins, say so and stop; do not delete files yourself.

2. Tell the user what you found and the exact commands you are about to run. Wait for a yes.

3. Remove the plugin, then the marketplace it came from.

   Claude Code:

   ```
   claude plugin uninstall i-am-the-duck@i-am-the-duck --scope <the scope from step 1>
   claude plugin marketplace remove i-am-the-duck
   ```

   Codex:

   ```
   codex plugin remove i-am-the-duck@i-am-the-duck
   codex plugin marketplace remove i-am-the-duck
   ```

   Do not pass `--prune`; it removes other plugins as well. Leave the marketplace in place if it holds other plugins the user still wants. If a command is refused or fails, show the user the command and what it said, and ask them to run it themselves after this session.

Tell the user to start a new session; this one still has the rules loaded, which does not mean the removal failed.
