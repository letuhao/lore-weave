# Actor Settings Audit — All configurable fields per actor (V1 + V1+ status)

> **Purpose:** Comprehensive inventory of EVERY actor-level setting across all locked LoreWeave features. Used by PO_001 Advanced Mode UI to ensure 100% coverage.
> **Status:** 2026-04-27 audit · 14 features touched · 12 categories · ~45 distinct settings
> **Methodology:** Walked each Tier 5 + foundation feature spec; extracted actor-level configurable fields; categorized by lifecycle (immutable / mutable V1 / V1+ runtime).

---

## §1 Coverage matrix — 12 categories × 14 features

| Category | Owning feature(s) | # V1 settings | # V1+ deferred |
|---|---|---|---|
| **A. Identity (immutable)** | ACT_001 actor_core | 9 | 0 |
| **B. Race & physiology** | IDF_001 race_assignment | 1 | 4 (transformation/reincarnation) |
| **C. Languages** | IDF_002 actor_language_proficiency | 1 (Vec<proficiency>) | 2 (dialect/code-switch) |
| **D. Personality & mood** | IDF_003 actor_personality + ACT_001 actor_core flexible_state_init | 6 | 2 (archetype evolution/overlay) |
| **E. Origin & background** | IDF_004 actor_origin | 4 | 1 (origin pack default_titles) |
| **F. Ideology & beliefs** | IDF_005 actor_ideology_stance | 1 (Vec<stance>) | 5 (tenet/sect-binding/conversion) |
| **G. Family & lineage** | FF_001 family_node + dynasty | 4 | 8 (extended traversal/cadet/perks/etc.) |
| **H. Faction membership** | FAC_001 actor_faction_membership | 6 | 4 (sworn-bond/cross-reality/etc.) |
| **I. Reputation** | REP_001 actor_faction_reputation | 1 (sparse per-faction) | 4 (runtime delta/cascade/decay) |
| **J. Titles & rank** | TIT_001 actor_title_holdings | 1 (sparse per-title) | 5 (FactionElect/term-limited/decay) |
| **K. Skills & progression** | PROG_001 actor_progression | 1 (Vec<ProgressionInstance>; per-reality kinds) | 9 (atrophy/RNG/mentor/quest/etc.) |
| **L. Resources & inventory** | RES_001 vital_pool + resource_inventory | 8 | 3 (cap/bargaining/instance-id) |
| **M. PC-specific (xuyên không + binding)** | PCS_001 pc_user_binding + pc_mortality_state | 6 | 5 (respawn/runtime-login/body-substitution) |
| **N. Time clocks** | TDIL_001 actor_clocks | 3 (system-managed) | 6 (subjective rate/dilation target/wandering) |
| **O. Cell membership** | EF_001 entity_binding | 1 (system-managed via spawn_cell) | 0 |
| **P. AI tier hint** | AIT_001 NpcTrackingTier | 1 (NPCs only) | 4 (promotion/demotion/etc.) |

**Total V1 settings:** ~46 across 14 features.

---

## §2 Per-category settings detail (V1 + V1+ status)

### A. Identity (ACT_001 actor_core; immutable post-bootstrap)

| Setting | V1 status | Type | Notes |
|---|---|---|---|
| `actor_id` | ✅ V1 immutable | `Uuid` | Auto-generated; module-private constructor (DP-A12); never user-editable |
| `kind` | ✅ V1 immutable | `enum ActorKind { Pc / Npc }` | V1 Synthetic forbidden (universal substrate axiom) |
| `canonical_traits.name` | ✅ V1 immutable | `I18nBundle` | Multi-language name; LLM uses in narration |
| `canonical_traits.role` | ✅ V1 immutable | `String` | E.g., "Sect Master" / "Innkeeper" / "Wandering Hero" |
| `canonical_traits.voice_register` | ✅ V1 immutable | `enum { TerseFirstPerson / Novel3rdPerson / Mixed }` | Persona narration style |
| `canonical_traits.physical` | ✅ V1 immutable | `I18nBundle` | Text description (V1 text-only; V2+ portrait sliders) |
| `canonical_traits.core_beliefs_ref` | ✅ V1 immutable | `Option<GlossaryEntityId>` | Canon belief reference |
| `canonical_traits.spawn_cell` | ✅ V1 immutable (P2 LOCKED) | `ChannelId` | Initial cell location; populates entity_binding |
| `canonical_traits.glossary_entity_id` | ✅ V1 immutable (P2 LOCKED) | `GlossaryEntityId` | Primary glossary entry; DISTINCT from core_beliefs_ref |
| `canonical_traits.gender_pronouns` | ⚠ V1 in flexible_state.extensions | `String` (e.g., "anh/em" / "cô/em") | NOT explicit V1 field; stored in extensions HashMap |

### B. Race & physiology (IDF_001)

| Setting | V1 status | Type | Notes |
|---|---|---|---|
| `race_id` | ✅ V1 immutable post-bootstrap | `RaceId` (per-reality) | RealityManifest.races declared |
| Race transformation | ❌ V1+ (PROG-D / IDF-D) | — | Werewolf/dragon-form etc. |
| Reincarnation invalid target | ❌ V1+ | — | xuyên không + race change |
| Cyclic lineage | ❌ V1+ | — | DP-detection if needed |
| Synthetic body race | ❌ V1+ Synthetic V2+ | — | Universal substrate axiom |

### C. Languages (IDF_002)

| Setting | V1 status | Type | Notes |
|---|---|---|---|
| `actor_language_proficiency` | ✅ V1 mutable via Forge | `Vec<LanguageProficiency { language_id, axes: [Read/Write/Speak/Listen] }>` | Per-axis level u8 [0, 100] |
| Dialect mismatch | ❌ V1+ | — | Same language different dialects |
| Code-switch | ❌ V1+ | — | Mid-conversation language switch |

### D. Personality & mood (IDF_003 + ACT_001 flexible_state_init)

| Setting | V1 status | Type | Notes |
|---|---|---|---|
| `personality_archetype_id` | ✅ V1 immutable post-bootstrap | `ArchetypeId` (12 V1 variants: Stoic/Hothead/Cunning/Innocent/Pious/Cynic/Worldly/Idealist/Loyal/Aloof/Ambitious/Compassionate) | Affects opinion_modifier_table |
| `mood_init` 4-axis | ✅ V1 mutable runtime | `ActorMood { joy: u8, anger: u8, sadness: u8, fear: u8 } [0, 100]` | Wuxia 喜怒哀乐 + 惧 emotional axes |
| `flexible_state.disposition` | ✅ V1 mutable | `enum 7-variant Disposition { Friendly / Neutral / Suspicious / Hostile / Curious / Indifferent / Romantic }` | Default Neutral |
| `flexible_state.last_interacted_with` | ✅ V1 mutable | `Option<ActorRef>` | LRU updated by NPC_001 §13 |
| `flexible_state.last_emotional_event` | ✅ V1 mutable | `Option<I18nBundle>` | Free-text LLM hint |
| `flexible_state.secret_held` | ✅ V1 mutable | `Option<I18nBundle>` | "Lý Lão Tổ has unread letter from dead disciple" |
| `flexible_state.recent_event_refs` | ✅ V1 mutable | `VecDeque<EventId>` (≤5 LRU) | Causal-ref bounded list |
| `flexible_state.extensions` | ✅ V1 mutable | `HashMap<String, JsonValue>` | Free-form per-feature extension; gender stored here V1 |
| Archetype evolution | ❌ V1+ | — | Path of evolution (Stoic → Cynical) |
| Overlay conflict | ❌ V1+ | — | Multi-archetype hybrid |

### E. Origin & background (IDF_004)

| Setting | V1 status | Type | Notes |
|---|---|---|---|
| `birthplace_channel` | ✅ V1 immutable post-bootstrap | `ChannelId` (cell-tier) | RealityManifest.places ref |
| `lineage_id` | ✅ V1 immutable | `LineageId` opaque V1 → resolves via FF_001 dynasty V1+ | Resolves IDF_004 ORG-D12 |
| `native_language` | ✅ V1 immutable | `LanguageId` | RealityManifest.languages ref |
| `default_ideology_refs` | ✅ V1 mutable | `Vec<(IdeologyId, FervorLevel)>` | Auto-seed at canonical seed (Light fervor per IDL-Q9) |
| `origin_pack_default_titles` | ❌ V1+ (TIT-D10) | — | OriginPack additive field |

### F. Ideology & beliefs (IDF_005)

| Setting | V1 status | Type | Notes |
|---|---|---|---|
| `actor_ideology_stance` | ✅ V1 mutable (ONLY mutable IDF aggregate V1) | `Vec<IdeologyStanceEntry { ideology_id, fervor_level: 5-variant }>` | Multi-stance V1 (Wuxia syncretism Đạo+Phật+Nho) |
| Tenet violation | ❌ V1+ (IDL-D1) | — | Action contradicts ideology |
| Sect-membership-required | ❌ V1+ (IDL-D2) | — | RESOLVED by FAC_001 |
| Conversion cost | ❌ V1+ (IDL-D11) | — | Free V1 per IDL-Q13 LOCKED |
| Conflict auto-drop | ❌ V1+ | — | Mutually exclusive ideologies |
| Fervor transition validation | ❌ V1+ | — | Light → Devout requires conditions |

### G. Family & lineage (FF_001 family_node + dynasty)

| Setting | V1 status | Type | Notes |
|---|---|---|---|
| `family_node.parents` | ✅ V1 mutable via Forge | `Vec<RelationKind { Biological/Adopted Parent/Child + Spouse + Sibling 6-variant }>` | RelationKind 6-variant enum |
| `family_node.spouses` | ✅ V1 mutable via Forge | `Vec<ActorRef>` | Forge:EditFamily AddSpouse/RemoveSpouse |
| `family_node.children` | ✅ V1 mutable via Forge | `Vec<ActorRef>` | Bidirectional sync validated |
| `family_node.deceased` | ✅ V1 mutable via Forge | `bool` | Marks Forge:EditFamily MarkDeceased |
| `dynasty.dynasty_id` (membership) | ✅ V1 immutable post-bootstrap | `Option<DynastyId>` | RealityManifest.canonical_dynasties ref |
| Extended traversal API (cousins/uncles/aunts) | ❌ V1+ (FF-D2) | — | When V1+ consumer needs |
| Cadet branches | ❌ V1+ | — | Hierarchical dynasty |
| Dynasty traditions/perks | ❌ V1+ | — | CK3-style tradition tree |
| Marriage as alliance | ❌ V1+ DIPL_001 (FF-D5) | — | Cross-feature DIPL |
| Sworn brotherhood | ❌ V1+ FAC_001 (FF-D6) | — | Boundary discipline |
| Master-disciple | ❌ V1+ FAC_001 (FF-D7) | — | RESOLVED by FAC |
| Title inheritance | ✅ V1 RESOLVED (TIT-001) | `dynasty.current_head_actor_id` | Read by SuccessionRule::Eldest |
| Family-shared inventory | ❌ V1+ RES_001 (FF-D12) | — | Clan treasury |

### H. Faction membership (FAC_001 actor_faction_membership; V1 cap=1 per Q2 REVISION)

| Setting | V1 status | Type | Notes |
|---|---|---|---|
| `faction_id` | ✅ V1 mutable via Forge | `FactionId` | RealityManifest.canonical_factions ref |
| `role_id` | ✅ V1 mutable via Forge | `RoleId` per FactionDecl.roles | RoleDecl.authority_level u8 [0, 100] |
| `rank_within_role` | ✅ V1 mutable | `u16 numeric V1` | Per Q4 REVISION numeric-only V1; named computed display |
| `master_actor_id` | ✅ V1 mutable | `Option<ActorId>` | RESOLVES FF-D7 master-disciple |
| `joined_at_turn` + `joined_at_fiction_ts` | ✅ V1 immutable post-join | `u64 + i64` | Audit trail |
| `joined_reason` | ✅ V1 immutable post-join | `enum 4-variant { CanonicalSeed/PcCreation/NpcSpawn/AdminOverride }` | |
| Multi-faction membership | ❌ V1+ (Q2 REVISION cap=1 V1) | — | Vec+cap=1 → Vec+cap=N V1+ via single-line validator change |
| Sworn bond | ❌ V1+ (FAC-D10) | — | Per Q7 REVISION |
| Cross-reality migration | ❌ V2+ (FAC-D9) | — | Per Q8 LOCKED Heresy |
| Lex axiom forbidden | ❌ V1+ (Q9) | — | Faction-gated abilities |

### I. Reputation (REP_001 actor_faction_reputation; sparse per-(actor, faction))

| Setting | V1 status | Type | Notes |
|---|---|---|---|
| Per-faction `score` | ✅ V1 mutable via Forge | `i16` bounded [-1000, +1000]; Forge:SetReputation/ResetReputation V1 | Default Neutral (0) per Q4 REVISION |
| Tier label (engine-fixed) | ✅ V1 derived | `enum ReputationTier { 8-variant Hated/Hostile/Unfriendly/Neutral/Friendly/Honored/Revered/Exalted }` | Asymmetric thresholds |
| Wuxia I18n display labels | ✅ V1 (REP-4) | `I18nBundle` | Đại nghịch / Nghịch tặc / Kẻ thù / Người lạ / Đệ tử / Trưởng lão / Tôn sư / Đại Thánh nhân |
| Runtime delta events | ❌ V1+ (REP-D1) | — | PL_005 Strike on faction member |
| Cascade rep | ❌ V1+ (REP-D2) | — | Rival's enemy = friend bonus |
| Decay over time | ❌ V1+ (REP-D3) | — | Rep drift toward 0 |
| Per-faction tier overrides | ❌ V1+ (REP-D4) | — | FactionDecl.rep_tier_overrides display labels |

### J. Titles & rank (TIT_001 actor_title_holdings; sparse per-(actor, title))

| Setting | V1 status | Type | Notes |
|---|---|---|---|
| Per-title `granted_at_fiction_ts` | ✅ V1 mutable via Forge | `i64` | Forge:GrantTitle V1 |
| Per-title `granted_via` | ✅ V1 mutable | `enum GrantSource { CanonicalSeed/ForgeAdmin/SuccessionCascade }` V1 | V1+ QuestReward + FactionElectVote |
| Per-title `designated_heir` | ✅ V1 mutable via Forge | `Option<ActorRef>` | For Designated SuccessionRule |
| MultiHoldPolicy compliance | ✅ V1 enforced (TIT-C6) | enum Exclusive/StackableUnlimited/StackableMax(N) | Per-title author-declared |
| FactionElect succession | ❌ V1+ (TIT-D1) | — | DIPL_001 V2+ dependency |
| Runtime min_rep validator | ❌ V1+ (TIT-D2) | — | Schema-active V1; runtime V1+ alongside REP-D1 |
| requires_title Lex axiom | ❌ V1+ (TIT-D3) | — | WA_001 closure pass 5-companion-fields |
| Term-limited titles | ❌ V2+ (TIT-D6) | — | Imperator consul fiction-time bound |
| Title decay | ❌ V2+ (TIT-D7) | — | CK3 prestige decay |

### K. Skills & progression (PROG_001 actor_progression)

| Setting | V1 status | Type | Notes |
|---|---|---|---|
| `Vec<ProgressionInstance>` | ✅ V1 mutable runtime | `Vec<{ kind_id, raw_value, current_tier, last_trained_at, last_observed_at, training_log_window }>` | Per-reality declared kinds (PROG-A1) |
| ProgressionType per kind | ✅ V1 immutable per kind | `enum 3-variant { Attribute / Skill / Stage }` | RealityManifest.progression_kinds declared |
| BodyOrSoul per kind | ✅ V1 immutable per kind | `enum 3-variant { Body / Soul / Both }` | xuyên không cross-reality stat translation |
| Forge:GrantProgression | ✅ V1 mutable via Forge | — | Initial value override per actor |
| Forge:TriggerBreakthrough | ✅ V1 mutable via Forge | — | Tier advance |
| Atrophy / decay | ❌ V1+ (PROG-D5) | — | No-practice decay |
| Failed breakthrough (走火入魔) | ❌ V1+ (PROG-D2) | — | Tier regress |
| Cross-actor delta | ❌ V1+ (PROG-D33) | — | Dual cultivation / demonic absorb |
| RawValueDecrement (drain) | ❌ V1+ (PROG-D34) | — | Cauldron mechanic |
| derives_from cross-feature | ❌ V2 (PROG-D35) | — | FF/FAC/REL state → rate multiplier |
| KarmaThreshold breakthrough | ❌ V1+ (PROG-D36) | — | Heart demon gating |
| RebirthBonusDecl | ❌ V2 (PROG-D37) | — | Cumulative per-death bonus |
| Subsystem stacking | ❌ V1+ (PROG-D6) | — | chaos-backend Contribution |

### L. Resources & inventory (RES_001 vital_pool + resource_inventory)

| Setting | V1 status | Type | Notes |
|---|---|---|---|
| Vital `Hp` current/max | ✅ V1 mutable runtime | `u32 + u32` | Per-reality VitalProfileDecl declares max |
| Vital `Stamina` current/max | ✅ V1 mutable runtime | `u32 + u32` | |
| Vital `Mana` current/max (if reality declares) | ✅ V1 mutable runtime | `u32 + u32` | Optional per-reality |
| Currency balance(s) | ✅ V1 mutable runtime | `HashMap<CurrencyKind, u64>` | Multi-currency (xianxia copper/silver/gold) |
| Inventory items | ✅ V1 mutable runtime | `Vec<ItemEntry { kind, quantity, instance_id? }>` | inventory_cap per actor |
| `SocialCurrency::Reputation` (global fame) | ✅ V1 mutable runtime | `i64` | "danh tiếng" wuxia world; DISTINCT from REP_001 per-faction |
| Cell ownership | ✅ V1 (cell_owner) | — | EF_001 + RES_001 cross-feature |
| Maintenance cost per cell | ✅ V1 if owned | — | RES_001 cell_maintenance_profiles |
| Cap exceeded V1+ | ❌ V1+ (resource.balance.cap_exceeded) | — | |
| Bargaining failed | ❌ V1+ | — | Trade negotiation |
| Item instance_id | ❌ V1+ | — | Per-item uniqueness |

### M. PC-specific (PCS_001 pc_user_binding + pc_mortality_state; sparse PC-only; V1 cap=1)

| Setting | V1 status | Type | Notes |
|---|---|---|---|
| `pc_id` | ✅ V1 immutable | `Uuid` (DP-A12 module-private) | |
| `user_id` | ✅ V1 mutable via Forge | `Option<UserId>` | auth-service ref; bound via Forge:BindPcUser |
| `current_session` | ✅ V1 mutable | `Option<SessionId>` | Current session (DF05 ties in) |
| `body_memory.SoulLayer.origin_world_ref` | ✅ V1 immutable post-creation | `Option<GlossaryEntityId>` | xuyên không trope |
| `body_memory.SoulLayer.knowledge_tags` | ✅ V1 mutable via Forge | `Vec<KnowledgeTag>` | Soul-level meta-knowledge |
| `body_memory.SoulLayer.native_skills` | ✅ V1 schema (empty Vec V1) | `Vec<ProgressionKindId>` | V1+ runtime activation |
| `body_memory.SoulLayer.native_language` | ✅ V1 immutable | `LanguageId` | |
| `body_memory.BodyLayer.host_body_ref` | ✅ V1 immutable | `Option<GlossaryEntityId>` | The body the soul inherited |
| `body_memory.BodyLayer.knowledge_tags` | ✅ V1 mutable via Forge | `Vec<KnowledgeTag>` | Body's residual memory |
| `body_memory.BodyLayer.motor_skills` | ✅ V1 schema (empty Vec V1) | `Vec<ProgressionKindId>` | V1+ runtime activation |
| `body_memory.BodyLayer.native_language` | ✅ V1 immutable | `LanguageId` | Body's native tongue |
| `body_memory.LeakagePolicy` | ✅ V1 mutable via Forge | `enum 4-variant { NoLeakage / SoulPrimary { body_blurts_threshold: f32 } / BodyPrimary { soul_slips_threshold: f32 } / Balanced }` | Soul ↔ body integration |
| `pc_mortality_state` | ✅ V1 mutable via Forge | `enum 4-variant { Alive/Dying/Dead/Ghost }` | Per Q7 LOCKED |
| Multi-PC per reality | ❌ V1+ (PCS-D3) | — | Cap=1 V1; relax via RealityManifest.max_pc_count |
| Runtime login | ❌ V1+ (PCS-D1) | — | PO_001 V1+ Player Onboarding |
| Body substitution runtime | ❌ V1+ (PCS-D-N) | — | Beyond canonical seed |
| Respawn flow | ❌ V1+ (PCS-D2) | — | RespawnAtLocation mode V1 forbidden per Q7 |

### N. Time clocks (TDIL_001 actor_clocks; ALWAYS-PRESENT V1 post-creation)

| Setting | V1 status | Type | Notes |
|---|---|---|---|
| `actor_clock` | ✅ V1 system-managed | `i64` proper-time τ | Canonical worldline; monotonic V1 |
| `soul_clock` | ✅ V1 system-managed | `i64` | BodyOrSoul::Soul progressions read this |
| `body_clock` | ✅ V1 system-managed | `i64` | BodyOrSoul::Body progressions + future aging V2+ |
| Initial clocks override | ✅ V1 OPTIONAL author | `InitialClocksDecl` on CanonicalActorDecl | xuyên không clock-split contract per Q11 |
| Subjective rate modifier | ❌ V1+30d (TDIL-D3) | — | Per-actor time dilation |
| Dilation target | ❌ V1+30d (TDIL-D4) | — | BodyOnly/SoulOnly chamber |
| Soul wandering | ❌ V1+30d (TDIL-D5) | — | Soul travels alone |
| Forge:AdvanceActorClock | ❌ V1+30d | — | When activated |
| Forge:AdvanceChannelClock | ❌ V1+30d (TDIL-D2) | — | |
| Past-clock edits | ❌ FORBIDDEN PERMANENTLY V1+ (TDIL-A8) | — | Worldline monotonicity |

### O. Cell membership (EF_001 entity_binding)

| Setting | V1 status | Type | Notes |
|---|---|---|---|
| `cell_id` (current location) | ✅ V1 mutable via Travel | `ChannelId` (cell-tier) | Sourced from CanonicalActorDecl.spawn_cell at bootstrap |

### P. AI tier (AIT_001; NPCs only)

| Setting | V1 status | Type | Notes |
|---|---|---|---|
| `tier_hint` | ✅ V1 immutable post-bootstrap (NPCs only) | `enum NpcTrackingTier { Major / Minor / Untracked }` | PC always None tier |
| Capacity cap (≤20 Major / ≤100 Minor per reality) | ✅ V1 enforced | — | Per AIT_001 §11 |
| Tier promotion | ❌ V1+30d (AIT-D1) | — | Significance threshold |
| Tier demotion | ❌ V1+30d (AIT-D2) | — | |
| Causal-ref pin | ❌ V1+30d (AIT-D6) | — | |
| Scripted attack | ❌ V1+30d (AIT-D18) | — | Untracked attack invalid |

---

## §3 Categorization for Advanced Mode UI

For PO_001 Advanced Mode wireframe, group settings into **8 visible UI sections** + **2 system-managed (read-only)** sections:

### User-editable sections (V1 active)

1. **Identity** (Category A) — name + role + voice register + physical text + gender pronouns + spawn cell
2. **Race & Origin** (B + E) — race + birthplace + lineage + native language + origin pack
3. **Personality, Mood & Beliefs** (D + F) — archetype + 4-axis mood + disposition + ideology stances + secret held + extensions JSON
4. **Knowledge & Languages** (C) — knowledge_tags + Vec<LanguageProficiency>
5. **Family & Lineage** (G) — parents + spouses + children + dynasty membership
6. **Faction & Reputation & Titles** (H + I + J) — single faction membership V1 + reputation rows + title holdings
7. **Skills & Progression** (K) — per-reality progression kinds với raw_value + current_tier
8. **Resources & Inventory** (L) — vital pools + currencies + items + global fame
9. **PC-Specific Body Memory** (M; only visible for PC actors) — Soul Layer + Body Layer + LeakagePolicy
10. **System (read-only)** (N + O + P) — actor_clocks + cell_id + AIT_001 tier

### V1+ deferred fields (show as locked with V1+ badge)

All V1+ deferred settings (~40+ across categories) shown as locked/disabled with badge:
- 📦 V1+30d (fast-follow)
- 📦 V2 (economy/strategy module)
- 📦 V2+ (Heresy / cross-reality)
- 🔒 Permanently forbidden (e.g., past-clock edits)

---

## §4 AI Assistant scope (cross-cutting)

AI Assistant operates ON TOP of these settings:
- **Read all current settings** as context
- **Natural-language input** from user ("I want a fox-spirit demon assassin who's the secret daughter of the emperor")
- **Output: structured field suggestions** for any V1 active settings
- **User reviews + applies** (apply all / apply some / reject)
- **Constraint awareness**: AI knows V1 active vs V1+ (won't suggest V1+ fields)
- **Reality-aware**: AI reads RealityManifest declarations (races/factions/titles/progression_kinds/places) and proposes only valid values
- **Coherence checking**: AI validates cross-feature consistency (e.g., if faction = Đông Hải Đạo Cốc, suggests role = "nội môn đệ tử"; if race = "demon clan" + ideology = "Devout Buddhist" — AI flags inconsistency)
- **Iterative refinement**: User can ask "make this character more {tragic / cunning / heroic}" — AI adjusts axes accordingly
- **Randomization within constraints**: "Surprise me — but keep ethnic = Vietnamese ancestry"

---

## §5 V1 implementation strategy (informational; not in this commit)

PO_001 V1 ships:
- **Mode B Custom PC = 8-step wizard (basic mode)** — for new players; uses M7 progressive disclosure + origin pack defaults
- **Advanced toggle** — switches to Advanced Mode showing all ~46 V1 settings organized in 10 sections
- **AI Assistant overlay** — accessible from any screen via floating button → modal; reads current state + reality manifest; suggests changes via LLM (chat-service)

V1+ deferred field activation propagates as consumer features ship (REP-D1 runtime delta → activates TIT-D2 + REP-D9 runtime gating; WA_001 closure pass adds 5-companion-fields → activates TIT-D3; PROG-D5 atrophy → activates Skills decay; etc.).

---

## §6 References

- ACT_001 spec — `features/00_actor/ACT_001_actor_foundation.md`
- IDF_001..005 specs — `features/00_identity/IDF_*.md`
- FF_001 spec — `features/00_family/FF_001_family_foundation.md`
- FAC_001 spec — `features/00_faction/FAC_001_faction_foundation.md`
- REP_001 spec — `features/00_reputation/REP_001_reputation_foundation.md`
- TIT_001 spec — `features/00_titles/TIT_001_title_foundation.md`
- PROG_001 spec — `features/00_progression/PROG_001_progression_foundation.md`
- RES_001 spec — `features/00_resource/RES_001_resource_foundation.md`
- PCS_001 spec — `features/06_pc_systems/PCS_001_pc_substrate.md`
- TDIL_001 spec — `features/17_time_dilation/TDIL_001_time_dilation_foundation.md`
- EF_001 spec — `features/00_entity/EF_001_entity_foundation.md`
- AIT_001 spec — `features/16_ai_tier/AIT_001_ai_tier_foundation.md`
- WA_006 mortality — `features/02_world_authoring/WA_006_mortality.md`
- DF05 sessions — `features/DF/DF05_session_group_chat/DF05_001_session_foundation.md`
