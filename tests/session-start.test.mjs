import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { copyFile, mkdir, mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

const root = new URL('..', import.meta.url);
const sourceHook = new URL('hooks/session-start.mjs', root);
const sourceSkill = new URL('skills/duck/SKILL.md', root);

async function runHook(hookPath, cwd, input) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [hookPath], { cwd });
    let stdout = '';
    let stderr = '';
    child.stdout.setEncoding('utf8');
    child.stderr.setEncoding('utf8');
    child.stdout.on('data', (chunk) => { stdout += chunk; });
    child.stderr.on('data', (chunk) => { stderr += chunk; });
    child.on('error', reject);
    child.on('close', (code, signal) => resolve({ code, signal, stdout, stderr }));
    child.stdin.end(typeof input === 'string' ? input : JSON.stringify(input));
  });
}

async function makeFixture(withSkill) {
  const fixture = await mkdtemp(join(tmpdir(), 'duck session-start '));
  await mkdir(join(fixture, 'hooks'), { recursive: true });
  if (withSkill) await mkdir(join(fixture, 'skills', 'duck'), { recursive: true });
  await copyFile(sourceHook, join(fixture, 'hooks', 'session-start.mjs'));
  if (withSkill) await copyFile(sourceSkill, join(fixture, 'skills', 'duck', 'SKILL.md'));
  return fixture;
}

test('startup includes the complete adjacent skill from a different cwd', async (t) => {
  const fixture = await makeFixture(true);
  const cwd = await mkdtemp(join(tmpdir(), 'duck hook cwd-'));
  t.after(async () => Promise.all([
    rm(fixture, { recursive: true, force: true }),
    rm(cwd, { recursive: true, force: true }),
  ]));

  const result = await runHook(join(fixture, 'hooks', 'session-start.mjs'), cwd, { source: 'startup' });
  const output = JSON.parse(result.stdout);
  const skill = await readFile(sourceSkill, 'utf8');
  assert.equal(result.code, 0);
  assert.equal(result.signal, null);
  assert.equal(result.stderr, '');
  assert.ok(fixture.includes(' '));
  assert.ok(output.hookSpecificOutput.additionalContext.includes(skill));
  assert.ok(output.hookSpecificOutput.additionalContext.includes('already loaded'));

  const invalid = await runHook(join(fixture, 'hooks', 'session-start.mjs'), cwd, '{');
  assert.equal(invalid.code, 0);
  assert.equal(invalid.signal, null);
  assert.ok(JSON.parse(invalid.stdout).hookSpecificOutput.additionalContext.includes(skill));
});

test('compact includes the complete adjacent skill', async (t) => {
  const fixture = await makeFixture(true);
  const cwd = await mkdtemp(join(tmpdir(), 'duck hook cwd-'));
  t.after(async () => Promise.all([
    rm(fixture, { recursive: true, force: true }),
    rm(cwd, { recursive: true, force: true }),
  ]));

  const result = await runHook(join(fixture, 'hooks', 'session-start.mjs'), cwd, { source: 'compact' });
  const output = JSON.parse(result.stdout);
  const skill = await readFile(sourceSkill, 'utf8');
  assert.equal(result.code, 0);
  assert.ok(output.hookSpecificOutput.additionalContext.includes(skill));
  assert.ok(output.hookSpecificOutput.additionalContext.includes('context was just compacted'));
});

test('missing skill fails open with no output', async (t) => {
  const fixture = await makeFixture(false);
  const cwd = await mkdtemp(join(tmpdir(), 'duck hook cwd-'));
  t.after(async () => Promise.all([
    rm(fixture, { recursive: true, force: true }),
    rm(cwd, { recursive: true, force: true }),
  ]));

  const result = await runHook(join(fixture, 'hooks', 'session-start.mjs'), cwd, { source: 'startup' });
  assert.equal(result.code, 0);
  assert.equal(result.signal, null);
  assert.equal(result.stdout, '');
});
