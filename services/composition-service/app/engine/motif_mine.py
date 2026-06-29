"""W8 — motif mining worker entrypoint (Wave-2, P3, "mine my own graph", §3.2).

``run_mine_motifs`` is the worker handler behind the Tier-W ``composition_motif_mine``
tool: the confirm effect (``routers/actions.py:_execute_motif_mine``) enqueues a
``mine_motifs`` job; the consumer dispatches HERE. The FROZEN input envelope (stamped
by the confirm effect) is::

    input = {
        "worker_op":   "mine_motifs",
        "scope":       "book" | "corpus",
        "book_id":     str | None,     # required when scope == "book"
        "min_support": int | None,     # min occurrences before a beat-pattern is a draft
        "promote_to":  "user" | None,  # where accepted drafts land (default user-tier draft)
        "language":    str | None,     # motif language axis (P1)
    }

and ``user_id`` comes off the job row. The result dict is written to
``generation_job.result`` for the GET /jobs/{id} poll.

The compute (W8), structured as a PURE orchestration with injected
knowledge/llm/repo (unit-testable with FAKES — the W9 precedent):

  0. **Tag-beats pre-pass (v2, D-W8-MOTIF-BEAT-LLM-EXTRACTOR):** ``run_mine_motifs`` first
     calls ``knowledge.tag_beats`` over the book/corpus with the user's VISIBLE motif catalog
     (system + own) + the BYOK model, so the :Event timeline carries ``mined_motif_code`` and
     the beat-source emits GENERIC ``namespace:local`` axes (corpus-reusable). Best-effort:
     skipped without a model; any tagging error → the Option-A axes (fewer patterns, no crash).
  1. **Beat-sequence source (cross-service):** ``knowledge.get_motif_beat_sequences``
     returns ``event_order``-ordered beat sequences (each a list of
     ``{beat, thread, tension, role_mentions}``). The knowledge-service SERVER
     ``motif_beat`` extractor (``POST /internal/extraction/motif-beats``, commit 73004c33)
     SHIPPED; the client returns ``[]`` only for a cold/empty corpus, so the path still
     DEGRADES cleanly (``mined: 0, reason: 'beat_extractor_unavailable'``) when a book was
     never analysis-extracted.
  2. **PrefixSpan mining:** mine frequent ordered beat-subsequences with support ≥
     ``min_support``. Each frequent pattern (+ its ``mining_support`` count) is a
     candidate motif. ``prefixspan`` is a pure, unit-tested function.
  3. **LLM abstraction:** per candidate, ONE LLM call (via LLMClient → provider-
     registry; model from input else the platform default, NO hardcoded name)
     abstracts the beat-subsequence into a motif spec — GENERIC role slots, no
     source proper nouns.
  4. **Binary judge:** score each abstracted candidate; below ``motif_mine_min_judge``
     it is SHOWN, never silently dropped (§11) — the result lists ALL candidates with
     their ``judge_score`` + a ``passed_gate`` flag; only gate-passers are persisted.
  5. **Persist:** gate-passers → ``MotifRepo.create(source='mined', status='draft',
     judge_score=…, mining_support=…)`` (drafts; the user reviews/promotes).

Provider-gateway invariant: the abstraction + judge LLM calls route through
``LLMClient`` → provider-registry; NO provider SDK, NO hardcoded model name (resolved
from the job input or the platform default; fails closed if neither yields a ref). The
beat source goes through the knowledge client, never a direct DB read of
loreweave_extraction (the contract §3 seam).

SHIPPED:
  - ``D-W8-MOTIF-BEAT-EXTRACTOR`` (commit 73004c33) — the knowledge-service ``motif_beat``
    deriver (Option A: deterministic, rides the extracted :Event timeline).
  - ``D-W8-MOTIF-BEAT-LLM-EXTRACTOR`` — the ``tag-beats`` classifier (catalog → ``mined_motif_code``)
    that promotes the beat/thread axes to generic ``namespace:local`` (the tag-beats pre-pass
    above + ``motif_beat@v2``). Live-smoked over a real 106-event corpus (22 events → 7 codes).
  - ``D-W8-MINE-LIVE-SMOKE`` (commit f890da77) — the cross-service mine→draft live-smoke.

W2-F0 FREEZE: this module is the SOLE worker-owned entrypoint for mining — W8 fills
the body. The worker-dispatch seam (``constants.py`` + ``job_consumer.py``) is frozen
and MUST NOT be re-edited by W8; only this file's body changes.
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg

from app.clients.eval_client import extract_judge_content
from app.clients.llm_client import LLMClient
from app.config import settings
from app.db.models import Motif, MotifBeat, MotifCreateArgs, MotifRole
from app.engine.critic import parse_critique_json

logger = logging.getLogger(__name__)

__all__ = [
    "run_mine_motifs",
    "mine_motifs",
    "prefixspan",
    "build_abstraction_messages",
    "build_judge_messages",
]

_VALID_ACTANTS = {"subject", "object", "sender", "receiver", "helper", "opponent"}
_VALID_KINDS = {"sequence", "situation", "hook", "emotion_arc", "trope", "pattern", "scheme"}

# D-W8-MOTIF-BEAT-LLM-EXTRACTOR — how many of the user's visible motifs form the tag-beats
# vocabulary. The whole seeded system catalog (~60) + a user's own motifs fits comfortably in
# the classifier prompt (the engine lists code+name+summary per code); cap so a power user with
# hundreds of motifs can't blow the context. System rows sort first (NULLS FIRST), so the cap
# keeps the canonical packs even when truncating a large personal library.
_MINE_CATALOG_LIMIT = 200


# ── beat-symbol encoding (the PrefixSpan alphabet) ───────────────────────────────────
def _beat_symbol(beat: Any) -> str | None:
    """Map ONE timeline beat-step to a canonical comparison symbol (the PrefixSpan
    item). A motif is a recurring shape of (beat, thread) — the role MENTIONS are the
    concrete cast (Story A's hero ≠ Story B's hero), so they are EXCLUDED from the
    symbol; mining over (beat, thread) is what makes a pattern reusable across books.
    A malformed step → None (skipped, never crashes the miner)."""
    if not isinstance(beat, dict):
        return None
    label = str(beat.get("beat") or "").strip().lower()
    if not label:
        return None
    thread = str(beat.get("thread") or "").strip().lower()
    return f"{thread}:{label}" if thread else label


def _encode_sequences(raw_sequences: list[list[dict[str, Any]]]) -> list[list[str]]:
    """Each raw beat sequence → a list of canonical symbols (drop malformed steps).
    Empty sequences are dropped (nothing to mine)."""
    out: list[list[str]] = []
    for seq in raw_sequences:
        if not isinstance(seq, list):
            continue
        symbols = [s for s in (_beat_symbol(b) for b in seq) if s is not None]
        if symbols:
            out.append(symbols)
    return out


# ── PrefixSpan: frequent SEQUENTIAL pattern mining (pure, unit-tested) ───────────────
def _is_subsequence(pattern: tuple[str, ...], sequence: list[str]) -> bool:
    """True iff `pattern` appears as an ORDERED (not necessarily contiguous)
    subsequence of `sequence` — the sequential-pattern containment relation."""
    it = iter(sequence)
    return all(any(sym == p for sym in it) for p in pattern)


def _support(pattern: tuple[str, ...], sequences: list[list[str]]) -> int:
    """The support of a pattern = the number of input sequences that CONTAIN it as an
    ordered subsequence (sequence-frequency, not occurrence-count — one sequence
    counts once even if the pattern recurs within it)."""
    return sum(1 for s in sequences if _is_subsequence(pattern, s))


def prefixspan(
    sequences: list[list[str]], *, min_support: int, max_len: int = 8,
) -> list[tuple[tuple[str, ...], int]]:
    """A PrefixSpan-style frequent sequential-pattern miner over single-item
    sequences (each step is one symbol — the (thread:beat) encoding above).

    Returns ``[(pattern, support), …]`` for every pattern of length ≥ 2 whose
    support ≥ ``min_support`` (a length-1 "pattern" is a single beat, not a motif —
    a motif is a recurring multi-beat SHAPE, so singletons are not candidates).
    Sorted by support desc then pattern, deterministic. ``max_len`` bounds the
    recursion depth (a runaway-long pattern is not a useful motif).

    The classic PrefixSpan recursion: for a given prefix, project each containing
    sequence to the suffix AFTER the prefix's last match, count the locally-frequent
    next-items in those projections, and recurse on each frequent extension. This
    avoids the 2^|items| candidate-generation blow-up of naive Apriori."""
    if min_support < 1:
        min_support = 1
    results: list[tuple[tuple[str, ...], int]] = []

    def _project(prefix_last_matched: list[list[str]]) -> dict[str, int]:
        """Count next-item sequence-frequencies in the projected databases."""
        counts: dict[str, int] = {}
        for suffix in prefix_last_matched:
            for sym in set(suffix):     # set() → one count per projected sequence
                counts[sym] = counts.get(sym, 0) + 1
        return counts

    def _recurse(prefix: tuple[str, ...], projections: list[list[str]]) -> None:
        if len(prefix) >= max_len:
            return
        for sym, sup in _project(projections).items():
            if sup < min_support:
                continue
            new_prefix = prefix + (sym,)
            # Re-project: each sequence → the suffix AFTER this sym's first match.
            new_projections: list[list[str]] = []
            for suffix in projections:
                try:
                    idx = suffix.index(sym)
                except ValueError:
                    continue
                new_projections.append(suffix[idx + 1:])
            if len(new_prefix) >= 2:
                results.append((new_prefix, sup))
            _recurse(new_prefix, new_projections)

    _recurse((), list(sequences))
    # Deterministic order: support desc, then the pattern itself.
    results.sort(key=lambda r: (-r[1], r[0]))
    return results


# ── the abstraction prompt (generic role slots, no source proper nouns) ──────────────
def build_abstraction_messages(
    pattern: tuple[str, ...], *, support: int, language: str,
) -> tuple[str, str]:
    """(system, user) for abstracting ONE frequent beat-pattern into a reusable motif
    spec. The pattern is already de-identified (thread:beat symbols — no proper
    nouns), but the prompt RE-STATES the §12.6 abstraction rule so the generated
    name/summary/roles never reintroduce a source name."""
    system = (
        "You turn a recurring ABSTRACT beat-pattern mined from a body of stories into "
        "ONE reusable narrative MOTIF. STRICT RULES: "
        "(1) Use only GENERIC role slots ('protagonist', 'rival', 'mentor', 'the-faction') "
        "— NEVER a specific character/place/work name. "
        "(2) The beats are generic labels — never a sentence copied from any source. "
        "Return ONLY a JSON object: "
        '{"code": str, "name": str, '
        '"kind": "sequence"|"situation"|"hook"|"emotion_arc"|"trope"|"pattern"|"scheme", '
        '"summary": str, '
        '"roles": [{"key": str, "actant": "subject"|"object"|"sender"|"receiver"|"helper"|"opponent", "label": str}], '
        '"beats": [{"key": str, "label": str, "intent": str, "order": int}], '
        '"preconditions": [str], "effects": [str]}.'
    )
    steps = " → ".join(pattern)
    user = (
        f"MINED BEAT-PATTERN (recurs across {support} of your stories, language "
        f"'{language}'): {steps}\n\n"
        "Each step is 'thread:beat'. Abstract this into one generic, reusable motif. "
        "Emit no names — generic role slots only."
    )
    return system, user


# ── the binary judge prompt (§11 no-silent-drop — every candidate is scored + shown) ──
def build_judge_messages(spec: dict[str, Any]) -> tuple[str, str]:
    """(system, user) for the BINARY quality judge over an abstracted candidate motif.
    The judge returns a 0..1 score + a verdict; the orchestration gates on
    ``motif_mine_min_judge`` but SHOWS every candidate with its score (no silent
    drop). A distinct judge model_ref is the caller's anti-self-reinforcement choice."""
    system = (
        "You are a strict binary judge of mined narrative motifs. A GOOD motif is "
        "abstract (generic roles, no proper nouns), coherent (the beats form a "
        "recognizable reusable shape), and non-trivial (not one obvious beat). "
        "Return ONLY a JSON object: "
        '{"score": number (0.0..1.0), "verdict": "pass"|"fail", "reason": str}.'
    )
    name = str(spec.get("name") or "")
    summary = str(spec.get("summary") or "")
    beats = [str((b or {}).get("label") or "") for b in (spec.get("beats") or []) if isinstance(b, dict)]
    user = (
        f"CANDIDATE MOTIF:\nname: {name}\nsummary: {summary}\n"
        f"beats: {' → '.join(b for b in beats if b)}\n\n"
        "Score its quality 0.0..1.0 and give a pass/fail verdict."
    )
    return system, user


# ── arg-builders (the abstract spec → validated MotifCreateArgs; mirror W9) ───────────
def _slug(value: Any, fallback: str) -> str:
    s = re.sub(r"[^a-z0-9._-]+", "-", str(value or "").strip().lower()).strip("-.")
    return s or fallback


def _coerce_actant(value: Any) -> str:
    v = str(value or "").strip().lower()
    return v if v in _VALID_ACTANTS else "subject"


def _motif_args(spec: dict[str, Any], *, index: int, language: str) -> MotifCreateArgs:
    """The abstracted spec → a validated MotifCreateArgs (private; the repo stamps
    owner + source='mined' + status='draft'). Coercions mirror W9's deconstruct so a
    garbled-but-parseable frame never crashes the persist."""
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
            order=int(b.get("order") if isinstance(b.get("order"), int) else i),
        )
        for i, b in enumerate(spec.get("beats") or []) if isinstance(b, dict)
    ]
    preconds = [{"text": str(p)[:2000]} for p in (spec.get("preconditions") or []) if p]
    effects = [{"text": str(e)[:2000]} for e in (spec.get("effects") or []) if e]
    kind = spec.get("kind") if spec.get("kind") in _VALID_KINDS else "sequence"
    return MotifCreateArgs(
        code=_slug(spec.get("code"), f"mined.motif-{index}"),
        name=str(spec.get("name") or f"Mined Motif {index + 1}")[:500],
        language=language,
        kind=kind,
        summary=str(spec.get("summary") or "")[:20000],
        roles=roles,
        beats=beats,
        preconditions=preconds,
        effects=effects,
        visibility="private",
    )


def _judge_score(content: str) -> float:
    """Parse the judge frame → a clamped 0..1 score. A garbled/absent frame → 0.0
    (so it is SHOWN below the gate, never silently passed)."""
    obj = parse_critique_json(content) or {}
    raw = obj.get("score")
    try:
        score = float(raw)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, score))


# ── the PURE orchestration (knowledge + llm + repo injected → unit-testable) ──────────
async def mine_motifs(
    *, knowledge, llm: LLMClient, motif_repo, user_id: str,
    scope: str, book_id: UUID | None, language: str,
    min_support: int, min_judge: float,
    model_source: str, model_ref: str,
) -> dict[str, Any]:
    """Pure mining: fetch beat sequences → PrefixSpan → per-candidate LLM abstraction
    → binary judge → persist gate-passers as drafts. knowledge/llm/motif_repo are
    injected so this is unit-testable with FAKES (no DB / no real gateway / no
    knowledge-service).

    Fails closed (ValueError) on an empty model_ref (provider-gateway invariant: a
    mine never silently runs on an unconfigured model). Degrades — NOT raises — when
    the deferred ``motif_beat`` extractor returns no sequences
    (``reason: 'beat_extractor_unavailable'``).

    §11 NO SILENT DROP: ``candidates`` lists EVERY abstracted candidate with its
    ``judge_score`` + ``passed_gate``; only gate-passers are persisted."""
    if not model_ref:
        raise ValueError(
            "mine_motifs: no abstraction model_ref resolved "
            "(set motif_deconstruct_model_ref or pass model_ref on the job)"
        )

    raw_sequences = await knowledge.get_motif_beat_sequences(
        UUID(user_id),
        book_id=book_id, corpus=(scope == "corpus"), language=language,
    )
    sequences = _encode_sequences(raw_sequences or [])
    if not sequences:
        # The deferred extractor (or a genuinely empty corpus) yielded nothing —
        # DEGRADE cleanly so the job completes instead of crashing (D-W8-MOTIF-BEAT-
        # EXTRACTOR). The path is fully wired; it goes live when the extractor ships.
        return {
            "mined": 0,
            "reason": "beat_extractor_unavailable",
            "extractor_version": settings.motif_mine_extractor_version,
            "scope": scope,
            "sequences": 0,
            "candidates": [],
        }

    patterns = prefixspan(sequences, min_support=min_support)
    if not patterns:
        return {
            "mined": 0,
            "reason": "no_frequent_patterns",
            "scope": scope,
            "sequences": len(sequences),
            "min_support": min_support,
            "candidates": [],
        }

    candidates: list[dict[str, Any]] = []
    persisted_ids: list[str] = []
    for idx, (pattern, support) in enumerate(patterns):
        # 1) abstraction.
        sys_a, usr_a = build_abstraction_messages(pattern, support=support, language=language)
        job = await llm.submit_and_wait(
            user_id=user_id, operation="chat",
            model_source=model_source, model_ref=model_ref,
            input={
                "messages": [{"role": "system", "content": sys_a},
                             {"role": "user", "content": usr_a}],
                "response_format": {"type": "text"}, "temperature": 0.3,
                "max_tokens": 1024,
            },
            job_meta={"extractor": "motif_mine", "pattern": list(pattern)},
        )
        if getattr(job, "status", None) != "completed":
            logger.warning("mine: abstraction not completed for pattern=%s: %s",
                           pattern, getattr(job, "status", None))
            candidates.append({
                "pattern": list(pattern), "mining_support": support,
                "judge_score": 0.0, "passed_gate": False,
                "status": "abstraction_failed",
            })
            continue
        parsed = parse_critique_json(extract_judge_content(job.result))
        spec = parsed or {}
        # MED-5 (/review-impl): a COMPLETED job whose frame won't parse yields {} — the
        # candidate is still SHOWN (§11), but tag it so a reviewer can tell "model judged
        # it weak" from "we couldn't parse the model".
        unparseable = not parsed

        # 2) binary judge.
        sys_j, usr_j = build_judge_messages(spec)
        judge_job = await llm.submit_and_wait(
            user_id=user_id, operation="chat",
            model_source=model_source, model_ref=model_ref,
            input={
                "messages": [{"role": "system", "content": sys_j},
                             {"role": "user", "content": usr_j}],
                "response_format": {"type": "text"}, "temperature": 0.0,
                "max_tokens": 256,
            },
            job_meta={"extractor": "motif_mine_judge", "pattern": list(pattern)},
        )
        score = (
            _judge_score(extract_judge_content(judge_job.result))
            if getattr(judge_job, "status", None) == "completed" else 0.0
        )
        passed = score >= min_judge

        entry: dict[str, Any] = {
            "pattern": list(pattern),
            "mining_support": support,
            "name": str(spec.get("name") or ""),
            "judge_score": round(score, 4),
            "passed_gate": passed,
        }
        if unparseable:
            entry["status"] = "abstraction_unparseable"

        # 3) persist ONLY gate-passers (drafts); the rest are SHOWN, never dropped.
        if passed:
            args = _motif_args(spec, index=idx, language=language)
            try:
                motif: Motif = await motif_repo.create(
                    UUID(user_id), args,
                    source="mined", status="draft",
                    judge_score=Decimal(str(round(score, 4))), mining_support=support,
                )
            except asyncpg.UniqueViolationError:
                # MED-6 (/review-impl): a (owner, code, language) collision (a re-run, or
                # two patterns abstracting to the same slug) must NOT crash the whole job
                # and lose every other candidate (the §11 no-silent-drop guarantee). Mark
                # this one persisted=False + keep going; the user can re-mine / rename.
                logger.info("mine: code collision persisting candidate idx=%d (skipped)", idx)
                entry["passed_gate"] = True
                entry["persisted"] = False
                entry["status"] = "code_collision"
                candidates.append(entry)
                continue
            entry["motif_id"] = str(motif.id)
            entry["code"] = motif.code
            entry["persisted"] = True
            persisted_ids.append(str(motif.id))
        candidates.append(entry)

    below_gate = sum(1 for c in candidates if not c["passed_gate"])
    return {
        "mined": len(persisted_ids),
        "motif_ids": persisted_ids,
        "scope": scope,
        "language": language,
        "sequences": len(sequences),
        "patterns": len(patterns),
        "min_support": min_support,
        "min_judge": min_judge,
        # §11 no-silent-drop: EVERY candidate is here with its score + gate flag.
        "candidates": candidates,
        "below_gate": below_gate,
        "promote_to": "user",
    }


async def run_mine_motifs(
    pool: asyncpg.Pool, llm: LLMClient, knowledge, *, user_id: str, input: dict[str, Any]
) -> dict[str, Any]:
    """Mine recurring motif beat-patterns from the user's own corpus/book → draft
    motifs. See module docstring for the frozen input envelope. Raises ``ValueError``
    (a terminal business error — the job is marked failed cleanly, never an infra
    redeliver loop) on a missing book_id (scope='book') or an unconfigured model.

    Degrades (job COMPLETES with ``mined: 0, reason: 'beat_extractor_unavailable'``)
    when the deferred knowledge-service ``motif_beat`` extractor returns nothing —
    so the path is live + drivable the moment the extractor ships."""
    scope = str(input.get("scope") or "book")
    book_id: UUID | None = None
    if scope == "book":
        try:
            book_id = UUID(str(input["book_id"]))
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError("mine_motifs: scope='book' requires a valid book_id") from exc
    language = str(input.get("language") or "en")
    # min_support: the job input wins (the user's confirm choice), else the platform
    # default; floored at 2 (a length-≥2 pattern needs ≥2 sequences to be "frequent").
    min_support = int(input.get("min_support") or settings.motif_mine_min_support)
    if min_support < 2:
        min_support = 2
    min_judge = float(settings.motif_mine_min_judge)

    # Resolve the abstraction/judge model: job input wins (a future per-call override),
    # else the platform deconstruct default (the only platform chat-model config — W8
    # shares the deconstruct model rather than adding a duplicate knob). NO hardcoded
    # literal (provider-gateway invariant); mine_motifs() fails closed if both empty.
    model_source = str(input.get("model_source") or settings.motif_deconstruct_model_source)
    model_ref = str(input.get("model_ref") or settings.motif_deconstruct_model_ref)

    from app.db.repositories.motif_repo import MotifRepo

    motif_repo = MotifRepo(pool)

    # D-W8-MOTIF-BEAT-LLM-EXTRACTOR — tag the :Event corpus into the user's visible motif
    # catalog FIRST (operation=chat via the BYOK model), so motif-beats emits GENERIC
    # namespace:local axes and PrefixSpan mines reusable motif-sequences rather than one-off
    # concrete titles. ADVISORY + best-effort: skipped when no model resolved (mine_motifs then
    # fails closed on the same empty model_ref), and any tagging error degrades to the Option-A
    # axes — never breaks the mine. Only the catalog the user can actually see is the vocab
    # (system + their own motifs); a cross-user motif can never enter it.
    if model_ref:
        try:
            catalog = await motif_repo.list_for_caller(
                UUID(user_id), scope="all", status="active", limit=_MINE_CATALOG_LIMIT,
            )
            vocab = [{"code": m.code, "name": m.name, "summary": m.summary} for m in catalog]
            if vocab:
                result = await knowledge.tag_beats(
                    UUID(user_id), book_id=book_id, corpus=(scope == "corpus"),
                    motifs=vocab, model_source=model_source, model_ref=model_ref,
                )
                logger.info("mine_motifs: tag-beats over %d-motif catalog → %s",
                            len(vocab), result.get("tagged") if isinstance(result, dict) else "?")
        except Exception as exc:  # advisory — tagging never fails the mine (Option-A fallback)
            logger.warning("mine_motifs: tag-beats pre-pass failed (Option-A fallback): %r", exc)

    return await mine_motifs(
        knowledge=knowledge,
        llm=llm,
        motif_repo=motif_repo,
        user_id=user_id,
        scope=scope,
        book_id=book_id,
        language=language,
        min_support=min_support,
        min_judge=min_judge,
        model_source=model_source,
        model_ref=model_ref,
    )
