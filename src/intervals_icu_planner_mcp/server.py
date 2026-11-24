"""The MCP server: five tools over stdio, thin wrappers around :mod:`.planner`.

Run it with ``uvx intervals-icu-planner-mcp`` (or ``intervals-icu-planner-mcp``).
"""

from __future__ import annotations

from collections.abc import Callable

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from . import __version__, planner
from .client import ApiError, IntervalsClient
from .config import find_api_key
from .plan import PlanError

INSTRUCTIONS = """\
Plan-level operations on the user's intervals.icu calendar.

Safety rules: push_plan and delete_plan default to dry_run=true and return a
calendar diff. Show that diff to the user and get their explicit OK before
calling again with dry_run=false. These tools only ever modify events whose uid
was created by a plan (planner-<plan_id>-w<NN>-<day>); nothing else on the
calendar is touched.
"""

mcp = MCPServer(
    "intervals-icu-planner",
    instructions=INSTRUCTIONS,
    version=__version__,
)


def _client() -> IntervalsClient | None:
    key = find_api_key()
    return IntervalsClient.from_api_key(key) if key else None


def _run(op: Callable[[IntervalsClient | None], str]) -> str:
    """Run an operation, turning expected failures into tool errors the model can read."""
    client = _client()
    try:
        return op(client)
    except PlanError as e:
        raise ToolError(f"invalid plan:\n{e}") from None
    except (planner.PlannerError, ApiError) as e:
        raise ToolError(str(e)) from None
    finally:
        if client is not None:
            client.close()


READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=True)


@mcp.tool(
    annotations=ToolAnnotations(destructive_hint=True, idempotent_hint=True, open_world_hint=True)
)
def push_plan(
    plan_yaml: str,
    start_date: str | None = None,
    dry_run: bool = True,
    prune: bool = False,
) -> str:
    """Push a whole training plan (plan.yaml + .zwo workouts) to the intervals.icu calendar.

    Validates the plan and every workout first, then compares it with the calendar and
    returns a per-date diff: + new, ~ updated, = unchanged, ! stale. With dry_run=true
    (the default) nothing is written. Only call with dry_run=false after the user has
    seen the diff and agreed. Re-pushing is safe: events are matched by uid and updated
    in place.

    Stale events (this plan's events that the plan no longer produces) are kept
    unless prune=true, which deletes the ones dated today or later. Past events are
    never pruned, and nothing outside the plan is ever touched.

    Args:
        plan_yaml: Path to the plan.yaml file.
        start_date: Optional YYYY-MM-DD Monday for week 1, overriding the plan's start.
        dry_run: true = show the diff only; false = write new and updated events.
        prune: true = also delete stale events from today on (shown as - in the diff).
    """
    return _run(
        lambda c: planner.push(plan_yaml, client=c, start=start_date, dry_run=dry_run, prune=prune)
    )


@mcp.tool(annotations=READ_ONLY)
def get_planned(oldest: str, newest: str, plan_id: str | None = None) -> str:
    """List planned events (workouts, notes, ...) on the calendar between two dates.

    Args:
        oldest: First day, YYYY-MM-DD.
        newest: Last day, YYYY-MM-DD (inclusive).
        plan_id: Optional plan id; only list events created by that plan.
    """
    return _run(lambda c: planner.planned(oldest, newest, client=c, plan_id=plan_id))


@mcp.tool(
    annotations=ToolAnnotations(destructive_hint=True, idempotent_hint=True, open_world_hint=True)
)
def delete_plan(
    plan_id: str,
    dry_run: bool = True,
    oldest: str | None = None,
    newest: str | None = None,
) -> str:
    """Remove every event a plan created, and nothing else.

    Only events whose uid is exactly planner-<plan_id>-w<NN>-<day> are selected. With
    dry_run=true (the default) it lists them and deletes nothing. Only call with
    dry_run=false after the user has seen the list and agreed.

    Args:
        plan_id: The plan's id (the `id` in its plan.yaml).
        dry_run: true = list what would be deleted; false = delete it.
        oldest: Optional first day to search (default: one year ago).
        newest: Optional last day to search (default: two years ahead).
    """
    return _run(
        lambda c: planner.delete(plan_id, client=c, dry_run=dry_run, oldest=oldest, newest=newest)
    )


@mcp.tool(annotations=READ_ONLY)
def get_fitness(oldest: str, newest: str) -> str:
    """Daily fitness (CTL), fatigue (ATL), Form (TSB = CTL - ATL) and Form as % of CTL.

    Args:
        oldest: First day, YYYY-MM-DD.
        newest: Last day, YYYY-MM-DD (inclusive).
    """
    return _run(lambda c: planner.fitness(oldest, newest, client=c))


@mcp.tool(annotations=READ_ONLY)
def get_activities(oldest: str, newest: str) -> str:
    """Completed activities between two dates: type, duration, distance, training load,
    average and normalized power, intensity factor and average heart rate.

    Activities that reached intervals.icu through Strava can't be read via the API and
    are listed without details.

    Args:
        oldest: First day, YYYY-MM-DD.
        newest: Last day, YYYY-MM-DD (inclusive).
    """
    return _run(lambda c: planner.activities(oldest, newest, client=c))


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
