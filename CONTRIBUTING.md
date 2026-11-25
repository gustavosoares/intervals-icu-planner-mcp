# Contributing

Thanks for helping. Issues and pull requests are welcome.

## Setup

```sh
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
```

## Before opening a PR

```sh
ruff check . && ruff format --check .
mypy
pytest
```

CI runs the same checks on Python 3.10 to 3.13.

## Ground rules

- **Keep the safety rules intact** (see [docs/safety.md](docs/safety.md)). Write
  operations default to a dry run, and the code only ever modifies events
  whose uid fully matches `planner-<plan_id>-w<NN>-<day>`. A change to either
  of these needs tests that show it still holds.
- **Tests never use the network.** Mock HTTP with
  [respx](https://lundberg.github.io/respx/), and never commit API keys,
  athlete ids or personal data. That includes example plans: use % of FTP,
  not watts.
- **Keep the layers separate.** `client.py` knows nothing about MCP or plans,
  and `planner.py` holds the operations. `server.py` and `cli.py` are thin
  front ends over it.
- **If you change the plan models in `plan.py`**, regenerate the schema:
  `intervals-icu-planner schema > schemas/plan.schema.json`.
- Add a line to `CHANGELOG.md` under the next version.
