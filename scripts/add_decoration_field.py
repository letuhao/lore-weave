#!/usr/bin/env python3
"""Insert `decoration_density: None,` after every `world_zone: ...,` line
in tilemap-service source AND test files.

**ONE-SHOT TOOL** — designed for the TMP-Q1 chunk-A migration only. Safe
to re-run (idempotency check window is 200 chars) but not a maintenance
tool. After chunk A merges, this script's job is done. New struct
literals in chunks B/C/D should declare the field directly.

Handles both single-line (`world_zone: None,`) and multi-line
(`world_zone: Some(WorldZoneSnapshot { ... }),`) forms by scanning for the
trailing `,` at top-level brace depth.

Run from repo root: python3 scripts/add_decoration_field.py
"""

import re
import subprocess
from pathlib import Path

repo = Path(__file__).resolve().parent.parent
search_roots = [
    repo / "services" / "tilemap-service" / "src",
    repo / "services" / "tilemap-service" / "tests",
]


def find_files() -> list[Path]:
    files: list[Path] = []
    for root in search_roots:
        result = subprocess.run(
            ["grep", "-rlE", r"world_zone:", str(root)],
            capture_output=True, text=True,
        )
        files.extend(Path(p) for p in result.stdout.splitlines() if p)
    return files


def insert_after_world_zone(text: str) -> tuple[str, int]:
    """Find every `world_zone:` field-init in a struct literal and append
    `decoration_density: None,` after it. Works for both single-line and
    multi-line value spans.
    """
    out = []
    i = 0
    n = len(text)
    inserts = 0
    while i < n:
        # Find next `world_zone:` token at start of a line (allowing whitespace).
        m = re.search(r"(?m)^(?P<indent>\s*)world_zone:\s*", text[i:])
        if not m:
            out.append(text[i:])
            break
        start_match = i + m.start()
        out.append(text[i:start_match])
        indent = m.group("indent")
        # Cursor right after "world_zone: "
        cursor = i + m.end()
        # Walk forward respecting brace + paren depth to find the field's
        # closing ',' at the same nesting level (depth 0 wrt this field).
        depth_paren = 0
        depth_brace = 0
        in_str = False
        str_char = ""
        end = cursor
        while end < n:
            ch = text[end]
            if in_str:
                if ch == "\\":
                    end += 2
                    continue
                if ch == str_char:
                    in_str = False
                end += 1
                continue
            if ch in ('"', "'"):
                in_str = True
                str_char = ch
                end += 1
                continue
            if ch == "(":
                depth_paren += 1
            elif ch == ")":
                depth_paren -= 1
            elif ch == "{":
                depth_brace += 1
            elif ch == "}":
                if depth_brace == 0:
                    # End of containing struct literal — no comma here.
                    break
                depth_brace -= 1
            elif ch == "," and depth_paren == 0 and depth_brace == 0:
                # This is the field-terminating comma.
                end += 1
                break
            end += 1
        # Emit the world_zone field through its terminating ','.
        out.append(text[start_match:end])
        # Skip if already followed by decoration_density (idempotent).
        # LOW-4 fix: 200-char window tolerates long comments between
        # the two field-inits without inserting duplicates.
        tail = text[end:end + 200]
        if "decoration_density" not in tail:
            out.append(f"\n{indent}decoration_density: None,")
            inserts += 1
        i = end
    return "".join(out), inserts


def main() -> None:
    total = 0
    for path in find_files():
        text = path.read_text(encoding="utf-8")
        new_text, n = insert_after_world_zone(text)
        if n:
            path.write_text(new_text, encoding="utf-8")
        rel = path.relative_to(repo)
        print(f"{rel}: {n} insertion(s)")
        total += n
    print(f"\nTotal: {total} insertion(s)")


if __name__ == "__main__":
    main()
