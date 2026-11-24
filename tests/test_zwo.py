import glob
import os

import pytest

from intervals_icu_planner_mcp.zwo import MAX_TOTAL_SECONDS, ZwoError, parse_zwo, validate_zwo

from .conftest import EXAMPLE


def zwo(segments: str, name: str = "Test") -> str:
    return (
        f"<workout_file><name>{name}</name><sportType>bike</sportType>"
        f"<workout>{segments}</workout></workout_file>"
    )


def errors(text: str) -> list[str]:
    with pytest.raises(ZwoError) as e:
        validate_zwo(text, "t.zwo")
    return e.value.errors


def test_valid_workout_totals_every_segment_type():
    w = validate_zwo(
        zwo(
            '<Warmup Duration="600" PowerLow="0.4" PowerHigh="0.7"/>'
            '<SteadyState Duration="300" Power="0.9">'
            '<textevent timeoffset="0" message="hi"/></SteadyState>'
            '<IntervalsT Repeat="5" OnDuration="30" OffDuration="30" OnPower="1.2" OffPower="0.5"/>'
            '<Ramp Duration="120" PowerLow="0.5" PowerHigh="0.8"/>'
            '<FreeRide Duration="60" FlatRoad="1"/>'
            '<MaxEffort Duration="10"/>'
            '<Cooldown Duration="300" PowerLow="0.6" PowerHigh="0.4"/>'
        ),
        "t.zwo",
    )
    assert w.total_seconds == 600 + 300 + 5 * 60 + 120 + 60 + 10 + 300
    assert w.name == "Test"
    assert w.filename == "t.zwo"


def test_name_falls_back_to_filename():
    w = validate_zwo(
        '<workout_file><workout><SteadyState Duration="60" Power="0.5"/></workout></workout_file>',
        "My_Ride.zwo",
    )
    assert w.name == "My_Ride"


@pytest.mark.parametrize(
    "text, expected",
    [
        ("<workout_file><workout>", "invalid XML"),
        ("<other/>", "expected <workout_file>"),
        ("<workout_file><workout/></workout_file>", "missing or empty <workout>"),
        ('<!DOCTYPE x [<!ENTITY a "b">]><workout_file/>', "DOCTYPE"),
    ],
)
def test_structure_errors(text, expected):
    assert expected in errors(text)[0]


@pytest.mark.parametrize("duration", ["0", "-30"])
def test_duration_must_be_positive(duration):
    assert (
        "Duration must be > 0"
        in errors(zwo(f'<SteadyState Duration="{duration}" Power="0.5"/>'))[0]
    )


@pytest.mark.parametrize("power", ["0", "-0.1", "3.01", "250"])
def test_power_ratio_must_be_in_range(power):
    assert "outside (0, 3]" in errors(zwo(f'<SteadyState Duration="60" Power="{power}"/>'))[0]


def test_power_of_exactly_3_is_allowed():
    validate_zwo(zwo('<SteadyState Duration="10" Power="3.0"/>'), "t.zwo")


def test_interval_powers_and_durations_checked():
    errs = errors(
        zwo('<IntervalsT Repeat="0" OnDuration="0" OffDuration="30" OnPower="4" OffPower="0.5"/>')
    )
    assert any("OnDuration must be > 0" in e for e in errs)
    assert any("OnPower=4" in e for e in errs)
    assert any("Repeat" in e for e in errs)


def test_missing_and_non_numeric_attributes():
    errs = errors(zwo('<SteadyState Power="0.5"/><Warmup Duration="abc" PowerLow="0.4"/>'))
    assert "segment 1 <SteadyState>: missing Duration" in errs
    assert any("Duration='abc' is not a number" in e for e in errs)
    assert any("missing PowerHigh" in e for e in errs)


def test_unknown_segment_is_rejected():
    assert "unsupported segment type" in errors(zwo('<Teleport Duration="60"/>'))[0]


def test_total_must_be_under_six_hours():
    errs = errors(zwo(f'<SteadyState Duration="{MAX_TOTAL_SECONDS}" Power="0.5"/>'))
    assert "not under the 6:00:00 limit" in errs[0]
    validate_zwo(zwo(f'<SteadyState Duration="{MAX_TOTAL_SECONDS - 1}" Power="0.5"/>'), "t.zwo")


def test_all_problems_reported_together():
    errs = errors(zwo('<SteadyState Duration="0" Power="9"/><Teleport/>'))
    assert len(errs) == 3


def test_missing_file(tmp_path):
    with pytest.raises(ZwoError, match="file not found"):
        parse_zwo(str(tmp_path / "nope.zwo"))


def test_every_example_workout_is_valid():
    files = glob.glob(os.path.join(EXAMPLE.parent, "workouts", "*.zwo"))
    assert len(files) == 14
    for path in files:
        w = parse_zwo(path)
        assert 0 < w.total_seconds < MAX_TOTAL_SECONDS
