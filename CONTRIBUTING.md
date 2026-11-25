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

## Releasing (maintainer only)

Releases go to PyPI from the manual `publish` workflow, with
[trusted publishing](https://docs.pypi.org/trusted-publishers/) (no token).

One-time setup:

1. On PyPI and TestPyPI, add a pending trusted publisher: project
   `intervals-icu-planner-mcp`, owner `gustavosoares`, repository
   `intervals-icu-planner-mcp`, workflow `publish.yml`, environment `pypi`
   (TestPyPI: `testpypi`).
2. In the repo's Settings → Environments, create `pypi` and `testpypi`, each
   with the maintainer as required reviewer and deployment limited to `main`.

Each release:

1. Bump `version` in `pyproject.toml` and move the changelog's Unreleased
   entries under the new version. Merge that to `main`.
2. Actions → publish → Run workflow on `main` with target `testpypi`, and
   check the page and `uvx --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ intervals-icu-planner-mcp`.
3. Run it again with target `pypi`. It checks, builds, uploads, then tags
   `v<version>` and creates the GitHub release.
