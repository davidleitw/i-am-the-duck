#!/usr/bin/env node
// Finds and removes what the older, hand-installed version of this plugin left behind:
// skill directories with a `.rubberduck` marker, the SessionStart hook line pointing at
// .rubberduck/hooks/session-start.mjs, and the known files inside ~/.rubberduck.
//
// No flag: print what would be removed, change nothing.  --yes: remove it.
// Both settings files are parsed before anything is removed; an unreadable one aborts.
// A settings file is re-read right before it is written and left alone if it changed in
// between; the edited copy keeps the file mode, is backed up next to the original, and is
// written through a temp file plus rename. Unknown files inside ~/.rubberduck are kept.
import { copyFileSync, existsSync, readdirSync, readFileSync, renameSync, rmSync, rmdirSync, statSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

const HOME = homedir();
const MARKER = '.rubberduck';
const OLD_STATE = join(HOME, '.rubberduck');
const OLD_HOOK_TAIL = '.rubberduck/hooks/session-start.mjs';
const OLD_STATE_FILES = ['hooks', 'backups', 'state.json', 'findings.jsonl', 'rulings.md', 'holdout-v1.md'];
const SKILL_DIRS = ['duck', 'digest'].flatMap((s) => [join(HOME, '.claude', 'skills', s), join(HOME, '.agents', 'skills', s)]);
const SETTINGS = [join(HOME, '.claude', 'settings.json'), join(HOME, '.codex', 'hooks.json')];
const apply = process.argv.includes('--yes');
const stamp = new Date().toISOString().replace(/[:.]/g, '-');

function parseObject(raw, file) {
  const value = JSON.parse(raw);
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(`${file} is not a JSON object`);
  return value;
}

const handlersOf = (group) => (Array.isArray(group?.hooks) ? group.hooks : []);
const isOldHook = (h) => h && h.type === 'command' && typeof h.command === 'string' && h.command.includes(OLD_HOOK_TAIL);

function withoutOldHook(groups) {
  return (Array.isArray(groups) ? groups : [])
    .map((g) => (Array.isArray(g?.hooks) ? { ...g, hooks: g.hooks.filter((h) => !isOldHook(h)) } : g))
    .filter((g) => !(Array.isArray(g?.hooks) && g.hooks.length === 0));
}

const found = [];

for (const dir of SKILL_DIRS) {
  if (!existsSync(dir)) continue;
  if (existsSync(join(dir, MARKER))) found.push({ label: `skill directory ${dir}`, remove: () => rmSync(dir, { recursive: true }) });
  else console.log(`keep         ${dir} (no ${MARKER} marker, not installed by the older version)`);
}

for (const file of SETTINGS) {
  if (!existsSync(file)) continue;
  let raw, settings;
  try { raw = readFileSync(file, 'utf8'); settings = parseObject(raw, file); } catch (e) { console.error(`error: ${e.message}`); process.exit(1); }
  const groups = settings.hooks?.SessionStart;
  if (!(Array.isArray(groups) ? groups : []).some((g) => handlersOf(g).some(isOldHook))) continue;
  found.push({
    label: `SessionStart hook in ${file}`,
    remove: () => {
      if (readFileSync(file, 'utf8') !== raw) { console.log(`skipped      ${file} changed since it was read; run again`); return; }
      const backup = `${file}.bak-${stamp}`;
      copyFileSync(file, backup);
      const kept = withoutOldHook(groups);
      const hooks = { ...settings.hooks };
      if (kept.length) hooks.SessionStart = kept; else delete hooks.SessionStart;
      const next = { ...settings };
      if (Object.keys(hooks).length) next.hooks = hooks; else delete next.hooks;
      const tmp = `${file}.tmp-${process.pid}`;
      writeFileSync(tmp, JSON.stringify(next, null, 2) + '\n', { mode: statSync(file).mode });
      renameSync(tmp, file);
      console.log(`             backup ${backup}`);
    },
  });
}

if (existsSync(OLD_STATE)) {
  const entries = readdirSync(OLD_STATE);
  const known = entries.filter((e) => OLD_STATE_FILES.includes(e));
  const unknown = entries.filter((e) => !OLD_STATE_FILES.includes(e));
  if (known.length === 0) console.log(`keep         ${OLD_STATE} (none of the older version's files are in it)`);
  else found.push({
    label: `${OLD_STATE} (${known.join(', ')})${unknown.length ? `, keeping ${unknown.join(', ')}` : ''}`,
    remove: () => {
      for (const e of known) rmSync(join(OLD_STATE, e), { recursive: true });
      if (unknown.length === 0) rmdirSync(OLD_STATE);
    },
  });
}

if (found.length === 0) {
  console.log('nothing left from the older version');
} else {
  for (const item of found) {
    if (apply) { item.remove(); console.log(`removed      ${item.label}`); }
    else console.log(`would remove ${item.label}`);
  }
  if (!apply) console.log('\nrun again with --yes to remove these');
}
