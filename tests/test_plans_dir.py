"""The optional plans folder: plans and workouts outside it are refused."""

import asyncio
import os

import pytest
import yaml
from mcp.server.mcpserver.exceptions import ToolError

from intervals_icu_planner_mcp import planner, server
from intervals_icu_planner_mcp.config import PLANS_DIR_ENV_VAR, find_plans_dir
from intervals_icu_planner_mcp.plan import PlanError, load_plan

from .conftest import plan_data


def write(plan_dir, **kw):
    path = plan_dir / "plan.yaml"
    path.write_text(yaml.safe_dump(plan_data(**kw)), encoding="utf-8")
    return path


@pytest.mark.parametrize("value", [None, "", "  ", "${user_config.plans_dir}"])
def test_unset_blank_or_unfilled_placeholder_means_anywhere(value):
    env = {} if value is None else {PLANS_DIR_ENV_VAR: value}
    assert find_plans_dir(env) is None


def test_plans_dir_expands_home():
    assert find_plans_dir({PLANS_DIR_ENV_VAR: "~/training"}) == os.path.expanduser("~/training")


def test_plan_inside_the_folder_loads(workouts, tmp_path):
    plan = load_plan(str(write(workouts)), root=str(tmp_path))
    assert plan.events


def test_plan_outside_the_folder_is_refused_before_it_is_read(tmp_path):
    root = tmp_path / "plans"
    root.mkdir()
    missing = tmp_path / "elsewhere" / "plan.yaml"  # never opened, so it needn't exist
    with pytest.raises(PlanError, match="outside the plans folder"):
        load_plan(str(missing), root=str(root))


def test_dotdot_does_not_escape(workouts, tmp_path):
    root = tmp_path / "plans"
    root.mkdir()
    sneaky = root / ".." / "plan" / "plan.yaml"
    write(workouts)
    with pytest.raises(PlanError, match="outside the plans folder"):
        load_plan(str(sneaky), root=str(root))


def test_workouts_dir_outside_the_folder_is_an_error(workouts, tmp_path):
    root = tmp_path / "plans" / "mine"
    root.mkdir(parents=True)
    path = write(root, workouts_dir="../../plan/workouts")
    with pytest.raises(PlanError, match=r"A\.zwo: outside the plans folder"):
        load_plan(str(path), root=str(root))
    assert load_plan(str(path)).events  # without a plans folder the same plan is fine


def test_symlinked_workout_pointing_outside_is_an_error(workouts, tmp_path):
    root = tmp_path / "plans"
    (root / "workouts").mkdir(parents=True)
    for n in ("B", "C"):
        os.symlink(workouts / "workouts" / f"{n}.zwo", root / "workouts" / f"{n}.zwo")
    (root / "workouts" / "A.zwo").write_text(
        (workouts / "workouts" / "A.zwo").read_text(), encoding="utf-8"
    )
    with pytest.raises(PlanError, match=r"C\.zwo: outside the plans folder"):
        load_plan(str(write(root)), root=str(root))


def test_move_outside_the_folder_changes_nothing(workouts, tmp_path):
    root = tmp_path / "plans"
    root.mkdir()
    path = write(workouts)
    before = path.read_text()
    with pytest.raises(PlanError, match="outside the plans folder"):
        planner.move(str(path), 1, "tue", "thu", client=None, plans_dir=str(root))
    assert path.read_text() == before


def test_push_plan_tool_honours_the_env_var(workouts, tmp_path, monkeypatch):
    root = tmp_path / "plans"
    root.mkdir()
    monkeypatch.setenv(PLANS_DIR_ENV_VAR, str(root))
    with pytest.raises(ToolError, match="outside the plans folder"):
        asyncio.run(server.mcp.call_tool("push_plan", {"plan_yaml": str(write(workouts))}))
