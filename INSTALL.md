# How to install

Claude Code and Codex are the two hosts this plugin is built for and tested on: a hook loads the rules at every session start and again after context compaction, so you type nothing. Gemini CLI loads them through `GEMINI.md` instead. On every other host the rules are there but nothing loads them for you, so you invoke them yourself once per session.

Needs `node` 18 or newer on your PATH for the hook. Gemini CLI reads `hooks/hooks.json` too, but the hook checks for a variable only Claude Code and Codex set, so it does nothing there and prints nothing.

<details>
<summary><strong>Claude Code</strong></summary>

### Install

```
claude plugin marketplace add davidleitw/i-am-the-duck
claude plugin install i-am-the-duck@i-am-the-duck
```

Start a new session. The hook loads the rules before the first reply.

### Verify

```
claude plugin list
```

To load the rules by hand mid-session, type `/i-am-the-duck:duck`.

### Update

```
claude plugin marketplace update i-am-the-duck
claude plugin update i-am-the-duck@i-am-the-duck
```

Restart to apply.

### Uninstall

```
claude plugin uninstall i-am-the-duck@i-am-the-duck
claude plugin marketplace remove i-am-the-duck
```

Add `--scope project` or `--scope local` to the first command if you installed it there. Or type `/i-am-the-duck:unduck` and let the plugin walk you through it.

</details>

<details>
<summary><strong>Codex</strong></summary>

### Install

```
codex plugin marketplace add davidleitw/i-am-the-duck
codex plugin add i-am-the-duck@i-am-the-duck
```

Open `/hooks` once, review the session-start hook and trust it. Until you do, Codex skips it and nothing loads the rules. Then start a new session.

### Verify

```
codex plugin list
```

To load the rules by hand mid-session, type `$i-am-the-duck:duck`.

### Update

```
codex plugin marketplace upgrade i-am-the-duck
codex plugin remove i-am-the-duck@i-am-the-duck
codex plugin add i-am-the-duck@i-am-the-duck
```

The hook file changes with an update, so `/hooks` asks you to trust it again.

### Uninstall

```
codex plugin remove i-am-the-duck@i-am-the-duck
codex plugin marketplace remove i-am-the-duck
```

Or type `$i-am-the-duck:unduck`.

</details>

<details>
<summary><strong>Gemini CLI</strong> — not tested by us</summary>

Gemini CLI has no plugin marketplace. Installing this repo as an extension makes `GEMINI.md` part of every session, and that file imports the rules, so they apply from the first message.

### Install

```
gemini extensions install https://github.com/davidleitw/i-am-the-duck
```

`git` must be installed.

### Verify

```
gemini extensions list
```

### Update

```
gemini extensions update i-am-the-duck
```

### Uninstall

```
gemini extensions uninstall i-am-the-duck
```

</details>

<details>
<summary><strong>Qwen Code</strong> — not tested by us</summary>

### Install

```
qwen extensions install davidleitw/i-am-the-duck
```

Nothing changes until you invoke the rules. Type `/duck` at the start of a session.

### Verify

```
qwen extensions list
```

Then in a session, run `/skills` and confirm `duck` is listed.

### Update

```
qwen extensions update i-am-the-duck
```

### Uninstall

```
qwen extensions uninstall i-am-the-duck
```

</details>

<details>
<summary><strong>Kimi Code CLI</strong> — not tested by us</summary>

### Install

In a Kimi Code session: run `/plugins`, choose **Custom**, paste `https://github.com/davidleitw/i-am-the-duck`, press Enter, then choose **Trust and install**.

Type `/skill:duck` at the start of a session to load the rules.

### Verify

Run `/plugins` and confirm **I Am the Duck** is listed, then check that `/skill:duck` works. Start a new session, or `/reload`, after installing.

### Update and uninstall

Run `/plugins`, move to **I Am the Duck**, and use the update and remove keys the list shows. We have not run this host, so we are not quoting a keystroke we have not seen.

</details>

<details>
<summary><strong>Cursor, Zed, GitHub Copilot, Amp, and any other agent-skills harness</strong> — not tested by us</summary>

These read `SKILL.md` files directly, so no conversion is needed.

### Install

```
npx skills add davidleitw/i-am-the-duck --skill duck                 # this project
npx skills add davidleitw/i-am-the-duck --skill duck -g              # all projects
npx skills add davidleitw/i-am-the-duck --skill duck -a cursor -y    # one agent only
```

`--skill duck` installs the rules and nothing else. Without it you also get `unduck`, whose only job is to uninstall this plugin, on a host that may or may not honour the setting that stops the agent invoking it on its own.

Without that CLI, copy the folder into whatever directory your agent scans:

```
git clone https://github.com/davidleitw/i-am-the-duck
mkdir -p ~/.cursor/skills          # Cursor. Use your agent's own path.
cp -R i-am-the-duck/skills/duck ~/.cursor/skills/
```

Start a new session and type `/duck`. Nothing loads the rules for you here, so do it once per session.

### Verify

```
npx skills list
npx skills ls -g    # if you installed globally
```

Or type `/` in a session and confirm `duck` is listed.

### Update

```
npx skills update duck
npx skills update duck -g    # if you installed globally
```

Or re-copy the folder after `git pull`.

### Uninstall

```
npx skills remove duck
npx skills remove duck -g    # if you installed globally
```

Or delete the `duck` folder from the skills directory it landed in.

</details>

## If you use a host that is not listed

The rules are one file, `skills/duck/SKILL.md`, with nothing host-specific in it. Any agent that can be given a block of instructions can use it: paste it into whatever persistent-rules file your agent reads, and it applies from then on.

If you get it working somewhere, a pull request adding a block above is welcome. Keep `skills/duck/SKILL.md` as the only copy of the rules — a second copy drifts.
