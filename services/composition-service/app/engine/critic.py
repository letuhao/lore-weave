"""judge_prose advisory critic (§4) — 4 dims + per-violation canon check.

Reuses the eval client (the JudgeLLMClient Protocol is satisfied by our
LLMClient) with `operation="chat"`. The critic model MUST differ from the
drafter (anti-self-reinforcement §4) — the CALLER passes a distinct model_ref.

Tolerance (enrichment repair.py lesson): the model returns JSON; we strip
fences + extract the first balanced object, then read dims defensively and
FILTER malformed `violations[]` per-item — one bad verdict never discards the
whole critique. CC4: any LLM/timeout error degrades to an empty advisory
critique (the critic is advisory; it must NEVER block accept).

De-bias (§2.6): the rubric judges in the book's `source_language`; prompts use
abstract phrasing, NO English-only illustrative phrases (memory: those bias a
CJK/VN judge to English).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

from loreweave_llm import no_thinking_fields
from loreweave_llm.errors import LLMError

from app.clients.eval_client import extract_judge_content
from app.clients.llm_client import LLMClient
from app.packer.profile import BookProfile
from app.llm_budget import max_tokens_for

logger = logging.getLogger(__name__)

_DIMENSIONS = ("coherence", "voice_match", "pacing", "canon_consistency")
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_critique_json(text: str) -> dict[str, Any] | None:
    """Strip code fences + extract the first balanced {...} object. None on
    hard failure (the caller degrades — never raises)."""
    if not text:
        return None
    cleaned = _FENCE_RE.sub("", text).strip()
    try:
        return json.loads(cleaned)
    except (ValueError, TypeError):
        pass
    # Fallback: first balanced top-level object.
    depth = 0
    start = -1
    for i, ch in enumerate(cleaned):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                candidate = cleaned[start:i + 1]
                try:
                    return json.loads(candidate)
                except (ValueError, TypeError):
                    return _repair_missing_commas(candidate)
    return None


#: A closing quote, a line break, then a quoted identifier followed by `:` — i.e. the next
#: token is unambiguously a KEY, so the only thing that can belong between them is a comma.
_MISSING_COMMA_RE = re.compile(r'"(\s*\n\s*)"([A-Za-z_][A-Za-z0-9_-]*)"(\s*):')


def _repair_missing_commas(candidate: str) -> dict[str, Any] | None:
    """Last resort: insert the comma a judge left out, and accept the result ONLY if it parses.

    🔴 **Measured live (C34), not imagined.** On the real 4757-char chapter-10 draft the shipped
    critic returned `canon=None raw=0` on **3 of 3** runs. `llm_jobs` ruled out truncation —
    `finish_reason=stop`, 2257–2273 tokens each time — and the raw reply was JSON-shaped and
    invalid by one character:

        "note": "...does not fit well with the established narrative flow."
                    "span": "..."                                  <- no comma

    The whole object was then refused, discarding the `violations` array ABOVE it, which had
    already found and attributed R1. A verdict thrown away over punctuation is the same family
    as C12's dropped finding, one layer lower.

    ⚠️ **Narrow on purpose.** It repairs the ONE shape that was observed and nothing else, and
    it is reached only after both strict parse and balanced extraction have failed. If the
    repair does not produce valid JSON the answer is still `None` — a parser that guesses its
    way to an object would invent a verdict, which is worse than reporting none. Do not widen
    this to "fix whatever the model emitted" without a measurement showing the new shape.
    """
    repaired, n = _MISSING_COMMA_RE.subn(r'",\1"\2"\3:', candidate)
    if not n:
        return None
    try:
        out = json.loads(repaired)
    except (ValueError, TypeError):
        return None
    logger.info(
        "parse_critique_json salvaged a verdict by inserting %d missing comma(s) — the judge "
        "emitted invalid JSON and the finding would otherwise have been discarded", n,
    )
    return out if isinstance(out, dict) else None


def _coerce_score(value: Any) -> int | None:
    """A dim score is an int 0-5; anything else → None (unjudged on that dim)."""
    if isinstance(value, bool):  # bool is an int subclass — exclude
        return None
    if isinstance(value, int):
        return value if 0 <= value <= 5 else None
    if isinstance(value, float) and value.is_integer():
        v = int(value)
        return v if 0 <= v <= 5 else None
    return None


def _filter_violations(raw: Any) -> list[dict[str, Any]]:
    """Keep only well-formed violation verdicts (dict with a rule_id). A
    malformed item is dropped, not fatal (tolerant parse)."""
    out: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return out
    for v in raw:
        if not isinstance(v, dict) or v.get("rule_id") in (None, ""):
            continue
        out.append({
            "rule_id": str(v.get("rule_id")),
            "violated": bool(v.get("violated", True)),
            "span": v.get("span") if isinstance(v.get("span"), str) else "",
            "why": v.get("why") if isinstance(v.get("why"), str) else "",
        })
    return out


def normalize_critique(parsed: dict[str, Any] | None) -> dict[str, Any]:
    """Shape a parsed judge response into the generation_job.critic contract.
    Missing/malformed dims → None; malformed violations filtered out."""
    parsed = parsed or {}
    crit: dict[str, Any] = {d: _coerce_score(parsed.get(d)) for d in _DIMENSIONS}
    crit["violations"] = _filter_violations(parsed.get("violations"))
    # C12 — carried through because the prompt now asks for it. A judge told to write to a
    # field the normaliser drops is a judge told nothing: the finding would vanish exactly as
    # it did when `map_rule_tokens` discarded the invented rule.
    crit["craft_notes"] = [
        {"note": str(n.get("note", ""))[:400], "span": str(n.get("span", ""))[:200]}
        for n in (parsed.get("craft_notes") or [])
        if isinstance(n, dict) and str(n.get("note", "")).strip()
    ][:10]
    # NOTHING WAS JUDGED, and it has to SAY so. `parse_critique_json` returns None on a hard
    # failure and this function then produced all-None dims, an empty violations list and NO
    # error marker -- a shape a consumer cannot tell from a verdict. Measured 2026-08-21 on a
    # 7187-char passage: 2 of 3 critique calls came back `canon_consistency=None,
    # violations=[], error=None`, intermittently, while 10 earlier calls on the SAME passage
    # scored 2. A silent parse failure that reads as "unjudged" is the same defect class as a
    # dropped verdict that reads as "nothing found" -- and unlike those, this one had no
    # counter beside it at all.
    #
    # The condition is deliberately "the judge scored NOTHING", not "parsed was falsy": a reply
    # that parses but carries no dims is equally not a verdict, and keying on the parse result
    # would miss it.
    if all(crit[d] is None for d in _DIMENSIONS):
        crit["error"] = "critic_unparsable"
    return crit


def rule_token(index: int) -> str:
    """The label a rule is shown under, and the only thing the judge is asked to echo.

    Positional and short on purpose — see the note in `build_critique_prompt`. 1-based
    because `[R0]` reads like an error to both a model and a human.
    """
    return f"R{index + 1}"


def map_rule_tokens(
    violations: list[dict[str, Any]], active_rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Translate `R<n>` labels back to real rule ids, DROPPING anything unrecognised.

    Dropping is the point. The previous shape accepted whatever string the judge put in
    `rule_id`, so a copied or invented id became a verdict about a real rule that the judge
    had never actually been asked about. An unmappable label means the verdict cannot be
    attributed, and a finding nobody can attribute is not evidence — it is noise with a
    citation. Tolerant of a judge that echoes the real id anyway (some do), because that is
    still an attributable verdict.
    """
    out: list[dict[str, Any]] = []
    for v in violations:
        mapped = _attribute(v, active_rules)
        if mapped is None:
            continue
        out.append({**v, "rule_id": str(mapped)})
    return out


def _attribute(v: dict[str, Any], active_rules: list[dict[str, Any]]) -> str | None:
    """The single attribution decision, shared so the mapper and the drop-reporter cannot
    drift. Returns the real rule id, or None when the verdict is unattributable."""
    by_token = {rule_token(i): r.get("rule_id") for i, r in enumerate(active_rules)}
    known_ids = {str(r.get("rule_id")) for r in active_rules if r.get("rule_id")}
    raw = str(v.get("rule_id", "")).strip().strip("[]")
    mapped = by_token.get(raw.upper())
    if mapped is None and raw in known_ids:
        mapped = raw              # the judge echoed the real id — still attributable
    return None if mapped is None else str(mapped)


def unattributable_labels(
    violations: list[dict[str, Any]], active_rules: list[dict[str, Any]], limit: int = 5,
) -> list[str]:
    """The labels `map_rule_tokens` could not attribute, for the ENVELOPE.

    Not a set-difference against the mapped output: `map_rule_tokens` REWRITES `rule_id` to the
    real id, so subtracting kept ids from raw ids flags the attributable ones too. (That bug was
    written here first and caught by its own test.) It asks the same predicate instead.
    """
    return sorted({
        str(v.get("rule_id", ""))[:48] for v in violations
        if _attribute(v, active_rules) is None
    })[:limit]


def build_critique_prompt(
    passage: str, active_rules: list[dict[str, Any]], present_facts: list[str],
    profile: BookProfile,
) -> tuple[str, str]:
    """Build (system, user) for judge_prose. Abstract, multilingual-safe rubric
    (no English-only illustrative phrases). The judge scores in source_language
    when known."""
    lang = "" if profile.source_language in ("", "auto") else (
        f" Write all string values in the language with code '{profile.source_language}'."
    )
    system = (
        "You are a fiction continuity and craft critic. Judge the passage on four "
        "dimensions, each an integer 0-5: coherence (logical flow), voice_match "
        "(consistency with the work's voice), pacing (fit to the scene's beat), and "
        "canon_consistency (does it contradict any active canon rule or established "
        "fact). Each active rule is labelled [R1], [R2] and so on. For each active rule the "
        "passage contradicts, add a violation whose rule_id is that rule's label exactly, "
        "with a short contradicting span, and a `why` that describes THAT rule — never "
        "repeat another rule's reason. "
        # 🔴 THE JUDGE NEEDS SOMEWHERE TO PUT A FINDING NO LISTED RULE COVERS, or it invents a
        # rule to carry it. Measured by REPLAYING the stored request (C12, job 01a02149-…): the
        # judge returned `rule_id` "QUY UOC XUNG HO" whose `why` translates to "uses the pronoun
        # 'anh' as the narrative person instead of conventional pronouns" — a REAL craft finding
        # (voice_match scored 2), not a hallucination. `map_rule_tokens` then correctly dropped
        # it, so the author saw `violations: []` and lost the observation.
        #
        # Three runs per arm on the replayed request:
        #     control (this prompt without the clause)  invented [2, 6, 6]  notes [0, 0, 0]
        #     "do not invent a rule"                    invented [0, 0, 0]  notes [0, 0, 0]
        #     THIS clause (a channel)                   invented [0, 0, 0]  notes [2, 2, 2]
        #
        # Both stop the invention; only this one KEEPS the finding. Telling a judge not to
        # report something it can see does not make it stop seeing it — it makes it discard it.
        "A craft or continuity problem that NONE of the listed rules covers is NOT a "
        'violation: put it in "craft_notes" instead, and never invent a rule id for it. '
        "Return ONLY a JSON object "
        '{"coherence":int,"voice_match":int,"pacing":int,"canon_consistency":int,'
        '"violations":[{"rule_id":str,"violated":true,"span":str,"why":str}],'
        '"craft_notes":[{"note":str,"span":str}]}.'
        + lang
    )
    # ⚠️ RULES ARE LABELLED R1..Rn, NOT BY THEIR UUID — and that is the fix, not a tidy-up.
    #
    # This block used to render `- [<uuid>] <text>` and ask the judge to echo the uuid back in
    # each verdict. Measured 2026-08-12 (QC-5, `D-QC5-PROSE-JUDGE-VERDICT-NOT-PER-RULE`): given
    # one rule the passage flatly contradicts and one its first sentence plainly confirms, the
    # judge returned BOTH as `violated: true` **carrying the same `why` verbatim** — the reason
    # belonging to the other rule. Stable 3/3 on byte-identical input, so it is structural, not
    # sampling noise.
    #
    # A 36-character uuid is not a label a model can carry accurately through a long passage;
    # it is a string to be approximated. A short positional token is, and the same defect one
    # judge over (`judge_role_attribution`, *"the verdict attached to the wrong relationship —
    # subject-id keying → per-statement token"*) was closed exactly this way. `map_rule_tokens`
    # maps them back and DROPS anything unrecognised, so a copied or invented label can no
    # longer reach an author as a verdict about a real rule.
    rules_block = "\n".join(
        f'- [{rule_token(i)}] {r.get("text", "")}' for i, r in enumerate(active_rules)
    ) or "(none)"
    facts_block = "\n".join(f"- {f}" for f in present_facts) or "(none)"
    user = (
        f"ACTIVE CANON RULES:\n{rules_block}\n\n"
        f"ESTABLISHED FACTS (present entities):\n{facts_block}\n\n"
        f"PASSAGE:\n{passage}"
    )
    return system, user


VERIFIER_SYSTEM = (
    "You audit a proposed canon violation for a work of fiction. You are given one canon RULE, "
    "the SPAN a critic flagged, and the full PASSAGE for context. "
    "Answer true ONLY if the passage makes the rule false. "
    "Answer false if the passage is consistent with the rule, if the rule does not speak to "
    "what the passage describes, or if the claim would need a requirement the RULE TEXT does "
    "not literally state. Restating the rule is not a contradiction. "
    'Return ONLY {"contradicts": true|false, "reason": "<one short sentence>"}.'
)


async def verify_violations(
    judge: LLMClient, *, user_id: str, model_source: str, model_ref: str, passage: str,
    violations: list[dict[str, Any]], active_rules: list[dict[str, Any]],
    trace_id: str | None = None, cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Second, NARROW pass per attributed violation: does the passage make the rule FALSE?

    🔴 **The critique call is the wrong shape for this judgement and the measurement says so.**
    It asks one model to score four dimensions and find violations across a whole chapter at
    once, and `D-QC5-PROSE-JUDGE-FIRES-ON-CONFORMING-PROSE` is what comes back: of 14 attributed
    violations adjudicated by hand against their rule texts, the false ones restate the rule
    ("Lam Trach is the betrayer and no one else" as the REASON a passage depicting exactly that
    is a violation), invent a clause and hang it on a real rule id ("...and no one can drain his
    spiritual energy", which R5 does not say), or flag prose the rule plainly permits.

    Asking one question about one rule and one passage is a task the same model can do. Measured
    on the arms below, planted-vs-clean on one passage differing by a single name:

        verifier      planted (a real R1 violation)   clean        historical false
        gemma-4-26b   kept 4/4                        dropped 2/2  dropped 14/14
        qwen2.5-7b    kept 4/4                        kept 0/3     -

    ⚠️ So this HELPS exactly as far as the configured critic can audit itself, and the 7B row is
    why that is stated rather than assumed: it says `true` to everything, which is the mirror of
    the span-only variant that said `false` to everything. Neither is a filter. A book whose
    critic cannot discriminate is left where it was — no verdict is invented and none is
    silently dropped — and `violations_unverified` says so on the envelope.

    ⚖️ **The span alone is NOT enough context, measured before this shape was chosen.** A
    span-only verifier scored 0/3 on the sound verdicts, and its own reasons said why: "trying
    to resist the L-Field" contradicts "Lâm Uyên controls the L-Field" only once you know who
    is resisting. A criterion that cannot pass for a true case is not a filter.

    Fails OPEN, per CC4: a verifier that errors must not delete a finding. Returns
    `(kept, dropped_reasons)`.
    """
    by_id = {str(r.get("rule_id")): str(r.get("text", "")) for r in active_rules}
    kept: list[dict[str, Any]] = []
    dropped: list[str] = []
    for v in violations:
        # ⚰️ **SPAN CONTAINMENT was built here and MEASURED OUT (C36).** The idea: a span the
        # judge quotes must appear in the passage, which would catch the fabricated quote C35
        # found the semantic verifier keeping (a sentence with a different character's name
        # substituted in, 3/3). It was validated on the 16 stored violations — 14 spans present,
        # the 2 absent already adjudicated false — and then the LIVE planted arm killed it:
        #
        #     clean arm    raw=2 kept=0   3/3   both false positives dropped
        #     planted arm  raw=4 kept=0   ALL FOUR dropped by CONTAINMENT
        #
        # The planted arm contains a REAL violation, and this route's judge PARAPHRASES its
        # spans ("He walked as if he had just strolled in…") rather than quoting them. So
        # containment has 0 recall here — the same failure as the span-only verifier, arrived at
        # from the other side. The 14/16 census came from the AUTHORING path and did not
        # generalise, which is rule 3 catching a detector validated on one distribution.
        #
        # Fuzzy overlap does not rescue it: C35's fabrication shares every token with the real
        # sentence except the name. Do not rebuild this without a way to tell a paraphrase from
        # a substitution.
        rule_text = by_id.get(str(v.get("rule_id")), "")
        if not rule_text:
            # Nothing to audit against. `map_rule_tokens` already refuses unattributable
            # verdicts, so this is belt-and-braces rather than a live branch — and it keeps
            # rather than drops, because an unauditable verdict is not a disproven one.
            kept.append(v)
            continue
        user = (f"RULE:{chr(10)}{rule_text}{chr(10)}{chr(10)}FLAGGED SPAN:{chr(10)}"
                f"{v.get('span', '')}{chr(10)}{chr(10)}PASSAGE:{chr(10)}{passage}")
        try:
            job = await judge.submit_and_wait(
                user_id=user_id, operation="chat", model_source=model_source, model_ref=model_ref,
                input={
                    "messages": [{"role": "system", "content": VERIFIER_SYSTEM},
                                 {"role": "user", "content": user}],
                    "response_format": {"type": "text"}, "temperature": 0.0, "max_tokens": 400,
                    **no_thinking_fields(),
                },
                job_meta={"usage_purpose": "prose_critic_verify", "extractor": "verify_violations"},
                trace_id=trace_id, cancel_check=cancel_check,
            )
        except LLMError as exc:
            logger.warning("verify_violations degraded (LLM error), KEEPING the verdict: %s", exc)
            kept.append(v)
            continue
        if job.status != "completed":
            kept.append(v)
            continue
        parsed = parse_critique_json(extract_judge_content(job.result))
        if not isinstance(parsed, dict) or "contradicts" not in parsed:
            # Unparsable is not a refutation. Same reasoning as the LLMError arm.
            kept.append(v)
            continue
        if parsed.get("contradicts"):
            kept.append(v)
        else:
            dropped.append(f"{v.get('rule_id')}: {str(parsed.get('reason', ''))[:160]}")
    return kept, dropped


async def judge_prose(
    judge: LLMClient, *, user_id: str, model_source: str, model_ref: str,
    passage: str, active_rules: list[dict[str, Any]], present_facts: list[str],
    profile: BookProfile, max_tokens: int | None = None, trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
    verifier_source: str | None = None, verifier_ref: str | None = None,
    emit_canon_violations: bool = False,
) -> dict[str, Any]:
    """Run the advisory critique. Returns the generation_job.critic dict. CC4:
    any LLM/timeout/parse failure degrades to an empty critique with an `error`
    marker — NEVER raises (advisory must not block accept)."""
    # The critique is FOUR scored dimensions plus at most one violation per active canon
    # rule, so the rule count is the part that varies per call — a book with 40 active rules
    # can return an order of magnitude more than one with two, and the old import-time
    # default gave both the same room. `language` because the reason strings are written in
    # the book's language and VERDICT is a branch that reads it.
    max_tokens = max_tokens or max_tokens_for(
        "judge_prose", target=len(_DIMENSIONS) + len(active_rules),
        language=profile.source_language)
    system, user = build_critique_prompt(passage, active_rules, present_facts, profile)
    try:
        job = await judge.submit_and_wait(
            user_id=user_id, operation="chat", model_source=model_source,
            model_ref=model_ref,
            input={
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "response_format": {"type": "text"}, "temperature": 0.0,
                "max_tokens": max_tokens,
                # The critic emits JSON, so reasoning tokens are pure budget-burn.
                **no_thinking_fields(),
            },
            job_meta={"usage_purpose": "prose_critic", "extractor": "judge_prose"}, trace_id=trace_id,
            cancel_check=cancel_check,
        )
    except LLMError as exc:
        logger.warning("judge_prose degraded (LLM error): %s", exc)
        return {**{d: None for d in _DIMENSIONS}, "violations": [], "active_rule_count": len(active_rules),
                "present_fact_count": len(present_facts), "error": "critic_unavailable"}
    if job.status != "completed":
        logger.info("judge_prose job status=%s → degraded", job.status)
        return {**{d: None for d in _DIMENSIONS}, "violations": [], "active_rule_count": len(active_rules),
                "present_fact_count": len(present_facts), "error": f"critic_{job.status}"}
    content = extract_judge_content(job.result)
    crit = normalize_critique(parse_critique_json(content))
    # Attribute the verdicts before anyone sees them. Done here rather than inside
    # `normalize_critique` so that function stays a pure shape-normaliser with no knowledge of
    # which rules were sent — the mapping needs the request, not just the response.
    raw_violations = crit.get("violations", [])
    crit["violations"] = map_rule_tokens(raw_violations, active_rules)
    # A DROP MUST BE VISIBLE. `map_rule_tokens` discards a verdict it cannot attribute, which
    # is right — but discarding silently would turn "the judge answered about a rule we never
    # sent" into "the judge found nothing", and those two need opposite responses. Without
    # this line a mapping bug and a clean passage are the same observation, which is the
    # failure this whole task exists to stop being possible.
    dropped = len(raw_violations) - len(crit["violations"])
    # ...and visible TO THE CONSUMER, not only to a log reader. The line below was the whole
    # detector, and a log line is not readable by the Run Report, the quality report, or the
    # author looking at the score — all of whom see `violations: []` and cannot tell "the
    # passage is clean" from "the judge found seven things and none could be attributed".
    # Measured 2026-08-13 (C3): chapter 12 of the acceptance book produced **7 raw verdicts,
    # 7 dropped, rules=0** while the report showed an empty violations list beside
    # `canon_consistency=1`. The score carried the finding; the channel meant to name it was
    # silently empty. `active_rules` being empty is the CAUSE, this field is the SYMPTOM made
    # silently empty. `active_rules` being empty is ONE cause — and C7 measured a SECOND that
    # this comment used to deny by saying "the CAUSE". On 2026-08-21 a run with **six** active
    # rules dropped 2 of 2, and the labels say why:
    #
    #     dropped 2 unattributable verdict(s) of 2 (labels=['QUY UOC XUNG HO', ...], rules=6)
    #
    # The book's six rules are character facts ("X is the cousin of Y"); none of them is a
    # naming-convention rule. The judge INVENTED a category and answered about that, so the
    # drop is CORRECT and the mapper is not the defect. A fallback matching on the label would
    # have attached a fabricated rule to a real one — `D-QC5-PROSE-JUDGE-VERDICT-NOT-PER-RULE`,
    # fixed 2026-08-12. Do not add one. Which cause applies is read off `rules=` in the warning
    # below, and off `violations_dropped_labels` on the envelope.
    crit["violations_dropped"] = dropped
    crit["violations_raw_count"] = len(raw_violations)
    # The LABELS belong on the ENVELOPE, not only in a log line. Diagnosing the above needed a
    # container that still happened to be running; after a rotation `dropped=2, rules=6` cannot
    # distinguish "the judge invented a rule" from "the mapper is broken", and those need
    # opposite responses — a model decision versus a code fix. Bounded so a chatty judge cannot
    # inflate the envelope.
    if dropped:
        crit["violations_dropped_labels"] = unattributable_labels(raw_violations, active_rules)
    crit["violations_raw_count"] = len(raw_violations)
    if dropped:
        logger.warning(
            "judge_prose dropped %d unattributable verdict(s) of %d (labels=%r, rules=%d) — "
            "the judge answered about something it was not asked about",
            dropped, len(raw_violations),
            [str(v.get("rule_id"))[:24] for v in raw_violations], len(active_rules),
        )
    # ── The verdict is now ATTRIBUTABLE. Whether it is TRUE is a different question ──────
    #
    # `map_rule_tokens` proves the judge answered about a rule we sent. It cannot tell whether
    # the passage actually contradicts that rule, and `D-QC5-PROSE-JUDGE-FIRES-ON-CONFORMING-
    # PROSE` is the gap: 14 attributed violations adjudicated by hand, and the false ones cite a
    # REAL rule id while inventing its content — which is exactly the class attribution cannot
    # catch, by construction. The narrow second pass is measured in `verify_violations`.
    # Always stamped, even at zero — `violations_dropped` beside it is, and a key that
    # appears only when it is non-zero makes every consumer write a `.get`, which is how
    # a missing field and a clean result become the same observation.
    # QC-5 C46 — the ATTRIBUTION CHANNEL, gated. Measured: C44 put the judge at 4/4 false
    # attributions on canon-conforming prose with one rule in play, and C45 measured the
    # precision pass at 14/14 IN-SAMPLE against 0/5 HELD OUT. The PO's C31 conditional
    # ("spend on precision first; if precision cannot be reached, default the judge OFF")
    # therefore fires, narrowed to the one output the evidence indicts (PO, 2026-08-30).
    #
    # ⚠️ **The parameter DEFAULTS to the product default, and that is deliberate.** C34 found
    # the verifier role passed at one of three `judge_prose` call sites; the same forgetting
    # here must fail SAFE, so a caller that says nothing suppresses. Emitting is opt-in.
    #
    # NEVER silent. The raw count and a marker ride the envelope, because "the judge was
    # refuted" and "the passage is clean" need opposite responses — the same reason
    # `violations_dropped` and `violations_unverified` are stamped even at zero.
    if not emit_canon_violations:
        crit["canon_violations_suppressed"] = True
        crit["violations_withheld_count"] = len(crit["violations"])
        crit["violations"] = []
    else:
        crit["canon_violations_suppressed"] = False
    crit["violations_unverified"] = 0
    if crit["violations"]:
        # The verifier is its OWN role (`ModelRole.CRITIC_VERIFIER`), falling back to the
        # critic when a book has not chosen one. C31 measured why the two are separable:
        # a model kept 4/4 planted violations and 0/3 false ones when auditing itself, so
        # breadth and precision can want different models. The fallback keeps every book
        # that never configures a verifier on exactly today's behaviour.
        verified, unverified = await verify_violations(
            judge, user_id=user_id,
            model_source=verifier_source or model_source,
            model_ref=verifier_ref or model_ref,
            passage=passage, violations=crit["violations"], active_rules=active_rules,
            trace_id=trace_id, cancel_check=cancel_check,
        )
        crit["violations"] = verified
        # Counted and NAMED, for the reason every other drop on this envelope is: a verdict that
        # vanished silently turns "the judge was refuted" into "the passage is clean", and those
        # need opposite responses. The reasons are the verifier's own words, bounded.
        crit["violations_unverified"] = len(unverified)
        if unverified:
            crit["violations_unverified_reasons"] = unverified[:5]
            logger.info(
                "judge_prose verifier refuted %d of %d attributed verdict(s)",
                len(unverified), len(unverified) + len(verified),
            )
    # HOW MANY RULES THE JUDGE WAS ACTUALLY GIVEN, stamped here rather than by the caller.
    # `authoring_run_service` has added this since C5 and `quality_report` never did, so the
    # SAME empty `violations: []` was self-explaining on one seam and mute on the other — and
    # the mute one is the second seam that passes `active_rules=[]` deliberately. A reader of
    # that report could not tell a deliberate no-rules critique from the C3 failure it looks
    # exactly like. One home, every exit, including both degrades above.
    crit["active_rule_count"] = len(active_rules)
    # ...and how many established FACTS, for the same reason and a worse spread. The three
    # seams that call this judge each ground it differently, measured 2026-08-21:
    #
    #   authoring_run_service   rules ✓   facts ✓ (bible.as_present_facts())
    #   routers/engine critique rules ✓   facts ✗ -- no chapter anchor, so no spoiler-safe
    #                                     "as of" cast exists to render; DEFENSIBLE
    #   quality_report          rules ✗   facts ✓ (the rendered bible, deliberately)
    #
    # So `canon_consistency` means three different things by endpoint, and NONE of the three
    # said which. A withheld input is fine; a withheld input the output does not declare is
    # the C3 shape again -- indistinguishable from the input having gone missing.
    crit["present_fact_count"] = len(present_facts)
    return crit
