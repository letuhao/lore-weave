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
# `#3a1f1c` (canon --destructive-muted) was a row here and CAN NEVER BE
# CONSULTED: this dict is only read for a colour that already passed
# `is_destructive_red`, and the muted brown fails that gate on both saturation
# (~0.35 < 0.40) and lightness (~0.17). An exemption for something the rule can
# never flag is `NV-1` — a row that reads as coverage and does nothing. Removed;
# the shrink arm below now refuses to let one back in.
ALLOWED_REDS: dict[str, str] = {
    "#d9584f": "canon --destructive",
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


def check(drafts=None, repo=None, allowed_reds=None) -> int:
    """The REAL checker, parameterised so `--self-test` can drive it over a
    synthetic drafts directory instead of re-implementing its rules."""
    drafts = DRAFTS if drafts is None else pathlib.Path(drafts)
    repo = REPO if repo is None else pathlib.Path(repo)
    allowed_reds = ALLOWED_REDS if allowed_reds is None else allowed_reds

    # Message refinement, not detection: a missing directory globs to zero
    # files, so the empty-corpus floor below reds anyway. Kept because
    # "the directory moved" and "the directory is empty" are different
    # problems. A bite arm on it came back green.
    if not drafts.is_dir():
        # NOT "nothing to check". This gate exists because a prose audit declared
        # 24 files normalized when they were not; a missing directory that reports
        # OK is the same failure with fewer steps.
        print(f"design-draft-token-lint: ERROR — {drafts} is not a directory. A rule with no "
              f"corpus is not a clean corpus.", file=sys.stderr)
        return 2

    files = sorted(drafts.glob("*.html"))
    if not files:
        print(f"design-draft-token-lint: ERROR — 0 .html draft(s) under {drafts}. "
              f"Zero violations across zero files is not compliance (BDR-82).",
              file=sys.stderr)
        return 2

    violations: list[str] = []
    reds_seen: set[str] = set()

    for path in files:
        try:
            rel = path.relative_to(repo).as_posix()
        except ValueError:
            rel = path.name
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
                if not is_destructive_red(*_rgb(h)):
                    continue
                reds_seen.add(h)
                if h not in allowed_reds:
                    violations.append(
                        f"{rel}:{lineno}: RULE 2 — non-canon destructive red `{m}`.\n"
                        f"    Canon is {CANON_DESTRUCTIVE} (+ {CANON_DESTRUCTIVE_MUTED} muted). "
                        f"Use var(--destructive), not a raw hex.\n"
                        f"    | {line.strip()[:100]}"
                    )
            for r, g, b in RGBA_RE.findall(line):
                r, g, b = int(r), int(g), int(b)
                as_hex = f"#{r:02x}{g:02x}{b:02x}"
                if not is_destructive_red(r, g, b):
                    continue
                reds_seen.add(as_hex)
                if as_hex not in allowed_reds:
                    violations.append(
                        f"{rel}:{lineno}: RULE 2 — non-canon destructive red "
                        f"`rgba({r},{g},{b},…)` (== {as_hex}).\n"
                        f"    Canon is {CANON_DESTRUCTIVE} ⇒ rgba(217,88,79,…).\n"
                        f"    | {line.strip()[:100]}"
                    )

    # ── SUBJECT FLOOR (GT-F3). RULE 2's whole claim is "every destructive red in
    # these drafts is canon". If the drafts contain NO destructive red at all —
    # a restyle, a moved corpus, a hue gate that stopped matching — that sentence
    # is true of nothing, and it reads exactly like success.
    if not reds_seen:
        print(f"design-draft-token-lint: ERROR — {len(files)} draft(s) scanned and NOT ONE "
              f"contains a destructive-signal red, not even the canon token. RULE 2 has no "
              f"subject, so its silence proves nothing.", file=sys.stderr)
        return 2

    # ── SHRINK ARM (GT-F5). An ALLOWED_REDS row is an exemption with a written
    # reason; a row matching no red in the corpus exempts nothing and stands ready
    # to exempt whatever takes that value next. The header is emphatic that adding
    # a row is "a deliberate act" — so is keeping a dead one.
    for h, reason in sorted(allowed_reds.items()):
        # Death 1 — UNREACHABLE. A MESSAGE REFINEMENT, not a distinct finding:
        # a non-red row can never be in `reds_seen` either, so death 2 catches
        # it regardless. It stays because "can never be consulted" tells the
        # reader something "expired" does not. A bite arm on it came back green. This dict is consulted only for colours that
        # already passed `is_destructive_red`, so a row that is not itself a
        # destructive red can never be read. `#3a1f1c` was exactly this.
        if not is_destructive_red(*_rgb(h)):
            violations.append(
                f"ALLOWED_REDS[{h}] is not a destructive red by the hue gate, so it can never "
                f"be consulted — the rule only reads this dict for colours it has already "
                f"flagged. Reason on file: {reason!r}. Delete the row."
            )
            continue
        # Death 2 — EXPIRED. It could be consulted, but nothing in the corpus
        # takes that value any more.
        if h not in reds_seen:
            violations.append(
                f"ALLOWED_REDS[{h}] matches no destructive red in the drafts — its reason "
                f"({reason!r}) has expired. Delete the row, or fix the value."
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

    print(f"design-draft-token-lint: OK — {len(files)} studio drafts, 0 token violations "
          f"({len(reds_seen)} distinct destructive red(s), all canon).")
    return 0


# ── SELF-TEST ────────────────────────────────────────────────────────────────
CANON_HTML = (":root { --destructive: #d9584f; --destructive-muted: #3a1f1c; "
              "--warning: #e8a832; }\n")


def self_test() -> int:
    import contextlib
    import io
    import tempfile

    failures = 0

    def probe(name: str, want: int, files: dict[str, str], *, allowed=None,
              seed: bool = True, no_dir: bool = False) -> None:
        nonlocal failures
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            drafts = root / "design-drafts" / "screens" / "studio"
            if not no_dir:
                drafts.mkdir(parents=True, exist_ok=True)
                if seed:
                    files = {"canon.html": CANON_HTML, **files}
                for rel, body in files.items():
                    (drafts / rel).write_text(body, encoding="utf-8")
            try:
                with contextlib.redirect_stdout(io.StringIO()), \
                        contextlib.redirect_stderr(io.StringIO()):
                    got = check(drafts, root,
                                ALLOWED_REDS if allowed is None else allowed)
            except Exception as e:  # noqa: BLE001
                failures += 1
                print(f"  FAIL {name}: raised {type(e).__name__}: {e}")
                return
        ok = got == want
        failures += 0 if ok else 1
        print(f"  {'ok  ' if ok else 'FAIL'} {name}: rc={got} (want {want})")

    print("design-draft-token-lint --self-test")

    probe("the canon template passes", 0, {})

    # RULE 1 — the name IS the bug
    for alias in ("--danger", "--error", "--warn", "--critical", "--fail-bg"):
        probe(f"RULE 1: `{alias}` is banned", 1, {"x.html": f":root {{ {alias}: #d9584f; }}\n"})
    probe("...but --destructive-muted is allowed", 0, {
        "x.html": ":root { --destructive-muted: #3a1f1c; }\n"})
    probe("...and --warning-muted is allowed", 0, {
        "x.html": ":root { --warning-muted: #d9584f; }\n"})

    # RULE 2 — by hue, not by a known-bad list
    probe("RULE 2: a NEW drift red nobody listed fails", 1, {
        "x.html": ".e { color: #e85a5a; }\n"})
    probe("...and another one", 1, {"x.html": ".e { color: #ef5350; }\n"})
    probe("...including the rgba() form", 1, {
        "x.html": ".e { color: rgba(232, 90, 90, .4); }\n"})
    probe("...and a 3-digit hex", 1, {"x.html": ".e { color: #e55; }\n"})

    # …and the colors that must NOT trip it
    probe("...but the amber warning does not", 0, {"x.html": ".w { color: #e8a832; }\n"})
    probe("...nor the peach lane-b", 0, {"x.html": ".w { color: #e8b87e; }\n"})
    probe("...nor a pale decorative pink", 0, {"x.html": ".p { color: #f2c6c6; }\n"})
    probe("...nor a green", 0, {"x.html": ".g { color: #4fd97a; }\n"})
    probe("...nor a blue", 0, {"x.html": ".b { color: #4f7fd9; }\n"})

    # the shrink arm
    probe("an ALLOWED_REDS row matching nothing fails (expired)", 1, {},
          allowed={**ALLOWED_REDS, "#c04040": "a red nothing uses"})
    probe("an ALLOWED_REDS row that is not even red fails (unreachable)", 1, {},
          allowed={**ALLOWED_REDS, "#3a1f1c": "the muted brown the hue gate never flags"})

    # floors
    probe("a MISSING drafts directory is misuse, not a pass", 2, {}, no_dir=True)
    probe("an EMPTY drafts directory is misuse, not a pass", 2, {}, seed=False)
    probe("drafts with NO destructive red at all is misuse", 2, {
        "x.html": ".g { color: #4fd97a; }\n"}, seed=False,
        allowed={})

    if failures:
        print(f"design-draft-token-lint --self-test: {failures} rule(s) did not behave")
        return 2
    print("design-draft-token-lint --self-test: every rule bites, and none cries wolf")
    return 0


def main() -> int:
    if "--self-test" in sys.argv or "--selftest" in sys.argv:
        return self_test()
    rc = self_test()
    if rc:
        return rc
    print()
    return check()


if __name__ == "__main__":
    sys.exit(main())
