# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- `push_plan(prune=true)` / `push --prune`: also delete the plan's stale
  events (sessions removed from the plan), from today on. Past events are
  never pruned, and deletion runs only after the upsert succeeds.

### Changed
- Pushes look for the plan's existing events one year back and two years
  ahead (or the plan's own range, if wider), so leftovers of a shorter or
  shifted plan are found, and moved events show as updated, not new.
- `push_plan` is now annotated as destructive, since it can delete with `prune`.

## [0.1.0] - Unreleased

### Added
- MCP server (stdio) with five tools: `push_plan`, `get_planned`,
  `delete_plan`, `get_fitness` and `get_activities`.
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
  `activities` and `schema` subcommands.
- httpx-based API client, independent of MCP.
- Example 12-week winter base plan.
- CI: ruff, mypy (strict) and pytest on Python 3.10–3.13.

### Changed (from the unreleased prototype)
- The API key variable is now `INTERVALS_ICU_API_KEY`. `INTERVALS_API_KEY`
  still works but prints a deprecation warning.
- uids gained the `planner-` prefix. Events pushed by the prototype
  (`<id>-wNN-<day>`) aren't recognised; delete them from the calendar first.
- plan.yaml: `template` / `recovery` / `overrides` / `weeks: N` were replaced
  by named `templates` and a `weeks` list.
- Requires Python 3.10+.

[0.1.0]: https://github.com/gustavosoares/intervals-icu-planner-mcp/releases/tag/v0.1.0
