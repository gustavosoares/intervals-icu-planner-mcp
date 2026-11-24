"""Edit a plan.yaml in place, keeping its comments and layout.

``plan.yaml`` is the source of truth: tools that move sessions change the file,
then push it. Editing a copy only on the calendar would be undone by the next
push. Every function here takes the file's text and returns the new text plus a
summary; nothing touches the disk or the network. The result is validated
(:func:`.plan.build_plan`) before anything is written.

Round-tripping uses ruamel.yaml. It can't reproduce every layout (it drops the
spaces inside ``{ flow: maps }``, for one), so only the lines an edit changes are
taken from its output; every other line is kept exactly as written (see
:func:`_splice`).
"""

from __future__ import annotations

import copy
import datetime as dt
import difflib
import io
import re
from dataclasses import dataclass, field
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from .plan import DAYS

# (mapping, sequence, offset) indents to try, most common first.
_INDENTS = ((2, 4, 2), (2, 2, 0), (4, 6, 4), (4, 4, 2))
_WEEK_COMMENT = re.compile(r"#\s*Week\s+\d+")
_SHIFT_NOTE = "rest, added by shift_plan"


class EditError(Exception):
    """The requested change can't be made to this plan."""


@dataclass
class Edited:
    text: str
    summary: list[str] = field(default_factory=list)
    reformatted: bool = False  # the file's layout couldn't be kept exactly


def _new_yaml(indent: tuple[int, int, int]) -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.width = 4096  # never re-wrap long lines
    y.indent(mapping=indent[0], sequence=indent[1], offset=indent[2])
    y.representer.add_representer(
        type(None), lambda r, _: r.represent_scalar("tag:yaml.org,2002:null", "null")
    )
    return y


def _dump(y: YAML, doc: Any) -> str:
    out = io.StringIO()
    y.dump(doc, out)
    return out.getvalue()


@dataclass
class _Doc:
    """A loaded plan.yaml: the ruamel document plus what's needed to write it back."""

    yaml: YAML
    doc: CommentedMap
    src: str  # the file as written
    base: str  # ruamel's rendering of the unedited document
    aligned: bool  # base and src have the same lines, so edits can be spliced into src

    def text(self) -> str:
        return _splice(self.src, self.base, _dump(self.yaml, self.doc), self.aligned)


def _yaml_for(src: str) -> tuple[YAML, Any, str]:
    """The YAML instance whose rendering of ``src`` is closest to it, the document,
    and that rendering: identical if possible, else with the same number of lines."""
    fallback = None
    for indent in _INDENTS:
        y = _new_yaml(indent)
        doc = y.load(src)
        base = _dump(y, doc)
        if base == src:
            return y, doc, base
        if fallback is None and base.count("\n") == src.count("\n"):
            fallback = (y, doc, base)
    if fallback is not None:
        return fallback
    y = _new_yaml(_INDENTS[0])
    doc = y.load(src)
    return y, doc, _dump(y, doc)


def _splice(src: str, base: str, new: str, aligned: bool) -> str:
    """Apply the change from ``base`` to ``new`` onto ``src``, line by line.

    Lines the edit didn't touch come from ``src`` verbatim, so ruamel's layout
    normalisation only shows up on the lines that actually changed.
    """
    if base == src or not aligned:
        return new
    s, b, n = (
        src.splitlines(keepends=True),
        base.splitlines(keepends=True),
        new.splitlines(keepends=True),
    )
    out: list[str] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, b, n, autojunk=False).get_opcodes():
        out += s[i1:i2] if tag == "equal" else n[j1:j2]
    return "".join(out)


def _load(src: str) -> _Doc:
    y, doc, base = _yaml_for(src)
    if not isinstance(doc, CommentedMap) or not isinstance(doc.get("weeks"), CommentedSeq):
        raise EditError("plan.yaml has no `weeks` list")
    if not isinstance(doc.get("templates"), CommentedMap):
        raise EditError("plan.yaml has no `templates` mapping")
    return _Doc(y, doc, src, base, aligned=base.count("\n") == src.count("\n"))


def describe(entry: Any) -> str:
    """Short text for a day's entry, for summaries and errors."""
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        if "workout" in entry:
            return str(entry["workout"])
        if "note" in entry:
            return f"note '{entry['note']}'"
    return "nothing"


def _day(value: str) -> str:
    d = value.strip().lower()[:3]
    if d not in DAYS:
        raise EditError(f"{value!r} is not a day (use {', '.join(DAYS)})")
    return d


# ---------------------------------------------------------------- move_workout


def _week_item(weeks: CommentedSeq, week: int) -> CommentedMap:
    if not 1 <= week <= len(weeks):
        raise EditError(f"week {week} is outside 1..{len(weeks)}")
    item = weeks[week - 1]
    if not isinstance(item, CommentedMap):
        raise EditError(f"week {week} is not a mapping")
    return item


def _template_entry(doc: CommentedMap, item: CommentedMap, day: str) -> Any:
    template = doc["templates"].get(item.get("template"))
    if template is None:
        raise EditError(f"unknown template {item.get('template')!r}")
    return template.get(day)


def _effective(doc: CommentedMap, week: int, day: str) -> Any:
    item = _week_item(doc["weeks"], week)
    overrides = item.get("overrides") or {}
    if day in overrides:
        return overrides[day]
    return _template_entry(doc, item, day)


def _set_override(doc: CommentedMap, week: int, day: str, value: Any) -> None:
    """Make ``day`` of ``week`` hold ``value``, as minimally as possible."""
    item = _week_item(doc["weeks"], week)
    overrides = item.get("overrides")
    if _template_entry(doc, item, day) == value:  # back to the template: no override needed
        if overrides is not None and day in overrides:
            del overrides[day]
            if not overrides:
                del item["overrides"]
        return
    if overrides is None:
        overrides = CommentedMap()
        if item.fa.flow_style():
            overrides.fa.set_flow_style()
        item["overrides"] = overrides
    overrides[day] = copy.deepcopy(value)
    if isinstance(overrides[day], CommentedMap) and overrides.fa.flow_style():
        overrides[day].fa.set_flow_style()  # a block map can't sit inside a flow map


def move_session(
    src: str,
    *,
    week: int,
    day: str,
    to_day: str,
    to_week: int | None = None,
    swap: bool = False,
) -> Edited:
    """Move the session on ``week``/``day`` to ``to_week``/``to_day`` (same week by default).

    The target day must be free, unless ``swap``: then the two sessions trade places.
    """
    d = _load(src)
    doc = d.doc
    day, to_day = _day(day), _day(to_day)
    to_week = week if to_week is None else to_week
    if (week, day) == (to_week, to_day):
        raise EditError("the session is already on that day")

    moving = _effective(doc, week, day)
    if moving is None:
        raise EditError(f"week {week} {day} has no session to move")
    target = _effective(doc, to_week, to_day)
    if target is not None and not swap:
        raise EditError(
            f"week {to_week} {to_day} already has {describe(target)}; "
            "pick a free day or pass swap=true to trade places"
        )

    _set_override(doc, week, day, target if swap else None)
    _set_override(doc, to_week, to_day, moving)
    summary = [f"moved {describe(moving)}: week {week} {day} -> week {to_week} {to_day}"]
    if swap:
        summary.append(f"moved {describe(target)}: week {to_week} {to_day} -> week {week} {day}")
    return Edited(d.text(), summary, reformatted=not d.aligned)


# ------------------------------------------------------------------ shift_plan


def shift_start(src: str, *, weeks: int) -> Edited:
    """Move the whole plan by ``weeks`` (for a plan that hasn't started)."""
    d = _load(src)
    doc = d.doc
    old = doc.get("start")
    if not isinstance(old, dt.date):
        raise EditError("plan.yaml `start` is not a date")
    doc["start"] = old + dt.timedelta(weeks=weeks)
    return Edited(d.text(), [f"start: {old} -> {doc['start']}"], reformatted=not d.aligned)


def _rest_template(templates: CommentedMap) -> tuple[str, bool]:
    """Name of a template with no sessions, adding ``rest: {}`` if there isn't one."""
    for name, days in templates.items():
        if not days or all(days.get(d) is None for d in DAYS):
            return str(name), False
    name, n = "rest", 2
    while name in templates:
        name, n = f"rest{n}", n + 1
    empty = CommentedMap()
    empty.fa.set_flow_style()
    templates[name] = empty
    return name, True


def shift_remaining(src: str, *, weeks: int, from_week: int) -> Edited:
    """Insert ``weeks`` empty weeks before ``from_week``: it and everything after move later."""
    d = _load(src)
    doc = d.doc
    seq: CommentedSeq = doc["weeks"]
    if not 1 <= from_week <= len(seq):
        raise EditError(f"from_week {from_week} is outside 1..{len(seq)}")
    rest, added = _rest_template(doc["templates"])
    flow = isinstance(seq[from_week - 1], CommentedMap) and seq[from_week - 1].fa.flow_style()
    for i in range(weeks):
        item = CommentedMap(template=rest)
        if flow:
            item.fa.set_flow_style()
        seq.insert(from_week - 1 + i, item)
    inserted = set(range(from_week, from_week + weeks))  # 1-based week numbers
    text = _renumber_week_comments(d.text(), inserted)

    last = from_week + weeks - 1
    span = f"week {from_week}" if weeks == 1 else f"weeks {from_week}-{last}"
    summary = [f"inserted {span} as rest (template '{rest}')"]
    summary.append(f"old weeks {from_week}-{len(seq) - weeks} are now {last + 1}-{len(seq)}")
    if added:
        summary.append(f"added an empty template '{rest}'")
    return Edited(text, summary, reformatted=not d.aligned)


def _renumber_week_comments(text: str, inserted: set[int]) -> str:
    """Keep ``# Week N`` comments on the weeks list correct after inserting weeks.

    Only comments of exactly that shape are touched. Inserted weeks get one too, if
    the list uses them.
    """
    lines = text.splitlines(keepends=True)
    try:
        start = next(i for i, ln in enumerate(lines) if ln.startswith("weeks:"))
    except StopIteration:
        return text
    item_indent: int | None = None
    items: list[int] = []  # line index of each week item
    for i in range(start + 1, len(lines)):
        ln = lines[i]
        if ln.strip() and not ln[0].isspace() and not ln.startswith(("-", "#")):
            break  # next top-level key
        stripped = ln.lstrip(" ")
        if stripped.startswith("- "):
            indent = len(ln) - len(stripped)
            if item_indent is None:
                item_indent = indent
            if indent == item_indent:
                items.append(i)
    commented = [i for i in items if _WEEK_COMMENT.search(lines[i])]
    if not commented:
        return text
    column = lines[commented[0]].index("#")
    for week, i in enumerate(items, start=1):
        body = lines[i].rstrip("\n")
        if _WEEK_COMMENT.search(body):
            body = _WEEK_COMMENT.sub(f"# Week {week}", body, count=1)
        elif week in inserted:
            body = f"{body.ljust(column - 1)} # Week {week} ({_SHIFT_NOTE})"
        lines[i] = body + "\n"
    return "".join(lines)
