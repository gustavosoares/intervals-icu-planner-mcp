import datetime as dt

import pytest
import yaml

from zwo_plan_pusher.plan import PlanError, build_plan, load_plan, parse_zwo


def base(**kw):
    data = {
        "id": "test",
        "start": dt.date(2026, 11, 30),
        "weeks": 3,
        "template": {"tue": "A.zwo", "sat": {"note": "Group ride"}},
    }
    data.update(kw)
    return data


def by_key(plan):
    return {(e.week, e.day): e for e in plan.events}


def test_template_repeats_every_week(workouts):
    plan = build_plan(base(), str(workouts))
    assert [(e.week, e.day) for e in plan.events] == [
        (1, "tue"), (1, "sat"), (2, "tue"), (2, "sat"), (3, "tue"), (3, "sat")]
    assert plan.events[0].date == dt.date(2026, 12, 1)
    assert plan.events[-1].date == dt.date(2026, 12, 19)
    assert plan.end == dt.date(2026, 12, 20)


def test_workout_name_comes_from_zwo(workouts):
    ev = build_plan(base(), str(workouts)).events[0]
    assert ev.category == "WORKOUT"
    assert ev.name == "Workout A"
    assert ev.workout.filename == "A.zwo"
    assert "<workout_file>" in ev.workout.contents


def test_note_event(workouts):
    ev = by_key(build_plan(base(), str(workouts)))[(1, "sat")]
    assert ev.category == "NOTE"
    assert ev.name == "Group ride"
    assert ev.workout is None


def test_overrides_merge_and_null_removes(workouts):
    data = base(overrides={2: {"tue": "B.zwo", "thu": {"workout": "C.zwo", "name": "Custom"}},
                           3: {"sat": None}})
    ev = by_key(build_plan(data, str(workouts)))
    assert ev[(1, "tue")].workout.filename == "A.zwo"
    assert ev[(2, "tue")].workout.filename == "B.zwo"
    assert ev[(2, "thu")].name == "Custom"
    assert (2, "sat") in ev
    assert (3, "sat") not in ev


def test_recovery_weeks_use_recovery_template(workouts):
    data = base(recovery={"weeks": [2], "template": {"wed": "C.zwo"}})
    ev = by_key(build_plan(data, str(workouts)))
    assert [k for k in ev if k[0] == 2] == [(2, "wed")]
    assert (1, "tue") in ev and (3, "tue") in ev


def test_overrides_apply_on_top_of_recovery(workouts):
    data = base(recovery={"weeks": [2], "template": {"wed": "C.zwo"}},
                overrides={2: {"sun": {"note": "Rest"}}})
    ev = by_key(build_plan(data, str(workouts)))
    assert sorted(k for k in ev if k[0] == 2) == [(2, "sun"), (2, "wed")]


def test_uids_are_stable_and_unique(workouts):
    a = build_plan(base(), str(workouts))
    b = build_plan(base(), str(workouts), start="2027-01-04")
    assert [e.uid for e in a.events] == [e.uid for e in b.events]
    assert a.events[0].uid == "test-w01-tue"
    assert len({e.uid for e in a.events}) == len(a.events)
    assert b.events[0].date == dt.date(2027, 1, 5)


def test_start_accepts_string(workouts):
    plan = build_plan(base(start="2026-11-30"), str(workouts))
    assert plan.start == dt.date(2026, 11, 30)


def test_start_must_be_monday(workouts):
    with pytest.raises(PlanError) as e:
        build_plan(base(start="2026-12-01"), str(workouts))
    assert "Tuesday, must be a Monday" in str(e.value)


def test_start_override_must_be_monday(workouts):
    with pytest.raises(PlanError, match="must be a Monday"):
        build_plan(base(), str(workouts), start=dt.date(2026, 12, 6))


def test_bad_start_date(workouts):
    with pytest.raises(PlanError, match="not a YYYY-MM-DD"):
        build_plan(base(start="next monday"), str(workouts))


def test_missing_zwo_reported_once(workouts):
    with pytest.raises(PlanError) as e:
        build_plan(base(template={"tue": "Missing.zwo"}), str(workouts))
    assert len(e.value.errors) == 1
    assert "Missing.zwo: cannot read" in e.value.errors[0]


def test_malformed_zwo(workouts):
    (workouts / "workouts" / "Bad.zwo").write_text("<workout_file><workout>", encoding="utf-8")
    with pytest.raises(PlanError, match="Bad.zwo: invalid XML"):
        build_plan(base(template={"tue": "Bad.zwo"}), str(workouts))


def test_zwo_wrong_root_or_empty(tmp_path):
    p = tmp_path / "x.zwo"
    p.write_text("<foo/>", encoding="utf-8")
    with pytest.raises(ValueError, match="expected <workout_file>"):
        parse_zwo(str(p))
    p.write_text("<workout_file><workout/></workout_file>", encoding="utf-8")
    with pytest.raises(ValueError, match="empty <workout>"):
        parse_zwo(str(p))


def test_collects_all_errors(workouts):
    data = base(start="2026-12-02", weeks=3, template={"tue": "Nope.zwo", "funday": "A.zwo"},
                overrides={9: {"tue": "A.zwo"}}, recovery={"weeks": [0], "template": {}})
    with pytest.raises(PlanError) as e:
        build_plan(data, str(workouts))
    msg = str(e.value)
    for part in ("must be a Monday", "unknown day 'funday'", "overrides: week 9 is outside 1..3",
                 "recovery.weeks: week 0 is outside", "Nope.zwo"):
        assert part in msg


def test_required_fields(workouts):
    with pytest.raises(PlanError) as e:
        build_plan({"template": {"tue": "A.zwo"}}, str(workouts))
    msg = str(e.value)
    assert "id: required" in msg and "start: required" in msg and "weeks:" in msg


def test_entry_needs_workout_or_note(workouts):
    with pytest.raises(PlanError, match="exactly one of 'workout' or 'note'"):
        build_plan(base(template={"tue": {"name": "x"}}), str(workouts))


def test_load_plan_from_file(workouts):
    path = workouts / "plan.yaml"
    path.write_text(yaml.safe_dump({**base(), "start": "2026-11-30"}), encoding="utf-8")
    plan = load_plan(str(path))
    assert len(plan.events) == 6


def test_load_plan_invalid_yaml(tmp_path):
    p = tmp_path / "plan.yaml"
    p.write_text("weeks: [1, 2\n", encoding="utf-8")
    with pytest.raises(PlanError, match="invalid YAML"):
        load_plan(str(p))
