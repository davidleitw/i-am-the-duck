#!/usr/bin/env node
// Finds and removes what the older, hand-installed version of this plugin left behind:
// skill directories with a `.rubberduck` marker, the SessionStart hook line pointing at
// ~/.rubberduck/hooks/, and ~/.rubberduck itself.
//
// No flag: print what would be removed, change nothing.  --yes: remove it.
// Both settings files are parsed before anything is removed; an unreadable one aborts.
// Edited settings files are backed up next to themselves and written through a temp
// file plus rename.
import { copyFileSync, existsSync, readFileSync, renameSync, rmSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

const HOME = homedir();
const MARKER = '.rubberduck';
const OLD_STATE = join(HOME, '.rubberduck');
const OLD_HOOK = join(OLD_STATE, 'hooks', 'session-start.mjs');
const SKILL_DIRS = ['duck', 'digest'].flatMap((s) => [join(HOME, '.claude', 'skills', s), join(HOME, '.agents', 'skills', s)]);
const SETTINGS = [join(HOME, '.claude', 'settings.json'), join(HOME, '.codex', 'hooks.json')];
const apply = process.argv.includes('--yes');
const stamp = new Date().toISOString().replace(/[:.]/g, '-');

function readJsonObject(p) {
  if (!existsSync(p)) return null;
  const value = JSON.parse(readFileSync(p, 'utf8'));
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(`${p} is not a JSON object`);
  return value;
}

const isOldHook = (h) => h && h.type === 'command' && typeof h.command === 'string' && h.command.includes(OLD_HOOK);

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
  let settings;
  try { settings = readJsonObject(file); } catch (e) { console.error(`error: ${e.message}`); process.exit(1); }
  if (!settings) continue;
  const groups = settings.hooks?.SessionStart;
  if (!(Array.isArray(groups) ? groups : []).some((g) => (g?.hooks ?? []).some(isOldHook))) continue;
  found.push({
    label: `SessionStart hook in ${file}`,
    remove: () => {
      const backup = `${file}.bak-${stamp}`;
      copyFileSync(file, backup);
      const kept = withoutOldHook(groups);
      const hooks = { ...settings.hooks };
      if (kept.length) hooks.SessionStart = kept; else delete hooks.SessionStart;
      const next = { ...settings };
      if (Object.keys(hooks).length) next.hooks = hooks; else delete next.hooks;
      const tmp = `${file}.tmp-${process.pid}`;
      writeFileSync(tmp, JSON.stringify(next, null, 2) + '\n');
      renameSync(tmp, file);
      console.log(`             backup ${backup}`);
    },
  });
}

if (existsSync(OLD_STATE)) found.push({ label: `directory ${OLD_STATE}`, remove: () => rmSync(OLD_STATE, { recursive: true }) });

if (found.length === 0) {
  console.log('nothing left from the older version');
  process.exit(0);
}
for (const item of found) {
  if (apply) { item.remove(); console.log(`removed      ${item.label}`); }
  else console.log(`would remove ${item.label}`);
}
if (!apply) console.log('\nrun again with --yes to remove these');
