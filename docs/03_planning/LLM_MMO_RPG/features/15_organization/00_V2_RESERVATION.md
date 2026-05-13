# ORG — Organization System V3 Reservation

> **Status:** RESERVED 2026-04-26 — V3 deferred. No design here. Captures namespace reservation + V1+ hooks + V3 scope sketch.
>
> **Filename note:** Kept as `00_V2_RESERVATION.md` for consistency with sibling folders (`13_quests/` + `14_crafting/`); content explicitly marks V3 deferral.
>
> **DO NOT design organizations in this file.** When V3 begins, create `ORG_001_faction_foundation.md`.

---

## §1 — What organization system is

**In-fiction collective entities** that NPCs (and PCs) belong to: factions (political), guilds (professional), sects / môn phái (wuxia/xianxia spiritual), dynasties (familial), merchant houses, mercenary companies, religious orders.

V3 scope (high-level): Faction aggregate + member roster + shared treasury + internal hierarchy (ranks/titles) + faction-vs-faction reputation + diplomatic relations + tax/tribute flow + faction-tier resources.

---

## §2 — Why V3 deferred (not V1 or V2)

- **Depends on full RES_001 Strategy module V3** — faction treasury (RES-D19) + hierarchical income (RES-D20) + tax system (RES-D23) + diplomatic exchange (RES-D24) all V3
- **Depends on V2 quest system** — faction quests / faction missions need QST V2 first
- **V1 has individual NPC reputation only** — RES_001 SocialCurrency Reputation V1 covers per-NPC standing; faction-tier reputation is V3
- **V2 might have light faction tags** — NPC.flexible_state could carry faction membership tag without full faction system; but real faction mechanics V3
- **Wuxia/xianxia môn phái = central trope** — important for genre but heavy feature; better designed once on top of solid V2 economy

---

## §3 — Existing V1+ hooks already reserved

| Hook | Owner | Reserved as |
|---|---|---|
| `EntityRef::Faction(FactionId)` | EF_001 + RES_001 §4.4 | V3 reserved EntityRef variant — factions can own resources |
| `RES-D19 Per-faction treasury aggregation` | RES_001 §15.3 V3 Strategy module | "Civ/EU4/CK3 empire-tier pool" |
| `RES-D20 Hierarchical income flow` | RES_001 §15.3 | "vassal → liege; cell → town → faction; CK3 pattern" |
| `RES-D23 Tax system` | RES_001 §15.3 | "% flow lower→upper tier; CK3/EU4" |
| `RES-D24 Diplomatic resource exchange` | RES_001 §15.3 | "cross-faction gifting + tribute" |
| `SocialKind::Influence` | RES_001 §3.2 | V2 reserved enum variant — political/factional leverage |
| `SocialKind::Prestige` | RES_001 §3.2 | V2 reserved — CK3 prestige pattern |
| `SocialKind::Piety` | RES_001 §3.2 | V2 reserved — religious standing |

---

## §4 — V3 scope sketch (no design — bullets only)

When V3 design begins:

- **Faction aggregate** (T2/Reality scope; per-(reality, faction_id) row)
- **Member roster** — Vec<MembershipRecord { actor_ref, rank, joined_at_fiction_ts, status }>
- **Hierarchy / ranks** — author-declared per faction (e.g., wuxia sect: 弟子 → 内门 → 长老 → 掌门)
- **Shared treasury** — `EntityRef::Faction` owns resource_inventory entries (RES_001 RES-D19)
- **Income flow** — vassal cells / member dues → faction treasury (CK3 pattern; RES-D20)
- **Tax** — % skim from member income (RES-D23)
- **Diplomatic relations** — Faction × Faction reputation matrix; alliance / war / neutral / vassalage
- **Faction-vs-faction reputation** — distinct from per-NPC SocialCurrency Reputation V1
- **Member benefits** — access to faction resources / shared cells / training / quest gating
- **Defection / expulsion** — membership state transitions
- **Faction wars** — V3+ — large-scale conflict resolution
- **Wuxia/xianxia patterns** — sect rivalry / 武林大会 / 灭门 / sect-level techniques (V3+)
- **Charter integration** — author co-authors (PLT_001) might roleplay as faction leaders (orthogonal but referenceable)

---

## §5 — Cross-folder relationships when V3 designs

| Touched folder | Concern |
|---|---|
| `00_resource/` (RES_001 V3 deferrals) | Treasury / tax / income / diplomatic exchange — FOUNDATIONAL dependency |
| `00_entity/` (EF_001) | EntityRef::Faction discriminator |
| `05_npc_systems/` (NPC_001) | NPC membership; NPC loyalty/defection state |
| `06_pc_systems/` (PCS_001) | PC membership; PC rank progression |
| `04_play_loop/` (PL_005) | Faction-mediated interactions (faction reputation gates trade / dialogue / combat) |
| `10_platform_business/` (PLT_001 Charter) | DIFFERENT concept (platform-level co-author grants vs in-fiction faction); document boundary clearly |
| `08_narrative_canon/` (NAR) | Faction history / canon faction events |
| `13_quests/` (V2 deferred) | Faction quests gated by membership/rank |
| `14_crafting/` (V2 deferred) | Faction-exclusive recipes (sect-only techniques V3) |
| `02_world_authoring/` (WA_003 Forge) | Author UI for declaring factions + members + ranks + initial diplomatic state |
| `12_daily_life/` (DF1) | Faction routines / faction-specific NPC behaviors |

---

## §6 — Reference games for V3 design

- **Crusader Kings 3** — dynasties + houses + religion + cultural groups (closest match for character-centric LoreWeave)
- **Total War series** — factions with armies + diplomacy + provinces
- **Europa Universalis 4** — estates within nation + Holy Roman Empire structure
- **Stellaris** — empires + federations + galactic council
- **Mount & Blade Bannerlord** — kingdoms + clans + vassal hierarchy
- **Rimworld Ideology DLC** — religion/ideology as collective + member rituals
- **Wuxia/xianxia tropes** — môn phái rivalry / 正派 vs 邪派 / 武林盟主 elections / sect-internal politics
- **Skyrim** — guilds (Companions / Thieves Guild / Mages College) — narrative-light faction membership
- **WoW** — Horde vs Alliance — binary faction loyalty + faction-locked content

---

## §7 — Boundary lines (when V3 designs)

ORG will OWN:
- `Faction` aggregate + state machine (active / dormant / dissolved)
- `MembershipRecord` shape + rank progression
- Faction × Faction diplomatic relations matrix
- Faction-tier reputation (distinct from per-NPC reputation V1)
- `organization.*` RejectReason namespace
- Member income / dues / faction-treasury flow rules

ORG will NOT own (these stay where they are):
- Individual NPC reputation (RES_001 SocialCurrency Reputation V1)
- Co-author grants (PLT_001 Charter — DIFFERENT layer)
- Quest gating (QST V2 owns; ORG provides faction context)
- Resource pools per faction (RES_001 V3 RES-D19 owns aggregate; ORG declares which factions exist)
- Faction-internal NPCs (NPC_001 owns NPCs themselves; ORG owns membership association)

---

## §8 — Promotion checklist (when V3 design begins)

1. Read RES_001 V3 deferrals (RES-D19..D24) — foundational dependency
2. Read NPC_001 + PCS_001 (post-V1+30d shipping) for membership integration patterns
3. Read PLT_001 Charter (boundary clarity — ORG is NOT Charter)
4. Survey reference games §6 (CK3 dynasties + wuxia môn phái patterns primary)
5. Claim `_boundaries/_LOCK.md`
6. Create `catalog/cat_15_ORG_organization.md`
7. Update `_boundaries/01_feature_ownership_matrix.md` Stable-ID prefix ownership row to add `ORG-*` + new `faction` aggregate ownership row
8. Update `_boundaries/02_extension_contracts.md` §1.4 add `organization.*` rule_id namespace
9. Coordinate with RES_001 V3 module to formalize EntityRef::Faction(FactionId) active
10. Promote → ORG_001 DRAFT (~800-1000 lines; expect heavy feature given scope)
11. Release lock + commit `[boundaries-lock-claim+release]`

---

## §9 — DO NOT design here

- ❌ NO Rust struct definitions for Faction aggregate
- ❌ NO membership state machines
- ❌ NO diplomatic relations algorithms
- ❌ NO RejectReason rule_ids
- ❌ NO acceptance criteria
- ❌ NO rank progression rules

This is a RESERVATION + SCOPE SKETCH. V3 design lives in `ORG_001_faction_foundation.md` when V3 begins.
