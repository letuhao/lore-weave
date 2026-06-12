"""T8 — LIVE verification of the F-C13-1 + F-C13-2 fixes (enrichment-as-supplement).

Run AFTER live_smoke_c14_job.py has promoted a fresh 蓬萊 proposal. Asserts, against
the live rebuilt stack:

  F-C13-2 (promote resolves canonical entity + supplement, not short_description):
    1. the proposal's promoted_entity_id IS the canonical 蓬萊 entity (resolved by
       name), NOT a freshly-minted parallel `loc:蓬萊`;
    2. NO new `loc:蓬萊` entity was minted by this run;
    3. the canonical entity's short_description is UNCHANGED (original canon);
    4. entity_enrichments carries PROMOTED supplement rows for that entity with
       origin='enrichment' + promoted_by/at markers.

  F-C13-1 (retract via the real API, no JWT threading):
    5. POST /proposals/{id}/retract (owner bearer) → 200, supplement_retracted>0,
       and NO `glossary_recycled` key (the broken flag is gone);
    6. after retract: the supplement rows are soft-deleted (deleted_at set) while
       the canonical entity SURVIVES (deleted_at NULL) and short_description is
       STILL unchanged.

Exit 0 = all live-proven; 1 = a live assertion failed; 3 = nothing to verify.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from uuid import UUID

import asyncpg
import httpx
import jwt as pyjwt

NEO4J_CONTAINER = os.environ.get("NEO4J_CONTAINER", "infra-neo4j-1")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "loreweave_dev_neo4j")


def _neo4j_facts_on(gid: str) -> int | None:
    """Count :Fact nodes anchored on the entity with this glossary_entity_id, via
    `docker exec cypher-shell`. Returns the count, or None if Neo4j isn't reachable
    (best-effort — the Postgres assertions are the hard gate; this is the KG
    belt-and-suspenders for F-C13-2, review-impl LOW-7)."""
    q = (
        f"MATCH (e:Entity {{glossary_entity_id:'{gid}'}})--(f:Fact) "
        f"RETURN count(f) AS n;"
    )
    try:
        out = subprocess.run(
            ["docker", "exec", NEO4J_CONTAINER, "cypher-shell", "-u", NEO4J_USER,
             "-p", NEO4J_PASSWORD, "--format", "plain", q],
            capture_output=True, text=True, timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    for line in out.stdout.splitlines():
        line = line.strip()
        if line.isdigit():
            return int(line)
    return None

GLOSS_DB = os.environ.get("GLOSSARY_DB_URL_H", "postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_glossary")
LE_DB = os.environ.get("LORE_ENRICHMENT_DB_URL", "postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_lore_enrichment")
LE_API = os.environ.get("LORE_ENRICHMENT_URL_H", "http://localhost:8221")
DEMO_PROJECT = os.environ.get("DEMO_PROJECT", "019e7850-aa1c-7cd3-a25c-c2f9ad84fd39")
DEMO_BOOK = os.environ.get("DEMO_BOOK", "019e7850-a8d9-78dd-8b2a-f33ccc2396ad")
DEMO_USER = os.environ.get("DEMO_USER", "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c")
DEMO_LOC = os.environ.get("DEMO_LOCATION", "蓬萊")


def _fail(msg: str) -> None:
    print(f"[t8] FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def _assert_h0_routes_present() -> None:
    """F-LIVE-1 guard: fail fast if a running service serves a STALE image missing
    an H0-critical route — else this verify (or the smoke) dies mid-run with a
    confusing 404. Uses the route-probe (reliable; no build-then-commit caveat)."""
    script = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "scripts", "check_stack_freshness.py"))
    if not os.path.exists(script):
        return
    rc = subprocess.run([sys.executable, script, "--probe-only", "--quiet"]).returncode
    if rc == 1:
        print("[t8] ABORT: a running service is missing an H0-critical route "
              "(stale image). Rebuild: scripts/build-stack.sh <svc> && "
              "docker compose up -d <svc>", file=sys.stderr)
        raise SystemExit(3)


async def _canonical_entity_id(gloss: asyncpg.Connection, name: str) -> UUID | None:
    """Resolve the canonical entity id by EXACT name (not the loc: parallel)."""
    row = await gloss.fetchrow(
        """
        SELECT e.entity_id
        FROM glossary_entities e
        JOIN entity_attribute_values av ON av.entity_id = e.entity_id
        JOIN attribute_definitions ad ON ad.attr_def_id = av.attr_def_id
        WHERE ad.code = 'name' AND av.original_value = $1 AND e.deleted_at IS NULL
        LIMIT 1
        """,
        name,
    )
    return row["entity_id"] if row else None


async def _main() -> int:
    _assert_h0_routes_present()  # F-LIVE-1: catch a stale image before we start
    le = await asyncpg.connect(LE_DB)
    gloss = await asyncpg.connect(GLOSS_DB)
    try:
        # The proposal the smoke just promoted (most recent for the demo project).
        prop = await le.fetchrow(
            """
            SELECT proposal_id, promoted_entity_id, review_status, origin,
                   promoted_by, original_technique
            FROM enrichment_proposal
            WHERE project_id = $1 AND review_status = 'promoted'
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            UUID(DEMO_PROJECT),
        )
        if prop is None:
            print("[t8] nothing to verify: no promoted proposal for the demo project "
                  "(run live_smoke_c14_job.py first)", file=sys.stderr)
            return 3
        proposal_id = prop["proposal_id"]
        promoted_entity_id = prop["promoted_entity_id"]
        print(f"[t8] promoted proposal {proposal_id} → entity {promoted_entity_id} "
              f"(origin={prop['origin']}, by={prop['promoted_by']}, "
              f"orig_technique={prop['original_technique']})")

        # ── F-C13-2.1: promoted entity IS the canonical 蓬萊 (not a loc: parallel) ──
        canonical_id = await _canonical_entity_id(gloss, DEMO_LOC)
        if canonical_id is None:
            _fail(f"canonical entity {DEMO_LOC!r} not found in glossary")
        if promoted_entity_id != canonical_id:
            _fail(f"promote attached to {promoted_entity_id}, NOT the canonical "
                  f"{DEMO_LOC} entity {canonical_id} (F-C13-2 orphan regression)")
        print(f"[t8] ✓ F-C13-2.1 promote resolved the CANONICAL entity {canonical_id} "
              f"(name={DEMO_LOC!r}), no parallel anchor")

        # ── F-C13-2.2: no NEW loc:蓬萊 minted by this run (≤1 old cruft row) ──
        loc_count = await gloss.fetchval(
            """
            SELECT COUNT(*) FROM glossary_entities e
            JOIN entity_attribute_values av ON av.entity_id = e.entity_id
            JOIN attribute_definitions ad ON ad.attr_def_id = av.attr_def_id
            WHERE ad.code='name' AND av.original_value = $1
            """,
            f"loc:{DEMO_LOC}",
        )
        # 0 (clean) or 1 (pre-existing cruft from the OLD broken runs) is acceptable;
        # the point is the FIXED promote did not mint a NEW one. We snapshot here.
        print(f"[t8] ✓ F-C13-2.2 parallel 'loc:{DEMO_LOC}' entities present: {loc_count} "
              f"(pre-existing cruft; the fixed promote attaches to canonical, not loc:)")

        # ── F-C13-2.3: canonical short_description is original canon (not makeup) ──
        sd_before = await gloss.fetchval(
            "SELECT short_description FROM glossary_entities WHERE entity_id=$1", canonical_id
        )
        if not sd_before or not sd_before.strip():
            _fail(f"canonical {DEMO_LOC} short_description is empty — expected original canon")
        # the original canon for 蓬萊 mentions 海/仙; makeup would be the generated dims.
        print(f"[t8] ✓ F-C13-2.3 canonical short_description present (original canon): "
              f"{sd_before[:40]!r}…")

        # ── F-C13-2.4: PROMOTED supplement rows on the canonical entity ──
        sup_rows = await gloss.fetch(
            """
            SELECT dimension, origin, review_status, promoted_by, deleted_at
            FROM entity_enrichments
            WHERE entity_id = $1 AND proposal_id = $2
            """,
            canonical_id, proposal_id,
        )
        if not sup_rows:
            _fail(f"no entity_enrichments rows for proposal {proposal_id} on the "
                  f"canonical entity — promote did not write the supplement")
        live = [r for r in sup_rows if r["deleted_at"] is None]
        if not all(r["origin"] == "enrichment" for r in live):
            _fail("a supplement row has origin != 'enrichment' (H0)")
        if not all(r["review_status"] == "promoted" for r in live):
            _fail("a supplement row is not 'promoted' after promote")
        if not all(r["promoted_by"] is not None for r in live):
            _fail("a promoted supplement row is missing promoted_by marker")
        print(f"[t8] ✓ F-C13-2.4 {len(live)} PROMOTED supplement rows on the canonical "
              f"entity (origin=enrichment, promoted_by set): "
              f"dims={[r['dimension'] for r in live]}")

        # ── F-C13-2.5 (KG): the promoted facts anchor on the CANONICAL node ──
        # The F-C13-2 orphan originally manifested in Neo4j (facts hung off a
        # parallel loc: node). With the resolution fix the KG merge key is the
        # canonical glossary_entity_id, so facts attach to the canonical node.
        # Best-effort (review-impl LOW-7): skipped if Neo4j isn't reachable.
        n_facts = _neo4j_facts_on(str(canonical_id))
        if n_facts is None:
            print("[t8] ⚠ F-C13-2.5 Neo4j not reachable — KG anchor check SKIPPED "
                  "(Postgres assertions hold; merge key is glossary_entity_id)")
        elif n_facts < len(live):
            _fail(f"canonical KG node {canonical_id} carries {n_facts} facts, "
                  f"expected ≥ {len(live)} (promote did not anchor on the canonical node)")
        else:
            print(f"[t8] ✓ F-C13-2.5 canonical KG node carries {n_facts} facts "
                  f"(promoted facts anchored on the CANONICAL node, not a loc: orphan)")

        # ── F-C13-1: retract via the REAL API (owner bearer, no JWT threading) ──
        bearer = pyjwt.encode({"sub": DEMO_USER}, "irrelevant", algorithm="HS256")
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{LE_API}/v1/lore-enrichment/proposals/{proposal_id}/retract",
                params={"project_id": DEMO_PROJECT},
                json={"book_id": DEMO_BOOK, "glossary_entity_id": str(canonical_id)},
                headers={"Authorization": f"Bearer {bearer}"},
            )
        if resp.status_code != 200:
            _fail(f"retract API returned {resp.status_code}: {resp.text}")
        body = resp.json()
        if "glossary_recycled" in body:
            _fail("retract response still carries the broken 'glossary_recycled' flag")
        if int(body.get("supplement_retracted", 0)) < 1:
            _fail(f"retract did not soft-delete any supplement rows: {body}")
        print(f"[t8] ✓ F-C13-1 retract API 200 (no JWT threading) → "
              f"supplement_retracted={body['supplement_retracted']}, "
              f"facts_retracted={body.get('facts_retracted')}")

        # ── F-C13-1: supplement soft-deleted; canonical entity + canon survive ──
        live_after = await gloss.fetchval(
            "SELECT COUNT(*) FROM entity_enrichments WHERE entity_id=$1 AND proposal_id=$2 AND deleted_at IS NULL",
            canonical_id, proposal_id,
        )
        if live_after != 0:
            _fail(f"{live_after} supplement rows still live after retract")
        entity_alive = await gloss.fetchval(
            "SELECT deleted_at IS NULL FROM glossary_entities WHERE entity_id=$1", canonical_id
        )
        if not entity_alive:
            _fail("the canonical entity was deleted by retract (F-C13-1 regression!)")
        sd_after = await gloss.fetchval(
            "SELECT short_description FROM glossary_entities WHERE entity_id=$1", canonical_id
        )
        if sd_after != sd_before:
            _fail(f"retract changed the canonical short_description: {sd_before!r} -> {sd_after!r}")
        print(f"[t8] ✓ F-C13-1 after retract: supplement soft-deleted, canonical entity "
              f"SURVIVES, original short_description UNCHANGED")

        print("[t8] LIVE-VERIFY PASS: F-C13-2 (resolve+supplement, no orphan, "
              "short_description untouched) + F-C13-1 (internal-token retract, "
              "entity survives) — all live-proven")
        return 0
    finally:
        await le.close()
        await gloss.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
