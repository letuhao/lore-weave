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


def test_translation_offers_pause_resume():
    # B2 (D-JOBS-P3-TRANSLATION-PAUSE): translation now honors stop-dispatch pause/resume,
    # so a running job offers pause+cancel and a paused job offers resume+cancel.
    assert _vals(derive_control_caps(JobStatus.RUNNING, "translation")) == ["pause", "cancel"]
    assert _vals(derive_control_caps(JobStatus.PAUSED, "translation")) == ["resume", "cancel"]


def test_enrichment_job_is_multi_unit_offers_pause():
    # lore-enrichment's C8 gap-fill runner dispatches many units → real pause/resume.
    assert _vals(derive_control_caps(JobStatus.RUNNING, "enrichment_job")) == ["pause", "cancel"]
    assert _vals(derive_control_caps(JobStatus.PAUSED, "enrichment_job")) == ["resume", "cancel"]


def test_unknown_kind_defaults_to_cancel_only_when_running():
    assert _vals(derive_control_caps(JobStatus.RUNNING, "some_new_kind")) == ["cancel"]


def test_book_import_is_view_only_in_any_state():
    # book_import has NO unified control surface (fire-and-forget; a running import can't be
    # stopped) → NO caps in ANY state (D-JOBS-BOOK-IMPORT-UNWIRED).
    for s in (JobStatus.PENDING, JobStatus.RUNNING, JobStatus.PAUSED,
              JobStatus.FAILED, JobStatus.COMPLETED, JobStatus.CANCELLED):
        assert derive_control_caps(s, "book_import") == [], f"book_import/{s} should be view-only"


def test_glossary_secondary_kinds_are_cancel_only():
    # D-JOBS-SECONDARY-KIND-CONTROL: glossary-extract/translate native endpoints only CANCEL
    # (pending|running). No pause/resume/retry even though they're multi-unit.
    for kind in ("glossary_extraction", "glossary_translation"):
        assert _vals(derive_control_caps(JobStatus.PENDING, kind)) == ["cancel"]
        assert _vals(derive_control_caps(JobStatus.RUNNING, kind)) == ["cancel"]
        assert derive_control_caps(JobStatus.PAUSED, kind) == []   # no paused state / no resume
        assert derive_control_caps(JobStatus.FAILED, kind) == []   # not retryable
        assert derive_control_caps(JobStatus.COMPLETED, kind) == []
        assert derive_control_caps(JobStatus.CANCELLING, kind) == []


def test_wiki_gen_caps_match_native():
    # D-JOBS-SECONDARY-KIND-CONTROL: wiki cancel works pending|paused, resume works paused;
    # a RUNNING wiki job is NOT cancellable (D-WIKI-M7B-RUNNING-CANCEL) → no caps.
    assert _vals(derive_control_caps(JobStatus.PENDING, "wiki_gen")) == ["cancel"]
    assert _vals(derive_control_caps(JobStatus.PAUSED, "wiki_gen")) == ["resume", "cancel"]
    assert derive_control_caps(JobStatus.RUNNING, "wiki_gen") == []  # can't cancel a running wiki job
    assert derive_control_caps(JobStatus.FAILED, "wiki_gen") == []
    assert derive_control_caps(JobStatus.COMPLETED, "wiki_gen") == []
    assert derive_control_caps(JobStatus.CANCELLING, "wiki_gen") == []


def test_accepts_string_status():
    assert _vals(derive_control_caps("running", "extraction")) == ["pause", "cancel"]
    assert ControlCap.PAUSE in derive_control_caps("running", "campaign")
