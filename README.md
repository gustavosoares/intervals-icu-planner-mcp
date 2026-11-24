# intervals-icu-planner-mcp

Push a multi-week training plan of `.zwo` workouts to your
[intervals.icu](https://intervals.icu) calendar from one YAML file.

You describe the plan once: a start Monday, a weekly template, per-week
changes, recovery weeks, and notes for outdoor rides. `intervals-icu-planner-mcp` turns
that into dated calendar events and uploads them in one request. Every event
has a stable id, so you can edit the plan and run it again: existing entries
are updated in place, not duplicated.

intervals.icu then syncs the planned workouts to Zwift, MyWhoosh and Garmin
(see [Syncing to your training apps](#syncing-to-your-training-apps)).

- Python 3.9+, one dependency (PyYAML)
- Validates the plan before sending anything: every `.zwo` exists and parses,
  the start date is a Monday, the week numbers are in range
- `--dry-run` prints the full schedule without touching the network

## Quick start

```sh
git clone https://github.com/gustavosoares/intervals-icu-planner-mcp.git
cd intervals-icu-planner-mcp
pip install -e .            # or just: pip install PyYAML

# 1. See what would be scheduled (no API key needed)
python push.py examples/winter-base-12wk/plan.yaml --dry-run

# 2. Add your API key: intervals.icu -> Settings -> Developer Settings -> API key
echo 'INTERVALS_API_KEY=your-key-here' > .env    # .env is git-ignored
#    (or: export INTERVALS_API_KEY=your-key-here)

# 3. Push it
python push.py examples/winter-base-12wk/plan.yaml
```

After `pip install -e .` the same command is also available as
`intervals-icu-planner-mcp plan.yaml ...`.

### Options

```
push.py PLAN [--dry-run] [--start YYYY-MM-DD] [--delete]
```

| Option | What it does |
|---|---|
| `--dry-run` | Print the schedule and stop. Nothing is sent. |
| `--start YYYY-MM-DD` | Use this Monday as week 1 instead of the plan's `start`. |
| `--delete` | Remove this plan's events from the calendar instead of pushing. |

**Re-running is safe.** Each event's id is `<plan id>-w<week>-<day>`, for
example `winterbase-w03-tue`. The id doesn't include the date, so changing a
workout, or shifting the whole plan with `--start`, updates the existing
events instead of adding new ones. Events are sent with
`POST /api/v1/athlete/0/events/bulk?upsert=true`, with the ZWO in
`file_contents` and the id in `external_id` and `uid`. Athlete `0` means "the
athlete who owns the API key".

**Deleting.** `--delete` lists the calendar events between the plan's first
and last day, keeps only the ones whose id starts with `<plan id>-w`, and
deletes those. Nothing else on your calendar is touched. Use the same
`--start` you pushed with, so it searches the right dates. Combine it with
`--dry-run` to see what it would do.

The API key comes from the `INTERVALS_API_KEY` environment variable if it is
set, otherwise from a `.env` file in the current directory.

## plan.yaml reference

```yaml
name: Winter Base 12wk     # shown in the output (optional)
id: winterbase             # required: prefix of every event id; letters, digits, - and _
start: 2026-11-30          # required: Monday of week 1 (--start overrides it)
weeks: 12                  # required: number of weeks
workouts_dir: workouts     # folder with the .zwo files, relative to plan.yaml (default: workouts)
type: Ride                 # intervals.icu activity type for workouts (default: Ride)

template:                  # the default week: mon, tue, wed, thu, fri, sat, sun
  tue: T1_Threshold_3x8.zwo              # a string is a .zwo file -> WORKOUT event
  thu:
    workout: W04_Z2_60_Neuromuscular_Sprints.zwo
    name: Sprints                        # optional: override the name from the .zwo
    description: ERG off for the sprints # optional
  sat:
    note: Outdoor group ride             # a note -> NOTE event (no workout file)
    description: Bad weather? Ride W08 indoors.

recovery:                  # optional
  weeks: [4, 8, 12]        # these weeks use the recovery template instead of `template`
  template:
    tue: W02_Z2_Endurance_60_Cadence.zwo
    sat: { note: Recovery week - easy ride or skip }

overrides:                 # optional: per-week changes, merged over that week's template
  2: { tue: W06_Tempo_3x10.zwo, thu: W05_Low_Cadence_Force_5x5.zwo }
  5: { sat: null }         # null removes that day's session
```

Rules:

- Days left out of a template have nothing scheduled.
- For each week the base is `recovery.template` if the week is listed in
  `recovery.weeks`, otherwise `template`. Then `overrides[week]` is applied on
  top, day by day.
- A workout's name comes from the `<name>` in its `.zwo` file, or from the
  file name if there is none.
- Events are all-day entries on the calendar (`T00:00:00` local time).
- Every problem in the plan is reported together, before anything is sent.

### Example

[`examples/winter-base-12wk/`](examples/winter-base-12wk/) is a 12-week winter
base plan: a threshold session that progresses from 3×8 to 2×20 minutes, tempo
and low-cadence force work, a Saturday outdoor ride, and a recovery week every
fourth week. That adds up to 54 events. All targets are % of FTP, so it works
for any rider once your FTP is set in your training app.

## Syncing to your training apps

intervals.icu sends planned workouts to the apps you connect under
**Settings → Connections**:

- **Zwift** and **MyWhoosh**: the day's planned workouts show up in the app's
  workout list, ready to ride.
- **Garmin Connect**: workouts land on the Garmin Connect calendar and reach
  your device on its next sync.

Only the **next 7 days** are synced, not the whole plan. If you push 12 weeks,
the apps show this week's sessions, and the later weeks appear as the window
moves forward each day. If a workout is missing in the app, check that it
falls within the next 7 days, then re-sync or reopen the app. Changes you push
again are picked up the same way.

## Sprints and ERG mode

Turn **ERG mode off** for sprint intervals, and ride them in resistance or
slope mode instead. In ERG the trainer holds the target wattage, so you can't
sprint above it. Short all-out efforts like the 10-second sprints in
`W04_Z2_60_Neuromuscular_Sprints.zwo` only work when you control the power. The
target in the file is a placeholder.

## Development

```sh
pip install -e ".[test]"
pytest
```

The tests cover plan parsing, validation and payload building, and never use
the network. GitHub Actions runs them on Python 3.9 to 3.13.

## License

MIT, see [LICENSE](LICENSE).
