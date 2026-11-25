"""Command line front end, for people who don't use MCP. Same core as the server.

intervals-icu-planner push plan.yaml [--start YYYY-MM-DD] [--prune] [--apply]
intervals-icu-planner delete PLAN_ID [--oldest D] [--newest D] [--apply]
intervals-icu-planner planned OLDEST NEWEST [--plan-id ID]
intervals-icu-planner fitness OLDEST NEWEST
intervals-icu-planner activities OLDEST NEWEST
intervals-icu-planner move plan.yaml WEEK DAY TO_DAY [--to-week N] [--swap] [--apply]
intervals-icu-planner shift plan.yaml [--weeks N] [--from-week N] [--apply]
intervals-icu-planner library [--folder NAME]
intervals-icu-planner schema
intervals-icu-planner guide
"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__, guide, planner
from .client import ApiError, IntervalsClient
from .config import find_api_key
from .plan import PlanError, plan_json_schema

EXIT_OK, EXIT_API, EXIT_INPUT = 0, 1, 2


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="intervals-icu-planner",
        description="Push, inspect and remove whole training plans on intervals.icu. "
        "Write commands are dry runs unless you pass --apply.",
    )
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("push", help="push a plan.yaml (dry run unless --apply)")
    p.add_argument("plan", help="path to plan.yaml")
    p.add_argument("--start", help="Monday of week 1, YYYY-MM-DD (overrides the plan's start)")
    p.add_argument("--apply", action="store_true", help="write to the calendar")
    p.add_argument(
        "--prune",
        action="store_true",
        help="also delete this plan's stale events (from today on; past ones are kept)",
    )

    d = sub.add_parser("delete", help="remove a plan's events (dry run unless --apply)")
    d.add_argument("plan_id", help="the plan's id")
    d.add_argument("--oldest", help="first day to search (default: a year ago)")
    d.add_argument("--newest", help="last day to search (default: two years ahead)")
    d.add_argument("--apply", action="store_true", help="really delete")

    g = sub.add_parser("planned", help="list planned events")
    g.add_argument("oldest")
    g.add_argument("newest")
    g.add_argument("--plan-id", help="only events created by this plan")

    f = sub.add_parser("fitness", help="CTL / ATL / Form per day")
    f.add_argument("oldest")
    f.add_argument("newest")

    a = sub.add_parser("activities", help="completed activities")
    a.add_argument("oldest")
    a.add_argument("newest")

    m = sub.add_parser("move", help="move one session to another day (dry run unless --apply)")
    m.add_argument("plan", help="path to plan.yaml")
    m.add_argument("week", type=int, help="plan week of the session (1 = first)")
    m.add_argument("day", help="day of the session (mon..sun)")
    m.add_argument("to_day", help="day to move it to")
    m.add_argument("--to-week", type=int, help="week to move it to (default: same week)")
    m.add_argument("--swap", action="store_true", help="trade places if the day is taken")
    m.add_argument("--apply", action="store_true", help="write plan.yaml and the calendar")

    s = sub.add_parser("shift", help="push the rest of the plan back (dry run unless --apply)")
    s.add_argument("plan", help="path to plan.yaml")
    s.add_argument("--weeks", type=int, default=1, help="weeks to push back (default: 1)")
    s.add_argument("--from-week", type=int, help="first week to move (default: current week)")
    s.add_argument("--apply", action="store_true", help="write plan.yaml and the calendar")

    lib = sub.add_parser("library", help="list the workout library (read-only)")
    lib.add_argument("--folder", help="only folders whose name contains this")

    sub.add_parser("schema", help="print the plan.yaml JSON Schema")
    sub.add_parser("guide", help="print how to write a plan.yaml and its .zwo workouts")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "schema":
        print(json.dumps(plan_json_schema(), indent=2))
        return EXIT_OK
    if args.command == "guide":
        print(guide.plan_guide(), end="")
        return EXIT_OK

    key = find_api_key()
    client = IntervalsClient.from_api_key(key) if key else None
    try:
        if args.command == "push":
            out = planner.push(
                args.plan,
                client=client,
                start=args.start,
                dry_run=not args.apply,
                prune=args.prune,
                apply_hint="--apply",
                prune_hint="--prune",
            )
        elif args.command == "delete":
            out = planner.delete(
                args.plan_id,
                client=client,
                dry_run=not args.apply,
                oldest=args.oldest,
                newest=args.newest,
                apply_hint="--apply",
            )
        elif args.command == "planned":
            out = planner.planned(args.oldest, args.newest, client=client, plan_id=args.plan_id)
        elif args.command == "fitness":
            out = planner.fitness(args.oldest, args.newest, client=client)
        elif args.command == "move":
            out = planner.move(
                args.plan,
                args.week,
                args.day,
                args.to_day,
                client=client,
                to_week=args.to_week,
                swap=args.swap,
                dry_run=not args.apply,
                apply_hint="--apply",
            )
        elif args.command == "shift":
            out = planner.shift(
                args.plan,
                client=client,
                weeks=args.weeks,
                from_week=args.from_week,
                dry_run=not args.apply,
                apply_hint="--apply",
            )
        elif args.command == "library":
            out = planner.library(client=client, folder=args.folder)
        else:
            out = planner.activities(args.oldest, args.newest, client=client)
    except PlanError as e:
        print(f"Invalid plan:\n{e}", file=sys.stderr)
        return EXIT_INPUT
    except planner.PlannerError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_INPUT
    except ApiError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_API
    finally:
        if client is not None:
            client.close()
    print(out)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
