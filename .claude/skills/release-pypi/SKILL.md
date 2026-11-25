---
name: release-pypi
description: Release a new version of intervals-icu-planner-mcp to PyPI. Proposes the version from the changelog, opens the changelog PR, runs the publish workflow on TestPyPI and then PyPI, and checks each upload. Only the maintainer starts it, with /release-pypi [version].
disable-model-invocation: true
---

# Release to PyPI

Walk the maintainer through one release, as described in CONTRIBUTING.md →
Releasing. You do the mechanical steps; the maintainer makes every decision
that matters.

**Never:**
- approve a deployment (not in the UI, not through the API): the approval gate
  on the `pypi` / `testpypi` environments is the maintainer's;
- merge a PR;
- release from anything but an up-to-date `main`;
- edit a version into `pyproject.toml` or `__init__.py` (it comes from the git
  tag via hatch-vcs);
- re-run a failed PyPI upload with a different version without asking.

If a step fails, stop, show the error (for a workflow: `gh run view <id>
--log-failed`), and ask. The shell is zsh: quote variables, and use arrays
rather than space-separated strings.

## 1. Check the starting point

```sh
git checkout main && git pull --ff-only && git status --short
git fetch --tags && git describe --tags --abbrev=0     # the last release, e.g. v0.1.0
grep -n 'version:' .github/workflows/publish.yml        # the workflow takes a version input
```

Stop if the tree isn't clean, or if `## [Unreleased]` in CHANGELOG.md is
empty: there's nothing to release.

## 2. Pick the version

Read the Unreleased section and propose the next version from it, with a
one-line reason (semver, while we're on 0.x):

- only fixes and docs → patch (0.1.0 → 0.1.1);
- a new tool, option or behaviour, or anything incompatible → minor
  (0.1.0 → 0.2.0).

If the maintainer passed a version as the argument, use that one, and say if
it doesn't fit the changes. Confirm the number with AskUserQuestion before
going on. It must be a plain version (`0.2.0`, or `0.2.0rc1` for a
pre-release), with no `v`.

## 3. Changelog PR

On a branch `release-<version>`, edit CHANGELOG.md:

- rename `## [Unreleased]` to `## [<version>] - <today, YYYY-MM-DD>`;
- add an empty `## [Unreleased]` above it;
- at the bottom, set `[Unreleased]: .../compare/v<version>...HEAD` and add
  `[<version>]: .../compare/v<previous>...v<version>` above the older links.

Show the diff. Commit as `Release <version>` (with this session's attribution
trailer), push, and open the PR with `gh pr create`: title `Release
<version>`, body = the new changelog section. Give the maintainer the link
and **stop until they say it's merged**. Then:

```sh
git checkout main && git pull --ff-only
grep -n "^## \[<version>\]" CHANGELOG.md    # must be on main now
```

## 4. TestPyPI

```sh
gh workflow run publish.yml --ref main -f version=<version> -f target=testpypi
sleep 5; gh run list --workflow publish.yml -L 1 --json databaseId,url
```

Poll every ~15 s (`gh run view <id> --json status,jobs`) until the run is
`waiting` (the upload needs approval) or `completed`. If the build job
failed, show why and stop. When it's waiting, give the maintainer the run
link ("Review deployments → testpypi → Approve and deploy") and **stop until
they say they've approved**. Then poll until it completes.

Check the upload. TestPyPI has a stale `mcp` 0.8 that breaks
`--index-url` installs, so install the wheel by its URL:

```sh
W=$(curl -s https://test.pypi.org/pypi/intervals-icu-planner-mcp/<version>/json \
  | python3 -c "import json,sys; print([f['url'] for f in json.load(sys.stdin)['urls'] if f['filename'].endswith('.whl')][0])")
FROM=(--refresh --from "intervals-icu-planner-mcp @ $W")
```

Then run the smoke test below with `"${FROM[@]}"`. Also check the
project's JSON: `info.version` is `<version>`, and its `description` has no
relative `](...)` links left. If the page isn't there yet, wait a minute and
retry: the index can lag.

A version number can only be uploaded to TestPyPI once. If this step has to
be repeated, ask the maintainer: either skip TestPyPI, or try `<version>rc1`
there (TestPyPI doesn't need a changelog section).

## 5. PyPI

Ask the maintainer to confirm before starting the real release. Then the same
as TestPyPI with `-f target=pypi`: start the run, poll until it waits, give
the link, **stop until approved**, poll until it completes. The `release`
job should finish too: it tags `v<version>` and creates the GitHub release.

Check it, retrying for a minute or two if PyPI hasn't caught up:

```sh
FROM=(--refresh --from "intervals-icu-planner-mcp==<version>")
gh release view "v<version>" --json tagName,url,isPrerelease
git fetch --tags && git describe --tags --abbrev=0     # v<version>
```

Then run the smoke test with `"${FROM[@]}"`.

## Smoke test

Run it from an empty temporary folder (`cd "$(mktemp -d)"`), never from the
repo, so the installed package is what gets tested, not the source tree.
Leave the API key out, and use a fake one for the server.

```sh
uvx -q "${FROM[@]}" intervals-icu-planner --version
# expect: intervals-icu-planner <version>

env -u INTERVALS_ICU_API_KEY uvx -q "${FROM[@]}" intervals-icu-planner push \
  <repo>/examples/winter-base-12wk/plan.yaml | tail -2
# expect: "60 new, 0 updated, 0 unchanged, 0 stale." and "Dry run: nothing was written."

echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"release-check","version":"0"}}}' \
  | env INTERVALS_ICU_API_KEY=FAKE_KEY uvx -q "${FROM[@]}" intervals-icu-planner-mcp 2>/dev/null | head -c 200
# expect: a JSON-RPC result with "capabilities"
```

## 6. Wrap up

Report the version, the PyPI link
(`https://pypi.org/project/intervals-icu-planner-mcp/<version>/`), the GitHub
release link, and what each check showed. Remind the maintainer that `uvx`
keeps its cached version: run `uvx intervals-icu-planner-mcp@latest` once and
restart Claude Desktop and Claude Code to use the new release.
