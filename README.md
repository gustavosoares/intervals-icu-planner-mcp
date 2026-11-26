# intervals-icu-planner-mcp

[![PyPI](https://img.shields.io/pypi/v/intervals-icu-planner-mcp.svg)](https://pypi.org/project/intervals-icu-planner-mcp/)
[![tests](https://github.com/gustavosoares/intervals-icu-planner-mcp/actions/workflows/tests.yml/badge.svg)](https://github.com/gustavosoares/intervals-icu-planner-mcp/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python 3.10–3.13](https://img.shields.io/badge/python-3.10%E2%80%933.13-blue.svg)
[![MCP server](https://img.shields.io/badge/MCP-server-8A2BE2.svg)](https://modelcontextprotocol.io)

**Plan a whole training block with Claude and put it on your
[intervals.icu](https://intervals.icu) calendar in one go, safely.**

![One week of the example plan on the intervals.icu calendar](docs/images/calendar-week.png)

<!-- TODO: add a short GIF: "I was sick, push everything back a week" -> dry-run diff -> "apply it" -->

## What it's for

If you train with a plan, you know the routine: every week you open the
calendar and drag in Tuesday's intervals, Wednesday's endurance ride,
Saturday's long ride… for twelve weeks. Then you get sick, and all of it
has to move.

With this, you ask Claude in plain words.

**Build a plan for your goal and put it on your calendar**

> *"I'm riding a 100 km sportive on 14 June. I have about 6 hours a week:
> short indoor rides Tuesday to Thursday, a long ride at the weekend. Build me
> a plan and put it on my calendar."*

Or, if you already have one: *"Put my 12-week winter base plan on my
calendar, starting next Monday."*

Claude shows you exactly what it's going to add, and nothing changes until
you say yes. Then the whole block lands on your intervals.icu calendar, and
from there each day's workout shows up in **Zwift, MyWhoosh or on your
Garmin**, ready to ride.

<p align="center">
  <img src="docs/images/mywhoosh-calendar.png" alt="The plan's workouts synced to the MyWhoosh calendar">
  <br>
  <img src="docs/images/garmin-training-plan.jpg" alt="Today's workout from the plan on a Garmin head unit" width="240">
</p>

**See how you did**

- *"I raced on Sunday. How did I do?"*
- *"Review my rides this week. How did they go compared to the plan?"*

Claude reads your completed rides from intervals.icu (time, power, heart
rate, training load) and compares them with what was planned and with your
fitness. Rides that reached intervals.icu through Strava can't be read
([why](docs/training-apps.md#reading-your-activities)).

**Adjust when life gets in the way**

- *"Check my fitness. Should I rest, or change the plan?"*
- *"I was sick this week, push the rest of the plan back a week."*
- *"Move Thursday's sprints to Friday."*

Claude looks at your fitness, fatigue and form, suggests what to change, and
shows you the new calendar before changing anything.

It only ever touches the workouts it put there. Your races, notes and
anything you added by hand are left alone.

<details>
<summary>What's an MCP server?</summary>

[MCP](https://modelcontextprotocol.io) is how apps like Claude get new
abilities. This project is a small program that runs on your computer and
gives Claude a few safe tools for your intervals.icu calendar. Claude
decides when to use them, and asks you before writing anything.
</details>

## Why a plan, not single workouts

Putting one workout on a calendar is easy. A 12-week block is dozens of them,
and the hard part is everything after the first push: getting sick, swapping
days, making the build weeks harder, starting again next season. With this
server, Claude works on the plan as a whole:

- **Change the whole block in one sentence, and see exactly what moves.**
  *"Push everything back a week"* or *"make every build week's Tuesday
  harder"* is one change to the plan. You get a per-date diff (`+` new,
  `~` updated, `=` unchanged, `!` stale), and nothing is written until you
  say yes.
- **Pick up where you left off, in any chat.** The plan's structure (week
  templates, recovery weeks, per-week changes) is saved in a `plan.yaml`, so a
  new conversation, or another AI app, sees what the plan is meant to be, not
  just a scatter of calendar events.
- **Keep it, reuse it, share it.** Next season, change the start date and push
  again. Give a friend the folder. Keep it in git and see exactly what changed
  after you got sick.
- **Bring your own workouts.** Workouts are plain `.zwo` files, the format
  Zwift uses, so you can use ones you already have.
- **Only its own events, and reversible.** Each event carries a uid,
  `planner-<plan_id>-w<NN>-<day>`, and nothing without one is touched.
  Pushing an edited plan updates events in place, never duplicates them, and
  with `prune=true` removes the ones you took out. `delete_plan` removes
  exactly what a plan created.

This works because the plan is a file you own. Claude writes it for you, so
you never have to touch YAML unless you want to.

It also reads your fitness (CTL / ATL / Form) and completed activities, so
you can ask Claude how the block is going.

## This or the official connector?

intervals.icu runs its own [MCP connector](https://www.intervals.icu/connector/):
hosted by intervals.icu, part of the Supporter plan, and it works in Claude,
ChatGPT and Gemini. The two do different jobs (as of November 2026):

- **Use the official connector** to talk about your training (readiness,
  wellness, activity detail, zones and settings), to add the odd workout, for
  coaching, and when you don't want to install anything.
- **Use this planner** for a whole block you'll keep reshaping and reusing:
  - you edit the plan and push it again, and changed sessions are updated in
    place and dropped ones removed (the connector's `apply_training_plan` only
    adds sessions);
  - you have `.zwo` files (the connector has no workout-file import);
  - you want a dry-run diff before every write, including single moves;
  - you want it free, local, and scriptable from a [CLI](docs/cli.md).
- **Or use both.** This planner only touches events carrying its own uid, so
  you can connect both: analyse your rides with one, plan with the other.

## Quick start

### Claude Desktop: one-click install

1. **Download `intervals-icu-planner-<version>.mcpb`** from the
   [latest release](https://github.com/gustavosoares/intervals-icu-planner-mcp/releases/latest)
   and double-click it (or drag it into Claude Desktop → Settings → Extensions).
2. **Click Install.** Leave the API key empty. Optionally, pick a **plans
   folder**: the planner then refuses to read or edit plans anywhere else.
3. **Ask Claude to "connect to intervals.icu".** intervals.icu opens in your
   browser: sign in and click **OK**. That's it; no API key to copy. The
   access is saved in your system keychain.

   <img src="docs/images/sign-in-permissions.png" alt="intervals.icu asks to let intervals-icu-planner-mcp read and update your calendar, and read your library, wellness data and activities" width="380">

> **About the install warning.** Claude Desktop says the extension gets
> "access to everything on your computer". It shows that for every extension
> that isn't in its reviewed directory, because extensions run as ordinary
> programs on your computer, as any MCP server does. Here is what this one
> actually does:
>
> - It talks only to intervals.icu (your calendar, workout library, fitness
>   and rides), over HTTPS, with the access you approved. Nothing goes to the author or
>   anyone else ([privacy](docs/privacy.md)).
> - It reads only the plan files you point it at, and edits only the
>   `plan.yaml` you ask it to move or shift. With a plans folder set, it
>   refuses anything outside that folder.
> - It's open source: the extension installs this repository's
>   [PyPI release](https://pypi.org/project/intervals-icu-planner-mcp/), and
>   the safety rules are [tested](docs/safety.md).

### Claude Code, or a manual setup

1. **Install [uv](https://docs.astral.sh/uv/)**, then add the server.

   **Claude Desktop** (Settings → Developer → Edit Config):

   ```json
   {
     "mcpServers": {
       "intervals-icu-planner": {
         "command": "uvx",
         "args": ["intervals-icu-planner-mcp"]
       }
     }
   }
   ```

   **Claude Code**:

   ```sh
   claude mcp add -s user intervals-icu-planner -- uvx intervals-icu-planner-mcp
   ```

2. **Restart Claude** and check the `intervals-icu-planner` tools are listed.
   If they aren't, see [docs/troubleshooting.md](docs/troubleshooting.md).
3. **Ask Claude to "connect to intervals.icu"** and approve in your browser
   (or run `uvx --from intervals-icu-planner-mcp intervals-icu-planner login`).
   Prefer an API key? See [docs/setup.md](docs/setup.md).

### Other AI apps

It's a standard MCP server, so any app that can run a local (stdio) MCP server
should work, such as Cursor, VS Code with GitHub Copilot, Windsurf or Zed. Add it in
that app's MCP settings with the command `uvx intervals-icu-planner-mcp`, then ask
it to connect to intervals.icu. Only Claude Desktop and Claude Code are tested so
far; reports of other apps are welcome in the
[issues](https://github.com/gustavosoares/intervals-icu-planner-mcp/issues).

ChatGPT isn't supported: it only connects to remote MCP servers, and this one runs
on your computer. In ChatGPT, use intervals.icu's
[official connector](https://www.intervals.icu/connector/) instead.

## Try it

Clone the repo for the [example plan](examples/winter-base-12wk/) (12 weeks
of winter base, all targets in % of FTP), then paste this into Claude:

> Push `/path/to/intervals-icu-planner-mcp/examples/winter-base-12wk/plan.yaml`
> starting next Monday. Show me the dry run first and don't apply anything
> until I say so.

Claude calls `push_plan` as a dry run and shows you the diff:

```
Winter Base 12 Weeks (winterbase): 12 weeks, 2026-11-30 -> 2027-02-21

Week 1, 2026-11-30
  + 2026-12-01 Tue  WORKOUT  W09_Tempo_60_2x12.zwo
  + 2026-12-02 Wed  WORKOUT  W10_Z2_45.zwo
  + 2026-12-03 Thu  WORKOUT  W04_Z2_60_Neuromuscular_Sprints.zwo
  + 2026-12-05 Sat  WORKOUT  W12_Group_Ride_2h30_Placeholder.zwo
  + 2026-12-06 Sun  WORKOUT  W01_Recovery_Spin_45.zwo
...
60 new, 0 updated, 0 unchanged, 0 stale.
Dry run: nothing was written. Run again with dry_run=false to apply.
```

Say "apply it" and the plan lands on your calendar, as in the screenshot
above. More things to ask:

- **Plan:**
  - *"What's planned for next week?"*
  - *"What's in my workout library?"*
- **Review:**
  - *"Review my race on Sunday: power, heart rate and load against my
    fitness. What went well and what should I work on?"*
  - *"How did last week go? Compare what was planned with what I rode."*
- **Adjust:**
  - *"Check my fitness and form over the last 6 weeks. Am I fresh enough for
    next week's plan, or should I rest or ease it off?"*
  - *"Move week 3's Thursday session to Friday."*
  - *"I was sick, push the rest of the plan back a week."*
  - *"Remove the winterbase plan from my calendar."*

Anything that writes shows you a dry run first and waits for your OK.

### Building a plan from your goals

Claude learns the plan format from the server's `plan_guide` tool, then
writes the plan as files (a `plan.yaml` and `.zwo` workouts) and pushes them.
So it needs somewhere to save them: Claude Code can do that directly, and in
Claude Desktop, add a filesystem extension that can write to a folder of your
choice.

> I'm riding a 100 km sportive on 14 June and have about 6 hours a week:
> short indoor rides Tuesday to Thursday, a long ride at the weekend. Build me
> a plan in `~/training/sportive`, then do a dry-run push and show me the diff.

Claude will usually ask about your goal and week first. Workouts use % of
FTP, so set your FTP in intervals.icu (or your training app).

Every plan and workout is checked before anything is sent, so a mistake in
what Claude wrote is reported, not uploaded. Your answers about fitness and
when to rest are Claude's suggestions from your intervals.icu numbers, not a
coach's or doctor's advice.

## Tools

| Tool | What it does | Writes? |
|---|---|---|
| `push_plan(plan_yaml, start_date?, dry_run=true, prune=false)` | Validate a plan, diff it against the calendar, upsert new and updated events; with `prune=true` also delete the plan's stale events | only with `dry_run=false` |
| `get_planned(oldest, newest, plan_id?)` | List planned events; optionally only one plan's | no |
| `delete_plan(plan_id, dry_run=true, oldest?, newest?)` | Remove every event the plan created, nothing else | only with `dry_run=false` |
| `get_fitness(oldest, newest)` | CTL, ATL, Form (TSB = CTL − ATL) and Form as % of CTL, per day | no |
| `get_activities(oldest, newest)` | Completed activities: time, distance, load, avg/normalized power, IF, HR | no |
| `move_workout(plan_yaml, week, day, to_day, to_week?, swap=false, dry_run=true)` | Move one session to another day: edits plan.yaml, then syncs with prune | only with `dry_run=false` |
| `shift_plan(plan_yaml, weeks=1, from_week?, dry_run=true)` | Push the rest of the plan back N weeks (illness, travel); past weeks stay | only with `dry_run=false` |
| `list_library(folder?)` | Your intervals.icu workout library: folders and plans with their workouts | no |
| `plan_guide()` | How to write a plan: the plan.yaml format and schema, the .zwo rules, examples and steps. Claude reads it before writing a plan | no |

`plan_yaml` is a path to the file. Everything also works from the
command line: see [docs/cli.md](docs/cli.md).

## Writing your own plan

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/gustavosoares/intervals-icu-planner-mcp/main/schemas/plan.schema.json
id: myblock
name: My 3-week block
start: 2026-11-30            # a Monday
templates:
  build:
    tue: W09_Tempo_60_2x12.zwo
    thu: W04_Z2_60_Neuromuscular_Sprints.zwo
    sat: { note: Long outdoor ride }
weeks:
  - { template: build }
  - { template: build, overrides: { thu: W06_Tempo_3x10.zwo } }
  - { template: build, overrides: { thu: null }, recovery: true }
```

Workouts are `.zwo` files in a `workouts/` folder next to the plan. The first
line gives you validation and autocomplete in editors with the YAML language
server. The full reference (overrides, notes, re-pushing, pruning, moving and
shifting) is in [docs/plan-reference.md](docs/plan-reference.md).

## Safety

This writes to your real training calendar, so it's built to be hard to misuse:

- **Dry run first**: every write returns a diff and waits for your OK.
- **Only its own events**: nothing without the plan's exact uid is touched or even shown.
- **Validate before upload**: the plan and every `.zwo` are checked, and one error means nothing is sent.
- **The API key stays private**: never logged, printed or put in error messages.
- **Careful file edits**: moves and shifts are previewed, never touch the past, and are written atomically.

Details in [docs/safety.md](docs/safety.md).

## Documentation

- [Setup](docs/setup.md): API key, the macOS Keychain, Claude Desktop and Claude Code
- [plan.yaml reference](docs/plan-reference.md): fields, uids, pruning, moving and shifting, the example plan
- [Training apps and activities](docs/training-apps.md): Zwift, MyWhoosh, Garmin, ERG mode, Strava limits
- [CLI](docs/cli.md): every command
- [Safety design](docs/safety.md)
- [Privacy](docs/privacy.md): what data goes where (nowhere but intervals.icu and your AI app)
- [How it works](docs/how-it-works.md): architecture and intervals.icu API notes
- [Troubleshooting](docs/troubleshooting.md)
- [Contributing](CONTRIBUTING.md) and [Changelog](CHANGELOG.md)

## Roadmap

- Activity analysis: planned vs completed, compliance per week
- Writing to the workout library (import or remove workouts in one dedicated folder)

## A note on AI assistance

This project is built with help from AI coding tools, which speed up writing code, tests
and documentation. Every change is reviewed and tested by a human maintainer before it's
merged, and the maintainer is responsible for what ships, including the safety rules above.

## License

MIT, see [LICENSE](LICENSE).
