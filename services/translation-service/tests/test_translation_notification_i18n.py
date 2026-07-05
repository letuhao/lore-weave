"""Notification i18n: the translation completion notification carries a stable
message_key + params (a locale-aware client localizes) plus the English title as a
fallback. D-C-PRODUCER-OUTBOX moved delivery from a fire-and-forget POST to an in-tx
outbox emit, so this now tests the pure body builder (the payload the outbox row +
the relay's /internal/notifications POST carry)."""
from app.workers.chapter_worker import _translation_notification_body


def test_completed_notification_carries_message_key_and_params():
    body = _translation_notification_body("u1", "j1", "Dracula", "completed", 3, 0)
    # Canonical top-level substrate (the FE renders from these).
    assert body["message_key"] == "notif.translation.completed"
    assert body["message_params"] == {"count": 3, "book": "Dracula"}
    # Legacy metadata channel kept for pre-message_key clients.
    assert body["metadata"]["i18n_key"] == "notif.translation.completed"
    assert body["metadata"]["i18n_params"] == {"count": 3, "book": "Dracula"}
    # English title kept as fallback for older clients.
    assert "Translation complete" in body["title"]
    assert body["category"] == "translation"


def test_partial_notification_carries_message_key_and_params():
    body = _translation_notification_body("u1", "j1", "Dracula", "partial", 2, 1)
    assert body["message_key"] == "notif.translation.partial"
    assert body["message_params"] == {"done": 2, "failed": 1}


def test_failed_notification_carries_message_key_and_params():
    body = _translation_notification_body("u1", "j1", "Dracula", "failed", 0, 1)
    assert body["message_key"] == "notif.translation.failed"
    assert body["message_params"] == {"book": "Dracula"}


def test_dedup_key_is_deterministic_per_job_and_status():
    # The relay delivers at-least-once; the dedup_key makes a re-POST idempotent.
    a = _translation_notification_body("u1", "job-9", "Dracula", "completed", 3, 0)
    b = _translation_notification_body("u1", "job-9", "Dracula", "completed", 3, 0)
    assert a["dedup_key"] == b["dedup_key"] == "translation:job-9:completed"
    # A different terminal status is a distinct notification (not a dupe).
    c = _translation_notification_body("u1", "job-9", "Dracula", "failed", 0, 1)
    assert c["dedup_key"] != a["dedup_key"]
