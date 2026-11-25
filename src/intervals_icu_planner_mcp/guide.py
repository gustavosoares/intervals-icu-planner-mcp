"""How to write a plan: the text behind the ``plan_guide`` tool and ``guide`` command.

A model asked to "build me a plan" needs the plan.yaml format and the .zwo
rules before it writes anything. The rules here are generated from the same
constants and models the validator uses (``plan.plan_json_schema``,
``zwo.SEGMENTS`` ...), so the guide can't drift from what ``push_plan``
accepts. Both examples are checked by the tests to validate.
"""

from __future__ import annotations

import json

from .plan import plan_json_schema
from .zwo import MAX_POWER, MAX_TOTAL_SECONDS, SEGMENTS

EXAMPLE_PLAN = """\
id: sportive-100k          # lowercase letters, digits, - and _; prefix of every event uid
name: 100 km sportive, 4-week build
start: 2027-01-04          # Monday of week 1
workouts_dir: workouts     # .zwo folder, relative to this file

templates:
  build:
    tue: Tempo_3x10.zwo
    wed: Z2_60.zwo
    thu:
      workout: Tempo_3x10.zwo
      name: Tempo 3x10 (cadence 95+)        # optional: overrides the .zwo <name>
      description: Same session, higher cadence.
    sat:
      note: Long outdoor ride, 3h mostly Z2  # a note: no workout file
      description: Bad weather? Ride Z2_60 indoors.
  recovery:
    wed: Z2_60.zwo
    sat: { note: "Easy ride, 90 min, or rest" }   # quote text with commas in { }

weeks:                     # in order; the first item is week 1
  - { template: build }
  - { template: build }
  - { template: build, overrides: { thu: Z2_60.zwo } }   # per-week change
  - { template: recovery, recovery: true }
"""

EXAMPLE_ZWO = """\
<?xml version="1.0" encoding="UTF-8"?>
<workout_file>
  <author>intervals-icu-planner-mcp</author>
  <name>Tempo 3x10min</name>
  <description>3 x 10 min at 80% FTP with 5 min easy between.</description>
  <sportType>bike</sportType>
  <workout>
    <Warmup Duration="600" PowerLow="0.45" PowerHigh="0.70"/>
    <IntervalsT Repeat="3" OnDuration="600" OffDuration="300" OnPower="0.80" OffPower="0.55"/>
    <SteadyState Duration="600" Power="0.65">
      <textevent timeoffset="0" message="Easy Z2 to finish"/>
    </SteadyState>
    <Cooldown Duration="300" PowerLow="0.60" PowerHigh="0.40"/>
  </workout>
</workout_file>
"""


def _segment_lines() -> str:
    lines = []
    for name, (durations, powers) in SEGMENTS.items():
        attrs = [*durations, *powers]
        lines.append(f"  - `{name}`: {', '.join(attrs)}")
    return "\n".join(lines)


def plan_guide() -> str:
    """Everything a model needs to write a valid plan.yaml and its .zwo workouts."""
    schema = json.dumps(plan_json_schema(), separators=(",", ":"))
    hours = MAX_TOTAL_SECONDS // 3600
    return f"""\
# Writing a training plan for intervals-icu-planner

A plan is a folder with a `plan.yaml` and a `workouts/` folder of `.zwo`
files. Write the files, then push them with `push_plan`.

## Steps

1. Agree the outline with the athlete first: goal and date, weeks available,
   hours per week, which days they ride (indoors or outdoors), rest days and
   recovery weeks. Fitness numbers from `get_fitness` and recent rides from
   `get_activities` help set the starting load.
2. Write `plan.yaml` and one `.zwo` per distinct workout into a folder of the
   athlete's choice. Reuse a workout file across weeks rather than copying it.
   If you can't write files here, show them to the athlete to save, and ask
   for the folder path.
3. Call `push_plan(plan_yaml=<path to plan.yaml>)`. It's a dry run: it
   validates every file and reports every error together. Fix them and run it
   again until it shows the diff.
4. Show the athlete the diff. Only call `push_plan(..., dry_run=false)` after
   they say yes.

## plan.yaml

```yaml
{EXAMPLE_PLAN}```

- `start` must be a Monday. `push_plan(start_date=...)` can override it.
- `templates` are named weeks (keys `mon` ... `sun`). A day is a `.zwo` file
  name, `{{workout: <file>, name?, description?}}`, or
  `{{note: <title>, description?}}`. Days left out have nothing scheduled.
- `weeks` lists the weeks in order. `overrides` are merged over the template
  day by day, and `day: null` removes that day's session. `recovery: true`
  only labels the week; the template makes it easy.
- Quote text that contains a comma or colon inside `{...}`, or YAML splits it.
- Workout file names are plain names (no folders), ending in `.zwo`.
- Keep the same `id` when you change a plan: events are matched by
  `planner-<id>-w<NN>-<day>`, so re-pushing updates them in place.

JSON Schema for plan.yaml:

```json
{schema}
```

## .zwo workouts

```xml
{EXAMPLE_ZWO}```

- Every power target is a fraction of FTP, in (0, {MAX_POWER:g}]: `0.80` is
  80% FTP. Never write watts.
- Durations are in seconds and must be > 0. A workout must be under {hours}
  hours in total.
- Allowed segments and their required attributes:
{_segment_lines()}
- `IntervalsT` also takes `Repeat` (default 1). Segments can hold
  `<textevent timeoffset="..." message="..."/>` cues.
- The root is `<workout_file>`, with a non-empty `<workout>` inside it.
- No DOCTYPE or ENTITY declarations.
- `<name>` is the title shown on the calendar; `<description>` is optional.
- `FreeRide` (no target) suits outdoor-style or unstructured parts. Ask riders
  to turn ERG off for sprints (`MaxEffort` or very high short targets).
"""
