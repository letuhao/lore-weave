#!/usr/bin/env python3
"""Seed the 封神演义 (Fengshen Yanyi) lore-enrichment demo data into the RUNNING stack.

Goal (BOUNDED — no LLM extraction):
  The 4 locked demo LOCATIONS exist as UNDER-DESCRIBED `location` entities in
  glossary-service AND propagate to the Neo4j KG (for a test knowledge project),
  so the enrichment demo (C13/C14) can detect them as gaps.

What it seeds (idempotent — safe to re-run):
  1. A Fengshen *book* in book-service for the test account (found-or-created by
     title). A handful of representative chapters (the 回 that introduce each of
     the 4 places) are created to back provenance / chapter_links — NOT the whole
     100-回 corpus (that would trigger the per-chapter LLM extraction pipeline).
  2. A *knowledge_project* row (knowledge-service Postgres) linking that book, so
     the C4 `glossary.entity_updated` consumer can resolve user_id/project_id via
     book_id and sync glossary writes to Neo4j.
  3. The 4 demo *location* entities + a handful of related canon entities, written
     via the glossary internal bulk `extract-entities` API with ONLY their sparse
     canon-level descriptions (under-described on purpose — the missing
     历史/地理/文化 dimensions are the gaps the demo fills). source_type = authored
     glossary canon. These writes emit `glossary.entity_updated` outbox events
     which the worker-infra outbox-relay ships to Redis and the knowledge-service
     consumer syncs to Neo4j.
  4. Waits for the relay (30s poll) + consumer, then VERIFIES the Neo4j nodes
     exist for the (user_id, project_id) pair via cypher-shell.

DATA SEEDING ONLY — does not modify any service source. Reaches Postgres / Neo4j
through `docker exec` (host has docker access); reaches the HTTP APIs directly.

Method: DIRECT entity seeding (no LLM extraction) + automatic C4 outbox→Neo4j
propagation.

Run:  python scripts/seed_fengshen_demo.py
Env overrides (all have working defaults for the current infra stack):
  AUTH_URL=http://localhost:8204  BOOK_URL=http://localhost:8205
  GLOSSARY_URL=http://localhost:8211  KNOWLEDGE_URL=http://localhost:8216
  INTERNAL_SERVICE_TOKEN=dev_internal_token
  TEST_EMAIL=claude-test@loreweave.dev  TEST_PASSWORD=Claude@Test2026
  PG_CONTAINER=infra-postgres-1  PG_USER=loreweave
  NEO4J_CONTAINER=infra-neo4j-1  NEO4J_USER=neo4j  NEO4J_PASSWORD=loreweave_dev_neo4j
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import requests

# ── Config ──────────────────────────────────────────────────────────────────
AUTH_URL = os.environ.get("AUTH_URL", "http://localhost:8204").rstrip("/")
BOOK_URL = os.environ.get("BOOK_URL", "http://localhost:8205").rstrip("/")
GLOSSARY_URL = os.environ.get("GLOSSARY_URL", "http://localhost:8211").rstrip("/")
KNOWLEDGE_URL = os.environ.get("KNOWLEDGE_URL", "http://localhost:8216").rstrip("/")
INTERNAL_TOKEN = os.environ.get("INTERNAL_SERVICE_TOKEN", "dev_internal_token")

TEST_EMAIL = os.environ.get("TEST_EMAIL", "claude-test@loreweave.dev")
TEST_PASSWORD = os.environ.get("TEST_PASSWORD", "Claude@Test2026")

PG_CONTAINER = os.environ.get("PG_CONTAINER", "infra-postgres-1")
PG_USER = os.environ.get("PG_USER", "loreweave")
KNOWLEDGE_DB = os.environ.get("KNOWLEDGE_DB", "loreweave_knowledge")

NEO4J_CONTAINER = os.environ.get("NEO4J_CONTAINER", "infra-neo4j-1")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "loreweave_dev_neo4j")

BOOK_TITLE = "封神演義 (Fengshen Yanyi) — Lore Enrichment Demo"
PROJECT_NAME = "封神演義 Lore Enrichment Demo"
ORIG_LANG = "zh"

# ── Demo data ───────────────────────────────────────────────────────────────
# The 4 locked demo LOCATIONS, each with ONLY its sparse canon-level mention.
# UNDER-DESCRIBED on purpose: canon names the place but gives no 历史/地理/文化
# depth — those missing dimensions are exactly the gaps the enrichment demo fills.
# `chapter_key` ties each to the 回 that first introduces it (provenance).
DEMO_LOCATIONS = [
    {
        "name": "玉虛宮",
        "aliases": ["玉虚宫"],
        "type": "仙宮 (immortal palace)",
        # sparse canon mention, 第9回
        "description": "崑崙山玉虛宮，掌闡道法、宣揚正教的聖人元始天尊講道之所。",
        "evidence": "崑崙山玉虛宮掌闡道法宣揚正教聖人元始天尊閉了講筵",
        "chapter_key": "第9回",
    },
    {
        "name": "碧遊宮/金鰲島",
        "aliases": ["碧遊宮", "金鰲島", "碧游宫", "金鳌岛"],
        "type": "仙宮 / 仙島 (immortal palace / isle)",
        # sparse canon mention, 第35回 (碧遊宮) + 第43回 (金鰲島)
        "description": "碧遊宮乃截教通天教主道場；金鰲島為截教群仙聚會之所。",
        "evidence": "太師乃碧遊宮金靈聖母門下；五行大道 ／ 金鰲島內邀仙友",
        "chapter_key": "第35回",
    },
    {
        "name": "蓬萊",
        "aliases": ["蓬萊海島", "蓬莱"],
        "type": "海外仙島 (overseas immortal isle)",
        # sparse canon mention, 第3回
        "description": "蓬萊海島，海外仙家之地，僅於斬蛟龍一語中略見其名。",
        "evidence": "蓬萊海島斬蛟龍；那一個萬仞山前誅猛虎",
        "chapter_key": "第3回",
    },
    {
        "name": "陳塘關",
        "aliases": ["陈塘关"],
        "type": "邊關 (frontier garrison)",
        # sparse canon mention, 第12回
        "description": "陳塘關，總兵官李靖鎮守之邊關；哪吒出世之地。",
        "evidence": "話說陳塘關有一總兵官，姓李，名靖，自幼訪道修真",
        "chapter_key": "第12回",
    },
]

# A handful of related canon entities for contradiction-check + neighborhood
# context (characters/organizations). Minimal sparse fields only.
RELATED_ENTITIES = [
    {"kind": "character", "name": "姜子牙", "aliases": ["姜尚", "子牙", "呂尚"],
     "description": "闡教門下，出世輔周伐紂、主持封神之人中仙。", "chapter_key": "第9回"},
    {"kind": "character", "name": "元始天尊", "aliases": ["元始"],
     "description": "闡教教主，居崑崙山玉虛宮。", "chapter_key": "第9回"},
    {"kind": "character", "name": "通天教主", "aliases": ["通天"],
     "description": "截教教主，居碧遊宮。", "chapter_key": "第35回"},
    {"kind": "organization", "name": "闡教", "aliases": ["阐教"],
     "description": "元始天尊所領玄門正教，道場在崑崙山玉虛宮。", "chapter_key": "第9回"},
    {"kind": "organization", "name": "截教", "aliases": ["截教门"],
     "description": "通天教主所領之教，道場在碧遊宮、金鰲島。", "chapter_key": "第35回"},
    {"kind": "location", "name": "昆侖山", "aliases": ["崑崙山", "昆仑山"],
     "type": "仙山 (immortal mountain)",
     "description": "闡教祖庭所在之仙山，玉虛宮坐落其上。", "chapter_key": "第9回"},
]

# Representative chapters to create (to back provenance). Keyed by the 回 that
# introduces each demo place. body is a short canon excerpt — enough provenance,
# not the full 回 (full text would invite the per-chapter extraction pipeline).
DEMO_CHAPTERS = [
    {"key": "第3回", "sort_order": 3, "title": "第3回",
     "body": "（節錄）蓬萊海島斬蛟龍；那一個萬仞山前誅猛虎。— demo excerpt for provenance"},
    {"key": "第9回", "sort_order": 9, "title": "第9回",
     "body": "（節錄）崑崙山玉虛宮，掌闡道法、宣揚正教聖人元始天尊閉了講筵。— demo excerpt for provenance"},
    {"key": "第12回", "sort_order": 12, "title": "第12回",
     "body": "（節錄）話說陳塘關有一總兵官，姓李，名靖，自幼訪道修真，拜西崑崙度厄真人為師。— demo excerpt for provenance"},
    {"key": "第35回", "sort_order": 35, "title": "第35回",
     "body": "（節錄）太師乃碧遊宮金靈聖母門下；五行大道，倒海移山。— demo excerpt for provenance"},
    {"key": "第43回", "sort_order": 43, "title": "第43回",
     "body": "（節錄）金鰲島內邀仙友，「封神榜」上早標名。— demo excerpt for provenance"},
]


# ── helpers ─────────────────────────────────────────────────────────────────
def log(msg: str) -> None:
    print(f"[seed] {msg}", file=sys.stderr, flush=True)


def fail(reason: str, what_landed: str = "", result: str = "FAILED") -> None:
    print(json.dumps({"result": result, "reason": reason,
                       "what_landed": what_landed}, ensure_ascii=False))
    sys.exit(1)


def psql(db: str, sql: str) -> str:
    """Run a SQL statement in a service DB via docker exec, return tab/A output.

    psql prints command-status tags (e.g. ``INSERT 0 1``) to stdout alongside
    RETURNING data; strip those so a RETURNING value comes back clean.
    """
    cp = subprocess.run(
        ["docker", "exec", PG_CONTAINER, "psql", "-U", PG_USER, "-d", db,
         "-tAc", sql],
        capture_output=True, text=True, encoding="utf-8",
    )
    if cp.returncode != 0:
        raise RuntimeError(f"psql failed ({db}): {cp.stderr.strip()}")
    lines = [ln for ln in cp.stdout.strip().splitlines()
             if not _PSQL_STATUS_RE.match(ln.strip())]
    return "\n".join(lines).strip()


import re  # noqa: E402

_PSQL_STATUS_RE = re.compile(
    r"^(INSERT|UPDATE|DELETE|SELECT|MERGE|COPY|BEGIN|COMMIT|ROLLBACK)\b.*$"
)


def cypher(query: str) -> str:
    cp = subprocess.run(
        ["docker", "exec", NEO4J_CONTAINER, "cypher-shell",
         "-u", NEO4J_USER, "-p", NEO4J_PASSWORD, "--format", "plain", query],
        capture_output=True, text=True, encoding="utf-8",
    )
    if cp.returncode != 0:
        raise RuntimeError(f"cypher-shell failed: {cp.stderr.strip()}")
    # strip JVM warnings on stderr; stdout is the data
    return cp.stdout.strip()


def login() -> tuple[str, str]:
    r = requests.post(f"{AUTH_URL}/v1/auth/login",
                      json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
                      timeout=15)
    r.raise_for_status()
    body = r.json()
    return body["access_token"], body["user_profile"]["user_id"]


def find_or_create_book(jwt: str) -> str:
    h = {"Authorization": f"Bearer {jwt}"}
    # find by exact title among active books
    r = requests.get(f"{BOOK_URL}/v1/books?limit=200", headers=h, timeout=15)
    r.raise_for_status()
    payload = r.json()
    items = payload.get("books") or payload.get("items") or payload
    if isinstance(items, dict):
        items = items.get("books", [])
    for b in items:
        if b.get("title") == BOOK_TITLE:
            bid = b.get("book_id") or b.get("id")
            log(f"book exists: {bid}")
            return bid
    # create
    r = requests.post(f"{BOOK_URL}/v1/books", headers=h, timeout=15, json={
        "title": BOOK_TITLE,
        "description": "Investiture of the Gods — demo corpus for lore-enrichment gap detection.",
        "original_language": ORIG_LANG,
        "summary": "100回 Ming-dynasty shenmo novel; 4 under-described demo locations seeded.",
        "genre_tags": ["fantasy", "historical"],
    })
    r.raise_for_status()
    bid = r.json().get("book_id") or r.json().get("id")
    log(f"book created: {bid}")
    return bid


def find_or_create_chapters(jwt: str, book_id: str) -> dict[str, str]:
    """Create the representative chapters; return {chapter_key: chapter_id}."""
    h = {"Authorization": f"Bearer {jwt}"}
    # list existing chapters
    existing: dict[str, str] = {}
    r = requests.get(f"{BOOK_URL}/v1/books/{book_id}/chapters?limit=200",
                     headers=h, timeout=15)
    if r.status_code == 200:
        payload = r.json()
        chs = payload.get("chapters") or payload.get("items") or []
        for c in chs:
            title = c.get("title")
            cid = c.get("chapter_id") or c.get("id")
            if title and cid:
                existing[title] = cid

    out: dict[str, str] = {}
    for ch in DEMO_CHAPTERS:
        if ch["title"] in existing:
            out[ch["key"]] = existing[ch["title"]]
            continue
        rr = requests.post(
            f"{BOOK_URL}/v1/books/{book_id}/chapters",
            headers={**h, "Content-Type": "application/json"}, timeout=20,
            json={"title": ch["title"], "original_language": ORIG_LANG,
                  "sort_order": ch["sort_order"], "body": ch["body"]},
        )
        if rr.status_code not in (200, 201):
            log(f"WARN: chapter {ch['key']} create -> {rr.status_code} {rr.text[:200]}")
            continue
        body = rr.json()
        cid = body.get("chapter_id") or body.get("id")
        if cid:
            out[ch["key"]] = cid
    log(f"chapters ready: {len(out)}/{len(DEMO_CHAPTERS)}")
    return out


def ensure_knowledge_project(user_id: str, book_id: str) -> str:
    """Find-or-create a knowledge_projects row linking book_id. Returns project_id.

    Direct DB write (bounded seeding path). The C4 glossary.entity_updated
    handler resolves user_id/project_id from this row via book_id, then syncs
    to Neo4j.
    """
    pid = psql(KNOWLEDGE_DB,
               f"SELECT project_id FROM knowledge_projects "
               f"WHERE book_id = '{book_id}' AND user_id = '{user_id}' LIMIT 1;")
    if pid:
        log(f"knowledge project exists: {pid}")
        return pid
    name = PROJECT_NAME.replace("'", "''")
    pid = psql(KNOWLEDGE_DB,
               "INSERT INTO knowledge_projects "
               "(user_id, name, description, project_type, book_id, "
               " extraction_enabled, extraction_status) "
               f"VALUES ('{user_id}', '{name}', 'lore-enrichment demo', 'book', "
               f"'{book_id}', false, 'disabled') RETURNING project_id;")
    log(f"knowledge project created: {pid}")
    return pid


def bulk_upsert_entities(book_id: str, chapters: dict[str, str]) -> dict:
    """Write the 4 locations + related canon via glossary internal bulk API.

    Emits glossary.entity_updated outbox events → relay → Neo4j (C4 pipeline).
    Idempotent: the API dedups by normalized name/alias and merges.
    """
    h = {"X-Internal-Token": INTERNAL_TOKEN, "Content-Type": "application/json"}

    entities = []

    def chapter_links(key: str):
        cid = chapters.get(key)
        if not cid:
            return []
        ch = next((c for c in DEMO_CHAPTERS if c["key"] == key), None)
        return [{"chapter_id": cid, "chapter_title": key,
                 "chapter_index": ch["sort_order"] if ch else 0,
                 "relevance": "appears"}]

    for loc in DEMO_LOCATIONS:
        entities.append({
            "kind_code": "location",
            "name": loc["name"],
            "attributes": {
                "aliases": loc["aliases"],
                "type": loc["type"],
                # ONLY a sparse description — significance/atmosphere left EMPTY
                # so the demo can detect the missing 历史/地理/文化 dimensions.
                "description": loc["description"],
            },
            "evidence": loc["evidence"],
            "chapter_links": chapter_links(loc["chapter_key"]),
        })

    for ent in RELATED_ENTITIES:
        attrs = {"aliases": ent["aliases"], "description": ent["description"]}
        if "type" in ent:
            attrs["type"] = ent["type"]
        entities.append({
            "kind_code": ent["kind"],
            "name": ent["name"],
            "attributes": attrs,
            "evidence": ent["description"],
            "chapter_links": chapter_links(ent["chapter_key"]),
        })

    # attribute_actions: on MERGE of an existing entity, fill empty attrs (never
    # overwrite a user/demo edit). On first create all attrs are written anyway.
    fill = {"aliases": "fill", "type": "fill", "description": "fill"}
    req = {
        "source_language": ORIG_LANG,
        "attribute_actions": {
            "location": fill,
            "character": {"aliases": "fill", "description": "fill"},
            "organization": {"aliases": "fill", "description": "fill"},
        },
        "entities": entities,
    }
    r = requests.post(f"{GLOSSARY_URL}/internal/books/{book_id}/extract-entities",
                      headers=h, json=req, timeout=60)
    r.raise_for_status()
    res = r.json()
    log(f"bulk upsert: created={res.get('created')} updated={res.get('updated')} "
        f"skipped={res.get('skipped')}")
    return res


def backfill_outbox_events(book_id: str) -> int:
    """Backfill glossary.entity_updated outbox rows for the seeded entities.

    The bulk extract-entities handler is SUPPOSED to emit one
    `glossary.entity_updated` outbox row per written entity (C4/K14). If the
    deployed glossary binary predates that code path, no events are emitted and
    nothing reaches Neo4j. This step makes the seed robust against a stale
    binary: for each seeded entity that has NO outbox event yet, it inserts the
    exact C4 payload the current code would emit. The live worker-infra relay +
    knowledge-service consumer + glossary_sync then propagate to Neo4j through
    the real pipeline — we only substitute the one emit step.

    Idempotent: skips entities that already have a glossary.entity_updated row
    (whether the binary emitted it or a prior seed run backfilled it). Returns
    the number of rows inserted this run.
    """
    # Pull seeded entities (id, kind code, cached_name, cached_aliases,
    # short_description) for this book.
    rows = psql(
        "loreweave_glossary",
        "SELECT e.entity_id::text, k.code, COALESCE(e.cached_name,''), "
        "       COALESCE(e.short_description,'') "
        "FROM glossary_entities e JOIN entity_kinds k ON k.kind_id=e.kind_id "
        f"WHERE e.book_id='{book_id}' AND e.deleted_at IS NULL "
        "  AND e.cached_name IS NOT NULL AND e.cached_name <> '';",
    )
    inserted = 0
    for line in rows.splitlines():
        parts = line.split("|")
        if len(parts) < 3:
            continue
        eid, kind, name = parts[0], parts[1], parts[2]
        short = parts[3] if len(parts) > 3 else ""
        # already has an event?
        has = psql(
            "loreweave_glossary",
            "SELECT COUNT(*) FROM outbox_events "
            f"WHERE aggregate_id='{eid}' "
            "AND event_type='glossary.entity_updated';",
        )
        if has and int(has) > 0:
            continue
        payload = {
            "book_id": book_id,
            "glossary_entity_id": eid,
            "name": name,
            "kind": kind,
            "aliases": [],
            "short_description": short,
            "op": "created",
            "source_type": "glossary",
            "emitted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        payload_json = json.dumps(payload, ensure_ascii=False).replace("'", "''")
        psql(
            "loreweave_glossary",
            "INSERT INTO outbox_events "
            "(aggregate_type, aggregate_id, event_type, payload) "
            f"VALUES ('glossary', '{eid}', 'glossary.entity_updated', "
            f"'{payload_json}'::jsonb);",
        )
        inserted += 1
    if inserted:
        log(f"backfilled {inserted} glossary.entity_updated outbox rows "
            f"(deployed glossary binary did not emit them)")
    else:
        log("no outbox backfill needed (events already present)")
    return inserted


def seeded_entities(book_id: str) -> list[dict]:
    """Read back the seeded glossary entities (id, kind, name, short_desc)."""
    rows = psql(
        "loreweave_glossary",
        "SELECT e.entity_id::text, k.code, COALESCE(e.cached_name,''), "
        "       COALESCE(e.short_description,'') "
        "FROM glossary_entities e JOIN entity_kinds k ON k.kind_id=e.kind_id "
        f"WHERE e.book_id='{book_id}' AND e.deleted_at IS NULL "
        "  AND e.cached_name IS NOT NULL AND e.cached_name <> '' "
        "ORDER BY k.code, e.cached_name;",
    )
    out = []
    for line in rows.splitlines():
        parts = line.split("|")
        if len(parts) < 3:
            continue
        out.append({
            "entity_id": parts[0], "kind": parts[1], "name": parts[2],
            "short_description": parts[3] if len(parts) > 3 else "",
        })
    return out


def direct_glossary_sync(user_id: str, project_id: str, book_id: str) -> int:
    """Drive the K15.11 glossary_sync → Neo4j directly via the internal endpoint.

    The C4 event pipeline (glossary outbox → relay → Redis → knowledge-service
    consumer → glossary_sync) is the *primary* path and we backfill its outbox
    rows. But the deployed knowledge-service consumer can be wedged on a Redis
    read-timeout reconnect loop, leaving the graph un-converged. The task
    explicitly permits triggering glossary_sync directly. This calls
    `POST /internal/extraction/glossary-sync-entity` — a thin wrapper around the
    SAME `sync_glossary_entity_to_neo4j` (K15.11) the consumer invokes, so the
    resulting :Entity nodes are byte-identical to the event-driven path.
    Idempotent: the underlying MERGE keys on (user_id, glossary_entity_id).
    """
    h = {"X-Internal-Token": INTERNAL_TOKEN, "Content-Type": "application/json"}
    # Pull aliases per entity from glossary alias attribute (best-effort).
    alias_map = {}
    for loc in DEMO_LOCATIONS:
        alias_map[loc["name"]] = loc["aliases"]
    for ent in RELATED_ENTITIES:
        alias_map[ent["name"]] = ent["aliases"]
    synced = 0
    for ent in seeded_entities(book_id):
        body = {
            "user_id": user_id,
            "project_id": project_id,
            "glossary_entity_id": ent["entity_id"],
            "name": ent["name"],
            "kind": ent["kind"],
            "aliases": alias_map.get(ent["name"], []),
            "short_description": ent["short_description"] or None,
        }
        r = requests.post(
            f"{KNOWLEDGE_URL}/internal/extraction/glossary-sync-entity",
            headers=h, json=body, timeout=30)
        if r.status_code == 200:
            synced += 1
        else:
            log(f"WARN: direct sync {ent['name']} -> {r.status_code} {r.text[:160]}")
    log(f"direct glossary_sync -> Neo4j: {synced}/{len(seeded_entities(book_id))} entities")
    return synced


def glossary_location_count(book_id: str) -> int:
    return int(psql("loreweave_glossary",
                    "SELECT COUNT(*) FROM glossary_entities e "
                    "JOIN entity_kinds k ON k.kind_id = e.kind_id "
                    f"WHERE e.book_id = '{book_id}' AND e.deleted_at IS NULL "
                    "AND k.code = 'location';") or "0")


def neo4j_node_count(user_id: str, project_id: str) -> int:
    out = cypher(
        f"MATCH (e:Entity {{user_id: '{user_id}', project_id: '{project_id}'}}) "
        "RETURN count(e) AS c;")
    # plain format: header line 'c' then value
    for line in out.splitlines():
        line = line.strip().strip('"')
        if line.isdigit():
            return int(line)
    return 0


def neo4j_location_names(user_id: str, project_id: str) -> list[str]:
    out = cypher(
        f"MATCH (e:Entity {{user_id: '{user_id}', project_id: '{project_id}', "
        "kind: 'location'}) RETURN e.name AS name ORDER BY name;")
    names = []
    for line in out.splitlines():
        line = line.strip().strip('"')
        if line and line != "name":
            names.append(line)
    return names


# ── main ────────────────────────────────────────────────────────────────────
def main() -> None:
    try:
        jwt, user_id = login()
    except Exception as e:  # noqa: BLE001
        fail(f"login failed: {e}")
    log(f"user_id={user_id}")

    try:
        book_id = find_or_create_book(jwt)
    except Exception as e:  # noqa: BLE001
        fail(f"book create/find failed: {e}", result="FAILED")

    try:
        chapters = find_or_create_chapters(jwt, book_id)
    except Exception as e:  # noqa: BLE001
        log(f"WARN: chapter seeding error (non-fatal for entity seeding): {e}")
        chapters = {}

    try:
        project_id = ensure_knowledge_project(user_id, book_id)
    except Exception as e:  # noqa: BLE001
        fail(f"knowledge project ensure failed: {e}",
             what_landed=f"book {book_id} created", result="PARTIAL")

    try:
        bulk_res = bulk_upsert_entities(book_id, chapters)
    except Exception as e:  # noqa: BLE001
        fail(f"glossary bulk upsert failed: {e}",
             what_landed=f"book {book_id}, project {project_id}", result="PARTIAL")

    # C4 emit robustness: if the deployed glossary binary didn't emit the
    # outbox events (stale image), backfill them so the live relay+consumer
    # pipeline can still propagate the seed to Neo4j.
    try:
        backfill_outbox_events(book_id)
    except Exception as e:  # noqa: BLE001
        log(f"WARN: outbox backfill failed: {e}")

    try:
        gloss_count = glossary_location_count(book_id)
    except Exception as e:  # noqa: BLE001
        gloss_count = -1
        log(f"WARN: glossary count query failed: {e}")

    # Propagate to Neo4j. PRIMARY path is the C4 event pipeline (outbox→relay→
    # consumer→glossary_sync); we already backfilled its outbox rows. Give the
    # relay (30s poll) + consumer a window to converge, then fall back to the
    # task-sanctioned DIRECT glossary_sync if the graph is still empty (the
    # deployed consumer can be stuck on a Redis read-timeout loop).
    log("waiting for C4 outbox→relay→consumer→Neo4j propagation (relay polls 30s)...")
    neo_count = 0
    neo_locs: list[str] = []
    deadline = time.time() + 75
    while time.time() < deadline:
        try:
            neo_count = neo4j_node_count(user_id, project_id)
            neo_locs = neo4j_location_names(user_id, project_id)
        except Exception as e:  # noqa: BLE001
            log(f"WARN: neo4j query error (retrying): {e}")
        if len(neo_locs) >= 4:
            break
        time.sleep(10)

    if len(neo_locs) < 4:
        log("event pipeline did not converge in window — using DIRECT "
            "glossary_sync fallback (same K15.11 sync code, task-permitted)")
        try:
            direct_glossary_sync(user_id, project_id, book_id)
        except Exception as e:  # noqa: BLE001
            log(f"WARN: direct glossary_sync failed: {e}")
        try:
            neo_count = neo4j_node_count(user_id, project_id)
            neo_locs = neo4j_location_names(user_id, project_id)
        except Exception as e:  # noqa: BLE001
            log(f"WARN: neo4j re-query failed: {e}")

    result = "DONE" if (gloss_count >= 4 and len(neo_locs) >= 4) else "PARTIAL"
    notable_bits = [
        f"glossary {gloss_count} locs; neo4j locs={neo_locs}",
        "verified via cypher-shell on (user,project)",
    ]
    if result != "DONE":
        notable_bits.append("propagation incomplete; re-run to re-verify")
    notable = "; ".join(notable_bits)[:200]

    print(json.dumps({
        "result": result,
        "project_id": project_id,
        "book_id": book_id,
        "locations_seeded": ["玉虛宮", "碧遊宮/金鰲島", "蓬萊", "陳塘關"],
        "glossary_count": gloss_count,
        "neo4j_nodes": neo_count,
        "seed_script": "scripts/seed_fengshen_demo.py",
        "method": "direct",
        "notable": notable,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
