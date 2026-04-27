# PO_001 Player Onboarding — Concept Notes

> **Status:** CONCEPT 2026-04-27 — Phase 0 capture; Q-deep-dive batched decisions pending; transitions to LOCKED matrix when Q1-Q10 close.
> **Companion docs:** [`_index.md`](_index.md) (folder index) + [`01_REFERENCE_GAMES_SURVEY.md`](01_REFERENCE_GAMES_SURVEY.md) (reference materials) + [`wireframes/`](wireframes/) (12 HTML/CSS/MD files; FE-first design committed 19855a5b + 4c4fd6d7) + [`wireframes/ACTOR_SETTINGS_AUDIT.md`](wireframes/ACTOR_SETTINGS_AUDIT.md) (46 V1 actor settings × 14 features audit)
> **Stable-ID prefix:** `PO-*` (anticipated)
> **Catalog:** `catalog/cat_03_PO_player_onboarding.md` (planned at DRAFT 2/4 commit)

---

## §1 — User framing (FE-first approach)

User direction 2026-04-27: "ok, tiếp tục với PO_001 — nhưng trước đó nên thiết kế FE trước; thảo luận FE sau đó chúng ta quyết định draft html trước khi đi sâu vào thiết kế tính năng" (FE-first approach).

PO_001 is THE first user-visible feature post-foundation closure. Unlike backend Tier 5 features (PCS/ACT/IDF/FF/FAC/REP/TIT/PROG/RES/...), PO_001 is the GATEWAY from auth-service login to actual gameplay. UX must be locked BEFORE backend feature spec.

**Why PO_001 NOW (vs deferring):**

Cross-feature integration is mature — 14 locked features ship the primitives PO_001 needs:
- PCS_001 (Forge:RegisterPc + Forge:BindPcUser cascade) — CANDIDATE-LOCK
- ACT_001 (CanonicalActorDecl + actor_core canonical_traits) — CANDIDATE-LOCK
- IDF_001..005 (race + language + personality + origin + ideology) — all CANDIDATE-LOCK
- FF_001 + FAC_001 + REP_001 + TIT_001 (family/faction/rep/title) — all CANDIDATE-LOCK
- PROG_001 + RES_001 (skills/resources) — DRAFT
- PF_001 + EF_001 + TDIL_001 (places/entity/clocks) — all CANDIDATE-LOCK or CANDIDATE-LOCK target
- M7 progressive disclosure (multiverse charter)
- SR11 turn UX reliability (turn state machine)
- chat-service (Python/FastAPI; LLM via LiteLLM) — V1 platform service

PO_001 doesn't need new substrate — it's pure UX layer + thin orchestration over existing primitives.

### What V1 ships (per Q1-Q10 LOCKED anticipation)

- **3 onboarding modes** (Q1): (A) Canonical PC / (B) Custom PC / (C) Xuyên Không Arrival
- **Mode B 3-level UX** (Q2): Basic Wizard 8 steps + Advanced Settings (46 V1 fields) + AI Character Assistant
- **AI Character Assistant V1 active** (Q3): natural-language input → LLM-suggested field values via chat-service; reality-aware constraint checking; iterative tweak; 6 quick actions; constraint-aware (skips V1+ deferred fields)
- **Account creation** (Q4): email + password V1; OAuth V1+
- **Single-PC per reality** (Q5): cap=1 V1 per PCS-A9; PO_001 doesn't override
- **Reality switcher** (Q6): one-time selection per session V1; multi-reality character roster V1+
- **Save/resume** (Q7): all-or-nothing submit V1; auto-save per step V1+30d
- **Desktop-only V1** (Q8): mobile responsive V1+30d
- **First turn drop-in** (Q9): immediate spawn cell + LLM scene narration; SR11 state machine visible from turn 1
- **Inline tooltips minimal V1** (Q10): tooltip-on-hover V1; richer tutorial overlay V1+
- **NEW aggregate**: `actor_user_session` (T2/Reality, sparse per-(actor, session) — onboarding draft state V1+30d; minimal session tracking V1)
- **2 RealityManifest extensions** (both OPTIONAL V1): `onboarding_config: Option<OnboardingConfigDecl>` (per-reality mode availability + AI Assistant enable) + `canonical_pcs: Vec<ActorRef>` (Mode A picker source)
- **3 EVT-T8 AdminAction sub-shapes**: Forge:CreateOnboardingDraft + Forge:UpdateOnboardingDraft + Forge:CompleteOnboarding (all V1+30d active; V1 ships canonical seed + manual Forge admin)
- **Cross-aggregate validator C-rule**: PC creation cascade fires Forge:RegisterPc → Forge:BindPcUser → ACT_001 ActorBorn → EF_001 EntityBorn → IDF_*Born → FF_001 FamilyBorn → FAC_001 FactionMembershipBorn → REP_001 ReputationBorn → PROG_001 progression-init → TDIL_001 actor_clocks-init → SR11 first-turn-state
- **`onboarding.*` namespace** (~6-8 V1 reject rules + V1+ reservations)
- **Stable-ID prefix**: `PO-*`

### What V1 NOT shipping (deferred per anticipated Q-decisions)

| Feature | Defer to | Why |
|---|---|---|
| OAuth (Google/Discord) account creation | V1+ (PO-D1) | Q4 — V1 email+password only; OAuth requires auth-service integration |
| Multi-PC roster per reality | V1+ when PCS-D3 cap=1 relaxed (PO-D2) | Q5 — V1 PCS-A9 cap=1 |
| Auto-save per step + draft resume | V1+30d (PO-D3) | Q7 — V1 all-or-nothing submit |
| Mobile responsive layout | V1+30d (PO-D4) | Q8 — V1 desktop-only |
| Reality switcher mid-session | V2+ (PO-D5) | Q6 — V1 one-time selection |
| Character export/import | V2+ (PO-D6) | Cross-reality migration |
| Community-shared character templates | V2+ (PO-D7) | Social feature |
| AI-generated character portraits | V2+ (PO-D8) | Visual AI feature; chat-service V1 text-only |
| Voice-to-text input for AI Assistant | V2+ (PO-D9) | Speech-to-text infra |
| Richer tutorial overlay (post-creation) | V1+30d (PO-D10) | Q10 — V1 inline tooltips minimal |
| Reality-themed onboarding skin (per-reality custom UI) | V1+30d (PO-D11) | Visual variant; V1 single skin với reality-themed accent only |
| Onboarding telemetry analytics | V1+30d (PO-D12) | A/B testing infrastructure |

---

## §2 — Worked examples

### §2.1 Wuxia 3-mode walkthrough (PRIMARY V1 reference; Đông Phong Cõi)

**Mode A (Canonical PC) — pick Lý Lão Tổ:**
- User browses 5 canonical PCs (Lý Lão Tổ / Lý Tử / Phụng Nhi / Lý Đại Hoàng / Mạc Tà Phong)
- Clicks Lý Lão Tổ — sees portrait + bio + relationships + secrets + story hooks
- Clicks "Chọn Lý Lão Tổ →"
- Cascade: Forge:BindPcUser binds user_id to existing canonical_actor.ly_lao_to; pc_user_binding.user_id_init populated
- First turn: drop into Đông Hải Đạo Cốc đỉnh Hàn Tuyết Phong; LLM-narrated scene
- Time: ~2 minutes from landing to first turn

**Mode B (Custom PC) — basic wizard then advanced toggle:**
- User picks Đông Phong Cõi reality
- Picks Mode B — enters 8-step wizard
- Step 1: Name "Lý Minh" + đại từ "anh/em (m)"
- Step 2: Race "Người Hán"
- Step 3: Origin pack "Đông Hải coastal village" (sets language + ideology + birthplace defaults)
- Step 4: Personality "Mưu mô (Cunning)"
- Step 5: Faction "Đông Hải Đạo Cốc / nội môn đệ tử / master: Lý Lão Tổ"
- Step 6: Appearance text "Thanh niên 22 tuổi, dáng người gầy nhưng săn chắc..."
- Step 7: Spawn cell "Đông Hải Đạo Cốc tu luyện thất"
- Step 8: Review & confirm
- (User clicks Advanced toggle midway — reviews 46 fields; tweaks mood sliders + adds secret_held + edits ideology stances)
- Confirm: Forge:RegisterPc cascade emits 10+ events (ActorBorn + EntityBorn + RaceBorn + LanguageBorn + PersonalityBorn + OriginBorn + IdeologyStanceBorn + FamilyBorn + FactionMembershipBorn + ReputationBorn + actor_clocks-init + first-turn-state)
- Time: ~5 minutes basic wizard; ~10-15 with Advanced

**Mode C (Xuyên Không Arrival) — Disco Elysium amnesia + wuxia transmigration:**
- User picks Mode C
- Step 1 Soul Layer: origin world "Trái Đất hiện đại 2026" + knowledge tags [internet, wuxia_meta_knowledge, modern_weapons] + native language "Vietnamese"
- Step 2 Body Layer: pick host body "Lý Minh deceased disciple" (just died from cultivation deviation; soul nhập vào trước khi cơ thể lạnh)
- Step 3 LeakagePolicy: "SoulPrimary { body_blurts_threshold: 0.3 }" — original body occasionally blurts under stress
- Step 4 Spawn cell: inherited from body (cultivation chamber)
- Step 5 First reveal: LLM-generated opening narration — "Bạn mở mắt. Trên trần là gỗ thô đen. Phổi đau như rách... Đây là... đâu? Tay bạn — không phải tay bạn..."
- Cascade: Forge:RegisterPc với body_memory_init populated (Soul + Body + LeakagePolicy)
- First turn: spawn cell scene với amnesia framing; player gradually rediscovers identity through gameplay
- Time: ~7 minutes; dramatic narrative onboarding

### §2.2 AI Character Assistant walkthrough

User input: "Tôi muốn tạo một thiếu nữ hồ ly tinh, là con gái bí mật của Hoàng đế, từng đọc nhiều tiểu thuyết tu tiên ở Trái Đất và xuyên không vào đây. Cá tính cunning, tu vi Trúc Cơ, biết kiếm pháp + bùa chú. Sống ở Đông Hải Đạo Cốc nhưng bí mật là gián điệp của Ma Tông..."

AI Assistant maps to 18 fields across 9 categories:
- Identity (5): name "Lý Phụng Nhi" + role "Đông Hải Đạo Cốc nội môn đệ tử kiêm nội ứng Ma Tông" + voice + physical + gender_pronouns "cô/em"
- Race & Origin (4): race "fox_spirit_lineage" + birthplace "imperial_capital_palace_secret_quarters" + lineage "li_imperial (secret)" + native_language "imperial_mandarin"
- Personality, Mood & Beliefs: archetype "Cunning" + mood {joy: 35, anger: 60, sadness: 70, fear: 45} + disposition "Suspicious" + secret_held "Ma Tông double agent + Earth-soul transmigrator" + 2 ideology stances (cover + true)
- Family: father "imperial_emperor (secret bio)" + mother "imperial_concubine (deceased)"
- Faction · Rep · Title: faction "donghai_dao_coc / inner_disciple / master: ly_lao_to" + rep[donghai_dao_coc]=+250 Friendly + rep[ma_tong]=+800 Revered (secret)
- Skills: qi_cultivation tier 2 Trúc Cơ + sword_arts 480 + intelligence 28
- PC Body Memory: soul.origin_world_ref "earth_modern_2026" + soul.knowledge_tags [internet, wuxia_meta_knowledge, fox_folklore, espionage_basics] + body.host_body_ref "deceased_ly_phung_nhi_npc" + leakage_policy "Balanced"

Iterative tweak: user requests "complicate secret further — she doesn't know she's Imperial Princess; mother concealed at birth; reveal trigger chương 50". AI refines secret_held to "Ma Tông double agent + Earth-soul transmigrator (TWO secrets only — không biết về Imperial bloodline)" + adds narrative_arc_hook (LLM canon-only; not PC-visible).

3 coherence checks fired:
- ✅ fox_spirit_lineage exists in RealityManifest.races
- ⚠ imperial_emperor not directly linkable as biological_father — needs author coordination
- ⚠ rep[imperial_court]=+400 ghost rep allowed under sparse storage

User clicks "Apply all 18 fields" → returns to Advanced Settings với fields populated → continues to Confirm → First Turn.

### §2.3 Modern Saigon variant (Mode B basic wizard)

Reality: Saigon 2026 — Modern noir reality.

User picks Saigon 2026 (theme switches to neon pink/cyan dark mode). Picks Mode B basic wizard:
- Step 1: Name "Trần Văn Hùng" + đại từ "anh/em (m)"
- Step 2: Race "Người Việt" (no exotic races in modern reality)
- Step 3: Origin pack "Quận 1 mid-class" (sets language Vietnamese + ideology Pragmatic + birthplace q1)
- Step 4: Personality "Loyal"
- Step 5: Faction "Saigon Police / Detective Q1 / master: Captain Phạm"
- Step 6: Appearance "30 tuổi, mặt trầm lặng, tay trái có sẹo"
- Step 7: Spawn cell "Saigon Police HQ Q1"
- Step 8: Review & confirm
- First turn: police HQ scene; first case briefing

Same flow; reality-themed accent dynamically switches; AI Assistant respects Saigon RealityManifest constraints (no race "fox_spirit_lineage"; uses faction "saigon_police_q1" not "donghai_dao_coc").

---

## §3 — Domain concepts (anticipated)

### §3.1 OnboardingConfigDecl (RealityManifest declaration)

```rust
pub struct OnboardingConfigDecl {
    pub modes_enabled: Vec<OnboardingMode>,                // V1: 3-variant subset (Canonical/Custom/XuyenKhong)
    pub canonical_pcs: Vec<ActorRef>,                      // Mode A picker source; canonical_actors[kind=Pc]
    pub ai_assistant_enabled: bool,                        // V1: per-reality opt-in (Wuxia ON; sandbox/freeplay may opt-out)
    pub default_spawn_cell: ChannelId,                     // Fallback if user skips spawn cell selection
    pub onboarding_skin: Option<I18nBundle>,               // V1+ PO-D11 reality-themed skin variant
    pub tutorial_steps: Vec<TutorialStepDecl>,             // V1+ PO-D10 richer tutorial
}

pub enum OnboardingMode {
    Canonical,       // Mode A — pick from canonical_pcs
    Custom,          // Mode B — basic wizard + Advanced + AI Assistant
    XuyenKhong,      // Mode C — Disco Elysium amnesia + wuxia transmigration
}

pub struct TutorialStepDecl {                              // V1+ schema-reserved per Q10
    pub step_id: String,
    pub trigger: TutorialTrigger,                          // OnEnter / OnFirstAction / OnDuration
    pub content: I18nBundle,
}
```

### §3.2 actor_user_session aggregate (V1 minimal session tracking)

```rust
#[derive(Aggregate)]
#[dp(type_name = "actor_user_session", tier = "T2", scope = "reality")]
pub struct ActorUserSession {
    pub reality_id: RealityId,
    pub actor_ref: ActorRef,
    pub session_id: SessionId,
    pub user_id: UserId,
    pub onboarding_completed_at_turn: Option<u64>,         // None = onboarding in-progress; Some = completed
    pub onboarding_mode: OnboardingMode,
    pub schema_version: u32,
    // V1+30d additive (PO-D3): pub onboarding_draft: Option<OnboardingDraft>,
    // V1+ additive (PO-D2): multi-PC roster — Vec<actor_ref> instead of single
}
```

### §3.3 Cascade pseudocode (PC creation post Mode B confirm)

```pseudo
on Forge:CompleteOnboarding(user_id, mode, draft_data, reality_id):
  // Validation
  reject_if reality_id not in user's accessible realities → onboarding.reality_unauthorized
  reject_if mode not in onboarding_config.modes_enabled → onboarding.mode_unsupported
  reject_if draft_data invalid for mode → onboarding.draft_invalid
  reject_if reality.canonical_actors[kind=Pc].count >= max_pc_count → onboarding.pc_cap_exceeded (V1: cap=1)
  
  // Atomic 3-write transaction (PCS_001 + ACT_001 + EF_001 cascade)
  WRITE 1: insert canonical_actor (CanonicalActorDecl from draft_data; if Mode A: lookup existing canonical_pc)
  WRITE 2: emit Forge:RegisterPc + Forge:BindPcUser cascade events
  WRITE 3: append forge_audit_log entry
  
  // Cascade events (synchronous same turn)
  emit ActorBorn (ACT_001)
  emit EntityBorn (EF_001) at spawn_cell
  emit RaceBorn (IDF_001)
  emit LanguageBorn (IDF_002) for each declared language
  emit PersonalityBorn (IDF_003)
  emit OriginBorn (IDF_004)
  emit IdeologyStanceBorn (IDF_005) for each declared stance
  emit FamilyBorn (FF_001) if family_node populated
  emit FactionMembershipBorn (FAC_001) if faction declared
  emit ReputationBorn (REP_001) for each declared rep row
  emit TitleGranted (TIT_001) if origin pack default_titles V1+ (PO-D-#)
  emit ProgressionInit (PROG_001) for declared progression_kinds
  emit ResourceInit (RES_001) for vital_pool + currencies + items
  emit actor_clocks-init (TDIL_001)
  emit OnboardingCompleted (PO_001)
  
  // First turn state initialization
  initialize SR11 turn UX state machine for actor
  generate LLM scene narration via chat-service
  return turn_id of first turn
```

---

## §4 — Boundary intersections with locked features

| Locked feature | PO_001 V1 interaction |
|---|---|
| **EF_001 Entity Foundation** | Reads ActorId source-of-truth; emits EntityBorn at spawn_cell |
| **PF_001 Place Foundation** | Reads RealityManifest.places for spawn cell selection (Mode B Step 7) |
| **ACT_001 Actor Foundation** | Consumes CanonicalActorDecl shape; populates actor_core canonical_traits + flexible_state_init + mood_init |
| **PCS_001 PC Substrate** | RESOLVES PCS-D1 (runtime login flow) + PCS-D10 (UI integration); orchestrates Forge:RegisterPc + Forge:BindPcUser cascade |
| **IDF_001..005** | Mode B wizard steps consume race/language/personality/origin/ideology decls |
| **FF_001 Family Foundation** | Mode B Advanced allows family relations input (parents/spouses/children); emits FamilyBorn |
| **FAC_001 Faction Foundation** | Mode B Step 5 + Advanced — faction membership input; emits FactionMembershipBorn |
| **REP_001 Reputation Foundation** | Mode B Advanced — initial reputation rows per faction; emits ReputationBorn |
| **TIT_001 Title Foundation** | V1+ origin pack default_titles via TIT-D10; V1 typically no titles at PC creation |
| **PROG_001 Progression Foundation** | Mode B + Advanced — initial progression values per ClassDefaultDecl; emits ProgressionInit |
| **RES_001 Resource Foundation** | Mode B + Advanced — initial vital pools + currencies + items; emits ResourceInit |
| **TDIL_001 Time Dilation Foundation** | actor_clocks initialized at PC creation (3-clock system; xuyên không clock-split if Mode C) |
| **AIT_001 AI Tier Foundation** | PCs always None tier (PO_001 doesn't override) |
| **WA_006 Mortality** | mortality_state initialized to Alive |
| **WA_003 Forge** | 3-write atomic Forge admin pattern + forge_audit_log (CompleteOnboarding event) |
| **chat-service** (Python/FastAPI) | AI Character Assistant V1 dependency — LLM via LiteLLM; reads RealityManifest for constraint awareness; suggests 18+ fields per natural-language input |
| **auth-service** | Account creation V1 (email + password); JWT issuance for session |
| **api-gateway-bff** | First WS connection + ticket exchange per S12 |
| **knowledge-service** | Reads canonical glossary entries for AI Assistant constraint validation |
| **M7 progressive disclosure** | Mode B "Skip → use defaults" CTA enforces tier defaults via origin pack |
| **SR11 turn UX reliability** | First turn state machine visible from turn 1 (PO_001 §05 first turn screen) |
| **UI_COPY_STYLEGUIDE** | Tooltip + first-run copy governance |

---

## §5 — Gap analysis (10 dimensions across 4 grouped concerns)

### Concern A: Mode scope + Custom PC depth (Q1 + Q2)

**Q1**: Mode selection scope V1 — 3 modes (Canonical/Custom/XuyenKhong) confirmed?
- (A) 3 modes V1 (Canonical + Custom + XuyenKhong) — wireframes anchor; all 3 work via existing PCS_001 primitives
- (B) 2 modes V1 (Custom + XuyenKhong); Canonical V1+
- (C) 1 mode V1 (Custom only); Canonical + XuyenKhong V1+

Pre-recommendation: **(A)** 3 modes V1 — wireframes locked; all 3 use existing primitives; no extra backend required.

**Q2**: Custom PC wizard depth V1 — Basic Wizard only OR Basic + Advanced OR Basic + Advanced + AI Assistant?
- (A) 3-level (Basic + Advanced + AI Assistant) V1 — wireframes anchor
- (B) 2-level (Basic + Advanced; AI Assistant V1+30d)
- (C) 1-level (Basic only V1; Advanced V1+30d; AI Assistant V1+30d)

Pre-recommendation: **(A)** 3-level V1 — chat-service is a V1 platform service; AI Assistant adds significant value for power users; wireframes already demonstrate full UX.

### Concern B: AI Assistant + Account (Q3 + Q4)

**Q3**: AI Character Assistant V1 active OR V1+ deferred?
- (A) V1 active — natural-language input → LLM field suggestions via chat-service
- (B) V1+30d deferred — concept proven via wireframes; defer until chat-service hardened
- (C) V1 active for Mode B Advanced only; V1+ standalone full-screen

Pre-recommendation: **(A)** V1 active — chat-service is V1 platform service (already operational); reality-aware constraint checking via knowledge-service; iterative tweak demonstrated in wireframes; significant onboarding value.

**Q4**: Account creation V1 scope — email+password only OR OAuth day-one?
- (A) Email + password V1; OAuth V1+ (PO-D1)
- (B) OAuth (Google + Discord) V1; email/password V1+
- (C) Both V1 (email + OAuth)

Pre-recommendation: **(A)** Email + password V1 — minimum auth-service scope; OAuth V1+ when auth-service ships OAuth integration.

### Concern C: Persistence + Mobile (Q5 + Q6 + Q7 + Q8)

**Q5**: Multi-PC roster V1 — per PCS-A9 cap=1 V1?
- (A) Cap=1 V1 (matches PCS-A9 LOCKED) — single PC per reality
- (B) Multi-PC V1 — override PCS-A9 (NOT viable; PCS-A9 LOCKED 2026-04-27)

Pre-recommendation: **(A)** cap=1 V1 — matches PCS-A9; PO-D2 deferral when PCS-D3 cap relaxed V1+.

**Q6**: Reality switcher V1 — locked-in selection per session OR mid-session switch?
- (A) Locked-in per session (one-time selection at landing) — V1 simple
- (B) Mid-session switcher (V2+ feature; requires sub-session migration)

Pre-recommendation: **(A)** locked-in V1 — V2+ mid-session switcher (PO-D5).

**Q7**: Save/resume during onboarding — auto-save per step OR all-or-nothing submit?
- (A) All-or-nothing V1 (submit at end; no draft persistence) — simplest
- (B) Auto-save per step V1+30d (PO-D3) — UX improvement
- (C) Local storage draft V1; server-side draft V1+30d

Pre-recommendation: **(A)** all-or-nothing V1 — V1+30d auto-save (PO-D3).

**Q8**: Mobile responsive V1 — desktop-only V1 OR responsive day-one OR mobile-first?
- (A) Desktop-only V1; mobile responsive V1+30d (PO-D4)
- (B) Both V1
- (C) Mobile-first V1 (priority on mobile)

Pre-recommendation: **(A)** desktop-only V1 — wireframes are desktop-optimized; mobile V1+30d when responsive layout designed.

### Concern D: First turn + Tutorial (Q9 + Q10)

**Q9**: First turn integration — drop into spawn cell immediately OR show summary first OR prologue narration?
- (A) Immediate drop into spawn cell + LLM scene narration — wireframes anchor
- (B) Show PC summary card before first turn (BG3 pattern post-creation)
- (C) Prologue narration (Cyberpunk lifepath opening cinematic)

Pre-recommendation: **(A)** immediate drop-in — fastest path to gameplay; matches wireframes; LLM scene narration provides context organically.

**Q10**: Tutorial integration — inline tooltips during creation OR separate tutorial post-creation OR none V1?
- (A) Inline tooltips minimal V1; richer tutorial overlay V1+30d (PO-D10)
- (B) Separate tutorial post-creation V1
- (C) No tutorial V1; all V1+

Pre-recommendation: **(A)** inline tooltips minimal V1 — concrete and lightweight; richer onboarding V1+30d when content authored.

---

## §6 — Q1-Q10 critical scope questions (for batched deep-dive)

| # | Question | Options | Pre-rec |
|---|---|---|---|
| Q1 | Mode selection scope V1 | A (3 modes) / B (2 modes) / C (1 mode) | A |
| Q2 | Custom PC wizard depth V1 | A (3-level) / B (2-level; AI V1+) / C (Basic only) | A |
| Q3 | AI Character Assistant V1 timing | A (V1 active) / B (V1+30d) / C (V1 partial) | A |
| Q4 | Account creation V1 scope | A (email+pwd) / B (OAuth) / C (both) | A |
| Q5 | Multi-PC roster V1 | A (cap=1 per PCS-A9) / B (multi V1) | A |
| Q6 | Reality switcher V1 | A (locked-in) / B (mid-session V2+) | A |
| Q7 | Save/resume V1 | A (all-or-nothing) / B (auto-save V1+30d) / C (local-only V1) | A |
| Q8 | Mobile responsive V1 | A (desktop V1; mobile V1+30d) / B (both V1) / C (mobile-first) | A |
| Q9 | First turn integration | A (immediate spawn) / B (summary first) / C (prologue narration) | A |
| Q10 | Tutorial V1 | A (inline tooltips minimal) / B (separate tutorial) / C (none V1) | A |

**Q-decision philosophy:** V1 minimum scope; FE-first wireframes already validate UX direction; conservative on backend scope (chat-service + auth-service email+pwd only V1); aggressive on UX (3 modes + 3-level Mode B + AI Assistant V1 active because wireframes demonstrate clear value).

---

## §7 — V1 reject rules (`onboarding.*` namespace; anticipated)

| rule_id | Trigger | Vietnamese display |
|---|---|---|
| `onboarding.reality_unauthorized` | User tries to create PC in reality they don't have access to | "Bạn không có quyền truy cập thế giới này" |
| `onboarding.mode_unsupported` | User tries mode not in onboarding_config.modes_enabled | "Chế độ tạo nhân vật này không khả dụng cho thế giới này" |
| `onboarding.draft_invalid` | Mode B draft data fails schema validation (e.g., race not in canonical_races) | "Dữ liệu nhân vật không hợp lệ" |
| `onboarding.pc_cap_exceeded` | User tries to create PC when reality's max_pc_count reached (V1: cap=1) | "Đã đạt giới hạn số nhân vật cho thế giới này" |
| `onboarding.canonical_pc_unavailable` | Mode A picker — canonical PC already bound to another user | "Nhân vật này đã được người chơi khác chọn" |
| `onboarding.spawn_cell_unauthorized` | User picks spawn cell not in reality.places | "Vị trí xuất hiện không hợp lệ" |
| `onboarding.user_already_has_pc` | User tries to create second PC in single-reality V1 | "Bạn đã có nhân vật trong thế giới này" |

V1+ reservations:
- `onboarding.draft_resume_failed` — V1+30d (PO-D3 auto-save resume)
- `onboarding.oauth_provider_invalid` — V1+ (PO-D1 OAuth)
- `onboarding.ai_assistant_unavailable` — V1+ if chat-service down fallback
- `onboarding.tutorial_step_invalid` — V1+ (PO-D10)
- `onboarding.cross_reality_migration_unsupported_v1` — V2+ (PO-D6 character export/import)

---

## §8 — Reference materials slot

User-provided sources: pending. Reference games surveyed in [`01_REFERENCE_GAMES_SURVEY.md`](01_REFERENCE_GAMES_SURVEY.md):
- BG3 (PRIMARY anchor — Origin Character vs Custom dual-mode)
- Cyberpunk 2077 (lifepath narrative branching)
- Disco Elysium (amnesia framing — Mode C anchor)
- AI Dungeon (custom prompt freedom — AI Assistant inspiration)
- NovelAI (writer-mode flexible structure)
- FFXIV (MMO standard — race/class flow)
- Lost Ark (class-first MMO action)
- Pathfinder Wrath (deep customization)
- Persona series (cinematic intro)

Cross-genre:
- Stardew Valley (warmth + minimal customization)
- The Sims (extensive sliders; visual emphasis)
- Skyrim (race + appearance + tutorial Helgen)

---

## §9 — Status

- **Created:** 2026-04-27 by main session
- **Phase:** CONCEPT 2026-04-27 — Phase 0 capture (post-wireframes commits 19855a5b + 4c4fd6d7)
- **Status target:** Q1-Q10 LOCKED → DRAFT 2/4 commit (~700-900 lines PO_001_player_onboarding.md + boundary updates + catalog seed + WITH `[boundaries-lock-claim]`)
- **Companion docs:**
  - [`_index.md`](_index.md) (folder index)
  - [`01_REFERENCE_GAMES_SURVEY.md`](01_REFERENCE_GAMES_SURVEY.md) (reference materials)
  - [`wireframes/`](wireframes/) — 12 files HTML/CSS/MD; FE-first design committed 19855a5b + 4c4fd6d7
  - [`wireframes/ACTOR_SETTINGS_AUDIT.md`](wireframes/ACTOR_SETTINGS_AUDIT.md) — 46 V1 actor settings × 14 features inventory

## §10 — Q-LOCKED matrix (FILLED at Q-deep-dive completion)

| Q | LOCKED decision | Variants | Justification |
|---|---|---|---|
| Q1 | TBD | TBD | TBD |
| Q2 | TBD | TBD | TBD |
| Q3 | TBD | TBD | TBD |
| Q4 | TBD | TBD | TBD |
| Q5 | TBD | TBD | TBD |
| Q6 | TBD | TBD | TBD |
| Q7 | TBD | TBD | TBD |
| Q8 | TBD | TBD | TBD |
| Q9 | TBD | TBD | TBD |
| Q10 | TBD | TBD | TBD |

(Filled when batched Q-deep-dive locks all 10.)
