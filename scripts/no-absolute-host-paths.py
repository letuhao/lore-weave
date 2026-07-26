#!/usr/bin/env python3
"""Gate: no ABSOLUTE HOST PATH may be hardcoded in committed code.

WHY. A path like ``D:/Works/source/lore-weave-mvp/...`` resolves on exactly one machine.
Everywhere else the script dies, or — worse — the path happens to exist and it silently
reads a STALE COPY from a sibling checkout. That is not hypothetical here: four POC
exporters pointed at `lore-weave-mvp`, a different repo, and an `add_mining_i18n.py`
rewrote i18n files through `d:/Works/source/lore-weave/...` — correct only from one
checkout, on one drive letter, for one developer.

The repo already knows the portable pattern: `gen-prop-bundle.py` derived its OUTPUT via
`Path(__file__).resolve().parents[1]` while hardcoding its INPUT. The pattern was there;
nothing enforced it.

THE RULE
  * A path INSIDE the repo → derive it from ``__file__``.
  * A path OUTSIDE the repo (another service's output, a crawled corpus) → read an env var
    with the old value as the default, and FAIL LOUDLY when it is missing. A silent wrong
    path is the failure mode this gate exists to kill.

Run: ``python scripts/no-absolute-host-paths.py``. Wired as a pre-commit hook alongside the
other gates (ai-provider-gate.py, db-safety-gate.py).
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

# A Windows drive path or a POSIX /home|/Users path used as a STRING LITERAL.
_PATTERN = re.compile(
    r"""['"]\s*[A-Za-z]:[\\/](?:Works|Users|home)[\\/]"""   # C:/Users/…, D:\Works\…
    r"""|['"]/(?:home|Users)/[A-Za-z0-9_.-]+/""",            # /home/me/…, /Users/me/…
)

_EXTS = {".py", ".ts", ".tsx", ".js", ".go", ".sh", ".yml", ".yaml", ".toml", ".json"}
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".claude", "dist", "build",
              ".venv", "venv", ".mypy_cache", ".pytest_cache", "coverage"}

# Lines that legitimately mention such a path: env-var DEFAULTS (the sanctioned escape
# hatch — the value is overridable and its absence fails loudly), and this gate's own
# pattern/docs. Add a row only with a reason; never to silence a real finding.
_ALLOW = re.compile(
    r"os\.environ\.get\(|getenv\(|process\.env|# *no-absolute-host-paths: ok"
)


def offenders() -> list[tuple[pathlib.Path, int, str]]:
    out: list[tuple[pathlib.Path, int, str]] = []
    for path in ROOT.rglob("*"):
        if path.suffix not in _EXTS or not path.is_file():
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if path.resolve() == pathlib.Path(__file__).resolve():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        lines = text.splitlines()
        for i, line in enumerate(lines, 1):
            if not _PATTERN.search(line):
                continue
            stripped = line.strip()
            # A path inside a COMMENT is documentation (often this rule's own example),
            # not a value the code uses.
            if stripped.startswith(("#", "//", "*")):
                continue
            # The env-var call may open several lines ABOVE the default value it wraps, so
            # look back a short window rather than at this line alone.
            window = chr(10).join(lines[max(0, i - 4):i])
            if _ALLOW.search(window):
                continue
            out.append((path.relative_to(ROOT), i, stripped[:120]))
    return out


def main() -> int:
    bad = offenders()
    if not bad:
        print("no-absolute-host-paths: clean")
        return 0
    print(f"no-absolute-host-paths: {len(bad)} hardcoded host path(s)\n")
    for rel, line_no, line in bad:
        print(f"  {rel}:{line_no}\n      {line}")
    print(
        "\nA hardcoded host path works on ONE machine and silently reads a stale sibling "
        "checkout everywhere else.\n"
        "  in-repo target  -> derive it from __file__\n"
        "  external target -> os.environ.get(VAR, <default>) AND fail loudly when absent"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
