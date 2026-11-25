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
    assert "60 new" in out


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
                        "external_id": "planner-winterbase-w01-tue",
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


def test_guide_command(capsys):
    from intervals_icu_planner_mcp.guide import plan_guide

    assert main(["guide"]) == 0
    assert capsys.readouterr().out == plan_guide()


def test_push_prune_without_apply_is_still_a_dry_run(monkeypatch, capsys):
    monkeypatch.setenv("INTERVALS_ICU_API_KEY", "k")
    stale = {
        "id": 9,
        "external_id": "planner-winterbase-w13-tue",
        "start_date_local": "2099-01-06T00:00:00",  # always in the future
        "name": "Old",
        "category": "WORKOUT",
    }
    with respx.mock:  # only GET is mocked: a write would fail the test
        respx.get(f"{API}/events").mock(return_value=httpx.Response(200, json=[stale]))
        assert main(["push", str(EXAMPLE), "--prune"]) == 0
    out = capsys.readouterr().out
    assert "  - 2099-01-06" in out
    assert "(1 to delete)" in out
    assert "Run again with --apply" in out


def test_move_and_shift_without_apply_are_dry_runs(tmp_path, capsys):
    import shutil

    plan_dir = tmp_path / "plan"
    shutil.copytree(EXAMPLE.parent, plan_dir)
    plan = plan_dir / "plan.yaml"
    before = plan.read_text()
    # Offline (no key): the plan file must be left alone, and nothing is sent.
    assert main(["move", str(plan), "12", "tue", "fri"]) == 0
    out = capsys.readouterr().out
    assert "moved S3_SweetSpot_3x15.zwo: week 12 tue -> week 12 fri" in out
    assert "Run again with --apply" in out
    assert main(["shift", str(plan), "--weeks", "2", "--from-week", "12"]) == 0
    assert "inserted weeks 12-13 as rest" in capsys.readouterr().out
    assert plan.read_text() == before


def test_move_refusal_exit_code(capsys):
    assert main(["move", str(EXAMPLE), "12", "tue", "wed"]) == 2
    assert "already has" in capsys.readouterr().err


def test_library_command(monkeypatch, capsys):
    monkeypatch.setenv("INTERVALS_ICU_API_KEY", "k")
    with respx.mock:
        respx.get(f"{API}/folders").mock(return_value=httpx.Response(200, json=[]))
        assert main(["library"]) == 0
    assert "No workout folders in the library." in capsys.readouterr().out
