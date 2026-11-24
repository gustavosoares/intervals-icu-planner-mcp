import datetime as dt
import glob
import os
import re
from collections import Counter

from intervals_icu_planner_mcp.plan import load_plan


def test_example_plan_loads(example_plan):
    plan = load_plan(example_plan)
    assert plan.start == dt.date(2026, 11, 30)
    assert plan.end == dt.date(2027, 2, 21)
    # 9 build weeks x 5 sessions + 3 recovery weeks x 3 sessions
    assert len(plan.events) == 54
    assert len({e.uid for e in plan.events}) == 54
    cats = Counter(e.category for e in plan.events)
    assert cats == {"WORKOUT": 42, "NOTE": 12}


def test_example_threshold_progression(example_plan):
    plan = load_plan(example_plan)
    tue = {e.week: e.workout.filename for e in plan.events if e.day == "tue"}
    assert tue[1] == "T1_Threshold_3x8.zwo"
    assert tue[4] == "W02_Z2_Endurance_60_Cadence.zwo"  # recovery week
    assert tue[11] == "T6_Threshold_2x20_Progressed.zwo"


def test_example_has_no_personal_data(example_plan):
    """Power targets are %FTP only: no absolute watts, club names or athlete ids."""
    folder = os.path.dirname(example_plan)
    files = [example_plan] + glob.glob(os.path.join(folder, "workouts", "*.zwo"))
    assert len(files) == 15
    for path in files:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        assert not re.search(r"\b\d+\s?W\b", text), path
        assert not re.search(r"athlete/i?\d+|\bi\d{5,}\b", text), path
        assert "TCC" not in text, path
