import re

import yaml

from intervals_icu_planner_mcp import guide
from intervals_icu_planner_mcp.plan import build_plan
from intervals_icu_planner_mcp.zwo import MAX_POWER, SEGMENTS, validate_zwo


def test_example_zwo_is_valid():
    w = validate_zwo(guide.EXAMPLE_ZWO, "Tempo_3x10.zwo")
    assert w.name == "Tempo 3x10min"
    assert w.total_seconds == 600 + 3 * (600 + 300) + 600 + 300


def test_example_plan_is_valid(tmp_path):
    data = yaml.safe_load(guide.EXAMPLE_PLAN)
    (tmp_path / "workouts").mkdir()
    for name in ("Tempo_3x10.zwo", "Z2_60.zwo"):
        (tmp_path / "workouts" / name).write_text(guide.EXAMPLE_ZWO, encoding="utf-8")
    plan = build_plan(data, str(tmp_path))
    assert plan.start.weekday() == 0
    assert len({e.week for e in plan.events}) == 4
    assert {e.category for e in plan.events} == {"WORKOUT", "NOTE"}


def test_guide_embeds_both_examples_and_the_schema():
    text = guide.plan_guide()
    assert guide.EXAMPLE_PLAN in text
    assert guide.EXAMPLE_ZWO in text
    assert '"title":"plan.yaml"' in text


def test_guide_rules_come_from_the_validator():
    text = guide.plan_guide()
    for name, (durations, powers) in SEGMENTS.items():
        assert f"`{name}`" in text
        for attr in (*durations, *powers):
            assert attr in text
    assert f"(0, {MAX_POWER:g}]" in text


def test_guide_never_uses_absolute_watts():
    assert not re.search(r"\b\d+\s?W\b", guide.plan_guide())
