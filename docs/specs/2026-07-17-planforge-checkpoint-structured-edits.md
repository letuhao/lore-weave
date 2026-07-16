# PlanForge — structured checkpoint edits (D-S3-CHECKPOINT-STRUCTURED-EDITS)

> **Status:** detail spec (design). NOT built. Origin: S3 /review-impl removed a raw-JSON edit
> textarea from `CheckpointReview` (it violated the pass-rail draft's "no raw JSON/spec editor;
> viewer is read-only" callout, and a whole-doc deep-merge cannot express a deletion). The checkpoint
> review currently ships **read-only** (view → approve/reject/seed-gate). This spec designs the
> structured "Save edits" (F-P10) that should replace the banned raw editor.

## 1 · The problem

At a **blocking checkpoint** (cast, beats) the author needs to *correct* what the pass produced
before approving — rename a character, fix a wrong role, drop a spurious cast member, reorder beats.
The backend already supports this: `POST /checkpoint {approved:false, pass_id, edits}` **deep-merges**
`edits` into the pass artifact, saves a NEW artifact (so everything downstream re-stales by derivation,
PF-3), and records `decision=rejected` (F-P10 — "Save edits is not a hold").

Two hard constraints make the UX non-trivial:

1. **No raw JSON editor** (sealed, draft callout). A free-form textarea over the artifact is a second,
   un-derived write channel and invites malformed writes. The editor must be **structured** — it
   understands the artifact's shape.
2. **Deep-merge cannot delete.** `{"roster": [...]}` deep-merged onto the old artifact *adds/overrides*
   keys; it can never *remove* a roster entry. A user who deletes a cast member in a naive editor gets
   a silent no-op — the member persists. This is the exact silent-success bug /review-impl caught.

And the artifacts are **polymorphic**: `cast_plan` is a roster of {name, role, trait}; `beat_plan` is
an ordered curve of beats; `world_plan`, `char_arc_plan`, `scene_plan` each differ. One editor cannot
serve all shapes.

## 2 · Design

### 2.1 Per-artifact-kind editors, registered like a small strategy table
A `PASS_EDITORS: Record<PlanArtifactKind, PassEditorComponent>` map. Each editor:
- takes the artifact content (read via BE-3, already built),
- renders a **structured form** (cast → an editable list of member rows with add/remove; beats → an
  ordered, reorderable/removable beat list),
- emits a **patch** in the protocol below — never a raw blob.

Ship order: **`cast_plan` first, then `beat_plan`** (the two blocking checkpoints — the only passes
that *gate* the compiler, so the only ones where an edit-before-approve is load-bearing). Advisory
passes (world/arcs/scenes/self_heal) can re-run instead of edit; their editors are follow-ups.

### 2.2 The patch protocol — solve the deletion problem at the boundary
The deep-merge-can't-delete problem is a **backend contract** question, not an FE one. Pick ONE:

- **Option A — list fields are REPLACE, not merge (recommended).** `POST /checkpoint` learns that for a
  known artifact kind, the top-level list field (`roster`, `beats`) is **replaced wholesale** from the
  patch, while scalar/object fields still deep-merge. The FE editor sends the full edited list; a
  removal is expressed by the list simply being shorter. Simple, no sentinels, matches how a user
  thinks ("here is the roster I want"). The cost: two concurrent edits to the same list last-write-win
  the whole list (acceptable — checkpoint edits are single-author, pre-approval).
- **Option B — tombstone sentinels.** The patch carries `{"roster": {"$remove": ["id-3"]}}`. More
  expressive (targeted removal, concurrent-safe) but a new merge dialect the backend must implement +
  the FE must build, and it leaks merge mechanics into the UX.

**Recommendation: Option A**, scoped to the known blocking kinds (cast, beats), because the checkpoint
is a single-author pre-approval gate — full-list replace is both simpler and matches intent. Document
the replace-vs-merge rule per artifact kind in `plan_pass_service` (the registry that already owns the
pass contracts).

### 2.3 Where the edit lands
`CheckpointReview` gains, per its pass kind, `<PassEditor kind={...} content={...} onPatch={...}/>`
between the read-only view and the approve/reject row. "Save edits" sends the patch through the
already-wired `onReview(false, patch)` path (reject + edits) — the plumbing exists; only the editor +
the replace-semantics are new.

## 3 · Acceptance criteria (the falsifiable bar)
1. At the **cast** checkpoint, the author can **add**, **edit a field of**, and **REMOVE** a roster
   member; Save edits → the new artifact reflects all three (a live smoke that removes a member and
   re-reads the artifact — a removal must actually be gone, the anti-silent-success test).
2. Downstream passes go **stale** after a save (PF-3 by derivation — assert `world.fresh == false`
   after a cast edit).
3. No raw-JSON textarea anywhere in the checkpoint (the draft ban holds; a grep guard).
4. `beat_plan` editor: reorder + remove a beat, same guarantees.
5. Unit: the patch protocol (replace vs merge) has a backend test proving a shorter list REMOVES.

## 4 · Open questions for the PO
- **OQ-1:** Option A (list-replace) vs B (tombstones)? (spec recommends A.)
- **OQ-2:** ship only cast+beats editors in v1, advisory-pass editors deferred? (spec recommends yes.)
- **OQ-3:** should "Save edits" stay `decision=rejected` (F-P10), or is a "save + keep pending" mode
  wanted so the author can edit then approve in one step rather than edit(reject)→re-open→approve?
  (F-P10 says rejected; but the 2-step flow is awkward — worth a PO ruling.)

## 5 · Effort / risk
S–M per editor (cast ~S, beats ~S) + one backend change (the replace-semantics in `review_checkpoint`
+ its test). No migration. The risk is entirely in OQ-1/OQ-3 — decide those before building.
