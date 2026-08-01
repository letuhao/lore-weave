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

The route that closes it is not a better judge — it is removing the need to infer identity:
have a scene WRITE BACK who was in it, so the next scene compares against a stable key instead
of against a fresh inference. That is D-GENERATED-FACT-HAS-NO-HOME and it is now built
(`engine/exit_state.py`): a drafted scene records its cast into `outline_node.exit_state`, and
`earlier_recorded` below feeds those rows in as the earlier side of the first seam.

**It does not rescue the anchor→Scribe case, and this docstring will not pretend it does.**
That referent is unnamed on both sides; a recorded `who="the anchor"` and an extracted
`who="She"` still do not link, and this check still counts it in `unlinked_earlier`. What the
recording changes there is the DRAFTING side — the fact is now in the next scene's prompt as a
stated constraint rather than as a sentence 14,000 characters back in compressible prose. For
people the prose NAMES, the earlier side becomes a record a human can correct instead of a
re-reading of the same text.

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
    #: WHERE the earlier side of each seam came from: `recorded` (the prior scene's
    #: `exit_state.cast`, written when that scene was drafted) or `extracted` (re-read from its
    #: prose now). Not decoration — the two differ in what a human can have corrected, so a
    #: reader of this result must not have to guess which one produced it.
    earlier_source: str = "extracted"

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
        '`name` is their PROPER NAME and must be "" unless the passage actually names them — '
        'a pronoun, a title, or a description like "the man" is NOT a name.\n'
        'Return ONLY JSON: {"people": [{"who": "<name, or the noun phrase used>", '
        '"name": "<their proper name, or empty>", '
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
                    "name": str(row.get("name") or "").strip(),
                    "pronoun": str(row.get("pronoun") or "none").strip().lower(),
                    "role": str(row.get("role") or "").strip()})
    return out


def identity_of(row: dict) -> str:
    """The row's IDENTITY key — its proper name, normalised. `""` = not an identity.

    MEASURED 2026-08-01, live, on a Vietnamese scene. Keying on `who` produced ten "people":
    *Người kia · Anh ta · Người đàn ông · Anh · cộng đồng · những người xung quanh · đối phương ·
    ngươi · hai người đàn ông · Ánh mắt họ* — every one a pronoun or a common noun, one of them
    ("their gaze") not a person at all. `_NOT_A_NAME` is an ENGLISH word list, so it filtered
    none of them.

    That is not a cosmetic problem in either consumer. As a recorded cast it would inject ten
    invented "facts" into the next scene's prompt. As a seam key it means two DIFFERENT people
    both called *anh ta* link as one and can be reported as a gender contradiction — a
    false-finding generator, and it has been live.

    There is no deterministic language-independent test for "is this a proper name": Vietnamese
    is Latin-scripted, so capitalisation cannot decide it (`Người đàn ông` at a sentence start
    is the same shape as `Cassius`). So the EXTRACTOR is asked to fill a `name` slot — a
    reading question, the kind a weak model answers reliably — and the decision stays here.
    FAILS CLOSED: no `name`, no identity. Recording nothing is strictly better than recording
    a key that means "everybody".
    """
    return _norm_name(str(row.get("name") or ""))


def compare_people(earlier: list[dict], later: list[dict]) -> CrossSceneResult:
    """The deterministic half. No model, no network — this is what the tests pin.

    Links by normalised NAME only. A person named in one passage and referred to only by role
    in the other stays unlinked and is COUNTED, never silently treated as agreement.
    """
    def _key(p: dict) -> str:
        """A proper name is the only key that means ONE person.

        The presence of the `name` KEY — not its value — decides which rule applies, and the
        difference is not academic. A live CONTROL run on a Vietnamese scene where nobody is
        named reported `linked=2, clean=true`: the first version of this fell back to `who`
        whenever `name` was empty, so two common nouns matched and the seam read as verified.
        An empty `name` from the extractor is an ANSWER ("the passage does not name them"), and
        falling back on it re-created the exact false green this check exists to remove.

        A row with no `name` key at all is a different thing: a stored cast (which passed the
        name filter when it was recorded) or a pre-`name` caller. Those keep the old behaviour.
        """
        if "name" in p:
            return identity_of(p)
        return _norm_name(str(p.get("who") or ""))

    e_by = {}
    for p in earlier:
        n = _key(p)
        if n:
            e_by.setdefault(n, p)
    l_by = {}
    for p in later:
        n = _key(p)
        if n:
            l_by.setdefault(n, p)

    shared = sorted(set(e_by) & set(l_by))
    found: list[Contradiction] = []
    for name in shared:
        a, b = e_by[name], l_by[name]
        # `.get`, not `[...]`: this function is public and takes rows from two producers —
        # `extract_people` and a STORED cast — so a missing optional key must not be a
        # KeyError inside a guard that is supposed to be degrade-safe.
        pa, pb = a.get("pronoun", "none"), b.get("pronoun", "none")
        ra, rb = a.get("role") or "", b.get("role") or ""
        if pa in _GENDERED and pb in _GENDERED and pa != pb:
            found.append(Contradiction(
                what=f"{a.get('who')} is referred to as '{pa}' and then '{pb}'",
                earlier=f"{a.get('who')} — {pa}" + (f", {ra}" if ra else ""),
                later=f"{b.get('who')} — {pb}" + (f", {rb}" if rb else ""),
            ))
    return CrossSceneResult(
        status="checked", contradictions=found, linked=len(shared),
        unlinked_earlier=len(e_by) - len(shared), unlinked_later=len(l_by) - len(shared),
        pairs_checked=1,
    )


async def extract_people_from(
    judge, *, user_id: str, model_source: str, model_ref: str, text: str,
    source_language: str = "auto", trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> list[dict] | None:
    """One extraction call over one passage. `None` on any outage — never `[]`, which a caller
    would read as "nobody is in this scene".

    Public because the exit-state write-back (D-GENERATED-FACT-HAS-NO-HOME) records the SAME
    extraction this check consumes. Two different extractors over the same prose would disagree
    eventually, and the disagreement would surface as a phantom contradiction at a seam.
    """
    return await _extract_one(
        judge, user_id=user_id, model_source=model_source, model_ref=model_ref, text=text,
        system=build_extract_prompt(source_language), source_language=source_language,
        trace_id=trace_id, cancel_check=cancel_check,
    )


async def _extract_one(
    judge, *, user_id: str, model_source: str, model_ref: str, text: str, system: str,
    source_language: str = "auto", trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> list[dict] | None:
    # The passage is DATA here, not prose to continue — it is being read for a structured
    # answer. So `neutralize` is the right tool (unlike `build_beat_scope`, where bracketing
    # directive spans would write editing marks into the continuity context): a payload riding
    # in from `<lore>` must not be able to steer the extraction into returning nothing, which
    # would degrade this guard while it reported `checked`.
    text = neutralize(text)
    try:
        job = await judge.submit_and_wait(
            user_id=user_id, operation="chat",
            model_source=model_source, model_ref=model_ref,
            input={"messages": [{"role": "system", "content": system},
                                {"role": "user", "content": text}],
                   "response_format": {"type": "text"}, "temperature": 0.0,
                   # `source_language` is threaded in rather than inferred from `system`,
                   # which already baked it into a prompt string. No `target`: the row count
                   # is what the extraction is for, so stating one would be a guess wearing
                   # the shape of a measurement.
                   "max_tokens": max_tokens_for("cross_scene_check",
                                                language=source_language),
                   **no_thinking_fields()},
            job_meta={"usage_purpose": "continuity_check", "extractor": "cast_state"},
            trace_id=trace_id, cancel_check=cancel_check,
        )
    except LLMError as exc:
        logger.warning("cast extract degraded (LLM error): %s", exc)
        return None
    if job.status != "completed":
        logger.info("cast extract status=%s → degraded", job.status)
        return None
    return extract_people(job.result)


async def check_chapter_consistency(
    judge, *, user_id: str, model_source: str, model_ref: str,
    scenes: list[str], source_language: str = "auto",
    trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
    earlier_recorded: list[dict] | None = None,
) -> CrossSceneResult:
    """Two extraction calls per seam, then `compare_people`. Degrade-safe: any outage is
    `degraded`, never a clean pass.

    ``earlier_recorded`` (D-GENERATED-FACT-HAS-NO-HOME) is the FIRST scene's cast as the scene
    itself recorded it at draft time (`exit_state.cast`). When present it replaces that side's
    extraction call — same rows, but they are the ones a human can have corrected, and the call
    is not paid twice. It applies to the first seam only; later seams still extract, because
    only the immediately-preceding scene has been through the write-back at this point.
    """
    body = [s for s in scenes if s and s.strip()]
    if len(body) < 2:
        return CrossSceneResult(status="skipped_single_scene")

    system = build_extract_prompt(source_language)

    async def extract(text: str) -> list[dict] | None:
        return await _extract_one(
            judge, user_id=user_id, model_source=model_source, model_ref=model_ref,
            text=text, system=system, source_language=source_language,
            trace_id=trace_id, cancel_check=cancel_check,
        )

    merged = CrossSceneResult(status="checked")
    # An empty recorded list is NOT a usable earlier side — it would compare the later scene
    # against nobody and report `linked=0` as though the extraction had run. Treat it as absent.
    carried = list(earlier_recorded) if earlier_recorded else None
    merged.earlier_source = "recorded" if carried else "extracted"
    degraded = False
    for i, (a, b) in enumerate(zip(body, body[1:])):
        ea = carried if (i == 0 and carried is not None) else await extract(a[-_TAIL_CHARS:])
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
