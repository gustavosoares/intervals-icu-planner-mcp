import json

import httpx
import respx

from intervals_icu_planner_mcp.cli import main
from intervals_icu_planner_mcp.plan import plan_json_schema

from .conftest import API, EXAMPLE


def test_push_without_apply_is_a_dry_run(capsys):
    assert main(["push", str(EXAMPLE)]) == 0
    out = capsys.readouterr().out
    assert "Dry run: nothing was written. Run again with --apply to apply." in out
    assert "54 new" in out


def test_push_with_key_dry_run_reads_but_never_writes(monkeypatch, capsys):
    monkeypatch.setenv("INTERVALS_ICU_API_KEY", "k")
    with respx.mock:  # only GET /events is mocked: any write would fail the test
        respx.get(f"{API}/events").mock(return_value=httpx.Response(200, json=[]))
        assert main(["push", str(EXAMPLE)]) == 0


def test_apply_without_key(capsys):
    assert main(["push", str(EXAMPLE), "--apply"]) == 2
    assert "no intervals.icu API key" in capsys.readouterr().err


def test_invalid_plan_exit_code(capsys):
    assert main(["push", str(EXAMPLE), "--start", "2026-12-01"]) == 2
    assert "must be a Monday" in capsys.readouterr().err


def test_api_error_exit_code(monkeypatch, capsys):
    monkeypatch.setenv("INTERVALS_ICU_API_KEY", "k")
    with respx.mock:
        respx.get(f"{API}/wellness").mock(return_value=httpx.Response(500, text="oops"))
        assert main(["fitness", "2026-12-01", "2026-12-07"]) == 1
    assert "HTTP 500" in capsys.readouterr().err


def test_delete_defaults_to_dry_run(monkeypatch, capsys):
    monkeypatch.setenv("INTERVALS_ICU_API_KEY", "k")
    with respx.mock:
        respx.get(f"{API}/events").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "id": 1,
                        "uid": "planner-winterbase-w01-tue",
                        "start_date_local": "2026-12-01T00:00:00",
                    }
                ],
            )
        )
        assert main(["delete", "winterbase"]) == 0
    assert "Run again with --apply" in capsys.readouterr().out


def test_schema_command(capsys):
    assert main(["schema"]) == 0
    assert json.loads(capsys.readouterr().out) == plan_json_schema()
