"""Build the Claude Desktop extension (.mcpb) for a released version.

    python scripts/build_mcpb.py 0.3.0            # -> dist/intervals-icu-planner-0.3.0.mcpb

Copies mcpb/ to build/mcpb, stamps the version into manifest.json and pins
the PyPI dependency in pyproject.toml to it, then packs it with the mcpb CLI
(needs Node: npx downloads @anthropic-ai/mcpb). Run it after the version is
on PyPI: Claude Desktop installs the package from there.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "mcpb"
PACKAGE = "intervals-icu-planner-mcp"
MCPB_CLI = "@anthropic-ai/mcpb@2"


def stamp(bundle: Path, version: str) -> None:
    """Set the bundle's version and pin the package dependency to it."""
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["version"] = version
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    pyproject_path = bundle / "pyproject.toml"
    text = pyproject_path.read_text(encoding="utf-8")
    pinned, n = re.subn(rf'"{PACKAGE}"', f'"{PACKAGE}=={version}"', text)
    if n != 1:
        raise SystemExit(f"expected one {PACKAGE!r} dependency in {pyproject_path}")
    pyproject_path.write_text(pinned, encoding="utf-8")


def build(version: str) -> Path:
    staging = ROOT / "build" / "mcpb"
    shutil.rmtree(staging, ignore_errors=True)
    shutil.copytree(SOURCE, staging)
    stamp(staging, version)
    out = ROOT / "dist" / f"intervals-icu-planner-{version}.mcpb"
    out.parent.mkdir(exist_ok=True)
    subprocess.run(["npx", "-y", MCPB_CLI, "pack", str(staging), str(out)], check=True)
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2 or not re.fullmatch(r"\d+\.\d+\.\d+\S*", sys.argv[1]):
        raise SystemExit("usage: python scripts/build_mcpb.py <version, e.g. 0.3.0>")
    print(build(sys.argv[1]))
