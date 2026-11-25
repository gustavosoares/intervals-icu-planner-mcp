"""The operations behind both the MCP tools and the CLI.

Each function takes an :class:`IntervalsClient` (or ``None`` where offline use
makes sense) and returns text for a person or a model to read. Safety rules
live here, so every front end gets them:

- writes happen only when ``dry_run`` is False, and the diff is computed first;
- only events whose uid belongs to the plan are updated or deleted.
"""

from __future__ import annotations

import datetime as dt
import difflib
import os
import shutil
from collections.abc import Callable
from typing import Any

import yaml

from . import edit
from .client import JSON, ApiError, IntervalsClient
from .diff import compute_diff, event_date, event_uid, render_diff
from .edit import Edited, EditError
from .plan import (
    DAYS,
    Plan,
    PlannedEvent,
    build_plan,
    ensure_inside,
    load_plan,
    owns_uid,
    valid_plan_id,
)

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


def search_window(plan: Plan, today: dt.date) -> tuple[dt.date, dt.date]:
    """Where to look for a plan's existing events.

    Wider than the plan's own dates, so events left behind by a shorter or shifted
    version of the plan are still found (shown as moved or stale).
    """
    return (
        min(plan.start, today - DEFAULT_LOOKBACK),
        max(plan.end, today + DEFAULT_LOOKAHEAD),
    )


def push(
    plan_path: str,
    *,
    client: IntervalsClient | None,
    start: str | None = None,
    dry_run: bool = True,
    prune: bool = False,
    plans_dir: str | None = None,
    today: Callable[[], dt.date] = dt.date.today,
    apply_hint: str = "dry_run=false",
    prune_hint: str = "prune=true",
) -> str:
    """Validate the plan, diff it against the calendar, and write only if asked.

    ``prune=True`` also deletes stale events (this plan's uids that the plan no
    longer produces), from today on; past events are never pruned. Without it a
    push never deletes anything.

    With no client a dry run still works: the calendar isn't checked and every
    event shows as new. With ``plans_dir``, the plan must be inside that folder.
    """
    plan = load_plan(plan_path, start=start, root=plans_dir)  # PlanError before any network call
    return _sync(
        plan,
        client=client,
        dry_run=dry_run,
        prune=prune,
        now=today(),
        apply_hint=apply_hint,
        prune_hint=prune_hint,
    )


def _sync(
    plan: Plan,
    *,
    client: IntervalsClient | None,
    dry_run: bool,
    prune: bool,
    now: dt.date,
    apply_hint: str,
    prune_hint: str,
) -> str:
    """Diff a validated plan against the calendar; upsert (and prune) unless a dry run."""
    if not dry_run:
        _require(client)
    existing = client.list_events(*search_window(plan, now)) if client else None
    diff = compute_diff(plan, existing)

    def render(applied: bool, deleted: int = 0) -> str:
        return render_diff(
            diff,
            applied=applied,
            apply_hint=apply_hint,
            prune=prune,
            prune_hint=prune_hint,
            today=now,
            deleted=deleted,
        )

    if dry_run:
        return render(applied=False)

    assert client is not None
    to_send = diff.to_send
    if to_send:
        client.upsert_events([event_payload(e, plan.type) for e in to_send])
    deleted = 0
    doomed = diff.prunable(now) if prune else []
    if doomed:  # after the upsert: a failed upsert raises before anything is deleted
        deleted = _delete_owned(client, plan.id, doomed)
    return render(applied=True, deleted=deleted)


# ------------------------------------------------------------ move and shift


def week_of(plan: Plan, day: dt.date) -> int:
    """The plan week ``day`` falls in (may be < 1 or > plan.weeks)."""
    return (day - plan.start).days // 7 + 1


def session_date(plan: Plan, week: int, day: str) -> dt.date:
    return plan.week_start(week) + dt.timedelta(days=DAYS.index(day))


def _edit_and_sync(
    plan_path: str,
    make_edit: Callable[[str, Plan], Edited],
    *,
    client: IntervalsClient | None,
    dry_run: bool,
    now: dt.date,
    apply_hint: str,
    plans_dir: str | None,
) -> str:
    """Edit plan.yaml, validate the result, then (unless a dry run) write it and push with prune.

    The dry run shows both the plan.yaml change and the calendar diff. On apply the
    file is written first (it is the source of truth; git can undo it), then the
    calendar follows. If the push fails, the error says how to finish it.
    """
    ensure_inside(plan_path, plans_dir)  # before reading anything
    with open(plan_path, encoding="utf-8") as f:
        src = f.read()
    current = load_plan(plan_path, root=plans_dir)  # the file must be valid before we change it
    try:
        edited = make_edit(src, current)
    except EditError as e:
        raise PlannerError(str(e)) from None
    base_dir = os.path.dirname(os.path.abspath(plan_path))
    new_plan = build_plan(
        yaml.safe_load(edited.text), base_dir, root=plans_dir
    )  # PlanError if broken

    changes = "".join(
        difflib.unified_diff(
            src.splitlines(keepends=True),
            edited.text.splitlines(keepends=True),
            fromfile=os.path.basename(plan_path),
            tofile=os.path.basename(plan_path),
            n=0,
        )
    )
    head = ["Plan file change:", *(f"  {s}" for s in edited.summary)]
    if edited.reformatted:
        head.append("  note: the file's layout couldn't be kept exactly; check the diff")
    head += ["", changes.rstrip("\n"), ""]

    if not dry_run:
        _require(client)
        with open(plan_path, encoding="utf-8") as f:
            if f.read() != src:
                raise PlannerError(f"{plan_path} changed while this ran; nothing was written")
        _write_atomic(plan_path, edited.text)
        head.insert(0, f"Wrote {plan_path}.")
    try:
        calendar = _sync(
            new_plan,
            client=client,
            dry_run=dry_run,
            prune=True,
            now=now,
            apply_hint=apply_hint,
            prune_hint="prune=true",
        )
    except ApiError as e:
        if dry_run:
            raise
        raise ApiError(
            f"{e}\n{plan_path} was updated but the calendar wasn't: "
            "run push_plan with prune=true to finish."
        ) from None
    return "\n".join(head) + "\n" + calendar


def _write_atomic(path: str, text: str) -> None:
    tmp = f"{path}.tmp-{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    shutil.copymode(path, tmp)
    os.replace(tmp, path)


def move(
    plan_path: str,
    week: int,
    day: str,
    to_day: str,
    *,
    client: IntervalsClient | None,
    to_week: int | None = None,
    swap: bool = False,
    dry_run: bool = True,
    plans_dir: str | None = None,
    today: Callable[[], dt.date] = dt.date.today,
    apply_hint: str = "dry_run=false",
) -> str:
    """Move one session to another day by editing plan.yaml, then push with prune."""
    now = today()

    def make_edit(src: str, plan: Plan) -> Edited:
        edited = edit.move_session(
            src, week=week, day=day, to_day=to_day, to_week=to_week, swap=swap
        )
        d_from = session_date(plan, week, day[:3].lower())
        d_to = session_date(plan, week if to_week is None else to_week, to_day[:3].lower())
        for label, d in (("session", d_from), ("target day", d_to)):
            if d < now:
                raise EditError(f"the {label} ({d}) is in the past; only future sessions can move")
        return edited

    return _edit_and_sync(
        plan_path,
        make_edit,
        client=client,
        dry_run=dry_run,
        now=now,
        apply_hint=apply_hint,
        plans_dir=plans_dir,
    )


def shift(
    plan_path: str,
    *,
    client: IntervalsClient | None,
    weeks: int = 1,
    from_week: int | None = None,
    dry_run: bool = True,
    plans_dir: str | None = None,
    today: Callable[[], dt.date] = dt.date.today,
    apply_hint: str = "dry_run=false",
) -> str:
    """Push the rest of the plan back by ``weeks``, leaving past weeks where they were.

    Nothing ridden yet (no session before today): the start date moves, and every
    event is moved in place. Under way: ``weeks`` rest weeks are inserted before
    ``from_week`` (default: the current week).
    """
    if not 1 <= weeks <= 12:
        raise PlannerError("weeks must be between 1 and 12")
    now = today()

    def make_edit(src: str, plan: Plan) -> Edited:
        current = week_of(plan, now)
        started = any(e.date < now for e in plan.events)
        if not started and from_week is None:
            return edit.shift_start(src, weeks=weeks)
        if current > plan.weeks:
            raise EditError("the plan has already finished")
        start_at = max(current, 1) if from_week is None else from_week
        if start_at < current:
            raise EditError(f"week {start_at} is in the past (this is week {current})")
        return edit.shift_remaining(src, weeks=weeks, from_week=start_at)

    return _edit_and_sync(
        plan_path,
        make_edit,
        client=client,
        dry_run=dry_run,
        now=now,
        apply_hint=apply_hint,
        plans_dir=plans_dir,
    )


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


# ------------------------------------------------------------------- library


def library(*, client: IntervalsClient | None, folder: str | None = None) -> str:
    """The athlete's workout library (read-only): folders and plans with their workouts.

    ``folder`` keeps only folders whose name contains it (case-insensitive).
    """
    folders = _require(client).list_folders()
    if folder:
        folders = [f for f in folders if folder.lower() in str(f.get("name") or "").lower()]
    if not folders:
        scope = f" matching {folder!r}" if folder else ""
        return f"No workout folders{scope} in the library."

    out: list[str] = []
    total = 0
    for f in sorted(folders, key=lambda f: str(f.get("name") or "").lower()):
        workouts = [w for w in f.get("children") or [] if isinstance(w, dict)]
        total += len(workouts)
        kind = "plan" if str(f.get("type") or "").upper() == "PLAN" else "folder"
        out.append(f"{f.get('name') or '(unnamed)'} ({kind}, {len(workouts)} workouts)")
        rows = [
            [
                _truncate(str(w.get("name") or ""), 44),
                str(w.get("type") or "-"),
                _duration(w.get("moving_time")),
                _num(w.get("icu_training_load")),
            ]
            for w in sorted(workouts, key=lambda w: str(w.get("name") or "").lower())
        ]
        if rows:
            table = _table(["workout", "type", "time", "load"], rows, right={2, 3})
            out.append("\n".join(f"  {line}" for line in table.splitlines()))
        out.append("")
    head = f"Workout library: {len(folders)} folder(s), {total} workouts.\n\n"
    return head + "\n".join(out).rstrip()


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
