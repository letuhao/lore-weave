"""S2 — translation idempotency gate (G3).

The job SKIPS chapters that already have a fresh successful active translation
for the target language; only {never ∪ stale ∪ failed ∪ forced} are fanned out.
Skipped chapters emit `chapter.translation_skipped` so a resumed campaign's
projection converges. Tested via the public route (mirrors test_jobs.py).
"""

import datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

from tests.conftest import FakeRecord

USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
BOOK_ID = str(uuid4())
JOB_ID = str(uuid4())
C1 = str(uuid4())
C2 = str(uuid4())
MODEL_REF = str(uuid4())
_NOW = datetime.datetime.now(datetime.timezone.utc)

_BOOK_SETTINGS_ROW = FakeRecord({
    "book_id": UUID(BOOK_ID), "owner_user_id": UUID(USER_ID),
    "target_language": "vi", "model_source": "platform_model",
    "model_ref": UUID(MODEL_REF), "system_prompt": "Translate.",
    "user_prompt_tpl": "{chapter_text}", "updated_at": _NOW,
})


def _job_row(status="pending", total=1):
    return FakeRecord({
        "job_id": UUID(JOB_ID), "book_id": UUID(BOOK_ID),
        "owner_user_id": UUID(USER_ID), "status": status, "target_language": "vi",
        "model_source": "platform_model", "model_ref": UUID(MODEL_REF),
        "system_prompt": "Translate.", "user_prompt_tpl": "{chapter_text}",
        "chapter_ids": [UUID(C1)], "total_chapters": total, "completed_chapters": 0,
        "failed_chapters": 0, "error_message": None, "started_at": None,
        "finished_at": None, "created_at": _NOW,
    })


def _post(client, body):
    # E0-4a: book authz is the conftest grant_stub (default OWNER); no httpx mock.
    with (
        patch("app.routers.jobs.publish", new_callable=AsyncMock) as pub,
        patch("app.routers.jobs.publish_event", new_callable=AsyncMock),
    ):
        resp = client.post(f"/v1/translation/books/{BOOK_ID}/jobs", json=body)
    return resp, pub


def test_all_chapters_already_current_skips_and_completes(client, fake_pool):
    # skip query returns C1 (fresh+done) → todo empty → no publish, job completed,
    # and a chapter.translation_skipped event emitted for C1.
    fake_pool.fetchrow.side_effect = [
        _BOOK_SETTINGS_ROW,                 # resolve_effective_settings
        _job_row(total=0),                  # INSERT job RETURNING *
        _job_row(status="completed", total=0),  # re-fetch on empty
    ]
    fake_pool.fetch.return_value = [FakeRecord({"chapter_id": UUID(C1)})]

    resp, pub = _post(client, {"chapter_ids": [C1]})
    assert resp.status_code == 201, resp.text
    assert resp.json()["total_chapters"] == 0
    pub.assert_not_called()  # nothing to fan out
    emitted = [c for c in fake_pool.execute.call_args_list
               if "chapter.translation_skipped" in str(c.args[0])]
    assert emitted, "skipped chapter must emit a done-signal for projection convergence"


def test_force_retranslate_bypasses_skip(client, fake_pool):
    # force_retranslate → no skip query consulted, all chapters fanned out.
    fake_pool.fetchrow.side_effect = [_BOOK_SETTINGS_ROW, _job_row()]
    fake_pool.fetch.return_value = [FakeRecord({"chapter_id": UUID(C1)})]  # would-skip, but forced

    resp, pub = _post(client, {"chapter_ids": [C1], "force_retranslate": True})
    assert resp.status_code == 201
    pub.assert_called_once()
    published = pub.call_args.args[1]["chapter_ids"]
    assert published == [C1]


def test_partial_skip_translates_only_todo(client, fake_pool):
    # C2 already current, C1 not → translate C1, skip-emit C2.
    fake_pool.fetchrow.side_effect = [_BOOK_SETTINGS_ROW, _job_row()]
    fake_pool.fetch.return_value = [FakeRecord({"chapter_id": UUID(C2)})]

    resp, pub = _post(client, {"chapter_ids": [C1, C2]})
    assert resp.status_code == 201
    pub.assert_called_once()
    assert pub.call_args.args[1]["chapter_ids"] == [C1]  # only the to-do
    skip_emits = [c for c in fake_pool.execute.call_args_list
                  if "chapter.translation_skipped" in str(c.args[0])]
    assert len(skip_emits) == 1  # exactly C2


def test_never_translated_translates_all(client, fake_pool):
    # No active versions → skip query empty → all chapters to-do.
    fake_pool.fetchrow.side_effect = [_BOOK_SETTINGS_ROW, _job_row()]
    fake_pool.fetch.return_value = []

    resp, pub = _post(client, {"chapter_ids": [C1]})
    assert resp.status_code == 201
    pub.assert_called_once()
    assert pub.call_args.args[1]["chapter_ids"] == [C1]
    skip_emits = [c for c in fake_pool.execute.call_args_list
                  if "chapter.translation_skipped" in str(c.args[0])]
    assert not skip_emits
