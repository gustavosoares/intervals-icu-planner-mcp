# plan.yaml reference

[← Back to README](../README.md)

A plan is one `plan.yaml` plus a folder of `.zwo` workout files. It describes
a training block once (week templates, per-week changes, recovery weeks),
and the server expands it into dated calendar events.

## Editor support

A [JSON Schema](../schemas/plan.schema.json) is included. Editors with the YAML
language server (e.g. VS Code's YAML extension) validate and autocomplete
plans when the file starts with:

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/gustavosoares/intervals-icu-planner-mcp/main/schemas/plan.schema.json
```

## Fields

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

## Rules

- Days left out of a template have nothing scheduled.
- `overrides` are merged over the week's template, day by day. `day: null`
  removes that day's session.
- `recovery: true` just marks the week in the output. What makes it a
  recovery week is the template you give it.
- A workout's name comes from the `<name>` in its `.zwo`, or from the file
  name if there is none.
- Events are all-day entries (`T00:00:00` local time).
- Every problem in the plan is reported together, before anything is sent.
  The checks are listed in [safety.md](safety.md#3-validate-before-upload).

## uids and re-pushing

Each event's uid is `planner-<id>-w<NN>-<day>`, for example
`planner-winterbase-w03-tue`. The uid has no date in it, so changing a
workout, or shifting the whole plan with `start_date`, updates the existing
events instead of adding new ones.

The diff compares date, category, name and (for notes) description. intervals.icu
doesn't return the original `.zwo`, so a workout is compared by name and
duration: if you change the inside of a workout but keep its name and total
length, the diff shows it as unchanged and it isn't re-sent. Rename it (or
change `name:`) to force an update.

How the uid is stored on intervals.icu is covered in
[how-it-works.md](how-it-works.md#where-the-uid-lives).

## Removing sessions: stale events and `prune`

If you take a session out of the plan (`day: null`, a shorter `weeks` list,
a different template), the event already on the calendar becomes **stale**:
it has the plan's uid, but the plan no longer produces it. The diff marks it
`!`, and a normal push leaves it alone.

Push with `prune=true` (CLI: `--prune`) to delete stale events too. In the
dry run they show as `-`. Here, a few weeks into the plan, two sessions were
taken out (`day: null`), one already ridden and one still to come:

```
Stale: on the calendar with this plan's uid but no longer in the plan.
Pruning deletes the ones from today on (-); earlier ones are kept (!).
  - 2026-12-22  WORKOUT  Tempo 60min (2x12)  planner-winterbase-w05-tue
  ! 2026-11-25  WORKOUT  Z2 Endurance 45min  planner-winterbase-w01-wed  (past, kept)

0 new, 0 updated, 58 unchanged, 2 stale (1 to delete).
```

Pruning only deletes events dated **today or later**, so your past planned
sessions stay on the calendar. It runs after the upsert, so if the upsert
fails nothing is deleted. Like everything else, it only matches this plan's
own uids.

To find stale events, a push searches one year back and two years ahead
(further if the plan goes further), not only the plan's own dates. Events
left behind by a shorter or shifted version of the plan are found too, and
a shifted plan shows its events as moved rather than new.

## Moving sessions and shifting the plan

`plan.yaml` is the source of truth, so these tools **change the file** and then
sync the calendar. Changing only the calendar would be undone by your next
push. The dry run shows both: the `plan.yaml` diff and the calendar diff.

**`move_workout`** moves one session, e.g. "week 3, Tuesday to Friday". It
writes the smallest possible override for that week (`tue: null, fri: ...`),
and moving it back removes the override again. It refuses to:

- move a session that's already in the past, or move one into the past;
- move onto a day that already has a session (pass `swap=true` to trade places);
- move from a day that has no session.

Because uids are `w<NN>-<day>`, a move is a delete plus a create on the
calendar: `+ Fri` and `- Tue` in the diff.

**`shift_plan`** is for "I was sick, push the rest back a week":

- **Nothing ridden yet** (no session before today): `start` moves by N weeks,
  and every event is moved in place.
- **Under way:** N empty `rest` weeks are inserted before `from_week` (default:
  the current week), and an empty `rest: {}` template is added if the plan has
  none. That week and everything after it move N weeks later. Past sessions stay
  on the calendar where they happened; pruning never deletes the past. `# Week N`
  comments on the weeks list are renumbered.

When editing, comments and layout are kept: every line the edit doesn't
change stays byte for byte as you wrote it. If someone else changes the file
while the tool runs, nothing is written. The file is written first (git can
undo it), then the calendar is synced. If the sync fails, the error tells you
to finish with `push_plan(prune=true)`.

## The example plan

[`examples/winter-base-12wk/`](../examples/winter-base-12wk/) is a 12-week winter
base plan with no threshold work: mostly Z1–Z2 and light tempo, in three
4-week cycles of two short weeks (weekday rides of 60 minutes or less), one
longer week, and a sweet spot week. The sweet spot session builds each cycle:
2×15, then 2×20, then 3×15 minutes. Saturday is an outdoor group ride, and
Sunday a recovery spin. Monday and Friday are rest days. That's 60 events.

The Saturday ride is planned as a **placeholder workout**
(`W12_Group_Ride_2h30_Placeholder.zwo`, 2h30 at mostly Z2 with some Z3), not
as a note, so each week shows a realistic planned training load in
intervals.icu. Ride it outdoors. On a rainy Saturday, the description points
to `W08_Rainy_Saturday_2h.zwo` for the trainer instead. All targets are % of
FTP, so it works for any rider once your FTP is set in your training app.
