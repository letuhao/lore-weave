# 10 — Medium-Correction Blast-Radius Audit

> **Status:** COMPLETE (2026-06-20). A deliberate decision-by-decision sweep of the locked design
> for *silent text-medium assumptions* beyond the two already resolved (movement authority — 08;
> interaction layer + position model — 09). Run as four parallel domain audits.
> **Verdict:** the medium correction is **substantially complete.** No further RTM/position-model-sized
> structural contradictions exist. One new (small) structural finding + two cosmetic clarifications;
> the rest of the design is medium-agnostic.
> **Why this doc exists:** twice the "steady-state, 2 OPEN" closure was found to hide medium-era debt
> (movement authority, position model) almost by accident. This sweep closes that gap *deliberately* —
> so "the rest is clean" is an audited claim, not an assumption.

---

## 1. Method

Four parallel auditors, each given the corrected medium (`00_VISION.md` §0) + the already-resolved
08/09 set, told to hunt **structural** contradictions (the kind that need a design decision), classify
severity (STRUCTURAL / COSMETIC / NONE), and be honest about clean clusters:

| Auditor | Cluster |
|---|---|
| A | Player-experience · product-UX · play-loop · onboarding · multiverse disclosure UX |
| B | World · spatial · travel · geography · tilemap · time-dilation |
| C | Combat · progression · character systems · resources · AI-tier · NPC |
| D | Social · meta · platform · narrative · world-authoring |

---

## 2. Findings

| ID | File | Assumption | Severity | Resolution |
|---|---|---|---|---|
| **AUD-F1** | `features/18_combat/00_CONCEPT_NOTES.md` §6 | V1 combat has **no zone-graph movement** ("no Move verb V1; abstract"), but Skill/Strike **target selection UI** is unspecified for the graphical client — how does a player pick a target with no spatial grid? | **STRUCTURAL (new)** | **OPEN — recommended:** V1 combat targeting is **roster/party-list-based** (select ally/enemy from a turn-select list, à la Pokémon / Honkai: Star Rail), *not* spatial-grid. Zone-targeted skills → V2+ when a combat zone-graph lands. Confirm + record as a COMB decision. |
| **AUD-F2** | `features/18_combat/00_CONCEPT_NOTES.md` §6 row-mechanic | Front/Back **row** reads like a spatial position, but V1 defers zone graph. | **COSMETIC** | V1 row is a **damage modifier / stat badge**, not a visual position; all combatants render at one depth; row promotes to real grid position V2+. Clarify in COMB doc. |
| **AUD-F3** | `features/04_play_loop/PL_002_command_grammar.md` §13 ACs | Acceptance criteria test slash-command parsing only; ILR-D4 locked "UI gestures primary, slash optional" but it isn't **tested**. | **COSMETIC (testability)** | Add an acceptance criterion: *UI gesture → Interaction mapping* (map-click→travel, NPC-click→speak, drag→give) resolves to the same envelopes. Makes ILR-D4 enforceable. |
| **AUD-F4** | `C_product_ux.md` C5 · `cat_11_CC_cross_cutting.md` CC-1 · onboarding copy | Residual "chat window / stream / tab" vocabulary from the text era. | **COSMETIC** | Terminology pass: "chat window" → "HUD panel", "stream" → "pane", "tab" → "toggle". Non-blocking; do opportunistically. |

Everything the auditors initially flagged as structural beyond AUD-F1 (voice modes, onboarding
visual-drop-in, scene zone-placement) was confirmed **already resolved** by 08/09 (ILR-D2, ILR-A1,
ILR-A3) — not re-opened here.

---

## 3. Confirmed clean (medium-agnostic — no action)

The audit explicitly cleared these as data-tier / mechanical / already-graphical, with narrative as a
sub-layer per `00_VISION.md` §0:

- **World/spatial:** travel (TVL_001..005 — turn-based travel is a *separate time scale* that coexists
  with realtime local movement per RTM-Q1), tilemap (TMP_001..009), geography (GEO_*), place (PF_001),
  time-dilation (TDIL_001 — fiction-time, independent of wall-clock).
- **Combat/systems:** damage formula (engine-clamped), progression (PROG_001), resources (RES_001),
  status effects (PL_006), AI-tier ephemeral NPC generation (AIT_001).
- **Social/meta:** faction (FAC_001), family (FF_001), reputation (REP_001), heresy lifecycle
  (WA_002b), platform charter (PLT_001), titles (TIT_001), succession (PLT_002). All numeric/relational
  data with presentation downstream — zero text-medium coupling.

---

## 4. Net result

The medium correction (text → 2D/2.5D) is **closed** across the design:

| Layer | Where resolved |
|---|---|
| Server / realtime authority | `08_realtime_movement_authority.md` (RTM-A1..A9, RTM-D1..D10) |
| Player-facing interaction + position model | `09_interaction_layer_reconciliation.md` (ILR-A1..A3, ILR-D1..D9) |
| Everything else (this sweep) | substantially clean; 1 open (AUD-F1), 3 cosmetic |

**Only `AUD-F1` (combat targeting UI model) needs a decision.** It's small and has a clear recommended
default (roster-based V1). The rest is cosmetic or already done.

---

## 5. Cross-references

- Medium statement — [`00_VISION.md` §0](00_VISION.md)
- Movement authority — [`08_realtime_movement_authority.md`](08_realtime_movement_authority.md)
- Interaction reconciliation — [`09_interaction_layer_reconciliation.md`](09_interaction_layer_reconciliation.md)
- Combat — [`features/18_combat/`](features/18_combat/)
- Command grammar — [`features/04_play_loop/PL_002_command_grammar.md`](features/04_play_loop/PL_002_command_grammar.md)
