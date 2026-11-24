#!/usr/bin/env python3
"""Run intervals-icu-planner-mcp from a checkout: python push.py plan.yaml --dry-run"""

import sys

from intervals_icu_planner_mcp.cli import main

if __name__ == "__main__":
    sys.exit(main())
