"""F0 — the motif library FROZEN-contract tests (pure unit, no DB).

These assert the parallelization contract Wave-1 builds against: the repo +
retriever method signatures (the exact parameter names), the ForbidExtra write
guard (audit S2), the MotifCandidate shape, model round-trips, and the B-1
"one platform embedding model" shape (no per-row model choice on a write arg).

Once F0 merges these signatures are FROZEN — a WS that needs a new field files a
follow-up against F0, never edits it mid-wave.
"""

from __future__ import annotations

import inspect
import uuid

import pytest

from app.db.models import (
    ArcTemplate,
    ImportSource,
    Motif,
    MotifApplication,
    MotifCandidate,
    MotifCreateArgs,
    MotifLink,
    MotifPatchArgs,
)
from app.db.repositories.motif_repo import MotifRepo
from app.db.repositories.motif_retrieve import MotifRetriever


def _params(fn) -> list[str]:
    return list(inspect.signature(fn).parameters)


# ── the frozen repo signatures (§3) ────────────────────────────────────────────
def test_motif_repo_signatures_frozen():
    # The POSITIONAL contract is frozen (owner is NEVER a positional arg — it is
    # server-stamped = user_id). W8/W9 added provenance/book kwargs ADDITIVELY (see
    # MotifRepo.create docstring); assert the additive convention, matching
    # list_for_caller/clone below — not an exact `==` that a documented additive
    # follow-up must break.
    create_params = _params(MotifRepo.create)
    assert create_params[:3] == ["self", "user_id", "args"]
    for kw in ("source", "imported_derived", "status", "book_id", "book_shared"):
        assert kw in create_params, f"create missing kw '{kw}'"
    assert _params(MotifRepo.get_visible) == ["self", "caller_id", "motif_id"]
    # patch: positional + required `expected_version` frozen; repin_* added additively.
    patch_params = _params(MotifRepo.patch)
    assert patch_params[:4] == ["self", "caller_id", "motif_id", "args"]
    assert "expected_version" in patch_params
    assert _params(MotifRepo.archive) == ["self", "caller_id", "motif_id"]
    list_params = _params(MotifRepo.list_for_caller)
    assert list_params[:2] == ["self", "caller_id"]
    for kw in ("scope", "genre", "kind", "status", "q", "language", "limit"):
        assert kw in list_params, f"list_for_caller missing kw '{kw}'"
    clone_params = _params(MotifRepo.clone)
    assert clone_params[:3] == ["self", "caller_id", "src_motif_id"]
    for kw in ("target_owner", "retag_genres"):
        assert kw in clone_params, f"clone missing kw '{kw}'"


def test_motif_retriever_signature_frozen():
    params = _params(MotifRetriever.retrieve)
    assert params[:2] == ["self", "caller_id"]
    for kw in (
        "book_id", "project_id", "genre_tags", "language",
        "beat_role", "tension", "prev_effects", "limit",
    ):
        assert kw in params, f"retrieve missing kw '{kw}'"


async def test_retriever_is_implemented_w3():
    """W3 replaced F0's NotImplementedError stub with the real impl. retrieve() over an
    empty pre-filter returns [] (no candidates) — NOT a NotImplementedError. The deep
    behavior (pre-filter bound, cosine rank, degrade, NULL-skip) is covered in
    tests/unit/test_motif_retrieve.py + tests/integration/db/test_motif_retrieve_db.py."""

    class _EmptyConn:
        async def fetch(self, _sql, *_args):
            return []

    class _Acquire:
        async def __aenter__(self):
            return _EmptyConn()

        async def __aexit__(self, *_exc):
            return False

    class _Pool:
        def acquire(self):
            return _Acquire()

    retr = MotifRetriever(_Pool())  # type: ignore[arg-type]
    out = await retr.retrieve(
        uuid.uuid4(), book_id=uuid.uuid4(), project_id=uuid.uuid4(),
        genre_tags=["xianxia"], language="en", beat_role="hook", tension=3,
    )
    assert out == []


# ── ForbidExtra write guard (audit S2) ─────────────────────────────────────────
def test_create_args_forbid_extra_and_no_owner_or_embed_field():
    # a clean create validates.
    MotifCreateArgs(code="c", name="N")
    # owner_user_id is NOT a write arg (the repo stamps it) → rejected.
    with pytest.raises(Exception):
        MotifCreateArgs(code="c", name="N", owner_user_id=str(uuid.uuid4()))
    # B-1: there is NO per-row embedding-model arg (the model is platform config).
    fields = set(MotifCreateArgs.model_fields)
    assert "embedding_model" not in fields
    assert "embedding" not in fields
    assert "embedding_model_source" not in fields and "embedding_model_ref" not in fields


def test_patch_args_forbid_extra_and_immutable_identity():
    MotifPatchArgs(name="new")
    # code/language/source/owner are identity/lineage — not patchable here.
    for forbidden in ("code", "language", "source", "owner_user_id"):
        with pytest.raises(Exception):
            MotifPatchArgs(**{forbidden: "x"})


# ── model round-trips + MotifCandidate shape ───────────────────────────────────
def _sample_motif() -> Motif:
    return Motif(id=uuid.uuid4(), code="cultivation.fortuitous_encounter", name="Lucky Break")


def test_motif_roundtrips_json():
    m = _sample_motif()
    again = Motif.model_validate(m.model_dump(mode="json"))
    assert again.code == m.code
    assert again.annotations == {}  # RECONCILE D1 default


def test_motif_candidate_shape():
    cand = MotifCandidate(
        motif=_sample_motif(), score=0.42,
        match_reason={"tension": 1.0, "genre": 0.5, "precond": 1.0, "cosine": 0.42},
    )
    dumped = cand.model_dump(mode="json")
    assert dumped["score"] == 0.42
    assert set(dumped["match_reason"]) == {"tension", "genre", "precond", "cosine"}
    assert dumped["motif"]["code"] == "cultivation.fortuitous_encounter"


def test_row_models_construct():
    """The other frozen row models construct + round-trip (W9/W10/W2 consume)."""
    MotifLink(id=uuid.uuid4(), from_motif_id=uuid.uuid4(), to_motif_id=uuid.uuid4(), kind="precedes")
    MotifApplication(
        id=uuid.uuid4(), created_by=uuid.uuid4(), project_id=uuid.uuid4(), book_id=uuid.uuid4(),
    )
    ArcTemplate(id=uuid.uuid4(), code="arc.revenge", name="Revenge Arc")
    ImportSource(id=uuid.uuid4(), owner_user_id=uuid.uuid4(), content="raw text")
