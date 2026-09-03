#!/usr/bin/env python3
"""Emit the `/goal` condition for the v1 retirement — QUEUE derived, never typed.

The predecessor's board sat at `pending` for three shipped slices for six weeks because it was
typed. So the queue here is read from the code every time this runs: a slice that gets finished
leaves the queue by itself, and the resume pointer moves on its own.

Usage:  python scripts/v1_retire/goal_prompt.py [--check]
"""
from __future__ import annotations

import argparse
import ast
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import runstate  # noqa: E402

ROOT = runstate.ROOT
BUDGET = 4000


def _grep(pattern: str, *paths: str) -> bool:
    """True when the pattern is still present in tracked source (git grep, so no build dirs)."""
    r = subprocess.run(["git", "grep", "-l", "-E", pattern, "--", *paths],
                       cwd=ROOT, capture_output=True, text=True)
    return bool(r.stdout.strip())


def _exit_code(*cmd: str) -> int | None:
    try:
        return subprocess.run(cmd, cwd=ROOT, capture_output=True, timeout=300).returncode
    except (OSError, subprocess.TimeoutExpired):
        return None


def _asserts_dormancy() -> bool:
    """Does task_detect.py's module docstring still CLAIM the ext-tasks gate is dormant?

    🔴 THIS WAS A SUBSTRING GREP FOR "dormant-safe" AND IT WAS WRONG THE MOMENT R5 LANDED. The
    correction quotes the false sentence verbatim so a reader can see what was fixed — so the
    grep matched the fix and reported V0 permanently open. That is the repo's own recurring
    failure (a guard matching non-behavioural text: an import line, a dead string, a quoted
    comment) committed inside the generator written to prevent it.

    The honest signal is the SUMMARY LINE, which is what an IDE hover and `help()` show and the
    one sentence most readers see. Quotes of the old text live deeper in the docstring and must
    not count.
    """
    p = ROOT / "services/chat-service/app/services/task_detect.py"
    try:
        doc = ast.get_docstring(ast.parse(p.read_text(encoding="utf-8"))) or ""
    except (OSError, SyntaxError):
        return True  # unreadable -> assume not yet corrected; never silently pass
    return "dormant" in doc.splitlines()[0].lower() if doc else True


def slices(d: dict) -> list[tuple[str, str, bool]]:
    """(id, one-line description, is_open). Every `is_open` is DERIVED."""
    fe = ROOT / "services/chat-service/app/services/frontend_tools.py"
    out = []

    # V0 — the two instruments that lie by construction, plus the doc worklist.
    pr = _exit_code(sys.executable, "scripts/toolloop/problem_remaining.py")
    cache = _exit_code(sys.executable, "scripts/refresh_tool_catalog_cache.py", "--check")
    v0 = (pr == 0) or (cache == 1) or _asserts_dormancy()
    out.append(("V0", "de-rot (DEROT.md) + the 4 lying instruments", v0))

    # V1/V2 — the gate census, and the wire proof that follows it.
    n = d["d4"]["total"]
    out.append(("V1", f"gate totality: {n} ungated mint sites open a task or cite GATE-2", d["d4"]["state"] != "PASS"))
    out.append(("V2", "prove on the wire: bare-token rate, denominator = calls to those tools, stratified", d["d4"]["state"] != "PASS"))

    # V3 — model-facing prose. Order matters: BEFORE the allowlist edit (trap T1).
    v3 = _grep(r"glossary_confirm_action|glossary_propose_entity_edit",
               "services/chat-service/app/services/glossary_skill.py")
    out.append(("V3", "prose: the 19 Go descriptions (glossary skill DONE). BEFORE any _CORE_EXTRA edit", v3))

    # V4 — advertisement.
    adv = d["d2"].get("advertised_from_always_on_core")
    out.append(("V4", "stop advertising: ALWAYS_ON_CORE_NAMES, _STICKY_DOMAIN_IGNORE, _EXECUTOR_KEEP_CORE, 3 frontend_tool_defs sites (EDIT them, propose_edit rides along)",
                bool(adv) and adv != runstate.UNKNOWN))

    # V5 — frontend, incl. the DQ-V4 rename.
    v5 = _grep(r"glossary_confirm_action", "cms-frontend/src")
    out.append(("V5", "frontend: cms MessageList.tsx:28 is the SOLE admin-confirm gate; card -> batch_confirm (DQ-V4)", v5))

    # V6/V7 — interception and the module itself.
    out.append(("V6", "delete the v1 intercept ONLY — the other 6 suspend producers stay", d["d1"]["state"] != "PASS"))
    out.append(("V7", "DQ-V5 split (2 confirms -> glossary MCP; propose_entity_edit -> gateway directive), DELETE frontend_tools.py, re-home is_browser_executed", fe.exists()))

    # V8 — manifest, via the state machine.
    out.append(("V8", "manifest: retire the chat-service row AND admit the new owner in ONE slice", d["d3"]["state"] != "PASS"))

    # V9 — deprecated-is-dead, per DQ-V3. RUN the guard rather than grep for words: the first
    # version was `_grep(r"legacy.*refus|refus.*legacy", tool_discovery.py)`, which is line-based
    # and so reported V9 open after it had shipped. Third substring-detector miss in this file.
    v9 = _exit_code(sys.executable, "-m", "pytest",
                    "services/chat-service/tests/"
                    "test_a_deprecated_tool_is_refused_not_declared_absent.py",
                    "-q", "--no-header") != 0
    out.append(("V9", "tool_load refuses a legacy tool by name; pinned_legacy KEPT (DQ-V3)", v9))

    # VS — the SDK promotion (DQ-V7). The blocker that stalled round 1, now a slice.
    vs = not (ROOT / "sdks/python/loreweave_mcp/pg_task_store.py").exists()
    out.append(("VS", "promote PgTaskStore into sdks/python + sdks/go (copy-pasted 3x, in no kit); re-point book/glossary/composition; THEN gate translation x4 + provider-registry x1 (DQ-V7)", vs))

    # VX — the anti-vacuity guards (DQ-V8). Derived by RUNNING one representative guard rather
    # than grepping for a `pytest.skip` marker: a substring scan would match the word in a
    # docstring or a comment, which is the exact false-signal this loop has now hit three times.
    # One file, not the whole suite — bounded runtime, same answer for this class.
    vx = _exit_code(sys.executable, "-m", "pytest",
                    "scripts/test_the_queue_counts_every_state_that_is_not_finished.py",
                    "-q", "--no-header") != 0
    out.append(("VX", "anti-vacuity guards get a finished-skip mode: a COMPLETED loop must not leave its suite red (DQ-V8)", vx))

    # V10 — the gates.
    v10 = not (ROOT / "scripts/status-header-gate.py").exists()
    out.append(("V10", "gates G1-G6; each proven RED by deleting its fix first", v10))
    return out


def build() -> tuple[str, list[str]]:
    d = runstate.collect()
    sl = slices(d)
    openq = [(i, t) for i, t, o in sl if o]
    done = [i for i, _, o in sl if not o]

    q = "\n".join(f"- {i} {t}" for i, t in openq) or "- (empty — run runstate.py --check)"
    nxt = openq[0][0] if openq else "NONE — verify with runstate.py --check"

    body = f"""/goal RETIRE ARCHITECTURE V1 — the chat-service frontend-tool construct.

SPEC (SEALED, do not re-litigate): docs/specs/2026-09-03-retire-architecture-v1.md
PLAN: docs/plans/2026-09-03-retire-v1-BUILD.md · DE-ROT: ...-retire-v1-DEROT.md
BOARD IS GENERATED: python scripts/v1_retire/runstate.py (--check exits 1 while v1 lives)

OBJECTIVE — runstate.py reports "v1 IS DEAD": D1 no FRONTEND_TOOL_NAMES /
is_frontend_tool / production importer; D2 nothing chat-service-local reaches
the model; D3 the manifest row has a domain owner; D4 every confirm-mint site
opens a task or cites a GATE-2 exemption.

UNIT — ONE slice from the QUEUE. Each leaves the system working.

🔴 NEVER STOP ON A DECISION — the last run stalled on exactly that.
DQ-V6: INVESTIGATE, DECIDE IT YOURSELF, record the ruling + reasoning in the
plan's decisions register, CONTINUE. Irreversible ones included. The owner
reviews the FINAL REPORT at the end and overrules there; a reversal is a
cheap edit, a stalled run is not. No slice is blocked — some just open with
a decision.

METHOD — name the invariant, fix the class at one chokepoint, prove the
falsifier RED on an original instance, FULL owning suite green, live run.
Order: prose -> advertisement -> interception -> machinery. Never a subset
suite: 3 changes here passed their own targeted tests and were caught only
by the whole one (unregistered catalogue narrowing; swallowed outage;
UnboundLocalError on the non-discovery path = 60 red).

WHAT MUST SURVIVE (deleting any is the failure mode):
- the confirm_token spine + POST /v1/<domain>/actions/confirm. The public edge
  and external agents cannot drive tasks; the fallback is PERMANENT (GATE-2).
- mcp-public-gateway's OWN confirm_action — same name, different owner.
- chat_suspended_runs + /tool-results — 6 of 7 suspend producers are not v1.
- the three TOOLS. Only their chat-service-local IMPLEMENTATION dies.
Name a FILE in every removal step, never a tool name: confirm_action is four
different things here.

EVIDENCE — a real run, not code that looks right. State the call count beside
any rate; stratify, never pool. A test GREEN over an emptied set is a FAILURE
(plan's VACUITY REGISTER, 13 rows). Record a failed attempt; never retry
silently until it passes.

STOP — runstate.py --check exits 0 AND a final report naming every DQ-V6
decision. Nothing else stops the run. NEVER: delete anything in WHAT MUST
SURVIVE; edit an applied migration step (seeded rails need a NEW one); touch
deprecated-tool-scan's _CORE_EXTRA before V3 (that lint SKIPS, hiding a
partial edit); rewrite a historical ledger; pass a D-clause with an exemption
lacking class + reason + cited_at.

QUEUE ({len(openq)} open, {len(done)} done — derived by this script)
{q}

NEXT — {nxt}"""
    return body, [i for i, _ in openq]


def main() -> int:
    a = argparse.ArgumentParser()
    a.add_argument("--check", action="store_true")
    args = a.parse_args()
    body, openq = build()
    n = len(body)
    if n > BUDGET:
        print(f"OVER BUDGET: {n} > {BUDGET} chars. Shorten the SOURCE (the plan's slice "
              f"descriptions), never by cutting upward from QUEUE.", file=sys.stderr)
        return 1
    if args.check:
        print(f"ok — {n}/{BUDGET} chars, {len(openq)} open: {', '.join(openq)}")
        return 0
    print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
