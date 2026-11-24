import datetime as dt
import glob
import os
import re
from collections import Counter

from intervals_icu_planner_mcp.plan import load_plan

from .conftest import EXAMPLE


def test_example_plan_loads():
    plan = load_plan(str(EXAMPLE))
    assert plan.start == dt.date(2026, 11, 30)
    assert plan.end == dt.date(2027, 2, 21)
    assert plan.recovery_weeks == {4, 8, 12}
    # 9 build weeks x 5 sessions + 3 recovery weeks x 3 sessions
    assert len(plan.events) == 54
    assert len({e.uid for e in plan.events}) == 54
    assert all(e.uid.startswith("planner-winterbase-w") for e in plan.events)
    assert Counter(e.category for e in plan.events) == {"WORKOUT": 42, "NOTE": 12}


def test_example_threshold_progression():
    plan = load_plan(str(EXAMPLE))
    tue = {e.week: e.workout.filename for e in plan.events if e.day == "tue" and e.workout}
    assert [tue[w] for w in (1, 3, 5, 7, 9, 11)] == [
        "T1_Threshold_3x8.zwo",
        "T2_Threshold_3x10.zwo",
        "T3_Threshold_2x15.zwo",
        "T4_Threshold_3x12.zwo",
        "T5_Threshold_2x20.zwo",
        "T6_Threshold_2x20_Progressed.zwo",
    ]
    assert tue[4] == tue[8] == tue[12] == "W02_Z2_Endurance_60_Cadence.zwo"  # recovery


def test_example_has_no_personal_data():
    """Power targets are %FTP only: no absolute watts, club names or athlete ids."""
    files = [str(EXAMPLE), *glob.glob(os.path.join(EXAMPLE.parent, "workouts", "*.zwo"))]
    assert len(files) == 15
    for path in files:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        assert not re.search(r"\b\d+\s?W\b", text), path
        assert not re.search(r"athlete/i?\d+|\bi\d{5,}\b", text), path
        assert "TCC" not in text, path
