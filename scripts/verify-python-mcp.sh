#!/usr/bin/env sh
set -eu

python - <<'PY'
import importlib.metadata as metadata

from mcp.server.fastmcp import Context  # noqa: F401
import loreweave_mcp  # noqa: F401

version = metadata.version("mcp")
if not version.startswith("1."):
    raise SystemExit(f"unsupported mcp version for FastMCP providers: {version}")
print(f"FastMCP dependency check passed: mcp {version}")
PY
