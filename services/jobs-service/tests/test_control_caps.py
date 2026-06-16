"""State-aware control_caps derivation (spec M5) — pure, no DB."""

from app.contract import derive_control_caps
from loreweave_jobs import ControlCap, JobStatus


def _vals(caps):
    return [c.value for c in caps]


def test_terminal_statuses_offer_nothing():
    # completed/cancelled never offer a cap; failed offers nothing for a NON-retryable kind.
    for s in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
        assert derive_control_caps(s, "extraction") == []


def test_failed_translation_offers_retry():
    # D-JOBS-P4-RETRY: a failed job of a retry-supported kind offers retry (re-submit).
    assert _vals(derive_control_caps(JobStatus.FAILED, "translation")) == ["retry"]


def test_failed_non_retryable_kind_offers_nothing():
    # composition/knowledge/video_gen/enrichment retry not wired yet → no retry button.
    for kind in ("extraction", "campaign", "video_gen", "enrichment_job", "generate"):
        assert derive_control_caps(JobStatus.FAILED, kind) == []


def test_retry_only_from_failed_not_other_terminal():
    # retry is gated on FAILED only — a completed/cancelled translation job offers nothing.
    assert derive_control_caps(JobStatus.COMPLETED, "translation") == []
    assert derive_control_caps(JobStatus.CANCELLED, "translation") == []


def test_cancelling_offers_nothing():
    assert derive_control_caps(JobStatus.CANCELLING, "extraction") == []


def test_pending_offers_cancel_only():
    assert _vals(derive_control_caps(JobStatus.PENDING, "extraction")) == ["cancel"]


def test_paused_offers_resume_and_cancel():
    assert _vals(derive_control_caps(JobStatus.PAUSED, "video_gen")) == ["resume", "cancel"]


def test_running_multi_unit_offers_pause_and_cancel():
    caps = _vals(derive_control_caps(JobStatus.RUNNING, "extraction"))
    assert "pause" in caps and "cancel" in caps


def test_running_single_call_kind_is_cancel_only():
    # video_gen / composition single ops cannot pause.
    assert _vals(derive_control_caps(JobStatus.RUNNING, "video_gen")) == ["cancel"]


def test_translation_is_cancel_only_until_pause_ships():
    # translation IS multi-chapter but has no pause impl yet (D-JOBS-P3-TRANSLATION-PAUSE);
    # caps must not offer an un-honored pause button.
    assert _vals(derive_control_caps(JobStatus.RUNNING, "translation")) == ["cancel"]


def test_enrichment_job_is_multi_unit_offers_pause():
    # lore-enrichment's C8 gap-fill runner dispatches many units → real pause/resume.
    assert _vals(derive_control_caps(JobStatus.RUNNING, "enrichment_job")) == ["pause", "cancel"]
    assert _vals(derive_control_caps(JobStatus.PAUSED, "enrichment_job")) == ["resume", "cancel"]


def test_unknown_kind_defaults_to_cancel_only_when_running():
    assert _vals(derive_control_caps(JobStatus.RUNNING, "some_new_kind")) == ["cancel"]


def test_accepts_string_status():
    assert _vals(derive_control_caps("running", "extraction")) == ["pause", "cancel"]
    assert ControlCap.PAUSE in derive_control_caps("running", "campaign")
