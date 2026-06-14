"""Unit tests for /v1/translation/chapters/.../versions endpoints (LW-72)."""
import datetime
import json
from uuid import UUID, uuid4

import pytest

from tests.conftest import FakeRecord

USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
OTHER_USER_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
CHAPTER_ID = str(uuid4())
BOOK_ID = str(uuid4())
JOB_ID = str(uuid4())
VERSION_ID = str(uuid4())

_NOW = datetime.datetime.utcnow()
_CT_ID = uuid4()


def _list_row(**overrides):
    base = {
        "id": _CT_ID,
        "job_id": UUID(JOB_ID),
        "chapter_id": UUID(CHAPTER_ID),
        "book_id": UUID(BOOK_ID),
        "owner_user_id": UUID(USER_ID),
        "status": "completed",
        "translated_body": "Phần mở đầu...",
        "source_language": "en",
        "target_language": "vi",
        "version_num": 1,
        "translated_body_json": None,
        "translated_body_format": "text",
        "authored_by": "llm",
        "edited_from_version_id": None,
        "input_tokens": 100,
        "output_tokens": 80,
        "usage_log_id": None,
        "error_message": None,
        "started_at": _NOW,
        "finished_at": _NOW,
        "created_at": _NOW,
        "is_active": True,
        "active_ct_id": _CT_ID,
        "model_source": "platform_model",
        "model_ref": uuid4(),
    }
    base.update(overrides)
    return FakeRecord(base)


def _get_row(**overrides):
    base = {
        "id": _CT_ID,
        "job_id": UUID(JOB_ID),
        "chapter_id": UUID(CHAPTER_ID),
        "book_id": UUID(BOOK_ID),
        "owner_user_id": UUID(USER_ID),
        "status": "completed",
        "translated_body": "Phần mở đầu...",
        "source_language": "en",
        "target_language": "vi",
        "version_num": 1,
        "translated_body_json": None,
        "translated_body_format": "text",
        "authored_by": "llm",
        "edited_from_version_id": None,
        "input_tokens": 100,
        "output_tokens": 80,
        "usage_log_id": None,
        "error_message": None,
        "started_at": _NOW,
        "finished_at": _NOW,
        "created_at": _NOW,
    }
    base.update(overrides)
    return FakeRecord(base)


def _active_row(**overrides):
    base = {
        "owner_user_id": UUID(USER_ID),
        "book_id": UUID(BOOK_ID),  # M7b: read for the translation.reviewed emit
        "target_language": "vi",
        "status": "completed",
        "unresolved_high_count": 0,
    }
    base.update(overrides)
    return FakeRecord(base)


def _active_upsert_called(fake_pool):
    """True if the active-versions upsert ran (ignores the M7b translation.reviewed emit)."""
    return any(
        "active_chapter_translation_versions" in c.args[0]
        for c in fake_pool.execute.call_args_list
    )


def _reviewed_emits(fake_pool):
    """The translation.reviewed outbox emits captured on fake_pool.execute (M7b)."""
    return [c for c in fake_pool.execute.call_args_list if "translation.reviewed" in c.args[0]]


# ── GET /v1/translation/chapters/{chapter_id}/versions ────────────────────────

def test_list_versions_empty_when_no_translations(client, fake_pool):
    fake_pool.fetch.return_value = []
    resp = client.get(f"/v1/translation/chapters/{CHAPTER_ID}/versions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["chapter_id"] == CHAPTER_ID
    assert data["languages"] == []


def test_list_versions_groups_rows_by_language(client, fake_pool):
    row_vi = _list_row()
    row_zh = _list_row(
        id=uuid4(),
        target_language="zh",
        active_ct_id=None,
        is_active=False,
        version_num=1,
    )
    fake_pool.fetchval.return_value = UUID(BOOK_ID)  # E0-4a book_for_chapter bootstrap
    fake_pool.fetch.return_value = [row_vi, row_zh]
    resp = client.get(f"/v1/translation/chapters/{CHAPTER_ID}/versions")
    assert resp.status_code == 200
    langs = {g["target_language"] for g in resp.json()["languages"]}
    assert langs == {"vi", "zh"}


def test_list_versions_marks_is_active_true_for_active_version(client, fake_pool):
    fake_pool.fetchval.return_value = UUID(BOOK_ID)
    fake_pool.fetch.return_value = [_list_row(is_active=True, active_ct_id=_CT_ID)]
    resp = client.get(f"/v1/translation/chapters/{CHAPTER_ID}/versions")
    assert resp.status_code == 200
    group = resp.json()["languages"][0]
    assert group["target_language"] == "vi"
    assert group["versions"][0]["is_active"] is True


def test_list_versions_marks_is_active_false_when_no_active_set(client, fake_pool):
    fake_pool.fetchval.return_value = UUID(BOOK_ID)
    fake_pool.fetch.return_value = [_list_row(is_active=False, active_ct_id=None)]
    resp = client.get(f"/v1/translation/chapters/{CHAPTER_ID}/versions")
    assert resp.status_code == 200
    group = resp.json()["languages"][0]
    assert group["active_id"] is None
    assert group["versions"][0]["is_active"] is False


def test_list_versions_surfaces_authored_by(client, fake_pool):
    # T1 AC4: the FE needs authored_by to detect a human-version + a newer machine one.
    fake_pool.fetchval.return_value = UUID(BOOK_ID)
    fake_pool.fetch.return_value = [
        _list_row(id=uuid4(), version_num=2, authored_by="human", is_active=True),
        _list_row(id=uuid4(), version_num=1, authored_by="llm", is_active=False),
    ]
    resp = client.get(f"/v1/translation/chapters/{CHAPTER_ID}/versions")
    assert resp.status_code == 200
    vers = resp.json()["languages"][0]["versions"]
    by = {v["version_num"]: v["authored_by"] for v in vers}
    assert by == {2: "human", 1: "llm"}


def test_list_versions_includes_version_num(client, fake_pool):
    fake_pool.fetchval.return_value = UUID(BOOK_ID)
    fake_pool.fetch.return_value = [_list_row(version_num=3)]
    resp = client.get(f"/v1/translation/chapters/{CHAPTER_ID}/versions")
    assert resp.status_code == 200
    group = resp.json()["languages"][0]
    assert group["versions"][0]["version_num"] == 3


def test_list_versions_multiple_versions_same_language(client, fake_pool):
    v2_id = uuid4()
    row_v2 = _list_row(id=v2_id, version_num=2, is_active=False)
    row_v1 = _list_row(id=_CT_ID, version_num=1, is_active=True)
    fake_pool.fetchval.return_value = UUID(BOOK_ID)
    fake_pool.fetch.return_value = [row_v2, row_v1]
    resp = client.get(f"/v1/translation/chapters/{CHAPTER_ID}/versions")
    assert resp.status_code == 200
    langs = resp.json()["languages"]
    # All under single language group
    assert len(langs) == 1
    assert len(langs[0]["versions"]) == 2


# ── GET /v1/translation/chapters/{chapter_id}/versions/{version_id} ───────────

def test_get_version_returns_full_translation(client, fake_pool):
    fake_pool.fetchrow.return_value = _get_row()
    resp = client.get(f"/v1/translation/chapters/{CHAPTER_ID}/versions/{VERSION_ID}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["translated_body"] == "Phần mở đầu..."
    assert data["target_language"] == "vi"
    assert data["input_tokens"] == 100
    assert data["output_tokens"] == 80


def test_get_version_returns_404_when_not_found(client, fake_pool):
    fake_pool.fetchrow.return_value = None
    resp = client.get(f"/v1/translation/chapters/{CHAPTER_ID}/versions/{VERSION_ID}")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "TRANSL_NOT_FOUND"


def test_get_version_returns_404_when_no_grant(client, fake_pool, grant_stub):
    # E0-4a: the version exists but the caller has no grant on its book → 404.
    from app.grant_client import GrantLevel
    grant_stub.level = GrantLevel.NONE
    fake_pool.fetchrow.return_value = _get_row()
    resp = client.get(f"/v1/translation/chapters/{CHAPTER_ID}/versions/{VERSION_ID}")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "TRANSL_NOT_FOUND"


# ── PUT /v1/translation/chapters/{chapter_id}/versions/{version_id}/active ────

def test_set_active_version_returns_200_and_upserts(client, fake_pool):
    fake_pool.fetchrow.return_value = _active_row()
    resp = client.put(f"/v1/translation/chapters/{CHAPTER_ID}/versions/{VERSION_ID}/active")
    assert resp.status_code == 200
    data = resp.json()
    assert data["active_id"] == VERSION_ID
    assert data["target_language"] == "vi"
    assert data["chapter_id"] == CHAPTER_ID
    # DB execute upserts the active table (+ M7b emits translation.reviewed)
    assert _active_upsert_called(fake_pool)


def test_set_active_version_returns_404_when_not_found(client, fake_pool):
    fake_pool.fetchrow.return_value = None
    resp = client.put(f"/v1/translation/chapters/{CHAPTER_ID}/versions/{VERSION_ID}/active")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "TRANSL_NOT_FOUND"


def test_set_active_version_returns_404_when_no_grant(client, fake_pool, grant_stub):
    # E0-4a: no grant on the version's book → 404 (anti-oracle).
    from app.grant_client import GrantLevel
    grant_stub.level = GrantLevel.NONE
    fake_pool.fetchrow.return_value = _active_row()
    resp = client.put(f"/v1/translation/chapters/{CHAPTER_ID}/versions/{VERSION_ID}/active")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "TRANSL_NOT_FOUND"


def test_set_active_version_returns_403_when_view_grantee(client, fake_pool, grant_stub):
    # A view-grantee cannot publish (set active) — needs edit → 403.
    from app.grant_client import GrantLevel
    grant_stub.level = GrantLevel.VIEW
    fake_pool.fetchrow.return_value = _active_row()
    resp = client.put(f"/v1/translation/chapters/{CHAPTER_ID}/versions/{VERSION_ID}/active")
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "TRANSL_FORBIDDEN"


def test_set_active_version_returns_422_when_status_failed(client, fake_pool):
    fake_pool.fetchrow.return_value = _active_row(status="failed")
    resp = client.put(f"/v1/translation/chapters/{CHAPTER_ID}/versions/{VERSION_ID}/active")
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "TRANSL_NOT_COMPLETED"


def test_set_active_version_returns_422_when_status_pending(client, fake_pool):
    fake_pool.fetchrow.return_value = _active_row(status="pending")
    resp = client.put(f"/v1/translation/chapters/{CHAPTER_ID}/versions/{VERSION_ID}/active")
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "TRANSL_NOT_COMPLETED"


# ── M5b publish quality-gate ──────────────────────────────────────────────────

def test_set_active_version_holds_when_unresolved_high_issues(client, fake_pool):
    """Soft gate: a flagged version is held (409) and NOT made active without ack."""
    fake_pool.fetchrow.return_value = _active_row(unresolved_high_count=2)
    resp = client.put(f"/v1/translation/chapters/{CHAPTER_ID}/versions/{VERSION_ID}/active")
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["code"] == "TRANSL_NEEDS_REVIEW"
    assert detail["unresolved_high_count"] == 2
    fake_pool.execute.assert_not_called()  # not published


def test_set_active_version_publishes_flagged_with_acknowledge(client, fake_pool):
    """acknowledge_issues=true overrides the hold and publishes the flagged version."""
    fake_pool.fetchrow.return_value = _active_row(unresolved_high_count=2)
    resp = client.put(
        f"/v1/translation/chapters/{CHAPTER_ID}/versions/{VERSION_ID}/active"
        "?acknowledge_issues=true"
    )
    assert resp.status_code == 200
    assert resp.json()["active_id"] == VERSION_ID
    assert _active_upsert_called(fake_pool)


def test_set_active_version_no_gate_when_clean(client, fake_pool):
    """unresolved_high_count=0 → publishes directly, no acknowledgement needed."""
    fake_pool.fetchrow.return_value = _active_row(unresolved_high_count=0)
    resp = client.put(f"/v1/translation/chapters/{CHAPTER_ID}/versions/{VERSION_ID}/active")
    assert resp.status_code == 200
    assert _active_upsert_called(fake_pool)


# ── M7b: human-accept signal emit ─────────────────────────────────────────────

def test_set_active_emits_translation_reviewed(client, fake_pool):
    """Setting a version active emits translation.reviewed (human accept → learning)."""
    fake_pool.fetchrow.return_value = _active_row()
    resp = client.put(f"/v1/translation/chapters/{CHAPTER_ID}/versions/{VERSION_ID}/active")
    assert resp.status_code == 200
    emits = _reviewed_emits(fake_pool)
    assert len(emits) == 1
    # args: sql, $1 version_id (aggregate_id), $2 payload json
    payload = json.loads(emits[0].args[2])
    assert payload["chapter_translation_id"] == VERSION_ID
    assert payload["acknowledged_issues"] is False
    assert payload["target_language"] == "vi"


def test_acknowledged_publish_emits_with_flag_and_count(client, fake_pool):
    """The verifier-calibration case: ack=true + the flagged count ride in the event."""
    fake_pool.fetchrow.return_value = _active_row(unresolved_high_count=2)
    resp = client.put(
        f"/v1/translation/chapters/{CHAPTER_ID}/versions/{VERSION_ID}/active?acknowledge_issues=true"
    )
    assert resp.status_code == 200
    payload = json.loads(_reviewed_emits(fake_pool)[0].args[2])
    assert payload["acknowledged_issues"] is True
    assert payload["unresolved_high_count"] == 2


def test_held_version_emits_nothing(client, fake_pool):
    """A 409 hold (no ack) sets nothing active → no human-accept signal."""
    fake_pool.fetchrow.return_value = _active_row(unresolved_high_count=2)
    resp = client.put(f"/v1/translation/chapters/{CHAPTER_ID}/versions/{VERSION_ID}/active")
    assert resp.status_code == 409
    assert _reviewed_emits(fake_pool) == []


# ── M7c: save a human-edited translation (gold) ───────────────────────────────

def _edit_body(**over):
    base = {"target_language": "vi", "edited_from_version_id": VERSION_ID,
            "translated_body": "Bản người sửa", "translated_body_format": "text"}
    base.update(over)
    return base


def _corrected_emits(fake_pool):
    return [c for c in fake_pool.execute.call_args_list if "translation.corrected" in c.args[0]]


def test_save_edited_creates_human_version_and_emits_gold(client, fake_pool):
    src = _get_row(translated_body="LLM draft")          # the version edited from
    new = _get_row(id=uuid4(), authored_by="human",      # the new human version
                   edited_from_version_id=UUID(VERSION_ID), translated_body="Bản người sửa")
    fake_pool.fetchrow.side_effect = [src, new]
    resp = client.post(f"/v1/translation/chapters/{CHAPTER_ID}/versions/edit", json=_edit_body())
    assert resp.status_code == 201
    assert resp.json()["authored_by"] == "human"
    # review-impl: pin the INSERT SHAPE (not just the mocked response) — the 2nd
    # fetchrow is the INSERT...RETURNING; it must actually write authored_by='human'
    # + the parent link + version_num=MAX+1.
    insert_sql = fake_pool.fetchrow.call_args_list[1].args[0]
    assert "INSERT INTO chapter_translations" in insert_sql
    assert "authored_by" in insert_sql and "'human'" in insert_sql
    assert "edited_from_version_id" in insert_sql
    assert "MAX(version_num)" in insert_sql
    # translation.corrected emitted with before(LLM)/after(human)
    emits = _corrected_emits(fake_pool)
    assert len(emits) == 1
    payload = json.loads(emits[0].args[2])
    assert payload["before"]["body"] == "LLM draft"
    assert payload["after"]["body"] == "Bản người sửa"
    assert payload["edited_from_version_id"] == VERSION_ID


def test_save_edited_404_when_source_missing(client, fake_pool):
    fake_pool.fetchrow.return_value = None
    resp = client.post(f"/v1/translation/chapters/{CHAPTER_ID}/versions/edit", json=_edit_body())
    assert resp.status_code == 404
    assert _corrected_emits(fake_pool) == []


def test_save_edited_attributes_to_caller_not_source_owner(client, fake_pool):
    # review-impl MED-1: caller-attribution — the human edit is owned by the CALLER
    # (the editing collaborator), NOT the source version's owner. Source is owned by
    # OTHER; the INSERT's owner_user_id ($7, last positional) must be the caller.
    src = _get_row(owner_user_id=UUID(OTHER_USER_ID), translated_body="LLM draft")
    new = _get_row(id=uuid4(), authored_by="human")
    fake_pool.fetchrow.side_effect = [src, new]
    resp = client.post(f"/v1/translation/chapters/{CHAPTER_ID}/versions/edit", json=_edit_body())
    assert resp.status_code == 201
    insert_args = fake_pool.fetchrow.call_args_list[1].args
    assert insert_args[-1] == UUID(USER_ID)  # caller, not OTHER_USER_ID (the source owner)


def test_save_edited_404_when_no_grant(client, fake_pool, grant_stub):
    # E0-4a: no grant on the source version's book → 404 (anti-oracle).
    from app.grant_client import GrantLevel
    grant_stub.level = GrantLevel.NONE
    fake_pool.fetchrow.return_value = _get_row()
    resp = client.post(f"/v1/translation/chapters/{CHAPTER_ID}/versions/edit", json=_edit_body())
    assert resp.status_code == 404


def test_save_edited_422_on_language_mismatch(client, fake_pool):
    fake_pool.fetchrow.return_value = _get_row(target_language="en")
    resp = client.post(f"/v1/translation/chapters/{CHAPTER_ID}/versions/edit",
                       json=_edit_body(target_language="vi"))
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "TRANSL_LANG_MISMATCH"


def test_set_active_version_returns_422_when_status_running(client, fake_pool):
    fake_pool.fetchrow.return_value = _active_row(status="running")
    resp = client.put(f"/v1/translation/chapters/{CHAPTER_ID}/versions/{VERSION_ID}/active")
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "TRANSL_NOT_COMPLETED"


# ── PATCH /v1/translation/chapters/{chapter_id}/versions/blocks (T1) ───────────

def _blk(text):
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


_BASE_BLOCKS = [_blk("Khối 0 (LLM)"), _blk("Khối 1 (LLM)")]
NEW_BLOCK = _blk("Khối 1 (người sửa)")


def _json_base(**over):
    base = {
        "owner_user_id": UUID(USER_ID),
        "book_id": UUID(BOOK_ID),
        "target_language": "vi",
        "status": "completed",
        "version_num": 1,
        "translated_body_json": list(_BASE_BLOCKS),
        "translated_body_format": "json",
    }
    base.update(over)
    return FakeRecord(base)


def _hv_sel(hv_id, blocks=None):
    return FakeRecord({"id": hv_id, "translated_body_json": blocks if blocks is not None else list(_BASE_BLOCKS)})


def _patched_full(hv_id, **over):
    return _get_row(id=hv_id, authored_by="human", target_language="vi",
                    translated_body_format="json", translated_body_json=list(_BASE_BLOCKS),
                    edited_from_version_id=UUID(VERSION_ID), **over)


def _patch_body(**over):
    b = {"target_language": "vi", "base_version_id": VERSION_ID,
         "block_index": 1, "block": NEW_BLOCK, "source_block_text": "Source para 1"}
    b.update(over)
    return b


def _corrected_block_emits(fake_pool):
    return [c for c in fake_pool.execute.call_args_list if "translation.corrected" in c.args[0]]


def _jsonb_set_calls(fake_pool):
    return [c for c in fake_pool.execute.call_args_list if "jsonb_set" in c.args[0]]


def _ct_insert_in_fetchrow(fake_pool):
    return any("INSERT INTO chapter_translations" in (c.args[0] if c.args else "")
               for c in fake_pool.fetchrow.call_args_list)


_PATCH_URL = f"/v1/translation/chapters/{CHAPTER_ID}/versions/blocks"


def test_patch_block_creates_human_version_and_sets_active(client, fake_pool):
    """First patch get-or-creates the single human-version, makes it active, patches."""
    hv_id = uuid4()
    # fetchrow order: base, hv-select(None), insert RETURNING, updated
    fake_pool.fetchrow.side_effect = [
        _json_base(), None, _hv_sel(hv_id), _patched_full(hv_id),
    ]
    resp = client.patch(_PATCH_URL, json=_patch_body())
    assert resp.status_code == 200
    assert resp.json()["authored_by"] == "human"
    # human-version was INSERTed (get-or-create) + made active
    assert _ct_insert_in_fetchrow(fake_pool)
    assert _active_upsert_called(fake_pool)
    # exactly one block patched via jsonb_set, at the requested index
    sets = _jsonb_set_calls(fake_pool)
    assert len(sets) == 1
    assert sets[0].args[2] == "1"  # block_index passed as the path element
    # per-block gold emitted with block_index
    emits = _corrected_block_emits(fake_pool)
    assert len(emits) == 1
    payload = json.loads(emits[0].args[2])
    assert payload["block_index"] == 1
    assert payload["before"]["block"]["content"][0]["text"] == "Khối 1 (LLM)"
    assert payload["after"]["block"]["content"][0]["text"] == "Khối 1 (người sửa)"
    assert payload["source_block_text"] == "Source para 1"


def test_patch_block_reuses_existing_human_version_no_new_version(client, fake_pool):
    """A second patch edits the existing human-version in place — NO new version, NO active re-set."""
    hv_id = uuid4()
    fake_pool.fetchrow.side_effect = [
        _json_base(), _hv_sel(hv_id), _patched_full(hv_id),
    ]
    resp = client.patch(_PATCH_URL, json=_patch_body(block_index=0))
    assert resp.status_code == 200
    # existing human-version found → NO INSERT INTO chapter_translations, NO active upsert
    assert not _ct_insert_in_fetchrow(fake_pool)
    assert not _active_upsert_called(fake_pool)
    assert len(_jsonb_set_calls(fake_pool)) == 1
    assert len(_corrected_block_emits(fake_pool)) == 1


def test_patch_block_404_when_base_missing(client, fake_pool):
    fake_pool.fetchrow.return_value = None
    resp = client.patch(_PATCH_URL, json=_patch_body())
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "TRANSL_NOT_FOUND"
    assert _corrected_block_emits(fake_pool) == []


def test_patch_block_404_when_no_grant(client, fake_pool, grant_stub):
    from app.grant_client import GrantLevel
    grant_stub.level = GrantLevel.NONE
    fake_pool.fetchrow.return_value = _json_base()
    resp = client.patch(_PATCH_URL, json=_patch_body())
    assert resp.status_code == 404


def test_patch_block_403_when_view_grantee(client, fake_pool, grant_stub):
    from app.grant_client import GrantLevel
    grant_stub.level = GrantLevel.VIEW
    fake_pool.fetchrow.return_value = _json_base()
    resp = client.patch(_PATCH_URL, json=_patch_body())
    assert resp.status_code == 403


def test_patch_block_422_on_language_mismatch(client, fake_pool):
    fake_pool.fetchrow.return_value = _json_base(target_language="en")
    resp = client.patch(_PATCH_URL, json=_patch_body(target_language="vi"))
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "TRANSL_LANG_MISMATCH"


def test_patch_block_422_on_text_format(client, fake_pool):
    fake_pool.fetchrow.return_value = _json_base(translated_body_format="text", translated_body_json=None)
    resp = client.patch(_PATCH_URL, json=_patch_body())
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "TRANSL_NOT_BLOCK_FORMAT"


def test_patch_block_422_when_index_out_of_range(client, fake_pool):
    hv_id = uuid4()
    fake_pool.fetchrow.side_effect = [_json_base(), _hv_sel(hv_id)]
    resp = client.patch(_PATCH_URL, json=_patch_body(block_index=9))
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "TRANSL_BLOCK_INDEX_OOR"


# ── pure helpers (recompute / JSONB coercion) ─────────────────────────────────

def test_block_text_extracts_nested_and_hardbreaks():
    from app.routers.versions import _block_text
    node = {"type": "paragraph", "content": [
        {"type": "text", "text": "Xin "},
        {"type": "hardBreak"},
        {"type": "text", "text": "chào"},
    ]}
    assert _block_text(node) == "Xin \nchào"
    assert _block_text({"type": "horizontalRule"}) == ""
    assert _block_text("not a dict") == ""


def test_blocks_to_text_joins_blocks_with_blank_line():
    from app.routers.versions import _blocks_to_text
    blocks = [
        {"type": "paragraph", "content": [{"type": "text", "text": "Khối 0"}]},
        {"type": "paragraph", "content": [{"type": "text", "text": "Khối 1"}]},
    ]
    assert _blocks_to_text(blocks) == "Khối 0\n\nKhối 1"
    assert _blocks_to_text([]) == ""
    assert _blocks_to_text(None) == ""


def test_as_list_coerces_str_and_passthrough_list():
    from app.routers.versions import _as_list
    blocks = [{"type": "paragraph"}]
    assert _as_list(blocks) == blocks            # already a list
    assert _as_list(json.dumps(blocks)) == blocks  # JSONB returned as text
    assert _as_list(None) == []
    assert _as_list("not json{") == []           # malformed → empty, never raises
    assert _as_list(123) == []                   # non-list/str → empty
