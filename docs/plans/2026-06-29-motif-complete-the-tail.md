# Plan — Complete the Motif Library Tail

> **Date:** 2026-06-29 · **Branch:** `feat/narrative-pattern-library` · **Driver:** [2026-06-29 completeness audit](../reports/2026-06-29-motif-completeness-audit.md)
> **Scope chosen:** *Everything incl. per-book adopt* (all six work items below).
> **Type:** DESIGN + PLAN (no code yet). Phase gate before BUILD: the **WI-5 decision** (it reverses locked decision R1.1.1) needs explicit sign-off.

This plan closes every gap the audit flagged, sequenced by value/risk and dependency. Each work item (WI) is independently shippable behind its own commit.

---

## 0. Summary table

| WI | Gap | Type | Size | Backend ready? | Reverses a locked decision? |
|----|-----|------|------|----------------|------------------------------|
| **WI-1** | Mining FE (trigger + draft review/promote) | FE | M | ✅ live-smoked | no |
| **WI-2** | Full motif field-editor UI | FE | M | ✅ `PATCH /motifs/{id}` | no |
| **WI-3** | `arc_suggest` semantic retrieve (`retrieve_arcs`) | BE | S–M | partial (mirror motif retrieve) | no |
| **WI-4** | Sync 3-way merge + upstream-diff UI | FS | L | ✅ data model exists | no |
| **WI-5** | Per-book adopt (`D-MOTIF-ADOPT-PER-BOOK`) | FS + migration | L–XL | needs schema | **YES — reverses R1.1.1** |
| **WI-6** | `motif_link` edge-walk MCP API (optional) | BE | S | table exists | no |

**Recommended build order:** WI-3 → WI-1 → WI-2 → WI-4 → (decision) → WI-5 → WI-6.
Rationale: WI-3 is a cheap backend that unblocks an arc-suggest UX; WI-1/WI-2 are high-value FE with ready backends; WI-4 is larger but self-contained; **WI-5 is gated on the R1.1.1 decision** and is the riskiest, so it goes last.

---

## WI-1 — Mining FE (`D-MOTIF-MINE-FE-BRIDGE`)  ·  [FE] · M

**Goal:** surface the self-enrichment flywheel (mockup 04) — trigger a corpus/book mine, watch the job, review the mined drafts, promote or discard.

**Backend is done** (live-smoked this branch): `composition_motif_mine` (propose) → `/actions/confirm` (JWT) → `mine_motifs` worker (tag-beats v2 → PrefixSpan → abstraction → judge → `status='draft'` motifs) → `composition_get_mine_job` / `GET /jobs/{id}` (poll). Drafts land in `motif` with `status='draft'`, `source='mined'`, `judge_score`, `mining_support`.

**No new backend.** Review/promote reuses existing surfaces: `list_for_caller(status='draft')`, `PATCH /motifs/{id}` (status `draft`→`active` = promote), `DELETE /motifs/{id}` (archive = discard).

### Design
- **`MotifMinePanel`** (new component) — a run-config form: scope (`book`|`corpus`), `min_support`, `language`, and a **`ModelRolePicker`** (mining needs a BYOK `model_ref`; reuse the one `ArcConformancePanel` deep uses). Runs the Tier-W flow.
- **`useMotifMine`** (new hook) — mirrors `useArcConformanceRun`: `mcpExecute('composition_motif_mine', { args: { scope, book_id, min_support, model_ref, model_source } })` → `confirm_token` + `estimate` → render **`CostConfirmCard`** → JWT `POST /actions/confirm?token=` → `job_id` → poll `GET /jobs/{id}` to terminal → expose `{ mined, candidates, reason }`.
- **Draft review queue** — extend `useMotifLibrary` with a `status` facet (default `active`; add a **"Drafts (N)"** scope/filter). `MotifCard` already has a draft variant; add **Promote** (`motifApi.promote` = `PATCH {status:'active'}`) and **Discard** (`archive`) actions on draft cards, plus the mined provenance line (`support ×N · judge X.XX`). Show below-gate candidates from the job result as read-only (they were never persisted — §11 no-silent-drop).
- **`motifApi`** additions: `minePropose`, `mineConfirm`, `pollMineJob` (or reuse the generic bridge + `getJob`), `promote(id, expectedVersion)`.

### Files
`frontend/src/features/composition/motif/components/MotifMinePanel.tsx` (new), `MotifDraftReviewList.tsx` (new or fold into library), `hooks/useMotifMine.ts` (new), `api.ts` (+mine/promote), `MotifLibraryView.tsx` (+Drafts filter + mine entry button), `types.ts` (+MineResult).

### Tests
Hook flow (mint→confirm→poll happy + quota-error + degrade); promote/discard mutations; draft-filter rendering; tsc + vitest. **Live smoke:** real corpus mine via the panel → drafts appear → promote one → it becomes `active`.

### Risks
Mining a single book yields few patterns (PrefixSpan counts *sequences*=books); the panel copy should steer users to **corpus** scope for real yield. Surface `reason: 'beat_extractor_unavailable'` honestly when a book has no extracted `:Event` corpus.

---

## WI-2 — Full motif field-editor UI (`D-MOTIF-FULL-EDITOR-FE`)  ·  [FE] · M

**Goal:** edit an *owned* motif's full schema in place (mockup 02 + 06-A). Today only create (`MotifQuickCreateForm`) + clone-to-edit exist; `MotifDetailDrawer` is read-only.

**Backend is done:** `PATCH /motifs/{id}` (owner-only, If-Match optimistic lock, re-embeds on summary change). System rows stay read-only (clone-to-edit).

### Design
- **`MotifEditorForm`** (new) — the full field editor, a superset of `MotifQuickCreateForm`:
  - identity: `name`, `code` (immutable post-create — show disabled), `kind`, `summary`, `genre_tags` (chip add/remove), `tension_target`, `emotion_target`
  - **roles[]**: actant (Greimas enum) · label · constraints · add/remove
  - **beats[]**: label · intent · `tension_target` (1–5) · order, with drag-reorder (reuse the dnd pattern from `ArcTimelineGrid` or a simple up/down)
  - **preconditions[] / effects[]**: free-text NL rows, add/remove
  - **examples[]**: author-written text rows (note: stripped on imported-derived publish)
  - **info_asymmetry**: shown only for `kind='scheme'` (reuse `InfoAsymmetryCard` in edit mode)
- **`useMotifEditor`** (new) — seed from `useMotifDetail`, track dirty fields + `version`, submit via `motifApi.patch(id, args, expectedVersion)`; handle 412 (version conflict → reload + warn); on success invalidate detail + library.
- Wire an **"Edit"** affordance into `MotifDetailDrawer` for owned motifs (drawer flips view↔edit), and reuse the same form for the "advanced build" continuation after `MotifQuickCreateForm` (mockup 06 "→ opens in the full editor").

### Files
`components/MotifEditorForm.tsx` (new), `hooks/useMotifEditor.ts` (new), `MotifDetailDrawer.tsx` (+edit mode toggle), `MotifLibraryView.tsx` (route quick-create → editor), `types.ts` (MotifPatchArgs shape).

### Tests
Form state (dirty tracking, validation, all field types incl. roles/beats reorder, scheme-only info_asymmetry); patch happy + 412-conflict; read-only enforcement for system/non-owned; tsc + vitest. **Live smoke:** edit an owned motif's beats + summary → PATCH 200 → re-embed observed (embedding hash changes).

---

## WI-3 — `arc_suggest` semantic retrieve (`D-ARC-RETRIEVE`)  ·  [BE] · S–M

**Goal:** make `composition_arc_suggest` return real candidates instead of `"not yet available"`. F0 froze only the motif `retrieve`; the arc retriever was never implemented.

### Design
- **`MotifRetriever.retrieve_arcs(caller_id, *, book_id, project_id, premise, genre, limit)`** — mirror `retrieve()` over `arc_template`:
  1. SQL pre-filter: `status='active'` + language + `genre_tags && book_genres` + visible predicate (system|public|owner), `LIMIT motif_candidate_ceiling`.
  2. Query vector from `premise + genre` via the platform embed (same `embed_query`).
  3. Cosine over `arc_template.embedding`; `match_reason = {genre, cosine}` (+ degrade to genre order on embed failure, mirroring R4). NULL arc vectors → queue lazy back-fill, skip in cosine path.
  4. Deterministic tie-break (cosine desc, code asc) → `ArcCandidate[]`.
- **Arc embedding pipeline:** confirm `arc_template` has the embed columns (it does) + a back-fill path mirroring `motif_embed`. If arc rows are unembedded, add the same lazy-back-fill `MotifRetriever` uses for motifs. The canonical arc summary text = name + summary + thread labels + member-motif codes.
- Wire `composition_arc_suggest` (server.py ~1234) to call `retrieve_arcs` and drop the stub branch.

### Files
`db/repositories/motif_retrieve.py` (+`retrieve_arcs`, +arc candidate fetch SQL), `engine/motif_embed.py` (arc summary text + back-fill if missing), `mcp/server.py` (`composition_arc_suggest` wiring), models (`ArcCandidate` if absent).

### Tests
`retrieve_arcs` pre-filter bounds load; cosine + tie-break deterministic; degrade path; embed back-fill idempotent; the tool returns candidates. **Live smoke:** `composition_arc_suggest` over the seeded arc(s) returns ranked results.

### Risk
If no system arc templates are seeded, suggest returns `[]` legitimately — confirm W7 seeds at least one arc, or note the empty-corpus degrade.

---

## WI-4 — Sync 3-way merge + upstream-diff (`D-MOTIF-SYNC-3WAY-BASE`)  ·  [FS] · L

**Goal:** the "upstream has an update" path (mockup 01 adopted-edited card): detect when an adopted motif's source advanced, show a 3-way diff (base/mine/theirs), let the user accept-upstream / keep-mine per field.

**Data model exists:** adopt snapshots `adopted_base` (the upstream's mergeable fields at adopt time) + pins `source_ref`/`source_version`; `patch()` already does atomic `repin_source_version` + `repin_adopted_base`. The gap is the merge orchestration + detection + UI.

### Design
- **Detection** — `MotifRepo.list_adopted_with_updates(user_id)`: for the caller's `source='adopted'` rows, join the upstream by lineage and flag where `upstream.version > source_version`. Returns `[{motif_id, upstream_version, has_conflict_hint}]`. Exposed via a Tier-R MCP read (`composition_motif_sync_status`) + a thin REST `GET /motifs/{id}/upstream`.
- **3-way merge** — `MotifRepo.sync_adopted(user_id, motif_id, upstream_version, resolutions)`:
  - load `base = adopted_base`, `mine = current local`, `theirs = current upstream`.
  - per mergeable field (summary, beats, roles, preconditions, effects, genre_tags): `mine==base` → take theirs; `theirs==base` → keep mine; else **conflict** → use the caller's `resolutions[field]` (`take_mine`|`take_theirs`), default surface-and-hold.
  - write via the existing atomic `patch(..., repin_source_version=upstream_version, repin_adopted_base=<new theirs snapshot>)`. Re-embed if summary/beats changed.
- **Tier-W?** Pure merge of the caller's own row = **Tier-A** (auto-write + undo via version restore); no LLM/quota. Add `composition_motif_sync` (Tier-A) calling `sync_adopted`.
- **FE** — `useMotifSync` hook + `UpstreamUpdateBanner` (on the adopted-edited `MotifCard`) + `SyncDiffDrawer` (base|mine|theirs three-column per field, per-field accept toggle, "Apply merge"). Mockup 01's "Review upstream diff" link opens the drawer.

### Files
BE: `motif_repo.py` (+`list_adopted_with_updates`, +`sync_adopted`), `mcp/server.py` (+`composition_motif_sync_status` R, +`composition_motif_sync` A), `routers/motif.py` (+`GET /motifs/{id}/upstream`). FE: `hooks/useMotifSync.ts`, `components/UpstreamUpdateBanner.tsx`, `components/SyncDiffDrawer.tsx`, `MotifCard.tsx` (banner), `api.ts`.

### Tests
3-way merge truth table (mine-only / theirs-only / both / conflict-resolution); atomic re-pin (no half-merge window); detection join; undo restores; FE diff render + per-field accept. **Live smoke:** adopt a system motif → bump the system source → detect update → merge → re-pin.

### Risk
Lineage join: `source_ref` is an **opaque token** on published imported-derived rows (B-3). For sync we need the real upstream id for the caller's *own* adopted rows — store the resolvable lineage on the **private** clone (not the published projection). Confirm the adopt path keeps a back-resolvable upstream id on the private row (it should — opaquing is publish-time only).

---

## WI-5 — Per-book adopt (`D-MOTIF-ADOPT-PER-BOOK`)  ·  [FS + migration] · L–XL  ·  ⚠ REVERSES R1.1.1

### ⚠ Decision required before BUILD
The spec **deliberately removed the book tier** (R1.1.1, locked): *"templates are book-independent; per-book customization = clone-to-your-library, then use in any book."* The whole tenancy model, the partial unique indexes, the read predicate, and the pre-build B-2 fix assume **2 tiers (user + system)**. Re-introducing a book tier is an architectural reversal, not just a feature add.

**The cheaper alternative already ships:** adopt-to-user (`target:'user'`) + bind the motif in whatever book you want. That covers "use this motif in my book" fully. The *only* thing per-book adopt adds is **isolation** — a clone scoped to ONE book, invisible to the user's other books.

> **Recommendation:** prefer the alternative (document "use in a book = adopt-to-user + bind") unless there's a concrete need for book-isolated motif copies. If we proceed, the design below is the minimal correct way.

### Design (if approved)
- **Migration:** add `book_id UUID NULL` to `motif`; new partial unique `UNIQUE(book_id, code, language) WHERE book_id IS NOT NULL`; the `motif_user_owned` CHECK extends so a book-tier row carries `owner_user_id` (the granting owner) **and** `book_id`. Tenancy resolution merges **System → User → Book** (book shadows user shadows system by code).
- **Read predicate** gains a 3rd arm: a book-tier row is visible to the book owner + E0 grantees (cross-tenant access stays grant-gated, never a global row — the kinds-bug rule).
- **Clone primitive:** `adopt(target='book', book_id=…)` resets owner to caller, sets `book_id`, visibility `private`; book-tier rows never publishable.
- **Retriever:** `_fetch_candidates` merges the book tier into the pre-filter (caller's book rows first).
- **MCP:** `composition_motif_adopt` arg `target: Literal['user','book']` + `book_id` (required when `target='book'`, BOOK(EDIT) grant gate).
- **FE:** re-add the per-book target option to `AdoptTargetModal` (it was removed when the backend went 2-tier) + a books prop.

### Files
`db/migrate.py` (motif book_id + index + CHECK + read predicate), `motif_repo.py` (adopt target=book, list predicate, retrieve merge), `mcp/server.py` (`_MotifAdoptArgs` target enum + gate), `routers/motif.py` (adopt body), FE `AdoptTargetModal.tsx` + `useAdoptFlow.ts` + `MotifLibraryView.tsx`.

### Tests
Migration idempotent; 3-tier resolution order; book-tier IDOR (a book grantee sees it, a stranger does not — uniform deny); book-tier never publishable; adopt target=book gated on BOOK(EDIT); retriever merges book tier. **Live smoke + a tenancy review (`/review-impl`) is mandatory** — this is the exact surface the original kinds-bug lived on.

### Risk
Highest on the branch. Touches the locked tenancy model + a migration + the read predicate every motif query relies on. **Do last, behind the decision, with a dedicated adversarial tenancy review.**

---

## WI-6 — `motif_link` edge-walk MCP API (optional)  ·  [BE] · S

**Goal:** a read tool to traverse the `precedes` / `composed_of` / `variant_of` graph (today only seed edges + pattern-member adopt exist; chain-it works off binding hints, not a generic API).

### Design
- `composition_motif_links(motif_id, kind?)` (Tier-R): return outgoing/incoming edges (visible motifs only), with cycle-safe traversal for `precedes` chains (DB already has the cycle-guard trigger).
- Optional Tier-A `composition_motif_link_create`/`_delete` (same-tier gated, the trigger enforces acyclic + same-owner).

Low priority — fold in only if the chain-it / succession UX needs a generic walk. Otherwise leave as a tracked nicety.

---

## Sequencing & checkpoints

```
WI-3 (BE, cheap) ─┐
WI-1 (FE, ready) ─┼─► commit each ─► WI-4 (FS) ─► [DECISION gate] ─► WI-5 (migration) ─► WI-6 (opt)
WI-2 (FE, ready) ─┘
```

- **Per-milestone gates** (per CLAUDE.md budget-driven cadence): VERIFY evidence + 2-stage review + live-smoke at each WI's risk boundary; one commit per WI.
- **POST-REVIEW checkpoints:** after WI-4 (largest of the non-reversing set) and **before WI-5 BUILD** (the R1.1.1 decision).
- **`/review-impl` mandatory** on WI-4 (merge correctness) and WI-5 (tenancy).

## Effort (rough)
WI-3 ~S–M · WI-1 ~M · WI-2 ~M · WI-4 ~L · WI-5 ~L–XL · WI-6 ~S. Tiers 1+ (WI-1/2/3) are the bulk of user-visible value and carry no schema risk; WI-4 is self-contained; WI-5 is the long pole and the one decision.

## Open decisions for sign-off
1. **WI-5 / R1.1.1** — proceed with per-book adopt (reversing the locked 2-tier decision), or take the recommended alternative (adopt-to-user + bind)?
2. **WI-6** — build now or leave tracked?
3. **Build order** — accept the recommended order, or front-load a specific WI?
