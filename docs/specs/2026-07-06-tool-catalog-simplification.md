# Spec: MCP Tool Catalog Simplification (Group Directory + CRUD Unification)

**Status:** DRAFT (CLARIFY/DESIGN, awaiting PO sign-off on §3 decisions) · **Date:** 2026-07-06 · **Size:** XL (cross-service, contract-shape change)
**Origin:** `docs/eval/context-budget/context-explosion-investigation-2026-07-06.md` (measured: a book-scoped chat pays a flat ~24K-token tool-schema tax per turn, re-sent N+1 times per tool-loop turn, from whole-domain hot-seeding).
**Related:** [[context-budget-law-and-kernel]], [[llm-client-first-tool-refactor]], `docs/plans/2026-07-05-search-tool-unification.md`, `docs/standards/mcp-tool-io.md`

---

## 1. Problem (grounded)

The platform federates **~150-160 MCP tools** across domain services (glossary ~47, composition 56, knowledge 30, translation 12, jobs 5, ...). `find_tools` (chat-service `tool_discovery.py` / ai-gateway `find-tools.ts`) already implements lazy discovery — a flat token-overlap/fuzzy search over the whole catalog, returning `{name, description}` only, with matched tools activated (full schema) on the next pass. This is sound and already shipped.

Two concrete gaps remain, confirmed by direct code/tool audit on 2026-07-06:

**(A) No group/domain structure is exposed to the model.** `find_tools` searches all ~150 tools flat; the model has no map of what domains exist, so a surface's skill resorts to *hot-seeding an entire domain's tool schemas* to guarantee its own skill works without a discovery round-trip (`tool_discovery.py:131,137` — `_BOOK_SCOPED_HOT_DOMAINS = {glossary, story}`, `_STUDIO_HOT_DOMAINS = {glossary, composition, story}`). Glossary alone is 47 tools; this is the measured 24K-token flat tax.

**(B) Search is not unified — but is already 80% fixed.** Audit found 5 federated search tools: `story_search` (manuscript hybrid: lexical+semantic+graph, canonical, hot-seeded), `memory_search` (delegates its chapter leg to the same engine as of `docs/plans/2026-07-05-search-tool-unification.md`, kept registered but find_tools-lazy and description-redirected to `story_search`), `glossary_search` (Postgres entity search — distinct corpus), `glossary_web_search` (external web — distinct corpus), `composition_motif_search` (motif library — distinct corpus). The redundant pair (`story_search`/`memory_search`) is already engine-unified; a **hard removal/alias of `memory_search`** was consciously deferred in that plan ("wide blast radius — FE i18n/labels, public-gateway policy, many tests"). The other three are genuinely different corpora, not duplicates — they are not consolidation candidates.

**(C) Glossary's 47 tools include real CRUD duplication ripe for unification.** Full inventory (this spec's audit):
- **15 pure CRUD tools** across **3 tenancy tiers** (book / user / system-admin — see `docs/CLAUDE.md` § User Boundaries & Tenancy): `glossary_book_create/patch/delete` (3), `glossary_user_create/patch/delete` (3), `glossary_admin_propose_create/patch/delete` (3, on the separate `/mcp/admin` server), plus `glossary_book_set_active_genres`, `glossary_book_set_kind_genres`, `glossary_propose_new_entity`, `glossary_entity_set_genres`, `glossary_create_chapter_link`, `glossary_create_evidence` (6 single-resource writes).
- **18 propose→confirm action tools** (mint a confirm token consumed by the shared `confirm_action` core tool) — a different, already-shared-executor pattern, out of scope here.
- **14 pure reads** (4 GET, 9 LIST, 1 SEARCH) — not in scope.
- **Batch (`items[]`) is already a proven, shipping pattern** — but only in the propose-action tier (`glossary_propose_batch` ops[], `glossary_propose_kinds` kinds[], `glossary_book_sync_apply` items[], `glossary_propose_status_change` entity_ids[], `glossary_propose_merge` loser_ids[], `glossary_propose_translation`/`glossary_propose_aliases` items[]). The direct-CRUD tier (book/user/admin create/patch/delete) is **strictly single-item today** — no batch support at all.

---

## 2. Goals / Non-goals

**Goals:**
- Cut the fixed per-turn tool-schema tax for book-scoped/studio surfaces from whole-domain hot-seeding to a near-zero-cost pointer, without regressing the "surface skill must work without a discovery round-trip" guarantee that motivated hot-seeding in the first place.
- Reduce glossary's direct-CRUD tool count via scope-level consolidation, and add batch support to the direct-CRUD tier (matching the already-proven `items[]` convention used elsewhere in the same service).
- Preserve every invariant in `docs/standards/mcp-tool-io.md` (IN-1..8, OUT-1..6) and the tenancy-tier boundary (system-tier writes stay admin-server-only, never merged into a user-facing tool).

**Non-goals (this pass):**
- Consolidating the 18 propose→confirm action tools (separate track — they already share the `confirm_action` executor; unifying their *schemas* is a distinct, larger design).
- Merging `glossary_search` / `composition_motif_search` / `glossary_web_search` into `story_search` or each other — different corpora, not duplicates.
- Hard removal of `memory_search` — already tracked as a conscious deferral in `docs/plans/2026-07-05-search-tool-unification.md`; this spec only carries that item forward, doesn't redesign it.
- Composition (56 tools), knowledge (30), translation (12) unification — glossary is the pilot; those are follow-on tracks once this pattern is validated.

---

## 3. Decisions requiring PO sign-off before PLAN

### 3.1 RESOLVED — upsert (create+update) via implicit discriminator; delete stays separate

Original proposal was "make create/update/edit one tool, single or batch." Cross-checked against external practice — Anthropic's own tool-design guidance (consolidate around workflows, not blanket CRUD), the STRAP pattern (96→10 tools via resource+action, reports near-zero tool-selection errors), and the Six-Tool Pattern's **upsert** trick (merge insert+update via presence of an id/version, no explicit action enum needed) — plus a re-check of our own schemas:

**Decision:** merge `create`+`update` into one **upsert** tool per scope, using the field the two tools already discriminate on — `base_version` **absent ⇒ create**, **present ⇒ optimistic-lock update**. No `action` enum to get wrong, and both branches share the same required-field shape (`level, code, +fields`) — this avoids the "differing required-fields per branch" problem a create/delete merge would hit.

**Delete stays a separate tool** — not a hedge, but a *confirmed* finding: re-auditing the schemas shows `glossary_book_delete` mints a confirm token ("mint confirm to soft-delete") while `glossary_user_delete` executes directly (a reversible soft-delete via `glossary_user_restore`). Folding delete into the same tool as create/update would either force user-tier deletes to start requiring confirmation they don't need today, or hide the book-tier confirm-requirement behind a branch the model can't see coming — exactly the failure mode the new `mcp-tool-io.md` CAT-2 rule (added this pass) now names explicitly: a merge across tools with different safety/confirm behavior must branch explicitly and get its own test per branch, never assume uniformity.

**Net:** 6 direct-write tools (`book_create/patch`, `user_create/patch`, `book_delete`, `user_delete`) → **2 tools** (`glossary_ontology_upsert`, `glossary_ontology_delete`), both batch-capable via `items[]` — a bigger cut than the original 6→3 proposal, reached by consolidating strictly along axes that don't cross a safety-behavior boundary. Exact schemas in §6.

### 3.2 Admin tier stays out of the merge (hard boundary, not a choice)

`glossary_admin_propose_create/patch/delete` live on the separate `/mcp/admin` server, never exposed on the main `/mcp` endpoint (INV-T6) — this is how "admin-only" write access is structurally enforced (per `docs/CLAUDE.md` § User Boundaries & Tenancy: system-tier rows are admin-managed, never user-mutable). Merging admin-tier tools into the same tool as book/user tiers would require the tool to live on both servers or take a scope value a non-admin caller could pass — a tenancy violation. Admin tools may independently gain `items[]` batch (cheap, no merge) as a low-priority follow-on; they do **not** merge with book/user tools.

### 3.3 RESOLVED (2026-07-06) — entity batch: build now; set_genres/chapter_link/evidence: still unconfirmed

`glossary_propose_new_entity`, `glossary_entity_set_genres`, `glossary_create_chapter_link`, `glossary_create_evidence` act on 4 different resource shapes (entity, genre-override, chapter-link, evidence) — not clean merge candidates with each other, so this is 4 independent batch decisions, not one.

**Decision:** PO confirmed bulk entity creation is a real near-term need (a KG-extraction-style pipeline minting many entities per pass). Shipped: `glossary_propose_entities` (`services/glossary-service/internal/api/entity_batch_tools.go`) — the batch-capable sibling of `glossary_propose_new_entity`, following the SAME playbook as §6/§7 (one new tool, `items[]` 1-50, per-item independent results, old tool tagged `_meta.visibility:"legacy"` rather than deleted). No CAT-1 discriminator needed (create-only, no update/delete branch to design). Reuses `proposeNewEntity` per item — the EXACT core the superseded tool calls — so a batch-created entity is indistinguishable from a singly-created one. 3 new integration tests (mixed new+dedup, unknown-kind per-item error, empty-items rejection); the CAT-4 drift-lock test (`TestLegacyToolsCarryVisibilityMeta`) extended to cover the newly-legacy-tagged tool. While touching `glossary_propose_new_entity`'s registration, also corrected a latent gap: it had no `_meta.tier` at all (defaulting to "R"/read despite being a direct write) — now correctly "A".

`glossary_entity_set_genres`, `glossary_create_chapter_link`, `glossary_create_evidence` remain **unconfirmed** — no near-term caller identified for batching any of these; revisit only when one appears (defer-gate #4: genuinely blocked on a concrete future need, not "missing infrastructure").

---

## 4. Design — Part A: Tool Group Directory

Replace whole-domain hot-seeding with a static, near-zero-cost **group index** injected as plain text (not tool schemas) alongside `ALWAYS_ON_CORE`:

```
GROUP_DIRECTORY = {
  "glossary": "Lore entities (characters/locations/items/kinds) — CRUD + wiki + standards ontology.",
  "story":    "Manuscript search + chapter reads (story_search, book_get_chapter).",
  "composition": "Outline/scene/canon planning — PlanForge, Story Grid rules.",
  "knowledge": "Derived KG facts (Neo4j-backed), passage retrieval, memory_search.",
  "translation": "Job-based chapter/book translation pipeline.",
  ...
}
```

- Injected as text in the surface's system prompt (~15-20 entries × ~1 line ≈ 300-500 tokens total, vs. ~24K for a hot-seeded domain).
- `find_tools` gains an optional `group` enum arg (closed-set, registered per IN rules) to scope the fuzzy search to one group — improves precision over today's fully-flat 150-tool search.
- A surface's skill references the group name instead of relying on hot-seeded schemas; `story` stays hot per the existing measured justification (`tool_discovery.py:126-130` — a weak model reaching for `memory_search` and punting instead of discovering `story_search`), since that's a *specific, already-measured* exception, not the general case.
- **Net effect:** book-scoped surfaces drop from ~24K hot tool-schema tokens to ~500 (directory text) + `story_search`'s own schema (small, single tool) — directly fixes Root Cause A from the investigation doc.

This part is additive (new optional param, no existing contract broken), lowest-risk, and should ship first regardless of the §3 decisions.

**Reconciled 2026-07-06:** a separate commit (`dda88c0dd fix(context): tame chat-service context explosion`) landed independently and already token-budgets the hot-seed (`tool_surface.budget_names_by_tokens`, `HOT_SEED_TOKEN_BUDGET=4000`) — read/query tools first, ascending schema size, `find_tools` backstops the tail. That caps the acute 24K bug at ≤4K by a different mechanism (smart selection within a token budget) than this spec's original "curated subset + text pointer" proposal. **Both now ship together, complementary, not conflicting:** `hot_tool_names()` (the candidate pool `budget_names_by_tokens` draws from) now also excludes `legacy`-tagged tools (CAT-4, §7), and `GROUP_DIRECTORY`/`group_directory_text()` remain a cheap, separate discovery-precision aid on top — giving the model an explicit domain map and letting `find_tools` scope its search, independent of which specific tools the token-budget happened to keep hot this turn. `group_directory_text()` injection into the actual system-prompt assembly is the one remaining wiring step (not yet done — see §10).

---

## 5. Design — Part B: Search (status, not new design)

No new design needed here — carry forward the existing, already-approved plan:
- `story_search` remains canonical and hot on book-scoped/studio surfaces.
- `memory_search`'s hard removal/alias stays a tracked, consciously-deferred item (per `docs/plans/2026-07-05-search-tool-unification.md` "Out of scope" section) — this spec does not reopen that decision, only notes it belongs on the same Deferred list this spec's other items land on.
- `glossary_search`, `glossary_web_search`, `composition_motif_search` are confirmed genuinely distinct corpora — no consolidation action.

---

## 6. Design — Part C: Glossary CRUD Unification (pilot) — concrete schemas

| Before (6 tools, single-item only) | After (2 tools, single-or-batch) |
|---|---|
| `glossary_book_create`, `glossary_book_patch`, `glossary_user_create`, `glossary_user_patch` | `glossary_ontology_upsert` |
| `glossary_book_delete`, `glossary_user_delete` | `glossary_ontology_delete` |

**`glossary_ontology_upsert`**
```json
{
  "name": "glossary_ontology_upsert",
  "description": "Create or update book- or user-tier ontology rows (genre, kind, or attribute) — one call may mix creates and updates freely. Omit base_version on an item to create it; include the current base_version to update it with optimistic locking. Accepts 1-50 items; each item succeeds or fails independently (not all-or-nothing).",
  "_meta": { "tier": "A", "synonyms": ["add a kind", "add a genre", "add an attribute", "edit a kind", "rename a kind", "new entity type"], "visibility": "discoverable" },
  "inputSchema": {
    "type": "object",
    "properties": {
      "scope": { "type": "string", "enum": ["book", "user"], "description": "Which tenancy tier to write to." },
      "book_id": { "type": "string", "description": "Required when scope=book; omit when scope=user." },
      "items": {
        "type": "array", "minItems": 1, "maxItems": 50,
        "items": {
          "type": "object",
          "properties": {
            "level": { "type": "string", "enum": ["genre", "kind", "attribute"] },
            "code": { "type": "string" },
            "name": { "type": "string" },
            "base_version": { "type": "string", "description": "Omit to create; include to update." },
            "fields": { "type": "object", "description": "Level-specific fields (e.g. a kind's attribute list, an attribute's field_type)." }
          },
          "required": ["level", "code"],
          "additionalProperties": true
        }
      }
    },
    "required": ["scope", "items"],
    "additionalProperties": false
  }
}
```
Output (bare payload, OUT-4; per-item results, CAT-3):
```json
{
  "results": [
    { "code": "protagonist", "level": "kind", "status": "created", "version": "1" },
    { "code": "magic_system", "level": "kind", "status": "error", "error": "base_version mismatch — row was changed since you read it, re-fetch and retry" }
  ],
  "summary": { "created": 1, "updated": 0, "failed": 1 }
}
```

**`glossary_ontology_delete`** — CAT-2 applies: the confirm-behavior genuinely differs by `scope`, stated explicitly in the description and tested per-branch.
```json
{
  "name": "glossary_ontology_delete",
  "description": "Delete book- or user-tier ontology row(s). scope=book mints a confirm token — a human must approve before the delete executes; returns {confirm_token, preview}. scope=user executes immediately as a reversible soft-delete (undo via glossary_user_restore); returns {results}. Deleting an already-deleted row is a no-op, not an error.",
  "_meta": { "tier": "W", "synonyms": ["remove a kind", "delete a genre", "trash an attribute"], "visibility": "discoverable" },
  "inputSchema": {
    "type": "object",
    "properties": {
      "scope": { "type": "string", "enum": ["book", "user"] },
      "book_id": { "type": "string", "description": "Required when scope=book." },
      "items": {
        "type": "array", "minItems": 1, "maxItems": 50,
        "items": {
          "type": "object",
          "properties": { "level": { "type": "string", "enum": ["genre", "kind", "attribute"] }, "code": { "type": "string" } },
          "required": ["level", "code"],
          "additionalProperties": false
        }
      }
    },
    "required": ["scope", "items"],
    "additionalProperties": false
  }
}
```
Output when `scope=book`: `{"confirm_token": "...", "preview": [{"level": "kind", "code": "..."}]}`
Output when `scope=user`: `{"results": [{"level": "kind", "code": "...", "status": "trashed"}], "summary": {"trashed": 1, "failed": 0}}`

**Both tools** register `scope` and `level` in `CLOSED_SET_ARGS` (IN-3); `book_id` requiredness is validated server-side, not left to prose (IN-4/IN-2 pattern).

**Out of this pilot slice:** `glossary_book_set_active_genres`/`glossary_book_set_kind_genres` (delta add/remove, different shape) and the 6 single-resource writes (entity/link/evidence/genre-override) — left as-is pending §3.3. Admin tier (`glossary_admin_propose_*`) may independently gain `items[]` batch later, no merge, no tool-count change (still a separate server, per §3.2).

---

## 7. Design — Part D: legacy tool visibility + manual GUI injection

Answers the "keep old tools, or rebuild everything" question directly: **neither literally — keep old tools registered and working, but hide them from the LLM by default; the new tools become the only ones the model can discover.** This is CAT-4 in the updated `mcp-tool-io.md` standard, applied concretely to this pilot.

1. **Tag, don't delete.** The 6 superseded tools (`glossary_book_create/patch/delete`, `glossary_user_create/patch/delete`) keep their existing schemas and behavior, untouched — any existing caller (older FE build, a test, another service) keeps working with zero migration risk. Each gets `_meta.visibility: "legacy"` added to its registration (mirrors how `tool_tier`/`tool_meta` already read `_meta` today), e.g.:
   ```json
   { "name": "glossary_book_create", "description": "…(unchanged)… NOTE: superseded by glossary_ontology_upsert — kept for existing callers only.",
     "_meta": { "tier": "A", "visibility": "legacy" } }
   ```
   The description gets one appended sentence pointing at the replacement — cheap insurance for the pin-and-confuse edge case in §8.9. `glossary_book_set_active_genres`/`glossary_book_set_kind_genres` are **NOT** tagged legacy — they aren't superseded by anything in this pass, despite sharing the `glossary_book_*` prefix with tools that are; tagging by prefix instead of by tool identity is the mistake to avoid here.
2. **Discovery exclusion, both surfaces.** `search_catalog()` (chat-service `tool_discovery.py`) and `searchCatalog()` (ai-gateway `find-tools.ts`) each add one filter: skip any tool with `_meta.visibility == "legacy"`. They must change together — the header comments in both files already document they must stay in lockstep. `hot_tool_names()` gets the same exclusion so a legacy tool is never hot-seeded even if its domain is.
3. **Net effect:** `find_tools "create a new kind"` surfaces `glossary_ontology_upsert` — never `glossary_book_create`. A legacy tool is unreachable through any normal agent action, confirming "if find_tools finds them [the new tools], the LLM uses them" — the old ones simply aren't in that search space at all.
4. **Manual injection is the only path back to a legacy tool**, and it's a **Settings & Configuration Boundary**-governed per-session choice (SET-1 — this is a user decision, not a platform toggle):
   - A new **per-session** field, e.g. `pinned_legacy_tools: string[]` — session-scoped (finest tier: a user wants the old tool for *this* conversation, not a standing account preference).
   - Small GUI affordance (an "Advanced tools" entry in the session's settings) listing every `legacy`-tagged tool by name + description, each with an enable-for-this-session toggle. The pinnable set is server-sourced from the real catalog (SET-6 closed-set), never free text.
   - Enabling one **unions it into the session's existing `activated_tools` set** — the same mechanism `find_tools` already writes to — tagged `source: "user_pinned"` instead of `source: "find_tools"` (SET-8: reuse the existing per-session activation store, don't invent a parallel one). Its full schema then rides subsequent turns exactly like a normally-activated tool.
   - Wherever the session shows its active tools, show *why* each is active — "you enabled this" vs. "the agent found this" (SET-4: no silent/unobservable default).
   - Persisted server-side on the session row (SET-7), not localStorage.

**Open (flag for PLAN):** per-session-only pinning, or also a per-user default ("always show me the old glossary tools")? Recommend **per-session only** to start — matches "manually inject" as a deliberate, scoped act, and avoids building a broader preference cascade before there's real repeat demand for it.

---

## 8. Edge cases (resolved this pass)

Self-review before BUILD, per this repo's mandatory second-pass-review convention. Grouped by which piece they land on; each has a decided resolution, not left open.

**`glossary_ontology_upsert`**

8.1 **Mixed create+update in one batch call is explicitly allowed** — each item is evaluated independently by its own `base_version` presence; the tool is not "all-create" or "all-update" per call. State this in the description (done above) so the model doesn't infer a whole-batch mode.

8.2 **Duplicate `(level, code)` within one call is rejected per-item**, not processed in a first-wins/last-wins order — an ordering-dependent result is a silent footgun. That item's result is `{status:"error", error:"duplicate level+code in this batch — split into separate calls"}"`; the rest of the batch still proceeds.

8.3 **Batch is NOT one DB transaction.** Each item executes and commits independently (matches CAT-3's per-item-results contract) — a naive "wrap the whole batch in one transaction" implementation would silently roll back N-1 good writes when item N fails, which is exactly the all-or-nothing behavior CAT-3 forbids. Call this out explicitly in the Go handler's implementation notes at BUILD time.

8.4 **`base_version` omitted but the row already exists** → per-item error distinct from a version mismatch: `{status:"error", error:"already exists — include base_version to update it"}`. **`base_version` present but no such row exists** → a different, distinguishable error: `{status:"error", error:"no such row — omit base_version to create it"}`. Two different self-correcting directives (IN-6) for two different mistakes, not one generic "invalid."

8.5 **`book_id` supplied when `scope=user`** is tolerated and ignored (IN-5 harmless-extra rule), not rejected — a model that always includes `book_id` out of habit shouldn't get a hard failure. **`book_id` missing when `scope=book`** is a one-line rejection naming the missing field (IN-6).

8.6 **The `fields` object is intentionally open** (no per-`level` conditional schema) because genre/kind/attribute need different sub-fields and JSON Schema's `if/then` conditionals are unreliable across function-calling backends — the same shape-heterogeneity concern that ruled out an `action` enum applies one level down here too. Accepted tradeoff: the server validates `fields` per `level` and returns a **per-item, field-naming** self-correcting error (IN-6) — e.g. `"attribute level requires fields.field_type"` — so the model can fix and retry even though the schema itself couldn't statically enforce it. This residual risk is exactly what the comprehension eval (next step) should stress-test.

8.7 **`maxItems: 50` is a placeholder, not a final number** — set low enough to bound worst-case payload size, but not yet tuned against real batch sizes (e.g. KG-extraction bulk-creating dozens of entities) or against the point where a weak local model's batch construction quality degrades. Revisit after the eval measures actual batch sizes requested and error rates by batch size.

**`glossary_ontology_delete`**

8.8 **One confirm token covers the whole batch** when `scope=book` — matches the existing precedent (`glossary_propose_batch`, `glossary_propose_merge` already gate a multi-item operation behind one token). At redeem time, results are still **per-item** (8.3's independent-execution rule applies at confirm-time too) — a concurrent edit between propose and confirm can make one item fail while others succeed; the redeem response must reflect that per-item, not fail the whole redemption. Deleting an already-trashed/already-deleted row returns `{status:"already_trashed"}`, not an error (idempotent delete).

8.9 **`_meta.tier` is one value covering two behaviorally-different branches** (book=confirm-gated, user=direct) — since tier metadata is per-tool, not per-branch, pick the more cautious bucket, `"W"` (write/confirm), uniformly. The actual confirm requirement is enforced server-side regardless of what the consumer-side tier says, so the worst case of this choice is the user-tier branch getting slightly more cautious UI/undo-hint treatment than strictly necessary — never the reverse (a real gap in confirm-gating). Documented in the schema's `_meta` above.

8.10 **Legacy tool pinned alongside the new tool = reintroduced ambiguity, mitigated not eliminated.** If a user manually pins `glossary_book_create` in a session that also has `glossary_ontology_upsert` active, the model now faces the exact "two similar tools" confusion the whole redesign exists to avoid — deliberately, for that one session. Mitigation: the legacy tool's description carries an explicit "superseded by X, prefer that unless you need this exact shape" pointer (§7.1) — doesn't eliminate the ambiguity, but gives the model a tie-breaker. Accepted as a known cost of the escape hatch, not solved further this pass.

8.11 **A pinned tool name that's later actually removed** (not this pass, but a future cleanup) must fail gracefully — surfaced as an "unavailable" signal (the same H10 pattern `provider_availability()` already uses for a down provider), never a hard crash on a stale pinned name. Not an issue today since nothing is being deleted, but worth stating now so a future removal doesn't skip it.

**Group directory (Part A)**

8.12 **Directory drift.** `GROUP_DIRECTORY` is hand-authored text; if a new tool-name-prefix/domain is federated later and nobody updates the map, that domain silently has no discovery pointer — the same class of drift the SDK-First/scope-separation standards already guard against elsewhere. Add a cheap test: every distinct tool-name-prefix present in the live catalog must have a `GROUP_DIRECTORY` entry or an explicit `_IGNORED_PREFIXES` allowlist entry — fails loud on an orphaned domain instead of silently degrading discovery.

8.13 **The glossary group-directory entry and the new tools' descriptions/synonyms need to actually say "batch, upsert, create-or-update"** now that the underlying tool changed shape — an easy thing to forget since the directory text is separate from the tool schema. Tracked as a required BUILD step, not assumed automatic.

---

## 9. Governance / contract constraints (must hold)

- Every consolidated tool's schema must satisfy `docs/standards/mcp-tool-io.md` IN-1..8 (closed-set enums, `extra`/`additionalProperties` discipline, bounds in schema not prose, one canonical arg name) and OUT-1..6 (reference-first, honest partiality on bounded batch results, bare-payload success / `{success:false,error}` failure shape).
- Whatever schema-source-of-truth mechanism glossary-service (Go) uses for its MCP tool defs must be updated in lockstep across every source that mirrors it — this exact class of bug already hit knowledge-service (`knowledge-mcp-three-schema-sources-fastmcp-strips` memory: 3 schema sources, one strips silently) — audit glossary-service's equivalent sources before BUILD, don't assume there's only one.
- Tenancy: the `scope` enum on the merged tools must not let a non-admin caller reach the admin tier — verified by a live test that a `scope="admin"`-shaped request is rejected/impossible (the enum itself should only ever contain `book`/`user`).
- A batch call must return **per-item** results (which of N items succeeded/failed), not an all-or-nothing opaque success — matches OUT-5 (honest partiality) and avoids a batch failure silently discarding N-1 successful writes.

---

## 10. Rollout sequencing

0. **Comprehension eval — DONE 2026-07-06.** `docs/eval/tool-catalog-comprehension-2026-07-06.md`. Ran the real target model (Gemma-4 26B-A4B QAT, `tool_calling:true`) through the real provider-registry streaming endpoint against the two new schemas (stub backend, no real writes) across 12 scenarios covering the model-facing §8 edge cases (mixed batch 8.1, base_version create/update discrimination, scope selection 8.5, delete branch-by-scope 8.8/8.9, open `fields` bag 8.6, batch sizes 3/5 at 8.7, no-hallucinated-legacy-tool 8.10). **Result: 12/12 PASS** — argument construction needs no schema changes. **But the offline `search_catalog()` check found CAT-4 is load-bearing, not optional**: with the 6 legacy tools still in the catalog, `glossary_ontology_upsert` loses the discovery-ranking race to `glossary_book_create`/`glossary_user_create` on every tested query (ranks 3rd, not 1st) *despite* the `_meta.synonyms` added specifically to help it — description/synonym tuning alone was insufficient. Confirms §7's legacy-visibility filter must ship in the same pass as the new tools, not as a follow-on.
1. **CAT-4 + Part A schema/filter layer — DONE 2026-07-06.** Shipped this pass:
   - `sdks/go/loreweave_mcp/meta.go`: added `Visibility`/`MetaKeyVisibility`/`WithVisibility` (additive, backward-compatible with existing `NewToolMeta` callers).
   - Tagged all 6 superseded glossary tools `_meta.visibility:"legacy"` + a "superseded by X" description sentence (`book_tools.go`, `user_tools.go`); `glossary-service` builds and its existing `internal/api` test suite is green.
   - `tool_discovery.py` (chat-service): `tool_visibility()`/`is_legacy_tool()`, `search_catalog()`/`hot_tool_names()` exclude legacy tools unconditionally, `GROUP_DIRECTORY` + `group_directory_text()` + `group` param wired into `FIND_TOOLS_TOOL`'s schema and into `stream_service.py`'s find_tools call site.
   - `find-tools.ts` (ai-gateway): mirrored `toolVisibility()`/`isLegacyTool()`/`providerPrefix()`, `searchCatalog()`/`findToolsResult()` take the same `group`/legacy-exclusion, wired into `handlers.ts`'s `handleFindTools`.
   - Tests: 12 new Python tests (`test_tool_discovery.py`) covering legacy-exclusion, group scoping, and the directory itself — reproduces the eval's exact finding (legacy tool would out-rank the new one without CAT-4) as a permanent regression test. Existing ai-gateway `find-tools.spec.ts` (11 tests) and chat-service's tool-discovery/tool-surface/stream-tools suites (103 tests) all green, no regressions.
   - **Wiring completed 2026-07-06 (next slice):** `group_directory_text()` is now injected as a tail-block in `stream_service.py`'s system-message assembly (gated on `stream_format=="agui" and not disable_tools and kctx.tool_calling_enabled` — only worth the tokens when tool-calling is actually live), ordered after the L1 skill-catalog block and before `book_context_note`. A live regression test (`test_stream_service_story04.py::test_group_directory_rides_the_system_prompt_when_tools_are_live`) asserts the directory text actually rides a real `stream_response()` system message, not just that the schema/filter side works. Note: this specific file edit landed inside a CONCURRENT session's commit (`dbc5c0b31`, an unrelated stateful-chain-management feature) because the file had zero further diff from HEAD by the time of staging — a benign provenance mix from the shared checkout, not a conflict; the code and its test are correct and verified independently.
2. **Part C — `glossary_ontology_upsert`/`glossary_ontology_delete` Go handlers — DONE 2026-07-06.** `services/glossary-service/internal/api/ontology_tools.go` (new file). Pure orchestration, no duplicated business logic:
   - **Upsert** dispatches per item by `scope` then by `base_version` presence to the EXACT same cores the legacy tools use: `createBookGenreCore`/`createBookKindCore`/`createBookAttributeCore` + `resolveBookPatch`/`bookRowVersions`/`compareBaseVersion`/`applyBookUpdate` for `scope=book`; `createUserGenreTool`/`createUserKindTool`/`createUserAttrTool` + `patchUserGenreTool`/`patchUserKindTool`/`patchUserAttrTool` for `scope=user`. Duplicate `(level,code)` in one call rejected up front (§8.2); per-item independent errors distinguish create-when-exists from update-when-missing (§8.4).
   - **Delete**, `scope=user`: direct per-item soft-delete reusing `toggleUserTrash`, idempotent (`already_trashed` status, not an error — §8.8).
   - **Delete**, `scope=book`: a NEW descriptor `descBookDeleteBatch` + `bookDeleteBatchParams{Items}` mints ONE confirm token for the whole batch, mirroring the already-proven `descSchemaCreateKinds`/`effectSchemaCreateKinds` per-item-independent idempotent-skip pattern in `action_confirm.go` — an item already gone since propose is skipped, not failed (verified with a dedicated partial-replay test). Registered in `liveDescriptor()` and both `dispatchConfirmEffect`/`dispatchPreviewEffect` switches.
   - `_meta.tier` for delete is `"W"` uniformly per §8.9 (the more cautious bucket, since one branch is confirm-gated and the other isn't).
   - **Tests:** 8 new integration tests (`ontology_tools_test.go`) against the real `glossary_test` Postgres DB — create-all-levels, mixed create+update batch, duplicate-code rejection, update-when-missing/create-when-exists per-item errors, user-scope create+update, user-scope idempotent delete, book-scope batch delete through a REAL confirm→redeem round-trip (token executes both items, single-use replay 422), and the partial-replay idempotency case (one valid + one already-gone target in the same batch, confirm still succeeds). All 8 pass. Full `go build ./...` clean; full suite green except one pre-existing, unrelated failure (`TestFK_WikiArticle_RestrictsEntityDelete`, a wiki-article FK constraint check — reproduces in total isolation with none of this session's code involved).
3. **`pinned_legacy_tools` per-session manual-injection setting — DONE 2026-07-06.**
   - **Backend:** new `pinned_legacy_tools TEXT[]` column on `chat_sessions` (migrate.py); `PatchSessionRequest`/`ChatSession` carry it; PATCH validates against the LIVE catalog (SET-6 closed-set — `tool_discovery.unknown_pinned_legacy_names()`), rejecting an unknown/non-legacy name with a 422 naming exactly which names were bad (IN-6), never a silent drop. `tool_discovery.legacy_tools_catalog()` is the server-sourced feed; `GET /v1/chat/tools/catalog` gained a `visibility` query filter (default now EXCLUDES legacy — closes a latent gap where the curated `enabled_tools` picker could already surface a superseded tool; `?visibility=legacy` is the dedicated feed for the new picker).
   - **Design deviation from §7.4's literal text, kept deliberately:** rather than "union into `activated_tools` tagged `source:user_pinned`" (no per-item source tagging exists on that list today — would've meant restructuring a plain `list[str]` into `list[{name,source}]`, a much bigger and unrelated change), `pinned_legacy_tools` is a SEPARATE session column, unioned into the advertised set in `tool_surface.discovery_seed_for_surface()` regardless of curated/auto mode (`SessionToolPins.pinned_legacy`). This matters: unioning into `enabled_tools` instead (the existing curated-pin list) would have flipped the WHOLE session into curated mode the moment one legacy tool was pinned — an oversized side effect for what's meant to be a scoped escape hatch. Provenance ("you enabled this" vs "the agent found this", SET-4) comes for free structurally (which list a name is in), no per-item tag needed.
   - **Frontend:** `ToolSkillAddModal`'s Tools tab gained a collapsed "Advanced tools" section (own fetch of `?visibility=legacy`, own toggle, "legacy" badge per row) — collapsed by default so it doesn't compete with the primary discovery flow; picking one calls a separate `onAddLegacyTool` callback, never `onAddTool`. `AgentContextRack` renders a pinned legacy tool as its own amber-tinted chip with a distinct remove callback and a "you enabled this" tooltip. `useContextRack` exposes `pinnedLegacyTools`/`addPinnedLegacyTool`/`removePinnedLegacyTool`, PATCHing `pinned_legacy_tools` on its own debounce, separate from the `enabled_tools` PATCH.
   - **Tests:** 4 new Python tests (`unknown_pinned_legacy_names`/`legacy_tools_catalog` in `test_tool_discovery.py`), 3 PATCH-validation tests + 1 catalog-visibility-filter test in the router suites, 1 `tool_surface` test proving the union rides BOTH curated and auto mode, plus a `resolve_session_tool_pins` degrade test (no column on the row → `[]`, never a crash). FE: 4 new `useContextRack` tests (separate-PATCH proof, remove, limit-refusal), 4 new `ToolSkillAddModal` tests (hidden without the callback, collapsed→expand, correct callback routing, existing-pin exclusion), 4 new `AgentContextRack` tests (distinct chip, distinct remove, no-button-without-callback, counts toward "has pins"). Full chat-service suite: 0 regressions from this slice (a PRE-EXISTING, unrelated `UnboundLocalError: _chain_reason` in `_emit_chat_turn`'s plain-gateway branch was found during the full-suite run — traced to the concurrent session's own newly-committed stateful-chain code, `dbc5c0b31`, not this slice; flagged to the user rather than fixed, since it's a different feature's actively-changing file). Full FE chat suite: 577/577 passed; `tsc --noEmit` clean.
   - **Deliberately out of this slice:** propagating the 3 new i18n keys (`rack.advanced_tools`, `rack.advanced_tools_hint`, `rack.legacy_pin_tooltip`) to the other 17 locale files via `scripts/i18n_translate.py` — added to `en/chat.json` only. The feature works correctly in every locale today via each `t()` call's inline `defaultValue` (the established pattern this file already uses throughout); the batch-translate run is a cheap, mechanical follow-up, not a functional gap.
4. Any FE surface naming the old 6 legacy tools directly (not yet audited).
5. **Verify (remaining):** cross-service live-smoke of the new tools through the real chat agent + a before/after token measurement on the book-scoped scenario the investigation doc used.
6. Composition/knowledge/translation unification are separate follow-on specs once this pilot's pattern is validated in production use — not committed to in this spec.

---

## 11. Open questions — ALL RESOLVED 2026-07-06

1. ~~Confirm §3.1~~ — **RESOLVED**: upsert (create+update via `base_version` presence) + separate delete, 6→2 tools (§3.1, §6).
2. ~~Confirm §3.3~~ — **RESOLVED**: entity batch is a real near-term need (PO-confirmed) — `glossary_propose_entities` shipped. `entity_set_genres`/`chapter_link`/`evidence` batching stays unconfirmed, deferred until a concrete caller appears (§3.3).
3. ~~Should `memory_search` hard-removal be pulled into this spec's Deferred tracking~~ — **RESOLVED: no.** It stays solely owned by `docs/plans/2026-07-05-search-tool-unification.md` — that plan is the single source of truth for that deferral; duplicating it into this spec's tracking would create a second row for the same item with no new information, exactly the "second source of truth that drifts" pattern `docs/standards/README.md`'s own maintenance rule warns against. This spec only cross-references it (§1B, §5).
4. ~~Any objection to `story` staying hot~~ — **RESOLVED: no objection, keep as shipped.** `_BOOK_SCOPED_HOT_DOMAINS`/`_STUDIO_HOT_DOMAINS` still include `story` today, unchanged by this spec's Part A/D work; the measured justification (Dracula eval — `story_search` ranked 7th/missed via `find_tools`) still holds and no counter-evidence has emerged since.
5. ~~§7: per-session-only legacy-tool pinning, or also a per-user default?~~ — **RESOLVED: per-session only, as shipped.** `pinned_legacy_tools` is a `chat_sessions` column (session-scoped), no per-user default cascade was built. Revisit only if real repeat-pin demand across sessions actually appears — no such signal yet.
6. ~~§8.7: is `maxItems: 50` reasonable?~~ — **RESOLVED: accept 50 as shipped, revisit only on evidence.** The comprehension eval tested sizes 3/5 (not near 50) and found no construction-quality degradation; 50 remains a soft ceiling bounding worst-case payload size, not a tuned product number. Revisit if real usage data shows either weak-model degradation before 50, or a genuine need for larger batches (the same trigger as item 2's `entity_set_genres`/etc. — if those ever get built with real bulk-KG-extraction volume, re-measure then).
