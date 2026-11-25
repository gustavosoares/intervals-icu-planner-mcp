import datetime as dt
import json
from dataclasses import dataclass

import httpx
import pytest
import respx

from intervals_icu_planner_mcp import edit as edit_mod
from intervals_icu_planner_mcp import planner
from intervals_icu_planner_mcp.client import ApiError
from intervals_icu_planner_mcp.plan import PlanError, load_plan
from intervals_icu_planner_mcp.planner import PlannerError, event_payload, form_percent

from .conftest import API, cal_event


@dataclass
class Api:
    router: respx.MockRouter
    events: respx.Route
    upsert: respx.Route
    bulk_delete: respx.Route

    @property
    def calls(self) -> respx.models.CallList:
        return self.router.calls


@pytest.fixture
def api():
    """Mocked intervals.icu. Unmatched requests fail the test."""
    with respx.mock(assert_all_called=False) as router:
        yield Api(
            router,
            events=router.get(f"{API}/events").mock(return_value=httpx.Response(200, json=[])),
            upsert=router.post(f"{API}/events/bulk").mock(
                side_effect=lambda req: httpx.Response(200, json=json.loads(req.content))
            ),
            bulk_delete=router.put(f"{API}/events/bulk-delete").mock(
                side_effect=lambda req: httpx.Response(
                    200, json={"eventsDeleted": len(json.loads(req.content))}
                )
            ),
        )


TODAY = lambda: dt.date(2026, 11, 23)  # noqa: E731


def writes(api: Api) -> int:
    return api.upsert.call_count + api.bulk_delete.call_count


# ---------------------------------------------------------------------- push


def test_push_dry_run_never_writes(api, client, write_plan):
    out = planner.push(write_plan(), client=client, today=TODAY)
    assert writes(api) == 0
    assert api.events.call_count == 1
    params = dict(api.events.calls.last.request.url.params)
    # a wide window, not just the plan's dates, so leftovers of older versions are found
    assert params == {"oldest": "2025-11-23", "newest": "2028-11-22"}
    assert "5 new, 0 updated, 0 unchanged, 0 stale." in out
    assert "Dry run: nothing was written" in out


def test_push_dry_run_is_the_default_even_with_changes(api, client, write_plan):
    api.events.return_value = httpx.Response(
        200, json=[cal_event("planner-test-w01-tue", "2026-12-01", id=1, name="Old")]
    )
    planner.push(write_plan(), client=client)
    assert writes(api) == 0


def test_push_offline_dry_run_needs_no_client(write_plan):
    out = planner.push(write_plan(), client=None)
    assert "Calendar not checked" in out


def test_push_apply_requires_a_key(write_plan):
    with pytest.raises(PlannerError, match=r"not connected to intervals\.icu"):
        planner.push(write_plan(), client=None, dry_run=False)


def test_invalid_plan_fails_before_any_request(api, client, write_plan):
    path = write_plan(start="2026-12-01")
    with pytest.raises(PlanError):
        planner.push(path, client=client, dry_run=False)
    assert len(api.calls) == 0


def test_push_apply_sends_only_new_and_updated(api, client, write_plan, make_plan):
    plan = make_plan()
    cal = [
        cal_event(
            e.uid,
            e.date.isoformat(),
            id=i,
            name=e.name,
            category=e.category,
            moving_time=e.workout.total_seconds if e.workout else None,
            description=e.description,
        )
        for i, e in enumerate(plan.events[:3], start=1)
    ]
    cal[0]["name"] = "Old name"
    cal.append(cal_event("someone-else", "2026-12-01", id=50))
    api.events.return_value = httpx.Response(200, json=cal)

    out = planner.push(write_plan(), client=client, dry_run=False)
    sent = json.loads(api.upsert.calls.last.request.content)
    assert [e["external_id"] for e in sent] == [
        "planner-test-w01-tue",
        "planner-test-w02-sat",
        "planner-test-w03-wed",
    ]
    assert api.bulk_delete.call_count == 0
    assert "Applied: sent 3 events" in out


def test_push_apply_with_nothing_to_do_sends_nothing(api, client, write_plan, make_plan):
    plan = make_plan()
    api.events.return_value = httpx.Response(
        200,
        json=[
            cal_event(
                e.uid,
                e.date.isoformat(),
                id=i,
                name=e.name,
                category=e.category,
                moving_time=e.workout.total_seconds if e.workout else None,
                description=e.description,
            )
            for i, e in enumerate(plan.events, start=1)
        ],
    )
    planner.push(write_plan(), client=client, dry_run=False)
    assert writes(api) == 0


def test_workout_payload(make_plan):
    ev = make_plan(type="VirtualRide").events[0]
    p = event_payload(ev, "VirtualRide")
    assert set(p) == {
        "category",
        "type",
        "start_date_local",
        "name",
        "filename",
        "file_contents",
        "external_id",
    }
    assert p["start_date_local"] == "2026-12-01T00:00:00"
    assert p["file_contents"] == ev.workout.contents  # sent as-is
    assert p["external_id"] == "planner-test-w01-tue"
    assert "uid" not in p  # intervals.icu assigns its own


def test_note_payload(make_plan):
    assert event_payload(make_plan().events[1]) == {
        "category": "NOTE",
        "start_date_local": "2026-12-05T00:00:00",
        "end_date_local": "2026-12-05T00:00:00",
        "name": "Group ride",
        "description": "or indoors",
        "external_id": "planner-test-w01-sat",
    }


# --------------------------------------------------------------------- prune


def calendar_for(plan, extra=()):
    """The calendar as a previous push of ``plan`` left it, plus ``extra`` events."""
    cal = [
        cal_event(
            e.uid,
            e.date.isoformat(),
            id=i,
            name=e.name,
            category=e.category,
            moving_time=e.workout.total_seconds if e.workout else None,
            description=e.description,
        )
        for i, e in enumerate(plan.events, start=1)
    ]
    return [*cal, *extra]


STALE_FUTURE = cal_event("planner-test-w04-tue", "2026-12-22", id=90, name="Dropped week")
STALE_PAST = cal_event("planner-test-w05-tue", "2026-11-10", id=91, name="Done already")
FOREIGN = [
    cal_event("planner-test-base-w01-tue", "2026-12-01", id=92, name="Other plan"),
    {
        "id": 93,
        "uid": "0b9e-server-uuid",
        "start_date_local": "2026-12-02T00:00:00",
        "name": "My race",
        "category": "RACE_A",
    },
]


@pytest.fixture
def stale_calendar(api, make_plan):
    api.events.return_value = httpx.Response(
        200, json=calendar_for(make_plan(), [STALE_FUTURE, STALE_PAST, *FOREIGN])
    )


def test_prune_dry_run_shows_what_would_go_and_never_writes(
    api, client, write_plan, stale_calendar
):
    out = planner.push(write_plan(), client=client, prune=True, today=TODAY)
    assert writes(api) == 0
    assert "  - 2026-12-22  WORKOUT  Dropped week  planner-test-w04-tue" in out
    assert "  ! 2026-11-10  WORKOUT  Done already  planner-test-w05-tue  (past, kept)" in out
    assert "0 new, 0 updated, 5 unchanged, 2 stale (1 to delete)." in out
    for foreign in ("Other plan", "My race"):
        assert foreign not in out


def test_push_without_prune_never_deletes(api, client, write_plan, stale_calendar):
    out = planner.push(write_plan(), client=client, dry_run=False, today=TODAY)
    assert api.bulk_delete.call_count == 0
    assert "push with prune=true to delete them" in out


def test_prune_apply_deletes_only_future_stale_events(api, client, write_plan, stale_calendar):
    out = planner.push(write_plan(), client=client, dry_run=False, prune=True, today=TODAY)
    body = json.loads(api.bulk_delete.calls.last.request.content)
    assert body == [{"id": 90}]  # not the past one, not the other plan, not the race
    assert "deleted 1 stale event." in out


def test_prune_upserts_before_deleting(api, client, write_plan, make_plan):
    cal = calendar_for(make_plan(), [STALE_FUTURE])
    cal[0]["name"] = "Old name"  # so there is something to upsert
    api.events.return_value = httpx.Response(200, json=cal)
    planner.push(write_plan(), client=client, dry_run=False, prune=True, today=TODAY)
    assert [c.request.method for c in api.calls] == ["GET", "POST", "PUT"]


def test_failed_upsert_deletes_nothing(api, client, write_plan):
    api.events.return_value = httpx.Response(200, json=[STALE_FUTURE])
    api.upsert.side_effect = None
    api.upsert.return_value = httpx.Response(500, text="boom")
    with pytest.raises(ApiError):
        planner.push(write_plan(), client=client, dry_run=False, prune=True, today=TODAY)
    assert api.bulk_delete.call_count == 0


def test_prune_with_nothing_stale_sends_no_delete(api, client, write_plan, make_plan):
    api.events.return_value = httpx.Response(200, json=calendar_for(make_plan()))
    out = planner.push(write_plan(), client=client, dry_run=False, prune=True, today=TODAY)
    assert writes(api) == 0
    assert "deleted 0 stale events." in out


def test_shifted_plan_finds_events_outside_its_new_dates(api, client, write_plan, make_plan):
    """Moving the start shows the old events as moved, not as new."""
    api.events.return_value = httpx.Response(200, json=calendar_for(make_plan()))
    out = planner.push(write_plan(), client=client, start="2027-06-07", today=TODAY)
    assert "0 new, 5 updated, 0 unchanged, 0 stale." in out
    assert "[date 2026-12-01 -> 2027-06-08]" in out


def test_search_window_covers_a_far_future_plan(make_plan):
    plan = make_plan(start="2029-01-01")
    assert planner.search_window(plan, TODAY()) == (dt.date(2025, 11, 23), plan.end)


# -------------------------------------------------------------------- delete

CALENDAR = [
    cal_event("planner-winter-w01-tue", "2026-12-01", id=1),
    cal_event("planner-winter-w02-sat", "2026-12-12", id=2, category="NOTE"),
    cal_event("planner-winter-base-w01-tue", "2026-12-01", id=3),  # a different plan
    cal_event("winter-w01-tue", "2026-12-01", id=4),  # old 0.0.x uid
    cal_event("planner-winter-w01-tue-copy", "2026-12-01", id=5),
    {"id": 6, "start_date_local": "2026-12-03T00:00:00", "name": "Race", "category": "RACE_A"},
    {"id": 7, "external_id": "planner-winter-w03-wed", "start_date_local": "2026-12-16T00:00:00"},
    {"uid": "planner-winter-w04-wed", "start_date_local": "2026-12-23T00:00:00"},  # no id
]


def test_delete_dry_run_lists_and_never_writes(api, client):
    api.events.return_value = httpx.Response(200, json=CALENDAR)
    out = planner.delete("winter", client=client, today=TODAY)
    assert writes(api) == 0
    assert "3 event(s) from plan 'winter'" in out
    assert "planner-winter-base" not in out
    params = dict(api.events.calls.last.request.url.params)
    assert params == {"oldest": "2025-11-23", "newest": "2028-11-22"}


def test_delete_never_touches_foreign_uids(api, client):
    api.events.return_value = httpx.Response(200, json=CALENDAR)
    out = planner.delete("winter", client=client, dry_run=False, today=TODAY)
    body = json.loads(api.bulk_delete.calls.last.request.content)
    assert sorted(d["id"] for d in body) == [1, 2, 7]
    assert api.upsert.call_count == 0
    assert "Deleted 3 event(s)" in out


def test_delete_other_plan_with_shared_prefix(api, client):
    api.events.return_value = httpx.Response(200, json=CALENDAR)
    planner.delete("winter-base", client=client, dry_run=False, today=TODAY)
    body = json.loads(api.bulk_delete.calls.last.request.content)
    assert body == [{"id": 3}]


def test_delete_nothing_found(api, client):
    api.events.return_value = httpx.Response(200, json=CALENDAR)
    out = planner.delete("summer", client=client, dry_run=False, today=TODAY)
    assert "Nothing to delete" in out
    assert writes(api) == 0


@pytest.mark.parametrize("bad", ["", "*", "-lead", "Winter", "a b", "../x", "x" * 41])
def test_delete_rejects_invalid_plan_ids(api, client, bad):
    with pytest.raises(PlannerError):
        planner.delete(bad, client=client, dry_run=False, today=TODAY)
    assert len(api.calls) == 0


def test_second_guard_refuses_foreign_events(client):
    with pytest.raises(PlannerError, match="refusing to delete 1"):
        planner._delete_owned(
            client, "winter", [cal_event("planner-other-w01-tue", "2026-12-01", id=9)]
        )


def test_delete_custom_range(api, client):
    planner.delete("winter", client=client, oldest="2026-01-01", newest="2026-02-01")
    assert dict(api.events.calls.last.request.url.params) == {
        "oldest": "2026-01-01",
        "newest": "2026-02-01",
    }


def test_delete_requires_a_key():
    with pytest.raises(PlannerError, match="not connected"):
        planner.delete("winter", client=None)


# ------------------------------------------------------------- planned/dates


def test_planned_filters_by_plan(api, client):
    api.events.return_value = httpx.Response(200, json=CALENDAR)
    out = planner.planned("2026-12-01", "2026-12-31", client=client, plan_id="winter")
    assert "4 events from plan 'winter'" in out  # listing includes the one without an id
    assert "planner-winter-base" not in out
    everything = planner.planned("2026-12-01", "2026-12-31", client=client)
    assert "8 events between" in everything


@pytest.mark.parametrize(
    "oldest, newest, msg",
    [
        ("2026-13-01", "2026-12-01", "not a YYYY-MM-DD"),
        ("2026-12-02", "2026-12-01", "after newest"),
        ("2020-01-01", "2026-01-01", "longer than 5 years"),
    ],
)
def test_date_validation(client, oldest, newest, msg):
    with pytest.raises(PlannerError, match=msg):
        planner.planned(oldest, newest, client=client)


# ------------------------------------------------------------------- fitness


def test_form_percent():
    assert form_percent(50, 60) == pytest.approx(-20)
    assert form_percent(0, 10) is None


def test_fitness_table(client):
    with respx.mock:
        respx.get(f"{API}/wellness").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"id": "2026-12-02", "ctl": 50.0, "atl": 60.0},
                    {"id": "2026-12-01", "ctl": 48.25, "atl": 40.0},
                    {"id": "2026-12-03", "ctl": 0, "atl": 0},
                    {"id": "2026-12-04"},
                ],
            )
        )
        out = planner.fitness("2026-12-01", "2026-12-04", client=client)
    lines = out.splitlines()
    assert lines[2].split() == ["date", "CTL", "ATL", "Form", "Form", "%"]
    assert lines[4].split() == ["2026-12-01", "48.2", "40.0", "+8.2", "+17%"]
    assert lines[5].split() == ["2026-12-02", "50.0", "60.0", "-10.0", "-20%"]
    assert lines[6].split() == ["2026-12-03", "0.0", "0.0", "+0.0", "-"]
    assert lines[7].split() == ["2026-12-04", "-", "-", "-", "-"]


# ---------------------------------------------------------------- activities


def test_activities_table_and_strava_stubs(client):
    with respx.mock:
        respx.get(f"{API}/activities").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "id": "i2",
                        "start_date_local": "2026-12-03T07:00:00",
                        "type": "VirtualRide",
                        "name": "Threshold 3x8",
                        "moving_time": 3600,
                        "distance": 31500.0,
                        "icu_training_load": 72,
                        "icu_average_watts": 201,
                        "icu_weighted_avg_watts": 225,
                        "icu_intensity": 86.5,
                        "average_heartrate": 148,
                    },
                    {
                        "id": "s1",
                        "start_date_local": "2026-12-02T09:00:00",
                        "source": "STRAVA",
                        "_note": "STRAVA activities are not available via the API",
                    },
                    {
                        "id": "i1",
                        "start_date_local": "2026-12-01T18:00:00",
                        "type": "Ride",
                        "name": "Spin",
                        "moving_time": 1800,
                    },
                ],
            )
        )
        out = planner.activities("2026-12-01", "2026-12-03", client=client)
    lines = out.splitlines()
    assert lines[0] == "3 activities 2026-12-01 -> 2026-12-03: 1:30 moving, load 72."
    assert lines[4].split()[:3] == ["2026-12-01", "Ride", "Spin"]
    assert lines[4].split()[3:] == ["0:30", "-", "-", "-", "-", "-", "-"]
    assert "(Strava import: details not available via API)" in lines[5]
    assert lines[6].split()[-7:] == ["1:00", "31.5", "72", "201", "225", "0.86", "148"]
    assert "1 activity came from Strava" in out


def test_no_activities(client):
    with respx.mock:
        respx.get(f"{API}/activities").mock(return_value=httpx.Response(200, json=[]))
        assert planner.activities("2026-12-01", "2026-12-03", client=client) == (
            "No activities between 2026-12-01 and 2026-12-03."
        )


# ------------------------------------------------------------ move and shift

D = dt.date


def at(day):
    return lambda: day


def read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_move_dry_run_shows_both_diffs_and_writes_nothing(api, client, write_plan, make_plan):
    path = write_plan()
    before = read(path)
    api.events.return_value = httpx.Response(200, json=calendar_for(make_plan()))
    out = planner.move(path, 1, "tue", "thu", client=client, today=TODAY)
    assert read(path) == before
    assert writes(api) == 0
    assert "moved A.zwo: week 1 tue -> week 1 thu" in out
    assert "+    thu: A.zwo" in out  # the plan.yaml diff
    assert "  + 2026-12-03 Thu  WORKOUT  A.zwo" in out
    assert "  - 2026-12-01  WORKOUT  Workout A  planner-test-w01-tue" in out
    assert "1 new, 0 updated, 4 unchanged, 1 stale (1 to delete)." in out


def test_move_apply_writes_the_file_then_syncs_with_prune(api, client, write_plan, make_plan):
    path = write_plan()
    api.events.return_value = httpx.Response(200, json=calendar_for(make_plan()))
    out = planner.move(path, 1, "tue", "thu", client=client, dry_run=False, today=TODAY)
    assert out.startswith(f"Wrote {path}.")
    plan = load_plan(path)
    assert {(e.week, e.day) for e in plan.events if e.week == 1} == {(1, "thu"), (1, "sat")}
    sent = json.loads(api.upsert.calls.last.request.content)
    assert [e["external_id"] for e in sent] == ["planner-test-w01-thu"]
    body = json.loads(api.bulk_delete.calls.last.request.content)
    assert body == [{"id": 1}]  # the old Tuesday event, nothing else


@pytest.mark.parametrize(
    "args, today, msg",
    [
        ((1, "tue", "thu"), D(2026, 12, 2), r"session \(2026-12-01\) is in the past"),
        ((1, "sat", "mon"), D(2026, 12, 2), r"target day \(2026-11-30\) is in the past"),
        ((1, "tue", "sat"), D(2026, 11, 23), "already has note 'Group ride'"),
        ((1, "wed", "thu"), D(2026, 11, 23), "has no session"),
    ],
)
def test_move_refusals_change_nothing(api, client, write_plan, args, today, msg):
    path = write_plan()
    before = read(path)
    with pytest.raises(PlannerError, match=msg):
        planner.move(path, *args, client=client, dry_run=False, today=at(today))
    assert read(path) == before
    assert len(api.calls) == 0


def test_move_apply_needs_a_key_and_leaves_the_file(write_plan):
    path = write_plan()
    before = read(path)
    with pytest.raises(PlannerError, match="not connected"):
        planner.move(path, 1, "tue", "thu", client=None, dry_run=False, today=TODAY)
    assert read(path) == before


def test_move_dry_run_works_offline(write_plan):
    out = planner.move(write_plan(), 1, "tue", "thu", client=None, today=TODAY)
    assert "Calendar not checked" in out


def test_file_changed_meanwhile_is_not_overwritten(api, client, write_plan, monkeypatch):
    path = write_plan()
    real = edit_mod.move_session

    def edit_and_touch(src, **kw):
        result = real(src, **kw)
        with open(path, "a") as f:
            f.write("# someone else\n")
        return result

    monkeypatch.setattr(edit_mod, "move_session", edit_and_touch)
    with pytest.raises(PlannerError, match="changed while this ran"):
        planner.move(path, 1, "tue", "thu", client=client, dry_run=False, today=TODAY)
    assert read(path).endswith("# someone else\n")
    assert writes(api) == 0


def test_failed_sync_after_write_says_how_to_finish(api, client, write_plan):
    api.events.return_value = httpx.Response(200, json=[])
    api.upsert.side_effect = None
    api.upsert.return_value = httpx.Response(500, text="boom")
    path = write_plan()
    with pytest.raises(ApiError, match="was updated but the calendar wasn't"):
        planner.move(path, 1, "tue", "thu", client=client, dry_run=False, today=TODAY)
    assert (1, "thu") in {(e.week, e.day) for e in load_plan(path).events}


def test_shift_before_the_start_moves_the_start(api, client, write_plan, make_plan):
    path = write_plan()
    api.events.return_value = httpx.Response(200, json=calendar_for(make_plan()))
    out = planner.shift(path, client=client, weeks=1, dry_run=False, today=TODAY)
    assert "start: 2026-11-30 -> 2026-12-07" in out
    assert load_plan(path).start == D(2026, 12, 7)
    assert "0 new, 5 updated, 0 unchanged, 0 stale" in out  # same uids, moved in place
    assert api.bulk_delete.call_count == 0


def test_shift_in_week_one_before_any_session_moves_the_start(api, client, write_plan):
    """Day 1 of the plan, a rest day: nothing ridden yet, so it's a plain start move."""
    out = planner.shift(write_plan(), client=client, today=at(D(2026, 11, 30)))
    assert "start: 2026-11-30 -> 2026-12-07" in out
    assert "inserted" not in out


def test_shift_under_way_keeps_the_past(api, client, write_plan, make_plan):
    """In week 2 (Dec 8): week 1 stays, week 2 onwards moves a week later."""
    path = write_plan()
    api.events.return_value = httpx.Response(200, json=calendar_for(make_plan()))
    out = planner.shift(path, client=client, weeks=1, dry_run=False, today=at(D(2026, 12, 8)))
    plan = load_plan(path)
    assert plan.weeks == 4
    assert {e.week for e in plan.events} == {1, 3, 4}
    assert "inserted week 2 as rest" in out
    body = json.loads(api.bulk_delete.calls.last.request.content)
    # Weeks are now [build, rest, build, easy]. Stale: old w02-tue (today, Dec 8),
    # w02-sat and w03-wed (that content is now w03/w04). Week 1, in the past, is untouched.
    assert sorted(d["id"] for d in body) == [3, 4, 5]
    sent = {e["external_id"] for e in json.loads(api.upsert.calls.last.request.content)}
    assert sent == {"planner-test-w03-tue", "planner-test-w03-sat", "planner-test-w04-wed"}


@pytest.mark.parametrize(
    "kw, today, msg",
    [
        ({"weeks": 0}, D(2026, 12, 8), "between 1 and 12"),
        ({"weeks": 13}, D(2026, 12, 8), "between 1 and 12"),
        ({"from_week": 1}, D(2026, 12, 8), r"week 1 is in the past \(this is week 2\)"),
        ({}, D(2027, 1, 30), "already finished"),
    ],
)
def test_shift_refusals(client, write_plan, kw, today, msg):
    with pytest.raises(PlannerError, match=msg):
        planner.shift(write_plan(), client=client, today=at(today), **kw)


# ------------------------------------------------------------------- library


FOLDERS = [
    {
        "id": 2,
        "name": "Winter base",
        "type": "PLAN",
        "children": [
            {"name": "Tempo 2x12", "type": "Ride", "moving_time": 3600, "icu_training_load": 62},
            {"name": "Recovery spin", "type": "Ride", "moving_time": 2700, "icu_training_load": 21},
        ],
    },
    {"id": 1, "name": "Favourites", "type": "FOLDER", "children": []},
]


def test_library_lists_folders_and_workouts(client):
    with respx.mock:
        respx.get(f"{API}/folders").mock(return_value=httpx.Response(200, json=FOLDERS))
        out = planner.library(client=client)
    lines = out.splitlines()
    assert lines[0] == "Workout library: 2 folder(s), 2 workouts."
    assert "Favourites (folder, 0 workouts)" in out
    assert "Winter base (plan, 2 workouts)" in out
    assert out.index("Recovery spin") < out.index("Tempo 2x12")  # sorted by name
    row = next(ln for ln in lines if "Tempo 2x12" in ln).split()
    assert row[-3:] == ["Ride", "1:00", "62"]


def test_library_folder_filter_and_empty(client):
    with respx.mock:
        respx.get(f"{API}/folders").mock(return_value=httpx.Response(200, json=FOLDERS))
        assert "Favourites" not in planner.library(client=client, folder="WINTER")
        assert planner.library(client=client, folder="summer") == (
            "No workout folders matching 'summer' in the library."
        )


# ------------------------------------------- which credential created an event

APP = 2022


def _calendar_with(plan, *, renamed: int, apps: dict[int, int | None]):
    """The plan's first three events on the calendar, event 1 renamed; apps maps id -> app."""
    cal = []
    for i, e in enumerate(plan.events[:3], start=1):
        ev = cal_event(
            e.uid,
            e.date.isoformat(),
            id=i,
            name=e.name,
            category=e.category,
            moving_time=e.workout.total_seconds if e.workout else None,
            description=e.description,
        )
        if apps.get(i):
            ev["oauth_client_id"] = apps[i]
        cal.append(ev)
    cal[renamed - 1]["name"] = "Old name"
    return cal


@pytest.fixture
def update_route(api):
    return api.router.put(url__regex=rf"{API}/events/\d+$").mock(
        side_effect=lambda req: httpx.Response(200, json=json.loads(req.content))
    )


@pytest.fixture
def oauth_client():
    from intervals_icu_planner_mcp.client import IntervalsClient

    c = IntervalsClient.from_token("tok-not-real", oauth_client_id=APP)
    yield c
    c.close()


def test_signed_in_push_updates_api_key_events_by_id_not_by_upsert(
    api, update_route, oauth_client, write_plan, make_plan
):
    # Events pushed earlier with an API key: an upsert from the app wouldn't match
    # them and would create duplicates, so they're updated in place by id.
    api.events.return_value = httpx.Response(
        200, json=_calendar_with(make_plan(), renamed=1, apps={})
    )
    planner.push(write_plan(), client=oauth_client, dry_run=False)

    assert update_route.call_count == 1
    req = update_route.calls.last.request
    assert req.url.path.endswith("/events/1")
    assert json.loads(req.content)["external_id"] == "planner-test-w01-tue"
    assert req.headers["Authorization"] == "Bearer tok-not-real"
    sent = json.loads(api.upsert.calls.last.request.content)  # only the new ones
    assert "planner-test-w01-tue" not in [e["external_id"] for e in sent]
    assert len(sent) == 2


def test_signed_in_push_upserts_its_own_events(
    api, update_route, oauth_client, write_plan, make_plan
):
    api.events.return_value = httpx.Response(
        200, json=_calendar_with(make_plan(), renamed=1, apps={1: APP, 2: APP, 3: APP})
    )
    planner.push(write_plan(), client=oauth_client, dry_run=False)
    assert update_route.call_count == 0
    sent = json.loads(api.upsert.calls.last.request.content)
    assert sent[0]["external_id"] == "planner-test-w01-tue"


def test_api_key_push_updates_app_events_by_id(api, update_route, client, write_plan, make_plan):
    api.events.return_value = httpx.Response(
        200, json=_calendar_with(make_plan(), renamed=2, apps={2: APP})
    )
    planner.push(write_plan(), client=client, dry_run=False)
    assert update_route.call_count == 1
    assert update_route.calls.last.request.url.path.endswith("/events/2")


def test_unchanged_events_of_another_credential_are_left_alone(
    api, update_route, oauth_client, write_plan, make_plan
):
    cal = _calendar_with(make_plan(), renamed=1, apps={})
    cal[0]["name"] = make_plan().events[0].name  # nothing changed
    api.events.return_value = httpx.Response(200, json=cal)
    planner.push(write_plan(), client=oauth_client, dry_run=False)
    assert update_route.call_count == 0


def test_signed_in_dry_run_writes_nothing(api, update_route, oauth_client, write_plan, make_plan):
    api.events.return_value = httpx.Response(
        200, json=_calendar_with(make_plan(), renamed=1, apps={})
    )
    planner.push(write_plan(), client=oauth_client)
    assert writes(api) == 0
    assert update_route.call_count == 0
