"""Unit tests for Pydantic models — validation rules."""
import pytest
from uuid import uuid4
from pydantic import ValidationError

from app.models import PreferencesPayload, CreateJobPayload


# ── PreferencesPayload ────────────────────────────────────────────────────────

def test_preferences_payload_accepts_valid_template():
    payload = PreferencesPayload(
        target_language="vi",
        model_source="platform_model",
        model_ref=None,
        system_prompt="You are a translator.",
        user_prompt_tpl="Translate {source_language} to {target_language}:\n{chapter_text}",
    )
    assert payload.user_prompt_tpl.startswith("Translate")


def test_preferences_payload_rejects_template_without_chapter_text():
    with pytest.raises(ValidationError) as exc_info:
        PreferencesPayload(
            target_language="vi",
            model_source="platform_model",
            model_ref=None,
            system_prompt="You are a translator.",
            user_prompt_tpl="Translate the following text.",  # missing {chapter_text}
        )
    errors = exc_info.value.errors()
    assert any("{chapter_text}" in str(e) for e in errors)


def test_preferences_payload_allows_null_model_ref():
    payload = PreferencesPayload(
        target_language="en",
        model_source="platform_model",
        model_ref=None,
        system_prompt="Translate.",
        user_prompt_tpl="Text: {chapter_text}",
    )
    assert payload.model_ref is None


def test_preferences_payload_accepts_uuid_model_ref():
    uid = uuid4()
    payload = PreferencesPayload(
        target_language="en",
        model_source="user_model",
        model_ref=uid,
        system_prompt="Translate.",
        user_prompt_tpl="Text: {chapter_text}",
    )
    assert payload.model_ref == uid


# ── CreateJobPayload ──────────────────────────────────────────────────────────

def test_create_job_payload_rejects_empty_list():
    with pytest.raises(ValidationError) as exc_info:
        CreateJobPayload(chapter_ids=[])
    errors = exc_info.value.errors()
    assert any("empty" in str(e).lower() or "chapter_ids" in str(e) for e in errors)


def test_create_job_payload_accepts_valid_ids():
    ids = [uuid4(), uuid4()]
    payload = CreateJobPayload(chapter_ids=ids)
    assert len(payload.chapter_ids) == 2


def test_create_job_payload_rejects_missing_field():
    with pytest.raises(ValidationError):
        CreateJobPayload()
