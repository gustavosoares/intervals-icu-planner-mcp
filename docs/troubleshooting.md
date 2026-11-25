# Troubleshooting

[← Back to README](../README.md)

## Claude Desktop doesn't show the tools, or says the server failed

Apps launched from the Dock on macOS get neither Homebrew's `PATH` nor your
`~/.zshrc`. So `uvx` isn't found, and an `INTERVALS_ICU_API_KEY` exported in
your shell isn't set.

- Use the full path to `uvx` in the config (`which uvx` shows it, usually
  `/opt/homebrew/bin/uvx`).
- Put the key in the config's `env`, or better, read it from the Keychain
  with the `/bin/sh -c` wrapper in [setup.md](setup.md#claude-desktop-read-the-keychain-when-the-server-starts).
- Quit Claude Desktop fully (⌘Q) and reopen it after editing the config.
- The server logs are under `~/Library/Logs/Claude/` (`mcp-server-intervals-icu-planner.log`).

## Claude Code only sees the server in one folder

`claude mcp add` without `-s user` registers the server **only for the
current directory**. Add it with `-s user` to have it everywhere. If both
exist, the local entry wins over the user one; `claude mcp list` shows which
is in use, and `claude mcp remove intervals-icu-planner -s local` removes the
local one.

## "not connected to intervals.icu"

Ask Claude to connect to intervals.icu, or run `intervals-icu-planner login`,
and approve in the browser. If you use an API key instead, it's read from
`INTERVALS_ICU_API_KEY`, then from a `.env` file in the working directory.
Check that it's set in the environment the server runs in, which isn't
necessarily your terminal's (see the Claude Desktop section above).

## "your intervals.icu sign-in is no longer valid"

The access was revoked (under intervals.icu **Settings → Apps**), or replaced
by a newer sign-in elsewhere. Connect again.

## A workout isn't in Zwift, MyWhoosh or Garmin

intervals.icu only syncs the **next 7 days**. Check that the workout falls in
that window and that the app is connected under intervals.icu **Settings →
Connections**, then re-sync or reopen the app. See
[training-apps.md](training-apps.md).

## I changed a .zwo but the diff says "unchanged"

intervals.icu doesn't return the original `.zwo`, so workouts are compared by
name and duration. Rename the workout (its `<name>` or `name:` in the plan)
to force an update. Details in [how-it-works.md](how-it-works.md#why-workouts-are-compared-by-name-and-duration).

## Removed sessions are still on the calendar

A normal push never deletes. Push with `prune=true` (`--prune`) to remove
sessions you took out of the plan. Past sessions are always kept. See
[plan-reference.md](plan-reference.md#removing-sessions-stale-events-and-prune).

## Rides show "details not available via API"

Those activities came into intervals.icu from Strava, whose terms forbid
sharing them through the API. Connect your device or app (Garmin, Zwift,
MyWhoosh…) to intervals.icu directly.

## move_workout or shift_plan says the file changed

Someone (or your editor) saved `plan.yaml` while the tool was running, so
nothing was written. Run it again. If a sync failed after the file was
written, finish with `push_plan(prune=true)`.
