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
| S-08 | Motif/arc-template restore mirrors `canon_rules.restore` exactly | the "complete" reference |

## Still needs a PO call (NOT sealed — do not build the affected item)

| Q | Decision needed |
|---|---|
| **G-WORKFLOWS** | Ownership vs Track C's P-5 — does THIS track build the workflows/workflow-proposals panels, or does Track C own them? Not a build decision; a track-ownership call. The item stays OUT of S-01..S-11 until answered. |
| **S-11 category** | Which category does the `search` panel belong to (`storyBible`, or a new top-level)? Minor; resolve at S-11 build. |

## Build-readiness

S-01..S-11 are **sealed and buildable** except the G-WORKFLOWS item (parked). Per D-order, the Tier-A four
(S-01, S-02, S-03, S-04) fan out in parallel; Tier-B/C follow. Each build runs the full workflow (VERIFY
evidence, 2-stage review, `/review-impl` for the data-layer/tenancy specs, live-smoke ≥2 services where the
spec crosses a service boundary).
