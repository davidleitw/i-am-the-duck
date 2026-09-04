#!/usr/bin/env node
// SessionStart hook. Reads the event from stdin and prints one instruction back as
// additionalContext. Fails open: on any error it exits 0 with no output, and it waits
// at most one second for stdin, so it can never keep a session from starting.
import { stdin, stdout } from 'node:process';

const LOAD = 'Load the duck skill (listed as i-am-the-duck:duck) now, before your first reply.';
const RELOAD = 'Your context was just compacted. Load the duck skill (listed as i-am-the-duck:duck) again before continuing. The user may no longer see where earlier terms were explained, so in your next report explain every project label again.';

function readStdin(ms) {
  return new Promise((resolve) => {
    let data = '';
    const finish = () => { clearTimeout(timer); stdin.removeAllListeners(); stdin.destroy(); resolve(data); };
    const timer = setTimeout(finish, ms);
    stdin.setEncoding('utf8');
    stdin.on('data', (chunk) => { data += chunk; });
    stdin.on('end', finish);
    stdin.on('error', finish);
  });
}

try {
  let source = '';
  try { source = JSON.parse(await readStdin(1000)).source ?? ''; } catch { /* no readable payload: treat as a fresh start */ }
  stdout.write(JSON.stringify({
    hookSpecificOutput: { hookEventName: 'SessionStart', additionalContext: source === 'compact' ? RELOAD : LOAD },
  }) + '\n');
} catch { /* fail open */ }
process.exitCode = 0;
