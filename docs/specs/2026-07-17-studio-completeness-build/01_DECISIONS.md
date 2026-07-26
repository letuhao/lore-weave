# Studio-completeness build — SEALED decisions (CLARIFY, 2026-07-17)

> All open questions across S-01..S-11 resolved. Two classes: **code-verified** (I settled from the
> repo) and **PO-decided** (the human chose). Sealed = do not re-litigate; re-read this, don't remember it.

## Code-verified seals (CLARIFY-verify against the repo)

| # | Question | SEALED | Evidence |
|---|---|---|---|
| CV-1 | S-01 `structure_template.kind` — closed enum? | **NO — free-text label, default `'generic'`.** Not in `CLOSED_SET_ARGS`. | `.kind` is read nowhere semantically (every consumer is outline-node/diagnostics/arc, not template). Forcing a user's custom structure to claim "save_the_cat" would be wrong. |
| CV-2 | S-05 add a `memory_invalidate` MCP tool? | **NO.** Human routes only (`POST /pending-facts`, `/facts/{id}/invalidate`). | `_handle_memory_forget` (`executor.py:726`) already calls `invalidate_fact` — agent parity on both verbs exists. A new tool would duplicate. |
| CV-3 | S-11 is `search` net-new? | **NO — a mount + aggregation.** No HTML draft. | `RawSearchPanel` + `RawSearchPage` + `story_search`/`memory_search` all exist; only the studio `search` activity-view is missing. |

## PO-decided seals (2026-07-17 AskUserQuestion)

| # | Question | PO DECISION | Effect |
|---|---|---|---|
| D-a | `search` activity-view — build or retire the icon? | **BUILD** (→ **S-11**) | new spec S-11; S-10 O4 no longer leaves it "Coming soon". |
| D-d | `[[`-create from the editor — build or leave hidden? | **BUILD** (→ **S-10 O7**) | `[[NewName` → kind-picker → `createEntity` → insert; wire `onCreateNew` in both consumers. |
| D-workflows | G-WORKFLOWS ownership | **BUILD IN THIS TRACK** (→ S-12) | ownership resolved; item un-parked. |
| D-order | Build order after seal | **FANOUT — each Tier-A a parallel session** | S-01/S-03/S-04 (composition) + S-02 (book-service) build in parallel, disjoint files; convergence node reconciles the studio registry. Same model as the 8-session run. |

## Author-sealed decisions (recorded in each spec; formalized here)

| Spec | Decision | Rationale |
|---|---|---|
| S-01 | Tenancy = partial-unique `UNIQUE(owner_user_id,name) WHERE NOT NULL` + a separate builtin-name unique; writes refuse owner-NULL rows (clone-to-edit) | not the `entity_kinds` global-unique bug |
| S-01 | version OCC + is_archived from day one | symmetry with canon_rules; motif/arc-template lacked restore (S-08) |
| S-01 | book-shared tier = OUT (per-user only; mirror arc-template `book_shared` later if wanted) | keep scope tight |
| S-02 | `path` for a user-created part = **synthesize from title** (keep NOT NULL) | (b) nullable weakens a column other code may assume non-null |
| S-02 | **No OCC on parts** | low-contention rename; `updated_at` + LWW acceptable |
| S-02 | trashing a part **un-homes** its chapters (`part_id=NULL`), never cascade-deletes | chapters survive in the flat manuscript |
| S-03 | Split UPDATE: PATCH metadata (no re-embed) vs PUT content (re-embed) | fixing a typo must not pay for a full re-embed |
| S-03 | **No OCC on references**; content-edit via MCP **out of scope** | low-contention; agent re-authoring a corpus is not wanted |
| S-04 | Scope = field-overrides + spec; relationship/event overrides stay M0-deferred | matches the existing deferral |
| S-04 | No DELETE of `divergence_spec` (delete = archive the Work) | the spec is the derivative's identity |
| S-04 | `add_override` upsert via `UNIQUE(work_id,target_entity_id)` | no silent duplicate |
| S-06 | No `glossary_attribute_value_delete` MCP tool (defer) | agents rarely delete a single attr row; conscious asymmetry |
| S-07 | Image upload gets its own `image_version`, never bumps metadata `version` | stops image-vs-rename racing |
| S-07 | `world_map_update` (MCP) takes an OPTIONAL `expected_version`; present ⇒ OCC-gated + conflict names the current version; absent ⇒ last-write-wins | agent parity with REST If-Match without forcing every caller to read a version first |
| S-07 (D-S07-world-delete-guard) | `world_delete` (MCP) is a direct TierA owner-scoped hard delete BUT REFUSES while the world holds non-bible member books (agent must move/remove them first) | `books.world_id` is ON DELETE SET NULL, so a naked delete silently ORPHANS the user's books — the guard keeps the tool to "clean up a world you mis-created" without a one-shot nuke, and is cheaper than the full TierW confirm spine |
| S-07 | `book_chapter_reorder` (MCP) takes the COMPLETE ordered chapter-id list for one language track and requires an exact permutation (same length + all-belong + no dupes) | a partial/foreign list would strand a `sort_order` slot; reject rather than silent-partial. Shares the two-phase engine (`lockActiveChapterTrack`+`writeChapterTrackOrder`) with the REST route |
| S-08 | Motif/arc-template restore mirrors `canon_rules.restore` exactly | the "complete" reference |

## Still needs a PO call (NOT sealed — do not build the affected item)

| Q | Decision needed |
|---|---|
| ~~G-WORKFLOWS~~ | **SEALED 2026-07-17: BUILD IN THIS TRACK (→ S-12).** PO decided ownership. CLARIFY-verify shrank it — the proposals routes + a workflows LIST already exist; only 3 backend verbs (get-one/delete/enablement, mirror skills) + the FE panels are missing. |
| **S-11 category** | ~~Which category does the `search` panel belong to?~~ **RESOLVED at S-11 build (D-S11-category): `knowledge`** — joins the kg-* group (semantic search = knowledge drawers), avoids a new top-level category (which would churn CATEGORY_ORDER + palette.group i18n + the frontend-tools contract). |

## Build-readiness

**All 12 specs (S-01..S-12) are sealed and buildable — nothing is parked.** Per D-order, the Tier-A four
(S-01, S-02, S-03, S-04) fan out in parallel; Tier-B/C (incl. S-11, S-12) follow. Each build runs the full
workflow (VERIFY evidence, 2-stage review, `/review-impl` for the data-layer/tenancy specs, live-smoke ≥2
services where the spec crosses a service boundary).

**S-11's panel category is now RESOLVED** (`knowledge`, D-S11-category, sealed at the S-11 build 2026-07-18).
No open details remain across the sealed specs.
