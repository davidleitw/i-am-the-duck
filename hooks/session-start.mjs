#!/usr/bin/env node
// SessionStart hook. Reads the event and adjacent skill, then provides the rules
// as additionalContext. Fails open with exit 0 and no output on errors. The stdin
// wait is bounded to one second; the host's hook timeout bounds the whole command.
import { stdin, stdout } from 'node:process';
import { readFile } from 'node:fs/promises';

const SKILL_PATH = new URL('../skills/duck/SKILL.md', import.meta.url);
const LOAD = 'The complete duck instructions below are already loaded. Apply them before your first reply. Do not search for or reread the skill, and do not tell the user you loaded it.';
const RELOAD = 'Your context was just compacted. The complete duck instructions below are already reloaded. Apply them before continuing. Do not search for or reread the skill, and do not tell the user you loaded it.';

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
  const skill = await readFile(SKILL_PATH, 'utf8');
  stdout.write(JSON.stringify({
    hookSpecificOutput: {
      hookEventName: 'SessionStart',
      additionalContext: `${source === 'compact' ? RELOAD : LOAD}\n\n${skill}`,
    },
  }) + '\n');
} catch { /* fail open */ }
process.exitCode = 0;
