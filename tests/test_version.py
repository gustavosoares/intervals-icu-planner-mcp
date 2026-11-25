from importlib.metadata import version

import intervals_icu_planner_mcp


def test_version_comes_from_package_metadata():
    """The version is set at build time from the git tag, never hard-coded."""
    assert intervals_icu_planner_mcp.__version__ == version("intervals-icu-planner-mcp")
    assert intervals_icu_planner_mcp.__version__ != "0.0.0+unknown"
