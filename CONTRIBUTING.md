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

Versions come from git tags (`hatch-vcs`): there's no version number in
`pyproject.toml` or the code. Merging a PR never releases anything; a release
is a deliberate, approved run of the `publish` workflow. Pick the number with
[semver](https://semver.org/): a fix is 0.1.1, a new tool or option 0.2.0.

Each release (in Claude Code, `/release-pypi [version]` walks through these
steps, and pauses for you to merge and to approve each upload):

1. Rename the changelog's `## [Unreleased]` heading to `## [0.2.0] - <date>`,
   add a fresh empty Unreleased above it, and merge that to `main`. That
   section becomes the GitHub release notes.
2. Try it on TestPyPI:
   `gh workflow run publish.yml --ref main -f version=0.2.0 -f target=testpypi`,
   then approve the deployment. To install it, use the wheel's URL from the
   TestPyPI page (`uvx --from "intervals-icu-planner-mcp @ <wheel url>" ...`):
   TestPyPI has an old `mcp` that blocks `--index-url` installs. A number can
   only be uploaded to TestPyPI once, so a retry needs a new one (`0.2.0rc2`).
3. Release it: the same command with `-f target=pypi`, and approve. The
   workflow checks the version is new and in the changelog, runs the tests,
   builds with that version, uploads, then tags `v0.2.0` and creates the
   GitHub release, with the Claude Desktop extension
   (`intervals-icu-planner-0.2.0.mcpb`, built by `scripts/build_mcpb.py`)
   attached.
