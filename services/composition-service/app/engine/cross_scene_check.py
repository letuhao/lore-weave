"""D-CROSS-SCENE-CONTRADICTION — does this scene contradict the one before it?

The failure, measured on a real chapter
----------------------------------------
2026-08-01, FullArc book, 4 authored scenes:

    scene 2 ends   "**He** is the anchor," Cassius said. "…**he** has been waiting for
                   someone with enough ink in their veins to take **his** place."
    scene 3 opens  "**She's** a Scribe." … **she** was a sentinel, waiting for the next hand.

Same character, consecutive scenes, and nothing saw it. It is the one class of defect that is
provable with NO ground truth — the text contradicts ITSELF — which matters because the book
had no glossary, no canon and no extraction, so every other guard was blind.

Why this is EXTRACT-then-compare, not "find the contradictions"
---------------------------------------------------------------
The first version asked the judge directly: *"report only DIRECT CONTRADICTIONS… gender, name,
title or role changes"*. Measured against the exact pair above, with the seeded case and a
hand-consistent control:

    SEEDED (he→she)        status=checked  contradictions=0
    CONTROL (consistent)   status=checked  contradictions=0

Raw output was `{"contradictions": []}` — valid JSON, no parse failure. **gemma-26b simply does
not make that judgement.** A check that returns the same answer on a seeded defect and on its
control is not a weak check, it is theatre — the "QA cannot fail" shape, where the weaker the
verifier the cleaner the work looks.

The same model, asked to EXTRACT instead of judge, is reliable:

    A → {"who": "He",  "pronoun": "he",  "role": "the anchor"}
    B → {"who": "She", "pronoun": "she", "role": "Scribe"}

So the model fills slots and **the comparison lives in code**, where it is deterministic and
testable. That is this repo's standing answer for a weak model, and InkOS's too: the state
machine is in the code, the model never decides the step.

What it can and cannot link — and why it SAYS so
-------------------------------------------------
Linking is the hard part, and the reason is worse than "the model is weak".

Three attempts, in order. (1) Two stripped JSON lists, "which row in A is the same person as
which row in B?" — matched `Elara↔Elara`, missed `the anchor↔the Scribe`. (2) The same question
with the PASSAGES instead of lists, which is a reading question rather than a matching one —
and it worked: `{"present_in_b": true, "referred_to_in_b_as": "The Scribe", "pronoun_in_a":
"he", "pronoun_in_b": "she"}`. Exactly right. (3) The same probe re-run with the controls
attached — and the seeded case flipped to `{"present_in_b": false}`. Not reproducible.

Run against all three variants the pattern is clear and it is structural:

    B says "he"  (consistent) → present_in_b TRUE,  pronoun he     ✓
    B says "she" (the defect) → present_in_b FALSE                 ✗
    B omits them (absent)     → present_in_b FALSE                 ✓

**The model resolves coreference BY gender agreement.** A disagreeing pronoun does not read to
it as "this person changed", it reads as "this is a different person" — so the one signal that
would expose the defect is the same signal it uses to rule the link out. No prompt fixes that;
the question is self-defeating for the case it exists to catch.

Therefore this check does not chase coreference at all. It compares people linked by NAME,
which is deterministic, and reports `unlinked_earlier`/`unlinked_later` so a caller can tell
"no contradiction found" from "the people who might contradict could not be matched". The
measured anchor→Scribe case lands in the second bucket and says so.

The route that would close it is not a better judge — it is removing the need to infer
identity: have a scene WRITE BACK who was in it (`exit_state`, today authored-only and never
updated from what was generated), so the next scene compares by a stable key instead of by
inference. That is D-GENERATED-FACT-HAS-NO-HOME, and it is the same gap that let scene 2 invent
a gender no spec contained.

Therefore: compare only people linked by NAME, which is deterministic; and report
`unlinked_earlier`/`unlinked_later` so a caller can tell "no contradiction found" from "the
people who might contradict could not be matched". The measured anchor→Scribe case lands in
the second bucket — this check does not catch it, and says that rather than reporting clean.
"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from loreweave_llm import no_thinking_fields
from loreweave_llm.errors import LLMError

from app.clients.eval_client import extract_judge_content
from app.engine.critic import parse_critique_json
from app.packer.sanitize import neutralize
from app.llm_budget import max_tokens_for

logger = logging.getLogger(__name__)

#: A contradiction at a seam lives near the seam: the END of the earlier scene, the START of
#: the later one. Sending both scenes whole costs more and buries the join.
_TAIL_CHARS = 3000
_HEAD_CHARS = 3000

#: Only these two disagree in a way that is a FACT changing. `they`/`none` are ambiguous
#: (a plural, an unresolved referent, a deliberate withholding) and claiming a contradiction
#: from them would manufacture findings.
_GENDERED = {"he", "she"}

_ARTICLE = re.compile(r"^(the|a|an)\s+", re.I)
_POSSESSIVE = re.compile(r"['’]s$")
#: Pronouns and bare role words are not NAMES; matching on them would link two different
#: people because both were called "she".
_NOT_A_NAME = frozenset("""
he she it they him her them his hers its their someone somebody anyone everyone nobody
man woman girl boy child person figure shape voice stranger
""".split())


@dataclass
class Contradiction:
    what: str
    earlier: str
    later: str
    confidence: str = "high"


@dataclass
class CrossSceneResult:
    """`status` and the unlinked counts come FIRST because they qualify everything else.

    `contradictions == []` means "nothing was found among the people that could be linked",
    NOT "the scenes agree". `unlinked_*` is how a caller tells those apart.
    """

    status: str                      # checked | degraded | skipped_single_scene
    contradictions: list[Contradiction] = field(default_factory=list)
    linked: int = 0
    unlinked_earlier: int = 0
    unlinked_later: int = 0
    pairs_checked: int = 0

    @property
    def clean(self) -> bool:
        """Only true when something was actually compared — an all-unlinked seam is not
        clean, it is unchecked."""
        return self.status == "checked" and self.linked > 0 and not self.contradictions


def build_extract_prompt(source_language: str = "auto") -> str:
    """Extraction, not judgement — see the module docstring for the measurement that forced it.

    Deliberately asks for the passage's OWN words and forbids inference: the value of this step
    is that it is mechanical. Every judgement call is downstream, in code.
    """
    lang = "" if source_language in ("", "auto") else (
        f" The passage is in the language with code '{source_language}'; keep `who` and `role` "
        "in that language."
    )
    return (
        "For each PERSON referred to in the passage, output one row. Use the exact words the "
        "passage uses. Do not infer, do not add anyone who is not there, and do not merge two "
        "people into one row.\n"
        'Return ONLY JSON: {"people": [{"who": "<name, or the noun phrase used>", '
        '"pronoun": "he"|"she"|"they"|"none", "role": "<their role in one or two words, or '
        'empty>"}]}' + lang
    )


def _norm_name(who: str) -> str:
    w = _POSSESSIVE.sub("", _ARTICLE.sub("", (who or "").strip())).strip().lower()
    return "" if w in _NOT_A_NAME or len(w) < 3 else w


def extract_people(raw: Any) -> list[dict]:
    parsed = parse_critique_json(extract_judge_content(raw)) or {}
    out: list[dict] = []
    for row in (parsed.get("people") or [])[:40]:
        if not isinstance(row, dict):
            continue
        who = str(row.get("who") or "").strip()
        if not who:
            continue
        out.append({"who": who,
                    "pronoun": str(row.get("pronoun") or "none").strip().lower(),
                    "role": str(row.get("role") or "").strip()})
    return out


def compare_people(earlier: list[dict], later: list[dict]) -> CrossSceneResult:
    """The deterministic half. No model, no network — this is what the tests pin.

    Links by normalised NAME only. A person named in one passage and referred to only by role
    in the other stays unlinked and is COUNTED, never silently treated as agreement.
    """
    e_by = {}
    for p in earlier:
        n = _norm_name(p["who"])
        if n:
            e_by.setdefault(n, p)
    l_by = {}
    for p in later:
        n = _norm_name(p["who"])
        if n:
            l_by.setdefault(n, p)

    shared = sorted(set(e_by) & set(l_by))
    found: list[Contradiction] = []
    for name in shared:
        a, b = e_by[name], l_by[name]
        if a["pronoun"] in _GENDERED and b["pronoun"] in _GENDERED \
                and a["pronoun"] != b["pronoun"]:
            found.append(Contradiction(
                what=f"{a['who']} is referred to as '{a['pronoun']}' and then '{b['pronoun']}'",
                earlier=f"{a['who']} — {a['pronoun']}"
                        + (f", {a['role']}" if a["role"] else ""),
                later=f"{b['who']} — {b['pronoun']}" + (f", {b['role']}" if b["role"] else ""),
            ))
    return CrossSceneResult(
        status="checked", contradictions=found, linked=len(shared),
        unlinked_earlier=len(e_by) - len(shared), unlinked_later=len(l_by) - len(shared),
        pairs_checked=1,
    )


async def check_chapter_consistency(
    judge, *, user_id: str, model_source: str, model_ref: str,
    scenes: list[str], source_language: str = "auto",
    trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> CrossSceneResult:
    """Two extraction calls per seam, then `compare_people`. Degrade-safe: any outage is
    `degraded`, never a clean pass."""
    body = [s for s in scenes if s and s.strip()]
    if len(body) < 2:
        return CrossSceneResult(status="skipped_single_scene")

    system = build_extract_prompt(source_language)

    async def extract(text: str) -> list[dict] | None:
        # The passage is DATA here, not prose to continue — it is being read for a structured
        # answer. So `neutralize` is the right tool (unlike `build_beat_scope`, where
        # bracketing directive spans would write editing marks into the continuity context):
        # a payload riding in from `<lore>` must not be able to steer the extraction into
        # returning nothing, which would degrade this guard while it reported `checked`.
        text = neutralize(text)
        try:
            job = await judge.submit_and_wait(
                user_id=user_id, operation="chat",
                model_source=model_source, model_ref=model_ref,
                input={"messages": [{"role": "system", "content": system},
                                    {"role": "user", "content": text}],
                       "response_format": {"type": "text"}, "temperature": 0.0,
                       "max_tokens": max_tokens_for("cross_scene_check"),
                       **no_thinking_fields()},
                job_meta={"usage_purpose": "continuity_check", "extractor": "cast_state"},
                trace_id=trace_id, cancel_check=cancel_check,
            )
        except LLMError as exc:
            logger.warning("cross-scene extract degraded (LLM error): %s", exc)
            return None
        if job.status != "completed":
            logger.info("cross-scene extract status=%s → degraded", job.status)
            return None
        return extract_people(job.result)

    merged = CrossSceneResult(status="checked")
    degraded = False
    for a, b in zip(body, body[1:]):
        ea = await extract(a[-_TAIL_CHARS:])
        lb = await extract(b[:_HEAD_CHARS])
        if ea is None or lb is None:
            degraded = True
            continue
        r = compare_people(ea, lb)
        merged.contradictions.extend(r.contradictions)
        merged.linked += r.linked
        merged.unlinked_earlier += r.unlinked_earlier
        merged.unlinked_later += r.unlinked_later
        merged.pairs_checked += 1
    if degraded:
        # A partial outage degrades the WHOLE result: two of three seams judged must not
        # report as a checked chapter.
        merged.status = "degraded"
    if merged.contradictions:
        logger.info("cross-scene: %d contradiction(s) across %d seam(s): %s",
                    len(merged.contradictions), merged.pairs_checked,
                    "; ".join(c.what for c in merged.contradictions))
    return merged
