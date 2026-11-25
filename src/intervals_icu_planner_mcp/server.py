"""The MCP server: tools over stdio, thin wrappers around :mod:`.planner`.

Run it with ``uvx intervals-icu-planner-mcp`` (or ``intervals-icu-planner-mcp``).
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from . import __version__, guide, oauth, planner
from .client import ApiError, IntervalsClient
from .config import find_api_key, find_plans_dir, make_client
from .plan import PlanError

INSTRUCTIONS = """\
Plan-level operations on the user's intervals.icu calendar.

Safety rules: push_plan, delete_plan, move_workout and shift_plan default to
dry_run=true and return a diff. Show that diff to the user and get their
explicit OK before calling again with dry_run=false. These tools only ever
modify events whose uid was created by a plan (planner-<plan_id>-w<NN>-<day>);
nothing else on the calendar is touched. move_workout and shift_plan also edit
the plan.yaml file (its diff is in the dry run), because the file is the
source of truth.

To write a new plan or change a plan's workouts, call plan_guide first: it has
the plan.yaml format, the .zwo rules and the steps to follow.

If a tool says it's not connected to intervals.icu, call connect: the user
signs in and approves access in their browser.
"""

PLANS_DIR = find_plans_dir()
if PLANS_DIR:
    INSTRUCTIONS += (
        f"\nPlans must be saved in {PLANS_DIR} (each plan in its own folder, with its"
        "\nworkouts/ inside): the tools refuse plan files anywhere else.\n"
    )

mcp = MCPServer(
    "intervals-icu-planner",
    instructions=INSTRUCTIONS,
    version=__version__,
)


def _client() -> IntervalsClient | None:
    return make_client()


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
        lambda c: planner.push(
            plan_yaml,
            client=c,
            start=start_date,
            dry_run=dry_run,
            prune=prune,
            plans_dir=find_plans_dir(),
        )
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


WRITES_PLAN = ToolAnnotations(destructive_hint=True, idempotent_hint=False, open_world_hint=True)


@mcp.tool(annotations=WRITES_PLAN)
def move_workout(
    plan_yaml: str,
    week: int,
    day: str,
    to_day: str,
    to_week: int | None = None,
    swap: bool = False,
    dry_run: bool = True,
) -> str:
    """Move one planned session to another day, e.g. week 3 Tuesday -> Wednesday.

    The change is made in plan.yaml (the source of truth, comments kept), then the
    calendar is synced with prune. With dry_run=true (the default) it shows the
    plan.yaml diff and the calendar diff and changes nothing. Only call with
    dry_run=false after the user has seen both and agreed. Refuses to move past
    sessions, or onto a day that already has one unless swap=true.

    Args:
        plan_yaml: Path to the plan.yaml file.
        week: Plan week of the session (1 = first week).
        day: Day of the session: mon, tue, wed, thu, fri, sat or sun.
        to_day: Day to move it to.
        to_week: Week to move it to (default: the same week).
        swap: If the target day has a session, trade places instead of refusing.
        dry_run: true = show the diffs only; false = write plan.yaml and the calendar.
    """
    return _run(
        lambda c: planner.move(
            plan_yaml,
            week,
            day,
            to_day,
            client=c,
            to_week=to_week,
            swap=swap,
            dry_run=dry_run,
            plans_dir=find_plans_dir(),
        )
    )


@mcp.tool(annotations=WRITES_PLAN)
def shift_plan(
    plan_yaml: str,
    weeks: int = 1,
    from_week: int | None = None,
    dry_run: bool = True,
) -> str:
    """Push the rest of a plan back by N weeks (e.g. after illness or travel).

    Past weeks stay where they happened. If the plan is under way, N empty (rest)
    weeks are inserted before from_week (default: the current week), so it and every
    later week move N weeks later. If the plan hasn't started, its start date moves.
    The change is made in plan.yaml, then the calendar is synced with prune; past
    events are never deleted. With dry_run=true (the default) nothing changes. Only
    call with dry_run=false after the user has seen the diffs and agreed.

    Args:
        plan_yaml: Path to the plan.yaml file.
        weeks: How many weeks to push back (1-12).
        from_week: First week to move (default: the current week).
        dry_run: true = show the diffs only; false = write plan.yaml and the calendar.
    """
    return _run(
        lambda c: planner.shift(
            plan_yaml,
            client=c,
            weeks=weeks,
            from_week=from_week,
            dry_run=dry_run,
            plans_dir=find_plans_dir(),
        )
    )


@mcp.tool(annotations=READ_ONLY)
def list_library(folder: str | None = None) -> str:
    """List the workout library on intervals.icu: folders and plans with their workouts
    (name, type, duration, training load). Read-only.

    Args:
        folder: Optional text; only folders whose name contains it.
    """
    return _run(lambda c: planner.library(client=c, folder=folder))


CONNECT_WAIT = 45.0  # seconds connect waits for the browser before answering
_login: oauth.Login | None = None
_login_lock = threading.Lock()


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=True
    )
)
def connect(again: bool = False) -> str:
    """Connect to the user's intervals.icu account: opens intervals.icu in their browser,
    where they sign in and approve access. Call this when another tool says it's not
    connected. No API key is needed; the access token is kept in the system keychain.

    Args:
        again: true = sign in again even if already connected (e.g. another account).
    """
    global _login
    if find_api_key():
        return "Already connected with an intervals.icu API key (INTERVALS_ICU_API_KEY)."
    current = oauth.load_token()
    if current and not again:
        return f"Already connected to intervals.icu as {current.who}."
    with _login_lock:
        if _login is None or _login.finished:
            try:
                _login = oauth.Login().start()
            except OSError as e:
                raise ToolError(f"could not start the sign-in ({type(e).__name__})") from None
        login = _login
    login.wait(CONNECT_WAIT)
    if login.token:
        return f"Connected to intervals.icu as {login.token.who}."
    if login.error:
        raise ToolError(f"not connected: {login.error}. Call connect to try again.")
    return (
        "Waiting for the user to approve access in their browser. If no intervals.icu "
        f"page opened, ask them to open this link:\n{login.url}\n"
        "After they approve, call connect again to confirm."
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def plan_guide() -> str:
    """How to write a training plan: the plan.yaml format (with its JSON Schema), the
    .zwo workout rules, an example of each, and the steps from the athlete's goal to a
    pushed plan. Call this before writing or changing plan files. Read-only, offline.
    """
    return guide.plan_guide()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
