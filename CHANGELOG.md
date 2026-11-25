# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0] - 2026-11-25

### Added
- `plan_guide` / `guide`: how to write a plan, for Claude: the plan.yaml
  format and JSON Schema, the .zwo rules, a tested example of each, and the
  steps from a goal to a dry-run push. The server's instructions tell Claude
  to read it before writing a plan, so "build me a plan for my sportive" no
  longer needs the example plan as a model.

### Changed
- README: example prompts for building a plan from your goals, reviewing a
  race or a week, and checking fitness before adjusting the plan, plus how to
  let Claude save a plan it writes.
- Install from PyPI: `uvx intervals-icu-planner-mcp`. The README and docs no
  longer need the GitHub URL, and explain upgrading and pinning a version.
- The version comes from the git tag (hatch-vcs) instead of `pyproject.toml`.
  The `publish` workflow takes the version as an input, checks it's newer than
  the last release and has a changelog section, and uses that section as the
  GitHub release notes.
- A `/release-pypi` Claude Code skill for maintainers, which walks through a
  release: changelog PR, TestPyPI, PyPI, and a smoke test of each upload.

## [0.1.0] - 2026-11-25

First release on PyPI.

### Added
- MCP server (stdio) with eight tools: `push_plan`, `get_planned`,
  `delete_plan`, `get_fitness`, `get_activities`, `move_workout`,
  `shift_plan` and `list_library`.
- Calendar diff before every write: new / updated / unchanged per date, plus
  stale events the plan no longer produces.
- `dry_run=true` by default for every write tool; `--apply` required in the CLI.
- Event uids `planner-<plan_id>-w<NN>-<day>`, matched exactly: a plan only
  ever modifies its own events.
- `.zwo` validation before upload: well-formed XML, known segments,
  durations > 0, power ratios in (0, 3], total under 6 hours.
- plan.yaml JSON Schema (`schemas/plan.schema.json`), generated from the
  pydantic models, with named week templates and a `weeks` list.
- CLI `intervals-icu-planner` with `push`, `delete`, `planned`, `fitness`,
  `activities`, `move`, `shift`, `library` and `schema` subcommands.
- httpx-based API client, independent of MCP.
- Example 12-week winter base plan.
- CI: ruff, mypy (strict) and pytest on Python 3.10–3.13.
- A manual `publish` workflow that uploads to TestPyPI or PyPI with trusted
  publishing, restricted to the maintainer, then tags the release. The PyPI
  page's README links point to GitHub.
- `push_plan(prune=true)` / `push --prune`: also delete the plan's stale
  events (sessions removed from the plan), from today on. Past events are
  never pruned, and deletion runs only after the upsert succeeds.
- `move_workout` / `move`: move one session to another day (or swap two),
  by editing plan.yaml and syncing with prune. Comments and layout are kept.
- `shift_plan` / `shift`: push the rest of a plan back N weeks. Past weeks
  stay; a plan with no sessions ridden yet just moves its start.
- `list_library` / `library`: read-only list of the workout library.

### Changed (from the unreleased prototype)
- The API key variable is now `INTERVALS_ICU_API_KEY`. `INTERVALS_API_KEY`
  still works but prints a deprecation warning.
- uids gained the `planner-` prefix. Events pushed by the prototype
  (`<id>-wNN-<day>`) aren't recognised; delete them from the calendar first.
- plan.yaml: `template` / `recovery` / `overrides` / `weeks: N` were replaced
  by named `templates` and a `weeks` list.
- Requires Python 3.10+.
- README rewritten for riders, not only developers: a calendar screenshot,
  a plain-language "what it's for", and example prompts to paste into Claude.
  The detailed reference moved to `docs/` (setup, plan reference, safety,
  CLI, training apps, how it works), and there's a new troubleshooting page.
- Pushes look for the plan's existing events one year back and two years
  ahead (or the plan's own range, if wider), so leftovers of a shorter or
  shifted plan are found, and moved events show as updated, not new.
- `push_plan` is now annotated as destructive, since it can delete with `prune`.
- The example plan's Saturday group ride is now a placeholder workout
  (`W12_Group_Ride_2h30_Placeholder.zwo`) instead of a note, so planned weekly
  load is realistic.
- `*.zip` is git-ignored, so exported workout archives aren't committed by mistake.

[Unreleased]: https://github.com/gustavosoares/intervals-icu-planner-mcp/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/gustavosoares/intervals-icu-planner-mcp/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/gustavosoares/intervals-icu-planner-mcp/releases/tag/v0.1.0
