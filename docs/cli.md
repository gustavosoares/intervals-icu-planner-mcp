# CLI

[← Back to README](../README.md)

The same core works without MCP, from the command line:

```sh
pip install git+https://github.com/gustavosoares/intervals-icu-planner-mcp
export INTERVALS_ICU_API_KEY=your-key-here      # or put it in .env

intervals-icu-planner push plan.yaml                       # dry run: prints the diff
intervals-icu-planner push plan.yaml --start 2027-01-04    # shift the plan
intervals-icu-planner push plan.yaml --apply               # write it
intervals-icu-planner push plan.yaml --prune --apply       # write it and delete removed sessions

intervals-icu-planner planned 2026-12-01 2026-12-31 [--plan-id winterbase]
intervals-icu-planner delete winterbase                    # dry run: lists what would go
intervals-icu-planner delete winterbase --apply
intervals-icu-planner fitness 2026-11-01 2026-11-30
intervals-icu-planner activities 2026-11-01 2026-11-30
intervals-icu-planner move plan.yaml 3 tue fri             # dry run: plan.yaml + calendar diff
intervals-icu-planner move plan.yaml 3 tue wed --swap --apply
intervals-icu-planner shift plan.yaml --weeks 1            # dry run: push the rest back a week
intervals-icu-planner library [--folder winter]            # list the workout library
intervals-icu-planner schema                               # print the plan.yaml JSON Schema
```

Every write command is a dry run unless you pass `--apply`.

`push` works without an API key as an offline dry run (the calendar isn't
checked, so everything shows as new). That's a quick way to validate a plan
and its workouts.

Exit codes: 0 ok, 1 API error, 2 invalid input or missing key.
