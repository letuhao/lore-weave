# Spec — Glossary + KG extraction-quality & approve-flow fixes

**Date:** 2026-06-22 · **Branch:** `feat/knowledge-graph-ontology` · **Status:** DESIGN (CLARIFY→DESIGN→REVIEW)

Designs the three deferred items surfaced during the Dracula glossary-assistant
session (see `docs/sessions/SESSION_HANDOFF.md` ▶ THIS BRANCH):

- **F1 — `D-GLOSSARY-SYSTEM-ATTR-DESCRIPTIONS`** — every attribute description is empty platform-wide; extraction has no per-attribute guidance.
- **F2 — `D-KG-SCHEMA-APPROVE-LIVE`** — KG schema propose→approve isn't live-proven, AND the new auto-confirm card mis-routes KG tokens to the glossary endpoint.
- **F3 — `D-GLOSSARY-WEAKMODEL-BATCH`** — local models fumble the multi-step curation (wrong `glossary_book_patch` arg shape, tangents, bulk degradation).

The three are independent and can ship as separate milestones; F2 and F3 each
have one small FE/contract change that is load-bearing.

---

## F1 — System-tier attribute descriptions

### Problem / root cause
`book_attributes.description` feeds the extraction prompt as the per-attribute
instruction ([extraction_prompt.py](../../services/translation-service/app/workers/extraction_prompt.py#L176-L185)).
Coverage today: **system_attributes 93/93 empty, book_attributes 26113/26119 empty,
user_attributes 11/11 empty.** Books clone System at adopt time
([book_adopt_handler.go](../../services/glossary-service/internal/api/book_adopt_handler.go#L238-L253):
`SELECT … sa.description … sa.content_hash`), so an empty System description
propagates to every adopting book. The seed simply never authored descriptions —
this is a **System-tier content gap**, not a code bug.

### Tier rules (CLAUDE.md "User Boundaries")
System attributes are **System tier** — admin-only writes, everyone reads, users
clone/override into their own book/user tier. So the fix is an **admin/seed**
action, never a per-user write. Per-book edits stay the user's (F3's tolerant
patch + the existing `glossary_book_patch`).

### Design
1. **Author the descriptions (content).** Write a clear, extraction-ready
   description (1 sentence, names what to capture) for every System attribute of
   the 12 seeded kinds. Source of authorship: drive the **admin glossary
   assistant** (`glossary_admin_propose_patch`, System tier) to draft them, OR
   hand-author a table. Output is a reviewed `(kind_code, genre_code, attr_code) →
   description` map. Also set `auto_fill_prompt` where the extraction wants a
   different instruction than the human-facing description (optional; extraction
   reads `description`).
2. **Apply on the System tier** via a **seed migration** (`UPDATE
   system_attributes SET description=…, content_hash=<recomputed>` keyed by
   `(kind, genre, code)`), reviewable + deterministic for 93 rows. Ongoing edits
   go through the admin tool (already exists).
3. **`content_hash` MUST include `description`** (VERIFY — F1's load-bearing
   check). The adopt copy uses `sa.content_hash` as the book row's `source_hash`;
   G5 Sync detects an upstream change by hash drift. If the current
   `content_hash` composition excludes `description`, a description-only edit is
   invisible to Sync → existing books never see it. Fix: include `description`
   (and `auto_fill_prompt`) in the hash, and recompute in the seed migration.
4. **Propagation:**
   - **New books** — automatic at adopt (copies `sa.description`).
   - **Existing books** — `glossary_book_sync_available` surfaces "source
     description changed" (hash drift) → the user pulls with `take_theirs`
     (per-row, `keep_mine` protects any local edit). FE Sync UI already exists.
   - **Optional one-time backfill** — for already-adopted books whose attr
     `description` is empty AND `source_hash` still matches the (old) System row,
     re-pull `description` from the source. Lower priority; Sync covers it.

### Slices
- F1a content: author + review the description map (admin assistant or table).
- F1b migration: set `system_attributes.description` + recompute `content_hash`; ensure hash includes description.
- F1c verify: a real-PG test — edit a System attr description → `book_sync_available` lists it → `sync_apply take_theirs` pulls it; `keep_mine` preserves a local edit.

### Risks
- A hash bump triggers a Sync prompt for **all** adopted books (intended, but noisy) — it's opt-in per row, non-destructive.
- Don't clobber user-edited descriptions — Sync's `keep_mine` + the per-row diff already guard this.

---

## F2 — KG schema propose→approve (+ auto-confirm card routing)

### Problem / root cause
Two things:
1. **Card mis-routing (HIGH).** KG class-C descriptors are **non-dotted but
   `kg_`-prefixed** (`kg_schema_edit`, `kg_adopt`, `kg_sync_apply`,
   `kg_triage_*`; [confirm.py](../../services/knowledge-service/app/ontology/confirm.py#L63-L84)).
   The new auto-confirm card routes by `descriptorDomain()`, which only knows
   **dotted** generic domains (`book.`/`composition.`/`translation.`/`settings.`)
   and falls back to the glossary `ConfirmCard` for everything non-dotted — which
   POSTs to `/v1/glossary/actions/confirm`. So an auto-rendered KG proposal hits
   the **wrong service** (→ 422). KG schema approve via chat is therefore broken
   for the auto-card path.
2. **Contract mismatch.** KG `/v1/kg/actions/preview` is **POST**
   ([kg_actions.py](../../services/knowledge-service/app/routers/public/kg_actions.py#L609)),
   while the generic `actionsApi.previewAction` does **GET `?token=`**
   ([actionsApi.ts](../../frontend/src/features/chat/actionsApi.ts#L46-L51)). The
   generic `ConfirmActionCard` can't preview KG as-is.
3. **Not live-proven.** `kg_schema_edit` requires an **adopted project-scoped
   schema** first (the System template is read-only), so the real flow is
   `kg_adopt_template → approve → kg_schema_edit → approve` — never run live.

### Design
1. **FE routing — recognise the `kg` domain.** Extend the descriptor→domain
   resolution (in `ConfirmActionCard.descriptorDomain` + `AssistantMessage`
   auto-card): a descriptor starting with `kg_` → domain `"kg"` →
   `ConfirmActionCard` (generic, `/v1/kg/actions/*`). Glossary's non-`kg_`
   non-dotted descriptors keep routing to `ConfirmCard`. Add `kg` to the
   generic-domain allowlist. This is the one load-bearing FE change.
2. **Align the KG actions contract to the generic shape.** Add a **GET
   `/v1/kg/actions/preview?token=`** (non-consuming) alongside the existing POST
   confirm, matching `actionsApi` (GET preview, POST confirm `{confirm_token}`).
   Keep the POST preview if other callers use it. Confirm the BFF proxies
   `/v1/kg/actions/*` (the `/v1/kg` proxy landed in `eb39a3ca` — verify the
   `/actions` subpath).
3. **Adopt-first guidance.** The knowledge/workflow skill states the ordering:
   to edit a project ontology you must first `kg_adopt_template` (or the project
   inherits System read-only). The auto-card handles both proposals (adopt +
   schema_edit each mint a token → each renders a card).
4. **Edge-type ontology (Dracula).** The agent proposes `kg_schema_edit add
   edge_type` for `TURNED_BY / HUNTS / PROTECTS / FEARS / LOCATED_IN` (the same
   set it already surfaced in research). Each is one approve card.

### Slices
- F2a FE: `kg` domain routing in `descriptorDomain` + auto-card + a unit test (kg_ descriptor → ConfirmActionCard, posts /v1/kg/actions/confirm).
- F2b BE: GET preview alias on KG actions; verify BFF `/v1/kg/actions` proxy.
- F2c skill: adopt-first ordering in the knowledge skill prompt.
- F2d live: adopt project schema → approve → add 5 edge types → approve → verify `kg_edge_types` rows + `schema_version` bump (Postgres) and the resolver sees them.

### Risks
- The KG confirm route's auth (browser-JWT, proposer==redeemer) must match what the FE card sends (the user JWT) — verify parity with glossary.
- Double preview routes (GET+POST) — keep both; GET is additive.

---

## F3 — Weak-model reliability

### Problem
Local gemma-26b (observed live): (a) emits the **entity-edit diff shape**
(`changes:[{target,old_value,new_value}]`) at `glossary_book_patch` instead of
the flat fields → silent no-op; (b) wanders into `web_search`/`kg_list_templates`
loops on a simple curation ask; (c) degrades across long multi-call batches;
(d) skips the frontend confirm tool — **already fixed** by the auto-confirm card.

### Design
1. **Tolerant `glossary_book_patch` parsing (highest-value).** Accept BOTH
   shapes server-side: the flat fields AND a `changes:[{target/code,new_value}]`
   diff, mapping the diff → flat (`target|code → attr code`, `new_value →
   description/name`). The model reliably *wants* to patch; only the shape is
   wrong. Low-risk, big reliability win. Reject ambiguous mixes explicitly.
2. **One-shot "kind + attributes" proposal (structural).** Add an optional
   `attributes: [{code,name,field_type,description}]` to
   `glossary_propose_new_kind`. The minted confirm token captures the kind AND
   its attributes; the **confirm effect creates the kind then its attributes in
   one transaction**. Collapses the fragile propose-kind → approve → propose-each-
   attr → approve chain into **one tool call + one approve card** — the single
   biggest reliability multiplier for weak models (and nicer for strong ones).
   The preview card lists the kind + N attributes; cancel/expiry unchanged.
3. **Reduce tangent surface.** In a book-scoped glossary-curation turn, the
   per-iteration tool curation should not surface `glossary_web_search` /
   `kg_list_templates` unless the user asked to research/adopt — they triggered
   the observed loops. Tighten via the find_tools curation hints + a skill line
   ("don't web-search for a local curation request").
4. **(Done) auto-confirm card** removes the `glossary_confirm_action` dependency.

### Slices
- F3a BE: tolerant `glossary_book_patch` (diff→flat) + tests (flat, diff, ambiguous-reject).
- F3b BE: `glossary_propose_new_kind` `attributes[]` + atomic confirm effect + preview rows + tests.
- F3c skill/curation: suppress research tools on a plain curation turn.

### Risks
- F3b atomic effect: partial failure (kind ok, attr dup) must roll back the whole tx and be re-proposable (422).
- F3a: never let a diff payload silently target the wrong row — require an unambiguous attr code.

---

## Sequencing & size

| Milestone | Touches | Size | Notes |
|---|---|---|---|
| F2a+F2b (KG card routing + GET preview) | FE + knowledge BE | **M** | unblocks KG approve in chat; load-bearing |
| F3a (tolerant patch) | glossary BE | **S** | quick, high reliability ROI |
| F3b (kind+attributes one-shot) | glossary BE | **M** | schema-ish (confirm effect), biggest UX win |
| F1 (system attr descriptions) | content + glossary migration | **L** | content authorship + hash/migration + sync verify |
| F2c/F2d, F3c, F1c | skills + live tests | per-milestone | VERIFY gates |

Each milestone is independently shippable with its own 2-stage REVIEW + live
smoke. Recommended order: **F2a/F2b → F3a → F3b → F1** (unblock KG first, then
the cheap reliability win, then the structural one, then the content-heavy F1).

## Test plan (per milestone)
- **F1:** real-PG — System desc edit → `book_sync_available` lists it → `sync_apply` pulls (take_theirs) / preserves (keep_mine); new adopt copies description; extraction prompt now carries it.
- **F2:** unit — `kg_` descriptor routes to ConfirmActionCard/`kg` domain; live — adopt→approve→schema_edit→approve→`kg_edge_types`+version bump; GUI — auto-card Confirm on a KG proposal hits `/v1/kg/actions/confirm` (not glossary).
- **F3:** unit — patch accepts flat+diff, rejects ambiguous; propose-kind-with-attributes atomic create + rollback; GUI — plain-language "add a Werewolf with weaknesses & triggers" → ONE approve card → kind+attrs land.

## CLARIFY sign-off (resolved 2026-06-22)
1. **F1 authorship → HAND-AUTHORED TABLE.** A reviewed `(kind, genre, attr) →
   description` table written by hand, baked into the seed migration. No
   admin-assistant drafting.
2. **F1 propagation → SYNC ONLY.** Rely on `book_sync_available → take_theirs`
   (per-row, user-initiated). **No one-time backfill** — empty descriptions stay
   until the user pulls. Keeps the change non-intrusive and fully user-controlled.
3. **F3 scope → BOTH.** Ship F3a (tolerant `glossary_book_patch`: accept flat +
   diff) AND F3b (`glossary_propose_new_kind` `attributes[]` + atomic
   kind+attributes confirm effect). Biggest reliability multiplier.

**Build order (locked):** F2a/F2b (KG card routing + GET preview) → F3a
(tolerant patch) → F3b (one-shot kind+attrs) → F1 (hand-authored table + seed
migration + `content_hash` includes description + sync-only propagation, verified
real-PG). Each milestone: 2-stage REVIEW + live smoke, its own commit.
