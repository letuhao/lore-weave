# 16_ai_tier — Index

> **Category:** AIT — AI Tier (3-tier NPC architecture for billion-NPC scaling; Schrödinger / quantum-observation pattern)
> **Catalog reference:** `catalog/cat_16_AIT_ai_tier.md` (NOT YET CREATED — defer to AIT_001 DRAFT promotion)
> **Purpose:** Defines NPC tier hierarchy (PC / Tracked-LLM / Tracked-Rule / Untracked) for scaling LoreWeave from small reality (≤100 actors) to billion-actor world. PCs always tracked + always LLM/player-driven. Tracked NPCs have full ActorProgression aggregate stored; behavior is either LLM-driven (like PCs) or rule-based (deterministic scripts including training). Untracked NPCs are ephemeral — LLM/RNG-generated per session, discarded after observation window ends. Owns `NpcTrackingTier` enum + tier promotion mechanics + Untracked procedural generation + discard policies + behavior model per tier.

**Active:** AIT_001 — **AI Tier Foundation** (CONCEPT 2026-04-26 — captures user 3-tier framing + 10+ open questions)

**Folder closure status:** Open — concept-notes phase. AIT_001 not yet drafted. User kickoff confirmed 2026-04-26 post PROG_001 DRAFT closure.

**Foundation tier discipline note:** This is **NOT a 7th foundation** — PROG_001 closed foundation tier at 6/6. AIT_001 is a Tier 5+ Actor Substrate **scaling/architecture feature** that consumes PROG_001's `tracking_tier: Option<NpcTrackingTier>` reservation field + NPC_001's NpcId + RES_001's resource_inventory pattern. AIT_001 exists because PROG_001 + RES_001 + NPC_001 alone don't define HOW NPCs are tiered for scale.

---

## Why this folder exists

User stated 2026-04-26 (during PROG_001 Q4 REVISED deep-dive):

> "chúng ta sẽ có kiến trúc phân tầng AI mà chúng ta chưa design, sẽ có design sau progression system"
>
> "1 thế giới rộng lớn với hàng tỷ NPC, làm sao mô phỏng?
> chúng ta sẽ chia NPC ra thành nhiều cấp độ tồn tại, được track và không được track
> generate ngẫu nhiên rồi biến mất theo session HOẶC major NPC được track với số lượng rất hạn chế và cực kỳ thông minh, có rule based action bao gồm training process VÀ có loại LLM tự điều khiển hành vi giống như 1 PC"

Translation: AI tier architecture pending design (post-progression). Billion-NPC world simulation requires tier-based existence levels — tracked vs untracked. Untracked NPCs randomly generated then disappear by session. Major tracked NPCs limited count, very intelligent, with rule-based actions including training, AND a subtype with LLM-driven behavior matching PCs.

→ Distinct concerns from PROG_001:
- PROG_001 owns progression substrate (HOW actors grow). It reserved `tracking_tier: Option<NpcTrackingTier>` field on `actor_progression` aggregate.
- AIT_001 owns the NpcTrackingTier enum + tier semantics + Untracked generation + discard policies + behavior models.

---

## Feature list

| ID | Conversational name | Title | Status | File | Commit |
|---|---|---|---|---|---|
| (concept) | **00_CONCEPT_NOTES.md** — AIT_001 brainstorm capture | CONCEPT 2026-04-26 — captures user 3-tier framing + 10+ open questions; awaits user direction on Q1-QN deep-dive | [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) | (this commit) |
| AIT_001 | **AI Tier Foundation** (AIT) | (awaiting Q1-QN lock) — 3-tier NPC architecture: PC (always tracked) / Tracked-LLM (Major; LLM-driven; behaves like PC) / Tracked-Rule (Minor; rule-based scripted actions including training) / Untracked (Background; ephemeral LLM/RNG generation per session). Owns `NpcTrackingTier` closed enum + tier promotion rules + Untracked procedural generation + discard policies. Integrates with NPC_001 (NpcId per-tier semantics) + PROG_001 (`tracking_tier` field active for first time) + PL_005 (action availability per tier) + EVT-G (Untracked generation triggers) + future scheduler (V2 NPC routine per tier). | NOT YET DRAFTED | (to be created) | n/a |

---

## Why this folder is concept-first

AIT_001 is fundamentally an **architecture-scale feature** with implications across many existing features:
- PROG_001 reserved `tracking_tier` field — AIT_001 populates the enum
- NPC_001 implicitly assumed all NPCs equally addressable — AIT_001 splits scoping
- RES_001 NPC eager auto-collect Generator was V1 design — AIT_001 implies eager-vs-lazy migration (PROG-D19)
- LLM context budget — AIT_001 changes which NPCs LLM "knows about" per turn
- Replay determinism — Untracked generation must be deterministic per EVT-A9

Concept phase first — capture user framing + open questions before deep-dive Q-by-Q (mirror PROG_001 / RES_001 pattern that produced ~30 LOCKED decisions across 6 deep-dive batches).

---

## Kernel touchpoints (anticipated; finalized at AIT_001 DRAFT)

- `06_data_plane/02_invariants.md` — DP-A14 scope/tier annotations on tier-discriminator data; DP-A18 channel lifecycle for Untracked discard
- `07_event_model/03_event_taxonomy.md` — NEW EVT-T5 Generated sub-types for Untracked generation; NEW EVT-T3 Derived for tier promotion/demotion events
- `_boundaries/01_feature_ownership_matrix.md` — `NpcTrackingTier` enum ownership + tier-related aggregates (if any) at AIT_001 DRAFT
- `_boundaries/02_extension_contracts.md` §1.4 — `ai_tier.*` rule_id namespace
- `_boundaries/02_extension_contracts.md` §2 — RealityManifest extensions for tier-related declarations (per-cell-type Untracked density / tier promotion thresholds / etc.)
- `00_progression/PROG_001_progression_foundation.md` — `tracking_tier` field activated at AIT_001 DRAFT; lazy materialization triggered by AIT_001-defined observation events
- `00_resource/RES_001_resource_foundation.md` — V1+30d closure pass migrates NPC eager auto-collect to lazy materialization (PROG-D19 alignment)
- `05_npc_systems/NPC_001 Cast` — NpcId discriminator extended with tier; persona assembly varies per tier; Untracked NPC ephemeral cache
- `04_play_loop/PL_005 Interaction` — action availability gate by tier (Tracked-LLM full; Tracked-Rule scripted-only; Untracked narrative-only)
- `04_play_loop/PL_001 Continuum` — scene_state membership reflects tier (Untracked NPCs as ephemeral participants)
- `02_world_authoring/WA_003 Forge` — author Forge actions for tier promotion/demotion
- `00_cell_scene/CSC_001` — cell-scene rendering may include Untracked NPCs (procedurally placed by AIT_001)

---

## Naming convention

`AIT_<NNN>_<short_name>.md`. Sequence per-category. AIT_001 is the foundation; future AIT_NNN reserved for V1+ extensions (per-tier behavior modules / cross-cell migration / global background simulation).

## How to add a feature

See root [`../_index.md`](../_index.md) § "How to add a new feature".

---

## Coordination note

AIT_001 is the **architecture-scale companion** to PROG_001 + NPC_001. Where PROG/NPC define WHAT is stored per actor, AIT_001 defines WHO is stored at all + HOW they're generated/discarded. Foundation tier 6/6 + Tier 5 Actor Substrate (IDF/FF/PROG) provide the WHAT; AIT_001 provides the WHO/WHEN scaling.

User explicitly noted post-PROG_001 priority. Subsequent priorities per existing roadmap:
- After AIT_001 DRAFT: PCS_001 PC Substrate (consumes 6 foundations + IDF + FF + AIT)
- Future: CULT_001 Cultivation Foundation (V1+ tu tiên-specific extensions on PROG_001)
- Future: FAC_001 Faction Foundation (V1+ — was reserved at IDF closure)
- Future: REP_001 Reputation Foundation (V1+ — was reserved at IDF closure)
