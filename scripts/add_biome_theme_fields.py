#!/usr/bin/env python3
"""Insert `biome_theme: None,` after every `inherit_treasure_from:` line
(ZoneSpec literals) and `background_biome: None,` after every
`decoration_density:` line (TilemapTemplate literals) in tilemap-service
source AND test files.

**ONE-SHOT TOOL** — designed for the TMP-Q2 chunk-A migration only. Safe
to re-run (idempotency check window is 200 chars) but not a maintenance
tool. After chunk A merges, this script's job is done. New struct
literals in chunks B/C should declare the fields directly.

Adapts `scripts/add_decoration_field.py` for the two new fields. Brace-
depth scanning identifies the field's terminating ',' at depth 0 so
nested struct literals don't trip the anchor detection.

Run from repo root: python3 scripts/add_biome_theme_fields.py
"""

import re
import subprocess
from pathlib import Path

repo = Path(__file__).resolve().parent.parent
search_roots = [
    repo / "services" / "tilemap-service" / "src",
    repo / "services" / "tilemap-service" / "tests",
]


def find_files(anchor: str) -> list[Path]:
    files: list[Path] = []
    for root in search_roots:
        result = subprocess.run(
            ["grep", "-rlE", f"{anchor}:", str(root)],
            capture_output=True, text=True,
        )
        files.extend(Path(p) for p in result.stdout.splitlines() if p)
    return files


def insert_after_field(text: str, anchor: str, new_field: str) -> tuple[str, int]:
    """Find every `<anchor>:` field-init and append `<new_field>: None,`
    after it. Walks brace/paren depth so multi-line values are handled.

    Idempotency: before inserting, walks forward to the END of the
    containing struct literal (where `depth_brace` would dip below 0
    relative to the field's position) and scans the entire tail for the
    `<new_field>:` substring. This is more robust than the original
    200-char window inherited from `add_decoration_field.py` — a future
    chunk that introduces a long comment block between the anchor and
    the (already-present) new field can no longer trigger a duplicate
    insertion (COSMETIC-2 fix from chunk-A /review-impl).
    """
    out = []
    i = 0
    n = len(text)
    inserts = 0
    pattern = re.compile(rf"(?m)^(?P<indent>\s*){anchor}:\s*")
    while i < n:
        m = pattern.search(text[i:])
        if not m:
            out.append(text[i:])
            break
        start_match = i + m.start()
        out.append(text[i:start_match])
        indent = m.group("indent")
        cursor = i + m.end()
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
                    break
                depth_brace -= 1
            elif ch == "," and depth_paren == 0 and depth_brace == 0:
                end += 1
                break
            end += 1
        out.append(text[start_match:end])
        # COSMETIC-2 fix — scan to the END of the containing struct
        # literal (depth_brace dropping below 0 from here = closing `}`
        # of the literal) so a duplicate-field check can't be defeated
        # by a long comment splitting the anchor from the (already
        # inserted) new field. Falls back to a 1000-char window if the
        # closing brace is never found (defensive against malformed
        # input).
        scan_end = min(n, end + 1000)
        depth_brace_post = 0
        in_str_post = False
        str_char_post = ""
        p = end
        while p < n:
            ch = text[p]
            if in_str_post:
                if ch == "\\":
                    p += 2
                    continue
                if ch == str_char_post:
                    in_str_post = False
                p += 1
                continue
            if ch in ('"', "'"):
                in_str_post = True
                str_char_post = ch
                p += 1
                continue
            if ch == "{":
                depth_brace_post += 1
            elif ch == "}":
                if depth_brace_post == 0:
                    scan_end = p
                    break
                depth_brace_post -= 1
            p += 1
        tail = text[end:scan_end]
        new_field_marker = f"{new_field}:"
        if new_field_marker not in tail:
            out.append(f"\n{indent}{new_field}: None,")
            inserts += 1
        i = end
    return "".join(out), inserts


def main() -> None:
    total = 0
    # ZoneSpec — biome_theme inserted after inherit_treasure_from.
    for path in find_files("inherit_treasure_from"):
        text = path.read_text(encoding="utf-8")
        new_text, n = insert_after_field(text, "inherit_treasure_from", "biome_theme")
        if n:
            path.write_text(new_text, encoding="utf-8")
        rel = path.relative_to(repo)
        if n:
            print(f"{rel}: {n} biome_theme insertion(s)")
        total += n
    # TilemapTemplate — background_biome inserted after decoration_density.
    for path in find_files("decoration_density"):
        text = path.read_text(encoding="utf-8")
        new_text, n = insert_after_field(text, "decoration_density", "background_biome")
        if n:
            path.write_text(new_text, encoding="utf-8")
        rel = path.relative_to(repo)
        if n:
            print(f"{rel}: {n} background_biome insertion(s)")
        total += n
    print(f"\nTotal: {total} insertion(s)")


if __name__ == "__main__":
    main()
