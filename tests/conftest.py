from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import pytest

from intervals_icu_planner_mcp.client import IntervalsClient
from intervals_icu_planner_mcp.plan import build_plan

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "winter-base-12wk" / "plan.yaml"
API = "https://intervals.icu/api/v1/athlete/0"
FAKE_KEY = "test-key-not-real"

ZWO = """<?xml version="1.0" encoding="UTF-8"?>
<workout_file>
  <name>{name}</name>
  <sportType>bike</sportType>
  <workout>
    <SteadyState Duration="600" Power="0.65"/>
  </workout>
</workout_file>
"""


@pytest.fixture(autouse=True)
def _no_ambient_key(monkeypatch, tmp_path):
    """Tests never pick up a real key from the environment or a .env file."""
    monkeypatch.delenv("INTERVALS_ICU_API_KEY", raising=False)
    monkeypatch.delenv("INTERVALS_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def workouts(tmp_path: Path) -> Path:
    """A plan folder with workouts/A.zwo, B.zwo, C.zwo (10 min each)."""
    d = tmp_path / "plan" / "workouts"
    d.mkdir(parents=True)
    for n in ("A", "B", "C"):
        (d / f"{n}.zwo").write_text(ZWO.format(name=f"Workout {n}"), encoding="utf-8")
    return d.parent


def plan_data(**kw: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": "test",
        "name": "Test plan",
        "start": dt.date(2026, 11, 30),
        "templates": {
            "build": {"tue": "A.zwo", "sat": {"note": "Group ride", "description": "or indoors"}},
            "easy": {"wed": "C.zwo"},
        },
        "weeks": [
            {"template": "build"},
            {"template": "build"},
            {"template": "easy", "recovery": True},
        ],
    }
    data.update(kw)
    return data


@pytest.fixture
def make_plan(workouts):
    def _make(**kw: Any):
        return build_plan(plan_data(**kw), str(workouts))

    return _make


@pytest.fixture
def write_plan(workouts):
    """Write plan.yaml into the workouts fixture folder; return its path."""
    import yaml

    def _write(**kw: Any) -> str:
        path = workouts / "plan.yaml"
        path.write_text(yaml.safe_dump(plan_data(**kw)), encoding="utf-8")
        return str(path)

    return _write


@pytest.fixture
def client():
    c = IntervalsClient.from_api_key(FAKE_KEY)
    yield c
    c.close()


def cal_event(
    uid: str, date: str, *, id: int, name: str = "x", category: str = "WORKOUT", **kw: Any
) -> dict[str, Any]:
    return {
        "id": id,
        "uid": uid,
        "start_date_local": f"{date}T00:00:00",
        "name": name,
        "category": category,
        **kw,
    }
