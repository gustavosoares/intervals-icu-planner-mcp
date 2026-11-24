"""Parse and validate .zwo workout files before anything is uploaded.

The file is sent to intervals.icu exactly as written; this module only decides
whether it is safe to send. Every problem in a file is reported together.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass

MAX_TOTAL_SECONDS = 6 * 3600
MAX_POWER = 3.0  # fraction of FTP

# segment -> (duration attributes, required power attributes)
SEGMENTS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "SteadyState": (("Duration",), ("Power",)),
    "SolidState": (("Duration",), ("Power",)),
    "Warmup": (("Duration",), ("PowerLow", "PowerHigh")),
    "Cooldown": (("Duration",), ("PowerLow", "PowerHigh")),
    "Ramp": (("Duration",), ("PowerLow", "PowerHigh")),
    "IntervalsT": (("OnDuration", "OffDuration"), ("OnPower", "OffPower")),
    "FreeRide": (("Duration",), ()),
    "MaxEffort": (("Duration",), ()),
}
# Any of these that appear on a segment are range-checked, required or not.
POWER_ATTRS = (
    "Power",
    "PowerLow",
    "PowerHigh",
    "OnPower",
    "OffPower",
    "PowerOnLow",
    "PowerOnHigh",
    "PowerOffLow",
    "PowerOffHigh",
)


class ZwoError(ValueError):
    """A .zwo file failed validation. ``errors`` lists every problem found."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


@dataclass(frozen=True)
class Workout:
    filename: str
    name: str
    contents: str
    total_seconds: int


def _number(seg: ET.Element, attr: str, where: str, errors: list[str]) -> float | None:
    raw = seg.get(attr)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        errors.append(f"{where}: {attr}={raw!r} is not a number")
        return None


def validate_zwo(contents: str, filename: str) -> Workout:
    """Validate the text of a .zwo file. Raises ZwoError listing every problem."""
    if "<!DOCTYPE" in contents or "<!ENTITY" in contents:
        raise ZwoError(["DOCTYPE/ENTITY declarations are not allowed"])
    try:
        root = ET.fromstring(contents)
    except ET.ParseError as e:
        raise ZwoError([f"invalid XML: {e}"]) from None
    if root.tag != "workout_file":
        raise ZwoError([f"root element is <{root.tag}>, expected <workout_file>"])
    body = root.find("workout")
    if body is None or len(body) == 0:
        raise ZwoError(["missing or empty <workout> element"])

    errors: list[str] = []
    total = 0.0
    for i, seg in enumerate(body, start=1):
        where = f"segment {i} <{seg.tag}>"
        if seg.tag not in SEGMENTS:
            errors.append(f"{where}: unsupported segment type")
            continue
        duration_attrs, required_power = SEGMENTS[seg.tag]

        durations: list[float] = []
        for attr in duration_attrs:
            value = _number(seg, attr, where, errors)
            if value is None:
                if attr not in seg.attrib:
                    errors.append(f"{where}: missing {attr}")
            elif value <= 0:
                errors.append(f"{where}: {attr} must be > 0, got {value:g}")
            else:
                durations.append(value)

        for attr in required_power:
            if attr not in seg.attrib:
                errors.append(f"{where}: missing {attr}")
        for attr in POWER_ATTRS:
            power = _number(seg, attr, where, errors)
            if power is not None and not 0 < power <= MAX_POWER:
                errors.append(
                    f"{where}: {attr}={power:g} is outside (0, {MAX_POWER:g}] (fraction of FTP)"
                )

        repeat = 1.0
        if seg.tag == "IntervalsT":
            r = _number(seg, "Repeat", where, errors)
            if r is not None:
                if r < 1 or r != int(r):
                    errors.append(f"{where}: Repeat must be a whole number >= 1, got {r:g}")
                else:
                    repeat = r
        total += repeat * sum(durations)

    if total >= MAX_TOTAL_SECONDS:
        errors.append(
            f"total length {_hms(total)} is not under the {_hms(MAX_TOTAL_SECONDS)} limit"
        )
    if errors:
        raise ZwoError(errors)

    name = (root.findtext("name") or "").strip() or os.path.splitext(filename)[0]
    return Workout(filename=filename, name=name, contents=contents, total_seconds=round(total))


def parse_zwo(path: str) -> Workout:
    """Read ``path`` and validate it. Raises ZwoError."""
    try:
        with open(path, encoding="utf-8") as f:
            contents = f.read()
    except FileNotFoundError:
        raise ZwoError(["file not found"]) from None
    except (OSError, UnicodeDecodeError) as e:
        raise ZwoError([f"cannot read: {e}"]) from None
    return validate_zwo(contents, os.path.basename(path))


def _hms(seconds: float) -> str:
    s = round(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"
