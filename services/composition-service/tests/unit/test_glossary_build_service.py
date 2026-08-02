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


# The REAL shape read from book_attributes: kind_code → ordered attr defs.
FAKE_ONTOLOGY = {
    # WIDE, like the real thing (the live `character` kind has 13 attributes) —
    # so it exercises the slice path and is NEVER batched.
    "character": [
        {"code": "name", "is_required": True, "sort_order": 1},
        {"code": "role", "is_required": False, "sort_order": 2},
        {"code": "description", "is_required": False, "sort_order": 3},
        {"code": "gender", "is_required": False, "sort_order": 4},
        {"code": "affiliation", "is_required": False, "sort_order": 5},
        {"code": "personality", "is_required": False, "sort_order": 6},
    ],
    # a deliberately NARROW kind — the batching + no-slice path
    "terminology": [
        {"code": "term", "is_required": True, "sort_order": 1},
        {"code": "definition", "is_required": False, "sort_order": 2},
    ],
    "organization": [
        {"code": "name", "is_required": True, "sort_order": 1},
        {"code": "description", "is_required": False, "sort_order": 2},
    ],
}


class FakeGlossary:
    def __init__(self):
        self.seeded = None
        self.ontology = FAKE_ONTOLOGY

    async def read_book_ontology(self, bearer, book_id):
        return self.ontology

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
    assert "nothing that fits this kind's schema" in by_name["Bad"]["skip_reason"]
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


# ── M3: the KG phase ─────────────────────────────────────────────────────────

class FakeKnowledge:
    """Models the REAL knowledge shapes the M4 maiden run exposed: the graph node
    `id` is a HASH distinct from the glossary entity_id, and the project's entity
    list also carries entities from EARLIER builds."""

    def __init__(self, *, project=True, relation=True, preexisting=(), projects=True,
                 lore_index=None):
        self._project = project
        self._relation = relation
        self._projects = projects            # False ⇒ the graph accepts nothing
        # The per-outcome tally from indexing the built lore as retrievable passages.
        # Default models the CURRENT dev reality that made this whole gap invisible:
        # a project with no embedding model indexes NOTHING.
        self._lore_index = lore_index if lore_index is not None else {
            "entities_seen": 0, "outcomes": {},
        }
        self.projected = None
        self.relations = []
        # name → graph node id, for lore that existed before this run
        self._graph = {name: f"hash-{i}" for i, name in enumerate(preexisting)}
        self._anchor: dict[str, str] = {}

    async def create_project(self, book_id, name, bearer, **kw):
        return {"project_id": str(uuid.uuid4())} if self._project else None

    async def project_entities_from_glossary(self, bearer, *, project_id, entity_ids=None):
        self.projected = entity_ids
        if not self._projects:
            return {"created": 0, "existing": 0, "seen": 0}
        for gid in entity_ids or []:
            self._anchor[str(gid)] = f"hash-g-{gid[:8]}"
        return {"created": len(entity_ids or []), "existing": 0}

    async def index_glossary_passages(self, *, project_id):
        return self._lore_index

    async def list_project_entities(self, bearer, *, project_id, limit=200):
        # the run's own items (resolved via their glossary anchor) + pre-existing lore
        out = [{"id": nid, "name": n, "glossary_entity_id": None}
               for n, nid in self._graph.items()]
        out += [{"id": nid, "name": None, "glossary_entity_id": gid}
                for gid, nid in self._anchor.items()]
        return out

    def name_the_projected(self, mapping: dict[str, str]) -> None:
        """Give the just-projected nodes their names (what the real list returns)."""
        for gid, name in mapping.items():
            if gid in self._anchor:
                self._graph[name] = self._anchor[gid]

    async def create_relation(self, bearer, *, subject_id, predicate, object_id):
        if not self._relation:
            return None
        self.relations.append((subject_id, predicate, object_id))
        return {"id": str(uuid.uuid4())}


def _built_rel(name, target, rtype="member_of"):
    return json.dumps({"name": name, "kind": "character",
                       "attributes": {"role": "r"},
                       "relations": [{"target_name": target, "type": rtype, "note": ""}]})


async def _run_to_proposed(llm_contents, knowledge=None):
    repo, gl = FakeRepo(), FakeGlossary()
    s = GlossaryBuildService(repo, FakeLLMClient(llm_contents), gl, knowledge=knowledge)
    run = await s.create_run(owner=OWNER, book_id=BOOK, params=PARAMS)
    await s.plan(run["run_id"], OWNER)
    await s.approve_plan(run["run_id"], OWNER)
    await asyncio.sleep(0.05)
    return s, run["run_id"]


@pytest.mark.asyncio
async def test_project_kg_resolves_relation_NAMES_to_entity_ids():
    """THE design point: the executor only ever emits NAMES; ids are resolved
    HERE, once, by the platform — the model never sees a UUID."""
    wl = [{"name": "Tô Thanh Dao", "kind": "character"},
          {"name": "Tô gia", "kind": "character"}]
    kg = FakeKnowledge(preexisting=["Tô Thanh Dao", "Tô gia"])
    s, run_id = await _run_to_proposed(
        [json.dumps(wl), _built_rel("Tô Thanh Dao", "Tô gia"), _built_rel("Tô gia", "Tô Thanh Dao")],
        knowledge=kg)
    out = await s.project_kg(run_id, OWNER, "bearer")
    assert out["status"] == "edges_ready"
    edges = out["edges"]
    assert len(edges) == 2 and all(not e["unresolved"] for e in edges)
    assert all(e["source_id"] and e["target_id"] for e in edges)
    assert len(kg.projected) == 2  # both proposed entities projected as nodes


@pytest.mark.asyncio
async def test_unresolvable_relation_name_is_kept_and_flagged_not_dropped():
    """A name that matches nothing must be VISIBLE to the human, not silently lost."""
    wl = [{"name": "A", "kind": "character"}]
    kg = FakeKnowledge(preexisting=["A"])
    s, run_id = await _run_to_proposed(
        [json.dumps(wl), _built_rel("A", "Someone Never Built")], knowledge=kg)
    out = await s.project_kg(run_id, OWNER, "bearer")
    (edge,) = out["edges"]
    assert edge["unresolved"] is True and edge["target_id"] is None
    assert edge["target_name"] == "Someone Never Built"


@pytest.mark.asyncio
async def test_approve_edges_writes_only_resolved_and_reports_the_failures():
    wl = [{"name": "A", "kind": "character"}, {"name": "B", "kind": "character"}]
    kg = FakeKnowledge(preexisting=["A", "B"])
    s, run_id = await _run_to_proposed(
        [json.dumps(wl), _built_rel("A", "B"), _built_rel("B", "Ghost")], knowledge=kg)
    await s.project_kg(run_id, OWNER, "bearer")
    out = await s.approve_edges(run_id, OWNER, "bearer")
    assert out["status"] == "done"
    assert out["params"]["edges_applied"] == 1     # A→B
    assert out["params"]["edges_failed"] == 1      # B→Ghost (unresolved)
    assert len(kg.relations) == 1


@pytest.mark.asyncio
async def test_a_failed_relation_write_is_counted_not_rounded_up():
    wl = [{"name": "A", "kind": "character"}, {"name": "B", "kind": "character"}]
    kg = FakeKnowledge(relation=False, preexisting=["A", "B"])   # every write fails
    s, run_id = await _run_to_proposed(
        [json.dumps(wl), _built_rel("A", "B"), _built("B")], knowledge=kg)
    await s.project_kg(run_id, OWNER, "bearer")
    out = await s.approve_edges(run_id, OWNER, "bearer")
    assert out["params"]["edges_applied"] == 0 and out["params"]["edges_failed"] == 1


@pytest.mark.asyncio
async def test_project_kg_records_whether_the_built_lore_is_RETRIEVABLE():
    """Projecting entities makes them EXIST; indexing makes them FINDABLE. The packer's
    lore lens searches passages, and a project with no embedding model indexes nothing —
    so the tally must reach the run, or the wizard reports a world the writer cannot
    actually look up."""
    wl = [{"name": "A", "kind": "character"}]
    kg = FakeKnowledge(lore_index={"entities_seen": 12,
                                   "outcomes": {"no_embedding_model": 12}})
    s, run_id = await _run_to_proposed([json.dumps(wl), _built("A")], knowledge=kg)
    out = await s.project_kg(run_id, OWNER, "bearer")
    assert out["params"]["lore_index"]["outcomes"] == {"no_embedding_model": 12}


@pytest.mark.asyncio
async def test_a_lore_index_outage_degrades_the_report_not_the_phase():
    """Indexing is additive — a knowledge outage must not fail a KG phase whose real
    work (entities + edges) already succeeded, but it must NOT read as indexed either."""
    wl = [{"name": "A", "kind": "character"}]
    kg = FakeKnowledge()
    kg.index_glossary_passages = _raise_unavailable
    s, run_id = await _run_to_proposed([json.dumps(wl), _built("A")], knowledge=kg)
    out = await s.project_kg(run_id, OWNER, "bearer")
    assert out["status"] == "edges_ready"
    assert out["params"]["lore_index"] == {"error": "unavailable"}


async def _raise_unavailable(*, project_id):
    """The real client swallows transport errors and returns None (degrade-safe)."""
    return None


@pytest.mark.asyncio
async def test_project_kg_without_a_knowledge_client_is_explicit_not_silent():
    wl = [{"name": "A", "kind": "character"}]
    s, run_id = await _run_to_proposed([json.dumps(wl), _built("A")], knowledge=None)
    with pytest.raises(GlossaryBuildError) as exc:
        await s.project_kg(run_id, OWNER, "bearer")
    assert exc.value.code == "KG_UNAVAILABLE"


@pytest.mark.asyncio
async def test_project_kg_from_the_wrong_state_is_a_409():
    wl = [{"name": "A", "kind": "character"}]
    kg = FakeKnowledge(preexisting=["A"])
    repo, gl = FakeRepo(), FakeGlossary()
    s = GlossaryBuildService(repo, FakeLLMClient([json.dumps(wl)]), gl, knowledge=kg)
    run = await s.create_run(owner=OWNER, book_id=BOOK, params=PARAMS)
    with pytest.raises(GlossaryBuildError) as exc:
        await s.project_kg(run["run_id"], OWNER, "bearer")   # still draft
    assert exc.value.code == "BAD_STATE"


# ── /review-impl findings (2026-07-27) ───────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_actually_STOPS_the_driver_from_spending_more():
    """HIGH (review): the driver ran to the end of the worklist after /cancel, because
    the task registry lived on a PER-REQUEST service instance — cancel flipped the row
    and the LLM kept being called (real money). The driver must re-read the row and
    stop. Driven through a SECOND service instance, exactly like the real HTTP path."""
    wl = [{"name": "A", "kind": "character"}, {"name": "B", "kind": "character"},
          {"name": "C", "kind": "character"}]
    repo, gl = FakeRepo(), FakeGlossary()

    # Deterministic (no sleep races): the moment the FIRST item's build call lands,
    # a DIFFERENT service instance cancels — exactly the real /cancel request shape.
    state: dict = {}

    class CancellingLLM(FakeLLMClient):
        async def submit_and_wait(self, **kw):
            job = await super().submit_and_wait(**kw)
            if self.calls == 2 and "s2" in state:            # 1 = planner, 2 = item A
                await state["s2"].cancel(state["run_id"], OWNER)
            return job

    llm = CancellingLLM([json.dumps(wl), _built("A"), _built("B"), _built("C")])
    s1 = GlossaryBuildService(repo, llm, gl)
    run = await s1.create_run(owner=OWNER, book_id=BOOK, params=PARAMS)
    await s1.plan(run["run_id"], OWNER)
    state["s2"] = GlossaryBuildService(repo, llm, gl)         # the /cancel request's instance
    state["run_id"] = run["run_id"]

    await s1.approve_plan(run["run_id"], OWNER)
    await asyncio.sleep(0.05)

    final = await state["s2"].get(run["run_id"], OWNER)
    assert final["status"] == "cancelled"
    # THE assertion: exactly planner + item A ran. B and C were never paid for.
    assert llm.calls == 2, f"the driver kept calling the LLM after cancel ({llm.calls} calls)"
    by_name = {i["name"]: i["status"] for i in final["items"]}
    assert by_name["B"] == "pending" and by_name["C"] == "pending"


@pytest.mark.asyncio
async def test_an_item_the_glossary_SKIPPED_is_not_reported_as_proposed():
    """MED (review): the glossary skips a name that already exists, returning nothing
    for it. Marking the item `proposed` anyway was a FALSE SUCCESS — the wizard counted
    it as filed and the KG phase silently dropped it (no entity id to project)."""
    class PartialGlossary(FakeGlossary):
        async def seed_entities_or_raise(self, book_id, *, source_language, entities):
            kept = [e for e in entities if e["name"] != "Dup"]        # 'Dup' already exists
            self.seeded = entities
            return [{"entity_id": str(uuid.uuid4()), "name": e["name"],
                     "kind_code": e["kind_code"]} for e in kept]

    wl = [{"name": "Dup", "kind": "character"}, {"name": "New", "kind": "character"}]
    repo = FakeRepo()
    s = GlossaryBuildService(repo, FakeLLMClient([json.dumps(wl), _built("Dup"), _built("New")]),
                             PartialGlossary())
    run = await s.create_run(owner=OWNER, book_id=BOOK, params=PARAMS)
    await s.plan(run["run_id"], OWNER)
    await s.approve_plan(run["run_id"], OWNER)
    await asyncio.sleep(0.05)

    by_name = {i["name"]: i for i in (await s.get(run["run_id"], OWNER))["items"]}
    assert by_name["New"]["status"] == "proposed" and by_name["New"]["proposed_entity_id"]
    assert by_name["Dup"]["status"] == "skipped"
    assert "already has an entry" in by_name["Dup"]["skip_reason"]


@pytest.mark.asyncio
async def test_a_second_concurrent_run_is_a_clean_409_not_a_raw_constraint_500():
    """MED (review): `draft` sits outside uq_glossary_build_active_book on purpose, so a
    second run collides on its first REAL transition. That must surface as ACTIVE_RUN."""
    import asyncpg

    class CollidingRepo(FakeRepo):
        async def transition(self, run_id, owner, from_status, to_status, **fields):
            if to_status == "planning":
                raise asyncpg.UniqueViolationError("uq_glossary_build_active_book")
            return await super().transition(run_id, owner, from_status, to_status, **fields)

    s = GlossaryBuildService(CollidingRepo(), FakeLLMClient([]), FakeGlossary())
    run = await s.create_run(owner=OWNER, book_id=BOOK, params=PARAMS)
    with pytest.raises(GlossaryBuildError) as exc:
        await s.plan(run["run_id"], OWNER)
    assert exc.value.status == 409 and exc.value.code == "ACTIVE_RUN"


@pytest.mark.asyncio
async def test_every_mutating_op_returns_the_run_WITH_its_items():
    """Live-caught driving the wizard (2026-07-27): project_kg answered the bare
    transition row, so the panel's "N entries filed" counter dropped to 0 after the
    KG step. Every mutating op must return the FULL run view."""
    wl = [{"name": "A", "kind": "character"}]
    kg = FakeKnowledge(preexisting=["A"])
    s, run_id = await _run_to_proposed([json.dumps(wl), _built("A")], knowledge=kg)

    after_kg = await s.project_kg(run_id, OWNER, "bearer")
    assert [i["name"] for i in after_kg["items"]] == ["A"]
    after_edges = await s.approve_edges(run_id, OWNER, "bearer")
    assert [i["name"] for i in after_edges["items"]] == ["A"]


def test_relation_types_cover_concepts_not_only_characters():
    """The closed set must have a member that FITS a lore term, or the model is forced
    into a false character-verb edge (live: "Chân Linh mentor_of Lâm Uyên")."""
    from app.services.glossary_build.prompts import RELATION_TYPES
    assert {"part_of", "property_of", "related_to"} <= set(RELATION_TYPES)


@pytest.mark.asyncio
async def test_cancel_stops_a_building_run():
    wl = [{"name": "A", "kind": "character"}]
    s, repo, _ = make_svc([json.dumps(wl)])
    run = await s.create_run(owner=OWNER, book_id=BOOK, params=PARAMS)
    await s.plan(run["run_id"], OWNER)
    await s.approve_plan(run["run_id"], OWNER)
    out = await s.cancel(run["run_id"], OWNER)
    assert out["status"] == "cancelled"


# ── M6: schema-aware executor (rules measured in eval/schema_recall_poc.py) ───

def test_select_fields_narrows_only_a_WIDE_schema():
    """POC: cutting terminology 4→2 gained nothing (123 ch/field both ways), but
    cutting power_system 7→3 gained +66%. So narrow by THRESHOLD, not mechanically."""
    from app.services.glossary_build.prompts import select_fields
    narrow = [{"code": c, "is_required": c == "term", "sort_order": i}
              for i, c in enumerate(["term", "definition", "category", "usage_note"])]
    wide = [{"code": c, "is_required": c == "name", "sort_order": i}
            for i, c in enumerate(["name", "aliases", "type", "rank", "user",
                                   "effects", "description"])]
    assert select_fields(narrow, deep=False) == ["term", "definition", "category", "usage_note"]
    cut = select_fields(wide, deep=False)
    assert len(cut) == 4 and cut[0] == "name"          # required first, then sort_order
    assert select_fields(wide, deep=True) == [d["code"] for d in wide]  # deep keeps all


def test_prompt_carries_the_kinds_REAL_fields_and_NO_hints():
    """The bug: a character-shaped field list was sent for every kind. And the POC
    showed the authored hints make quality WORSE (123→96 ch/field), so codes only."""
    from app.services.glossary_build.prompts import executor_messages
    sysmsg = executor_messages("s", "Chân Linh", "terminology",
                               ["term", "definition"], "vi")[0]["content"]
    assert '"term"' in sysmsg and '"definition"' in sysmsg
    assert "gender" not in sysmsg and "personality" not in sysmsg   # the old blind set
    assert "Định nghĩa ngắn gọn" not in sysmsg                      # no auto_fill_prompt


@pytest.mark.asyncio
async def test_a_kind_with_NO_schema_is_skipped_never_written_blind():
    """THE empty-shell fix: no attribute schema ⇒ skip with a reason. Guessing the
    fields is exactly what wrote 5 nameless rows on the first live run."""
    wl = [{"name": "Ghost", "kind": "character"}]
    repo, gl = FakeRepo(), FakeGlossary()
    gl.ontology = {}                                   # ontology unavailable
    s = GlossaryBuildService(repo, FakeLLMClient([json.dumps(wl), _built("Ghost")]), gl)
    run = await s.create_run(owner=OWNER, book_id=BOOK, params=PARAMS)
    await s.plan(run["run_id"], OWNER)
    await s.approve_plan(run["run_id"], OWNER)
    await asyncio.sleep(0.05)
    final = await s.get(run["run_id"], OWNER)
    item = final["items"][0]
    assert item["status"] == "skipped"
    assert "no attribute schema" in item["skip_reason"]
    assert gl.seeded in (None, [])                     # nothing written to the glossary


@pytest.mark.asyncio
async def test_attributes_outside_the_kinds_schema_are_dropped_not_written():
    """A character-shaped payload against `terminology` must not reach the glossary."""
    wl = [{"name": "Chân Linh", "kind": "terminology"}]
    repo, gl = FakeRepo(), FakeGlossary()
    bad = json.dumps({"name": "Chân Linh", "attributes": {
        "gender": "n/a", "personality": "cold", "definition": "tầng bất biến"}})
    s = GlossaryBuildService(repo, FakeLLMClient([json.dumps(wl), bad]), gl)
    run = await s.create_run(owner=OWNER, book_id=BOOK, params=PARAMS)
    await s.plan(run["run_id"], OWNER)
    await s.approve_plan(run["run_id"], OWNER)
    await asyncio.sleep(0.05)
    assert gl.seeded and gl.seeded[0]["attributes"] == {"definition": "tầng bất biến"}


@pytest.mark.asyncio
async def test_narrow_same_kind_items_are_built_in_ONE_batched_call():
    """POC E: same-kind batching is 3x cheaper with only mild decay — but ONLY for
    narrow schemas, and never mixing kinds."""
    wl = [{"name": "Trận pháp", "kind": "terminology"},
          {"name": "Luyện khí", "kind": "terminology"}]
    batch = json.dumps([
        {"name": "Trận pháp", "attributes": {"term": "Trận pháp", "definition": "d1"}},
        {"name": "Luyện khí", "attributes": {"term": "Luyện khí", "definition": "d2"}},
    ])
    repo, gl = FakeRepo(), FakeGlossary()
    llm = FakeLLMClient([json.dumps(wl), batch])
    s = GlossaryBuildService(repo, llm, gl)
    run = await s.create_run(owner=OWNER, book_id=BOOK, params=PARAMS)
    await s.plan(run["run_id"], OWNER)
    await s.approve_plan(run["run_id"], OWNER)
    await asyncio.sleep(0.05)
    final = await s.get(run["run_id"], OWNER)
    assert [i["status"] for i in final["items"]] == ["proposed", "proposed"]
    assert llm.calls == 2, "planner + ONE batch call — not one call per item"


@pytest.mark.asyncio
async def test_a_failed_batch_falls_back_to_per_item_not_lost():
    """Batching trades failure ISOLATION for tokens — a bad batch must not lose the
    whole group; each item is retried on its own."""
    wl = [{"name": "Trận pháp", "kind": "terminology"},
          {"name": "Luyện khí", "kind": "terminology"}]
    per_item = json.dumps({"attributes": {"term": "t", "definition": "d"}})
    repo, gl = FakeRepo(), FakeGlossary()
    # batch call returns garbage (x2 = the retry), then each item answers alone
    llm = FakeLLMClient([json.dumps(wl), "garbage", "garbage", per_item, per_item])
    s = GlossaryBuildService(repo, llm, gl)
    run = await s.create_run(owner=OWNER, book_id=BOOK, params=PARAMS)
    await s.plan(run["run_id"], OWNER)
    await s.approve_plan(run["run_id"], OWNER)
    await asyncio.sleep(0.05)
    final = await s.get(run["run_id"], OWNER)
    assert [i["status"] for i in final["items"]] == ["proposed", "proposed"]


# ── a book must never be stranded by its own checkpoint (2026-08-03) ─────────

@pytest.mark.asyncio
@pytest.mark.parametrize("stuck", ["kg_projecting", "edges_ready"])
async def test_every_state_that_HOLDS_the_active_slot_is_cancellable(stuck):
    """Found on the Mị Đế book: a run sat at `edges_ready` for a week and the book could
    not start a new one.

    `uq_glossary_build_active_book` covers six states — planning, plan_ready, building,
    proposing, kg_projecting, edges_ready — and `cancel` accepted five of them. So a run
    that reached the last two held the slot forever: `/plan` refused with ACTIVE_RUN and
    `/cancel` refused with BAD_STATE. No way forward and no way out.

    `edges_ready` is a HUMAN checkpoint (CP3 — approve relationships). A checkpoint that
    cannot be abandoned is a trap, not a gate.
    """
    repo, gl = FakeRepo(), FakeGlossary()
    s = GlossaryBuildService(repo, FakeLLMClient([]), gl)
    run = await s.create_run(owner=OWNER, book_id=BOOK, params=PARAMS)
    repo.runs[run["run_id"]]["status"] = stuck

    out = await s.cancel(run["run_id"], OWNER)
    assert out["status"] == "cancelled", f"a run at {stuck} could not be cancelled"


@pytest.mark.asyncio
async def test_the_cancellable_set_COVERS_the_active_index():
    """The rule, not one example: whatever holds the slot must be releasable.

    Pinned against the index's own state list so the two cannot drift again — adding a
    seventh blocking state without making it cancellable reds here.
    """
    import re, pathlib
    mig = (pathlib.Path(__file__).resolve().parents[2] / "app" / "db" / "migrate.py"
           ).read_text(encoding="utf-8")
    idx = re.search(r"uq_glossary_build_active_book.*?WHERE status IN \(([^)]*)\)",
                    mig, re.DOTALL)
    assert idx, "the active-run index changed shape — re-read it before trusting this test"
    blocking = set(re.findall(r"'([a-z_]+)'", idx.group(1)))

    svc = (pathlib.Path(__file__).resolve().parents[2] / "app" / "services"
           / "glossary_build" / "service.py").read_text(encoding="utf-8")
    body = svc[svc.index("async def cancel("):]
    # The list ARGUMENT of the transition call, not "everything before the word
    # cancelled" — that first draft cut at the word inside the comment above the call and
    # read the prose as the code. Same mistake this repo has a rule about, made while
    # writing the test for it.
    call = re.search(r"self\._repo\.transition\((.*?)\)", body, re.DOTALL)
    assert call, "the cancel transition changed shape — re-read it"
    states = re.search(r"\[(.*?)\]", call.group(1), re.DOTALL)
    assert states, "cancel no longer passes a list of from-states"
    cancellable = set(re.findall(r"['\"]([a-z_]+)['\"]", states.group(1)))

    missing = sorted(blocking - cancellable)
    assert missing == [], (
        f"these states hold the active-run slot but cannot be cancelled: {missing}. "
        f"A book with a run in one of them can neither continue nor start over."
    )
