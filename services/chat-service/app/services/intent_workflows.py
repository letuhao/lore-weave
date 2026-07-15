"""Intent → workflow pinning (all-tracks-clear M2, 2026-07-15).

WHY: a mode binding pins a rail by MODE (write → vision-to-book), which is why the flagship drives
reliably — "recognising a workflow from an assent is a step a mid-tier model does not reliably take;
a pin removes the step" (stream_service.py). But the mode binding pins only ONE rail per mode. The
OTHER rails — entity-triage, canon-check, kg-build, build-a-book — a mid-tier model has to DISCOVER
(workflow_list → recognise → workflow_load → drive), and measured, gemma-26B does that inconsistently:

  S03 entity-triage 0/3 (never calls list_ai_suggestions, thrashes kg_list_templates, hallucinates)
  S04 kg-build      1/3 (drove it once, missed twice)
  S09 canon-check   improvises KG ops instead of composition_conformance_run

This closes that gap the SAME way the mode binding does — by PINNING. It maps the user's own words to
the rail they describe, so "clean up my suggestions" pins entity-triage exactly as "write my novel"
pins vision-to-book. Deterministic keyword match (no LLM call — cheap, and reliable in a way an
embedding router is not for a small closed rail set). ADDITIVE: it unions with the mode-binding pin,
never replaces it, and is filtered to the workflows actually visible this turn (a pin naming an
invisible workflow is dropped upstream).

Conservative by construction: it only fires on phrases that unambiguously describe a rail's JOB, and
only for the discovery-hard rails (the mode-pinned vision-to-book is left to the binding). A false pin
is bounded — the step-runner drives a rail only when its steps are genuinely actionable against the
book's state, so pinning a rail the book isn't ready for is a no-op, not a wrong write.
"""
from __future__ import annotations

import re

# slug -> the patterns that describe THAT rail's job in a user's own words. Ordered, first-match-wins
# per slug (a message can pin more than one rail; the step-runner handles a list). Patterns are
# lowercase-matched against the user's message. Kept SPECIFIC to avoid mis-pinning.
_INTENT_PATTERNS: list[tuple[str, list[str]]] = [
    ("entity-triage", [
        r"\btriage\b",
        r"clean\s+up.*(suggestion|inbox|pile|entit|character|item)",
        r"review.*(inbox|suggestion)",
        r"(keep|throw).*(junk|out).*(character|entit|item|suggestion)",
        r"(merge|combine).*(duplicate|dupe|same)",
        r"get\s+rid\s+of.*(suggestion|entit|character|it'?s\s+not)",
        r"suggested\s+item",
        r"(approve|reject).*(suggestion|entit)",
    ]),
    ("canon-check", [
        r"contradict",
        r"consisten(t|cy)",
        r"\bcanon\b",
        r"(conflict|clash).*(story|chapter|world|plot)",
        r"stay.*(consistent|true).*(story|world)",
        r"flag.*(anything|something).*(wrong|off|contradict)",
    ]),
    ("kg-build", [
        r"how.*(everything|it\s+all|they).*(connect|relate)",
        r"map.*(connection|relationship|how)",
        r"(build|create).*(graph|knowledge\s+graph|connection\s+map)",
        r"relationships?\s+between",
        r"connect.*(the\s+dots|everything|characters)",
    ]),
    ("build-a-book", [
        r"(plan|outline|lay\s+out).*(the\s+)?(whole\s+|entire\s+)?book",
        r"book\s+plan",
        r"(overall\s+)?arc\s+and.*(beat|structure)",
        r"major\s+beats",
        r"plan\s+out.*(story|novel|book)",
    ]),
    ("translation-pass", [
        r"\btranslate\b",
        r"english\s+reader",
        r"(only|just).*(what\s+changed|the\s+new|dirty)",
        r"translation\s+pass",
    ]),
    ("autonomous-drafting", [
        r"draft.*(the\s+)?next.*(chapter|few)",
        r"keep\s+(writing|drafting)",
        r"write.*(several|multiple|the\s+next\s+few).*chapter",
        r"draft.*while\s+i",
    ]),
    ("draw-a-map", [
        r"\bmake\s+a\s+map\b",
        r"\bdraw\s+a\s+map\b",
        r"map\s+of\s+(my|the)\s+world",
        r"(see|show).*world.*(laid\s+out|on\s+a\s+map)",
        r"put.*(city|capital|place|town).*(on\s+the\s+)?map",
        r"\bworld\s+map\b",
    ]),
]

_COMPILED: list[tuple[str, list[re.Pattern]]] = [
    (slug, [re.compile(p, re.I) for p in pats]) for slug, pats in _INTENT_PATTERNS
]


def intent_pinned_workflows(text: str | None, visible_slugs: set[str] | None = None) -> list[str]:
    """Map a user's message to the workflow rail(s) it describes, filtered to the visible set.

    Returns an ordered, de-duplicated list of slugs to PIN this turn (in addition to the mode
    binding). Empty when nothing matches — the exact pre-existing behavior, so this can only ADD a
    pin, never remove one. `visible_slugs=None` skips the visibility filter (used by unit tests)."""
    if not text:
        return []
    out: list[str] = []
    for slug, patterns in _COMPILED:
        if visible_slugs is not None and slug not in visible_slugs:
            continue
        if any(p.search(text) for p in patterns):
            out.append(slug)
    return out
