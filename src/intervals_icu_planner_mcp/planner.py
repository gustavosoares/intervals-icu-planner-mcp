"""The operations behind both the MCP tools and the CLI.

Each function takes an :class:`IntervalsClient` (or ``None`` where offline use
makes sense) and returns text for a person or a model to read. Safety rules
live here, so every front end gets them:

- writes happen only when ``dry_run`` is False, and the diff is computed first;
- only events whose uid belongs to the plan are updated or deleted.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any

from .client import JSON, IntervalsClient
from .diff import compute_diff, event_date, event_uid, render_diff
from .plan import PlannedEvent, load_plan, owns_uid, valid_plan_id

DEFAULT_LOOKBACK = dt.timedelta(days=365)
DEFAULT_LOOKAHEAD = dt.timedelta(days=730)
MAX_RANGE = dt.timedelta(days=5 * 366)


class PlannerError(Exception):
    """Bad input to an operation (dates, plan id, missing credentials)."""


# ------------------------------------------------------------------- helpers


def parse_day(value: str, name: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value.strip())
    except (AttributeError, ValueError):
        raise PlannerError(f"{name}: {value!r} is not a YYYY-MM-DD date") from None


def parse_range(oldest: str, newest: str) -> tuple[dt.date, dt.date]:
    lo, hi = parse_day(oldest, "oldest"), parse_day(newest, "newest")
    if lo > hi:
        raise PlannerError(f"oldest ({lo}) is after newest ({hi})")
    if hi - lo > MAX_RANGE:
        raise PlannerError("date range is longer than 5 years")
    return lo, hi


def _require(client: IntervalsClient | None) -> IntervalsClient:
    if client is None:
        raise PlannerError(
            "no intervals.icu API key: set INTERVALS_ICU_API_KEY or add it to a .env file "
            "(intervals.icu -> Settings -> Developer Settings)"
        )
    return client


def _table(headers: list[str], rows: list[list[str]], right: set[int] | None = None) -> str:
    right = right or set()
    widths = [
        max(len(h), *(len(r[i]) for r in rows)) if rows else len(h) for i, h in enumerate(headers)
    ]

    def fmt(cells: list[str]) -> str:
        out = [
            c.rjust(w) if i in right else c.ljust(w)
            for i, (c, w) in enumerate(zip(cells, widths, strict=True))
        ]
        return "  ".join(out).rstrip()

    return "\n".join([fmt(headers), fmt(["-" * w for w in widths]), *(fmt(r) for r in rows)])


def _num(value: Any, fmt: str = "{:.0f}") -> str:
    return (
        fmt.format(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else "-"
    )


def _duration(seconds: Any) -> str:
    if not isinstance(seconds, int) or seconds <= 0:
        return "-"
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}"


def _truncate(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


# ---------------------------------------------------------------------- push


def event_payload(ev: PlannedEvent, event_type: str = "Ride") -> JSON:
    """The intervals.icu event for a planned entry. The .zwo is sent as-is."""
    date = f"{ev.date.isoformat()}T00:00:00"
    # The plan uid travels in external_id: upsert=true matches on it, and it's the
    # field intervals.icu keeps (it replaces `uid` with a server-generated UUID).
    payload: JSON = {
        "category": ev.category,
        "start_date_local": date,
        "name": ev.name,
        "external_id": ev.uid,
    }
    if ev.category == "NOTE":
        payload["end_date_local"] = date
        payload["description"] = ev.description or ""
    else:
        assert ev.workout is not None
        payload["type"] = event_type
        payload["filename"] = ev.workout.filename
        payload["file_contents"] = ev.workout.contents
        if ev.description:
            payload["description"] = ev.description
    return payload


def push(
    plan_path: str,
    *,
    client: IntervalsClient | None,
    start: str | None = None,
    dry_run: bool = True,
    apply_hint: str = "dry_run=false",
) -> str:
    """Validate the plan, diff it against the calendar, and write only if asked.

    With no client a dry run still works: the calendar isn't checked and every
    event shows as new.
    """
    plan = load_plan(plan_path, start=start)  # PlanError before any network call
    if not dry_run:
        _require(client)
    existing = client.list_events(plan.start, plan.end) if client else None
    diff = compute_diff(plan, existing)
    if dry_run:
        return render_diff(diff, apply_hint=apply_hint)

    assert client is not None
    to_send = diff.to_send
    if to_send:
        client.upsert_events([event_payload(e, plan.type) for e in to_send])
    return render_diff(diff, applied=True)


# ------------------------------------------------------------------- planned


def planned(
    oldest: str, newest: str, *, client: IntervalsClient | None, plan_id: str | None = None
) -> str:
    lo, hi = parse_range(oldest, newest)
    if plan_id is not None and not valid_plan_id(plan_id):
        raise PlannerError(f"plan_id: {plan_id!r} is not a valid plan id")
    events = _require(client).list_events(lo, hi)
    if plan_id is not None:
        events = [e for e in events if owns_uid(plan_id, event_uid(e))]
    events.sort(key=lambda e: (event_date(e), event_uid(e)))

    scope = f" from plan {plan_id!r}" if plan_id else ""
    if not events:
        return f"No events{scope} between {lo} and {hi}."
    rows = [
        [
            event_date(e),
            str(e.get("category") or "-"),
            _truncate(str(e.get("name") or ""), 40),
            event_uid(e) or "-",
        ]
        for e in events
    ]
    head = f"{len(events)} event{'s' if len(events) != 1 else ''}{scope} between {lo} and {hi}:\n\n"
    return head + _table(["date", "category", "name", "uid"], rows)


# -------------------------------------------------------------------- delete


def select_owned(plan_id: str, events: list[JSON]) -> list[JSON]:
    """Events created by this plan, and nothing else."""
    return [e for e in events if owns_uid(plan_id, event_uid(e)) and isinstance(e.get("id"), int)]


def _delete_owned(client: IntervalsClient, plan_id: str, doomed: list[JSON]) -> int:
    """Second guard, right before the write: refuse any event the plan doesn't own."""
    foreign = [e for e in doomed if not owns_uid(plan_id, event_uid(e))]
    if foreign:
        raise PlannerError(f"refusing to delete {len(foreign)} event(s) not created by {plan_id!r}")
    return client.delete_events([int(e["id"]) for e in doomed])


def delete(
    plan_id: str,
    *,
    client: IntervalsClient | None,
    dry_run: bool = True,
    oldest: str | None = None,
    newest: str | None = None,
    today: Callable[[], dt.date] = dt.date.today,
    apply_hint: str = "dry_run=false",
) -> str:
    if not valid_plan_id(plan_id):
        raise PlannerError(f"plan_id: {plan_id!r} is not a valid plan id")
    now = today()
    lo, hi = parse_range(
        oldest or (now - DEFAULT_LOOKBACK).isoformat(),
        newest or (now + DEFAULT_LOOKAHEAD).isoformat(),
    )
    c = _require(client)
    doomed = sorted(
        select_owned(plan_id, c.list_events(lo, hi)), key=lambda e: (event_date(e), event_uid(e))
    )

    if not doomed:
        return f"No events from plan {plan_id!r} between {lo} and {hi}. Nothing to delete."
    lines = [f"{len(doomed)} event(s) from plan {plan_id!r} between {lo} and {hi}:", ""]
    lines += [
        f"  - {event_date(e)}  {e.get('category', '?'):<7}  {e.get('name')}  {event_uid(e)}"
        for e in doomed
    ]
    lines.append("")
    if dry_run:
        lines.append(f"Dry run: nothing was deleted. Run again with {apply_hint} to delete these.")
    else:
        n = _delete_owned(c, plan_id, doomed)
        lines.append(f"Deleted {n} event(s). Nothing else on the calendar was touched.")
    return "\n".join(lines)


# ------------------------------------------------------------------- fitness


def form_percent(ctl: float, atl: float) -> float | None:
    """Form (TSB) as a percentage of fitness (CTL), the way intervals.icu shows it."""
    return None if ctl <= 0 else (ctl - atl) / ctl * 100


def fitness(oldest: str, newest: str, *, client: IntervalsClient | None) -> str:
    lo, hi = parse_range(oldest, newest)
    records = sorted(_require(client).list_wellness(lo, hi), key=lambda r: str(r.get("id")))
    rows = []
    for r in records:
        ctl, atl = r.get("ctl"), r.get("atl")
        if not isinstance(ctl, (int, float)) or not isinstance(atl, (int, float)):
            rows.append([str(r.get("id")), "-", "-", "-", "-"])
            continue
        pct = form_percent(ctl, atl)
        rows.append(
            [
                str(r.get("id")),
                f"{ctl:.1f}",
                f"{atl:.1f}",
                f"{ctl - atl:+.1f}",
                "-" if pct is None else f"{pct:+.0f}%",
            ]
        )
    if not rows:
        return f"No wellness data between {lo} and {hi}."
    head = f"Fitness {lo} -> {hi} (CTL = fitness, ATL = fatigue, Form = CTL - ATL):\n\n"
    return head + _table(["date", "CTL", "ATL", "Form", "Form %"], rows, right={1, 2, 3, 4})


# ---------------------------------------------------------------- activities


STRAVA_NOTE = (
    "{n} activit{ies} came from Strava, and intervals.icu can't share Strava data through "
    "its API. Connect Garmin, Zwift, MyWhoosh etc. to intervals.icu directly to see them here."
)


def is_strava_stub(a: JSON) -> bool:
    return str(a.get("source") or "").upper() == "STRAVA" and (
        "_note" in a or not a.get("moving_time")
    )


def activities(oldest: str, newest: str, *, client: IntervalsClient | None) -> str:
    lo, hi = parse_range(oldest, newest)
    items = sorted(
        _require(client).list_activities(lo, hi), key=lambda a: str(a.get("start_date_local"))
    )
    if not items:
        return f"No activities between {lo} and {hi}."

    rows, stubs, total_time, total_load = [], 0, 0, 0.0
    for a in items:
        date = str(a.get("start_date_local") or "")[:10]
        if is_strava_stub(a):
            stubs += 1
            rows.append([date, "-", "(Strava import: details not available via API)", *["-"] * 7])
            continue
        moving, load = a.get("moving_time"), a.get("icu_training_load")
        total_time += moving if isinstance(moving, int) else 0
        total_load += load if isinstance(load, (int, float)) else 0
        intensity = a.get("icu_intensity")
        dist = a.get("distance")
        rows.append(
            [
                date,
                str(a.get("type") or "-"),
                _truncate(str(a.get("name") or ""), 32),
                _duration(moving),
                _num(dist / 1000, "{:.1f}") if isinstance(dist, (int, float)) else "-",
                _num(load),
                _num(a.get("icu_average_watts")),
                _num(a.get("icu_weighted_avg_watts")),
                _num(intensity / 100, "{:.2f}") if isinstance(intensity, (int, float)) else "-",
                _num(a.get("average_heartrate")),
            ]
        )

    out = [
        f"{len(items)} activit{'ies' if len(items) != 1 else 'y'} {lo} -> {hi}: "
        f"{_duration(total_time)} moving, load {total_load:.0f}.",
        "",
        _table(
            ["date", "type", "name", "time", "km", "load", "avg W", "NP", "IF", "HR"],
            rows,
            right={3, 4, 5, 6, 7, 8, 9},
        ),
    ]
    if stubs:
        out += ["", STRAVA_NOTE.format(n=stubs, ies="ies" if stubs != 1 else "y")]
    return "\n".join(out)
