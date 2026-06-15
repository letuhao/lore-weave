"""State-aware control_caps derivation (spec M5) — pure, no DB."""

from app.contract import derive_control_caps
from loreweave_jobs import ControlCap, JobStatus


def _vals(caps):
    return [c.value for c in caps]


def test_terminal_statuses_offer_nothing():
    for s in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
        assert derive_control_caps(s, "extraction") == []


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


def test_enrichment_job_is_multi_unit_offers_pause():
    # lore-enrichment's C8 gap-fill runner dispatches many units → real pause/resume.
    assert _vals(derive_control_caps(JobStatus.RUNNING, "enrichment_job")) == ["pause", "cancel"]
    assert _vals(derive_control_caps(JobStatus.PAUSED, "enrichment_job")) == ["resume", "cancel"]


def test_unknown_kind_defaults_to_cancel_only_when_running():
    assert _vals(derive_control_caps(JobStatus.RUNNING, "some_new_kind")) == ["cancel"]


def test_accepts_string_status():
    assert _vals(derive_control_caps("running", "translation")) == ["pause", "cancel"]
    assert ControlCap.PAUSE in derive_control_caps("running", "campaign")
