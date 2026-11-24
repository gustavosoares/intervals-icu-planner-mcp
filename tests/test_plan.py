import datetime as dt
import json

import pytest

from intervals_icu_planner_mcp.plan import (
    PlanError,
    build_plan,
    load_plan,
    make_uid,
    owns_uid,
    plan_json_schema,
)

from .conftest import ROOT, plan_data


def by_key(plan):
    return {(e.week, e.day): e for e in plan.events}


def plan_errors(workouts, **kw) -> list[str]:
    with pytest.raises(PlanError) as e:
        build_plan(plan_data(**kw), str(workouts))
    return e.value.errors


def test_weeks_follow_their_templates(make_plan):
    plan = make_plan()
    assert [(e.week, e.day) for e in plan.events] == [
        (1, "tue"),
        (1, "sat"),
        (2, "tue"),
        (2, "sat"),
        (3, "wed"),
    ]
    assert plan.events[0].date == dt.date(2026, 12, 1)
    assert plan.events[-1].date == dt.date(2026, 12, 16)
    assert plan.end == dt.date(2026, 12, 20)
    assert plan.recovery_weeks == {3}
    assert by_key(plan)[(3, "wed")].recovery


def test_uids_are_stable_and_prefixed(make_plan):
    uids = [e.uid for e in make_plan().events]
    assert uids == [
        "planner-test-w01-tue",
        "planner-test-w01-sat",
        "planner-test-w02-tue",
        "planner-test-w02-sat",
        "planner-test-w03-wed",
    ]
    # the date isn't part of the uid, so shifting the plan updates in place
    shifted = make_plan(start="2027-01-04")
    assert [e.uid for e in shifted.events] == uids


def test_workout_and_note_events(make_plan):
    ev = by_key(make_plan())
    w, n = ev[(1, "tue")], ev[(1, "sat")]
    assert (w.category, w.name, w.workout.filename) == ("WORKOUT", "Workout A", "A.zwo")
    assert w.workout.total_seconds == 600
    assert (n.category, n.name, n.description, n.workout) == (
        "NOTE",
        "Group ride",
        "or indoors",
        None,
    )


def test_overrides_merge_and_null_removes(make_plan):
    weeks = [
        {"template": "build"},
        {
            "template": "build",
            "overrides": {"tue": "B.zwo", "thu": {"workout": "C.zwo", "name": "Custom"}},
        },
        {"template": "build", "overrides": {"sat": None}},
    ]
    ev = by_key(make_plan(weeks=weeks))
    assert ev[(1, "tue")].workout.filename == "A.zwo"
    assert ev[(2, "tue")].workout.filename == "B.zwo"
    assert ev[(2, "thu")].name == "Custom"
    assert (2, "sat") in ev
    assert (3, "sat") not in ev
    assert (3, "tue") in ev


def test_start_override_param(workouts):
    plan = build_plan(plan_data(), str(workouts), start="2027-01-04")
    assert plan.start == dt.date(2027, 1, 4)
    assert plan.events[0].date == dt.date(2027, 1, 5)


def test_start_must_be_monday(workouts):
    assert plan_errors(workouts, start="2026-12-01") == [
        "start: 2026-12-01 is a Tuesday, must be a Monday"
    ]
    with pytest.raises(PlanError, match="Wednesday"):
        build_plan(plan_data(), str(workouts), start="2026-12-02")


@pytest.mark.parametrize(
    "kw, expected",
    [
        ({"id": "Bad Id!"}, "id: String should match pattern"),
        ({"start": "soon"}, "start: Input should be a valid date"),
        ({"weeks": []}, "weeks: List should have at least 1 item"),
        ({"templates": {}}, "templates: Dictionary should have at least 1 item"),
        ({"surprise": 1}, "surprise: Extra inputs are not permitted"),
        ({"templates": {"build": {"funday": "A.zwo"}}}, "templates.build.funday: Extra inputs"),
        (
            {"templates": {"build": {"tue": "A.txt"}}},
            "templates.build.tue: String should match pattern",
        ),
        (
            {"templates": {"build": {"tue": {"workout": "A.zwo", "note": "x"}}}},
            "templates.build.tue: must be a .zwo file name",
        ),
        ({"templates": {"build": {"tue": 7}}}, "templates.build.tue: must be a .zwo file name"),
        (
            {
                "weeks": [
                    {"template": "build"},
                    {"template": "build", "overrides": {"tue": {"workout": "A.zwo", "x": 1}}},
                ]
            },
            "weeks[2].overrides.tue.x: Extra inputs",
        ),
    ],
)
def test_schema_errors(workouts, kw, expected):
    errs = plan_errors(workouts, **kw)
    assert any(e.startswith(expected) for e in errs), errs


def test_unknown_template(workouts):
    errs = plan_errors(workouts, weeks=[{"template": "build"}, {"template": "taper"}])
    assert errs == ["weeks[2].template: unknown template 'taper' (have: build, easy)"]


def test_missing_and_invalid_workouts_reported_once_each(workouts):
    (workouts / "workouts" / "Bad.zwo").write_text(
        '<workout_file><workout><SteadyState Duration="0" Power="0.5"/></workout></workout_file>'
    )
    errs = plan_errors(
        workouts,
        templates={"build": {"tue": "Nope.zwo", "thu": "Bad.zwo"}},
        weeks=[{"template": "build"}] * 4,
    )
    assert errs == [
        "Nope.zwo: file not found",
        "Bad.zwo: segment 1 <SteadyState>: Duration must be > 0, got 0",
    ]


def test_workout_paths_cannot_escape_workouts_dir(workouts):
    errs = plan_errors(
        workouts, templates={"build": {"tue": "../secret.zwo"}}, weeks=[{"template": "build"}]
    )
    assert errs == ["../secret.zwo: must be a file name inside workouts_dir, not a path"]


def test_all_errors_reported_together(workouts):
    errs = plan_errors(
        workouts,
        start="2026-12-01",
        weeks=[{"template": "nope"}, {"template": "build"}],
        templates={"build": {"tue": "Missing.zwo"}},
    )
    assert len(errs) == 3


def test_empty_plan_is_an_error(workouts):
    assert plan_errors(workouts, templates={"build": {}}, weeks=[{"template": "build"}]) == [
        "plan produces no events (are the templates empty?)"
    ]


def test_load_plan_errors(tmp_path):
    with pytest.raises(PlanError, match="cannot read"):
        load_plan(str(tmp_path / "missing.yaml"))
    bad = tmp_path / "bad.yaml"
    bad.write_text("id: [unclosed")
    with pytest.raises(PlanError, match="invalid YAML"):
        load_plan(str(bad))
    bad.write_text("- just a list")
    with pytest.raises(PlanError, match="top level must be a mapping"):
        load_plan(str(bad))


def test_load_plan_resolves_workouts_relative_to_the_file(write_plan):
    plan = load_plan(write_plan())
    assert len(plan.events) == 5


def test_owns_uid_is_exact():
    assert owns_uid("winter", make_uid("winter", 1, "tue"))
    assert owns_uid("winter", "planner-winter-w12-sun")
    # another plan whose id starts the same way
    assert not owns_uid("winter", "planner-winter-base-w01-tue")
    assert not owns_uid("winter-base", "planner-winter-w01-tue")
    for foreign in [
        "",
        None,
        "winter-w01-tue",
        "planner-winter-w1-tue",
        "planner-winter-w01-tuesday",
        "planner-winter-w01-tue-x",
        "xplanner-winter-w01-tue",
        "planner-WINTER-w01-tue",
    ]:
        assert not owns_uid("winter", foreign), foreign
    # an id that isn't a valid plan id owns nothing (no regex tricks)
    assert not owns_uid(".*", "planner-anything-w01-tue")
    assert not owns_uid("", "planner--w01-tue")


def test_committed_schema_is_up_to_date():
    committed = json.loads((ROOT / "schemas" / "plan.schema.json").read_text())
    assert committed == plan_json_schema(), (
        "schemas/plan.schema.json is stale: "
        "run `intervals-icu-planner schema > schemas/plan.schema.json`"
    )
