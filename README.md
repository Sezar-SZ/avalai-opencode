# AvalAI → OpenCode helper 🤝🤖

A tiny **run-once** helper that asks AvalAI for its current chat-model catalog and adds those models to OpenCode as `provider.avalai`.


```bash
./run.sh
```

## 🚀 Quick start

You need Python 3, OpenCode, and an AvalAI API key.

```bash
cp .env.example .env
nano .env
```

Put the real key in `.env`:

```dotenv
AVALAI_API_KEY='your-real-avalai-key'
```

Then:

```bash
chmod 600 .env
./run.sh
```

The real `.env` is covered by `.gitignore`. Do not commit it, paste it into an issue, or include it in screenshots.

## 🔑 How the helper reads the key

The helper can read `AVALAI_API_KEY` from:

1. This project's `.env` file
2. Your shell environment
3. A hidden terminal prompt

When `.env` and the shell contain different keys, the helper asks which one to use. It never prints the key; it only displays its source and character count.

You can also skip `.env` for a one-off run:

```bash
AVALAI_API_KEY='your-real-key' ./run.sh
```

The helper reads `.env` as data. It does **not** execute it as shell code.

## 🌐 Route selection

The helper asks you to choose one of AvalAI's three officially documented API routes:

```text
🌐 Choose an official AvalAI route
  1) Primary Iran route — api.avalai.ir (default)
  2) Iran fallback route — api.avalapis.ir
  3) Cloudflare route — api.avalai.org
👉 Choice [1]:
```

Press **Enter** to use `https://api.avalai.ir/v1`.

## 🔐 How OpenCode should store the key

During setup you choose:

```text
🔐 How should OpenCode read the AvalAI key?
  1) Environment variable — {env:AVALAI_API_KEY} (recommended)
  2) Hard-code it in opencode.json (simpler, but less secure)
👉 Choice [1]:
```

### Option 1: environment variable — recommended 🌱

OpenCode receives this setting:

```json
"apiKey": "{env:AVALAI_API_KEY}"
```

OpenCode must see the variable whenever it starts. From this project directory:

```bash
set -a
. ./.env
set +a
opencode
```

Or export the variable through your preferred shell/secret manager before running OpenCode.

> OpenCode does not automatically load this project's `.env`; the helper does.

### Option 2: hard-code the key ⚠️

The real key is written directly under `provider.avalai.options.apiKey` in:

```text
~/.config/opencode/opencode.json
```

This is convenient, but less secure. The helper sets the config permission to `0600`, meaning only your user should be able to read it. Backups may also contain the key after later runs, so keep them private.

## 🧩 Existing OpenCode settings are preserved

The helper adds or replaces only:

```text
provider.avalai
```

It leaves all other providers and unrelated settings semantically unchanged, including OpenAI, Anthropic, Google, OpenRouter, local providers, MCP servers, agents, permissions, plugins, `model`, and `small_model`.

A defensive check runs before writing: if anything outside `provider.avalai` changed in memory, the helper stops.


## 💾 Backup location

Before changing an existing config, the helper creates:

```text
~/.config/opencode/opencode.json.backup-YYYYMMDD-HHMMSS
```

Example:

```text
~/.config/opencode/opencode.json.backup-20260803-143012
```

The exact backup path is printed after a successful run.

Find the newest backup:

```bash
ls -1t ~/.config/opencode/opencode.json.backup-* 2>/dev/null | head -n 1
```

Restore one:

```bash
cp ~/.config/opencode/opencode.json.backup-YYYYMMDD-HHMMSS \
   ~/.config/opencode/opencode.json
chmod 600 ~/.config/opencode/opencode.json
```

## 🧯 API-key errors

For a `401 Unauthorized`, the helper now prints:

- the selected endpoint
- whether the key came from `.env`, the shell, or the hidden prompt
- AvalAI's short error message, when provided

It never prints the credential.

Common checks:

```bash
# Make sure the example placeholder is gone
grep '^AVALAI_API_KEY=' .env

# See whether your shell already has a different key
[[ -n ${AVALAI_API_KEY:-} ]] && echo 'shell key exists'
```

When both sources differ, rerun `./run.sh` and explicitly choose the correct one.

## 🔄 Refresh later

Run the same command again:

```bash
./run.sh
```

Only `provider.avalai` is refreshed.