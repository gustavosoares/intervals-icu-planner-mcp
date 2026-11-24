"""Load and validate a plan.yaml into a flat list of calendar entries."""

from __future__ import annotations

import datetime as dt
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


class PlanError(Exception):
    """Raised when a plan file is invalid. ``errors`` lists every problem found."""

    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__("\n".join(f"  - {e}" for e in errors))


@dataclass
class Workout:
    path: str
    filename: str
    name: str
    contents: str


@dataclass
class PlannedEvent:
    week: int
    day: str
    date: dt.date
    uid: str
    category: str  # "WORKOUT" or "NOTE"
    name: str
    description: Optional[str] = None
    workout: Optional[Workout] = None


@dataclass
class Plan:
    name: str
    id: str
    start: dt.date
    weeks: int
    type: str
    events: List[PlannedEvent] = field(default_factory=list)

    @property
    def end(self) -> dt.date:
        return self.start + dt.timedelta(weeks=self.weeks, days=-1)

    @property
    def uid_prefix(self) -> str:
        return f"{self.id}-w"


def parse_date(value: Any) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value).strip())


def parse_zwo(path: str) -> Workout:
    """Read and sanity-check a .zwo file. Raises ValueError on problems."""
    try:
        with open(path, encoding="utf-8") as f:
            contents = f.read()
    except OSError as e:
        raise ValueError(f"cannot read: {e.strerror or e}") from None
    try:
        root = ET.fromstring(contents)
    except ET.ParseError as e:
        raise ValueError(f"invalid XML: {e}") from None
    if root.tag != "workout_file":
        raise ValueError(f"root element is <{root.tag}>, expected <workout_file>")
    body = root.find("workout")
    if body is None or len(body) == 0:
        raise ValueError("missing or empty <workout> element")
    filename = os.path.basename(path)
    name = (root.findtext("name") or "").strip() or os.path.splitext(filename)[0]
    return Workout(path=path, filename=filename, name=name, contents=contents)


def _check_week_map(raw: Any, where: str, errors: List[str]) -> Dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        errors.append(f"{where}: must be a mapping of day -> entry")
        return {}
    out = {}
    for key, value in raw.items():
        day = str(key).lower()
        if day not in DAYS:
            errors.append(f"{where}: unknown day {key!r} (use {', '.join(DAYS)})")
            continue
        out[day] = value
    return out


def _week_numbers(raw: Any, weeks: int, where: str, errors: List[str]) -> List[int]:
    nums = []
    for w in raw:
        if isinstance(w, bool) or not isinstance(w, int):
            errors.append(f"{where}: week {w!r} is not an integer")
        elif not 1 <= w <= weeks:
            errors.append(f"{where}: week {w} is outside 1..{weeks}")
        else:
            nums.append(w)
    return nums


def load_plan(path: str, start: Optional[Any] = None) -> Plan:
    """Parse ``path`` and return a validated Plan. ``start`` overrides the plan's start date."""
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except OSError as e:
        raise PlanError([f"cannot read {path}: {e.strerror or e}"]) from None
    except yaml.YAMLError as e:
        raise PlanError([f"{path}: invalid YAML: {e}"]) from None
    if not isinstance(data, dict):
        raise PlanError([f"{path}: top level must be a mapping"])
    return build_plan(data, base_dir=os.path.dirname(os.path.abspath(path)), start=start)


def build_plan(data: Dict[str, Any], base_dir: str, start: Optional[Any] = None) -> Plan:
    errors: List[str] = []

    name = str(data.get("name") or "Training plan")
    plan_id = data.get("id")
    if not plan_id:
        errors.append("id: required (used as the prefix of every event uid)")
    elif not ID_RE.match(str(plan_id)):
        errors.append(f"id: {plan_id!r} may only contain letters, digits, '-' and '_'")
    plan_id = str(plan_id or "")

    start_raw = start if start is not None else data.get("start")
    start_date = None
    if start_raw is None:
        errors.append("start: required (or pass --start)")
    else:
        try:
            start_date = parse_date(start_raw)
        except ValueError:
            errors.append(f"start: {start_raw!r} is not a YYYY-MM-DD date")
        else:
            if start_date.weekday() != 0:
                errors.append(f"start: {start_date} is a {start_date:%A}, must be a Monday")

    weeks = data.get("weeks")
    if isinstance(weeks, bool) or not isinstance(weeks, int) or weeks < 1:
        errors.append(f"weeks: must be a positive integer, got {weeks!r}")
        weeks = 0

    event_type = str(data.get("type") or "Ride")
    workouts_dir = os.path.join(base_dir, str(data.get("workouts_dir") or "workouts"))

    template = _check_week_map(data.get("template"), "template", errors)

    recovery = data.get("recovery") or {}
    if not isinstance(recovery, dict):
        errors.append("recovery: must be a mapping with 'weeks' and 'template'")
        recovery = {}
    rec_weeks_raw = recovery.get("weeks") or []
    if not isinstance(rec_weeks_raw, list):
        errors.append("recovery.weeks: must be a list of week numbers")
        rec_weeks_raw = []
    recovery_weeks = set(_week_numbers(rec_weeks_raw, weeks, "recovery.weeks", errors))
    recovery_template = _check_week_map(recovery.get("template"), "recovery.template", errors)
    if recovery_weeks and "template" not in recovery:
        errors.append("recovery.template: required when recovery.weeks is set")

    overrides_raw = data.get("overrides") or {}
    if not isinstance(overrides_raw, dict):
        errors.append("overrides: must be a mapping of week number -> days")
        overrides_raw = {}
    overrides: Dict[int, Dict[str, Any]] = {}
    for w in _week_numbers(list(overrides_raw), weeks, "overrides", errors):
        overrides[w] = _check_week_map(overrides_raw[w], f"overrides.{w}", errors)

    cache: Dict[str, Any] = {}

    def resolve_workout(filename: str, where: str) -> Optional[Workout]:
        if filename not in cache:
            try:
                cache[filename] = parse_zwo(os.path.join(workouts_dir, filename))
            except ValueError as e:
                cache[filename] = f"{e}"
        result = cache[filename]
        if isinstance(result, str):
            errors.append(f"{where}: {filename}: {result}")
            return None
        return result

    events: List[PlannedEvent] = []
    for w in range(1, weeks + 1):
        base = recovery_template if w in recovery_weeks else template
        week_days = dict(base)
        week_days.update(overrides.get(w, {}))
        for offset, day in enumerate(DAYS):
            entry = week_days.get(day)
            if entry is None:
                continue
            where = f"week {w} {day}"
            date = start_date + dt.timedelta(weeks=w - 1, days=offset) if start_date else None
            uid = f"{plan_id}-w{w:02d}-{day}"
            ev = _make_event(entry, w, day, date, uid, where, resolve_workout, errors)
            if ev:
                events.append(ev)

    if not events and not errors:
        errors.append("plan produces no events (empty template?)")
    if errors:
        # Report each unique error once, in order (a bad file used every week repeats).
        seen, unique = set(), []
        for e in errors:
            key = e.split(": ", 1)[-1] if e.startswith("week ") else e
            if key not in seen:
                seen.add(key)
                unique.append(e)
        raise PlanError(unique)

    return Plan(name=name, id=plan_id, start=start_date, weeks=weeks, type=event_type, events=events)


def _make_event(entry, week, day, date, uid, where, resolve_workout, errors) -> Optional[PlannedEvent]:
    if isinstance(entry, str):
        entry = {"workout": entry}
    if not isinstance(entry, dict):
        errors.append(f"{where}: entry must be a .zwo filename or a mapping with 'workout' or 'note'")
        return None
    if ("workout" in entry) == ("note" in entry):
        errors.append(f"{where}: entry needs exactly one of 'workout' or 'note'")
        return None
    description = entry.get("description")
    if description is not None:
        description = str(description)
    if "note" in entry:
        return PlannedEvent(week=week, day=day, date=date, uid=uid, category="NOTE",
                            name=str(entry["note"]), description=description)
    filename = str(entry["workout"])
    workout = resolve_workout(filename, where)
    if workout is None:
        return None
    return PlannedEvent(week=week, day=day, date=date, uid=uid, category="WORKOUT",
                        name=str(entry.get("name") or workout.name),
                        description=description, workout=workout)
