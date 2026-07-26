# Glossary MCP Catalog Unification — Design Spec

**Status:** DESIGN (checkpoint) · **Date:** 2026-07-22 · **Branch:** `feat/frontend-tools-mcp-migration`
**Precedent:** the book MCP tool redesign (`8f0e40d4e` spec → `adec30a4b` deprecate → `656f6c105` unify).
Same playbook, applied to the glossary domain.

---

## 1. Problem

The glossary `/mcp` server (the co-writer catalog — admin tools live on a **separate** `/mcp/admin`
server, INV-T6, and are out of scope here) registers **~50 tools**; 8 are already
`visibility:legacy`, leaving **~42 default-visible**. The book catalog was taken to ~11. Glossary is
4× that, and the bloat is concentrated in a handful of **near-duplicate clusters** — several tools
whose purpose is nearly identical, differing only by cardinality (single vs batch), scope branch
(book vs user), or a matrix axis (active/kind/entity). A mid-tier model juggling 42 tools picks
wrong, re-reads the list, and burns its window — the exact failure the book shrink fixed.

**Goal:** collapse the near-duplicate clusters into a few well-shaped unified tools, take
default-visible from ~42 → ~24, and (riding along) give every surviving book-scoped tool the
`WithAmbientBook` envelope tag so the model stops transcribing the `book_id` UUID.

## 2. The governing tension — shrink vs discoverability (READ FIRST)

Fewer tools is **not** unconditionally better. This domain already learned it twice:

- **Context bloat** (too many tools / too-large results): gemma called `glossary_list_system_standards`
  **24 times** in one run and built nothing, because each 44KB result buried the last. → argues for
  **fewer, smaller** tools.
- **Discoverability** (a capability the model can't find): `glossary_entity_rename` exists **only**
  because a mid-tier model asked to "rename X" will not discover that `glossary_entity_set_attributes`
  renames via `attributes={"name": …}`. A named tool carrying rename synonyms is findable; folding it
  away **regresses** the live loop. → argues for **named, discoverable** tools.

**The unification rule this spec follows:** merge tools that are near-identical **in shape** and that a
model would **mis-pick between** (the confusion is the cost). **Keep** a "duplicate" that earns its
place as a **discovery affordance** (a distinct verb a weak model reaches for). Every merge below is
justified against *both* sides; every non-merge records why the duplicate stays.

Governed by `docs/standards/mcp-tool-io.md` (CAT rules) + the hot-set/lazy-tail surfacing design (F17).

## 3. Cluster decisions

### 3.1 Ontology write — 7 → 4 (legacy 3)  ✅ clear

| Tool | Fate | Why |
|---|---|---|
| `glossary_ontology_upsert` (Tier A, direct, create+update, book/user) | **keep** | the direct-write path |
| `glossary_ontology_delete` (Tier W book / A user) | **keep** | the delete path (confirm asymmetry, per 2026-07-06 spec) |
| `glossary_propose_batch` (Tier W, deterministic multi-op confirm) | **keep** | the proposed-batch path; its ops already cover the 3 below |
| `glossary_plan` (Tier W, **paid**, LLM-planned) | **keep** | the natural-language planning path |
| `glossary_propose_new_kind` | **legacy** | = `propose_batch` op `create_kinds` (1 item). Its own description says "PREFER `propose_batch`". |
| `glossary_propose_kinds` | **legacy** | = `propose_batch` op `create_kinds` (n items) |
| `glossary_propose_new_attribute` | **legacy** | = `propose_batch` op `add_attributes` |

Shape-identical, model told to prefer the batch already → pure confusion cost, zero discovery loss.
**`propose_batch` IS the one proposal tool** (the 3 singles fold entirely into it — "gộp hết vào 1").

**Why not *also* fold `ontology_upsert` / `ontology_delete` / `plan` into `propose_batch`?** They are
distinct **capabilities**, not duplicates, separated by a *safety* boundary the system (not the model)
must own:
- `ontology_upsert` is **Tier A — writes immediately**; `propose_batch` is **Tier W — mints a confirm
  card a human approves**. Merging them makes one tool whose safety behavior varies by an argument
  (`mode: direct|propose`) — the **CAT-2 footgun** (`mcp-tool-io.md`): a weak model must never get to
  choose whether a human confirms. The A/W split *is* the gate.
- `glossary_plan` **calls an LLM and spends real money** (paid); `propose_batch` is deterministic and
  free — a different cost class.
- *(Round-2, deferred D4:)* a server that auto-gates destructive ops behind confirm could make
  upsert+batch one tool — but it re-opens the confirm-token UX. Not this pass.

### 3.2 Curation reads — 6 → 1 new + fold 3 into `get_entity`

The 6 split by addressing:
- **Book-inbox lists** (`list_merge_candidates`, `list_unknown_entities`, `list_ai_suggestions`) —
  "what in this book needs triage." Same shape: `(book_id, status?) → list`. → **NEW
  `glossary_curation_list`** with `view ∈ {merge_candidates, unknowns, ai_suggestions}` (enum,
  closed-set) + optional `status`. Legacy the 3.
- **Entity-detail reads** (`list_chapter_links`, `list_entity_revisions`, `get_entity_evidence`) —
  "what's attached to THIS entity." → fold into **`glossary_get_entity`** via an
  `include ∈ {chapter_links, revisions, evidence, genres}[]` param (default: none, so the base read
  stays small). Legacy the 3.

**Discoverability guard:** `glossary_curation_list` carries synonyms (`review inbox`, `duplicates to
merge`, `triage`, `unknown entities`, `ai suggestions`). The `include` fold is the one real trade-off
(a model wanting "evidence for X" must know to expand `get_entity`) — mitigated by naming the
expansions in the `get_entity` description + synonyms. **D1 — ✅ DECIDED: fold** (6→1). Named
expansions + synonyms on `get_entity`; revert to named reads only if a live smoke shows gemma can't
find evidence/revisions.

### 3.3 Curation proposes — 4 → 1 new  ✅ clear

`propose_status_change`, `propose_restore_revision`, `propose_reassign_kind`, `propose_merge` are all
Tier-W confirm-minters over an entity target — the **exact op-dispatch shape `propose_batch` already
ships**. → **NEW `glossary_propose_curation`** with `op ∈ {status_change, restore_revision,
reassign_kind, merge}` + per-op params. Legacy the 4. (Deliberately a **sibling** of `propose_batch`,
not folded into it: `propose_batch` is ontology-scoped — kinds/genres/attributes — and mixing
entity-curation ops muddies both. Two clean op-dispatchers beat one overloaded one.)

### 3.4 Genre matrix — 4 → 1 new + fold getter  (verified NOT redundant)

Verified: `ontology_upsert` / `adopt_standards` / `propose_batch` operate on ontology **rows** or
**adopt** standards; **none** wire the genre **matrix**. So these are not dead weight — but they are 3
tiny Tier-A tools that collapse by axis:

- `book_set_active_genres` (book's active columns, delta) · `book_set_kind_genres` (kind→genre links,
  delta) · `entity_set_genres` (per-entity override, replace) → **NEW `glossary_set_genres`** with
  `target ∈ {book_active, kind, entity}` (enum) + the target's params. Legacy the 3.
- `entity_get_genres` (read) → fold into `get_entity` `include=genres` (§3.2). Legacy it.

### 3.5 User-tier management — 2 → 0 in co-writer  (user's call: GUI surface)

`glossary_user_standards_read`, `glossary_user_restore` (+ `user_create`/`patch`/`delete` already
legacy) → **legacy all**. Managing your personal custom-kinds catalog is a **user/settings action via
GUI**, not a co-writer capability. The `scope=user` branch stays reachable inside
`ontology_upsert`/`ontology_delete` if an agent genuinely needs it — we remove the dedicated tools,
not the capability.

### 3.6 Lifecycle — legacy `book_revert`

`glossary_book_revert` (Tier-W, reverts an ontology row to a prior version) → **legacy** (matches the
book precedent: lifecycle/destructive off the default catalog).

### 3.7 Explicit NON-targets (duplicates that EARN their place)

| Tool | Why it stays despite overlap |
|---|---|
| `glossary_entity_rename` | discoverability alias of `entity_set_attributes` ("name" is an attr_code) — folding it away regresses the live loop (§2). |
| `glossary_entity_delete` / `restore` | the FE Undo allowlist (`useActivityUndo.ts`) carries these exact names; a soft-delete pair is clearer split than as a `delete(restore=bool)` flag. |
| `glossary_propose_entities` vs `entity_set_attributes` | create-time batch vs post-hoc edit — genuinely different write moments (create is idempotent-skip; edit merges). |
| `glossary_propose_translation` / `propose_aliases` | distinct localization verbs; low mis-pick risk. Round-2 candidate only. |

## 4. Target catalog (~24 default-visible)

**Reads (7):** `search`* · `get_entity`* (+`include`) · `book_ontology_read`* · `list_system_standards` ·
**`curation_list`**◆ · `extract_entities_from_doc` · `book_sync_available`
**Ontology write (6):** `ontology_upsert` · `ontology_delete` · `propose_batch` · `plan` ·
`adopt_standards` · **`set_genres`**◆
**Entity write (4):** `propose_entities` · `entity_set_attributes` · `entity_rename` · `entity_delete` ·
`entity_restore`
**Curation (1):** **`propose_curation`**◆
**Localization (2):** `propose_translation` · `propose_aliases`
**Annotate (2):** `create_chapter_link` · `create_evidence`
**Research (1):** `deep_research` · **Sync (1):** `book_sync_apply`

`*` already `WithAmbientBook`. ◆ = NEW unified tool. **Legacy'd this pass (20):** propose_new_kind,
propose_kinds, propose_new_attribute (→ `propose_batch`); list_merge_candidates,
list_unknown_entities, list_ai_suggestions (→ `curation_list`); list_chapter_links,
list_entity_revisions, get_entity_evidence, entity_get_genres (→ `get_entity.include`);
propose_status_change, propose_restore_revision, propose_reassign_kind, propose_merge
(→ `propose_curation`); book_set_active_genres, book_set_kind_genres, entity_set_genres
(→ `set_genres`); book_revert, user_standards_read, user_restore (lifecycle/GUI).

## 5. Envelope — intersect, no separate pass

Every surviving **book-scoped** tool gets `WithAmbientBook` + `book_id,omitempty` + `resolveBookScope`
**as it is touched** this pass (the reads already have it; the 4 new tools are born with it; the write
survivors gain it). `list_system_standards` is `ScopeNone` (no envelope). Do **not** envelope-tag any
tool being legacy'd. This folds the parked envelope long-tail into the unification for the survivors —
the only tools that matter.

## 6. Migration atomicity (CAT / book precedent)

Per the book redesign + `docs/standards/mcp-tool-io.md`: a legacy-tag and its replacement land in the
**same change** so no capability is ever unreachable. Each NEW unified tool **reuses the legacy tools'
handler cores** (single source of truth — the write paths can never diverge), exactly as
`ontology_upsert` reused the book/user cores. The frontend-tools contract
(`contracts/frontend-tools.contract.json`) + the `mcp_tool_schema_contract_test.go` visibility test
regen in the same commit.

## 7. Open decisions (need a call before BUILD)

- **D1 — the `get_entity.include` fold (§3.2).** Fold the 3 entity-detail reads into `get_entity`
  (6→1, max shrink) **or** keep them as 3 named tools (6→4, safer discovery)? *Recommendation:* fold,
  with named expansions + synonyms; revert if a live smoke shows the model can't find evidence/revisions.
- **D2 — `curation_list` — ✅ DECIDED (unify with explicit enum).** One tool, closed-set
  `view ∈ {merge_candidates, unknowns, ai_suggestions}` + optional `status`. The enum is the guard
  against a weak model free-stringing a wrong view (the `panel_id` class). Live-smoke gemma picking
  each view before sealing.
- **D3 — round-2 (localization + annotate merges).** Defer `propose_translation`/`propose_aliases` and
  `create_chapter_link`/`create_evidence` merges to a later pass? *Recommendation:* defer — low
  mis-pick risk, not worth the churn now.
- **D4 — server-auto-gated ontology write (round-2).** Collapse `ontology_upsert` + `propose_batch`
  into one tool where the server (not the model) decides direct-vs-confirm by op destructiveness.
  *Recommendation:* defer — re-opens the confirm-UX; the A/W split is the safety boundary for now.

## 8. Build plan (parts, mirrors the book redesign)

- **Part A — legacy-tags** (the 16, no new tools): add `WithVisibility(..., VisibilityLegacy)`; verify
  the catalog count drops; contract/visibility test regen. Cheap, reversible, immediately shrinks.
- **Part B — `glossary_curation_list`** (§3.2 inbox) + fold entity-reads into `get_entity.include`.
- **Part C — `glossary_propose_curation`** (§3.3 op-dispatch), reusing the 4 legacy cores.
- **Part D — `glossary_set_genres`** (§3.4 target-dispatch), reusing the 3 legacy cores.
- **Part E — envelope tags** on the write survivors (§5) + live-smoke (gemma, $0) each new tool.

Each part: build → verify → 2-stage review → live-smoke → commit. VERIFY needs a real gateway call
(cross-service: chat-service ↔ ai-gateway ↔ glossary).
