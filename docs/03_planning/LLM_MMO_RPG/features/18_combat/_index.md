# 18_combat — Index

> **Category:** COMB — Combat (V1 simple side-based abstract combat with zone-aware narration; V2+ zone-graph tactical RPG using CSC_001 4-layer scene composition)
> **Catalog reference:** `catalog/cat_18_COMB_combat.md` (NOT YET CREATED — defer to COMB_001 DRAFT promotion)
> **Purpose:** Defines combat resolution including encounter mode, side allegiance, AI action selection, deterministic damage formula, status effect integration, and post-resolution narration. Solves user's V1 combat requirement (simple Pokemon-style hybrid with 2-row positioning; LLM-driven narration but engine-owned math). V2+ promotes to zone-graph tactical RPG using existing CSC_001 zones as battlefield grid (FE-style movement + range + terrain) without breaking TDIL-A5 atomic-per-turn travel. Resolves the long-standing PL_005 Strike "what does combat look like" gap that PROG_001 §9 partially addressed via hybrid LLM-proposes-damage formula.

**Active:** COMB_001 — **Combat Foundation** (CONCEPT 2026-04-27 — Q1-Q9 ALL LOCKED via 4-batch deep-dive 2026-04-27; concept-notes ready for COMB_001 DRAFT promotion; chaos-backend `combat-core` design adoption applied; module decomposition + damage law chain locked)

**Folder closure status:** Open — concept-notes Q-LOCKED phase complete; COMB_001 DRAFT promotion pending boundary lock window. User kickoff confirmed 2026-04-27 post TDIL_001 DRAFT; Q-deep-dive completed same session.

**NOT a foundation tier feature:** Foundation tier remains 6/6 (closed at PROG_001). COMB_001 is a **domain-scale Tier 6 feature** consuming 6 V1 foundations + IDF + FF + FAC + REP + ACT + AIT + TDIL clocks + PROG progression + RES vital_pool + PL_006 status. Opt-in per reality (modern slice-of-life reality may have NO combat; tu tiên / wuxia / sci-fi reality has rich combat).

---

## Why this folder exists

User raised combat as the final V1 design gap 2026-04-27 (post-TDIL_001 DRAFT closure):

> "tiếp theo còn 1 phần nữa cần hoàn thành trong v1 là combat đơn giản, và v2+ combat phức tạp
> tôi đang suy nghĩ về cách làm combat kiểu pokemon hay các game hero tương tự nơi các phe phái đứng về các phía các nhau và tiến hành combat
> hãy giúp tôi review về hệ thống combat trong các game trên thị trường
> nên làm combat kiểu này hay làm kiểu Fire Emblem hay kiểu gì khác?
> chúng ta đã có cell nên có thể làm combat kiểu tactic nhưng khá là khó"

Translation: V1 needs simple combat; V2+ extends to complex. Considering Pokemon-style (factions on opposite sides) vs Fire Emblem (grid tactics) vs other. Cell architecture allows tactic-style but quite hard.

User then LOCKED a critical architectural constraint 2026-04-27 (after market combat survey):

> "về phía LLM, tôi muốn nó can thiệp càng ít hoặc không cho can thiếp luôn, chỉ tham gia quyết định cho AI
> chúng ta nên có 1 combat engine đủ mạnh vì trong combat logic tính toán rất nghiêm ngắt mà AI thường rất ngu, nó sẽ bị ảo giác và calculation tầm bậy"

Translation: LLM intervention should be minimal or zero in combat. LLM only participates in AI decision-making. Combat engine must be strong enough — combat logic is strict math; LLM hallucinates and miscalculates.

→ **CRITICAL CONSTRAINT (COMB-A1 candidate):** Engine owns 100% of combat math (damage / hit / initiative / status / win-loss); LLM ONLY (a) selects actions for AI-controlled NPCs, (b) narrates POST-resolution prose. NEVER propose damage numbers, NEVER override engine results. This **REVERSES** PROG_001 §9 V1 hybrid Strike formula direction (LLM-proposes-damage → engine-computes-damage); PROG_001 closure-pass-extension required at COMB_001 DRAFT.

---

## Recommended V1 architecture (3-layer separation)

**Layer 1 — CombatEngine (deterministic; NO LLM):**
- Initiative queue (HSR-style action value system recommended)
- Damage formula chain (deterministic; seed = `(reality_id, turn_id, actor_id, action_idx)`)
- Hit/dodge roll
- Status effect tick (delegates to PL_006 — already engine-driven)
- Critical/elemental modifiers (V1 stub; V1+ DF7 expand)
- Win/lose detection (HP=0 → WA_006 mortality state transition)

**Layer 2 — AIDecisionLayer (LLM PARTICIPATES — only for Major NPCs):**
- PC actor: action selection from User UI command
- Major NPC (AIT_001 Tracked tier): NPC_002 Chorus AssemblePrompt(combat_ctx) → LLM returns structured `ActionDecl` (Pydantic-validated; reject + fallback Defend if hallucinates non-existent action)
- Minor NPC (AIT_001 scripted tier): minor_behavior_scripts.reaction_table → deterministic; ZERO LLM call
- Untracked NPC (AIT_001 ephemeral tier): bulk-resolved by engine; ZERO LLM call (engine treats group as a single damage source)

**Layer 3 — NarrationLayer (LLM POST-RESOLUTION ONLY):**
- Input: `ResolutionResult` (already computed by Layer 1 — `{damage, hit, status_applied, ko}`)
- LLM receives "Strike for 47 damage on Hostile #2, crit" → outputs prose narration paragraph
- LLM CANNOT modify damage; only describes
- Batched: 1 LLM call per round narrating ALL actions (token-efficient)

**Why this works:** LLM does what LLM does well (dramaturgy + AI personality decision). Engine does what engine does well (math + rules). Bug = engine bug, not hallucination. Replay determinism FREE (TDIL-A9 strengthened).

---

## V1 / V2+ feature ladder

| Phase | Combat archetype | Reference game | Status |
|---|---|---|---|
| **V1** | Hybrid A+D+F: side-vs-side abstract combat with 2-row positioning + LLM-narrated outcomes | Pokemon × Honkai Star Rail × Disco Elysium narration layer | concept-notes 2026-04-27 |
| **V1+30d** | Social skirmish (luận đạo / political confrontation) — LLM-narrate + engine dice-roll for non-physical conflict | BG3 dice rolls + Disco Elysium skill check | deferred V1+30d (COMB-D2) |
| **V2+** | Full zone-graph tactical RPG using CSC_001 4-layer zone graph as battlefield (FE-style movement/range/terrain within a single cell) | FFT × FE × Triangle Strategy + HSR action value | deferred V2+ (COMB-D3) |
| **V3+** | Multi-cell battlefield (siege warfare across multiple connected cells) — breaks atomic-per-turn travel; needs separate design | Total War × Stellaris fleet combat | deferred V3+ (COMB-D4) |

---

## Feature list

| ID | Conversational name | Title | Status | File | Commit |
|---|---|---|---|---|---|
| (concept) | **00_CONCEPT_NOTES.md** — COMB_001 brainstorm + market survey + LLM-zero-math constraint LOCKED + 3-layer architecture + chaos-backend module decomposition + Q1-Q9 LOCKED matrix | **CONCEPT Q-LOCKED 2026-04-27** — Q1-Q9 ALL LOCKED via 4-batch deep-dive; ready for DRAFT promotion | [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) | pending |
| COMB_001 | **Combat Foundation** (COMB) | **Q-LOCKED 2026-04-27 awaiting DRAFT promotion** — Side-based 2-row abstract combat V1; engine-owned math + LLM-narrated prose; HSR Action Value initiative; PL_006 status `knocked_out` for KO-intermediate; 4-step damage law chain (chaos-backend); 10 closure-pass-extensions across PROG/PL_005/PL_006/NPC_002/AIT_001/WA_006/WA_001/PF_001/ACT_001/RealityManifest. | DRAFT pending boundary lock | (to be created) | pending |

---

## Why this folder is concept-first

COMB_001 has heavy cross-cutting impact on PROG_001 (§9 Strike formula reversal) + PL_005 (Strike payload schema) + NPC_002 (Chorus AssemblePrompt for combat) + AIT_001 (tier dispatch for action selection) + RES_001 (vital_pool integration) + PL_006 (status effects) + FAC_001 (side allegiance) + WA_006 (mortality on KO) + EF_001 (entity_lifecycle dead transition). Per concept-notes-first discipline established by RES_001 / PROG_001 / AIT_001 / TDIL_001:

1. Capture user's combat framing (verbatim Vietnamese) + LLM-zero-math constraint
2. Reference patterns (Pokemon / FE / FFT / HSR / Persona 5 / Slay the Spire / Disco Elysium / BG3)
3. 3-layer architecture sketch (engine math / AI-decide / narrate)
4. V1 deterministic formula seed (damage / hit / initiative)
5. Boundary intersection (heavy: PROG/PL_005/NPC_002 closure-pass needed)
6. Critical scope questions (Q1-Q9) for V1 minimum + V1+ extensibility
7. Reference materials slot for incoming research (`01_REFERENCE_GAMES_SURVEY.md` companion if needed)

Mirror successful pattern (TDIL_001 4-batch deep-dive; AIT_001 4-batch; PROG_001 6-batch).

---

## Kernel touchpoints (anticipated; finalized at COMB_001 DRAFT)

- `_boundaries/01_feature_ownership_matrix.md` — `combat_session` aggregate (T2/Reality, sparse — only present during active combat) + COMB-* prefix at DRAFT
- `_boundaries/02_extension_contracts.md` §1.4 — `combat.*` rule_id namespace
- `_boundaries/02_extension_contracts.md` §2 — RealityManifest extensions (combat_config + side_default_setup + initiative_system selection)
- `00_progression/PROG_001` — **closure-pass revision**: §9 Strike formula REVERSED (LLM-proposes-damage → engine-computes-damage); promote PROG-D24 simple form to V1
- `04_play_loop/PL_005 Interaction` — **closure-pass revision**: Strike payload schema drops `damage_amount` field; engine sources from CombatEngine.compute_damage
- `04_play_loop/PL_006 Status Effects` — already engine-driven; combat consumes status apply/dispel
- `00_resource/RES_001` — `vital_pool` integration (HP/Stamina V1; Mana V1+); damage subtracts from HP; KO at HP=0
- `05_npc_systems/NPC_002 Chorus` — **closure-pass-extension**: combat-mode AssemblePrompt template (combat_state_summary + initiative_queue_next_3 + available_actions + structured ActionDecl response schema)
- `05_npc_systems/NPC_001` — actor_chorus_metadata combat_persona V1+ (deferred; LLM picks action character-consistently)
- `00_actor/ACT_001` — `actor_clocks.body_clock` reads for combat reaction speed V1+ (TDIL-D9 promotion)
- `00_faction/FAC_001` — RelationStance read for side allegiance assignment at encounter start
- `16_ai_tier/AIT_001` — 3-tier dispatch: PC + Major LLM-driven + Minor scripted + Untracked bulk-resolved; tier_capacity_caps applies to encounter participants
- `00_cell_scene/CSC_001` — V1 mượn 2 zones (Front/Back row); V2+ promote zone graph thành tactical grid
- `02_world_authoring/WA_001 Lex` — Lex axiom hooks (anti-grief tier-cap, no-PvP zones, sect-on-sect scaling)
- `02_world_authoring/WA_006 Mortality` — KO → Dying state transition; permadeath vs revival per reality config
- `00_entity/EF_001` — entity_lifecycle Dead transition on combat KO finalize
- `17_time_dilation/TDIL_001` — V1+ combat reaction speed reads body_clock (TDIL-D9); V3+ Lorentz-aware combat formula (TDIL-D10)
- `06_pc_systems/PCS_001 brief` — PC combat HUD spec (V1+ post-COMB_001 DRAFT)
- `13_quests` — combat-objective quests V1+ (deferred until QST_001 designs)

---

## Naming convention

`COMB_<NNN>_<short_name>.md`. Sequence per-category. COMB_001 is the foundation; future COMB_NNN reserved for V1+ extensions (V1+30d social skirmish / V2+ zone-tactics TRPG / V3+ multi-cell siege).

## How to add a feature

See root [`../_index.md`](../_index.md) § "How to add a new feature".

---

## Coordination note

COMB_001 is a **domain-scale Tier 6 feature** (NOT architecture-scale like AIT_001 / TDIL_001 — which provide universal scaling primitives — and NOT foundation tier — which closed at PROG_001 6/6). COMB_001 consumes the foundations + Tier 5 actor substrate + AIT_001 tier dispatch + TDIL_001 clocks + PROG_001 progression + RES_001 vital pools + PL_005 Strike intent + PL_006 status. Mirrors the consumption pattern PCS_001 will follow for PC substrate.

User's deep-dive 2026-04-27 surfaced the **LLM-zero-math constraint** which has architectural cascade:
- **PROG_001 §9 + PROG-D24**: Strike formula REVERSED (LLM-proposes → engine-computes); part of PROG-D24 deterministic damage law chain promoted to V1
- **PL_005 Strike**: payload schema simplified (drop `damage_amount`)
- **NPC_002 Chorus**: AssemblePrompt extension for combat mode (structured ActionDecl response)
- **A6 canon-drift detector V1+**: should NOT trigger on engine-computed combat values (only on LLM-narrated prose claims)

These are **mechanical revisions** + **schema simplifications** but boundary-coordinated. Recommended sequence:
1. COMB_001 concept-notes (this commit; non-boundary)
2. Q-deep-dive batched (mirror PROG/AIT/TDIL pattern; aim Q1-Q9 LOCKED)
3. PROG/PL_005/NPC_002 closure-pass revisions + COMB_001 DRAFT (single combined boundary commit)

Subsequent priorities per existing roadmap:
- After COMB_001 DRAFT: **PCS_001 PC Substrate kickoff** (consumes 6 foundations + IDF + FF + FAC + REP + ACT + AIT + TDIL + PROG + COMB; full V1 vertical slice)
- Future V1+: COMB_002 Social Skirmish (luận đạo / political confrontation) / V2+ COMB_003 Zone-Tactics TRPG / V3+ COMB_004 Multi-cell Siege
- Future genre: CULT_001 Cultivation Foundation (wuxia-genre cultivation method binding to FAC_001 + COMB_001 elemental damage V1+)
