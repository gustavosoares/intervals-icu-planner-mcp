import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

ZWO = """<?xml version="1.0" encoding="UTF-8"?>
<workout_file>
  <name>{name}</name>
  <sportType>bike</sportType>
  <workout>
    <SteadyState Duration="600" Power="0.65"/>
  </workout>
</workout_file>
"""


@pytest.fixture
def workouts(tmp_path):
    """A plan directory with a workouts/ folder holding A.zwo, B.zwo, C.zwo."""
    d = tmp_path / "workouts"
    d.mkdir()
    for n in ("A", "B", "C"):
        (d / f"{n}.zwo").write_text(ZWO.format(name=f"Workout {n}"), encoding="utf-8")
    return tmp_path


@pytest.fixture
def example_plan():
    return os.path.join(ROOT, "examples", "winter-base-12wk", "plan.yaml")
