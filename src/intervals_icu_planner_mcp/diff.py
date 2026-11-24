"""Compare a plan with what is already on the calendar, and render the result.

Only calendar events whose uid belongs to the plan (see :func:`.plan.owns_uid`)
are ever considered. Anything else on the calendar is invisible to the diff, so
it can never be updated or reported as stale.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Literal

from .plan import Plan, PlannedEvent, owns_uid

Status = Literal["new", "updated", "unchanged"]
MARK = {"new": "+", "updated": "~", "unchanged": "="}


def event_uid(event: dict[str, Any]) -> str:
    """The plan uid of a calendar event: its ``external_id``.

    intervals.icu stores the id we send in ``external_id`` and replaces ``uid``
    with its own random UUID, so ``uid`` is only a fallback (for display; it
    never matches a plan's uid pattern).
    """
    return str(event.get("external_id") or event.get("uid") or "")


def event_date(event: dict[str, Any]) -> str:
    return str(event.get("start_date_local") or "")[:10]


@dataclass(frozen=True)
class Change:
    status: Status
    event: PlannedEvent
    existing_id: int | None = None
    fields: tuple[str, ...] = ()  # what changed, for "updated"


@dataclass
class Diff:
    plan: Plan
    changes: list[Change]
    stale: list[dict[str, Any]] = field(default_factory=list)
    offline: bool = False  # calendar not checked (no API key)

    def count(self, status: Status) -> int:
        return sum(1 for c in self.changes if c.status == status)

    @property
    def to_send(self) -> list[PlannedEvent]:
        return [c.event for c in self.changes if c.status != "unchanged"]

    def prunable(self, today: dt.date) -> list[dict[str, Any]]:
        """Stale events that pruning may delete: today or later. Past ones are kept."""
        return [e for e in self.stale if event_date(e) >= today.isoformat()]


def _mmss(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


def compare(planned: PlannedEvent, existing: dict[str, Any]) -> tuple[str, ...]:
    """Fields that differ between the plan and the calendar, as short descriptions.

    Workout contents aren't returned by the API, so a workout is compared by
    name and duration. Descriptions are compared for notes only: intervals.icu
    may rewrite a workout's description from the .zwo.
    """
    changed: list[str] = []
    old_date = event_date(existing)
    if old_date != planned.date.isoformat():
        changed.append(f"date {old_date or '?'} -> {planned.date}")
    if existing.get("category") != planned.category:
        changed.append(f"category {existing.get('category')} -> {planned.category}")
    if (existing.get("name") or "") != planned.name:
        changed.append(f"name {existing.get('name')!r} -> {planned.name!r}")
    if (
        planned.category == "NOTE"
        and (existing.get("description") or "").strip() != (planned.description or "").strip()
    ):
        changed.append("description")
    if planned.workout is not None:
        old = existing.get("moving_time")
        new = planned.workout.total_seconds
        if isinstance(old, int) and abs(old - new) > 1:
            changed.append(f"duration {_mmss(old)} -> {_mmss(new)}")
    return tuple(changed)


def compute_diff(plan: Plan, existing: Iterable[dict[str, Any]] | None) -> Diff:
    """``existing=None`` means the calendar wasn't checked: everything is new."""
    if existing is None:
        return Diff(plan, [Change("new", e) for e in plan.events], offline=True)

    mine: dict[str, dict[str, Any]] = {}
    for ev in existing:
        uid = event_uid(ev)
        if owns_uid(plan.id, uid):
            mine.setdefault(uid, ev)

    changes = []
    for planned in plan.events:
        found = mine.pop(planned.uid, None)
        if found is None:
            changes.append(Change("new", planned))
            continue
        fields = compare(planned, found)
        changes.append(
            Change("updated" if fields else "unchanged", planned, found.get("id"), fields)
        )

    stale = sorted(mine.values(), key=lambda e: (event_date(e), event_uid(e)))
    return Diff(plan, changes, stale)


def render_diff(
    diff: Diff,
    *,
    applied: bool = False,
    apply_hint: str = "dry_run=false",
    prune: bool = False,
    prune_hint: str = "prune=true",
    today: dt.date | None = None,
    deleted: int = 0,
) -> str:
    plan = diff.plan
    lines = [f"{plan.name} ({plan.id}): {plan.weeks} weeks, {plan.start} -> {plan.end}"]
    if diff.offline:
        lines.append("Calendar not checked (no API key): every event is shown as new.")
    lines.append("")

    week = 0
    for c in diff.changes:
        ev = c.event
        if ev.week != week:
            if week:
                lines.append("")
            week = ev.week
            tag = "  (recovery)" if ev.week in plan.recovery_weeks else ""
            lines.append(f"Week {ev.week}, {plan.week_start(ev.week)}{tag}")
        what = ev.workout.filename if ev.workout else ev.name
        line = f"  {MARK[c.status]} {ev.date} {ev.date:%a}  {ev.category:<7}  {what}"
        if c.fields:
            line += f"  [{'; '.join(c.fields)}]"
        lines.append(line)

    prunable = diff.prunable(today or dt.date.today()) if prune else []
    doomed = {event_uid(e) for e in prunable}  # stale uids are unique
    if diff.stale:
        lines += ["", "Stale: on the calendar with this plan's uid but no longer in the plan."]
        if prune:
            lines.append("Pruning deletes the ones from today on (-); earlier ones are kept (!).")
        else:
            lines.append(f"Pushing keeps them; push with {prune_hint} to delete them.")
        for e in diff.stale:
            mark, note = (
                ("-", "") if event_uid(e) in doomed else ("!", "  (past, kept)" if prune else "")
            )
            lines.append(
                f"  {mark} {event_date(e)}  {e.get('category', '?'):<7}  {e.get('name')}  "
                f"{event_uid(e)}{note}"
            )

    n_new, n_upd, n_same = diff.count("new"), diff.count("updated"), diff.count("unchanged")
    stale = f"{len(diff.stale)} stale"
    if prune and diff.stale:
        stale += f" ({len(prunable)} to delete)"
    lines += ["", f"{n_new} new, {n_upd} updated, {n_same} unchanged, {stale}."]
    if applied:
        sent = n_new + n_upd
        msg = f"Applied: sent {sent} event{'s' if sent != 1 else ''} to intervals.icu"
        if prune:
            msg += f", deleted {deleted} stale event{'s' if deleted != 1 else ''}"
        lines.append(msg + ".")
    else:
        lines.append(f"Dry run: nothing was written. Run again with {apply_hint} to apply.")
    return "\n".join(lines)
