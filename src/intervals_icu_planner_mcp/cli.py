"""Command line front end, for people who don't use MCP. Same core as the server.

intervals-icu-planner push plan.yaml [--start YYYY-MM-DD] [--apply]
intervals-icu-planner delete PLAN_ID [--oldest D] [--newest D] [--apply]
intervals-icu-planner planned OLDEST NEWEST [--plan-id ID]
intervals-icu-planner fitness OLDEST NEWEST
intervals-icu-planner activities OLDEST NEWEST
intervals-icu-planner schema
"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__, planner
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

    sub.add_parser("schema", help="print the plan.yaml JSON Schema")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "schema":
        print(json.dumps(plan_json_schema(), indent=2))
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
                apply_hint="--apply",
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
