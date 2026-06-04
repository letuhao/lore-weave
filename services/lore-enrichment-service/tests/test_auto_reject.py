"""C3 — hybrid defense: AUTO-REJECT the egregious (spec 2026-06-01).

`decide_auto_reject` is the pure egregiousness classifier over a VerifyResult.
Per the PO ruling, a proposal is auto-rejected (terminal `rejected`, never canon —
H0-safe) iff it carries:
  * ANY injection flag (a neutralized payload is never legitimate lore), OR
  * a CONTRADICTION flag at HIGH severity (direct canon negation), OR
  * >= 2 DISTINCT anachronism markers (one marker stays advisory).
Everything else stays advisory (flag-for-human). The verifier itself stays
annotation-only; this decision lives in `wiring.py`.
"""

from __future__ import annotations

from app.generation.provenance import SourceRef, make_enriched_fact
from app.jobs.proposal_store import build_proposal_fields
from app.verify.canon_verify import FlagKind, Severity, VerifyFlag, VerifyResult
from app.verify.wiring import (
    RejectDecision,
    VerifyStatus,
    decide_auto_reject,
)


def _result(*flags: VerifyFlag, degraded: bool = False) -> VerifyResult:
    return VerifyResult(flags=list(flags), verify_degraded=degraded)


def _inj(field: str = "content:历史") -> VerifyFlag:
    return VerifyFlag(kind=FlagKind.INJECTION, dimension=field,
                      evidence="neutralized 1 injection span(s) [forget-the-above]",
                      severity=Severity.HIGH)


def _anachron(term: str) -> VerifyFlag:
    return VerifyFlag(kind=FlagKind.ANACHRONISM, dimension="历史",
                      evidence=f"出现「{term}」：{term}为现代产物", severity=Severity.MEDIUM)


def _contradiction(sev: Severity = Severity.HIGH) -> VerifyFlag:
    return VerifyFlag(kind=FlagKind.CONTRADICTION, dimension="历史",
                      evidence="与既有正典相抵触（冲突词：东海）", severity=sev)


# ── injection → always egregious ──────────────────────────────────────────────

def test_injection_auto_rejects():
    d = decide_auto_reject(_result(_inj()))
    assert isinstance(d, RejectDecision)
    assert "injection" in d.reason.lower()


# ── contradiction: HIGH rejects, lower stays advisory ─────────────────────────

def test_high_contradiction_auto_rejects():
    d = decide_auto_reject(_result(_contradiction(Severity.HIGH)))
    assert d is not None
    assert "contradiction" in d.reason.lower() or "正典" in d.reason


def test_medium_contradiction_does_not_auto_reject():
    assert decide_auto_reject(_result(_contradiction(Severity.MEDIUM))) is None


# ── anachronism: 1 marker advisory, >=2 distinct egregious ────────────────────

def test_single_anachronism_does_not_auto_reject():
    assert decide_auto_reject(_result(_anachron("飞机"))) is None


def test_two_distinct_anachronism_markers_auto_reject():
    d = decide_auto_reject(_result(_anachron("飞机"), _anachron("互联网")))
    assert d is not None
    assert "anachron" in d.reason.lower()


def test_two_duplicate_anachronism_markers_do_not_reject():
    # the SAME marker flagged twice is one distinct marker → not egregious.
    assert decide_auto_reject(_result(_anachron("飞机"), _anachron("飞机"))) is None


# ── clean / advisory-only results ─────────────────────────────────────────────

def test_clean_result_is_not_rejected():
    assert decide_auto_reject(_result()) is None


def test_degraded_only_is_not_rejected():
    # a degraded contradiction read is conservative, NOT egregious.
    assert decide_auto_reject(_result(degraded=True)) is None


# ── status derivation: AUTO_REJECTED takes priority ───────────────────────────

def test_status_auto_rejected_for_injection():
    from app.verify.wiring import _derive_status

    assert _derive_status(_result(_inj())) is VerifyStatus.AUTO_REJECTED


def test_status_needs_review_for_single_anachronism():
    from app.verify.wiring import _derive_status

    assert _derive_status(_result(_anachron("飞机"))) is VerifyStatus.NEEDS_REVIEW


# ── T2: build_proposal_fields review_status / rejected_reason override ─────────

def _one_fact():
    return [make_enriched_fact(
        user_id="u1", project_id="p1", entity_kind="location", canonical_name="蓬萊",
        target_ref="loc:penglai", dimension="历史", content="上古仙岛。",
        technique="retrieval",
        source_refs=[SourceRef(corpus_id="c", chunk_id="k", chunk_index=1, score=0.8)],
        model_ref="m",
    )]


def test_build_fields_defaults_to_proposed():
    fields = build_proposal_fields(
        user_id="u1", project_id="p1", entity_kind="location", canonical_name="蓬萊",
        target_ref="loc:penglai", technique="retrieval", confidence=0.05,
        facts=_one_fact(), verify=None, source_refs=[],
    )
    assert fields["review_status"] == "proposed"
    assert fields["rejected_reason"] is None


def test_build_fields_auto_reject_override_is_h0_safe():
    fields = build_proposal_fields(
        user_id="u1", project_id="p1", entity_kind="location", canonical_name="蓬萊",
        target_ref="loc:penglai", technique="retrieval", confidence=0.05,
        facts=_one_fact(), verify=None, source_refs=[],
        review_status="rejected", rejected_reason="auto-reject: injection (...)",
    )
    assert fields["review_status"] == "rejected"
    assert fields["rejected_reason"] == "auto-reject: injection (...)"
    # H0 intact even when rejected: never canon.
    assert fields["origin"] == "enrichment"
    assert 0.0 < fields["confidence"] < 1.0
    assert fields["pending_validation"] is True
