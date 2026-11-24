# AGENTS.md

Guidance for AI coding agents (and humans) working in this repository.
`CLAUDE.md` imports this file, so Claude Code reads it too. Keep it current
when you learn something non-obvious.

## What this is

`intervals-icu-planner-mcp`: an MCP server (stdio) and CLI that push,
inspect and remove **whole training plans** on an intervals.icu calendar.
A plan is a `plan.yaml` plus `.zwo` workout files. It's a public portfolio
project, so code quality, tests and docs matter as much as features.

## Commands

```sh
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q                       # all HTTP mocked, no network
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy                            # strict, covers src/ and tests/
.venv/bin/intervals-icu-planner push examples/winter-base-12wk/plan.yaml   # offline dry run
.venv/bin/intervals-icu-planner schema > schemas/plan.schema.json          # after changing plan models
```

CI (`.github/workflows/tests.yml`) runs lint, types and pytest on Python
3.10–3.13, plus the offline example dry run. Branch protection relies on the
aggregate `ci-checks` job name, so don't rename it.

## Layout

```
src/intervals_icu_planner_mcp/
  client.py    httpx client. No MCP or plan imports; auth is any httpx.Auth (OAuth later)
  zwo.py       .zwo parse + validation
  plan.py      pydantic models (source of truth for the JSON Schema), uid helpers, expansion
  diff.py      plan vs calendar diff + rendering
  planner.py   operations shared by both front ends: push/planned/delete/fitness/activities
  server.py    MCP tools (thin wrappers over planner)
  cli.py       argparse front end (thin wrapper over planner)
  config.py    API key lookup
schemas/plan.schema.json        generated, committed; a test fails if it drifts
examples/winter-base-12wk/      public example plan + workouts
```

Keep the layering: new behaviour goes in `planner.py`, or lower in the
stack, never only in `server.py` or `cli.py`.

## Safety invariants (the core design: don't weaken without tests)

1. **Dry run by default.** `push_plan` and `delete_plan` default to
   `dry_run=True`, and the CLI needs `--apply`. Tests assert that dry runs
   make no write calls (respx routes for POST and PUT stay uncalled).
2. **Only its own uids.** Event uid = `planner-<plan_id>-w<NN>-<day>`.
   Ownership is `plan.owns_uid()`, a **full regex match, never `startswith`**,
   because `planner-winter-` would also match plan `winter-base`. Deletion
   re-checks ownership right before sending (`planner._delete_owned`).
   Foreign events must never be updated, deleted, or even shown in the diff.
3. **Validate before any network call.** Plan schema plus semantic checks
   (start is a Monday, templates exist, workout names have no path parts).
   Each `.zwo`: no DOCTYPE/ENTITY, known segments only, durations > 0, power
   ratios in (0, 3], total < 6 h. Report every error together.
4. **The API key is never logged.** It comes from `INTERVALS_ICU_API_KEY`,
   then `.env`, with the legacy `INTERVALS_API_KEY` accepted plus a warning.
   It never goes in errors, reprs or output. Tests use `FAKE_KEY` and check
   it doesn't leak.

## intervals.icu API facts (verified against the OpenAPI spec at `https://intervals.icu/api/v1/docs`)

- Athlete id `0` means the athlete who owns the credentials. Auth is HTTP
  Basic with user `API_KEY` and the key as password.
- `POST /athlete/0/events/bulk?upsert=true` matches on **`external_id`**, and
  the docs say only for events "created by the same OAuth application".
  `upsertOnUid=true` matches on `uid` instead, but it's ignored when
  `upsert=true` is set. We use `upsert=true` because the original prototype
  worked that way with a personal API key. Still unverified: that an
  *update* push (a changed event) updates in place instead of duplicating.
  Check with a dry run plus a read-back the first time an event changes.
- **The plan uid lives in `external_id`.** Verified on a real account:
  intervals.icu keeps the `external_id` we send but **replaces `uid` with
  its own random UUID**, so a `uid` we send is discarded (we don't send it).
  `diff.event_uid()` reads `external_id` first. Reading `uid` first once made
  a freshly pushed plan invisible to itself (the regression test is in
  `tests/test_diff.py`). Test fixtures (`conftest.cal_event`) mirror this
  shape, so keep them that way.
- `.zwo` contents are sent as-is in `file_contents`, plus `filename`.
- `PUT /events/bulk-delete` takes `[{"id": n}]` (by id has no OAuth
  restriction; by external_id does). It returns `{"eventsDeleted": n}`.
- `GET /events` returns `id`, `uid` (server UUID), `external_id`, `moving_time`, `workout_doc`,
  and so on, but **not the original .zwo**. The diff therefore compares
  workouts by name and duration only, and descriptions only for NOTE events
  (intervals.icu may rewrite workout descriptions).
- `GET /wellness` gives `id` (the date), `ctl`, `atl`, `rampRate`. Form % =
  (ctl − atl) / ctl × 100.
- `GET /activities` returns newest first. **Strava-imported activities are
  empty stubs** (`source: "STRAVA"`, `_note`) because of Strava's API terms.
  Useful fields: `moving_time`, `distance` (m), `icu_training_load`,
  `icu_average_watts`, `icu_weighted_avg_watts`, `icu_intensity` (a
  percentage, 86.5 = IF 0.865), `average_heartrate`.

## MCP SDK notes

- This uses **`mcp` 2.x**: FastMCP was renamed `MCPServer`
  (`from mcp.server.mcpserver import MCPServer`). `mcp.server.fastmcp` no
  longer exists.
- Raise `mcp.server.mcpserver.exceptions.ToolError` for expected failures,
  and the model sees the message. Any other exception reaches the model only
  as "Error executing tool X".
- `list_tools()` and `call_tool()` are async. Tool schemas use `input_schema`.
  Annotations take `read_only_hint`, `destructive_hint` and so on.

## Testing conventions

- HTTP is mocked with respx. Unmatched requests fail, so a missing route
  means an unexpected call.
- An autouse fixture in `tests/conftest.py` removes API-key env vars and
  `chdir`s to a temp dir, so tests never pick up a real key or `.env`.
- `tests/test_example.py` enforces **no personal data** in the example:
  no absolute watts (`\d+ ?W`), no athlete ids. Example workouts use % of
  FTP only, author `intervals-icu-planner-mcp example`, and no HR numbers,
  names or clubs. It also checks the example's file count; update that when
  workouts are added or removed.
- Changing `plan.py` models means regenerating `schemas/plan.schema.json`.

## Environment gotchas (macOS)

- The shell is **zsh**: an unquoted `$VAR` holding a space-separated list is
  **not** word-split. Use arrays (`NEW=(a b); cmd "${NEW[@]}"`).
- There's no GNU `timeout`. BSD `sed -i` needs `''`.
- Claude Desktop, launched from the Dock, gets neither Homebrew's PATH nor
  `~/.zshrc`. Its MCP config must use `/opt/homebrew/bin/uvx`, with the key
  read from the macOS Keychain through a `/bin/sh -c` wrapper (see README).
- `claude mcp add` without `-s user` registers the server **only for the
  current directory**. A local-scope entry overrides a user-scope one.
- Until the package is on PyPI, install with
  `uvx --from git+https://github.com/gustavosoares/intervals-icu-planner-mcp[@branch] intervals-icu-planner-mcp`.
  On `main` before the MCP PR merged, that entry point was the old CLI.

## Conventions

- Commit messages: imperative subject, no Conventional Commits prefix.
  Work goes on a branch and merges through a PR.
- Update `CHANGELOG.md` (Keep a Changelog) for user-visible changes.
- Never commit `.env`, API keys, athlete ids, FTP or other personal data.
  Before anything is published, read files you didn't write (e.g. an
  extracted zip) and strip personal data from them.
- Writes to a real calendar always go dry run first, and only get applied
  after a person has seen the diff and said yes.
