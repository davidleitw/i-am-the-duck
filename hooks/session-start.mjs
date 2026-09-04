#!/usr/bin/env node
// SessionStart hook. Reads the event from stdin and prints one instruction back as
// additionalContext. Fails open: on any error it exits 0 with no output, so it can
// never keep Claude Code or Codex from starting a session.
import { readFileSync } from 'node:fs';

const LOAD = 'Load the duck skill (listed as i-am-the-duck:duck) now, before your first reply.';
const RELOAD = 'Your context was just compacted. Load the duck skill (listed as i-am-the-duck:duck) again before continuing. The user may no longer see where earlier terms were explained, so in your next report explain every project label again.';

try {
  let source = '';
  try { source = JSON.parse(readFileSync(0, 'utf8')).source ?? ''; } catch { /* no readable payload: treat as a fresh start */ }
  const text = source === 'compact' ? RELOAD : LOAD;
  process.stdout.write(JSON.stringify({
    hookSpecificOutput: { hookEventName: 'SessionStart', additionalContext: text },
  }) + '\n');
} catch { /* fail open */ }
process.exit(0);
