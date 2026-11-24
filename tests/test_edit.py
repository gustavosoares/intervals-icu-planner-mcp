import datetime as dt

import pytest
import yaml

from intervals_icu_planner_mcp import edit
from intervals_icu_planner_mcp.edit import EditError, move_session, shift_remaining, shift_start
from intervals_icu_planner_mcp.plan import build_plan

from .conftest import EXAMPLE

FLOW = """\
# a comment that must survive
id: t
name: T
start: 2026-11-30
templates:
  build:
    tue: A.zwo
    wed: { workout: B.zwo, name: Bee }
    sat: { note: Group ride, description: or indoors }
weeks:
  - {template: build}                 # Week 1
  - {template: build}                 # Week 2
  - {template: build, overrides: {sat: null}}  # Week 3
"""

BLOCK = """\
id: t
name: T
start: 2026-11-30  # a Monday
templates:
  build:
    tue: A.zwo
    sat:
      note: Group ride
weeks:
- template: build
- template: build
  overrides:
    sat: null
"""


def load(text, workouts):
    return build_plan(yaml.safe_load(text), str(workouts))


def changed_lines(a: str, b: str) -> list[str]:
    import difflib

    return [
        ln
        for ln in difflib.unified_diff(a.splitlines(), b.splitlines(), lineterm="", n=0)
        if ln[:1] in "+-" and not ln.startswith(("+++", "---"))
    ]


@pytest.mark.parametrize("src", [BLOCK, EXAMPLE.read_text()])
def test_round_trip_is_byte_identical(src):
    _y, _doc, base = edit._yaml_for(src)
    assert base == src


def test_lines_an_edit_does_not_touch_are_kept_verbatim():
    """ruamel drops the spaces in `{ flow: maps }`; untouched lines must keep them."""
    e = move_session(FLOW, week=2, day="tue", to_day="thu")
    assert "    wed: { workout: B.zwo, name: Bee }\n" in e.text
    assert "    sat: { note: Group ride, description: or indoors }\n" in e.text
    assert len(changed_lines(FLOW, e.text)) == 2
    assert not e.reformatted


def test_move_to_a_free_day_is_a_minimal_override(workouts):
    e = move_session(FLOW, week=1, day="tue", to_day="thu")
    assert e.summary == ["moved A.zwo: week 1 tue -> week 1 thu"]
    assert changed_lines(FLOW, e.text) == [
        "-  - {template: build}                 # Week 1",
        "+  - {template: build, overrides: {tue: null, thu: A.zwo}} # Week 1",
    ]
    assert "# a comment that must survive" in e.text
    ev = {(x.week, x.day) for x in load(e.text, workouts).events}
    assert (1, "thu") in ev and (1, "tue") not in ev


def test_moving_back_removes_the_override():
    there = move_session(FLOW, week=1, day="tue", to_day="thu")
    back = move_session(there.text, week=1, day="thu", to_day="tue")
    assert yaml.safe_load(back.text) == yaml.safe_load(FLOW)
    week1 = next(ln for ln in back.text.splitlines() if ln.endswith("# Week 1"))
    assert week1.split("#")[0].strip() == "- {template: build}"  # the override is gone again


def test_occupied_day_is_refused_unless_swap(workouts):
    with pytest.raises(EditError, match=r"week 1 wed already has B\.zwo.*swap=true"):
        move_session(FLOW, week=1, day="tue", to_day="wed")
    e = move_session(FLOW, week=1, day="tue", to_day="wed", swap=True)
    assert len(e.summary) == 2
    days = {x.day: x for x in load(e.text, workouts).events if x.week == 1}
    assert days["wed"].workout.filename == "A.zwo"
    assert (days["tue"].workout.filename, days["tue"].name) == ("B.zwo", "Bee")


def test_move_across_weeks_copies_the_entry(workouts):
    e = move_session(FLOW, week=1, day="sat", to_day="mon", to_week=2)
    plan = load(e.text, workouts)
    moved = next(x for x in plan.events if (x.week, x.day) == (2, "mon"))
    assert (moved.category, moved.name, moved.description) == ("NOTE", "Group ride", "or indoors")
    assert not any((x.week, x.day) == (1, "sat") for x in plan.events)


def test_block_style_files_stay_block_style(workouts):
    e = move_session(BLOCK, week=1, day="tue", to_day="fri")
    assert "  overrides:\n    tue: null\n    fri: A.zwo\n" in e.text
    assert "start: 2026-11-30  # a Monday" in e.text
    assert not e.reformatted
    load(e.text, workouts)


@pytest.mark.parametrize(
    "kw, msg",
    [
        ({"week": 1, "day": "mon", "to_day": "fri"}, "week 1 mon has no session"),
        ({"week": 3, "day": "sat", "to_day": "fri"}, "week 3 sat has no session"),  # null override
        ({"week": 1, "day": "tue", "to_day": "tue"}, "already on that day"),
        ({"week": 9, "day": "tue", "to_day": "fri"}, "week 9 is outside 1..3"),
        ({"week": 1, "day": "tue", "to_day": "fri", "to_week": 4}, "week 4 is outside"),
        ({"week": 1, "day": "tue", "to_day": "funday"}, "not a day"),
    ],
)
def test_move_errors(kw, msg):
    with pytest.raises(EditError, match=msg):
        move_session(FLOW, **kw)


def test_full_day_names_are_accepted():
    e = move_session(FLOW, week=1, day="Tuesday", to_day="THURSDAY")
    assert "thu: A.zwo" in e.text


def test_shift_remaining_inserts_rest_weeks_and_renumbers(workouts):
    e = shift_remaining(FLOW, weeks=2, from_week=2)
    assert "  rest: {}\n" in e.text
    weeks = [ln.strip() for ln in e.text.splitlines() if ln.lstrip().startswith("- {")]
    assert weeks == [
        "- {template: build}                 # Week 1",
        "- {template: rest}                  # Week 2 (rest, added by shift_plan)",
        "- {template: rest}                  # Week 3 (rest, added by shift_plan)",
        "- {template: build}                 # Week 4",
        "- {template: build, overrides: {sat: null}}  # Week 5",
    ]
    plan = load(e.text, workouts)
    assert plan.weeks == 5
    assert {x.week for x in plan.events} == {1, 4, 5}
    assert e.summary[:2] == [
        "inserted weeks 2-3 as rest (template 'rest')",
        "old weeks 2-3 are now 4-5",
    ]


def test_shift_reuses_an_existing_empty_template():
    src = FLOW.replace("templates:\n", "templates:\n  off: {}\n")
    e = shift_remaining(src, weeks=1, from_week=1)
    assert "rest: {}" not in e.text
    assert "{template: off}" in e.text
    assert not any("added an empty template" in s for s in e.summary)


def test_shift_block_style_without_week_comments(workouts):
    e = shift_remaining(BLOCK, weeks=1, from_week=2)
    assert "- template: build\n- template: rest\n- template: build\n" in e.text
    assert "Week" not in e.text
    assert load(e.text, workouts).weeks == 3


def test_shift_start():
    e = shift_start(FLOW, weeks=2)
    assert changed_lines(FLOW, e.text) == ["-start: 2026-11-30", "+start: 2026-12-14"]
    assert yaml.safe_load(e.text)["start"] == dt.date(2026, 12, 14)


def test_shift_from_week_out_of_range():
    with pytest.raises(EditError, match=r"outside 1\.\.3"):
        shift_remaining(FLOW, weeks=1, from_week=4)


def test_not_a_plan():
    with pytest.raises(EditError, match="no `weeks` list"):
        move_session("id: x\n", week=1, day="tue", to_day="wed")
