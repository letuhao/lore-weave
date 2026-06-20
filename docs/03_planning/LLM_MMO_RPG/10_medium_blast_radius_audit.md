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
| **AUD-F1** | `features/18_combat/00_CONCEPT_NOTES.md` §6 | V1 combat has **no zone-graph movement** ("no Move verb V1; abstract"), but Skill/Strike **target selection UI** is unspecified for the graphical client. | **STRUCTURAL (new)** | ✅ **RESOLVED 2026-06-20 (user) — TACTICAL GRID in V1.** Combat uses a tactical grid (positions + range/LoS; movement via pathfinding), **reversing** §6/§11.1/§11.3. Justified: grid was deferred *only* for LLM-narration token cost (§139), which the medium correction dissolves (engine-deterministic math + visual render + batched narration). Reuses TMP_001 pathfinding + CSC_001 zone graph + the instanced combat scene (RTM-Q4). Recorded on COMB_001 (dated note) + `locked_decisions`. **Detailed tactical-grid combat design = follow-up before COMB_001 DRAFT promotion.** |
| **AUD-F2** | `features/18_combat/00_CONCEPT_NOTES.md` §11.2 row-mechanic | Front/Back **row** reads like a spatial position. | ~~COSMETIC~~ **SUPERSEDED by AUD-F1** | The Front/Back 2-row metaphor is replaced by **real grid positions** (AUD-F1 tactical grid). No separate action. |
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
| Everything else (this sweep) | substantially clean; AUD-F1 resolved (tactical grid V1), 2 cosmetic remain |

**All findings resolved or cosmetic.** AUD-F1 → tactical grid in V1 (reverses COMB_001's abstract-V1
stance; recorded on COMB_001 + `locked_decisions`; detailed combat-grid design is a follow-up before
COMB_001 DRAFT). AUD-F2 superseded by it. Remaining cosmetic: AUD-F3 (a PL_002 UI-gesture acceptance
criterion) and AUD-F4 (terminology pass) — non-blocking, do opportunistically. The medium correction
is **closed**.

---

## 5. Cross-references

- Medium statement — [`00_VISION.md` §0](00_VISION.md)
- Movement authority — [`08_realtime_movement_authority.md`](08_realtime_movement_authority.md)
- Interaction reconciliation — [`09_interaction_layer_reconciliation.md`](09_interaction_layer_reconciliation.md)
- Combat — [`features/18_combat/`](features/18_combat/)
- Command grammar — [`features/04_play_loop/PL_002_command_grammar.md`](features/04_play_loop/PL_002_command_grammar.md)
