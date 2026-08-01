# 09 — Interaction Layer: Graphical-Medium Reconciliation

> **Status:** **RESOLVED + LOCKED (2026-06-20).** Reconciles the player-facing interaction layer to
> the rendered 2D/2.5D medium ([`00_VISION.md` §0](00_VISION.md)). Companion to
> [`08_realtime_movement_authority.md`](08_realtime_movement_authority.md) (the server half); this is
> the **player-facing half** of the medium correction.
> **Two findings:** (1) the interaction *semantics* survive the medium change **100%** — only the
> *input method* and *output medium* were text-shaped; (2) the survey surfaced a **position-model
> contradiction** between the just-locked RTM spec and the existing locked `EF_001` / `CSC_001`,
> resolved here (§4) and applied to those docs additively.
> **Decisions** `ILR-D1..D9` recorded in [`decisions/locked_decisions.md`](decisions/locked_decisions.md);
> namespace in [`00_foundation/06_id_catalog.md`](00_foundation/06_id_catalog.md).
> **Lock-gated remainder:** `_boundaries/` ownership-matrix touch for the revised CSC_001/EF_001 rows
> needs a `_LOCK.md` claim.

---

## 1. The reframing principle

The locked interaction design separates four concerns. Only two were text-shaped:

| Concern | Owned by | Text-era form | Status |
|---|---|---|---|
| **Logical action** | PL_005 (4-role: agent / tool / direct-targets / witnesses; closed verbs Speak/Strike/Give/Examine/Use) | — | ✅ **unchanged** |
| **Validators + tool-call allowlist** | PL_002 §7.4, PL_005 pipeline (server-side) | — | ✅ **unchanged** |
| **Input method** | PL_002 command grammar | typed `/verbatim`, `/prose`, `/travel`, `/chat @x` | 🔁 **reframed** → UI / spatial |
| **Output medium** | narration | narrator prose | 🔁 **reframed** → visual + prose sub-layer |

> **ILR-A1 — The interaction *envelope* is medium-agnostic; only input capture and output
> presentation are medium-specific.** The parser + A5 intent-classifier + validator pipeline + the
> EVT-T1/T6 command envelopes stay **server-side and unchanged**. The frontend maps UI/spatial
> gestures onto the *same* envelopes and renders outcomes from the *same* event stream. Zero core
> decision rows (C1-D1..D5, PL_002 §6, PL_005 4-role, DF5-A1..A11) change.

---

## 2. Per-decision reframing (input method + output medium)

| Locked decision | Text-era form | Graphical reframe | Survives as |
|---|---|---|---|
| **C1 voice modes** (terse/novel/mixed; `/verbatim`,`/prose`) | per-turn typed override of narrator prose | a **dialogue-rendering preference** (Settings → Dialogue Style), applied to how speech/narration renders (speech bubble vs prose pane). Not an input mode. | dialogue/narration **sub-layer** |
| **C5 multi-stream UI** (tabbed say/narration/system/whisper) | the primary UI surface = text streams | **HUD panels**: speech bubbles + subtitle pane (dialogue), combat/action log (system), toasts (events). One panel of the HUD, not the interface. | HUD information architecture |
| **PL_002 command grammar** (typed `/verb`) | every action = typed slash command | **UI / spatial gestures** map to the same envelopes: map-click → `travel`, NPC-click → `speak`/session, drag-to-NPC → `give`, click-to-examine → `examine`. Slash commands survive as an **optional power-user / chat affordance**. Parser + classifier stay backend. | the action model (backend envelopes) |
| **DF05 sessions** (`/chat @a @b`) | session created by typed command | **NPC right-click → "Talk"** / multi-select; sparse-session structure, caps, POV-distill, anchor invariant all **intact**. | session architecture (unchanged) |
| **PL_005 interaction output** | "You strike the bandit…" prose | **visual primary** (animation, HP-bar delta, SFX) + **prose sub-layer** (speech bubble / subtitle). | 4-role payload (unchanged) |

> **ILR-D1..D6** capture these (see §5). None touches game logic — they pin *presentation*.

---

## 3. What graphical-client design already exists vs. is missing

**Exists (spatial substrate, ready to build on):** `TMP_001` tilemap generation (deterministic),
`CSC_001` cell-interior 16×16 composition (fixtures + occupant zones), `MAP_001` authored world
graph, `EF_001` `entity_binding` (cell-level location). Plus `08` (RTM) now supplies the
realtime movement + AOI + presence layer that the survey flagged as "missing."

**Still genuinely missing — pure client-presentation, a separate V1 client-build track (NOT
interaction logic):** camera/viewport system, HUD layout, avatar/emote animation, input mapping
(mouse/keyboard/gamepad). Tracked as client-build items (§7), not reframing.

---

## 4. Position-model reconciliation (the contradiction)

**The conflict the survey surfaced:**
- `EF_001 entity_binding` tracks location as `EntityLocation::InCell(cell_id)` — **cell-granular**.
- `CSC_001` Layer 3 places occupants by per-entry **LLM zone-assignment** ("counter:behind", "table:seated") — coarse, recomputed on occupant-set change.
- `08` **RTM** assumes **continuous near-realtime position** streamed at ~10 Hz on a spatial grid.

These describe three *different* notions of "position." They are reconciled as **three stacked
layers**, not competitors:

> **ILR-A2 — Position is a three-layer stack.**
> 1. **Coarse cell membership** — `entity_binding.InCell(cell_id)` (EF_001). Authoritative, durable,
>    **evented only on the cell transition** (which is exactly RTM-A1's "semantic transition →
>    event"). Answers *which cell*.
> 2. **Continuous within-area position** — RTM-owned, **ephemeral**, ~10 Hz (08 RTM-A1). Answers
>    *where on the tilemap*. Never in the event log; periodically checkpointed.
> 3. **Static scene composition** — `CSC_001` fixtures (furniture; deterministic, unchanged) +
>    occupant **zone-assignment** for *ambient* placement & *spawn* layout.

> **ILR-A3 — Hybrid NPC movement.** *Ambient* NPCs keep `CSC_001` deterministic zone-placement
> (zero realtime cost — 95%+ of NPCs, matching the DF05 sparse-session model). **PCs always**, and
> **NPCs while engaged** (in a session or combat), carry **live RTM position** (layer 2) that
> **supersedes** their `CSC_001` zone-assignment for as long as they are engaged. On disengage they
> resolve back to a zone placement. The AOI/grid (RTM-A6..A8) tracks only **live** entities.

**Consequence:** `CSC_001` Layer 3 zone-assignment is reframed from "the occupant's position" to
"the occupant's *ambient/spawn* placement; superseded by RTM live position while engaged."
`entity_binding.InCell` is reframed from "the position" to "the coarse cell membership; fine position
is RTM-ephemeral." Both revisions are **additive** (applied this pass — §6).

---

## 5. Decisions (RESOLVED 2026-06-20)

| # | Decision | Resolution |
|---|---|---|
| **ILR-D1** | Interaction semantics under medium change | ✅ **Unchanged** — only input method + output medium reframe (ILR-A1). |
| **ILR-D2** | C1 voice modes | ✅ **Dialogue-rendering preference** (UI setting), not an input mode. |
| **ILR-D3** | C5 multi-stream UI | ✅ **HUD panels** (speech bubbles / subtitle / combat-log / toasts), not chat windows. |
| **ILR-D4** | PL_002 command grammar | ✅ **Backend envelopes unchanged**; frontend maps UI/spatial gestures; slash commands optional power-user affordance. |
| **ILR-D5** | DF05 session creation | ✅ **NPC-click / multi-select**; sparse-session structure intact. |
| **ILR-D6** | PL_005 interaction output | ✅ **Visual primary + prose sub-layer.** |
| **ILR-D7** | Position model | ✅ **Three-layer stack** (ILR-A2): coarse cell membership (EF_001) · continuous RTM-ephemeral · static CSC composition. |
| **ILR-D8** | NPC movement | ✅ **Hybrid** (ILR-A3) — ambient zone-placed; PCs + engaged NPCs live; AOI tracks live only. |
| **ILR-D9** | CSC_001 / EF_001 contradiction | ✅ **Revised additively this pass** (§6) — no rewrite of game logic. |

---

## 6. Doc revisions applied (this pass)

- **`CSC_001`** — Layer 3 occupant zone-assignment reframed as *ambient/spawn placement, superseded by
  RTM live position while an occupant is engaged*; added a reconciliation note pointing here + to 08.
- **`EF_001`** — `entity_binding.InCell(cell_id)` clarified as *coarse cell membership* (evented on
  cell transition); fine continuous position is **RTM-ephemeral, not in `entity_binding`**.

Both are dated additive notes (candidate-lock preserved; no decision row removed). The
`_boundaries/` ownership-matrix touch for these rows remains **lock-gated** (pending `_LOCK.md`).

---

## 7. Still-missing graphical-client design (tracked, not reframing)

Pure client presentation — a **V1 client-build track**, distinct from interaction logic:
camera/viewport · HUD layout · avatar + emote animation · input mapping (mouse/kbd/gamepad) ·
client-side interpolation tuning (RTM-Q6). These do not reopen any locked decision; they are net-new
client work and should get their own doc when the client build begins.

---

## 8. Cross-references

- Medium statement — [`00_VISION.md` §0](00_VISION.md)
- Server half (realtime movement authority) — [`08_realtime_movement_authority.md`](08_realtime_movement_authority.md) (RTM-A1, RTM-A6..A8)
- Voice modes / multi-stream — [`01_problems/C_product_ux.md`](01_problems/C_product_ux.md) (C1, C5)
- Command grammar — [`features/04_play_loop/PL_002_command_grammar.md`](features/04_play_loop/PL_002_command_grammar.md)
- Interaction model — [`features/04_play_loop/PL_005_interaction.md`](features/04_play_loop/PL_005_interaction.md)
- Sessions — [`features/DF/DF05_session_group_chat/`](features/DF/DF05_session_group_chat/)
- Entity location — [`features/00_entity/EF_001_entity_foundation.md`](features/00_entity/EF_001_entity_foundation.md)
- Cell scene — [`features/00_cell_scene/CSC_001_cell_scene_composition.md`](features/00_cell_scene/CSC_001_cell_scene_composition.md)
- Decisions / IDs — [`decisions/locked_decisions.md`](decisions/locked_decisions.md) · [`00_foundation/06_id_catalog.md`](00_foundation/06_id_catalog.md)
