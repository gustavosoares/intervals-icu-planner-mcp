"""plan.yaml: schema, validation, and expansion into dated calendar events.

The pydantic models below are the source of truth for ``schemas/plan.schema.json``
(see :func:`plan_json_schema`). Loading a plan validates its structure against
them, then checks what a schema can't: the start is a Monday, templates exist,
and every .zwo file exists and passes :mod:`.zwo` validation. All problems are
reported together, before anything touches the network.
"""

from __future__ import annotations

import datetime as dt
import os
import re
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    Tag,
    ValidationError,
)

from .zwo import Workout, ZwoError, parse_zwo

DAYS: tuple[str, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
ID_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,39}$"
UID_PREFIX = "planner-"
SCHEMA_ID = (
    "https://raw.githubusercontent.com/gustavosoares/intervals-icu-planner-mcp/main/"
    "schemas/plan.schema.json"
)


class PlanError(Exception):
    """The plan is invalid. ``errors`` lists every problem found."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(f"  - {e}" for e in errors))


# --------------------------------------------------------------------------- uids


def make_uid(plan_id: str, week: int, day: str) -> str:
    return f"{UID_PREFIX}{plan_id}-w{week:02d}-{day}"


def uid_regex(plan_id: str) -> re.Pattern[str]:
    """The exact shape of a uid this plan created.

    A plain ``startswith("planner-winter-")`` would also match a plan called
    ``winter-base``, so ownership is a full match, never a prefix test.
    """
    days = "|".join(DAYS)
    return re.compile(rf"^{re.escape(UID_PREFIX + plan_id)}-w\d{{2}}-(?:{days})$")


def owns_uid(plan_id: str, uid: str | None) -> bool:
    """True only if ``uid`` was created by plan ``plan_id``."""
    if not uid or not re.match(ID_PATTERN, plan_id):
        return False
    return uid_regex(plan_id).match(uid) is not None


def valid_plan_id(plan_id: str) -> bool:
    return re.match(ID_PATTERN, plan_id) is not None


# ------------------------------------------------------------------------ schema

_Strict = ConfigDict(extra="forbid", str_strip_whitespace=True)


class WorkoutEntry(BaseModel):
    """A planned workout from a .zwo file, with optional name/description overrides."""

    model_config = _Strict
    workout: str = Field(pattern=r"\.zwo$", description=".zwo file name inside workouts_dir")
    name: str | None = Field(None, min_length=1, description="Defaults to the <name> in the .zwo")
    description: str | None = None


class NoteEntry(BaseModel):
    """A calendar note (e.g. an outdoor ride), no workout file."""

    model_config = _Strict
    note: str = Field(min_length=1, description="Title of the note")
    description: str | None = None


def _entry_kind(value: Any) -> str | None:
    if isinstance(value, str):
        return "file"
    if isinstance(value, dict):
        if "workout" in value and "note" not in value:
            return "workout"
        if "note" in value and "workout" not in value:
            return "note"
    elif isinstance(value, (WorkoutEntry, NoteEntry)):
        return "workout" if isinstance(value, WorkoutEntry) else "note"
    return None


ZwoFile = Annotated[str, Field(pattern=r"\.zwo$", description="Shorthand for {workout: <file>}")]
Entry = Annotated[
    Annotated[ZwoFile, Tag("file")]
    | Annotated[WorkoutEntry, Tag("workout")]
    | Annotated[NoteEntry, Tag("note")],
    Discriminator(
        _entry_kind,
        custom_error_type="invalid_entry",
        custom_error_message=(
            "must be a .zwo file name, {workout: <file>, ...} or {note: <title>, ...}"
        ),
    ),
]


class WeekDays(BaseModel):
    """Day -> session. Days left out have nothing scheduled.

    In a week's ``overrides``, ``day: null`` removes that day's session.
    """

    model_config = _Strict
    mon: Entry | None = None
    tue: Entry | None = None
    wed: Entry | None = None
    thu: Entry | None = None
    fri: Entry | None = None
    sat: Entry | None = None
    sun: Entry | None = None


class Week(BaseModel):
    """One week of the plan, in order: the first item is week 1."""

    model_config = _Strict
    template: str = Field(min_length=1, description="Name of an entry in `templates`")
    overrides: WeekDays | None = Field(None, description="Merged over the template, day by day")
    recovery: bool = Field(False, description="Marks a recovery week (shown in the output)")


class PlanFile(BaseModel):
    """A multi-week training plan for intervals.icu."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, title="plan.yaml")
    id: str = Field(
        pattern=ID_PATTERN,
        description=(
            "Prefix of every event uid: planner-<id>-w<NN>-<day>. "
            "Lowercase letters, digits, - and _"
        ),
    )
    name: str = Field(min_length=1)
    start: dt.date = Field(description="Monday of week 1 (YYYY-MM-DD)")
    workouts_dir: str = Field(
        "workouts", description="Folder with the .zwo files, relative to plan.yaml"
    )
    type: str = Field("Ride", description="intervals.icu activity type for workouts")
    templates: dict[str, WeekDays] = Field(min_length=1, description="Named week templates")
    weeks: list[Week] = Field(min_length=1, max_length=99)


def plan_json_schema() -> dict[str, Any]:
    """The JSON Schema for plan.yaml, as committed in schemas/plan.schema.json."""
    schema = PlanFile.model_json_schema()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,
        **schema,
    }


# ----------------------------------------------------------------- expanded plan


@dataclass(frozen=True)
class PlannedEvent:
    week: int
    day: str
    date: dt.date
    uid: str
    category: Literal["WORKOUT", "NOTE"]
    name: str
    description: str | None = None
    workout: Workout | None = None
    recovery: bool = False


@dataclass
class Plan:
    id: str
    name: str
    start: dt.date
    weeks: int
    type: str
    events: list[PlannedEvent] = field(default_factory=list)
    recovery_weeks: frozenset[int] = frozenset()

    @property
    def end(self) -> dt.date:
        return self.start + dt.timedelta(weeks=self.weeks, days=-1)

    def week_start(self, week: int) -> dt.date:
        return self.start + dt.timedelta(weeks=week - 1)


_TAGS = {"file", "workout", "note"}


def _loc(loc: tuple[int | str, ...]) -> str:
    """('weeks', 3, 'overrides', 'tue', 'file') -> 'weeks[4].overrides.tue'."""
    parts: list[str] = []
    for i, p in enumerate(loc):
        prev = loc[i - 1] if i else None
        if isinstance(p, int) and prev == "weeks":
            parts[-1] = f"weeks[{p + 1}]"  # 1-based: weeks[1] is week 1
        elif p in _TAGS and prev in DAYS:
            continue  # the union's discriminator tag, not a real key
        else:
            parts.append(str(p))
    return ".".join(parts) or "plan"


def _format_validation_error(err: ValidationError) -> list[str]:
    return [f"{_loc(tuple(e['loc']))}: {e['msg']}" for e in err.errors()]


def _parse_start(value: Any) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value).strip())


def load_plan(path: str, start: str | dt.date | None = None) -> Plan:
    """Read, validate and expand ``path``. ``start`` overrides the plan's start Monday."""
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


def build_plan(data: dict[str, Any], base_dir: str, start: str | dt.date | None = None) -> Plan:
    """Validate parsed YAML and expand it into dated events."""
    try:
        pf = PlanFile.model_validate(data)
    except ValidationError as e:
        raise PlanError(_format_validation_error(e)) from None

    errors: list[str] = []
    start_date = pf.start
    if start is not None:
        try:
            start_date = _parse_start(start)
        except ValueError:
            errors.append(f"start: {start!r} is not a YYYY-MM-DD date")
    if start_date.weekday() != 0:
        errors.append(f"start: {start_date} is a {start_date:%A}, must be a Monday")

    workouts_dir = os.path.join(base_dir, pf.workouts_dir)
    cache: dict[str, Workout | str] = {}

    def resolve(filename: str, where: str) -> Workout | None:
        if filename not in cache:
            if os.path.basename(filename) != filename:
                cache[filename] = "must be a file name inside workouts_dir, not a path"
            else:
                try:
                    cache[filename] = parse_zwo(os.path.join(workouts_dir, filename))
                except ZwoError as e:
                    cache[filename] = "; ".join(e.errors)
        result = cache[filename]
        if isinstance(result, str):
            errors.append(f"{filename}: {result}")
            return None
        return result

    events: list[PlannedEvent] = []
    recovery_weeks: set[int] = set()
    for w, week in enumerate(pf.weeks, start=1):
        template = pf.templates.get(week.template)
        if template is None:
            known = ", ".join(sorted(pf.templates))
            errors.append(
                f"weeks[{w}].template: unknown template {week.template!r} (have: {known})"
            )
            continue
        if week.recovery:
            recovery_weeks.add(w)
        days: dict[str, Any] = {d: getattr(template, d) for d in DAYS}
        if week.overrides is not None:
            for d in week.overrides.model_fields_set:
                days[d] = getattr(week.overrides, d)
        for offset, day in enumerate(DAYS):
            entry = days[day]
            if entry is None:
                continue
            date = start_date + dt.timedelta(weeks=w - 1, days=offset)
            uid = make_uid(pf.id, w, day)
            if isinstance(entry, NoteEntry):
                events.append(
                    PlannedEvent(
                        w,
                        day,
                        date,
                        uid,
                        "NOTE",
                        entry.note,
                        entry.description,
                        recovery=week.recovery,
                    )
                )
                continue
            we = WorkoutEntry(workout=entry) if isinstance(entry, str) else entry
            workout = resolve(we.workout, f"weeks[{w}].{day}")
            if workout is not None:
                events.append(
                    PlannedEvent(
                        w,
                        day,
                        date,
                        uid,
                        "WORKOUT",
                        we.name or workout.name,
                        we.description,
                        workout,
                        recovery=week.recovery,
                    )
                )

    if not events and not errors:
        errors.append("plan produces no events (are the templates empty?)")
    if errors:
        raise PlanError(list(dict.fromkeys(errors)))  # a bad file used every week: report once

    return Plan(
        id=pf.id,
        name=pf.name,
        start=start_date,
        weeks=len(pf.weeks),
        type=pf.type,
        events=events,
        recovery_weeks=frozenset(recovery_weeks),
    )
