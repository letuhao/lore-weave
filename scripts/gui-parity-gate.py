#!/usr/bin/env python3
"""gui-parity-gate.py — a capability the agent can attempt but a human cannot do by hand is not shipped.

Owner, 2026-09-04: *"FE should have ability to help user fix llm weakness by edit manually on gui,
so we avoid to ship feature that user cannot use and agent is dumb."* When the model fails — and
this month measured three separate ways it loses an author's chapter — the user must be able to
finish the job by hand. A capability reachable ONLY through an unreliable agent does not work.

🔴 THE DEFECT THIS GENERALISES. LOOM M9 shipped a gate that disabled Publish until every
composition scene was `status='done'` — and the FE had **no control to mark a scene done**. The
backend was correct, the units passed, and the live smoke went green because it PATCHed the status
via curl. Every composition-enabled book got a permanently-disabled Publish button.

── WHY THIS GATE VERIFIES DECLARATIONS AND DOES NOT DISCOVER THEM ───────────────────────────
P1 tried three automatic matchers to derive parity from tool names, and a known-positive control
(tools driven through the UI by hand) refuted all three:

    endpoint-name overlap      25/118   missed `book_update_details`
    symbol + endpoint tokens   48/118   missed 2 of 4 controls
    loose keyword on testids  115/118   over-matched, e.g. translation_save_edited_version
                                        -> arc-save-conflict

The cause is not a weak regex. The FE's vocabulary genuinely differs from the tool vocabulary:
`book_update_details` is a settings form sharing no token with its tool name. **So parity is
DECLARED in `contracts/gui-parity.yaml`, and this gate's job is to stop those declarations rotting.**

── THE RULE ──────────────────────────────────────────────────────────────────────────────────
Every LIVE tier-A/W tool carries one of:

  * `UI`            — a route AND a `data-testid`. The testid must EXIST, and its component must
                      be MOUNTED. A testid in a component nothing renders is still LOOM M9.
  * `UI_NO_TESTID`  — the control exists and is mounted but has no testid, so it cannot be
                      checked. Transitional: add the testid, promote to `UI`.
  * `AGENT_ONLY`    — deliberately no manual path, `reason:` REQUIRED. Not a loophole — the point.
                      "Run a grounded multi-scene generation" has no hand equivalent, and saying
                      so is honest; a silent `NONE` dressed as agent-only is what this catches.
  * `NONE`          — the gap. Ratcheted, so it can only shrink.
  * `UNTRIAGED`     — the ABSENCE of a verdict. Never counts as parity. Ratcheted down.

Usage:
  python scripts/gui-parity-gate.py             # scan
  python scripts/gui-parity-gate.py --selftest  # prove it can go red
"""
from __future__ import annotations

import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CENSUS = os.path.join("contracts", "gui-parity.yaml")
FE_SRC = os.path.join("frontend", "src")

# ── RATCHETS ────────────────────────────────────────────────────────────────────────────────
# Set from P1's census (2026-09-04). Both may only DECREASE, and a change moves in the same
# commit as the work that moved it, with the reason written in.
MAX_NONE = 0          # T6 (2026-09-04): every one of the 118 live write tools has been
                      # adjudicated and NONE of them lacks a manual path, so 0 is now a
                      # MEASURED floor rather than an aspiration. It was deliberately held
                      # at 1 while 95 rows were unlooked-at: a ratchet that turns the next
                      # honestly-found gap into a build break teaches people not to look.
                      # That risk is gone — a NEW gap now means a new tool shipped without a
                      # manual path, which is exactly what should stop the build.
                      # History: 2 (P1 census) -> 1 (P3 closed world_delete) -> 0.
MAX_UNTRIAGED = 0     # T5 (2026-09-04): translation 8 + settings 7 adjudicated, 15 -> 0.
                      # EVERY live tier-A/W tool now carries a real verdict. A tool added
                      # tomorrow lands as UNTRIAGED, breaches this, and reddens CI until
                      # someone gives it one — which is the whole point of the loop.
                      # T4: the 100%-failure cluster (9), 24 -> 15.
                      # T3: glossary's 18, 42 -> 24.
                      # T2: knowledge's 14, 56 -> 42.
                      # T1 before it: composition's 39 write tools adjudicated, 95 -> 56.
                      # The domain with the most measured agent failures by a distance (1,189
                      # of 1,740 calls). Every one resolved to a real mounted control, so the
                      # gap there was the CENSUS, not the UI.

VERDICTS = {"UI", "UI_NO_TESTID", "AGENT_ONLY", "NONE", "UNTRIAGED"}


def load_census(text: str) -> list[dict]:
    """Parse the census. Deliberately a tiny reader, not a YAML dependency: this gate must run
    with nothing installed, and the file's shape is fixed by the writer above it."""
    rows, cur = [], None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip() if raw.lstrip().startswith("#") else raw.rstrip()
        if not line.strip():
            continue
        m = re.match(r"\s*-\s+tool:\s*(\S+)", line)
        if m:
            cur = {"tool": m.group(1)}
            rows.append(cur)
            continue
        m = re.match(r"\s+(\w+):\s*(.*)$", line)
        if m and cur is not None:
            cur[m.group(1)] = m.group(2).strip()
    return rows


def fe_index() -> tuple[dict[str, set[str]], set[str]]:
    """testid -> EVERY file defining it, plus every component rendered as a JSX tag.

    🔴 EVERY file, not the first one. The first version kept only the first match and then
    reported `book-title-input` as unreachable because it happened to index the studio dock
    panel rather than `pages/BooksPage.tsx`, which mounts the same control. A testid defined
    in two places is reachable if EITHER is mounted, and first-wins turns that into a false
    red — the kind that gets a gate disabled rather than fixed."""
    tid: dict[str, set[str]] = {}
    rendered: set[str] = set()
    root = os.path.join(REPO_ROOT, FE_SRC)
    for dirpath, _dirs, files in os.walk(root):
        if "__tests__" in dirpath.replace("\\", "/"):
            continue
        for fn in files:
            if not fn.endswith((".tsx", ".ts")) or fn.endswith(".d.ts"):
                continue
            path = os.path.join(dirpath, fn)
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    txt = fh.read()
            except OSError:
                continue
            rel = os.path.relpath(path, REPO_ROOT).replace("\\", "/")
            for m in re.finditer(r'data-testid="([A-Za-z0-9_-]+)"', txt):
                tid.setdefault(m.group(1), set()).add(rel)
            # PER-ROW CONTROLS. `data-testid={`divergence-switch-${w.project_id}`}` is a real,
            # mounted control that a literal scan cannot see at all — T1 hit it on
            # composition_switch_active_work and would otherwise have had to call a working
            # control missing. A template literal is recorded under its static PREFIX plus "*",
            # and a census row declares that same prefixed form.
            for m in re.finditer(r"data-testid=\{`([A-Za-z0-9_-]+)\$\{", txt):
                tid.setdefault(m.group(1) + "*", set()).add(rel)
            # A component is USED if another file names it outside an import line: a JSX tag
            # for ordinary rendering, and a bare identifier for the registry mounts this
            # codebase relies on (`catalog.ts` maps studio dock panels as
            # `component: BookImportPanel`). Import lines are stripped deliberately — an import
            # with no use left is exactly the unmounted case, and it is what the P2 bite made.
            body = chr(10).join(
                l for l in txt.split(chr(10)) if not l.lstrip().startswith("import "))
            for m in re.finditer(r"<([A-Z][A-Za-z0-9]*)[\s/>]", body):
                rendered.add(m.group(1))
            for m in re.finditer(r"[:=,(\[]\s*([A-Z][A-Za-z0-9]*)\b", body):
                rendered.add(m.group(1))
    return tid, rendered


def is_mounted(files: set[str], rendered: set[str]) -> bool:
    """A page IS the mount point; any other component must be rendered by someone else.

    🔴 This is the LOOM M9 half. A testid that exists in a component nothing renders is exactly
    the permanently-disabled Publish button: present in source, unreachable by a user.

    ⚠️ IT IS A HEURISTIC. The first version only looked for `<JsxTag>` and called **340 of 2,588**
    testids unreachable, nearly all wrongly: `catalog.ts` mounts every studio dock panel as
    `component: BookImportPanel`, never as a tag. P3 hit that as a false red on
    `book_chapter_bulk_create` and widened it to "named in another file outside an import line",
    which covers registry mounts and ordinary JSX both. **340 → 35.**

    The import-line strip is the load-bearing half: an import with nothing left using it IS the
    unmounted case, and it is exactly what the P2 bite produced. Re-verified after widening — the
    bite still goes red, so the wider rule did not blunt the check.

    35 remain, and they are still mostly false (a context provider in `auth.tsx`, Tiptap node
    views registered by type name). **A red here is a prompt to look, not a proof of a gap.**"""
    for f in files:
        norm = f.replace("\\", "/")
        if "/pages/" in norm or norm.endswith("Page.tsx"):
            return True
        if os.path.basename(norm).rsplit(".", 1)[0] in rendered:
            return True
    return False


def scan(census_text: str) -> list[str]:
    rows = load_census(census_text)
    if not rows:
        return ["census has no rows — the gate would pass vacuously"]

    tid, rendered = fe_index()
    if not tid:
        return ["no data-testid found anywhere in the frontend — the index is broken, "
                "and every UI row would fail for the wrong reason"]

    errs: list[str] = []
    counts = {v: 0 for v in VERDICTS}
    for r in rows:
        tool, v = r.get("tool", "?"), r.get("verdict", "")
        if v not in VERDICTS:
            errs.append(f"{tool}: unknown verdict {v!r} (expected one of {sorted(VERDICTS)})")
            continue
        counts[v] += 1
        if v == "UI":
            t, route = r.get("testid"), r.get("route")
            if not route:
                errs.append(f"{tool}: verdict UI with no route")
            if not t:
                errs.append(f"{tool}: verdict UI with no testid — use UI_NO_TESTID if the "
                            f"control genuinely has none yet")
            elif t not in tid:
                errs.append(f"{tool}: declares data-testid={t!r}, which does not exist in "
                            f"{FE_SRC} — the declaration has rotted")
            elif not is_mounted(tid[t], rendered):
                errs.append(f"{tool}: data-testid={t!r} lives only in {sorted(tid[t])}, which "
                            f"nothing renders "
                            f"— present in source, unreachable by a user (LOOM M9)")
        elif v == "AGENT_ONLY" and not r.get("reason"):
            errs.append(f"{tool}: AGENT_ONLY with no reason — a silent NONE dressed as "
                        f"agent-only is what this gate exists to catch")

    if counts["NONE"] > MAX_NONE:
        errs.append(f"NONE={counts['NONE']} exceeds the ratchet {MAX_NONE} — a write with no "
                    f"manual path was added")
    if counts["UNTRIAGED"] > MAX_UNTRIAGED:
        errs.append(f"UNTRIAGED={counts['UNTRIAGED']} exceeds the ratchet {MAX_UNTRIAGED} — new "
                    f"tools must be adjudicated, not parked")

    print(f"census rows: {len(rows)}")
    for v in ("UI", "UI_NO_TESTID", "AGENT_ONLY", "NONE", "UNTRIAGED"):
        print(f"  {v:<14}{counts[v]}")
    print(f"ratchets: NONE<={MAX_NONE}  UNTRIAGED<={MAX_UNTRIAGED}")
    return errs


# ── SELFTEST — NV-1..6: a gate that cannot fail is worse than no gate ────────────────────────
_BASE = """tools:
  - tool: t_ok
    provider: book
    tier: A
    verdict: UI
    route: /books
    testid: %(real)s
"""

_CASES = [
    ("a UI row whose testid does not exist",
     _BASE % {"real": "zz-testid-that-does-not-exist"}, "does not exist"),
    ("a UI row with no testid at all",
     "tools:\n  - tool: t\n    verdict: UI\n    route: /x\n", "no testid"),
    ("a UI row with no route",
     "tools:\n  - tool: t\n    verdict: UI\n    testid: %(real)s\n", "no route"),
    ("AGENT_ONLY with no reason",
     "tools:\n  - tool: t\n    verdict: AGENT_ONLY\n", "no reason"),
    ("an unknown verdict",
     "tools:\n  - tool: t\n    verdict: PROBABLY_FINE\n", "unknown verdict"),
    ("NONE over the ratchet",
     "tools:\n" + "".join(f"  - tool: t{i}\n    verdict: NONE\n" for i in range(MAX_NONE + 1)),
     "exceeds the ratchet"),
    ("an empty census (the vacuity trap)", "tools:\n", "vacuously"),
]


def selftest() -> int:
    tid, rendered = fe_index()
    real = next(iter(sorted(tid)))
    # A testid the index itself considers unreachable — proves the LOOM M9 arm fires in CI, not
    # only under the hand-run bite that unmounted KnowledgeIndexControl.
    unreachable = next((t for t in sorted(tid) if not is_mounted(tid[t], rendered)), None)
    bad = 0
    if unreachable:
        errs = scan(chr(10).join(["tools:", "  - tool: t", "    verdict: UI", "    route: /x", "    testid: " + unreachable]))
        hit = any("nothing renders" in e for e in errs)
        print(f"  {'ok  ' if hit else 'FAIL'}  a UI row whose control nothing renders (LOOM M9)"
              f"  ->  {(errs or ['<no error>'])[0][:60]}")
        bad += not hit
    print(f"selftest: using a real testid {real!r} as the positive control\n")
    ok_errs = scan(_BASE % {"real": real})
    if ok_errs:
        print(f"  FAIL  the positive control is not clean: {ok_errs}")
        bad += 1
    else:
        print("  ok    a well-formed census passes")
    for name, text, want in _CASES:
        errs = scan(text % {"real": real} if "%(real)s" in text else text)
        hit = any(want in e for e in errs)
        print(f"  {'ok  ' if hit else 'FAIL'}  {name}  ->  {(errs or ['<no error>'])[0][:78]}")
        bad += not hit
    return bad


def main() -> int:
    os.chdir(REPO_ROOT)
    if "--selftest" in sys.argv:
        bad = selftest()
        print(f"\nselftest: {'PASS' if not bad else f'{bad} case(s) could not go red'}")
        return 1 if bad else 0
    with open(CENSUS, encoding="utf-8") as fh:
        errs = scan(fh.read())
    if errs:
        print(f"\nGUI-PARITY GATE: {len(errs)} problem(s)")
        for e in errs:
            print(f"  - {e}")
        return 1
    print("\nGUI-PARITY GATE: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
