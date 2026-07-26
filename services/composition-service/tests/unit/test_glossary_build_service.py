"""Glossary-build FSM service — transitions, driver, skip-not-wedge, propose.

Fake repo (in-memory) + fake LLM + fake glossary client: these prove the FSM
contract (optimistic transitions, resume-safe items, loud failure) without a DB.
The SQL itself is exercised by the M4 live smoke."""
from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from app.services.glossary_build import service as svc_mod
from app.services.glossary_build.service import (
    GlossaryBuildError,
    GlossaryBuildService,
)

OWNER = uuid.uuid4()
BOOK = uuid.uuid4()


class FakeRepo:
    def __init__(self):
        self.runs: dict = {}
        self.items: list[dict] = []

    async def create_run(self, *, owner, book_id, params):
        rid = uuid.uuid4()
        row = {"run_id": rid, "owner_user_id": owner, "book_id": book_id,
               "params": params, "status": "draft", "worklist": [], "edges": [],
               "error_message": None}
        self.runs[rid] = row
        return dict(row)

    async def get_run(self, run_id, owner):
        r = self.runs.get(run_id)
        return dict(r) if r and r["owner_user_id"] == owner else None

    async def transition(self, run_id, owner, from_status, to_status, **fields):
        r = self.runs.get(run_id)
        if not r or r["owner_user_id"] != owner or r["status"] not in from_status:
            return None
        r["status"] = to_status
        r.update(fields)
        return dict(r)

    async def insert_items(self, run, worklist):
        for i, w in enumerate(worklist):
            self.items.append({"item_id": uuid.uuid4(), "run_id": run["run_id"],
                               "owner_user_id": run["owner_user_id"],
                               "book_id": run["book_id"], "ordinal": i,
                               "name": w["name"], "kind": w["kind"],
                               "depth": w.get("depth", "standard"),
                               "status": "pending", "built": None, "sections": None,
                               "relations": [], "skip_reason": None})

    async def list_items(self, run_id, owner):
        return [dict(i) for i in self.items if i["run_id"] == run_id]

    async def update_item(self, item_id, owner, **fields):
        for i in self.items:
            if i["item_id"] == item_id:
                i.update(fields)


class FakeLLMClient:
    """Sequential completed jobs whose result carries the given contents."""

    def __init__(self, contents):
        self.contents = list(contents)
        self.calls = 0

    async def submit_and_wait(self, **kw):
        self.calls += 1
        content = self.contents.pop(0) if self.contents else self.contents_default()
        class Job:  # gateway shape: result["messages"][0]["content"] (memory lesson)
            status = "completed"
            result = {"messages": [{"content": content}]}
        return Job()

    def contents_default(self):
        return "{}"


class FakeGlossary:
    def __init__(self):
        self.seeded = None

    async def select_for_context(self, *a, **kw):
        return [{"cached_name": "Lâm Uyên"}]

    async def seed_entities_or_raise(self, book_id, *, source_language, entities):
        self.seeded = entities
        return [{"entity_id": str(uuid.uuid4()), "name": e["name"],
                 "kind_code": e["kind_code"]} for e in entities]


PARAMS = {"model_source": "user_model", "model_ref": str(uuid.uuid4()),
          "source_text": "story", "lang": "vi"}


def make_svc(llm_contents):
    repo = FakeRepo()
    gl = FakeGlossary()
    s = GlossaryBuildService(repo, FakeLLMClient(llm_contents), gl)
    return s, repo, gl


@pytest.mark.asyncio
async def test_create_requires_model_ref_and_source_text():
    s, *_ = make_svc([])
    with pytest.raises(GlossaryBuildError) as exc:
        await s.create_run(owner=OWNER, book_id=BOOK, params={"model_source": "user_model"})
    assert exc.value.code == "MISSING_PARAMS"


@pytest.mark.asyncio
async def test_plan_dedups_against_existing_glossary_and_reaches_plan_ready():
    wl = [{"name": "Lâm Uyên", "kind": "character"},          # already in glossary → dropped
          {"name": "Tô Thanh Dao", "kind": "character", "depth": "deep"}]
    s, repo, _ = make_svc([json.dumps(wl)])
    run = await s.create_run(owner=OWNER, book_id=BOOK, params=PARAMS)
    out = await s.plan(run["run_id"], OWNER)
    assert out["status"] == "plan_ready"
    assert [w["name"] for w in out["worklist"]] == ["Tô Thanh Dao"]


@pytest.mark.asyncio
async def test_plan_twice_is_a_409_not_a_second_llm_run():
    s, repo, _ = make_svc([json.dumps([{"name": "X", "kind": "character"}])])
    run = await s.create_run(owner=OWNER, book_id=BOOK, params=PARAMS)
    await s.plan(run["run_id"], OWNER)
    with pytest.raises(GlossaryBuildError) as exc:
        await s.plan(run["run_id"], OWNER)
    assert exc.value.code == "BAD_STATE"


def _built(name):
    return json.dumps({"name": name, "kind": "character",
                       "attributes": {"role": "r"}, "relations": []})


@pytest.mark.asyncio
async def test_full_drive_builds_proposes_and_records_entity_ids():
    wl = [{"name": "A", "kind": "character"}, {"name": "B", "kind": "character"}]
    # planner, build A, build B  (standard = 1 call each)
    s, repo, gl = make_svc([json.dumps(wl), _built("A"), _built("B")])
    run = await s.create_run(owner=OWNER, book_id=BOOK, params=PARAMS)
    await s.plan(run["run_id"], OWNER)
    await s.approve_plan(run["run_id"], OWNER)
    await asyncio.sleep(0.05)  # let the driver task finish
    final = await s.get(run["run_id"], OWNER)
    assert final["status"] == "proposed"
    assert [i["status"] for i in final["items"]] == ["proposed", "proposed"]
    assert all(i.get("proposed_entity_id") for i in final["items"])
    assert [e["name"] for e in gl.seeded] == ["A", "B"]


@pytest.mark.asyncio
async def test_one_bad_item_skips_with_reason_and_the_run_continues():
    wl = [{"name": "Bad", "kind": "character"}, {"name": "Good", "kind": "character"}]
    # planner, Bad ×2 (invalid + retry invalid → skip), Good
    s, repo, gl = make_svc([json.dumps(wl), "garbage", "more garbage", _built("Good")])
    run = await s.create_run(owner=OWNER, book_id=BOOK, params=PARAMS)
    await s.plan(run["run_id"], OWNER)
    await s.approve_plan(run["run_id"], OWNER)
    await asyncio.sleep(0.05)
    final = await s.get(run["run_id"], OWNER)
    assert final["status"] == "proposed"
    by_name = {i["name"]: i for i in final["items"]}
    assert by_name["Bad"]["status"] == "skipped"
    assert "invalid model output" in by_name["Bad"]["skip_reason"]
    assert by_name["Good"]["status"] == "proposed"
    assert [e["name"] for e in gl.seeded] == ["Good"]  # only the built item proposed


@pytest.mark.asyncio
async def test_approve_plan_accepts_a_human_trimmed_worklist():
    wl = [{"name": "A", "kind": "character"}, {"name": "B", "kind": "character"}]
    s, repo, _ = make_svc([json.dumps(wl), _built("B")])
    run = await s.create_run(owner=OWNER, book_id=BOOK, params=PARAMS)
    await s.plan(run["run_id"], OWNER)
    await s.approve_plan(run["run_id"], OWNER,
                         worklist=[{"name": "B", "kind": "character"}])  # human trimmed A
    await asyncio.sleep(0.05)
    final = await s.get(run["run_id"], OWNER)
    assert [i["name"] for i in final["items"]] == ["B"]


@pytest.mark.asyncio
async def test_glossary_write_failure_fails_the_run_loudly():
    class ExplodingGlossary(FakeGlossary):
        async def seed_entities_or_raise(self, *a, **kw):
            raise RuntimeError("glossary down")
    wl = [{"name": "A", "kind": "character"}]
    repo = FakeRepo()
    s = GlossaryBuildService(repo, FakeLLMClient([json.dumps(wl), _built("A")]),
                             ExplodingGlossary())
    run = await s.create_run(owner=OWNER, book_id=BOOK, params=PARAMS)
    await s.plan(run["run_id"], OWNER)
    await s.approve_plan(run["run_id"], OWNER)
    await asyncio.sleep(0.05)
    final = await s.get(run["run_id"], OWNER)
    assert final["status"] == "failed"          # loud, never a silent stall
    assert "glossary down" in final["error_message"]


@pytest.mark.asyncio
async def test_cancel_stops_a_building_run():
    wl = [{"name": "A", "kind": "character"}]
    s, repo, _ = make_svc([json.dumps(wl)])
    run = await s.create_run(owner=OWNER, book_id=BOOK, params=PARAMS)
    await s.plan(run["run_id"], OWNER)
    await s.approve_plan(run["run_id"], OWNER)
    out = await s.cancel(run["run_id"], OWNER)
    assert out["status"] == "cancelled"
