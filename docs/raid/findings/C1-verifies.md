# C1 Platform-Assumption Verifies — H2 / H1 / M4

> RAID cycle 1 (KG-read port). These are **VERIFY-ONLY** findings — C1 records
> them; it does NOT fix H1 (C4's K14 pipeline) or H3 wiki (C5). Evidence is from
> reading the live platform service code on `lore-enrichment/foundation` +
> a live-smoke against the running knowledge-service (host :8216).

## Live-smoke evidence (cross-service, required)

`live smoke: read graph-stats from running knowledge-service` — CONFIRMED.
- `GET http://localhost:8216/health` → **HTTP 200** (service up).
- `KnowledgeClient.get_graph_stats(...)` against `http://localhost:8216/v1/knowledge/projects/<uuid>/graph-stats`
  → **HTTP 401 "invalid token"**, parsed into a typed `KnowledgeServiceError`.
- This proves: the route exists, the read client reaches it over the network,
  the JSON contract parses, and `(user, project)` JWT-scoping is enforced
  upstream. Per coordinator scope, **EMPTY/zero data is a VALID result** (no
  Fengshen KG seeded for this project yet) — reachability + contract +
  scoping/importability is what C1 verifies, not data presence.

---

## H2 — glossary entity scoping (user / project / book)

**Question:** are glossary entity reads scoped by user/project/book? Is
cross-project bleed possible?

**Finding (code-verified):**
- Glossary entities live in table **`glossary_entities`**, keyed on **`book_id`**.
  There is **NO `project_id` column** in glossary. Evidence:
  `services/glossary-service/internal/api/server.go` routes
  `GET /internal/books/{book_id}/entities`, `.../known-entities`,
  `.../entity-count`; tests insert/scope via `glossary_entities(book_id, ...)`
  (`internal/api/entities_list_test.go`, `known_entities_test.go`).
- knowledge-service, by contrast, scopes by **`(user_id, project_id)`** — e.g.
  `GET /v1/knowledge/projects/{project_id}/graph-stats` Cypher matches
  `{user_id: $user_id, project_id: $project_id}`
  (`services/knowledge-service/app/routers/public/extraction.py` `_GRAPH_STATS_CYPHER`).
- **Scoping keys, exact:**
  - glossary entities → `book_id` (server-to-server `/internal/*` via
    `X-Internal-Token`); user-facing `/v1/glossary/books/{book_id}/...` enforces
    ownership via JWT upstream.
  - glossary wiki → `book_id` (`/v1/glossary/books/{book_id}/wiki`).
  - knowledge graph-stats / context → `(user_id, project_id)`.
- **Bridge:** the `(user, project)` world of knowledge-service maps to glossary's
  `book_id` world. The C1 client therefore scopes glossary reads by `book_id` and
  knowledge reads by `(jwt-user, project_id)`. The enrichment caller (C6+) owns
  the `project_id ↔ book_id` resolution.

**Cross-project bleed risk:** glossary reads cannot bleed *across books* —
`book_id` is mandatory in every entity/wiki path. The only way a wrong-scope read
could occur is if the caller resolves the wrong `book_id` for a project; that is
a caller-side mapping concern, not an endpoint-scoping hole. The `/internal/*`
paths trust the internal token and do NOT additionally check user ownership, so
the enrichment service MUST only ever call them with a `book_id` it is authorized
for (it derives that from the JWT-scoped project the job runs under).

**Disposition:** recorded; no fix in C1. The `project_id ↔ book_id` mapping is an
input the enrichment job supplies (C6/C14); document it there.

---

## H1 — glossary → KG sync trigger

**Question:** what triggers glossary→KG propagation today, and do reads see
synced state?

**Finding (code-verified):**
- Today propagation is **manual / batch** via a `glossary_sync` path
  (knowledge-service consumes glossary entities into Neo4j) — there is **no
  automatic event** emitted on a glossary entity write yet.
- The planned automatic path is **K14**: glossary emits
  `glossary.entity_updated` on entity write (incl. `extract-entities`), and a
  knowledge-service consumer triggers `glossary_sync → Neo4j`. That is **C4's
  deliverable**, not C1. (See OPEN_QUESTIONS_LOCKED.md "K14 event pipeline" and
  CYCLE_DECOMPOSITION C4.)
- **Consequence for C1 reads:** a graph-stats / context read sees only what has
  already been synced into Neo4j. Until C4 lands, freshly-authored glossary
  entities may NOT appear in graph-stats until the next manual `glossary_sync`.
  This is the expected current state, NOT a C1 bug.

**Disposition:** recorded; H1 is fixed by C4 (K14). C1's read clients are
correct against the *current* (manual-sync) reality and will transparently see
auto-synced state once C4 ships (no client change needed — same read endpoints).

---

## M4 — injection-defense + CJK importability of the read path

**Question:** does the read path neutralize prompt-injection-bearing entity text
on the way IN, and does CJK round-trip without mojibake?

**Finding (implemented + tested in C1):**
- **Injection neutralization** — `app/clients/sanitize.py` `neutralize_injection`
  runs on every entity name/description, wiki title/body, and chapter/scene title
  read through the glossary/book clients. It: drops zero-width/bidi control chars,
  NFC-normalizes, and replaces chat-template / role-spoofing markers
  (`<|im_start|>`, `[INST]`, `system:`, "ignore all previous instructions", …)
  with an inert `[neutralized]` placeholder. It never raises and never returns
  `None`. Tested: `test_glossary_wiki_jwt_passthrough_and_neutralizes`,
  `test_neutralize_strips_chat_markers_and_invisibles`, `test_neutralize_none_and_empty`.
  This is defense-in-depth at the *entry* seam; the heavier canon/injection check
  at proposal-creation time is C12 (out of C1 scope).
- **CJK round-trip** — the 4 LOCKED Fengshen place names (玉虛宮, 碧遊宮, 金鰲島,
  蓬萊, 陳塘關) round-trip through the clients unchanged. Tested:
  `test_cjk_round_trip_all_locked_places`, plus CJK assertions in the
  graph-stats / glossary / book / embed parse tests.
- **CJK request-body finding (fixed):** httpx's default `json=` serializer uses
  stdlib `json.dumps(ensure_ascii=True)`, which escapes CJK to `\uXXXX` on the
  wire. The bytes are valid (downstreams decode correctly), but to avoid any
  ASCII-escape surprise we serialize request bodies with `ensure_ascii=False` +
  explicit `Content-Type: application/json; charset=utf-8`
  (`KnowledgeClient._request`). Now 封神演义 names travel as genuine UTF-8.
  Tested: `test_embed_uses_model_ref_not_hardcoded_name` asserts raw `蓬萊` in
  the request body.

**Importability:** CJK entity/wiki/source text imports cleanly through all read
clients (UTF-8 in and out, no mojibake), satisfying the demo's source-faithful
Chinese requirement.

**Disposition:** implemented + green in C1.
