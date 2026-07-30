"""D-SCENE-PROSE-NOWHERE-TO-LAND — generating into a plan-only scene spends real tokens
on prose the author can never reach.

Measured on the Mị Đế book: `composition_generate` on a planned scene produced **783
words** of good Vietnamese prose, the job finished `completed`, and the compose panel
said *"Chưa có cảnh"*. Nothing failed loudly. The work simply did not exist anywhere the
author could see, and the tokens were billed.

The mechanism, and why it is structural rather than a slip:

* a SCENE generate does not persist — only the chapter target passes `persist=True`. It
  returns candidates for the author to accept in the compose panel;
* that panel resolves a chapter's scenes by `chapter_id`
  (`useChapterScenes`: `n.kind === 'scene' && n.chapter_id === chapterId`);
* `chapter_id` is **NULL on a planned node** — the normal state, not an error. The
  migration notes 7/7 in the live DB. Bootstrap stamps it when it materialises a planned
  chapter into a real one.

So planned scenes are exactly the ones the compose surface cannot display, and generating
into them is guaranteed waste. Two guards, both in the RESULT rather than a docstring,
because an agent reads results:

  * `composition_generate` refuses at PROPOSE — before the confirm gate, before a token
    is billed — and names the step that fixes it;
  * `composition_outline_node_create` labels a plan-only node `plan_only`, so a caller
    that gets a full row back is not misled into thinking it can draft into it.
"""
from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import app.mcp.server as srv

BOOK = uuid.uuid4()
PROJECT = uuid.uuid4()
NODE = uuid.uuid4()
CHAPTER = uuid.uuid4()


class _Ctx:
    user_id = uuid.uuid4()
    project_id = None
    book_id = None
    mcp_key_id = None


def _node(*, chapter_id):
    return SimpleNamespace(
        id=NODE, project_id=PROJECT, book_id=BOOK, kind="scene",
        title="Hiện trường đẫm máu", chapter_id=chapter_id,
        model_dump=lambda mode="json": {
            "id": str(NODE), "kind": "scene", "title": "Hiện trường đẫm máu",
            "chapter_id": str(chapter_id) if chapter_id else None,
        },
    )


def _patched(node):
    works = AsyncMock()
    outline = AsyncMock()
    outline.get_node = AsyncMock(return_value=node)
    gate = AsyncMock(return_value=SimpleNamespace(
        book_id=BOOK, work_id=uuid.uuid4(), project_id=PROJECT))
    return (
        patch.object(srv, "_ctx", side_effect=lambda c: c),
        patch.object(srv, "get_pool", return_value=object()),
        patch.object(srv, "WorksRepo", return_value=works),
        patch.object(srv, "OutlineRepo", return_value=outline),
        patch.object(srv, "_book_or_deny", gate),
    )


def _args(**over):
    return srv._GenerateArgs(
        project_id=str(PROJECT), outline_node_id=str(NODE),
        model_source="user_model", model_ref=str(uuid.uuid4()), **over,
    )


@pytest.mark.asyncio
async def test_a_plan_only_scene_is_REFUSED_before_any_token_is_spent():
    """THE FIX. The refusal happens at propose — no confirm token is minted, so the
    expensive path is never even offered."""
    patches = _patched(_node(chapter_id=None))
    for p in patches:
        p.start()
    try:
        res = await srv.composition_generate(_Ctx(), _args())
    finally:
        for p in patches:
            p.stop()

    assert res["success"] is False
    assert res["code"] == "scene_has_no_chapter"
    # No confirm token: the cost gate is never reached, so nothing can be confirmed by
    # a caller that ignores the error and posts the token anyway.
    assert "confirm_token" not in res

    # Assert what the MODEL actually receives, not what this dict happens to hold. The
    # C4 envelope is built by `failure_message`, which reads `error` and DROPS a
    # `message` key — the first cut of this guard put the guidance in `message` and the
    # model got a bare "scene_has_no_chapter" with every actionable word stripped. That
    # survived the unit tests (they read the dict) and was caught only by calling the
    # live endpoint. Test the boundary, not the return value.
    from loreweave_mcp.error_signal import failure_message
    surfaced = failure_message(res)
    assert surfaced is not None, "the refusal must be signalled as a tool ERROR"
    body = json.loads(surfaced)
    assert body["code"] == "scene_has_no_chapter"
    # It must name the REPAIR, not merely the symptom — a refusal an agent cannot act on
    # just becomes a retry loop.
    assert "bootstrap" in body["message"].lower()
    assert "no tokens are spent" in body["message"]


@pytest.mark.asyncio
async def test_a_materialised_scene_still_generates():
    """The guard must not block the working path: a scene whose chapter exists proceeds
    to the normal cost gate."""
    patches = _patched(_node(chapter_id=CHAPTER))
    for p in patches:
        p.start()
    try:
        res = await srv.composition_generate(_Ctx(), _args())
    finally:
        for p in patches:
            p.stop()

    assert res.get("error") != "scene_has_no_chapter"
    assert res.get("success") is not False


@pytest.mark.asyncio
async def test_the_refusal_is_scene_only_and_never_touches_a_chapter_target():
    """A CHAPTER target is validated by the engine at confirm (it needs book-service to
    resolve the chapter). This guard reads a node's chapter_id and must not run there —
    it has no node to read."""
    works = AsyncMock()
    gate = AsyncMock(return_value=SimpleNamespace(
        book_id=BOOK, work_id=uuid.uuid4(), project_id=PROJECT))
    outline = AsyncMock()
    outline.get_node = AsyncMock(side_effect=AssertionError(
        "the chapter target must not read an outline node"))
    with patch.object(srv, "_ctx", side_effect=lambda c: c), \
         patch.object(srv, "get_pool", return_value=object()), \
         patch.object(srv, "WorksRepo", return_value=works), \
         patch.object(srv, "OutlineRepo", return_value=outline), \
         patch.object(srv, "_book_or_deny", gate):
        res = await srv.composition_generate(_Ctx(), srv._GenerateArgs(
            project_id=str(PROJECT), chapter_id=str(CHAPTER),
            model_source="user_model", model_ref=str(uuid.uuid4()),
        ))
    assert res.get("error") != "scene_has_no_chapter"


class TestPlanOnlyLabelOnCreate:
    """A caller that creates a node, gets a full row back, and starts drafting into it
    produces work nobody can reach. The row is correct; the SILENCE about what it is not
    was the defect."""

    @staticmethod
    async def _create(chapter_id):
        created = SimpleNamespace(
            id=NODE, chapter_id=chapter_id,
            model_dump=lambda mode="json": {"id": str(NODE), "kind": "chapter"},
        )
        works = AsyncMock()
        outline = AsyncMock()
        outline.find_node_by_title = AsyncMock(return_value=None)
        outline.create_node = AsyncMock(return_value=created)
        gate = AsyncMock(return_value=SimpleNamespace(
            book_id=BOOK, work_id=uuid.uuid4(), project_id=PROJECT))
        with patch.object(srv, "_ctx", side_effect=lambda c: c), \
             patch.object(srv, "get_pool", return_value=object()), \
             patch.object(srv, "WorksRepo", return_value=works), \
             patch.object(srv, "OutlineRepo", return_value=outline), \
             patch.object(srv, "_resolve_pid", return_value=PROJECT), \
             patch.object(srv, "_book_or_deny", gate):
            return await srv.composition_outline_node_create(
                _Ctx(), srv._NodeCreateArgs(
                    project_id=str(PROJECT), kind="chapter", title="Chương 1"))

    @pytest.mark.asyncio
    async def test_a_node_with_no_chapter_is_labelled_plan_only(self):
        out = await self._create(None)
        assert out["_status"] == "plan_only"
        assert "materialise" in out["_note"].lower()
        # The undo hint must survive — the label is additive, not a replacement.
        assert out["_meta"]["undo_hint"]["tool"] == "composition_outline_node_delete"

    @pytest.mark.asyncio
    async def test_a_node_bound_to_a_chapter_carries_no_such_label(self):
        out = await self._create(CHAPTER)
        assert "_status" not in out
        assert "_note" not in out


class TestBindingAPlanNodeToAChapter:
    """`chapter_id` used to be CREATE-ONLY, which made a plan-only node a dead end: it is
    created NULL (the normal state), the compose panel keys off that column, and nothing
    an author or agent could reach could set it afterwards. PlanForge's bootstrap stamps
    it with its own SQL, so an outline built OUTSIDE a plan run could never be drafted
    into — ever. The repo has always listed `chapter_id` in `_UPDATABLE_COLUMNS`; only the
    tool withheld it."""

    @staticmethod
    async def _update(**over):
        # The undo-hint builder reads `getattr(prior, f)` for every patched field, so the
        # prior must carry them. `chapter_id=None` is the REAL shape of a plan-only node,
        # and it is why binding one emits no undo_hint: there is no clear verb, so a
        # reverse patch of `chapter_id: null` would silently no-op while claiming success.
        prior = SimpleNamespace(
            id=NODE, project_id=PROJECT, version=1, chapter_id=None, title="Cảnh 1",
        )
        updated = SimpleNamespace(
            id=NODE, chapter_id=CHAPTER, version=2,
            model_dump=lambda mode="json": {"id": str(NODE), "chapter_id": str(CHAPTER)},
        )
        outline = AsyncMock()
        outline.get_node = AsyncMock(return_value=prior)
        outline.update_node = AsyncMock(return_value=updated)
        gate = AsyncMock(return_value=SimpleNamespace(
            book_id=BOOK, work_id=uuid.uuid4(), project_id=PROJECT))
        with patch.object(srv, "_ctx", side_effect=lambda c: c), \
             patch.object(srv, "get_pool", return_value=object()), \
             patch.object(srv, "WorksRepo", return_value=AsyncMock()), \
             patch.object(srv, "OutlineRepo", return_value=outline), \
             patch.object(srv, "_book_or_deny", gate):
            await srv.composition_outline_node_update(_Ctx(), srv._NodeUpdateArgs(
                project_id=str(PROJECT), node_id=str(NODE), expected_version=1, **over))
        return outline.update_node.await_args.args[1]

    @pytest.mark.asyncio
    async def test_chapter_id_reaches_the_patch(self):
        patch_sent = await self._update(chapter_id=str(CHAPTER))
        assert patch_sent["chapter_id"] == CHAPTER, "must be a UUID, not the raw string"

    @pytest.mark.asyncio
    async def test_an_unrelated_update_never_touches_chapter_id(self):
        """Sparse-patch convention: absent means leave unchanged. A title edit must not
        silently unbind a scene from its chapter."""
        patch_sent = await self._update(title="Cảnh 1 — bản sửa")
        assert "chapter_id" not in patch_sent

    @pytest.mark.asyncio
    async def test_binding_emits_no_undo_hint_rather_than_a_lying_one(self):
        """A plan-only node's prior `chapter_id` is None, and the reverse patch has no
        clear verb — `chapter_id: null` would be read as "leave unchanged" and silently
        no-op while the UI claimed the undo applied. The existing reversibility rule is
        generic (`any(v is None …)`), so binding is correctly un-undoable; this pins that
        it stays that way rather than growing a hard-coded field list that forgets it."""
        prior = SimpleNamespace(id=NODE, project_id=PROJECT, version=1, chapter_id=None)
        updated = SimpleNamespace(
            id=NODE, chapter_id=CHAPTER, version=2,
            model_dump=lambda mode="json": {"id": str(NODE)},
        )
        outline = AsyncMock()
        outline.get_node = AsyncMock(return_value=prior)
        outline.update_node = AsyncMock(return_value=updated)
        gate = AsyncMock(return_value=SimpleNamespace(
            book_id=BOOK, work_id=uuid.uuid4(), project_id=PROJECT))
        with patch.object(srv, "_ctx", side_effect=lambda c: c), \
             patch.object(srv, "get_pool", return_value=object()), \
             patch.object(srv, "WorksRepo", return_value=AsyncMock()), \
             patch.object(srv, "OutlineRepo", return_value=outline), \
             patch.object(srv, "_book_or_deny", gate):
            out = await srv.composition_outline_node_update(_Ctx(), srv._NodeUpdateArgs(
                project_id=str(PROJECT), node_id=str(NODE), expected_version=1,
                chapter_id=str(CHAPTER)))
        assert out["_meta"]["undo_hint"] is None
