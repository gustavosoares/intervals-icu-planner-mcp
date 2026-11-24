#!/usr/bin/env python3
"""Run zwo-plan-pusher from a checkout: python push.py plan.yaml --dry-run"""

import sys

from zwo_plan_pusher.cli import main

if __name__ == "__main__":
    sys.exit(main())
