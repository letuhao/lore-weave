"""T35f — the recanon backfill's APPLY path, executed against a real Neo4j.

🔴 **WHY THIS EXISTS.** `plan_recanon` is a pure function with ten unit rules. `run_recanon_backfill`
— the half that WRITES — is marked `# pragma: no cover (real I/O)` and had never been executed by
anything. T35 owes an operator a command that re-keys **1819 nodes and merges 1** on the shared dev
graph, and the only evidence it works was that the plan it produces looks right.

That is the exact split this session has now found three times (T35e's collision guard the loader
never fed, T39's invalidation no test invoked, T51's compatibility that WAS pinned and is why it
is a no-op). A planner is not an apply path.

⚠️ Uses a THROWAWAY database — the fixture refuses the dev ports. These tests CREATE, RE-KEY and
DELETE nodes.
"""
from __future__ import annotations

import uuid

import pytest

from app.db.migrations.recanon_honorifics import run_recanon_backfill

pytestmark = pytest.mark.asyncio

# The live shape, exactly: a name whose stored canonical was produced by an older
# canonicaliser (partial simplified/traditional conversion). 1826 nodes look like this.
_NAME = "規則之力"
_STALE_CN = "规則之力"          # what the OLD canonicaliser produced
_KIND = "concept"


async def _seed(session, *, uid, pid, eid, name=_NAME, cn=_STALE_CN, anchor=None):
    await session.run(
        "CREATE (e:Entity {id:$id, user_id:$u, project_id:$p, name:$n, canonical_name:$cn, "
        "kind:$k, canonical_version:1, source_types:['chapter'], confidence:0.9, "
        "glossary_entity_id:$a, created_at:datetime(), updated_at:datetime()})",
        id=eid, u=uid, p=pid, n=name, cn=cn, k=_KIND, a=anchor)


async def test_the_APPLY_path_repairs_a_stale_canonical_name(neo4j_driver):
    """The 1819-node case. After apply, the node must resolve by its CURRENT name — which is
    the whole point: today it forks, because neither the stale canonical_name nor the stale
    derived id matches what `merge_entity` computes."""
    uid, pid = f"u-{uuid.uuid4().hex[:10]}", f"p-{uuid.uuid4().hex[:10]}"
    eid = f"stale-{uuid.uuid4().hex[:10]}"
    async with neo4j_driver.session() as s:
        await _seed(s, uid=uid, pid=pid, eid=eid)
        plan = await run_recanon_backfill(s, apply=True)
        assert plan.rekeyed >= 1, plan

        r = await s.run(
            "MATCH (e:Entity {user_id:$u, project_id:$p}) "
            "RETURN count(e) AS c, collect(e.canonical_name)[0] AS cn", u=uid, p=pid)
        rec = await r.single()
        assert rec["c"] == 1, f"the repair duplicated the node instead of re-keying it: {rec}"

        from loreweave_extraction.canonical import canonicalize_entity_name
        assert rec["cn"] == canonicalize_entity_name(_NAME), (
            f"canonical_name is still stale after apply: {rec['cn']!r} — the node keeps forking")

        await s.run("MATCH (e:Entity {user_id:$u}) DETACH DELETE e", u=uid)


async def test_a_RE_KEY_does_not_orphan_an_EntityStatus_that_points_at_the_old_id(neo4j_driver):
    """🔴 The risk the apply path does not check, pinned before an operator runs it.

    `:EntityStatus` carries `entity_id` as a PROPERTY — 35 rows do on the dev graph — and the
    re-key changes `Entity.id`. Nothing in the migration re-points them. Measured 2026-08-14,
    **0 of the 33 resolvable status rows sit on an entity the backfill would re-key**, so the
    real run is safe *by luck, not by design*. This rule states the coupling so the luck is
    visible: if it ever goes red, a status row has been stranded from the entity it describes
    and a canon read would report that character as never having died.
    """
    uid, pid = f"u-{uuid.uuid4().hex[:10]}", f"p-{uuid.uuid4().hex[:10]}"
    eid = f"stale-{uuid.uuid4().hex[:10]}"
    async with neo4j_driver.session() as s:
        await _seed(s, uid=uid, pid=pid, eid=eid)
        await s.run(
            "CREATE (:EntityStatus {user_id:$u, project_id:$p, entity_id:$e, status:'gone', "
            "from_order:1000000, evidence_count:2})", u=uid, p=pid, e=eid)

        await run_recanon_backfill(s, apply=True)

        r = await s.run(
            "MATCH (st:EntityStatus {user_id:$u}) "
            "OPTIONAL MATCH (e:Entity {id: st.entity_id}) "
            "RETURN count(st) AS statuses, count(e) AS resolved", u=uid)
        rec = await r.single()
        assert rec["statuses"] == 1, "the fixture's status row vanished"
        assert rec["resolved"] == 1, (
            "the re-key STRANDED an :EntityStatus row — its entity_id still points at the old "
            "id, so the status describes an entity that no longer exists at that key. A canon "
            "read would report the character as never having died.")

        await s.run("MATCH (n {user_id:$u}) DETACH DELETE n", u=uid)


async def test_the_MERGE_path_preserves_a_relation_PREDICATE(neo4j_driver):
    """🔴 The merge branch re-creates edges with a bare `MERGE (new)-[:RELATES_TO]->(o)` — no
    properties carried. A relation's PREDICATE is its meaning: "betrayed" and "guards" are the
    same edge type and different facts. If the re-point drops it, the merge silently converts
    every relation on the folded node into a typeless link.

    Only ONE merge survives the anchor guard on the real graph, so this affects one node — but
    an operator running `--apply` deserves to know whether that node's edges keep their meaning.
    """
    uid, pid = f"u-{uuid.uuid4().hex[:10]}", f"p-{uuid.uuid4().hex[:10]}"
    survivor, stranded, other = (f"{k}-{uuid.uuid4().hex[:8]}" for k in ("surv", "strand", "oth"))
    async with neo4j_driver.session() as s:
        # ⚠️ `:Entity(user_id, project_id, glossary_entity_id)` is UNIQUE, so two nodes CANNOT
        # share an anchor — the first fixture tried and Neo4j refused it. That is worth
        # recording: the "two stale spellings of one glossary entity" case the planner's merge
        # branch handles can only arise when at least one side is UNANCHORED, which is exactly
        # what the one surviving merge on the real graph looks like.
        await _seed(s, uid=uid, pid=pid, eid=survivor, name="精靈大人", cn="精靈大人", anchor="gl-A")
        await _seed(s, uid=uid, pid=pid, eid=stranded, name="精靈小姐", cn="精靈小姐", anchor=None)
        await _seed(s, uid=uid, pid=pid, eid=other, name="Kai", cn="kai", anchor="gl-B")
        await s.run(
            "MATCH (a:Entity {id:$s}),(b:Entity {id:$o}) "
            "CREATE (a)-[:RELATES_TO {id:'r1', predicate:'betrayed', confidence:0.9, "
            "user_id:$u}]->(b)", s=stranded, o=other, u=uid)

        plan = await run_recanon_backfill(s, apply=True)

        r = await s.run(
            "MATCH ()-[rel:RELATES_TO]->() WHERE rel.user_id = $u OR rel.predicate IS NOT NULL "
            "RETURN count(rel) AS edges, collect(rel.predicate)[0] AS pred", u=uid)
        rec = await r.single()
        await s.run("MATCH (n {user_id:$u}) DETACH DELETE n", u=uid)
        assert rec["edges"] >= 1, f"the merge destroyed the relation entirely: {plan!r}"
        assert rec["pred"] == "betrayed", (
            f"the merge re-created the edge WITHOUT its predicate (got {rec['pred']!r}). "
            "A relation's predicate is its meaning — 'betrayed' and 'guards' are the same edge "
            "type and different facts.")
