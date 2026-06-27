"""W9 — import/deconstruct worker entrypoint (Wave-2, P4, the 拆文 mode).

``run_analyze_reference`` is the worker handler behind the Tier-W
``composition_arc_import_analyze`` tool: the confirm effect
(``routers/actions.py:_execute_arc_import``) re-checks import_source ownership, then
enqueues an ``analyze_reference`` job; the consumer dispatches HERE. The FROZEN input
envelope (stamped by the confirm effect) is::

    input = {
        "worker_op":        "analyze_reference",
        "import_source_id": str,          # the per-user import_source row (ownership re-checked at confirm)
        "use_web":          bool | None,  # augment with web-search arc boundaries for known works
        "arc_hint":         str | None,   # optional author hint to anchor segmentation
        "model_source":     str | None,   # OPTIONAL deconstruct model (else the platform default)
        "model_ref":        str | None,
    }

and ``user_id`` comes off the job row. The result is written to
``generation_job.result`` for the poll.

The compute (W9): ride the P1/P2/P3 map-reduce extraction rails (§12.4) — chunk the
imported text → LLM-direct deconstruct per chunk (MAP) → arc-reduce into one abstract
{threads, layout placements, pacing, arc_roster} + member motif specs (roles, beats,
preconditions, effects) → an **abstraction post-check** (§12.6) → a proposed
``arc_template`` (``source='imported'``, ``status='draft'``) + member motifs
(``source='imported'``, ``imported_derived=true``).

§12.6 COPYRIGHT (load-bearing): the deconstruct MUST abstract proper nouns / verbatim
phrasing into role slots + generic beats. The deconstruct PROMPT instructs the model to
abstract, AND ``_scrub_verbatim`` is a real POST-CHECK that strips any beat label/intent
or example that reproduces a long source shingle (near-verbatim retelling) — so a
"template" can never smuggle a chapter-by-chapter copy even if the model leaks one.
``examples[]`` on an imported-derived motif is author-written/synthetic, never copied
source prose; the post-check enforces it.

Provider-gateway invariant: the single LLM call routes through ``LLMClient`` →
provider-registry; NO provider SDK import, NO hardcoded model name (model resolved from
the job input or the platform default; fails closed if neither yields a ref).

DEFERRED (W9 backend slice):
  - the REAL end-to-end LLM+stack live-smoke — ``D-W9-DECONSTRUCT-LIVE-SMOKE``.
  - ``use_web`` augment — a thin flag passed to the prompt only — ``D-W9-WEBSEARCH``.
  - the deep per-chunk extraction rail (a 5th ``motif_beat`` extractor + semantic arc
    segmentation, §12.4) — this slice does a single LLM-direct deconstruct over chunked
    text, tracked ``D-W9-DECONSTRUCT-DEEP-RAIL``.

W2-F0 FREEZE: SOLE worker-owned entrypoint for import — W9 fills the body. The
worker-dispatch seam is frozen; only this file's body changes.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from uuid import UUID

import asyncpg

from app.clients.eval_client import extract_judge_content
from app.clients.llm_client import LLMClient
from app.config import settings
from app.db.models import (
    ArcPlacement,
    ArcRosterEntry,
    ArcTemplate,
    ArcTemplateCreateArgs,
    ArcThread,
    Motif,
    MotifBeat,
    MotifCreateArgs,
    MotifRole,
)
from app.db.repositories.arc_template_repo import ArcTemplateRepo
from app.db.repositories.import_source_repo import ImportSourceRepo
from app.db.repositories.motif_repo import MotifRepo
from app.engine.critic import parse_critique_json

logger = logging.getLogger(__name__)

__all__ = ["run_analyze_reference", "chunk_content", "build_deconstruct_messages",
           "scrub_verbatim", "deconstruct_reference"]

_WORD_RE = re.compile(r"\w+", re.UNICODE)


# ── chunking (P1 rail) ──────────────────────────────────────────────────────────────
def chunk_content(content: str, *, chunk_chars: int) -> list[str]:
    """Split the imported text into <= chunk_chars pieces on paragraph boundaries
    where possible (rides the P1 chunk rail — each chunk fits the deconstruct window).
    A single oversized paragraph is hard-split. Empty content → []."""
    text = (content or "").strip()
    if not text:
        return []
    if len(text) <= chunk_chars:
        return [text]
    chunks: list[str] = []
    buf = ""
    for para in text.split("\n\n"):
        if not para.strip():
            continue
        if len(para) > chunk_chars:
            # flush, then hard-split the oversized paragraph.
            if buf:
                chunks.append(buf)
                buf = ""
            for i in range(0, len(para), chunk_chars):
                chunks.append(para[i:i + chunk_chars])
            continue
        if buf and len(buf) + 2 + len(para) > chunk_chars:
            chunks.append(buf)
            buf = para
        else:
            buf = f"{buf}\n\n{para}" if buf else para
    if buf:
        chunks.append(buf)
    return chunks


# ── the deconstruct prompt (§12.6: abstract — role slots + generic beats) ────────────
def build_deconstruct_messages(
    chunk_text: str, *, arc_hint: str | None, use_web: bool, total_chunks: int,
    chunk_index: int,
) -> tuple[str, str]:
    """(system, user) for ONE chunk's abstract deconstruct. The system prompt is the
    §12.6 guardrail in instruction form: abstract EVERYTHING into role slots + generic
    beats, emit NO source proper nouns and NO verbatim source prose. The model returns
    a JSON object the reduce merges."""
    web = (
        " You MAY use well-known public arc conventions for this work to anchor the "
        "segmentation, but still emit only ABSTRACT structure." if use_web else ""
    )
    hint = f" The author hints the arc is about: {arc_hint}." if arc_hint else ""
    system = (
        "You deconstruct a passage of a story into ABSTRACT, reusable narrative "
        "structure — NOT a retelling. STRICT RULES (legal — copyright): "
        "(1) Replace every proper noun / character name / place name with a generic "
        "ROLE SLOT (e.g. 'protagonist', 'rival', 'mentor', 'the-sect'). "
        "(2) Beats are GENERIC labels ('isolation by disaster', 'betrayal reveal') — "
        "never a sentence copied or paraphrased closely from the source. "
        "(3) Emit NO source proper nouns and NO verbatim source phrasing anywhere. "
        "Return ONLY a JSON object: "
        '{"threads": [{"key": str, "label": str}], '
        '"roster": [{"key": str, "actant": "subject"|"object"|"sender"|"receiver"|"helper"|"opponent", "label": str}], '
        '"motifs": [{"code": str, "name": str, "kind": "sequence"|"scheme"|"reveal"|"reversal"|"relationship", '
        '"summary": str, "thread": str, "tension_target": int, '
        '"roles": [{"key": str, "actant": str, "label": str}], '
        '"beats": [{"key": str, "label": str, "intent": str, "order": int}], '
        '"preconditions": [str], "effects": [str]}], '
        '"placements": [{"motif_code": str, "thread": str, "span_start": int, "span_end": int, "ord": int}], '
        '"pacing": [{"chapter": int, "tension": int}]}.' + web + hint
    )
    user = (
        f"PASSAGE (chunk {chunk_index + 1} of {total_chunks}) — abstract its structure, "
        f"emit no names or source prose:\n\n{chunk_text}"
    )
    return system, user


# ── abstraction POST-CHECK (§12.6 guardrail — verbatim never survives) ───────────────
def _shingles(text: str, n: int) -> set[tuple[str, ...]]:
    """The set of lower-cased n-word shingles of `text` (the overlap unit for the
    near-verbatim check). Short text → its single shingle (or empty)."""
    words = [w.lower() for w in _WORD_RE.findall(text or "")]
    if len(words) < n:
        return {tuple(words)} if words else set()
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def _is_near_verbatim(candidate: str, source_shingles: set[tuple[str, ...]], n: int) -> bool:
    """True iff a SHARE of `candidate`'s n-word shingles above the configured ceiling
    appear verbatim in the source — i.e. the candidate reproduces a long run of source
    prose. A short generic beat label shares few/no long shingles → safe."""
    cand = _shingles(candidate, n)
    if not cand:
        return False
    overlap = len(cand & source_shingles)
    return (overlap / len(cand)) > settings.motif_deconstruct_verbatim_max_overlap


def scrub_verbatim(
    motifs: list[dict[str, Any]], *, source_text: str,
) -> tuple[list[dict[str, Any]], int]:
    """THE §12.6 abstraction post-check (a real gate, not a comment): walk every
    generated motif and BLANK any free-text field (beat label/intent, motif summary,
    example text) that reproduces a near-verbatim run of source prose. Returns the
    scrubbed motifs + the count of fields scrubbed. ``examples[]`` is dropped entirely
    if it survives at all (an imported-derived example must be author-written/synthetic,
    never copied source — §11/§12.6), and any example carrying source prose is removed.

    The model is INSTRUCTED to abstract; this is the backstop that proves verbatim
    source retelling cannot survive into a motif even if the model leaks one."""
    n = settings.motif_deconstruct_verbatim_shingle
    src = _shingles(source_text, n)
    scrubbed = 0
    out: list[dict[str, Any]] = []
    for m in motifs:
        mm = dict(m)
        # summary
        if _is_near_verbatim(str(mm.get("summary") or ""), src, n):
            mm["summary"] = ""
            scrubbed += 1
        # beats: label + intent
        beats_out: list[dict[str, Any]] = []
        for b in mm.get("beats") or []:
            bb = dict(b) if isinstance(b, dict) else {}
            for field in ("label", "intent"):
                if _is_near_verbatim(str(bb.get(field) or ""), src, n):
                    bb[field] = ""
                    scrubbed += 1
            beats_out.append(bb)
        mm["beats"] = beats_out
        # examples: any example reproducing source prose is REMOVED (not just blanked).
        examples_in = mm.get("examples") or []
        examples_out: list[dict[str, Any]] = []
        for ex in examples_in:
            text = ""
            if isinstance(ex, dict):
                text = " ".join(str(v) for v in ex.values() if isinstance(v, str))
            elif isinstance(ex, str):
                text = ex
            if _is_near_verbatim(text, src, n):
                scrubbed += 1
                continue  # drop the copied example entirely
            examples_out.append(ex)
        mm["examples"] = examples_out
        out.append(mm)
    return out, scrubbed


# ── parse one chunk's LLM deconstruct frame → a normalized dict ──────────────────────
def _parse_chunk(content: str) -> dict[str, Any]:
    """Tolerant parse of one deconstruct chunk frame → {threads, roster, motifs,
    placements, pacing}. A garbled frame yields empty lists (never crashes the reduce)."""
    obj = parse_critique_json(content) or {}
    return {
        "threads": obj.get("threads") if isinstance(obj.get("threads"), list) else [],
        "roster": obj.get("roster") if isinstance(obj.get("roster"), list) else [],
        "motifs": obj.get("motifs") if isinstance(obj.get("motifs"), list) else [],
        "placements": obj.get("placements") if isinstance(obj.get("placements"), list) else [],
        "pacing": obj.get("pacing") if isinstance(obj.get("pacing"), list) else [],
    }


# ── the arc-reduce (cluster/dedup the per-chunk maps into one abstract arc) ──────────
def _dedup_by_key(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    """Canonical dedup keeping first-seen (the tree_merge dedup spirit, §12.4)."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        k = str(it.get(key) or "")
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


def _reduce_chunks(chunk_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge per-chunk deconstruct maps into ONE abstract arc spec (threads/roster
    deduped by key; motifs deduped by code; placements concatenated; pacing kept).
    The reduce consumes the abstract MAP outputs, never raw text (§12.4)."""
    threads: list[dict[str, Any]] = []
    roster: list[dict[str, Any]] = []
    motifs: list[dict[str, Any]] = []
    placements: list[dict[str, Any]] = []
    pacing: list[dict[str, Any]] = []
    for r in chunk_results:
        threads += r.get("threads") or []
        roster += r.get("roster") or []
        motifs += r.get("motifs") or []
        placements += r.get("placements") or []
        pacing += r.get("pacing") or []
    return {
        "threads": _dedup_by_key(threads, "key"),
        "roster": _dedup_by_key(roster, "key"),
        "motifs": _dedup_by_key(motifs, "code"),
        "placements": placements,
        "pacing": pacing,
    }


# ── arg-builders: the abstract reduce → the validated Create args ────────────────────
_VALID_ACTANTS = {"subject", "object", "sender", "receiver", "helper", "opponent"}


def _coerce_actant(value: Any) -> str:
    v = str(value or "").strip().lower()
    return v if v in _VALID_ACTANTS else "subject"


def _coerce_tension(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and 1 <= value <= 5:
        return value
    return None


def _slug(value: Any, fallback: str) -> str:
    s = re.sub(r"[^a-z0-9._-]+", "-", str(value or "").strip().lower()).strip("-.")
    return s or fallback


def _motif_args(spec: dict[str, Any], *, index: int) -> MotifCreateArgs:
    roles = [
        MotifRole(
            key=_slug(r.get("key"), f"role-{i}"),
            actant=_coerce_actant(r.get("actant")),
            label=str(r.get("label") or "")[:500],
        )
        for i, r in enumerate(spec.get("roles") or []) if isinstance(r, dict)
    ]
    beats = [
        MotifBeat(
            key=_slug(b.get("key"), f"beat-{i}"),
            label=str(b.get("label") or "")[:500],
            intent=str(b.get("intent") or "")[:2000],
            order=int(b.get("order") or i),
        )
        for i, b in enumerate(spec.get("beats") or []) if isinstance(b, dict)
    ]
    preconds = [{"text": str(p)[:2000]} for p in (spec.get("preconditions") or []) if p]
    effects = [{"text": str(e)[:2000]} for e in (spec.get("effects") or []) if e]
    return MotifCreateArgs(
        code=_slug(spec.get("code"), f"imported.motif-{index}"),
        name=str(spec.get("name") or f"Imported Motif {index + 1}")[:500],
        kind=spec.get("kind") if spec.get("kind") in
        {"sequence", "scheme", "reveal", "reversal", "relationship"} else "sequence",
        summary=str(spec.get("summary") or "")[:20000],
        roles=roles,
        beats=beats,
        preconditions=preconds,
        effects=effects,
        tension_target=_coerce_tension(spec.get("tension_target")),
        examples=spec.get("examples") if isinstance(spec.get("examples"), list) else [],
        visibility="private",
    )


def _arc_args(
    reduced: dict[str, Any], *, code: str, name: str, language: str,
) -> ArcTemplateCreateArgs:
    threads = [
        ArcThread(key=_slug(t.get("key"), f"thread-{i}"), label=str(t.get("label") or "")[:500])
        for i, t in enumerate(reduced.get("threads") or []) if isinstance(t, dict)
    ]
    roster = [
        ArcRosterEntry(
            key=_slug(r.get("key"), f"role-{i}"),
            actant=_coerce_actant(r.get("actant")),
            label=str(r.get("label") or "")[:500],
        )
        for i, r in enumerate(reduced.get("roster") or []) if isinstance(r, dict)
    ]
    layout: list[ArcPlacement] = []
    for i, p in enumerate(reduced.get("placements") or []):
        if not isinstance(p, dict):
            continue
        try:
            layout.append(ArcPlacement(
                motif_code=_slug(p.get("motif_code"), f"imported.motif-{i}"),
                thread=_slug(p.get("thread"), "main"),
                span_start=int(p.get("span_start") or 1),
                span_end=int(p.get("span_end") or 1),
                ord=int(p.get("ord") or i),
            ))
        except (ValueError, TypeError):
            continue
    pacing = [p for p in (reduced.get("pacing") or []) if isinstance(p, dict)]
    chapter_span = max((p.get("span_end") or 1) for p in
                       (reduced.get("placements") or []) if isinstance(p, dict)) \
        if reduced.get("placements") else None
    return ArcTemplateCreateArgs(
        code=code, name=name, language=language,
        threads=threads, layout=layout, pacing=pacing, arc_roster=roster,
        visibility="private",
    )


# ── the pure orchestration (LLM + repos injected → fully unit-testable) ──────────────
async def deconstruct_reference(
    *, llm: LLMClient, arc_repo: ArcTemplateRepo, motif_repo: MotifRepo,
    user_id: str, source_title: str, source_content: str,
    model_source: str, model_ref: str,
    arc_hint: str | None = None, use_web: bool = False,
) -> dict[str, Any]:
    """Pure deconstruct: chunk → per-chunk LLM map → reduce → §12.6 scrub →
    persist (arc_template draft + imported_derived motifs). The LLM client + both
    repos are injected so this is unit-testable with FAKES (no DB / no real gateway).
    Returns the result dict for the GET /jobs/{id} poll.

    Fails closed (ValueError) on an empty model_ref (provider-gateway invariant: a
    deconstruct never silently runs on an unconfigured model)."""
    if not model_ref:
        raise ValueError(
            "analyze_reference: no deconstruct model_ref resolved "
            "(set motif_deconstruct_model_ref or pass model_ref on the job)"
        )
    chunks = chunk_content(source_content, chunk_chars=settings.motif_deconstruct_chunk_chars)
    if not chunks:
        raise ValueError("analyze_reference: import_source content is empty")

    # MAP — one abstract deconstruct per chunk (rides the P2 rail; each fits the window).
    chunk_results: list[dict[str, Any]] = []
    for i, ch in enumerate(chunks):
        system, user = build_deconstruct_messages(
            ch, arc_hint=arc_hint, use_web=use_web,
            total_chunks=len(chunks), chunk_index=i,
        )
        job = await llm.submit_and_wait(
            user_id=user_id, operation="chat",
            model_source=model_source, model_ref=model_ref,
            input={
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "response_format": {"type": "text"}, "temperature": 0.2,
                "max_tokens": 2048,
            },
            job_meta={"extractor": "motif_deconstruct", "chunk": i},
        )
        if getattr(job, "status", None) != "completed":
            logger.warning("deconstruct chunk %d not completed: %s", i, getattr(job, "status", None))
            chunk_results.append({"threads": [], "roster": [], "motifs": [],
                                  "placements": [], "pacing": []})
            continue
        chunk_results.append(_parse_chunk(extract_judge_content(job.result)))

    reduced = _reduce_chunks(chunk_results)

    # §12.6 ABSTRACTION POST-CHECK — scrub near-verbatim source prose out of the motifs.
    reduced["motifs"], scrubbed_count = scrub_verbatim(
        reduced.get("motifs") or [], source_text=source_content,
    )

    if not reduced["motifs"]:
        raise ValueError("analyze_reference: deconstruct produced no abstract motifs")

    # PERSIST — member motifs (source='imported', imported_derived=True) then the arc.
    base = _slug(source_title, "imported-arc")
    motif_ids: list[str] = []
    for idx, mspec in enumerate(reduced["motifs"]):
        args = _motif_args(mspec, index=idx)
        motif: Motif = await motif_repo.create(
            UUID(user_id), args, source="imported", imported_derived=True,
        )
        motif_ids.append(str(motif.id))

    arc_args = _arc_args(
        reduced, code=f"{base}.arc", name=source_title or "Imported Arc",
        language="en",
    )
    arc: ArcTemplate = await arc_repo.create(
        UUID(user_id), arc_args, source="imported", status="draft",
    )

    return {
        "arc_template_id": str(arc.id),
        "motif_ids": motif_ids,
        "abstraction_check": {
            "scrubbed_fields": scrubbed_count,
            "shingle_size": settings.motif_deconstruct_verbatim_shingle,
            "max_overlap": settings.motif_deconstruct_verbatim_max_overlap,
            "motifs_emitted": len(motif_ids),
        },
        "chunks": len(chunks),
        "use_web": bool(use_web),
        "websearch_status": "deferred:D-W9-WEBSEARCH" if use_web else "off",
    }


async def run_analyze_reference(
    pool: asyncpg.Pool, llm: LLMClient, *, user_id: str, input: dict[str, Any]
) -> dict[str, Any]:
    """Deconstruct an imported reference work into an abstract arc_template + member
    motifs. See module docstring for the frozen input envelope. Raises ``ValueError``
    (terminal business error — clean job-failed, no redeliver loop) on a bad/missing
    import_source, an empty source, an unconfigured model, or an empty deconstruct."""
    try:
        import_source_id = UUID(str(input["import_source_id"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError("analyze_reference: missing/invalid import_source_id") from exc

    repo = ImportSourceRepo(pool)
    # OWNER-checked load (defense-in-depth — the confirm effect already re-checked, but
    # the handler never trusts the envelope for the row contents; a foreign id → None).
    row = await repo.get_for_owner(UUID(user_id), import_source_id)
    if row is None:
        raise ValueError("analyze_reference: import_source not found or not owned")

    # Resolve the deconstruct model: job input wins (a future per-call override), else
    # the platform default. NO hardcoded literal (provider-gateway invariant); the pure
    # core fails closed if both are empty.
    model_source = str(input.get("model_source") or settings.motif_deconstruct_model_source)
    model_ref = str(input.get("model_ref") or settings.motif_deconstruct_model_ref)

    return await deconstruct_reference(
        llm=llm,
        arc_repo=ArcTemplateRepo(pool),
        motif_repo=MotifRepo(pool),
        user_id=user_id,
        source_title=row.title,
        source_content=row.content,
        model_source=model_source,
        model_ref=model_ref,
        arc_hint=input.get("arc_hint"),
        use_web=bool(input.get("use_web")),
    )
