# intervals-icu-planner-mcp

**Push, inspect and remove whole training plans on your [intervals.icu](https://intervals.icu) calendar from Claude (or the command line), safely.**

<!-- TODO: replace with a demo GIF: Claude runs push_plan as a dry run, shows the diff, then applies it -->
> 🎬 *Demo GIF coming soon.*

You describe a training block once in a `plan.yaml`: week templates,
per-week changes, recovery weeks, notes for outdoor rides, and the `.zwo`
workouts. This MCP server turns it into dated calendar events, shows you a
diff against what's already there, and writes only when you say so.
intervals.icu then syncs the workouts to Zwift, MyWhoosh and Garmin.

## Why this exists

General intervals.icu MCP servers expose the API one event at a time: create
an event, delete an event, list activities. That works for a single workout.
For a 12-week block it means dozens of separate writes, with nothing tying
them together and nothing that shows you what will change first.

This server works on **whole plans**:

- **One file, one plan.** `push_plan` validates the plan and every workout,
  then upserts the whole block. Edit the file and push again: events are
  updated in place, never duplicated.
- **Diff before write.** Every write tool is a dry run by default and returns
  a per-date diff (`+` new, `~` updated, `=` unchanged, `!` stale).
- **A plan only touches its own events.** Each event carries a uid,
  `planner-<plan_id>-w<NN>-<day>`, and the server never modifies an event
  without one. Your races, notes and other workouts are invisible to it.
- **Reversible.** `delete_plan` removes exactly the events a plan created.

It also reads your fitness (CTL / ATL / Form) and completed activities, so
you can ask Claude how the block is going.

## Quick start

### 1. Get an API key

intervals.icu → **Settings** → **Developer Settings** → **API key**.

#### On a Mac: keep it in the Keychain (recommended)

Don't leave the key in plain text in config files or your shell profile. Store it
in the macOS Keychain instead:

```sh
security add-generic-password -a "$USER" -s INTERVALS_ICU_API_KEY -w
```

With `-w` and no value, `security` asks for the key, so it doesn't end up in
your shell history. To replace a stored key later, add `-U`.

**For the CLI and Claude Code**, load it into your shell. Add this line to
`~/.zshrc` (or `~/.bashrc`):

```sh
export INTERVALS_ICU_API_KEY=$(security find-generic-password -w -a "$USER" -s INTERVALS_ICU_API_KEY)
```

Then run `source ~/.zshrc`. Programs you start from that shell, including
`claude`, get the key from the Keychain, and it's never written to a file.

**For Claude Desktop**, the shell profile doesn't help: apps launched from
the Dock don't read `~/.zshrc`. Have the server read the Keychain when it
starts instead. Use this config in place of the one in step 2:

```json
{
  "mcpServers": {
    "intervals-icu-planner": {
      "command": "/bin/sh",
      "args": [
        "-c",
        "INTERVALS_ICU_API_KEY=$(security find-generic-password -w -s INTERVALS_ICU_API_KEY) exec uvx --from git+https://github.com/gustavosoares/intervals-icu-planner-mcp intervals-icu-planner-mcp"
      ]
    }
  }
}
```

The same wrapper works in Claude Code if you don't want the key in your shell:

```sh
claude mcp add intervals-icu-planner -- /bin/sh -c \
  'INTERVALS_ICU_API_KEY=$(security find-generic-password -w -s INTERVALS_ICU_API_KEY) exec uvx --from git+https://github.com/gustavosoares/intervals-icu-planner-mcp intervals-icu-planner-mcp'
```

To check the key is stored, run
`security find-generic-password -s INTERVALS_ICU_API_KEY`. It shows the entry
but not the key. To remove it, run
`security delete-generic-password -s INTERVALS_ICU_API_KEY`.

### 2. Add the server to Claude Desktop

Edit `claude_desktop_config.json` (Claude Desktop → Settings → Developer →
Edit Config). You need [uv](https://docs.astral.sh/uv/) installed.

```json
{
  "mcpServers": {
    "intervals-icu-planner": {
      "command": "uvx",
      "args": [
        "--from", "git+https://github.com/gustavosoares/intervals-icu-planner-mcp",
        "intervals-icu-planner-mcp"
      ],
      "env": { "INTERVALS_ICU_API_KEY": "your-key-here" }
    }
  }
}
```

This stores the key in plain text in the config file. On a Mac, use the
Keychain version above instead.

Once the package is on PyPI this becomes `"args": ["intervals-icu-planner-mcp"]`.

For Claude Code: `claude mcp add intervals-icu-planner -e INTERVALS_ICU_API_KEY=your-key-here -- uvx --from git+https://github.com/gustavosoares/intervals-icu-planner-mcp intervals-icu-planner-mcp`.

### 3. First dry run

Clone the repo (or write your own plan), then ask Claude:

> Push `/path/to/intervals-icu-planner-mcp/examples/winter-base-12wk/plan.yaml`, starting next Monday.

Claude calls `push_plan` with `dry_run=true` and shows you the diff:

```
Winter Base 12 Weeks (winterbase): 12 weeks, 2026-11-30 -> 2027-02-21

Week 1, 2026-11-30
  + 2026-12-01 Tue  WORKOUT  W09_Tempo_60_2x12.zwo
  + 2026-12-02 Wed  WORKOUT  W10_Z2_45.zwo
  + 2026-12-03 Thu  WORKOUT  W04_Z2_60_Neuromuscular_Sprints.zwo
  + 2026-12-05 Sat  NOTE     Outdoor group ride
  + 2026-12-06 Sun  WORKOUT  W01_Recovery_Spin_45.zwo
...
60 new, 0 updated, 0 unchanged, 0 stale.
Dry run: nothing was written. Run again with dry_run=false to apply.
```

Nothing is on your calendar yet. Tell Claude to apply it and it calls
`push_plan` again with `dry_run=false`.

### Tools

| Tool | What it does | Writes? |
|---|---|---|
| `push_plan(plan_yaml, start_date?, dry_run=true)` | Validate a plan, diff it against the calendar, upsert new and updated events | only with `dry_run=false` |
| `get_planned(oldest, newest, plan_id?)` | List planned events; optionally only one plan's | no |
| `delete_plan(plan_id, dry_run=true, oldest?, newest?)` | Remove every event the plan created, nothing else | only with `dry_run=false` |
| `get_fitness(oldest, newest)` | CTL, ATL, Form (TSB = CTL − ATL) and Form as % of CTL, per day | no |
| `get_activities(oldest, newest)` | Completed activities: time, distance, load, avg/normalized power, IF, HR | no |

`plan_yaml` is a path to the file. Relative `workouts_dir` paths are resolved
from the plan file's folder. `delete_plan` searches one year back and two
years ahead by default; pass `oldest` / `newest` for anything outside that.

## plan.yaml reference

A [JSON Schema](schemas/plan.schema.json) is included. Editors with the YAML
language server (e.g. VS Code's YAML extension) validate and autocomplete
plans when the file starts with:

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/gustavosoares/intervals-icu-planner-mcp/main/schemas/plan.schema.json
```

```yaml
id: winterbase             # required; lowercase letters, digits, - and _ (max 40)
name: Winter Base 12wk     # required
start: 2026-11-30          # required; Monday of week 1 (start_date / --start overrides it)
workouts_dir: workouts     # .zwo folder, relative to plan.yaml (default: workouts)
type: Ride                 # intervals.icu activity type for workouts (default: Ride)

templates:                 # required; named weeks: mon, tue, wed, thu, fri, sat, sun
  build:
    tue: S1_SweetSpot_2x15.zwo             # a .zwo file name -> WORKOUT event
    thu:
      workout: W04_Z2_60_Neuromuscular_Sprints.zwo
      name: Sprints                        # optional: overrides the <name> in the .zwo
      description: ERG off for the sprints # optional
    sat:
      note: Outdoor group ride             # a note -> NOTE event, no workout file
      description: Bad weather? Ride W08 indoors.
  recovery:
    tue: W02_Z2_Endurance_60_Cadence.zwo
    sat: { note: Recovery week - easy ride or skip }

weeks:                     # required; in order, the first item is week 1
  - { template: build }
  - { template: build, overrides: { tue: W06_Tempo_3x10.zwo, sun: null } }
  - { template: recovery, recovery: true }
```

Rules:

- Days left out of a template have nothing scheduled.
- `overrides` are merged over the week's template, day by day. `day: null`
  removes that day's session.
- `recovery: true` just marks the week in the output. What makes it a
  recovery week is the template you give it.
- A workout's name comes from the `<name>` in its `.zwo`, or from the file
  name if there is none.
- Events are all-day entries (`T00:00:00` local time).
- Every problem in the plan is reported together, before anything is sent.

### uids and re-pushing

Each event's uid is `planner-<id>-w<NN>-<day>`, for example
`planner-winterbase-w03-tue`. The uid has no date in it, so changing a
workout, or shifting the whole plan with `start_date`, updates the existing
events instead of adding new ones. Events are sent to
`POST /api/v1/athlete/0/events/bulk?upsert=true` with the plan uid in
`external_id` (intervals.icu gives every event its own separate `uid`, so
that field is left alone) and the `.zwo` sent as-is in `file_contents`.

The diff compares date, category, name and (for notes) description. intervals.icu
doesn't return the original `.zwo`, so a workout is compared by name and
duration: if you change the inside of a workout but keep its name and total
length, the diff shows it as unchanged and it isn't re-sent. Rename it (or
change `name:`) to force an update.

### Example

[`examples/winter-base-12wk/`](examples/winter-base-12wk/) is a 12-week winter
base plan with no threshold work: mostly Z1–Z2 and light tempo, in three
4-week cycles of two short weeks (weekday rides of 60 minutes or less), one
longer week, and a sweet spot week. The sweet spot session builds each cycle:
2×15, then 2×20, then 3×15 minutes. Saturday is an outdoor group ride (a note,
with an indoor alternative) and Sunday a recovery spin. Monday and Friday are
rest days. That's 60 events. All targets are % of FTP, so it works for any
rider once your FTP is set in your training app.

## Safety design

These rules are the core of the project. Each one is covered by tests.

1. **Dry run first.** `push_plan` and `delete_plan` default to `dry_run=true`
   and return the diff (or the list of events to delete) without writing. The
   server's instructions tell the model to show you that output and wait for
   your OK before calling again with `dry_run=false`. The CLI's write commands
   need `--apply`. Tests assert that a dry run never calls a write endpoint.
2. **Only its own uids.** An event belongs to plan `X` only if its uid fully
   matches `planner-X-w<NN>-<day>`. That's an exact pattern, not a prefix
   test, so plan `winter` can never touch plan `winter-base`. Events without
   such a uid (your races, notes and manually added workouts) are never
   updated or deleted. They don't show up in the diff either. Before the
   delete request is sent, each event is checked against the pattern again.
3. **Validate before upload.** Every plan is checked against the schema, and
   every `.zwo` is checked before any network call:
   - well-formed XML (DOCTYPE/ENTITY declarations rejected);
   - only known segment types: SteadyState, Warmup, Cooldown, Ramp,
     IntervalsT, FreeRide, MaxEffort, SolidState;
   - every duration > 0;
   - every power target a ratio in (0, 3] of FTP (so `250` watts written by
     mistake is caught);
   - total length under 6 hours.

   A plan with any error sends nothing.
4. **The API key stays private.** It's read from the `INTERVALS_ICU_API_KEY`
   environment variable, or from a `.env` file in the working directory
   (`.env` is git-ignored). It's never logged, printed, or included in error
   messages or object reprs.

## Syncing to your training apps

intervals.icu sends planned workouts to the apps you connect under
**Settings → Connections**:

- **Zwift** and **MyWhoosh**: the day's planned workouts show up in the app's
  workout list, ready to ride.
- **Garmin Connect**: workouts land on the Garmin Connect calendar and reach
  your device on its next sync.

Only the **next 7 days** are synced, not the whole plan. If you push 12 weeks,
the apps show this week's sessions, and later weeks appear as the window moves
forward. If a workout is missing in the app, check that it falls within the
next 7 days, then re-sync or reopen the app. Changes you push again are picked
up the same way.

**Turn ERG mode off for sprint intervals**, and ride them in resistance or
slope mode instead. In ERG the trainer holds the target wattage, so you can't
sprint above it. Short all-out efforts like the 10-second sprints in
`W04_Z2_60_Neuromuscular_Sprints.zwo` only work when you control the power.
The target in the file is a placeholder.

## Reading your activities

`get_activities` lists completed rides with intervals.icu's numbers: moving
time, distance, training load, average and normalized power, intensity factor
and average heart rate. Combined with `get_fitness` and `get_planned`, Claude
can compare what was planned with what was ridden.

One limitation: **activities that reached intervals.icu through Strava can't
be read via the API** (Strava's terms forbid it). They're listed as
"Strava import: details not available via API". Connect Garmin, Zwift,
MyWhoosh etc. to intervals.icu directly to see them.

## CLI

The same core works without MCP:

```sh
pip install git+https://github.com/gustavosoares/intervals-icu-planner-mcp
export INTERVALS_ICU_API_KEY=your-key-here      # or put it in .env

intervals-icu-planner push plan.yaml                       # dry run: prints the diff
intervals-icu-planner push plan.yaml --start 2027-01-04    # shift the plan
intervals-icu-planner push plan.yaml --apply               # write it

intervals-icu-planner planned 2026-12-01 2026-12-31 [--plan-id winterbase]
intervals-icu-planner delete winterbase                    # dry run: lists what would go
intervals-icu-planner delete winterbase --apply
intervals-icu-planner fitness 2026-11-01 2026-11-30
intervals-icu-planner activities 2026-11-01 2026-11-30
intervals-icu-planner schema                               # print the plan.yaml JSON Schema
```

`push` works without an API key as an offline dry run (the calendar isn't
checked, so everything shows as new). Exit codes: 0 ok, 1 API error, 2
invalid input or missing key.

## Roadmap

- `move_workout`: move one session to another day
- `shift_plan`: move a whole plan by N weeks, with a diff
- Activity analysis: planned vs completed, compliance per week
- OAuth and the streamable HTTP transport, for claude.ai custom connectors
- PyPI release

## Development

```sh
pip install -e ".[dev]"
pytest              # HTTP is mocked with respx; no network
ruff check . && ruff format --check .
mypy
```

The code is in [`src/intervals_icu_planner_mcp/`](src/intervals_icu_planner_mcp/).
`client.py` is the HTTP client, with no MCP code in it. `plan.py`, `zwo.py` and
`diff.py` hold the plan logic. `planner.py` has the operations, shared by
`server.py` (MCP) and `cli.py`. See [CONTRIBUTING.md](CONTRIBUTING.md).

## A note on AI assistance

This project is built with help from AI coding tools, which speed up writing code, tests
and documentation. Every change is reviewed and tested by a human maintainer before it's
merged, and the maintainer is responsible for what ships, including the safety rules above.

## License

MIT, see [LICENSE](LICENSE).
