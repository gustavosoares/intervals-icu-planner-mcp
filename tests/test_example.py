import datetime as dt
import glob
import os
import re
from collections import Counter

from intervals_icu_planner_mcp.plan import load_plan

from .conftest import EXAMPLE


def test_example_plan_loads():
    plan = load_plan(str(EXAMPLE))
    assert plan.start == dt.date(2026, 11, 23)
    assert plan.end == dt.date(2027, 2, 14)
    # 12 weeks x 5 sessions (Tue, Wed, Thu, Sat, Sun); Monday and Friday are rest days
    assert len(plan.events) == 60
    assert len({e.uid for e in plan.events}) == 60
    assert all(e.uid.startswith("planner-winterbase-w") for e in plan.events)
    assert Counter(e.category for e in plan.events) == {"WORKOUT": 48, "NOTE": 12}
    assert {e.day for e in plan.events} == {"tue", "wed", "thu", "sat", "sun"}


def test_example_four_week_cycles_build_sweet_spot():
    plan = load_plan(str(EXAMPLE))
    tue = {e.week: e.workout.filename for e in plan.events if e.day == "tue" and e.workout}
    # short, short, long, sweet spot - three times
    for cycle in (0, 4, 8):
        assert tue[cycle + 1] == tue[cycle + 2] == "W09_Tempo_60_2x12.zwo"
        assert tue[cycle + 3] == "W06_Tempo_3x10.zwo"
    assert [tue[w] for w in (4, 8, 12)] == [
        "S1_SweetSpot_2x15.zwo",
        "S2_SweetSpot_2x20.zwo",
        "S3_SweetSpot_3x15.zwo",
    ]
    assert not any("Threshold" in name for name in tue.values())


def test_example_has_no_personal_data():
    """Power targets are %FTP only: no absolute watts, club names or athlete ids."""
    files = [str(EXAMPLE), *glob.glob(os.path.join(EXAMPLE.parent, "workouts", "*.zwo"))]
    assert len(files) == 14
    for path in files:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        assert not re.search(r"\b\d+\s?W\b", text), path
        assert not re.search(r"athlete/i?\d+|\bi\d{5,}\b", text), path
        assert not re.search(r"\bHR (under|below|over|above)? ?\d", text), path
        for personal in ("TCC", "gravel", "gym", "Coach"):
            assert personal not in text, (path, personal)
