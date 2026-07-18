#!/usr/bin/env python3
"""design-draft-token-lint — the destructive/warning token guard for the studio mockups.

WHY THIS EXISTS (read before you "simplify" it).
Spec 30 §8.3 audited the destructive red across the 24 studio design drafts, declared it had
"drifted FOUR ways", and pronounced "all 24 files are now normalized". Both claims were FALSE.
**The audit grepped the token NAMES** (`--danger`, `--destructive`) — so it never saw a fifth
drift wearing a THIRD name (`--error: #e85a5a`), nor a raw `#e85a5a` hex with no token at all,
nor a `--warn: #e8b87e` where canon is `--warning: #e8a832`.

    A prose checklist did not stop this drift, and a name-based grep could not SEE it.
    (repo lessons: `checklist-is-self-report-enforce-by-tests`,
                   `css-var-duplicated-across-two-consumers-drifts`,
                   `hygiene-grep-literal-token-in-comment-false-positive`)

So this lint greps by **CONCEPT — the COLOR ITSELF** — not by the token name:

  RULE 1 (names)  A destructive/warning ALIAS custom property is banned outright.
                  Only `--destructive` / `--destructive-muted` / `--warning` / `--warning-muted`
                  may exist. `--danger*`, `--error*`, `--warn` (≠ `--warning`) are drift by
                  construction — the name IS the bug.

  RULE 2 (colors) Any "destructive-signal red" literal — computed from HSL, so it catches a red
                  this script has never seen — must be one of the two canon values. A NEW drift
                  red (#e85a5a, #dc4e4e, #d95d5d, some future #ef5350) trips this even though no
                  rule names it. That is the whole point: RULE 1 alone would have missed the raw
                  hex at screen-studio-agent-gui-bridge.html:74, which had no token at all.

Canon (from the template, design-drafts/screens/studio/screen-issues-feed.html):
    --destructive: #d9584f;  --destructive-muted: #3a1f1c;  --warning: #e8a832;

Usage:  python scripts/design-draft-token-lint.py        # exit 0 = clean, 1 = violations
Wired into the pre-commit hook alongside scripts/ai-provider-gate.py.
"""
from __future__ import annotations

import colorsys
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
DRAFTS = REPO / "design-drafts" / "screens" / "studio"

# ── canon ────────────────────────────────────────────────────────────────────────
CANON_DESTRUCTIVE = "#d9584f"
CANON_DESTRUCTIVE_MUTED = "#3a1f1c"
CANON_WARNING = "#e8a832"

# The only sanctioned destructive/warning custom properties. Anything else in the alias
# family is drift — one concept, one name (DA-10).
ALLOWED_PROPS = {"--destructive", "--destructive-muted", "--warning", "--warning-muted"}
ALIAS_PROP_RE = re.compile(r"--(?:danger|error|warn|destructive|critical|fail)[\w-]*", re.I)

# RULE 2's allowlist: colors that ARE red-ish by the HSL gate but are legitimately NOT the
# destructive token. Each needs a REASON. Adding a row here is a deliberate act — that speed
# bump is the feature. Do not add a row to silence a real drift.
ALLOWED_REDS: dict[str, str] = {
    "#d9584f": "canon --destructive",
    "#3a1f1c": "canon --destructive-muted",
}

HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")
RGBA_RE = re.compile(r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*(?:,[^)]*)?\)")


def _norm_hex(h: str) -> str:
    h = h.lower()
    if len(h) == 4:  # #abc -> #aabbcc
        h = "#" + "".join(c * 2 for c in h[1:])
    return h


def _rgb(h: str) -> tuple[int, int, int]:
    h = _norm_hex(h)
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def is_destructive_red(r: int, g: int, b: int) -> bool:
    """A 'this is wrong' signal red, by HUE — not by a hardcoded list of known bad hexes.

    Catches a drift red nobody has written yet. Deliberately does NOT catch:
      - pale decorative pinks (L > .75, e.g. #f2c6c6 diff-del text),
      - the amber warning (#e8a832, hue ~40) or the peach lane-b (#e8b87e, hue ~30),
      - greens/blues/purples.
    """
    hue, light, sat = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    deg = hue * 360
    is_red_hue = deg >= 340 or deg <= 20
    return is_red_hue and sat >= 0.40 and 0.10 <= light <= 0.75


def main() -> int:
    if not DRAFTS.is_dir():
        print(f"design-draft-token-lint: {DRAFTS} not found — nothing to check.")
        return 0

    violations: list[str] = []

    for path in sorted(DRAFTS.glob("*.html")):
        rel = path.relative_to(REPO).as_posix()
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            # ── RULE 1 — a destructive/warning alias custom property ──────────────
            for prop in ALIAS_PROP_RE.findall(line):
                if prop.lower() not in ALLOWED_PROPS:
                    violations.append(
                        f"{rel}:{lineno}: RULE 1 — banned alias custom property `{prop}`.\n"
                        f"    One concept, one name. Use --destructive / --destructive-muted "
                        f"/ --warning / --warning-muted.\n"
                        f"    | {line.strip()[:100]}"
                    )

            # ── RULE 2 — a destructive-signal red that is not canon ───────────────
            seen: set[str] = set()
            for m in HEX_RE.findall(line):
                h = _norm_hex(m)
                if h in seen:
                    continue
                seen.add(h)
                if is_destructive_red(*_rgb(h)) and h not in ALLOWED_REDS:
                    violations.append(
                        f"{rel}:{lineno}: RULE 2 — non-canon destructive red `{m}`.\n"
                        f"    Canon is {CANON_DESTRUCTIVE} (+ {CANON_DESTRUCTIVE_MUTED} muted). "
                        f"Use var(--destructive), not a raw hex.\n"
                        f"    | {line.strip()[:100]}"
                    )
            for r, g, b in RGBA_RE.findall(line):
                r, g, b = int(r), int(g), int(b)
                as_hex = f"#{r:02x}{g:02x}{b:02x}"
                if is_destructive_red(r, g, b) and as_hex not in ALLOWED_REDS:
                    violations.append(
                        f"{rel}:{lineno}: RULE 2 — non-canon destructive red "
                        f"`rgba({r},{g},{b},…)` (== {as_hex}).\n"
                        f"    Canon is {CANON_DESTRUCTIVE} ⇒ rgba(217,88,79,…).\n"
                        f"    | {line.strip()[:100]}"
                    )

    if violations:
        print("design-draft-token-lint: FAIL — destructive/warning token drift\n")
        for v in violations:
            print(v)
        print(f"\n{len(violations)} violation(s). Canon: "
              f"--destructive: {CANON_DESTRUCTIVE}; --destructive-muted: {CANON_DESTRUCTIVE_MUTED}; "
              f"--warning: {CANON_WARNING}")
        print("Template: design-drafts/screens/studio/screen-issues-feed.html")
        return 1

    n = len(list(DRAFTS.glob("*.html")))
    print(f"design-draft-token-lint: OK — {n} studio drafts, 0 token violations.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
