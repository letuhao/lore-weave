"""Schema-governed GENERATION (RAID C11) — fill the C9 scaffold's empty Chinese
dimensions with content GENERATED from the C10 retrieved cultural grounding.

This is the cycle where empty dimension slots become real (Chinese, source-
faithful) lore. The pipeline per proposal is:

  1. build a schema-governed PROMPT (Chinese, cites the C10 grounding passages,
     names exactly the missing dimensions the model must fill),
  2. call the LLM through an INJECTED ``CompleteFn`` seam — the generating model
     is resolved via provider-registry by ``model_ref`` on the
     :class:`StrategyContext`; NO model NAME appears in code (the locked engine,
     a strong Classical-Chinese model served over LM Studio, is referenced only
     by its registry ref). Tests inject a deterministic stub; the real binding
     (provider-registry ``/internal/llm``) is wired at orchestration time (C14),
     exactly as C10 deferred its embed registry-wiring,
  3. REPAIR the raw output to the schema (``repair.repair_generation``) —
     malformed → repaired-or-typed-reject, never silently dropped,
  4. for EACH repaired dimension, mint an :class:`EnrichedFact` through the H0
     chokepoint (``provenance.make_enriched_fact``) — every fact is born
     ``origin='enriched:<technique>'`` + provenance + ``confidence<1.0`` +
     ``pending_validation=True`` + non-empty ``source_refs``.

H0 / scope boundary: the ONLY way a fact leaves this module is via the
provenance chokepoint, so an untagged fact cannot be produced. This cycle STOPS
at tagged in-memory records — NO write-back to glossary/Neo4j/KG (C13), NO
contradiction/anachronism check (C12), NO orchestration (C14).
"""

from __future__ import annotations

from typing import Awaitable, Callable

from app.generation.provenance import (
    GENERATION_CONFIDENCE,
    EnrichedFact,
    SourceRef,
    make_enriched_fact,
)
from app.db.book_profile import NEUTRAL_PROFILE, BookProfile
from app.gaps.model import is_zh, kind_label_for
from app.generation.repair import (
    RepairError,
    RepairReport,
    _extract_json_object,
    _load_json,
    _strip_fence,
    cjk_ratio,
)
from app.retrieval.strategy import GroundedProposal, GroundingRef
from app.strategies.base import StrategyContext, Technique

__all__ = [
    "CompleteFn",
    "GenerationError",
    "InsufficientGroundingError",
    "SchemaGovernedGenerator",
    "build_generation_prompt",
]

#: A dimension value must be at least this fraction CJK to count as grounded
#: Chinese content (mirrors repair.py's gate — an English/garbage value for a
#: Chinese dimension is treated as UNGROUNDED, never minted as a fact).
_MIN_CJK_RATIO: float = 0.30


#: The injected LLM-completion seam: (prompt, context) → raw model text. Bound to
#: the provider-registry generation endpoint by ``model_ref`` on the context
#: (NEVER a model name). The generator never imports an HTTP/LLM client; tests
#: pass a deterministic stub. Real binding lands in C14 (like C10's embed seam).
CompleteFn = Callable[[str, StrategyContext], Awaitable[str]]


class GenerationError(RuntimeError):
    """Raised when generation cannot produce a schema-valid set of facts.

    Wraps the un-repairable :class:`RepairError` (and empty-grounding rejects) so
    a caller distinguishes "the model produced unusable output" from a transport
    error. A generation that cannot be repaired is REJECTED — never emitted as a
    partial / untagged fact.
    """


class InsufficientGroundingError(GenerationError):
    """Raised when the retrieved grounding supports NONE of the gap's dimensions
    (LE-PROD slice B). Distinct from a generic :class:`GenerationError`: the model
    DID respond, but — per the grounded-flag protocol — marked every dimension
    ``grounded=false`` (the excerpts don't cover this entity). This is the
    "未提及" case that previously produced a useless proposal full of refusal prose;
    now the runner SKIPS the gap and surfaces an ACTIONABLE reason (paste context /
    use fabrication). A subclass of GenerationError so existing skip handlers still
    catch it; the runner checks the type to record the specific reason."""


def build_generation_prompt(
    proposal: GroundedProposal,
    profile: BookProfile = NEUTRAL_PROFILE,
    kind_label: str | None = None,
) -> str:
    """Build the schema-governed, grounding-citing generation prompt (de-bias C1).

    BOOK-AWARE: the worldview / output language / voice come from the per-book
    ``profile`` (NOT hardcoded to 封神演义 / 中文), and the entity-kind label is
    localized (``kind_label``). Deterministic: names the entity, lists EXACTLY the
    missing dimension labels the model must fill (the JSON keys), embeds the C10
    grounding excerpts as the ONLY evidence (source-faithful, no fabrication). NO
    model name, NO provider-specific tokens. The Fengshen profile (zh) reproduces
    the original Chinese prompt's intent (tests are substring-based, not byte-exact).
    """
    dims = list(proposal.dimensions.keys())
    grounding_block = "\n".join(
        f"［{i + 1}］（来源 {g.corpus_id}#{g.chunk_index}，相似度 {g.score}）{g.excerpt}"
        for i, g in enumerate(proposal.grounding)
    )
    # Grounded-flag shape (LE-PROD slice B): each dimension is an OBJECT carrying an
    # explicit ``grounded`` boolean + ``content``. This lets the model SIGNAL that the
    # excerpts don't cover a dimension (grounded=false, content="") instead of writing
    # apologetic "未提及" prose that then surfaces as a useless proposal. Robust across
    # languages/models (a structural flag, not a refusal-phrase string match).
    json_skeleton = ", ".join(
        f'"{d}": {{"grounded": true, "content": "……"}}' for d in dims
    )
    kind_label = kind_label or kind_label_for(proposal.entity_kind, profile.language)
    worldview = (profile.worldview or "").strip()

    if is_zh(profile.language):
        # Chinese template (Fengshen demo path). worldview/voice interpolated.
        keys_csv = "、".join(dims)
        wv = f"忠于{worldview}的" if worldview else ""
        voice = (profile.voice or "").strip()
        voice_clause = f"，{voice}" if voice else "，须与既有设定语气一致"
        return (
            f"你是一位{wv}世界观补全助手。\n"
            f"请仅依据下列检索片段，为{kind_label}「{proposal.canonical_name}」"
            f"补全以下维度：{keys_csv}。\n"
            f"要求：\n"
            f"1. 内容必须为中文{voice_clause}；\n"
            f"2. 严禁编造检索片段未支持的事实；\n"
            f"3. 逐维度判断：若检索片段确有依据，则该维度 grounded 设为 true 并在 "
            f"content 填写中文描述；若片段未提供依据，则 grounded 设为 false 且 content "
            f"留空字符串。切勿臆造、致歉或写「未提及」之类的说明文字；\n"
            f"4. 仅输出一个 JSON 对象，键为上述维度名，值为形如 "
            f'{{"grounded": true/false, "content": "中文描述"}} 的对象，不要输出任何额外说明。\n\n'
            f"检索到的依据：\n{grounding_block}\n\n"
            f"请输出 JSON：{{{json_skeleton}}}"
        )

    # English / neutral template (any non-Chinese or profile-less book).
    keys_csv = ", ".join(dims)
    lang_name = profile.language if profile.language not in ("", "auto") else "the book's language"
    setting = f"faithful to this work's setting ({worldview})" if worldview else "a worldbuilding assistant"
    voice = (profile.voice or "").strip()
    voice_clause = f", matching its voice ({voice})" if voice else ""
    return (
        f"You are {setting}.\n"
        f"Using ONLY the retrieved excerpts below as evidence, fill the following "
        f"dimensions for the {kind_label} «{proposal.canonical_name}»: {keys_csv}.\n"
        f"Rules:\n"
        f"1. Write in {lang_name}{voice_clause};\n"
        f"2. Do NOT invent facts the excerpts do not support;\n"
        f"3. For EACH dimension decide: if the excerpts support it, set grounded=true "
        f"and fill content; if they do NOT, set grounded=false and content=\"\". Do not "
        f"apologize, explain, or write 'not mentioned' — just set the flag;\n"
        f"4. Output ONLY a single JSON object keyed by the dimension names, each value "
        f'an object {{"grounded": true/false, "content": "…"}}, with no extra commentary.\n\n'
        f"Retrieved evidence:\n{grounding_block}\n\n"
        f"Output JSON: {{{json_skeleton}}}"
    )


def parse_grounded_output(
    raw: str, expected_keys: list[str]
) -> tuple[dict[str, str], list[str]]:
    """Parse generation output into ``(grounded, ungrounded)`` (LE-PROD slice B).

    Returns ``grounded`` = {dimension: content} for dimensions the model GROUNDED
    (flag true + non-empty + sufficiently-CJK content), and ``ungrounded`` = the
    dimensions it could not support. TOLERANT of two shapes so a non-compliant model
    never crashes the pipeline:

      * grounded-flag (preferred): ``{"dim": {"grounded": bool, "content": str}}``,
      * legacy flat: ``{"dim": "content"}`` (a non-empty CJK string ⇒ grounded).

    A dimension is UNGROUNDED when: ``grounded=false``, the key is missing, content
    is empty, or content is non-Chinese (low-CJK — English-leakage / garbage; never
    minted as a fact). Reuses the deterministic JSON recovery from ``repair`` (fence
    / surrounding-prose / trailing-comma tolerant). Raises :class:`GenerationError`
    only when NO JSON object can be recovered at all (truly unusable output)."""
    report = RepairReport()
    try:
        text = _strip_fence(raw, report)
        obj_text = _extract_json_object(text, report)
        data = _load_json(obj_text, report)
    except RepairError as exc:
        raise GenerationError(f"generation output is unusable: {exc}") from exc

    grounded: dict[str, str] = {}
    ungrounded: list[str] = []
    for key in expected_keys:  # C6 declaration order
        content, claimed = _dimension_value(data.get(key))
        if claimed and content and cjk_ratio(content) >= _MIN_CJK_RATIO:
            grounded[key] = content
        else:
            ungrounded.append(key)
    return grounded, ungrounded


def _truthy_grounded(flag: object) -> bool:
    """Interpret the ``grounded`` flag robustly (review-impl #3). A real JSON bool
    passes through; a STRING flag (`"false"`/`"no"`/`"0"` — a model that quoted the
    bool) is honored as false rather than being truthy-by-accident. Anything else
    falls back to the value's own truthiness."""
    if isinstance(flag, str):
        return flag.strip().lower() not in ("false", "no", "0", "")
    return bool(flag)


def _dimension_value(v: object) -> tuple[str, bool]:
    """Normalize one dimension's raw value to ``(content, claimed_grounded)``.

    ``{"grounded","content"}`` → the explicit flag + content; a bare string →
    grounded iff non-empty (legacy tolerance); a scalar → coerced + grounded; a
    list → ``、``-joined; anything else / None → ungrounded. The CJK gate is applied
    by the caller, so a low-CJK 'grounded' value still ends up ungrounded."""
    if isinstance(v, dict):
        content = v.get("content")
        text = str(content).strip() if isinstance(content, (str, int, float)) else ""
        return text, _truthy_grounded(v.get("grounded", True))
    if isinstance(v, str):
        t = v.strip()
        return t, bool(t)
    if isinstance(v, bool):  # bool before int (bool is an int subclass)
        return "", False
    if isinstance(v, (int, float)):
        return str(v).strip(), True
    if isinstance(v, list):
        joined = "、".join(str(x).strip() for x in v if str(x).strip())
        return joined, bool(joined)
    return "", False


def _source_refs_from_grounding(grounding: list[GroundingRef]) -> list[SourceRef]:
    """Project the C10 grounding refs onto the H0 ``source_refs`` shape.

    The grounding the retrieval cycle attached IS the provenance of the generated
    content — each generated fact must cite at least one of these. An empty
    grounding list means the content has no source → generation is rejected
    (an unprovenanced fact is an H0 violation, enforced downstream too).
    """
    return [
        SourceRef(
            corpus_id=g.corpus_id,
            chunk_id=g.chunk_id,
            chunk_index=g.chunk_index,
            score=g.score,
        )
        for g in grounding
    ]


class SchemaGovernedGenerator:
    """Turn a grounded proposal (C10) into a list of H0-tagged enriched facts.

    Construct with the injected :data:`CompleteFn`. :meth:`generate` runs the
    prompt → complete → repair → H0-tag pipeline for one proposal and returns one
    :class:`EnrichedFact` per missing dimension. NEVER emits canon: every fact
    passes through the provenance chokepoint.
    """

    def __init__(
        self,
        *,
        complete: CompleteFn,
        confidence: float = GENERATION_CONFIDENCE,
    ) -> None:
        self._complete = complete
        self._confidence = confidence

    async def generate(
        self,
        proposal: GroundedProposal,
        context: StrategyContext,
    ) -> list[EnrichedFact]:
        """Generate + repair + H0-tag the missing dimensions of one proposal.

        Rejects (raises :class:`GenerationError`) if the proposal has no grounding
        (no source → unprovenanced), if there are no dimensions to fill, or if the
        model output cannot be repaired to cover every missing dimension. Each
        returned fact is born quarantined (H0) — origin ``enriched:<technique>``,
        non-empty provenance + source_refs, ``confidence<1.0``,
        ``pending_validation=True``.
        """
        expected_keys = list(proposal.dimensions.keys())
        if not expected_keys:
            raise GenerationError(
                f"proposal for {proposal.canonical_name!r} has no missing "
                "dimensions to generate"
            )
        if not proposal.grounding:
            raise GenerationError(
                f"proposal for {proposal.canonical_name!r} has no grounding — "
                "refusing to generate unprovenanced content (H0)"
            )

        source_refs = _source_refs_from_grounding(proposal.grounding)
        prompt = build_generation_prompt(proposal, context.profile)
        raw = await self._complete(prompt, context)

        # Grounded-flag parse (slice B): keep ONLY dimensions the model grounded;
        # a dimension it could not support from the excerpts is dropped (never
        # minted as a "未提及" fact). If NONE are grounded the gap has no usable
        # corpus grounding → InsufficientGroundingError (the runner skips it with an
        # actionable reason, rather than surfacing an empty proposal).
        grounded, ungrounded = parse_grounded_output(raw, expected_keys)
        if not grounded:
            raise InsufficientGroundingError(
                f"retrieval grounding did not support any dimension of "
                f"{proposal.canonical_name!r} (excerpts do not cover it) — "
                "paste reference context or use fabrication"
            )

        technique = proposal.technique or Technique.RETRIEVAL.value
        facts: list[EnrichedFact] = []
        for dimension in expected_keys:  # C6 declaration order, deterministic
            if dimension not in grounded:
                continue  # ungrounded → not enough evidence; dropped (slice B)
            facts.append(
                make_enriched_fact(
                    user_id=proposal.user_id,
                    project_id=proposal.project_id,
                    entity_kind=proposal.entity_kind,
                    canonical_name=proposal.canonical_name,
                    target_ref=proposal.target_ref,
                    dimension=dimension,
                    content=grounded[dimension],
                    technique=technique,
                    source_refs=source_refs,
                    model_ref=context.model_ref,
                    confidence=self._confidence,
                    qualified_origin=True,
                    extra_provenance={
                        "source_proposal_technique": proposal.technique,
                        "grounding_count": len(proposal.grounding),
                        # slice B: which dims the excerpts could NOT support + the
                        # fraction grounded — surfaced so a reviewer sees the gap
                        # was only partially fillable from the corpus.
                        "ungrounded_dimensions": ungrounded,
                        "grounding_strength": round(
                            len(grounded) / len(expected_keys), 4
                        ),
                    },
                )
            )
        return facts
