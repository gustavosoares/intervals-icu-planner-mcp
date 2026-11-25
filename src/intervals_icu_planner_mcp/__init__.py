"""Push, inspect and remove whole training plans on intervals.icu, safely."""

from importlib.metadata import PackageNotFoundError, version

try:
    # Set at build time from the git tag (hatch-vcs); see CONTRIBUTING → Releasing.
    __version__ = version("intervals-icu-planner-mcp")
except PackageNotFoundError:  # running from a source tree that isn't installed
    __version__ = "0.0.0+unknown"
