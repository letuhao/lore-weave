# W1 — Motif CRUD + clone/adopt/publish + catalog + quotas (detailed design)

> **Workstream:** W1 of the narrative-motif-library parallel build.
> **Spec:** [`docs/specs/2026-06-26-narrative-motif-library.md`](../../specs/2026-06-26-narrative-motif-library.md) — read **§R1 + §R2** (LOCKED). This doc obeys §R1.1 (2-tier + clone primitive), §R1.3 (B-2/B-3/B-4 rules), §R1.4 (schema), §R2.2 (genre filter + cross-genre clone-retag).
> **Master plan:** [`docs/plans/2026-06-26-motif-library-master-plan.md`](../2026-06-26-motif-library-master-plan.md) §3 (F0 contracts) + §4 (W1 def) + §7 (risk-guards-as-tests).
> **Owner files (disjoint):** `routers/motif.py` (new), `db/repositories/motif_repo.py` (clone/adopt/publish methods — F0 hands ownership post-foundation), `tests/unit/test_motif_router.py` (new). Plus the publish-strip **DB trigger** (added to `db/migrate.py` by **F0**, exercised by W1 tests — W1 does NOT edit migrate.py).
> **Status:** DESIGN (file-by-file). Architecture is decided; this is the build contract.

---

## 1. Scope + F0 contracts consumed

### 1.1 What W1 owns (the HTTP surface + the clone/publish repo methods)

W1 builds the **non-agentic, user-driven HTTP CRUD** for motifs plus the three tenancy operations that are *not* plain field edits:

- **list / get / create / patch / archive** — the CRUD surface (`GET`/`POST`/`PATCH /v1/composition/motifs[/{id}]`).
- **clone** (= adopt = cross-genre-retag = customize — the **ONE** primitive, §R1.1.1) — `POST /v1/composition/motifs/{id}/clone`.
- **publish** (visibility flip to `public`/`unlisted`) — folded into `PATCH` (a `visibility` field change), with the imported-derived strip enforced by a **DB trigger** (F0-owned) so it fires on *any* write path, not just this one.
- **catalog** projection (explicit allow-list, `visibility='public'`) — `GET /v1/composition/motifs/catalog`.
- **per-user quotas** on publish + adopt (mirror `D-MCP-BOOK-CREATE-QUOTA`).

W1 does **NOT** own: retrieval/embedding (W3 owns `motif_embed.py` + the `MotifRetriever`; W1 *calls* W3's embed helper inside clone/patch when the summary changed), the planner (W2), MCP tools (W4 — but W4 reuses W1's repo `clone`/`create`/`patch`), conformance (W5), arc templates (W10), import_source ingest (W9). The `motif_link` cycle/same-tier guards live in **F0** (DB-level) + are *honored* by clone (clone of a `pattern` copies its `composed_of` subgraph — see §3.6).

### 1.2 F0 contracts W1 consumes (frozen — do not re-derive)

| Contract | Source | W1 use |
|---|---|---|
| `motif` table (§R1.4 schema) — 2 tenancy partials, `motif_user_owned` CHECK, `embedded_summary_hash`, platform `embedding_model` | F0 `db/migrate.py` | every query |
| **publish-strip trigger** on `motif` (examples→`[]` + source_ref→opaque token when `source IN ('imported','adopted'-from-imported)` AND row becomes shareable) | F0 `db/migrate.py` | W1 publish test asserts it fires |
| `Motif`, `MotifBeat`, `MotifRole`, `MotifLink` Pydantic models, all create/patch args `ForbidExtra` | F0 `db/models.py` | request/response DTOs |
| `MotifRepo` class skeleton — F0 ships `create`/`get_visible`/`patch`/`archive`/`list_for_caller` stubs; **W1 implements `clone()` + extends `patch()`/`create()` with the embed write-through + quota hooks** | F0 `db/repositories/motif_repo.py` (ownership transfers to W1) | W1 fills these |
| `MotifRetriever`/`motif_embed` embed helper signature (`embed_summary(text) -> (vec, model, dim, hash)`) | F0 freezes signature, W3 implements | clone/patch re-embed |
| config: `motif_embed_model`, `motif_max_public`, `motif_max_adopt` | F0 `config.py` | quota ceilings + embed model id |
| `get_current_user`, `get_motif_repo` dep, `get_embedding_client_dep` | existing `middleware/jwt_auth.py` + F0 `deps.py` | router wiring |

**The F0 `MotifRepo.clone` signature W1 implements (frozen in master-plan §3.3):**

```python
async def clone(
    self,
    caller_id: UUID,
    src_motif_id: UUID,
    *,
    target_owner: UUID,                  # always == caller_id now (book tier dropped, §R1.1.1)
    retag_genres: list[str] | None = None,  # cross-genre clone-and-retag (§R2.2)
) -> Motif: ...
```

> **Note on `target_owner`:** the signature keeps the parameter for forward-compat, but with the **book tier removed** (§R1.1.1) the only legal target is the **caller's user tier**. W1 asserts `target_owner == caller_id` and rejects anything else (a defensive guard; the router never passes a different value). This is the H-7 correction: **one clone target, not two ON-CONFLICT branches**.

---

## 2. The HTTP API

All routes live in `routers/motif.py` under `APIRouter(prefix="/v1/composition")`, gateway-proxied as `/v1/composition/motifs*`. Auth is the JWT `get_current_user` dep (→ `caller_id`). House conventions (matched verbatim from `references.py`/`style_voice.py`): `model_dump(mode="json")` responses, a missing/not-visible motif → **404 no-oracle**, optimistic concurrency via `If-Match` / `expected_version` (→ 412), `ForbidExtra` arg models.

### 2.0 The read predicate (R1.1) — lives in the repo SELECT, not the handler

Every read (`get_visible`, `list_for_caller`, and the `clone` source fetch) filters on the **single** locked predicate (§R1.1.1):

```sql
-- a motif is visible to caller IFF:
WHERE m.id = $1
  AND ( m.owner_user_id IS NULL            -- system tier (seed/migrate-only)
        OR m.visibility = 'public'         -- published, any owner
        OR m.owner_user_id = $caller )     -- the caller's own (private/unlisted/public)
```

No `book_id` branch (book tier dropped → kills the IDOR-1 book dimension). `unlisted` is **not** discoverable in list/catalog but **is** fetchable by direct id (link-sharing semantics) — handled by the projection scope, see §2.6. This predicate is the F0-frozen body of `MotifRepo.get_visible`; W1 reuses it unchanged for `clone`'s source fetch (you can only clone what you can see).

### 2.1 `GET /v1/composition/motifs` — list (tier-merged, owned + system + optional public)

```
GET /v1/composition/motifs?scope=mine|system|all&genre=&kind=&q=&language=&status=&limit=&offset=
```

| Param | Type | Default | Notes |
|---|---|---|---|
| `scope` | `mine\|system\|all` | `all` | `mine`=`owner_user_id=caller`; `system`=`owner_user_id IS NULL`; `all`=both (NOT others' public — that's the catalog, §2.6) |
| `genre` | string (repeatable) | — | `genre_tags && $genres` (GIN `idx_motif_genre`) |
| `kind` | enum | — | one of the 7 kinds |
| `q` | string ≤200 | — | ILIKE on `name`/`summary`/`code` (NOT vector — that's retrieval/W3) |
| `language` | string | — | exact `language=` filter |
| `status` | `draft\|active\|archived` | `active` | drafts shown only when explicitly asked (mirrors §R2.8 `_motif_search status?`) |
| `limit`/`offset` | int | 50 / 0 | `limit` capped at 100 |

**Response** (the `embedding` column is **never** projected — server-side only, references.py precedent):
```json
{ "motifs": [ <Motif.model_dump> … ], "total": 42, "limit": 50, "offset": 0 }
```
`Motif.model_dump` here is the **full owner/author view** (roles/beats/conditions/examples) — NOT the catalog allow-list (§2.6). Returned because the caller owns or is the platform for every row in this scope.

Repo: `list_for_caller(caller_id, *, scope, genre, kind, status, q, language, limit, offset)` (F0 stub; W1 adds `limit`/`offset` + the `q` ILIKE + `total` count).

### 2.2 `GET /v1/composition/motifs/{id}` — read one

`get_visible(caller_id, motif_id)` → 404 if `None`. Returns the full `Motif` view. This is the owner/author read; the catalog (§2.6) is the redacted public read.

### 2.3 `POST /v1/composition/motifs` — create (user tier; owner server-stamped)

```python
class MotifCreate(ForbidExtra):           # F0 model; W1 imports
    code: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    name: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    language: Annotated[str, StringConstraints(min_length=2, max_length=12)] = "en"
    kind: MotifKind = "sequence"          # Literal enum, the 7 kinds
    category: str | None = None
    summary: Annotated[str, StringConstraints(max_length=4000)] = ""
    genre_tags: list[_Tag] = Field(default_factory=list, max_length=40)
    roles: list[MotifRole] = Field(default_factory=list, max_length=20)
    beats: list[MotifBeat] = Field(default_factory=list, max_length=40)
    preconditions: list[dict] = ...        # [{text}]
    effects: list[dict] = ...
    tension_target: int | None = Field(default=None, ge=1, le=5)
    emotion_target: str | None = None
    examples: list[dict] = Field(default_factory=list, max_length=20)
    visibility: Literal["private","unlisted","public"] = "private"
    # NO owner_user_id / book_id / source / source_ref / id / version / embedding ARGS — server-controlled.
```

**Server-stamps (§R1.3 — the B-2 rule):**
- `owner_user_id = caller_id` **unconditionally**. The client cannot pass it (`ForbidExtra` rejects the field). A regular user can **never** create a both-NULL (system) row → the DB `motif_user_owned` CHECK is the backstop.
- `source = 'authored'`, `source_ref = NULL`, `source_version = NULL`, `version = 1`, `status = 'active'`.
- `embedding`: if `summary` non-empty, embed via W3's helper using the **platform** `motif_embed_model` (NOT the user's BYOK model — §R1.1.2); store `embedding`, `embedding_model`, `embedded_summary_hash`. Embed failure → create still succeeds with a null vector (degrade like references.py; retrieval just won't rank it until a later re-embed). `embedding_model` is **always** `settings.motif_embed_model` — asserted by W3's cross-model test.

If `visibility='public'` on create → run the **publish quota pre-check** (§5) AND the strip trigger fires (but a fresh authored motif has author-written examples, not imported → trigger no-ops on `source='authored'`). Returns 201 + the created `Motif`. A duplicate `(owner_user_id, code, language)` → **409** `MOTIF_CODE_EXISTS` (the `uq_motif_user` partial).

### 2.4 `PATCH /v1/composition/motifs/{id}` — edit / flip visibility

```python
class MotifPatch(ForbidExtra):
    # every field Optional; only present keys are updated (partial patch)
    name: str | None = None
    summary: str | None = None
    genre_tags: list[str] | None = None
    kind: MotifKind | None = None
    category: str | None = None
    roles: list[MotifRole] | None = None
    beats: list[MotifBeat] | None = None
    preconditions: list[dict] | None = None
    effects: list[dict] | None = None
    tension_target: int | None = None
    emotion_target: str | None = None
    examples: list[dict] | None = None
    visibility: Literal["private","unlisted","public"] | None = None
    status: Literal["draft","active","archived"] | None = None
```
Header `If-Match: <version>` → `expected_version` (412 on mismatch). **Owner-only**: the repo `patch(caller_id, …)` filters `WHERE id=$id AND owner_user_id=$caller` — a system row (owner NULL) or another user's row never matches → 404 (the FE "clone to edit" affordance, §11 system-read-only). This is the tenancy rule: **you edit your clone, never the shared original**.

**Re-embed on summary change (§11 "re-embed on summary edit"):** if `summary` is in the patch AND differs from stored, the repo re-embeds **transactionally in the same UPDATE tx** (W3's `embed_summary` + write `embedding`/`embedded_summary_hash`) — no stale-vector window (W3 owns the staleness guard; W1's patch calls it). `version` bumps by 1 on every patch.

**Publish via patch** (`visibility` → `public`/`unlisted`): the **publish quota pre-check** runs (§5) before the UPDATE when transitioning *into* a shareable state; the **strip trigger** (F0) fires on the row → for an imported-derived motif it nulls `examples`/opaques `source_ref` at the DB layer. Going `public→private` is always allowed (un-publishing never hits quota).

### 2.5 `DELETE /v1/composition/motifs/{id}` — archive (soft)

`archive(caller_id, motif_id)` → `UPDATE motif SET status='archived', version=version+1 WHERE id=$id AND owner_user_id=$caller`. Owner-only. Soft (not hard delete) because `motif_application.motif_id` FKs it `ON DELETE SET NULL` and an archived motif must still resolve in the trace (the "what was bound" history, §R1.4 edge-F3). Returns `{"id": …, "archived": true}`. A system/foreign row → 404. (Hard purge is out of scope for W1.)

### 2.6 `GET /v1/composition/motifs/catalog` — public discovery projection (allow-list)

```
GET /v1/composition/motifs/catalog?genre=&q=&kind=&language=&sort=recent|name&limit=&offset=
```
Reads `WHERE visibility = 'public' AND status='active'` (the `idx_motif_public` partial; `unlisted` is **excluded** — link-only, not discoverable). **Any authenticated user** may read it (`get_current_user`, no grant). The projection is an **explicit allow-list** (§R1.3 B-3 — the catalog-service `catalogItem` struct precedent, never `SELECT *`):

```python
# the ONLY columns the catalog returns — curated, NOT motif.model_dump:
_CATALOG_COLS = (
    "id", "code", "language", "kind", "category", "name", "summary",
    "genre_tags", "tension_target", "emotion_target", "source",
    "abstraction_confidence", "judge_score", "version", "updated_at",
)
# DELIBERATELY EXCLUDED (never leave the server on the public path):
#   embedding          — the vector
#   examples           — may carry imported source passages (copyright, §12.6)
#   source_ref         — raw upstream id / lineage (replaced by opaque token even when shown)
#   preconditions/effects/roles/beats — the full meso content stays owner-only until adopted
#   owner_user_id      — do not leak who authored a public motif by default
#   embedded_summary_hash, embedding_model, mining_support, source_version
```

> **Design decision (open micro-decision MD-1, §8):** do `roles`/`beats`/`preconditions`/`effects` belong in the catalog *preview*? Recommendation: **NO** in the list projection (keep the catalog row light + un-clonable-without-adopt), **but** expose them on a dedicated `GET /motifs/{id}` only after the caller has the row visible — i.e. a public motif's full body is visible via §2.2 `get_visible` (since `visibility='public'` satisfies the predicate). So the *catalog list* is the light allow-list; the *detail* read of a public motif returns the full body (legitimate — it's public). The allow-list's job is to keep `embedding`/`examples`/raw `source_ref` off **every** path, list and detail alike — those three are stripped from `get_visible`'s public branch too (see §4.2).

**Response:**
```json
{ "items": [ {<allow-listed fields>, "adopt_target": "user"} … ], "total": …, "limit": …, "offset": … }
```
(`adopt_count`/rating are **deferred** to P2+ per §11 — not in W1.)

### 2.7 `POST /v1/composition/motifs/{id}/clone` — adopt / customize / cross-genre-retag

The ONE primitive. Detailed in §3.

```python
class MotifClone(ForbidExtra):
    retag_genres: list[_Tag] | None = Field(default=None, max_length=40)  # cross-genre clone (§R2.2)
    # NO target arg — target is ALWAYS the caller's user tier (book tier dropped).
```
`POST .../{id}/clone {retag_genres?: [...]}` → **adopt quota pre-check** (§5) → `clone(caller_id, id, target_owner=caller_id, retag_genres=...)` → **201** + the new user-tier `Motif`. Idempotent: a second clone of the same source returns the **existing** clone (200, not a duplicate) — see §3.3.

### 2.8 Route table summary

| Method + path | Repo method | Gate | Quota | Codes |
|---|---|---|---|---|
| `GET /motifs` | `list_for_caller` | `get_current_user` | — | 200 |
| `GET /motifs/{id}` | `get_visible` | predicate | — | 200 / 404 |
| `POST /motifs` | `create` | self | publish (if public) | 201 / 409 / 422 |
| `PATCH /motifs/{id}` | `patch` | owner-only | publish (if →shareable) | 200 / 404 / 409 / 412 |
| `DELETE /motifs/{id}` | `archive` | owner-only | — | 200 / 404 |
| `GET /motifs/catalog` | `list_public` | any authed | — | 200 |
| `POST /motifs/{id}/clone` | `clone` | predicate (source visible) | adopt | 201 / 200(idem) / 404 / 409 |

---

## 3. The CLONE primitive (in detail)

> **One mechanism = adopt + cross-genre-retag + customize** (§R1.1.1). `public→user`, `system→user`, `user→user-variant` all go through `clone()`. There is **no separate adopt path**; "adopt" is the name the UI/MCP gives a clone of a public/system motif, "customize" is the name for a clone of your own, "cross-genre" is a clone with `retag_genres` set.

### 3.1 The column-enumerated INSERT...SELECT (glossary precedent)

Modeled exactly on `adoptBookOntologyCore` (column-enumerated copy, advisory lock, source_ref stamp) but **single-target** (user tier only — H-7 correction, no two-ON-CONFLICT mess):

```sql
-- inside clone(), in a transaction, AFTER the advisory lock (§3.4):
INSERT INTO motif (
    owner_user_id, code, language, visibility, kind, category, name, summary,
    genre_tags, roles, beats, preconditions, effects, tension_target, emotion_target,
    examples, abstraction_confidence,
    source, source_ref, source_version,
    embedding, embedding_model, embedded_summary_hash,
    judge_score, mining_support, status, version
)
SELECT
    $caller_id,                              -- (1) RESET owner → the caller (server-stamped)
    m.code, m.language,                      -- code/language preserved (the clone's identity within the caller's tier)
    'private',                               -- (2) RESET visibility → private (a clone is never born public)
    m.kind, m.category, m.name, m.summary,
    COALESCE($retag_genres, m.genre_tags),   -- (3) cross-genre RETAG if provided, else copy (§R2.2)
    m.roles, m.beats, m.preconditions, m.effects, m.tension_target, m.emotion_target,
    m.examples,                              -- copied here; the publish-strip TRIGGER handles imported-derived stripping at PUBLISH time, not clone time
    m.abstraction_confidence,
    'adopted',                               -- (4) source := 'adopted' ALWAYS (lineage marker, §R1.4)
    $opaque_lineage,                         -- (5) source_ref := opaque token (NOT 'system:'||id — see §3.5)
    m.version,                               -- (6) source_version := the pinned upstream version (N-4, for the future 3-way diff)
    m.embedding, m.embedding_model, m.embedded_summary_hash,   -- (7) COPY the vector — same platform space (§R1.1.2)
    NULL, NULL,                              -- (8) RESET judge_score + mining_support (clone is not independently judged/mined)
    'active',                                -- (9) RESET status → active
    1                                        -- (10) RESET version → 1 (a fresh row's own lifecycle)
FROM motif m
WHERE m.id = $src_id
  AND ( m.owner_user_id IS NULL OR m.visibility = 'public' OR m.owner_user_id = $caller_id )  -- the R1.1 read predicate: clone only what you can see
ON CONFLICT (owner_user_id, code, language) WHERE owner_user_id IS NOT NULL
  DO NOTHING                                 -- idempotent (§3.3) — ONE conflict target (uq_motif_user)
RETURNING <_SELECT_COLS>;                     -- the vector is NOT in _SELECT_COLS (server-side)
```

**The reset/preserve table (the eval-gate checks each row):**

| Field | Clone behavior | Why |
|---|---|---|
| `id` | **NEW** `uuidv7()` (DEFAULT) | fresh identity |
| `owner_user_id` | **RESET** → `caller_id` | the core tenancy rule — your tier |
| `code`, `language` | **preserved** | the clone's stable identity within your tier (the dedup key) |
| `visibility` | **RESET** → `private` | a clone is never auto-public; re-publish is a deliberate later act |
| `genre_tags` | **RETAG** if `retag_genres` else copy | §R2.2 cross-genre clone-and-retag |
| `source` | **RESET** → `'adopted'` | lineage marker, distinguishes from `authored`/`mined`/`imported` |
| `source_ref` | **RESET** → opaque lineage token | §3.5 — no back-readable upstream id |
| `source_version` | **set** → upstream `version` | pins the version for a future "update available" 3-way diff (N-4) |
| `embedding`,`embedding_model`,`embedded_summary_hash` | **COPY** | same platform vector space → cross-tier cosine stays correct (§R1.1.2); no re-embed needed |
| `judge_score`, `mining_support` | **RESET** → NULL | the clone is not independently judged or mined |
| `version` | **RESET** → 1 | the clone's own optimistic-lock lifecycle |
| `created_at`, `updated_at` | **NEW** `now()` (DEFAULT) | fresh timestamps |
| roles/beats/preconditions/effects/name/summary/category/kind/tension/emotion/examples/abstraction_confidence | **COPY** | the content you adopt |

### 3.2 Why copy the vector instead of re-embedding

§R1.1.2 locks **one platform embedding model** for all motif vectors. Because source and clone share `embedding_model = settings.motif_embed_model`, the source's vector is valid in the clone's space verbatim — copying is correct AND cheaper (no provider call on the adopt hot path). A re-embed is only needed if the clone's `summary` is later **edited** (handled by `PATCH` §2.4, not clone). This is W3's invariant ("cross-model contamination impossible"); W1's clone upholds it by copy + the same-model assert.

### 3.3 Idempotency

The `ON CONFLICT (owner_user_id, code, language) WHERE owner_user_id IS NOT NULL DO NOTHING` makes a repeated clone a no-op INSERT. But `RETURNING` yields **no row** on conflict, so the repo follows the glossary "adopt is idempotent" shape:

```python
async def clone(self, caller_id, src_motif_id, *, target_owner, retag_genres=None) -> Motif:
    assert target_owner == caller_id, "book tier dropped — clone target is always the caller"
    async with self._pool.acquire() as c, c.transaction():
        await c.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"motif-clone:{caller_id}")  # §3.4
        row = await c.fetchrow(_CLONE_SQL, caller_id, src_motif_id, retag_genres)
        if row is not None:
            return _row_to_motif(row)
        # ON CONFLICT DO NOTHING → the clone already exists (idempotent re-adopt).
        # Re-read it by (owner, code, language) of the SOURCE, scoped to the caller.
        existing = await c.fetchrow(
            f"SELECT {_SELECT_COLS} FROM motif "
            "WHERE owner_user_id=$1 AND (code,language) = "
            "  (SELECT code,language FROM motif WHERE id=$2) ",
            caller_id, src_motif_id)
        if existing is None:
            # source vanished/not-visible AND no existing clone → not-accessible
            raise MotifNotVisible()
        return _row_to_motif(existing)
```
Router maps `MotifNotVisible` → 404 (no oracle). The idempotent re-read returns 200 (existing) vs 201 (new) — the router distinguishes by whether the INSERT produced a row (the repo returns a `(motif, created: bool)` tuple in the real impl; elided above for clarity).

### 3.4 Advisory lock keyed on **owner** (NOT hash(NULL)) — the audit fix

The glossary precedent locks `hashtext('gloss-adopt:'||book_id)`. The motif clone serializes on the **caller's user id**, not on the source or on a book:

```sql
SELECT pg_advisory_xact_lock(hashtext('motif-clone:' || $caller_id::text))
```

**Why this exact key (the audit's "NOT hash(NULL)" warning):** the book tier is gone, so there is no `book_id` to key on. If we naively ported the glossary key using the *source's* `book_id` (now always NULL) we'd compute `hashtext('motif-clone:')` — a **single global lock** every concurrent adopt across all users would contend on (and worse, `hash(NULL)`-style degeneracies). Keying on `caller_id` gives each user their own lock domain: two users adopting the same public motif concurrently never block each other, while one user double-submitting the same adopt is correctly serialized (the second waits, then hits `ON CONFLICT`). This is correct because the uniqueness it protects (`uq_motif_user` on `(owner_user_id, code, language)`) is **per-owner** — so the lock granularity should be per-owner too.

### 3.5 `source_ref` → opaque lineage token (no back-readable foreign id)

§R1.3 B-3: on an imported-derived publish, `source_ref` must become an **opaque lineage token**, not a back-readable foreign id. W1 generalizes this to **all clones**: the clone's `source_ref` is never the raw `'system:'||src_id` / `'user:'||src_id` string (which would leak the source owner + let a clone be walked back to a private original). Instead:

```python
# opaque, non-reversible lineage token: HMAC(secret, src_id) truncated, prefixed by tier-class only.
opaque_lineage = "lin_" + hmac_sha256(settings.lineage_secret, str(src_id))[:24]
```
- It is **stable** (same source → same token) so "update available" can still match a clone to its upstream *server-side* (the server holds the secret + can recompute the token for a candidate upstream), but a **client** holding the token cannot derive `src_id`.
- It carries **no** owner id, no book id, no plaintext upstream id.
- The future N-4 3-way diff (W11) resolves it server-side by recomputing tokens over the user's visible upstream set — it never trusts a client-supplied source id.

> This means the lineage is opaque on **every** clone, not only imported-derived ones — simpler + strictly safer than a conditional. The publish-strip *trigger* (F0) additionally nulls `examples` for imported-derived rows at publish time; the opaque `source_ref` is set at clone time by this repo.

### 3.6 Cloning a `pattern` clones its `composed_of` subgraph (audit H-3)

A `kind='pattern'` motif is a named composition (`motif_link.composed_of` → member motifs). Adopting it must adopt the members too, else the clone references motifs the caller can't see. **W1 scope decision:** the *member-subgraph clone* is driven by W1's `clone()` but the `motif_link` table + its cycle/same-tier guards are **F0-owned**. W1's `clone()`:
1. clones the root motif (above),
2. if `kind='pattern'`, recursively clones each `composed_of` member **that the caller doesn't already own** (re-using the same idempotent `clone`), then
3. re-creates the `composed_of`/`precedes` edges **between the caller's cloned copies** (never pointing at the source's rows — H-2 "user edges may not touch system motifs").

This recursion is bounded by the F0 cycle guard (no infinite loop). **Micro-decision MD-2 (§8):** if the member-subgraph clone is heavy, P1 may ship **root-only clone + a `members_pending` flag** and defer subgraph adoption to W10 (arc templates, where `pattern`/arc composition is the focus). **Recommendation:** ship root + direct `composed_of` members (one level) in W1; defer deep nesting to W10. Patterns are P1-rare (seed packs are mostly `sequence`/`scheme`).

---

## 4. Catalog projection = explicit allow-list + `visibility='public'`

### 4.1 The allow-list is the no-leak boundary (B-3)

Per §2.6, the catalog query is a curated column list (`_CATALOG_COLS`), never `motif.model_dump()` / `SELECT *`. This mirrors catalog-service's `catalogItem` struct (a hand-listed projection with `json:` tags, fed by `/internal/books/{id}/projection`). The three fields that must **never** reach a non-owner — `embedding`, `examples`, raw `source_ref` — are excluded structurally, so even a future careless `SELECT *` refactor on the public path is caught by the no-leak test (§6).

### 4.2 The same redaction applies to a public motif's detail read

`get_visible`'s **public branch** (a row the caller does NOT own but is `visibility='public'`) returns the full meso content (roles/beats/conditions — legitimately public) **but still redacts** `embedding` (always server-side), `examples` (copyright — may be imported source text), and replaces `source_ref` with its opaque token. The owner branch (caller owns the row) sees everything except the raw `embedding`. W1 implements this as a `redact_for_viewer(motif, *, is_owner)` helper applied in the router before `model_dump`. (F0's `get_visible` returns the raw row; W1's router redacts — keeps the repo a pure data layer.)

| Field | Owner read (§2.2) | Public detail read (§2.2, not owner) | Catalog list (§2.6) |
|---|---|---|---|
| roles/beats/preconditions/effects | ✓ | ✓ | ✗ (light list) |
| summary/name/genre/kind/tension/emotion | ✓ | ✓ | ✓ |
| examples | ✓ | ✗ (copyright) | ✗ |
| embedding | ✗ (always) | ✗ | ✗ |
| source_ref | opaque token | opaque token | ✗ |
| owner_user_id | ✓ | ✗ | ✗ |

### 4.3 `unlisted` semantics

`unlisted` = fetchable by direct id (link-share) but **not** in `list` (`scope=all`) or `catalog`. Enforced by: `catalog`/`list` filter `visibility='public'` (catalog) / owned+system (list); `get_visible`'s predicate has **no** `unlisted` clause for non-owners — so an unlisted motif is visible to a non-owner **only** if... it is not (the predicate is system|public|owner). **Correction:** `unlisted` is visible to its **owner** and, for link-sharing, must be fetchable by anyone with the id. To support link-share, `get_visible` adds `OR visibility='unlisted'` **for direct-id fetch only** (§2.2), never for list/catalog. This is the one place the predicate widens for by-id reads. (If link-share-by-id is not wanted for P1, drop the `unlisted` widening and treat `unlisted` as owner-only-pre-publish staging — **Micro-decision MD-3, §8; recommend: owner-only staging for P1**, add link-share in P2 with the sync work.)

---

## 5. Quotas (per-user publish/adopt ceilings — mirror `D-MCP-BOOK-CREATE-QUOTA`)

The book-service precedent: a package-var ceiling (`maxBooksPerUser = 200`), a `countActiveBooks` helper sharing the list predicate, an **informative** refusal (not the uniform not-accessible error — a quota condition is not an ownership one), checked **before** the insert. W1 mirrors this in Python.

### 5.1 Two ceilings (config, F0-provided)

```python
# config.py (F0):
motif_max_public: int = 200   # max motifs a user may have at visibility IN ('public','unlisted')
motif_max_adopt:  int = 500   # max ADOPTED (source='adopted') motifs a user may hold
```
Both are `settings` ints (env-overridable; tests lower them to seed at the cap cheaply, like `maxBooksPerUser` being a var). Rationale for two separate ceilings: publish is the **spam-to-catalog** surface (cap protects the public catalog from an agent flooding it); adopt is the **library-bloat** surface (cap protects one user's own list + the embed/storage cost of unbounded clones). Mining-run quota (`motif_max_mine_runs`) is **W8/W11**, not W1.

### 5.2 The count helpers (share the list predicate)

```python
# motif_repo.py:
async def count_shared_by_owner(self, owner_id: UUID) -> int:
    # the publish ceiling input — same predicate the catalog "mine published" view uses
    return await self._scalar(
        "SELECT count(*) FROM motif "
        "WHERE owner_user_id=$1 AND visibility IN ('public','unlisted') AND status<>'archived'",
        owner_id)

async def count_adopted_by_owner(self, owner_id: UUID) -> int:
    # the adopt ceiling input
    return await self._scalar(
        "SELECT count(*) FROM motif "
        "WHERE owner_user_id=$1 AND source='adopted' AND status<>'archived'",
        owner_id)
```

### 5.3 The pre-checks (before the write, informative refusal)

```python
# router, on POST /motifs (visibility='public') and PATCH →public/unlisted:
if going_shareable:
    n = await repo.count_shared_by_owner(caller_id)
    if n >= settings.motif_max_public:
        raise HTTPException(409, detail={
            "code": "MOTIF_PUBLISH_LIMIT_REACHED",
            "limit": settings.motif_max_public,
            "message": f"published-motif limit reached ({settings.motif_max_public}) — unpublish one first"})

# router, on POST /motifs/{id}/clone:
n = await repo.count_adopted_by_owner(caller_id)
if n >= settings.motif_max_adopt:
    raise HTTPException(409, detail={
        "code": "MOTIF_ADOPT_LIMIT_REACHED",
        "limit": settings.motif_max_adopt,
        "message": f"adopted-motif limit reached ({settings.motif_max_adopt}) — archive one first"})
```

**Race note:** the count-then-write is not atomic, so a burst of concurrent publishes could overshoot by the concurrency width. Acceptable (the book-service precedent has the same property — it's a *generous* ceiling against runaway loops, not a hard billing boundary). If a hard cap is needed later, a partial-unique-count constraint or a `SELECT ... FOR UPDATE` on a per-user quota row (the daily_progress pattern) is the upgrade — tracked, not built in W1.

### 5.4 MCP parity (W4 reuses, not W1)

W4's `_motif_create`/`_motif_adopt` MCP tools call the **same** repo `count_*` helpers + raise the same informative tool error (book-service did exactly this — the ceiling on *both* the MCP tool and the HTTP surface via a shared helper). W1 exposes the helpers; W4 wires them into the MCP path. The eval-gate test for the N+1 rejection lives in W1 (HTTP) + is referenced by W4 (MCP).

---

## 6. Tests + eval-gate (`tests/unit/test_motif_router.py`)

DB-gated unit tests (the book-service `mcp_actions_db_test.go` precedent — a real Postgres, lower the ceiling to seed at the cap cheaply). Structure mirrors `test_grant_gate.py` / `test_progress_router.py` (FastAPI `TestClient` + a seeded pool fixture from `conftest.py`).

### 6.1 CRUD + tenancy

| Test | Asserts |
|---|---|
| `test_create_stamps_owner` | created motif `owner_user_id == caller`; a `MotifCreate` with an extra `owner_user_id` key → 422 (`ForbidExtra`) |
| `test_create_rejects_system_row` | no API path produces a both-NULL row; the DB CHECK + the server-stamp both hold |
| `test_create_duplicate_code` | second `(owner,code,language)` → 409 `MOTIF_CODE_EXISTS` |
| `test_patch_owner_only` | user B patching user A's motif → 404 (no oracle) |
| `test_patch_system_readonly` | patching a system (owner-NULL) motif → 404 ("clone to edit") |
| `test_patch_if_match_stale` | wrong `If-Match` → 412 |
| `test_patch_resummary_reembeds` | changing `summary` bumps `embedded_summary_hash` + version (mock W3 embed) |
| `test_archive_soft` | DELETE sets `status='archived'`, row still readable by owner, application FK survives |
| `test_get_idor` | **B-2 IDOR** — user B `GET`/`PATCH`/`DELETE` user A's *private* motif → 404; user A's *public* → 200 redacted |

### 6.2 Clone (the primitive — every reset + idempotency)

| Test | Asserts (eval-gate row) |
|---|---|
| `test_clone_resets_identity` | new `id`, `owner=caller`, `visibility='private'`, `source='adopted'`, `version=1`, fresh timestamps |
| `test_clone_copies_content` | roles/beats/conditions/summary copied byte-equal |
| `test_clone_copies_vector_same_model` | `embedding`/`embedding_model`/`embedded_summary_hash` copied; `embedding_model == settings.motif_embed_model` (no re-embed, B-1 cross-model impossible) |
| `test_clone_resets_judge_mining` | `judge_score`/`mining_support` → NULL |
| `test_clone_idempotent` | second clone of same source → **same** clone id (200), no duplicate row |
| `test_clone_advisory_lock_per_owner` | two concurrent clones (asyncio.gather) by the **same** user of the same source → exactly one row; by **different** users → two rows, no cross-block (proves the owner-keyed lock, NOT hash(NULL)) |
| `test_clone_source_predicate` | clone of another user's **private** motif → 404; of a **public**/system → ok |
| `test_clone_retag_genres` | `retag_genres` set → clone's `genre_tags == retag` (cross-genre, §R2.2); unset → copied |
| `test_clone_opaque_source_ref` | clone `source_ref` matches `lin_<hmac>` shape, NOT `system:`/`user:`+id; the same source → stable token |
| `test_clone_pattern_subgraph` | cloning a `pattern` clones its direct `composed_of` members + re-points edges at the caller's copies (H-3) |

### 6.3 Catalog no-leak (B-3)

| Test | Asserts |
|---|---|
| `test_catalog_only_public` | `unlisted`/`private`/`archived`/system rows absent; only `public+active` present |
| `test_catalog_allowlist_no_embedding` | response rows have **no** `embedding` key |
| `test_catalog_allowlist_no_examples` | **no** `examples` key (imported-derived seeded with a fake source passage → never appears) |
| `test_catalog_no_raw_source_ref` | **no** raw `source_ref`; (if present at all) only the opaque token |
| `test_public_detail_redacts` | `GET /motifs/{id}` of a public-not-owned motif: full roles/beats present, `examples` absent, `source_ref` opaque, `embedding` absent |

### 6.4 Quota (B-4)

| Test | Asserts |
|---|---|
| `test_publish_quota_rejects_n_plus_1` | seed user at `motif_max_public` (lowered to e.g. 2) → next `PATCH visibility=public` → 409 `MOTIF_PUBLISH_LIMIT_REACHED`; un-publish then re-publish → ok |
| `test_create_public_quota` | `POST` with `visibility='public'` at the cap → 409 |
| `test_adopt_quota_rejects_n_plus_1` | seed at `motif_max_adopt` → next clone → 409 `MOTIF_ADOPT_LIMIT_REACHED` |
| `test_quota_informative_not_uniform` | the 409 body carries `code`+`limit` (NOT the uniform not-accessible 404 — quota ≠ ownership) |
| `test_archive_frees_quota` | archiving a published motif drops the shared count → publish succeeds again |

### 6.5 The eval-gate (master-plan §4 W1 row)

The W1 gate passes IFF: **clone idempotent + resets id/owner/timestamps/version** (6.2), **strips `examples[]` on imported-derived publish** via the trigger (6.6 below), **catalog never leaks a non-allow-list field** (6.3), **quota rejects the N+1 publish** (6.4), **tenancy IDOR green** (6.1 `test_get_idor`).

### 6.6 The publish-strip trigger (F0-owned DDL, W1-exercised)

```python
def test_publish_strip_trigger_imported():
    # seed an imported-derived motif with examples=[{text:"<verbatim source passage>"}], source='adopted'
    #   whose lineage resolves to an import_source (the trigger condition).
    # PATCH visibility='public' → re-read → examples == [] AND source_ref is opaque/nulled.
def test_publish_strip_trigger_skips_authored():
    # an authored motif's examples SURVIVE publish (only imported-derived are stripped).
```
> The trigger lives in `migrate.py` (F0). W1 does **not** edit migrate.py; it writes the tests that prove the trigger's contract. If F0's trigger is not yet landed when W1 builds, these two tests are `xfail(strict=False)` with a `# F0 trigger pending` marker + a contract note — flipped to strict once F0 merges. (This is the W1↔F0 seam; the master-plan §8 has F0 land first, so in the normal order the trigger is present.)

---

## 7. Audit risk-guards as failing-tests (B-3 / B-4 / H-7)

Per master-plan §7 ("carry the audit blockers as tests, not memory"), each W1-owned blocker is written **failing-first**, then made green:

### B-3 — examples stripped on publish + catalog allow-list
- **Failing test first:** `test_catalog_allowlist_no_examples` + `test_publish_strip_trigger_imported` (§6.3/6.6) — written and RED before the projection allow-list + the trigger-contract wiring exist.
- **Green by:** the `_CATALOG_COLS` curated projection (§4.1) + `redact_for_viewer` (§4.2) + F0's trigger.
- **Why it's load-bearing:** a `SELECT *` catalog would ship the embedding (cost + IP) and imported source passages (copyright, §12.6) to every authed user. The allow-list makes the leak structurally impossible.

### B-4 — quota + (the MCP path's) usage-billing pre-check
- **Failing test first:** `test_publish_quota_rejects_n_plus_1` + `test_adopt_quota_rejects_n_plus_1` (§6.4) — RED before the `count_*` helpers + pre-checks exist.
- **Green by:** §5's helpers + router pre-checks (HTTP). The **usage-billing** pre-check (a $ pre-check) is for the **Tier-W mine/import** confirm effects — that is **W4/W11**, NOT W1 (W1's publish/adopt are free operations, only count-gated). W1's row is the **count ceiling**; W11 adds the billing ledger.
- **Why it's load-bearing:** without it an agent loop publishes/adopts unboundedly (the exact `D-MCP-BOOK-CREATE-QUOTA` gap, one tier up).

### H-7 — the corrected single-target clone (no two-ON-CONFLICT mess)
- **Failing test first:** `test_clone_advisory_lock_per_owner` + `test_clone_idempotent` (§6.2) — RED before the single-target INSERT + owner-keyed lock exist.
- **Green by:** §3.1's **one** `ON CONFLICT (owner_user_id, code, language)` target (book tier dropped → no second `ON CONFLICT (book_id, code)` branch) + §3.4's `caller_id`-keyed advisory lock (not the degenerate `hash(NULL)` from a removed book key).
- **Why it's load-bearing:** the original §4.3 draft had a two-target clone (user OR book) with a `hash(book_id)` lock; with the book tier dropped that lock collapses to a global `hash(NULL)` contention point and the second conflict target is dead code. The correction is: one target, one per-owner lock.

(Other blockers — B-1 cross-model-cosine in W3, B-2 both-NULL-write in F0/W1, H-2/H-3 motif_link in F0 — W1 only *honors* B-1 by copy-not-reembed and *exercises* B-2 via `test_create_rejects_system_row`/`test_get_idor`.)

---

## 8. Open micro-decisions + recommendation

| ID | Decision | Options | **Recommendation** |
|---|---|---|---|
| **MD-1** | Does the **catalog list** include roles/beats/conditions? | (a) light list, full body only on `get_visible` of a public row; (b) full body inline in the list | **(a)** — keeps the catalog row light + cheap; the full body is one `GET /motifs/{id}` away (legitimately public). Matches catalog-service's light projection. |
| **MD-2** | `pattern` clone depth | (a) root-only + `members_pending`; (b) root + 1-level `composed_of`; (c) full recursive | **(b)** for W1 (patterns are P1-rare); full recursion lands with W10 arc templates. |
| **MD-3** | `unlisted` semantics in P1 | (a) owner-only staging (no link-share yet); (b) link-share-by-id now | **(a)** for P1 — simpler; `get_visible` predicate stays exactly system|public|owner. Add link-share-by-id in P2 with the W11 sync work. |
| **MD-4** | Quota count basis | (a) `status<>'archived'`; (b) all rows incl. archived | **(a)** — archiving frees quota (the natural "unpublish/cleanup" UX; matches book-service `lifecycle_state='active'`). |
| **MD-5** | `source_ref` opacity scope | (a) opaque on ALL clones; (b) opaque only on imported-derived | **(a)** — strictly safer + simpler (no conditional); the trigger still handles `examples` stripping for imported-derived specifically. |
| **MD-6** | 201 vs 200 on idempotent clone | (a) 200 (existing) vs 201 (new); (b) always 201 | **(a)** — honest about idempotency; the repo returns `(motif, created)` so the router picks the code. |

None of these block the build; all have a recommended default the task list assumes.

---

## 9. Ordered task list

> Build TDD (failing test → impl → green), DB-gated. Each step is small; checkpoint at the risk boundaries noted. Assumes F0 merged (schema + models + `MotifRepo` stub + config + trigger present).

1. **Wire the router skeleton** — `routers/motif.py` with `APIRouter(prefix="/v1/composition")`, the `get_motif_repo`/`get_current_user`/`get_embedding_client_dep` deps, register in `main.py`. Stub all 7 routes returning 501. *(Test: routes mount, 401 without JWT.)*
2. **CRUD reads** — `GET /motifs` (`list_for_caller` + `limit`/`offset`/`q` ILIKE + `total`) and `GET /motifs/{id}` (`get_visible` + `redact_for_viewer`). *(Tests: §6.1 list/get, §6.1 `test_get_idor`.)* — **risk boundary: the read predicate (R1.1) is now load-bearing; verify IDOR before proceeding.**
3. **Create** — `POST /motifs` with `MotifCreate` (`ForbidExtra`), server-stamp owner/source, embed-on-create (mock W3 helper), 409 on dup. *(Tests: §6.1 create/stamp/dup/reject-system.)*
4. **Patch + archive** — `PATCH` (owner-only, `If-Match`, re-embed-on-summary), `DELETE` (soft archive). *(Tests: §6.1 patch-owner-only/system-readonly/if-match/resummary/archive.)*
5. **Quota helpers + pre-checks** — `count_shared_by_owner`/`count_adopted_by_owner` in `motif_repo.py`; wire the publish pre-check into POST/PATCH. *(Tests: §6.4 publish quota.)* — **risk boundary: B-4 publish half done.**
6. **The CLONE primitive** — `clone()` in `motif_repo.py`: the column-enumerated INSERT (§3.1), owner-keyed advisory lock (§3.4), idempotent re-read (§3.3), opaque `source_ref` (§3.5), `(motif, created)` return. Router `POST /motifs/{id}/clone` + the adopt quota pre-check. *(Tests: §6.2 all clone rows + §6.4 adopt quota.)* — **risk boundary: H-7 + B-4 adopt; the biggest single piece — checkpoint/commit here.**
7. **Pattern subgraph clone** — extend `clone()` for `kind='pattern'` (1-level `composed_of`, MD-2(b)), re-point edges at the caller's copies. *(Test: §6.2 `test_clone_pattern_subgraph`.)*
8. **Catalog** — `GET /motifs/catalog` with `_CATALOG_COLS` allow-list, `visibility='public'+active`, sort/filter/paginate. *(Tests: §6.3 all no-leak.)* — **risk boundary: B-3 catalog.**
9. **Publish-strip trigger contract tests** — §6.6 (xfail-until-F0 if needed, else strict). Confirms B-3's strip half.
10. **VERIFY** — run the full `test_motif_router.py` suite green; the W1 eval-gate (§6.5) checklist; **live-smoke** token: `live smoke: clone a seeded system motif → user-tier copy on a real stack-up` (needs F0 schema + W7 seed present; if not bootable, `LIVE-SMOKE deferred to D-MOTIF-W1-LIVE-SMOKE` per the cross-service rule — this WS touches one service so the soft-warning won't even fire, but the R-NODE-P1 reconcile will exercise it).
11. **REVIEW** (2-stage) — spec-compliance (every §R1.3 rule + the reset table) + code-quality (the allow-list is structural, the lock key is `caller_id`, no `SELECT *` anywhere, the opaque token is non-reversible). **Proactively `/review-impl`** — this is tenant-isolation + a clone/copy-down boundary + quota (load-bearing per the audit).
12. **SESSION + COMMIT** — update `docs/sessions/SESSION_HANDOFF.md` (W1 done, any deferred MD rows), commit `routers/motif.py` + the `motif_repo.py` clone/publish methods + `tests/unit/test_motif_router.py` together.

### Disjointness check (no file collisions with sibling WSs)
- `routers/motif.py` — **new**, W1 sole owner.
- `db/repositories/motif_repo.py` — F0 creates, **W1 owns post-foundation** (adds `clone`/`count_*`/embed-write-through to `create`/`patch`). W3 owns the *separate* `motif_retrieve.py`; W4 *imports* `motif_repo` but does not edit it (W4 owns `mcp/server.py` + `routers/actions.py`). **Seam:** W1 + W4 both call `motif_repo`; W1 owns the file, W4 consumes — coordinate the `count_*` helper signatures at F0-freeze so W4 doesn't need to edit the file.
- `tests/unit/test_motif_router.py` — **new**, W1 sole owner.
- `main.py` register line — append-only; if a sibling also appends, a trivial merge (one line each). Flag to F0 to pre-register all motif routers as a stub to avoid even that.
- `db/migrate.py` (the trigger), `db/models.py`, `config.py`, `deps.py` — **F0-owned**, W1 read-only.
