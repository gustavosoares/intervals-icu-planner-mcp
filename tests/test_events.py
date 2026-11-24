import base64
import datetime as dt
import json

from intervals_icu_planner_mcp import client as client_mod
from intervals_icu_planner_mcp.cli import main, matching_ids
from intervals_icu_planner_mcp.client import Client, auth_header
from intervals_icu_planner_mcp.events import build_payloads
from intervals_icu_planner_mcp.plan import build_plan


def make_plan(workouts):
    return build_plan({
        "id": "test", "start": "2026-11-30", "weeks": 1, "type": "VirtualRide",
        "template": {"tue": "A.zwo", "sat": {"note": "Group ride", "description": "or indoors"}},
    }, str(workouts))


def test_workout_payload(workouts):
    w = build_payloads(make_plan(workouts))[0]
    assert set(w) == {"category", "type", "start_date_local", "name", "filename",
                      "file_contents", "uid", "external_id"}
    assert w["category"] == "WORKOUT"
    assert w["type"] == "VirtualRide"
    assert w["start_date_local"] == "2026-12-01T00:00:00"
    assert w["filename"] == "A.zwo"
    assert w["file_contents"].startswith("<?xml")
    assert w["uid"] == w["external_id"] == "test-w01-tue"


def test_note_payload(workouts):
    n = build_payloads(make_plan(workouts))[1]
    assert n == {
        "category": "NOTE",
        "start_date_local": "2026-12-05T00:00:00",
        "end_date_local": "2026-12-05T00:00:00",
        "name": "Group ride",
        "description": "or indoors",
        "uid": "test-w01-sat",
        "external_id": "test-w01-sat",
    }


def test_payload_is_json_serialisable(workouts):
    json.dumps(build_payloads(make_plan(workouts)))


def test_auth_header():
    value = auth_header("secret")
    assert value.startswith("Basic ")
    assert base64.b64decode(value[6:]).decode() == "API_KEY:secret"


def test_upsert_request(monkeypatch, workouts):
    sent = []

    class Resp:
        def __init__(self, body):
            self.body = body

        def read(self):
            return self.body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        sent.append(req)
        return Resp(json.dumps([{"id": 1}, {"id": 2}]).encode())

    monkeypatch.setattr(client_mod.urllib.request, "urlopen", fake_urlopen)
    payloads = build_payloads(make_plan(workouts))
    res = Client("k").upsert_events(payloads)

    assert len(res) == 2
    req = sent[0]
    assert req.get_method() == "POST"
    assert req.full_url == "https://intervals.icu/api/v1/athlete/0/events/bulk?upsert=true"
    assert req.get_header("Authorization") == auth_header("k")
    assert req.get_header("Content-type") == "application/json"
    assert json.loads(req.data) == payloads


def test_list_and_delete_requests():
    c = Client("k")
    req = c.build_request("GET", "/events", {"oldest": "2026-11-30", "newest": "2026-12-06"})
    assert req.full_url.endswith("/athlete/0/events?oldest=2026-11-30&newest=2026-12-06")
    req = c.build_request("PUT", "/events/bulk-delete", body=[{"id": 5}])
    assert req.full_url.endswith("/athlete/0/events/bulk-delete")
    assert json.loads(req.data) == [{"id": 5}]


def test_matching_ids_only_this_plan(workouts):
    plan = make_plan(workouts)
    existing = [
        {"id": 1, "external_id": "test-w01-tue"},
        {"id": 2, "uid": "test-w01-sat"},
        {"id": 3, "external_id": "other-w01-tue"},
        {"id": 4, "uid": "testing-w01-tue"},
        {"id": 5},
    ]
    assert matching_ids(plan, existing) == [1, 2]


def test_dry_run_sends_nothing(monkeypatch, capsys, example_plan):
    def boom(*a, **k):
        raise AssertionError("network used in dry run")

    monkeypatch.setattr(client_mod.urllib.request, "urlopen", boom)
    monkeypatch.delenv("INTERVALS_API_KEY", raising=False)
    assert main([example_plan, "--dry-run"]) == 0
    assert main([example_plan, "--dry-run", "--delete"]) == 0
    out = capsys.readouterr().out
    assert "54 events" in out and "would delete" in out


def test_cli_rejects_non_monday(capsys, example_plan):
    assert main([example_plan, "--dry-run", "--start", "2026-12-01"]) == 2
    assert "must be a Monday" in capsys.readouterr().err


def test_cli_missing_key(monkeypatch, tmp_path, capsys, example_plan):
    monkeypatch.delenv("INTERVALS_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    assert main([example_plan]) == 2
    assert "Missing API key" in capsys.readouterr().err
