import datetime as dt
import json
from dataclasses import dataclass

import httpx
import pytest
import respx

from intervals_icu_planner_mcp import planner
from intervals_icu_planner_mcp.plan import PlanError
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


def writes(api: Api) -> int:
    return api.upsert.call_count + api.bulk_delete.call_count


# ---------------------------------------------------------------------- push


def test_push_dry_run_never_writes(api, client, write_plan):
    out = planner.push(write_plan(), client=client)
    assert writes(api) == 0
    assert api.events.call_count == 1
    params = dict(api.events.calls.last.request.url.params)
    assert params == {"oldest": "2026-11-30", "newest": "2026-12-20"}
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
    with pytest.raises(PlannerError, match=r"no intervals\.icu API key"):
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
TODAY = lambda: dt.date(2026, 11, 23)  # noqa: E731


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
    with pytest.raises(PlannerError, match="API key"):
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
