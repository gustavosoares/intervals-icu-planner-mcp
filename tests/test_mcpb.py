"""The Claude Desktop extension (mcpb/) stays in step with the server."""

import asyncio
import importlib.util
import json
import shutil
from pathlib import Path

from intervals_icu_planner_mcp import config, server

ROOT = Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "mcpb"


def manifest():
    return json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))


def build_script():
    spec = importlib.util.spec_from_file_location("build_mcpb", ROOT / "scripts" / "build_mcpb.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manifest_lists_every_tool():
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert {t["name"] for t in manifest()["tools"]} == names


def test_api_key_is_sensitive_and_passed_in_the_env_var_the_server_reads():
    m = manifest()
    assert m["user_config"]["api_key"]["sensitive"] is True
    env = m["server"]["mcp_config"]["env"]
    assert env[config.ENV_VAR] == "${user_config.api_key}"


def test_optional_plans_folder_is_passed_in_the_env_var_the_server_reads():
    m = manifest()
    field = m["user_config"]["plans_dir"]
    assert field["type"] == "directory"
    assert field["required"] is False
    env = m["server"]["mcp_config"]["env"]
    assert env[config.PLANS_DIR_ENV_VAR] == "${user_config.plans_dir}"
    assert set(env) == {config.ENV_VAR, config.PLANS_DIR_ENV_VAR}


def test_entry_point_runs_the_server():
    m = manifest()
    assert m["server"]["type"] == "uv"
    entry = (BUNDLE / m["server"]["entry_point"]).read_text(encoding="utf-8")
    assert "from intervals_icu_planner_mcp.server import main" in entry


def test_stamp_sets_the_version_and_pins_the_package(tmp_path):
    bundle = tmp_path / "mcpb"
    shutil.copytree(BUNDLE, bundle)
    build_script().stamp(bundle, "1.2.3")
    assert json.loads((bundle / "manifest.json").read_text())["version"] == "1.2.3"
    assert '"intervals-icu-planner-mcp==1.2.3"' in (bundle / "pyproject.toml").read_text()
    # the source files are untouched
    assert manifest()["version"] == "0.0.0"
