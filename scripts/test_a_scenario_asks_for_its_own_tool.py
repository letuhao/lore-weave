"""D-A-FIFTH-OF-SCENARIOS-DO-NOT-ASK-FOR-THEIR-OWN-TOOL — the gate.

A scenario whose prompt asks a READ question about a tool that WRITES measures the model
complying with the question it was given, not the tool it names. Seven such scenarios were
found and rewritten (D-THE-SCENARIO-ASKS-A-DIFFERENT-QUESTION-THAN-THE-TOOL-ANSWERS: 0 of 6
matched their own tool, 6 of 6 after), and that row asked for a gate so the class could not
recur.

WHY THIS GATE AND NOT THE OBVIOUS ONE. `answerable_tools()` finds 109 of 495 scenarios whose
own tool is not answerable from their prompt — but that population is TWO defects:

    world_get                   <- "List my worlds."                        SCENARIO
    registry_set_skill_enabled  <- "What skills do I have available?"       SCENARIO
    composition_motif_bind_edit <- "Attach the pattern called Emberfall
                                    Binding to this book's opening arc."    MATCHER

The third asks for exactly what the tool does; the matcher misses it, which is a missing
synonym. Failing on "does not match" would demand a prompt rewrite for cases needing a
synonym — and this loop has twice measured that rewriting something already correct makes it
worse. So the gate tests the half that is unambiguous: a READ-VERB prompt on a TIER A/W tool.
Sampled 4 of those, all genuine:

    world_map_update_marker        <- "List my worlds."
    settings_model_set_favorite    <- "List my registered AI models."
    translation_set_active_version <- "List the Vietnamese translation versions ..."
    registry_update_workflow       <- "What workflows are available to me?"

Tiers are read from the REGISTRATIONS, not from a live catalogue, so this runs offline —
validated 194/194 against the deployed catalogue on the day it was written.

The 60 existing offenders are seeded as a SHRINK-ONLY baseline, the same container
contracts/undeclared-emitter-baseline.json uses and the same choice the OUT-2 lint made with
its 14. They are historical batches whose tools are all `proven` via the corrected `-asked`
scenarios; rewriting archived measurements buys nothing. What the baseline buys is that the
61st cannot appear.
"""
from __future__ import annotations

import json
import pathlib
import re

BASELINE = pathlib.Path(__file__).resolve().parents[1] / "contracts" / "read-prompt-on-write-tool-baseline.json"
ROOT = pathlib.Path(__file__).resolve().parents[1]

#: A prompt that OPENS with one of these is asking to be told something.
READ_OPENERS = ("what ", "show ", "list ", "which ", "who ", "how many", "do i have", "tell me about")


def tiers_from_registrations() -> dict[str, str]:
    """tool -> tier, read from the MCP registrations in both languages.

    Deliberately not the live catalogue: a gate that needs a running stack does not run in CI,
    and the whole point is to stop the 61st offender being committed.
    """
    out: dict[str, str] = {}
    svc = ROOT / "services"
    for p in svc.rglob("*.py"):
        if "/tests/" in p.as_posix() or p.name.startswith("test_"):
            continue
        s = p.read_text(encoding="utf-8", errors="ignore")
        if "require_meta(" not in s:
            continue
        for blk in re.split(r"@mcp_server\.tool\(", s)[1:]:
            m = re.search(r'name="([a-z0-9_]+)"', blk)
            t = re.search(r'require_meta\(\s*"([RAWS])"', blk)
            if m and t:
                out.setdefault(m.group(1), t.group(1))
    for p in svc.rglob("*.go"):
        if p.name.endswith("_test.go"):
            continue
        s = p.read_text(encoding="utf-8", errors="ignore")
        if "NewToolMeta" not in s:
            continue
        for blk in re.split(r"registerTool\(", s)[1:]:
            m = re.search(r'Name:\s*"([a-z0-9_]+)"', blk)
            t = re.search(r'lwmcp\.Tier([RAWS])', blk)
            if m and t:
                out.setdefault(m.group(1), t.group(1))
    return out


def offenders() -> set[str]:
    """{file::id} for every scenario asking a READ question about a Tier A/W tool."""
    tiers = tiers_from_registrations()
    found: set[str] = set()
    for f in sorted((ROOT / "scripts" / "toolloop").glob("scenarios-*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for s in d.get("scenarios", []):
            tool = s.get("tool_under_test")
            prompt = (s.get("prompt") or "").lower().lstrip()
            if not tool or not prompt or tiers.get(tool) not in ("A", "W"):
                continue
            if any(prompt.startswith(o) for o in READ_OPENERS):
                found.add(f"{f.name}::{s.get('id')}")
    return found


def test_the_tier_scan_still_reads_the_registrations():
    """ANTI-VACUITY. If the registration pattern changes, every check below passes for free."""
    tiers = tiers_from_registrations()
    assert len(tiers) >= 150, f"only {len(tiers)} tools tiered — the scan has broken"
    assert sum(1 for v in tiers.values() if v in ("A", "W")) >= 100


def test_no_NEW_scenario_asks_a_read_question_of_a_write_tool():
    """THE GATE. The baseline may only SHRINK."""
    base = set(json.loads(BASELINE.read_text(encoding="utf-8"))["scenarios"])
    now = offenders()
    new = sorted(now - base)
    assert not new, (
        "these scenarios ask a READ question about a tool that WRITES, so they measure the "
        "model answering the question it was given rather than the tool they name:\n  "
        + "\n  ".join(new)
        + "\nFix the PROMPT to ask for the tool's action (see scenarios-c-ask.json), or if the "
          "prompt is right and the tool simply is not matched, that is a synonym gap and a "
          "different defect."
    )


def test_the_baseline_only_shrinks():
    """A fixed offender must come OUT, or the debt is never worked down."""
    base = set(json.loads(BASELINE.read_text(encoding="utf-8"))["scenarios"])
    now = offenders()
    fixed = sorted(base - now)
    assert not fixed, (
        f"these are no longer offenders and must be removed from {BASELINE.name}: {fixed}"
    )


def test_the_baseline_is_not_empty_and_is_not_growing_silently():
    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert base["count"] == len(base["scenarios"]), "the recorded count disagrees with the list"
    assert base["count"] > 0
