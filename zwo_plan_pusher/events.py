"""Turn planned events into intervals.icu event payloads."""

from __future__ import annotations

from typing import Any, Dict, List

from .plan import Plan, PlannedEvent


def event_payload(ev: PlannedEvent, event_type: str = "Ride") -> Dict[str, Any]:
    date = f"{ev.date.isoformat()}T00:00:00"
    # upsert=true matches on external_id; uid is sent too so the id is visible either way.
    payload: Dict[str, Any] = {
        "category": ev.category,
        "start_date_local": date,
        "name": ev.name,
        "uid": ev.uid,
        "external_id": ev.uid,
    }
    if ev.category == "NOTE":
        payload["end_date_local"] = date
        payload["description"] = ev.description or ""
    else:
        payload["type"] = event_type
        payload["filename"] = ev.workout.filename
        payload["file_contents"] = ev.workout.contents
        if ev.description:
            payload["description"] = ev.description
    return payload


def build_payloads(plan: Plan) -> List[Dict[str, Any]]:
    return [event_payload(ev, plan.type) for ev in plan.events]
