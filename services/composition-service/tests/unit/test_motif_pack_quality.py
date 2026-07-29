"""Seed-pack QUALITY gates — the bar the 2026-07-29 audit established, made repeatable.

`test_seed_motifs.py` proves a pack is VALID (schema, ids, acyclic links, no banned nouns).
Valid is not good. This file holds the content bars that a real audit found the first genre
expansion silently missing, so the next person adding a pack cannot repeat them:

  1. PRECOND↔EFFECT LINKAGE. `_precond_overlap` is Jaccard TOKEN overlap between a
     predecessor's `effects` and a successor's `preconditions`, and it is surfaced to the
     author as the "Setup" match-reason chip. Written as independent prose it scores 0.00 —
     which renders as "these two have no connection" on a pair that is explicitly chained.
     Measured: the original packs averaged 0.127 with 1 dead edge; the first draft of the new
     packs averaged 0.056 with 6. The fix is authoring discipline — state a successor's
     precondition in the predecessor's own nouns.

  2. NO ORPHAN TENSION. A genre motif with a flat or 1-2 beat curve gives the scene decomposer
     nothing to honour. (`hook` is exempt by design — §2.4 makes hooks single-beat.)

The embedding-space bars (self-retrieval recall@15, pack separation) need a live embed model
and a seeded DB, so they live in `scripts/motif_quality_audit.py` rather than here.
"""

from __future__ import annotations

import json

import pytest

from app.db.repositories.motif_retrieve import _precond_overlap
from app.db.seed_motifs import _MOTIF_PACKS, _read_pack

# The original five packs cleared 0.127 mean. Hold new work to a floor comfortably under that
# but far above the 0.056 the first draft scored — the point is to catch prose written without
# the handshake, not to force a target.
_MIN_MEAN_OVERLAP = 0.08
_CONNECTIVE_KINDS = {"hook", "emotion_arc"}


@pytest.fixture(scope="module")
def by_code() -> dict:
    out = {}
    for pack in _MOTIF_PACKS:
        if pack.endswith("_vi"):
            continue                      # links are language-invariant; measure the en side
        for row in _read_pack(pack):
            out[row["code"]] = row
    return out


@pytest.fixture(scope="module")
def precedes_edges() -> list:
    return [e for e in _read_pack("links") if e["kind"] == "precedes"]


def _overlap_for(edge: dict, by_code: dict) -> float:
    frm, to = by_code[edge["from_code"]], by_code[edge["to_code"]]
    return _precond_overlap(
        to.get("preconditions", []),
        [e.get("text", "") for e in frm.get("effects", [])],
    )


def test_no_precedes_edge_is_a_dead_handshake(by_code, precedes_edges):
    """Every chained pair must share SOME vocabulary between effect and precondition.

    A 0.00 here is not cosmetic: the pair is declared to chain, and the author is shown a
    Setup score of 0 for it. Either the texts should meet, or the edge should not exist."""
    dead = [(e["from_code"], e["to_code"]) for e in precedes_edges
            if _overlap_for(e, by_code) == 0.0]
    assert not dead, (
        "precedes edges whose effect/precondition texts share no tokens — state the "
        f"successor's precondition in the predecessor's own nouns: {dead}")


def test_precond_linkage_holds_the_authoring_bar(by_code, precedes_edges):
    mean = sum(_overlap_for(e, by_code) for e in precedes_edges) / len(precedes_edges)
    assert mean >= _MIN_MEAN_OVERLAP, (
        f"mean effect→precondition overlap {mean:.3f} is below the {_MIN_MEAN_OVERLAP} bar; "
        "chained motifs are being written as independent prose")


def test_genre_motifs_have_a_curve_to_honour(by_code):
    """Flat or near-empty beat curves give the scene decomposer nothing. Hooks are exempt:
    §2.4 defines them as single-beat connective tissue, which is why the first pass of this
    audit reported 13 false positives before the exemption was made explicit."""
    flat = []
    for code, row in by_code.items():
        if row.get("kind") in _CONNECTIVE_KINDS:
            continue
        beats = row.get("beats", [])
        curve = [b.get("tension_target") for b in beats]
        if len(beats) < 3 or len({t for t in curve if t is not None}) <= 1:
            flat.append((code, curve))
    assert not flat, f"genre motifs with no usable tension shape: {flat}"


def test_every_new_pack_row_carries_an_example(by_code):
    """`examples[]` is the author-facing instance of the abstraction, and the audit showed a
    mis-chosen one is a real defect — `rebirth.butterfly_divergence` shipped an example that
    actually illustrated `rebirth.save_what_was_lost`, and self-retrieval caught it at rank 59.
    An absent one cannot be checked at all."""
    missing = [c for c, r in by_code.items()
               if not [e for e in r.get("examples", []) if (e.get("text") or "").strip()]]
    assert not missing, f"motifs with no author-written example: {missing}"


def test_vi_siblings_mirror_their_base_pack_exactly(by_code):
    """A vi pack that drifts from its en base breaks the shared `links.json` manifest (edges
    are emitted per language only where BOTH endpoints exist) and silently halves a language's
    chain coverage."""
    for pack in _MOTIF_PACKS:
        if pack.endswith("_vi"):
            continue
        en = {r["code"] for r in _read_pack(pack)}
        vi = {r["code"] for r in _read_pack(f"{pack}_vi")}
        assert en == vi, (
            f"{pack}_vi drifted from {pack}: "
            f"only-en={sorted(en - vi)} only-vi={sorted(vi - en)}")


def test_pack_rows_are_valid_json_objects_with_stable_keys(by_code):
    """Cheap structural backstop: the packs are hand-edited JSON and a stray key would only
    surface at seed time (or, worse, be silently dropped by the loader's explicit column list)."""
    allowed = {
        "code", "language", "kind", "category", "name", "summary", "genre_tags", "roles",
        "beats", "preconditions", "effects", "info_asymmetry", "annotations",
        "tension_target", "emotion_target", "examples", "source", "source_version",
    }
    for code, row in by_code.items():
        extra = set(row) - allowed
        assert not extra, f"{code} carries key(s) the loader will drop: {sorted(extra)}"
        assert json.dumps(row)          # round-trips
