import asyncio

import httpx
import pytest
import respx
from mcp.server.mcpserver.exceptions import ToolError

from intervals_icu_planner_mcp import server

from .conftest import API, EXAMPLE


def tools():
    return {t.name: t for t in asyncio.run(server.mcp.list_tools())}


def call(name, **args):
    return asyncio.run(server.mcp.call_tool(name, args))


def test_tools_and_parameters():
    t = tools()
    assert set(t) == {"push_plan", "get_planned", "delete_plan", "get_fitness", "get_activities"}
    props = {n: tool.input_schema["properties"] for n, tool in t.items()}
    assert set(props["push_plan"]) == {"plan_yaml", "start_date", "dry_run"}
    assert set(props["delete_plan"]) == {"plan_id", "dry_run", "oldest", "newest"}
    assert set(props["get_planned"]) == {"oldest", "newest", "plan_id"}
    assert t["push_plan"].input_schema["required"] == ["plan_yaml"]
    assert t["delete_plan"].input_schema["required"] == ["plan_id"]


def test_write_tools_default_to_dry_run():
    t = tools()
    assert t["push_plan"].input_schema["properties"]["dry_run"]["default"] is True
    assert t["delete_plan"].input_schema["properties"]["dry_run"]["default"] is True


def test_annotations():
    t = tools()
    assert t["delete_plan"].annotations.destructive_hint is True
    assert t["push_plan"].annotations.destructive_hint is False
    for name in ("get_planned", "get_fitness", "get_activities"):
        assert t[name].annotations.read_only_hint is True


def test_push_plan_offline_dry_run():
    res = call("push_plan", plan_yaml=str(EXAMPLE))
    text = res.content[0].text
    assert "54 new, 0 updated, 0 unchanged, 0 stale." in text
    assert not res.is_error


def test_expected_errors_reach_the_model():
    with pytest.raises(ToolError, match="must be a Monday"):
        call("push_plan", plan_yaml=str(EXAMPLE), start_date="2026-12-01")
    with pytest.raises(ToolError, match=r"no intervals\.icu API key"):
        call("delete_plan", plan_id="winterbase", dry_run=False)


def test_api_errors_reach_the_model(monkeypatch):
    monkeypatch.setenv("INTERVALS_ICU_API_KEY", "test-key-not-real")
    with respx.mock:
        respx.get(f"{API}/wellness").mock(return_value=httpx.Response(401))
        with pytest.raises(ToolError) as e:
            call("get_fitness", oldest="2026-12-01", newest="2026-12-07")
    assert "check your intervals.icu API key" in str(e.value)
    assert "test-key-not-real" not in str(e.value)
