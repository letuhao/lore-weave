"""W3 — the ONE platform-embedding pipeline for motif vectors (R1.1.2 / B-1).

EVERY motif vector — a created motif's summary (W1), a back-filled seed (W3), and the
retrieval query (W3) — is produced by exactly ONE model: `config.motif_embed_model_*`.
Therefore every cosine in `retrieve()` is between two vectors in the SAME embedding
space; cross-model contamination (audit B-1/A8/A9 — "a user whose embed model != the
seed pack's model gets cosine 0.0 against the entire system tier") is impossible BY
CONSTRUCTION, not by validation. There is no per-Work / per-user / per-row choice for a
motif vector — the model is a single platform credential resolved once, here.

Why a PLATFORM model, not the Work's BYOK model (as `reference_source` uses): motif
retrieval crosses Works, users, and the shared system tier, so a per-Work model would
put the seed pack (embedded once at seed/back-fill time) and a user's adopted clone in
DIFFERENT spaces. R1.1.2 fixes that by fixing the model.

Provider invariant (ENFORCED): the only embed path is provider-registry `/internal/embed`
via `embedding_client` — no provider SDK here, no hardcoded model name (the model is
config). MD-1: the platform model is reached as a BYOK-as-platform credential owned by a
reserved platform user (`config.motif_embed_owner_id`) — the local-rerank precedent.

SEAM with W1/W7 (RECONCILE D4 + §2): a created motif and a seed start with
`embedding = NULL`; `clone()` (F0 `motif_repo`) COPIES the source vector (one model = one
space → copy is correct and cheap). So this module is NOT called on clone. It IS the
text→model→vector chokepoint W1 uses on create, and the lazy back-fill W3 runs on first
retrieve of a NULL-embedding (or hash-stale) row.
"""

from __future__ import annotations

import hashlib
from typing import Any
from uuid import UUID

from app.clients.embedding_client import (
    EmbeddingError,
    EmbeddingResult,
    get_embedding_client,
)
from app.config import settings

__all__ = [
    "EmbedConfigError",
    "motif_summary_text",
    "arc_summary_text",
    "summary_hash",
    "embed_motif_summary",
    "embed_query",
    "embedded_with",
]


class EmbedConfigError(RuntimeError):
    """The platform embed model/owner is unset — W3 fails CLOSED rather than embed
    against an undefined model (which would silently produce un-retrievable vectors).
    Distinct from EmbeddingError (a provider runtime failure)."""


def _platform_embed_model() -> tuple[str, str]:
    """The ONE fixed (model_source, model_ref) for ALL motif vectors (R1.1.2/B-1).

    NOT the Work's BYOK model. Read from `config.motif_embed_model_source/_ref` — the
    single chokepoint that makes cross-model contamination impossible. Fails closed
    (EmbedConfigError) if the ref is unset, so an unconfigured deploy never embeds
    against an empty model id."""
    source = settings.motif_embed_model_source or "platform_model"
    ref = settings.motif_embed_model_ref
    if not ref:
        raise EmbedConfigError(
            "motif_embed_model_ref is unset — the platform embedding model must be "
            "configured before motif vectors can be produced (R1.1.2/B-1)."
        )
    return (source, ref)


def _platform_embed_owner() -> UUID:
    """The reserved platform-owner user id whose provider-registry BYOK credential
    holds the platform embedding model (MD-1 / RECONCILE D2 — the local-rerank
    BYOK-as-platform precedent). Fails closed if unset."""
    raw = settings.motif_embed_owner_id
    if not raw:
        raise EmbedConfigError(
            "motif_embed_owner_id is unset — the platform embed credential owner must "
            "be configured (RECONCILE D2 / MD-1)."
        )
    return UUID(raw)


def motif_summary_text(motif_like: Any) -> str:
    """The canonical text that gets embedded. Stable + deterministic so the hash is
    reproducible: name + summary + the ordered beat labels/intents. Beats are part of
    identity — two motifs with the same summary but different beats embed differently.

    `motif_like` is anything with `.name`, `.summary`, `.beats` (a Motif row model or a
    create-args-derived object); beats may be MotifBeat models or plain dicts."""
    parts: list[str] = [_attr(motif_like, "name"), _attr(motif_like, "summary")]
    for b in (_attr(motif_like, "beats") or []):
        parts.append(_beat_attr(b, "label"))
        parts.append(_beat_attr(b, "intent"))
    return "\n".join(p for p in parts if p).strip()


def arc_summary_text(arc_like: Any) -> str:
    """The canonical text embedded for an arc_template (D-ARC-RETRIEVE). Stable +
    deterministic: name + summary + the ordered thread labels + the member-motif codes
    from the layout. Threads + members ARE part of an arc's identity — two arcs with the
    same summary but different threads/motifs embed differently. Same platform model as
    motifs (B-1: one space), so arc queries and arc vectors stay comparable.

    `arc_like` has `.name`, `.summary`, `.threads` ([{key,label}]), `.layout`
    ([{motif_code,...}]) — an ArcTemplate model or a create-args-derived object."""
    parts: list[str] = [_attr(arc_like, "name"), _attr(arc_like, "summary")]
    for t in (_attr(arc_like, "threads") or []):
        parts.append(_beat_attr(t, "label"))
    for p in (_attr(arc_like, "layout") or []):
        parts.append(_beat_attr(p, "motif_code"))
    return "\n".join(p for p in parts if p).strip()


async def embed_arc_summary(text: str) -> EmbeddingResult:
    """Embed an arc_template's canonical text with the PLATFORM model — the exact same
    path as `embed_motif_summary` (one model, one space, B-1). Kept as a named alias so
    arc back-fill reads clearly at the call site; raises EmbeddingError on a provider
    failure (the retrieve back-fill treats it as best-effort)."""
    return await embed_motif_summary(text)


def summary_hash(text: str) -> str:
    """sha256 of the canonical embed text → `motif.embedded_summary_hash`. The
    staleness guard: hash(current text) != stored hash ⟹ the vector is stale and must
    be re-embedded before it is trusted (data-R8). A stored NULL hash also means stale
    (a seed/created row whose vector was never produced)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def embed_motif_summary(text: str) -> EmbeddingResult:
    """Embed a motif's canonical summary text with the PLATFORM model. Raises
    EmbeddingError (retryable-flagged) on a provider failure — the caller (W1 create /
    W3 back-fill) decides fail-closed vs degrade. NEVER takes a model arg: the model is
    fixed config. A 200 with no embeddings is treated as a (retryable) EmbeddingError so
    an active motif never ends up with a null vector silently."""
    source, ref = _platform_embed_model()
    owner = _platform_embed_owner()
    client = get_embedding_client()
    res = await client.embed(
        user_id=owner, model_source=source, model_ref=ref, texts=[text],
    )
    if not res.embeddings or not res.embeddings[0]:
        raise EmbeddingError("platform embed returned an empty vector", retryable=True)
    return res


async def embed_query(text: str) -> list[float]:
    """Embed a chapter-intent query string with the SAME platform model → the retrieval
    query vector. Returns the bare vector. Raises EmbeddingError (the retrieve() degrade
    branch catches it). Reusing `embed_motif_summary`'s model guarantees the query and
    the candidate vectors are the same space — there is no path that embeds them apart."""
    res = await embed_motif_summary(text)
    return res.embeddings[0]


def embedded_with(model_source: str, model_ref: str) -> bool:
    """True iff (source, ref) is the current platform motif-embed model. Lets a caller
    (a back-fill / an audit) confirm a stored vector is in the live space before trusting
    its cosine. A vector embedded with a DIFFERENT model is stale w.r.t. the platform
    space and must be re-embedded."""
    try:
        return (model_source, model_ref) == _platform_embed_model()
    except EmbedConfigError:
        return False


# ── internals ────────────────────────────────────────────────────────────────────
def _attr(obj: Any, name: str) -> str:
    val = obj.get(name) if isinstance(obj, dict) else getattr(obj, name, "")
    return val or ""


def _beat_attr(beat: Any, name: str) -> str:
    if isinstance(beat, dict):
        return beat.get(name) or ""
    return getattr(beat, name, "") or ""
