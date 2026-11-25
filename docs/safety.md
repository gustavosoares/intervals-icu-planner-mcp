# Safety design

[← Back to README](../README.md)

This server writes to a real training calendar, so these rules are the core
of the project. Each one is covered by tests, and a change that weakens one
needs tests that show it still holds.

## 1. Dry run first

`push_plan`, `delete_plan`, `move_workout` and `shift_plan` default to
`dry_run=true` and return the diff (or the list of events to delete) without
writing. The server's instructions tell the model to show you that output and
wait for your OK before calling again with `dry_run=false`. The CLI's write
commands need `--apply`. Tests assert that a dry run never calls a write
endpoint.

A push never deletes anything unless you also pass `prune=true` (`--prune`),
and pruning never deletes past events.

## 2. Only its own uids

An event belongs to plan `X` only if its uid fully matches
`planner-X-w<NN>-<day>`. That's an exact pattern, not a prefix test, so plan
`winter` can never touch plan `winter-base`. Events without such a uid (your
races, notes and manually added workouts) are never updated or deleted. They
don't show up in the diff either. Before the delete request is sent, each
event is checked against the pattern again.

## 3. Validate before upload

Every plan is checked against the schema, along with semantic checks (start
is a Monday, templates exist, workout names have no path parts). Every `.zwo`
is checked before any network call:

- well-formed XML (DOCTYPE/ENTITY declarations rejected);
- only known segment types: SteadyState, Warmup, Cooldown, Ramp,
  IntervalsT, FreeRide, MaxEffort, SolidState;
- every duration > 0;
- every power target a ratio in (0, 3] of FTP (so `250` watts written by
  mistake is caught);
- total length under 6 hours.

Every error is reported together, and a plan with any error sends nothing.

## 4. The API key stays private

It's read from the `INTERVALS_ICU_API_KEY` environment variable, or from a
`.env` file in the working directory (`.env` is git-ignored). It's never
logged, printed, or included in error messages or object reprs. Tests use a
fake key and check that it doesn't leak. See [setup.md](setup.md) for keeping
it in the macOS Keychain.

## 5. Edits to `plan.yaml` are previewed and careful

`move_workout` and `shift_plan` show the file diff in the dry run, never touch
past sessions, refuse to overwrite a file that changed meanwhile, and write it
atomically. `list_library` only reads.

## 6. Optionally, plans only from one folder

With `INTERVALS_ICU_PLANS_DIR` set (the **Plans folder** setting of the
Claude Desktop extension), a plan is refused unless `plan.yaml`, its workouts
folder and every `.zwo` resolve inside that folder. Paths are compared after
following symlinks, so `..` and links can't escape it, and the check runs
before the file is read. This limits what the tools will do; like any MCP
server, the program itself still runs with your user's permissions.
