# Setup

[← Back to README](../README.md)

## Get an API key

intervals.icu → **Settings** → **Developer Settings** → **API key**.

The server reads it from the `INTERVALS_ICU_API_KEY` environment variable, or
from a `.env` file in the working directory. The older `INTERVALS_API_KEY`
name still works but prints a warning.

## On a Mac: keep it in the Keychain (recommended)

Don't leave the key in plain text in config files or your shell profile. Store it
in the macOS Keychain instead:

```sh
security add-generic-password -a "$USER" -s INTERVALS_ICU_API_KEY -w
```

With `-w` and no value, `security` asks for the key, so it doesn't end up in
your shell history. To replace a stored key later, add `-U`.

### CLI and Claude Code: load it into your shell

Add this line to `~/.zshrc` (or `~/.bashrc`):

```sh
export INTERVALS_ICU_API_KEY=$(security find-generic-password -w -a "$USER" -s INTERVALS_ICU_API_KEY)
```

Then run `source ~/.zshrc`. Programs you start from that shell, including
`claude`, get the key from the Keychain, and it's never written to a file.

### Claude Desktop: read the Keychain when the server starts

The shell profile doesn't help here: apps launched from the Dock don't read
`~/.zshrc`. Have the server read the Keychain when it starts instead, in
`claude_desktop_config.json` (Claude Desktop → Settings → Developer → Edit
Config):

```json
{
  "mcpServers": {
    "intervals-icu-planner": {
      "command": "/bin/sh",
      "args": [
        "-c",
        "INTERVALS_ICU_API_KEY=$(security find-generic-password -w -s INTERVALS_ICU_API_KEY) exec /opt/homebrew/bin/uvx intervals-icu-planner-mcp"
      ]
    }
  }
}
```

Apps launched from the Dock don't get Homebrew's `PATH` either, so give the
full path to `uvx` (`which uvx` shows it; `/opt/homebrew/bin/uvx` on Apple
silicon).

### Claude Code without the key in your shell

The same wrapper works in Claude Code:

```sh
claude mcp add -s user intervals-icu-planner -- /bin/sh -c \
  'INTERVALS_ICU_API_KEY=$(security find-generic-password -w -s INTERVALS_ICU_API_KEY) exec uvx intervals-icu-planner-mcp'
```

### Check or remove the stored key

To check the key is stored, run
`security find-generic-password -s INTERVALS_ICU_API_KEY`. It shows the entry
but not the key. To remove it, run
`security delete-generic-password -s INTERVALS_ICU_API_KEY`.

## Plain config (any OS)

You need [uv](https://docs.astral.sh/uv/) installed. This stores the key in
plain text in the config file; on a Mac, prefer the Keychain version above.

```json
{
  "mcpServers": {
    "intervals-icu-planner": {
      "command": "uvx",
      "args": ["intervals-icu-planner-mcp"],
      "env": { "INTERVALS_ICU_API_KEY": "your-key-here" }
    }
  }
}
```

Claude Code:

```sh
claude mcp add -s user intervals-icu-planner -e INTERVALS_ICU_API_KEY=your-key-here -- \
  uvx intervals-icu-planner-mcp
```

## Limit it to a plans folder (optional)

Set `INTERVALS_ICU_PLANS_DIR` to a folder (for example `~/training`), or pick
a **Plans folder** in the Claude Desktop extension's settings. The tools then
only read and edit plans whose `plan.yaml`, workouts folder and `.zwo` files
are inside it, following symlinks, and refuse anything else before reading
it. Unset, plans can be anywhere. Claude is told the folder, so it saves new
plans there.

## Upgrading

`uvx` caches the version it installed first. To move to a new release, run
`uvx intervals-icu-planner-mcp@latest` once (or `uv cache clean
intervals-icu-planner-mcp`), then restart Claude. To pin a version, use
`intervals-icu-planner-mcp@0.1.0` in the config instead.

To try unreleased changes from GitHub, use
`uvx --from git+https://github.com/gustavosoares/intervals-icu-planner-mcp intervals-icu-planner-mcp`.

## The CLI

```sh
pip install intervals-icu-planner-mcp      # or: uv tool install intervals-icu-planner-mcp
export INTERVALS_ICU_API_KEY=your-key-here      # or put it in .env
intervals-icu-planner push examples/winter-base-12wk/plan.yaml
```

See [cli.md](cli.md) for every command.

Something not working? See [troubleshooting.md](troubleshooting.md).
