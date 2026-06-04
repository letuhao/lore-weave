"""LE-PROD slice D — eval-suite DE-BIAS (profile-driven scorers + judge).

The C15 eval was Fengshen-hardcoded (anachronism 商周 markers, CJK-faithfulness,
location dims, 封神 judge rubric), so the gate that unlocks P2/P3 could never pass
for a NON-Fengshen book. These tests pin the de-biased behavior: with a per-book
profile the scorers/judge use the book's OWN dims / language / markers / worldview;
``profile=None`` keeps the legacy Fengshen behavior (covered by the existing eval
tests, asserted here for the run_eval default path)."""

from __future__ import annotations

import pytest

from app.db.book_profile import BookProfile
from app.eval import scorers
from app.eval.judge_usefulness import (
    USEFULNESS_RUBRIC_ZH,
    build_usefulness_rubric,
)
from app.eval.runner import run_eval
from app.eval.scorers import ScorableProposal
from app.eval.suite import load_suite
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SUITE = load_suite(REPO_ROOT / "eval" / "enrichment-eval-suite.toml")


# ── score_schema: dims + language-faithfulness are parameters ────────────────────

def _en_character_prop(**over) -> ScorableProposal:
    base = dict(
        name="Merlin",
        entity_kind="character",
        dimensions={  # English content for an English book's character dims
            "Appearance": "An aged man in star-flecked robes, eyes sharp as flint.",
            "Personality": "Wry, patient, prone to riddles; loyal to the young king.",
            "Abilities": "Prophecy, shapeshifting, mastery of the old magics.",
        },
        origin="enrichment", technique="retrieval", confidence=0.30,
        review_status="proposed", pending_validation=True,
        source_refs=[{"corpus_id": "c1", "chunk_id": "k1", "score": 0.8}],
        provenance={"technique": "retrieval", "model_ref": "r1", "canon_verify": {"flags": []}},
        canon_verify={"flags": []},
    )
    base.update(over)
    return ScorableProposal(**base)


def test_schema_english_content_not_penalized_when_cjk_not_required():
    # A non-Chinese book: English content for the kind's dims scores full when
    # require_cjk=False (legacy default would have flagged "not Chinese-faithful").
    p = _en_character_prop()
    s, issues = scorers.score_schema(
        p,
        required_dims=("Appearance", "Personality", "Abilities"),
        optional_dims=("Relationships", "Background"),
        require_cjk=False,
    )
    assert s == 75.0  # 3/3 required (60) + valid lifecycle (15); optional absent
    assert not any("not Chinese-faithful" in i for i in issues)


def test_schema_legacy_default_still_penalizes_english_in_zh_dim():
    # profile=None / default path: English in a Chinese-required dim is still flagged.
    p = _en_character_prop(dimensions={"历史": "This is English prose, not Chinese at all."})
    s, issues = scorers.score_schema(p)  # legacy Fengshen defaults (require_cjk=True)
    assert any("not Chinese-faithful" in i for i in issues)


# ── score_anachronism: markers are a parameter (EMPTY ⇒ off) ─────────────────────

def test_anachronism_empty_markers_is_off():
    # A sci-fi / modern book (no markers): "modern" content is NOT an anachronism.
    p = _en_character_prop(dimensions={"x": "She boarded the 汽车 and called on her 手机."})
    score, issues = scorers.score_anachronism(p, markers=())
    assert score == 100.0 and issues == []


def test_anachronism_custom_markers_fire():
    p = _en_character_prop(dimensions={"x": "a phaser and a starship"})
    score, issues = scorers.score_anachronism(p, markers=("phaser", "starship"))
    assert score == 50.0  # two distinct hits, -25 each
    assert len(issues) == 2


# ── build_usefulness_rubric: profile-driven ─────────────────────────────────────

def test_rubric_none_is_legacy_fengshen():
    assert build_usefulness_rubric(None) == USEFULNESS_RUBRIC_ZH


def test_rubric_zh_profile_uses_book_worldview_not_hardcoded_fengshen():
    r = build_usefulness_rubric(
        BookProfile(language="zh", worldview="紅樓夢"), kind_label="人物"
    )
    assert "紅樓夢" in r and "封神" not in r


def test_rubric_non_zh_profile_is_english():
    r = build_usefulness_rubric(
        BookProfile(language="en", worldview="Camelot"), kind_label="character"
    )
    assert "reviewer" in r.lower() and "Camelot" in r and "封神" not in r


# ── P3a: vendored Fleiss-κ fallback matches the SDK (in-container eval) ──────────

def test_vendored_kappa_matches_sdk_and_landis_koch():
    from app.eval import _ensemble_shim as shim

    samples = [
        [{"a": 2, "b": 1}, {"a": 3}, {"a": 1, "b": 2}],   # mixed
        [{"x": 3}, {"x": 3}, {"x": 3}],                     # unanimous single label
        [{"a": 2, "b": 1}, {"b": 2, "a": 1}],              # split
    ]
    try:
        from loreweave_eval.judge_ensemble import _fleiss_kappa as sdk_fk
    except Exception:  # pragma: no cover — SDK absent (in-container): vendored is the source
        sdk_fk = None
    for iv in samples:
        v = shim._vendored_fleiss_kappa(iv, 3)
        if sdk_fk is not None:
            assert round(v, 9) == round(sdk_fk(iv, 3), 9)
    # Landis–Koch cutoffs
    assert shim._vendored_kappa_interpretation(-0.1) == "below-chance"
    assert shim._vendored_kappa_interpretation(0.5) == "moderate"
    assert shim._vendored_kappa_interpretation(0.95) == "almost-perfect"


def test_shim_always_resolves_callables():
    from app.eval import _ensemble_shim as shim

    assert callable(shim.fleiss_kappa) and callable(shim.kappa_interpretation)


# ── run_eval threads the profile end-to-end ─────────────────────────────────────

@pytest.mark.asyncio
async def test_run_eval_with_en_profile_does_not_penalize_modern_or_english():
    # An English modern book: empty markers (anachronism off) + require_cjk=False →
    # the deterministic sub-scores do not punish era-appropriate English content.
    prof = BookProfile(language="en", worldview="A near-future thriller")
    p = _en_character_prop(
        dimensions={
            "Appearance": "Lean, augmented eyes, a worn flight jacket.",
            "Personality": "Cynical pilot with a soft spot for strays.",
            "Abilities": "Crack 汽车 driver — drives a car, flies a drone.",
        }
    )
    out = await run_eval([p], SUITE, profile=prof)
    # anachronism off (no markers) → 100; schema didn't flag English/CJK.
    assert out.scorecard.subscores["anachronism"] == 100.0
    assert not any("Chinese-faithful" in i for i in out.scorecard.issues)
    # CENTRAL INVARIANT (slice D): the eval resolved the character KIND's en labels
    # (Appearance/Personality/Abilities) and they MATCHED the proposal's keys — so
    # schema FOUND the 3 required dims (60) + valid lifecycle (15) = 75, NOT a
    # silent 0-for-"missing" from a label mismatch.
    assert out.scorecard.subscores["schema"] == 75.0
    assert not any("missing/empty" in i for i in out.scorecard.issues)
