"""Command line: push.py PLAN [--dry-run] [--start YYYY-MM-DD] [--delete]"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from typing import Any, Dict, List, Optional

from . import __version__
from .client import ApiError, Client
from .config import ENV_VAR, find_api_key
from .events import build_payloads
from .plan import Plan, PlanError, load_plan


def _date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not a YYYY-MM-DD date") from None


def parse_args(argv: Optional[List[str]]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="intervals-icu-planner-mcp",
        description="Push a multi-week plan of .zwo workouts to your intervals.icu calendar.",
    )
    ap.add_argument("plan", help="path to plan.yaml")
    ap.add_argument("--dry-run", action="store_true", help="print the schedule, send nothing")
    ap.add_argument("--start", type=_date, help="Monday of week 1 (overrides the plan's start)")
    ap.add_argument("--delete", action="store_true",
                    help="remove this plan's events from the calendar instead of pushing")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return ap.parse_args(argv)


def print_schedule(plan: Plan) -> None:
    print(f"{plan.name}: {plan.weeks} weeks, {plan.start} -> {plan.end}\n")
    week = None
    for ev in plan.events:
        if ev.week != week:
            if week is not None:
                print()
            week = ev.week
        what = ev.workout.filename if ev.workout else ev.name
        print(f"  {ev.date}  {ev.date:%a}  {ev.category:<7}  {what:<38}  {ev.uid}")
    n_workouts = sum(1 for e in plan.events if e.category == "WORKOUT")
    print(f"\n{len(plan.events)} events ({n_workouts} workouts, "
          f"{len(plan.events) - n_workouts} notes)")


def matching_ids(plan: Plan, existing: List[Dict[str, Any]]) -> List[int]:
    prefix = plan.uid_prefix
    ids = []
    for e in existing:
        tag = e.get("external_id") or e.get("uid") or ""
        if tag.startswith(prefix) and e.get("id") is not None:
            ids.append(e["id"])
    return ids


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    try:
        plan = load_plan(args.plan, start=args.start)
    except PlanError as e:
        print(f"Invalid plan {args.plan}:\n{e}", file=sys.stderr)
        return 2

    print_schedule(plan)

    if args.dry_run:
        if args.delete:
            print(f"\nDry run: would delete events with uid '{plan.uid_prefix}*' "
                  f"between {plan.start} and {plan.end}.")
        else:
            print("\nDry run: nothing sent.")
        return 0

    api_key = find_api_key()
    if not api_key:
        print(f"\nMissing API key: set {ENV_VAR} or put it in a .env file "
              "(intervals.icu -> Settings -> Developer Settings).", file=sys.stderr)
        return 2
    client = Client(api_key)

    try:
        if args.delete:
            ids = matching_ids(plan, client.list_events(plan.start, plan.end))
            if not ids:
                print(f"\nNo events with uid '{plan.uid_prefix}*' found between "
                      f"{plan.start} and {plan.end}.")
                return 0
            print(f"\nDeleted {client.delete_events(ids)} events.")
        else:
            res = client.upsert_events(build_payloads(plan))
            print(f"\nUpserted {len(res)} events to intervals.icu.")
    except ApiError as e:
        print(f"\n{e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
