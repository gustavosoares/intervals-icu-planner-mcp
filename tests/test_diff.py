from intervals_icu_planner_mcp.diff import compute_diff, render_diff

from .conftest import cal_event


def existing_for(plan):
    """The calendar exactly as a previous push of ``plan`` would have left it."""
    out = []
    for i, e in enumerate(plan.events, start=1):
        extra = (
            {"moving_time": e.workout.total_seconds}
            if e.workout
            else {"description": e.description}
        )
        out.append(
            cal_event(e.uid, e.date.isoformat(), id=i, name=e.name, category=e.category, **extra)
        )
    return out


def test_empty_calendar_everything_new(make_plan):
    plan = make_plan()
    diff = compute_diff(plan, [])
    assert [c.status for c in diff.changes] == ["new"] * 5
    assert diff.to_send == plan.events
    assert not diff.offline


def test_offline(make_plan):
    diff = compute_diff(make_plan(), None)
    assert diff.offline
    assert diff.count("new") == 5
    assert "Calendar not checked" in render_diff(diff)


def test_identical_calendar_everything_unchanged(make_plan):
    plan = make_plan()
    diff = compute_diff(plan, existing_for(plan))
    assert diff.count("unchanged") == 5
    assert diff.to_send == []


def test_updated_fields_are_listed(make_plan):
    plan = make_plan()
    cal = existing_for(plan)
    cal[0]["name"] = "Old name"
    cal[1]["description"] = "old text"
    cal[2]["start_date_local"] = "2026-12-09T00:00:00"
    cal[4]["moving_time"] = 1200
    diff = compute_diff(plan, cal)
    by_uid = {c.event.uid: c for c in diff.changes}
    assert by_uid["planner-test-w01-tue"].fields == ("name 'Old name' -> 'Workout A'",)
    assert by_uid["planner-test-w01-sat"].fields == ("description",)
    assert by_uid["planner-test-w02-tue"].fields == ("date 2026-12-09 -> 2026-12-08",)
    assert by_uid["planner-test-w03-wed"].fields == ("duration 20:00 -> 10:00",)
    assert by_uid["planner-test-w01-tue"].existing_id == 1
    assert [e.uid for e in diff.to_send] == [
        "planner-test-w01-tue",
        "planner-test-w01-sat",
        "planner-test-w02-tue",
        "planner-test-w03-wed",
    ]


def test_workout_description_rewritten_by_intervals_is_not_a_change(make_plan):
    plan = make_plan()
    cal = existing_for(plan)
    cal[0]["description"] = "- 10m 65%"  # intervals.icu's own rendering of the .zwo
    assert compute_diff(plan, cal).changes[0].status == "unchanged"


def test_stale_and_foreign_events(make_plan):
    plan = make_plan()
    cal = [
        *existing_for(plan),
        cal_event("planner-test-w04-tue", "2026-12-22", id=90, name="Dropped week"),
        cal_event("planner-test-base-w01-tue", "2026-12-01", id=91, name="Other plan"),
        cal_event("my-own-thing", "2026-12-01", id=92, name="Mine"),
        {"id": 93, "start_date_local": "2026-12-02T00:00:00", "name": "No uid", "category": "NOTE"},
    ]
    diff = compute_diff(plan, cal)
    assert [e["id"] for e in diff.stale] == [90]
    assert diff.count("unchanged") == 5
    out = render_diff(diff)
    assert "! 2026-12-22" in out
    for foreign in ("Other plan", "Mine", "No uid"):
        assert foreign not in out


def test_matches_on_external_id_not_the_server_uid(make_plan):
    """Regression: intervals.icu replaces `uid` with its own UUID and keeps our id
    in `external_id`. Reading `uid` first made a pushed plan invisible to itself."""
    plan = make_plan()
    cal = existing_for(plan)
    assert all(e["uid"] != e["external_id"] for e in cal)
    assert compute_diff(plan, cal).count("unchanged") == 5


def test_falls_back_to_uid_when_external_id_missing(make_plan):
    plan = make_plan()
    cal = existing_for(plan)
    for e in cal:
        e["uid"] = e.pop("external_id")
    assert compute_diff(plan, cal).count("unchanged") == 5


def test_render_snapshot(make_plan):
    plan = make_plan()
    cal = existing_for(plan)[:3]
    cal[2]["name"] = "Renamed"
    cal.append(cal_event("planner-test-w09-mon", "2027-01-25", id=99, name="Gone"))
    assert (
        render_diff(compute_diff(plan, cal), apply_hint="--apply")
        == """\
Test plan (test): 3 weeks, 2026-11-30 -> 2026-12-20

Week 1, 2026-11-30
  = 2026-12-01 Tue  WORKOUT  A.zwo
  = 2026-12-05 Sat  NOTE     Group ride

Week 2, 2026-12-07
  ~ 2026-12-08 Tue  WORKOUT  A.zwo  [name 'Renamed' -> 'Workout A']
  + 2026-12-12 Sat  NOTE     Group ride

Week 3, 2026-12-14  (recovery)
  + 2026-12-16 Wed  WORKOUT  C.zwo

Stale: on the calendar with this plan's uid but no longer in the plan.
Pushing keeps them; push with prune=true to delete them.
  ! 2027-01-25  WORKOUT  Gone  planner-test-w09-mon

2 new, 1 updated, 2 unchanged, 1 stale.
Dry run: nothing was written. Run again with --apply to apply."""
    )
