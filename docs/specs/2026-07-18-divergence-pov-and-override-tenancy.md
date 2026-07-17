# Spec — POV-shift derivative consumption (pov_anchor) + override cross-book tenancy verify

> **Status: CLARIFY (2026-07-18).** Two deferred items from the S-04 (derivative delta editing) build, now
> spec'd. Part A is a real feature (a `pov_shift` dị bản should actually generate from its POV character).
> Part B formalizes a conscious won't-fix into a documented decision + a ready build-path.
>
> **Provenance:** deferred in [`2026-07-17-studio-completeness-build/RUN-STATE_S03-S04.md`](2026-07-17-studio-completeness-build/RUN-STATE_S03-S04.md)
> (DEBT register). S-04 shipped `divergence_spec.pov_anchor` as writable (PATCH + Clear) but INTENTIONALLY did
> not build a re-pick picker, because the field is **write-only at HEAD** — nothing reads it — so a picker
> would write a maybe-wrong-id-space value nothing consumes (a shell). This spec defines the consumer FIRST
> (which pins the id-space), then the picker.

---

## CLARIFY summary — what's resolved vs what needs a PO call

| # | Question | Status |
|---|---|---|
| CV-A2 | `pov_anchor` id-space | **RESOLVED (code): glossary entity id, used directly (no knowledge→glossary remap)** |
| CV-A4a | Does POV reach the prompt today? | **RESOLVED (code): NO — scene POV is unrendered; only implicit as a `<present>` cast bio** |
| CV-A4b | Does the packer see taxonomy/pov_anchor today? | **RESOLVED (code): NO — PackRequest carries only source/branch/overrides; get_spec_for_work uncalled on pack path** |
| CV-B | Is a foreign override/anchor target a tenancy breach? | **RESOLVED (code): NO — no-op + book-scoped present lens; conscious won't-fix** |
| **PO-1** | Consumption model — default-fill (A3-1) / hard-override (A3-2) / additive (A3-3)? | **NEEDS PO** — recommend **A3-1 default-fill** |
| **PO-2** | Rendering — grounding-only (A4-grounding) or explicit `pov=` line + cowrite steer (A4-explicit)? | **NEEDS PO** — recommend **A4-explicit** (also fixes the scene-POV gap) |
| **PO-3** | Gate consumption on `taxonomy=='pov_shift'`, or apply whenever `pov_anchor` is set? | **NEEDS PO** — recommend **apply-when-set** (for a derivative Work), taxonomy is a label not a gate |

**Do not build Part A until PO-1/2/3 are decided.** All three have a recommendation; none blocks the others.

---

## Part A — Make a `pov_shift` derivative generate from its POV character

### A.1 Current state (verified at HEAD, 2026-07-18)

```
divergence_spec (migrate.py:146)
  taxonomy CHECK('pov_shift'|'character_transform'|'au')
  pov_anchor UUID?   ← "the POV entity for a POV-shift derivative" (migrate.py:142) — STORED, read by NOBODY
  canon_rule TEXT[]
```
`grep pov_anchor` across `services/composition-service`: only writes (create_spec / update_spec / derive),
the model, and tests — **no engine/packer/prompt read**. So the field is inert. A `pov_shift` dị bản today
diverges only via `entity_override` + `canon_rule`; the "shift the narrator to character X" intent it names
is **never realized in the generated prose**.

The SEPARATE, live concept is the **scene-level POV**: `outline_node.pov_entity_id`, packed by the beat lens
(`packer/lenses.py:210-214` → `beat.pov_entity_id`) and used by generation (`engine/cowrite.py:30` —
"Draft this scene from its beat, goal, POV, and synopsis"). `pack.py:261-263` also unions `pov_entity_id`
into `present_ids` so the POV character's bio is in-context. **This is the seam pov_anchor must connect to.**

### A.2 id-space (THE load-bearing decision) — RESOLVED: **glossary entity id**

**`pov_anchor` = a `glossary_entity_id` (the glossary anchor), used DIRECTLY (no resolution step.)**

Traced: `pov_entity_id` + `present_entity_ids` are folded into one `present_ids` list at `pack.py:261-263`
and passed straight to the present lens. `gather_present` (`lenses.py:129-177`) keys on the **glossary**
`entity_id` — its docstring is explicit: *"we cache the STABLE glossary entity_id, not knowledge's
rename-sensitive canonical_id"* (`lenses.py:137-138`); the worker calls them `cast_glossary_ids`
(`operations.py:351`). So `pov_entity_id` is glossary-anchor space, used as-is with **no** knowledge→glossary
remap.

⚠ **Contrast — do NOT copy the override lineage.** `entity_override.target_entity_id` gets a knowledge→glossary
remap (`_resolve_override_anchors`, `pack.py:730`) because "the C24 wizard records the knowledge node id". The
POV path does NOT and MUST NOT — `pov_anchor` is stored/consumed as a glossary anchor with no resolution. (This
also means the FE picker must supply `glossary_entity_id`, which it does — see A.5. Passing the knowledge node
id `e.id` instead would silently fail to match the present lens.)

### A.3 The consumption model — three options (PO decision)

When packing a scene for a **derivative Work whose `divergence_spec.pov_anchor` is set**, how does the anchor
affect the effective POV?

| Option | Rule | Trade-off |
|---|---|---|
| **A3-1 default-fill (RECOMMENDED)** | `effective_pov = scene.pov_entity_id ?? pov_anchor` — the anchor is the derivative's DEFAULT POV; a scene that sets its own POV wins | Respects author intent per-scene; the anchor covers every un-set scene. A retelling "from Kai's eyes" makes Kai the narrator everywhere the author didn't override. |
| **A3-2 hard-override** | `effective_pov = pov_anchor` (always) for a pov_shift derivative | Truest to "the WHOLE book is now X's POV", but silently discards a scene POV the author deliberately set (e.g. one interlude from another head). |
| **A3-3 additive directive** | keep scene POV; ADD a system directive "this is a POV-shift retelling anchored on ⟨name⟩" | Non-destructive but vague — the LLM decides, so it under-delivers (the pov_shift becomes flavor text, not a real constraint). |

Recommendation: **A3-1 default-fill.** It's the least-surprising, preserves per-scene authoring, and makes the
anchor load-bearing (not flavor). The effective pov then flows through the EXISTING beat + present + union-cast
machinery unchanged — so the POV character's bio is auto-included and the prompt's "draft from POV" already
consumes it.

Open sub-question: **gate on `taxonomy == 'pov_shift'`, or apply whenever `pov_anchor` is set?** Taxonomy is a
free-ish label (S-01 CV-1 established taxonomy isn't a hard semantic gate elsewhere). Recommend: **apply
whenever `pov_anchor` is set** (the anchor IS the data; taxonomy is the human label) — but only for a
DERIVATIVE Work (source_work_id set). This avoids a "user set pov_shift but the shift did nothing" dead-end.

### A.4 The rendering fork — grounding-only vs explicit POV (THE second decision) + the injection wiring

**Discovery that reframes this:** the scene-level `pov_entity_id` is **itself never rendered as an explicit
POV instruction**. The `<beat>` serializer (`assemble.py:85-94`) emits `beat=/goal=/synopsis=` but **drops
`pov_entity_id`**; there is **no id→name resolution** in the render path. Today POV reaches the LLM only
*implicitly* — `pack.py:262` folds `pov_entity_id` into `present_ids`, so the POV character's bio appears in
the `<present>` block (`assemble.py:77-83`) indistinguishable from the rest of the cast. The
`cowrite.py:30` steer *"Draft this scene from its beat, goal, POV, and synopsis"* has **no explicit POV
backing**.

So two consumption levels:

| Level | Edits | Result |
|---|---|---|
| **A4-grounding** (cheap) | fold `pov_anchor` into `present_ids` (the existing seam) | the POV character's BIO grounds the pack. But nothing marks it as the POV — same implicit, weak outcome as scene POV today. **This is the A3-3 "flavor" outcome the user rejects** — the pov_shift barely differs from an override. |
| **A4-explicit** (RECOMMENDED) | resolve effective_pov (glossary anchor) → **name**, render a `pov=<name>` line in the `<beat>` block, and steer cowrite to write from it | "write from X's POV" becomes a real constraint. **Bonus: this also fixes the pre-existing gap that SCENE `pov_entity_id` is unrendered** — the same render line serves both scene POV and the derivative anchor. |

**Recommendation: A4-explicit** — grounding-only reproduces the exact weak result we're trying to escape, and
the explicit render is a small, high-leverage fix that repays the whole POV feature (scene + derivative).

**Injection wiring (taxonomy/pov_anchor do NOT reach the packer today — verified):** `PackRequest`
(`pack.py:58-91`) carries only `source_project_id` / `branch_point` / `overrides`; `build_derivative_context`
(`pack.py:140-178`) resolves those three and NEVER reads the divergence spec. `get_spec_for_work`
(`derivatives.py:109`) exists but is uncalled on the pack path. Three small edits at one choke point:
1. In `build_derivative_context` (`pack.py:140`) also `await derivatives_repo.get_spec_for_work(work.id)` and
   surface `taxonomy` + `pov_anchor` on `DerivativeContext` (self-syncing — re-read every pack, no cache,
   mirroring `apply_entity_overrides`).
2. Add `taxonomy` + `pov_anchor` fields to `PackRequest` (`pack.py:58`), populated at each router site that
   builds a `PackRequest` from `deriv`: `engine.py:398-410` (primary SSE `/generate`), `:780`, `:989`,
   `grounding.py:98`, `approve.py:107`.
3. At the `present_ids` seam (`pack.py:261`), compute `effective_pov = node.pov_entity_id ?? (pov_anchor if
   is_derivative else None)` (A3-1 default-fill), fold it into `present_ids` (grounding), AND pass it to the
   new render/name-resolution step (A4-explicit).

### A.5 Frontend — the re-pick picker (the originally-deferred item)

Once A.2/A.4 pin the id-space + consumer, add a pov-anchor picker to `DivergenceSpecEditor` (the S-04 editor
already has Clear). Reuse the wizard's Step3 entity source (`knowledgeApi.listEntities` over the derivative's
SOURCE project) — the SAME anchored-entity list the override picker uses — so the picked id is in the correct
space by construction (no raw-UUID input). Show the current anchor's resolved name (via the same
`entityByAnchor` map `useDivergenceSpecEditor` already builds) instead of the raw UUID.

### A.6 Tests
- **default-fill:** a derivative with `pov_anchor=X` + a scene with no `pov_entity_id` → `effective_pov == X`;
  X is in `present_ids` (bio grounds). A scene WITH its own POV keeps it (A3-1).
- **explicit render (A4-explicit):** the `<beat>` block renders `pov=<X's name>` (glossary anchor → name
  resolved); a scene with its own POV renders that name — proves the pre-existing scene-POV gap is closed too.
- **inert-when-unset:** a derivative with no `pov_anchor` (and a canonical Work) packs byte-identically to
  today (regression — no `pov=` line, no present change).
- **book-scope safety:** a `pov_anchor` that is a foreign glossary id → no `<present>` bio added, no leak (B.2).
- **FE:** the picker offers only anchored SOURCE-project entities; picking one PATCHes `{pov_anchor: <glossary
  anchor>}`; the row shows the resolved name (via `entityByAnchor`); Clear still works.

### A.7 Out of scope
- Per-scene POV re-authoring (that's the existing outline editor's job).
- `character_transform` / `au` taxonomies gaining their own generation semantics — separate specs if wanted.

---

## Part B — Override / pov cross-book `target_entity_id` tenancy verify

### B.1 The concern (S-04 spec §4)

`entity_override.target_entity_id` (and, once Part A lands, `pov_anchor`) is a cross-DB entity id with **no
FK**. A caller with EDIT on book A could POST an override whose target is an entity from book B.

### B.2 Why it is NOT a breach at HEAD (verified)

- **No data leak / cross-tenant write.** The packer applies overrides ONLY within the derivative's own
  knowledge partition, keyed on the present item's glossary anchor (`merge.py apply_entity_overrides`). A
  foreign `target_entity_id` simply never matches any present item → **silent no-op**, exactly like the
  wizard's "unanchored entity" case. It reads/writes nothing of book B.
- **The present lens is BOOK-scoped** (`pack.py:409` — *"the glossary `present` lens is BOOK-scoped"*). So
  even a CONSUMED foreign glossary anchor (a `target_entity_id` OR a `pov_anchor` from book B, once Part A
  wires pov_anchor into `present_ids`) is resolved against book A's glossary — where it isn't present — so it
  pulls **no** book-B bio. This is why Part A does **not** open a leak (see B.4-#1).
- **Symmetric with the existing writer.** The derive-time writer (`perform_derive` → `create_override`) does
  NOT verify targets either. Adding a verify only on the post-derive path would be an inconsistent, partial
  guard.
- **The FE already prevents it.** The S-04 override picker + the future pov picker offer ONLY anchored
  entities from the derivative's source project — a foreign id can't be sent through the GUI.

⇒ **Decision: conscious won't-fix (defer gate #5).** It is a data-quality nit (a dangling reference), not a
tenancy breach.

### B.3 The hardening design — IF a trigger fires (ready, not built)

Build only if a trigger in B.4 occurs. The design:
- At `add_override` / `update_override` (and `pov_anchor` set), resolve `target_entity_id` → its owning book
  via a knowledge-service lookup, and reject (404, anti-oracle) when it ≠ the derivative's book. Apply the
  SAME check at the derive-time writer for symmetry (close the whole window, not half — see the
  [close-legacy-window-in-writer] lesson: fix the writer, not just the new path).
- Cost: one cross-service call per override write (or a batch resolve at derive). Acceptable for a write path;
  it must degrade to "allow" on a knowledge outage (never 500 an authoring write over a hardening check), OR
  fail-closed — a PO call at build time.

### B.4 Triggers that would promote B.3 from won't-fix to build
1. ~~Part A makes `pov_anchor` consumption harmful for a foreign id.~~ **CHECKED — does NOT fire.** The present
   lens is book-scoped (B.2), so a foreign glossary anchor consumed via `present_ids` pulls no book-B data.
   Part A is safe to ship WITHOUT B. (Re-confirm this one fact if Part A's implementation ever queries an
   entity OUTSIDE the book scope.)
2. A non-GUI writer (a bulk import, a public MCP key) starts creating overrides/anchors at scale where the FE
   guard doesn't apply — dangling targets could accumulate.
3. A multi-tenant data-quality audit flags dangling override/anchor targets as a real problem.

**No trigger is active. B stays a documented conscious decision — no code.**

---

## Sizing + build order
- **Part A: M** (schema untouched; new pack-path read + a beat-lens default-fill + FE picker + tests; crosses
  no service boundary — all composition-service + its FE). Full CLARIFY→…→RETRO when built.
- **Part B: XS-if-ever** (a route-level verify + symmetric derive-time verify), gated on a B.4 trigger.
- **Order:** A before B (A.2's id-space + present-lens book-scope decides whether B.4-#1 fires — so resolve A
  first, then re-confirm B stays won't-fix).
