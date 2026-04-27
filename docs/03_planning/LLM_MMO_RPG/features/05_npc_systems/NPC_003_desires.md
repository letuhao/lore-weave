# NPC_003 — NPC Desires (LIGHT)

> **⚠ CLOSURE-PASS-EXTENSION 2026-04-27 (2nd) — DF05_001 Session/Group Chat CANDIDATE-LOCK 71a60346:**
>
> V1: Desires read-only consumer of DF05_001 session lifecycle (NPC desires inform LLM persona prompt assembly during session turns; influence dialogue toward desire fulfillment). V2+ via DF5-D7 (DF5-41 catalog): NPC desire-driven session creation — alice's desire to find brother triggers `Forge:CreateSession { anchor_pc_id: closest_PC, ... }` if PC reputation/proximity threshold met (NPC walks up to PC autonomously). NPC desire fulfillment may transition `satisfied: bool` field via `Forge:ToggleNpcDesire` AdminAction within session context (existing pattern preserved). NO change to NPC_003 LIGHT scope (no state machine / no objective tracking / no rewards V1); CANDIDATE-LOCK status PRESERVED. LOW magnitude — session-scope read-only V1; desire-driven creation V2+ deferral. Reference: [DF05_001 §9 V1 scope cut DF5-D7](../DF/DF05_session_group_chat/DF05_001_session_foundation.md#9--v1-scope-cut).

> **⚠ CLOSURE-PASS-EXTENSION 2026-04-27 — ACT_001 Actor Foundation unification refactor:**
>
> Per ACT_001 unification (commits 1c0d2d7 + 74b2854 + 3/5 this update), NPC_003's `desires` field has been TRANSFERRED from `npc` aggregate to `actor_chorus_metadata`:
>
> | OLD field path | NEW field path | Type rename |
> |---|---|---|
> | `npc.desires: Vec<NpcDesireDecl>` | **`actor_chorus_metadata.desires: Vec<DesireDecl>`** | `NpcDesireDecl` → `DesireDecl` (kind-agnostic) |
>
> **Why:** desires is L3 AI-drive metadata (per ACT-A2 3-layer model) — applicable to any AI-driven actor (NPCs always; PCs V1+ when AI-driven offline). Belongs on `actor_chorus_metadata` substrate, not on per-NPC aggregate.
>
> **Sparse storage:** V1 NPCs always have `actor_chorus_metadata` row → desires populated. PCs never have row V1 → desires not applicable. V1+ AI-controls-PC-offline activation (ACT-D1) creates `actor_chorus_metadata` row for offline PCs → desires populated by author/AI.
>
> **NPC_003 ROLE POST-UNIFY:** Owns `DesireDecl` shape + lifecycle semantics + canonical declaration pattern + RealityManifest declaration (`canonical_actors[*].chorus_metadata.desires` instead of separate `npc_desires` HashMap). NO state machine / NO objective tracking / NO rewards / 5-desires cap / i18n via I18nBundle / author-only satisfaction toggle V1 via Forge — all preserved.
>
> **RealityManifest extension simplified:** Pre-unify, NPC_003 had separate `npc_desires: HashMap<NpcId, Vec<NpcDesireDecl>>` extension. Post-unify, desires nested inside `canonical_actors[*].chorus_metadata.desires` (additive on CanonicalActorDecl). NPC_003 still owns the field shape + cap + i18n contract.
>
> **Authoritative spec (post-unify):** [ACT_001 §3.2](../../features/00_actor/ACT_001_actor_foundation.md#32-actor_chorus_metadata-t2--reality-scope--sparse-ai-drive-metadata) (actor_chorus_metadata aggregate hosts desires) + NPC_003 §1..§16 (DesireDecl shape + lifecycle + Forge contract preserved).
>
> **Acceptance scenarios (§16):** AC names updated to actor_chorus_metadata.desires terminology in commit 4/5 Phase 3 cleanup. Functional behavior preserved V1 (desires drive LLM-context for NPC; sandbox-mitigation V1 feature unchanged).
>
> See [`_boundaries/99_changelog.md`](../../_boundaries/99_changelog.md) 2026-04-27 ACT_001 entries for full unification details.

---

> **Conversational name:** "Desires" (DSR). Light author-declared NPC goal scaffolding — what each NPC wants. Pure data + LLM-context integration; NO state machine, NO objective tracking, NO rewards, NO completion logic.
>
> **Category:** NPC — NPC Systems (5th catalog category; sibling of NPC_001 Cast + NPC_002 Chorus)
> **Catalog reference:** [`catalog/cat_05_NPC_systems.md`](../../catalog/cat_05_NPC_systems.md) (NPC-3 entry — added 2026-04-26)
> **Status:** **DRAFT 2026-04-26** — Path A from [`13_quests/00_V2_RESERVATION.md`](../13_quests/00_V2_RESERVATION.md) §5; sandbox-mitigation V1 feature.
> **Builds on:** [NPC_001 Cast](NPC_001_cast.md) (extends `npc` aggregate with desires field per I14 additive evolution) + [RES_001 §2 i18n contract](../00_resource/RES_001_resource_foundation.md#2-i18n-contract-new-cross-cutting-pattern) (`I18nBundle` for desire text)

---

## §1 — Why this feature exists

User raised "game giống sandbox, chả có gì để làm" concern 2026-04-26 after foundation tier 5/5 closure. Full quest system is V2 (per [`13_quests/00_V2_RESERVATION.md`](../13_quests/00_V2_RESERVATION.md)); but V1 needs SOMETHING to give NPCs direction so the game doesn't feel goalless.

**NPC Desires LIGHT** is the cheapest viable scaffolding:
- Authors declare 1-3 desires per NPC at reality bootstrap (e.g., "expand my tavern" / "find my missing brother" / "learn the secret of Mặc Vô Kiếm")
- LLM persona prompt assembles desires alongside core_beliefs / flexible_state → NPC dialogue naturally references goals
- PCs can choose to help / oppose / ignore — emergent quest-feel without quest aggregate
- Author manually toggles `satisfied` flag via WA_003 Forge when desire fulfilled (no automatic detection V1)

This is NOT quest system. There is NO objective tracking, NO state machine, NO rewards, NO completion logic. Just "NPCs want things; LLM knows; players notice."

When V2 quest system arrives (QST_001), NPC desires becomes optional precursor — quest-givers may have related desires; QST owns formal tracking.

---

## §2 — Aggregate extension (NPC core)

NPC_001 §2 owns the `npc` core aggregate (per R8 split). NPC_003 ADDS one field per I14 additive evolution:

```rust
// EXTENSION to NpcCore (NPC_001 §2 owns; NPC_003 adds desires field 2026-04-26)
pub struct NpcCore {
    // ... existing fields per NPC_001 §2 (canonical_traits, core_beliefs_ref, flexible_state, etc.)

    /// Author-declared desires (NPC_003 — light goal scaffolding).
    /// V1: declared at reality bootstrap; toggled via WA_003 Forge AdminAction.
    /// LLM consumes via AssemblePrompt persona context section.
    /// NO state machine; NO objective tracking; NO automatic satisfaction detection.
    pub desires: Vec<NpcDesireDecl>,
}
```

No new aggregate. No schema-version bump (additive optional field; missing in old realities defaults to empty Vec).

---

## §3 — `NpcDesireDecl` shape

```rust
pub struct NpcDesireDecl {
    /// Stable author-declared ID per NPC. Used for Forge AdminAction targeting.
    pub desire_id: NpcDesireId,                   // newtype String, scoped to NPC

    /// Multi-language description of what the NPC wants.
    /// Per RES_001 §2 i18n contract: English `default` required; per-locale translations optional.
    pub kind: I18nBundle,

    /// 1-10. Affects how often LLM brings the desire up in dialogue (higher = more frequent).
    /// V1 simplification: AssemblePrompt sorts desires by intensity DESC; top-N included in
    /// persona context (N = author-tunable in RealityManifest, default 3).
    pub intensity: u8,

    /// Mutable runtime state. Author toggles via WA_003 Forge `Forge:ToggleNpcDesire` AdminAction.
    /// Satisfied desires REMAIN in the Vec (not removed) for forensic / canon-history reasons —
    /// LLM may still narratively reference past achievements ("Lão Vương tự hào kể chuyện
    /// đã mở rộng tiểu điếm năm ngoái").
    pub satisfied: bool,

    /// Optional context. Some desires connect to specific entities/places/items.
    /// LLM uses references to ground narration ("tìm anh thất lạc" + actor_ref → "tìm Trần Tử Bằng").
    pub references: Vec<EntityRef>,               // empty Vec = abstract desire (no specific target)
}

pub struct NpcDesireId(pub String);               // e.g., "expand_tavern" / "find_brother"
```

**Constraint:** Each NPC has ≤ 5 desires V1 (validator-enforced). Authors should focus on driving traits, not exhaustive goal lists. V1+ may relax cap.

---

## §4 — RealityManifest extension

Authors declare initial NPC desires alongside CanonicalActorDecl:

```rust
// EXTENSION to RealityManifest (added 2026-04-26 NPC_003 DRAFT)
RealityManifest {
    // ... existing fields per `_boundaries/02_extension_contracts.md` §2 ...

    /// Per-NPC initial desires. Indexed by NpcId. Empty default = NPC has no declared desires
    /// (LLM falls back to core_beliefs / flexible_state for narrative direction).
    pub npc_desires: HashMap<NpcId, Vec<NpcDesireDecl>>,

    /// AssemblePrompt N — top-N highest-intensity desires included in persona context.
    /// Default: 3 (matches PL_001 §17 prompt-budget discipline). Author-tunable per reality.
    pub desires_prompt_top_n: u8,
}
```

Validator at reality bootstrap:
- Each NpcDesireDecl in `npc_desires` MUST reference a valid NpcId in `canonical_actors`
- Each NPC's desires Vec ≤ 5 (V1 cap)
- desire_id MUST be unique within a single NPC's desires
- intensity ∈ 1..=10
- I18nBundle.default MUST be non-empty (English fallback required per RES_001 §2)

---

## §5 — LLM AssemblePrompt integration

NPC persona context section (per S09_prompt_assembly.md `[ACTOR_CONTEXT]` block) gets a new sub-section:

```
[ACTOR_CONTEXT: Lão Vương]
canonical_traits: { ... }
core_beliefs: { ... }
flexible_state: { mood: jovial, ... }
opinions: { LM01 → 0.8 }
desires (top 3 by intensity):
  - "Mở rộng tiểu điếm Phong Vũ Lâu thành 3 tầng" (intensity=8, unsatisfied)
  - "Tìm vợ thất lạc Lý Tú Anh trong loạn" (intensity=10, unsatisfied, ref: actor:lty_an)
  - "Học bí kíp pha trà của họ Trần đã thất truyền" (intensity=5, unsatisfied)
```

Rendering rules:
- Use active locale per RES_001 I18nBundle.render(locale) helper
- Sort by intensity DESC; take top-N (RealityManifest.desires_prompt_top_n; default 3)
- Append `(satisfied)` marker if satisfied=true (so LLM can reference past wins narratively)
- Append `(ref: <entity_summary>)` if references non-empty
- If `desires.is_empty()` → omit entire `desires:` section (no-op for NPCs without declared desires)

LLM is INSTRUCTED via system prompt to:
- Naturally reference desires in dialogue when contextually appropriate (not every turn)
- Not invent NEW desires (only those declared)
- Not auto-mark desires satisfied (author-only via Forge)

---

## §6 — Author lifecycle (WA_003 Forge integration)

NPC_003 adds 1 new AdminAction sub-shape (per WA_003 ForgeEditAction enum extension; locked at WA closure pass downstream):

```rust
pub enum ForgeEditAction {
    // ... existing variants per WA_003 §7 + per RES_001 §17.2 (4 RES-related variants) ...

    /// Toggle satisfied flag on an NPC desire. NEW 2026-04-26 NPC_003 DRAFT.
    /// Used by author when narrative beats fulfill a desire (LLM-generated story OR PC action).
    /// V1 = manual toggle only. V1+ may add LLM-detection-with-author-confirm.
    ToggleNpcDesire {
        npc_id: NpcId,
        desire_id: NpcDesireId,
        new_satisfied: bool,                      // typically false → true; reverse rare (canon retcon)
    },
}
```

Audit trail via `forge_audit_log` (WA_003-owned). Causal-ref to triggering EVT-T1 Submitted optional (LLM-narrated fulfillment may not have a single triggering turn).

V1 does NOT support:
- ❌ Adding new desires post-bootstrap (RealityManifest is the only declarator V1)
- ❌ Removing desires (satisfied desires persist in Vec for history)
- ❌ Modifying intensity post-bootstrap (V1+ deferred — DSR-D2)

V1+ deferrals:
- DSR-D1 — Forge `AddNpcDesire` / `RemoveNpcDesire` for runtime authoring
- DSR-D2 — `EditNpcDesireIntensity` for runtime tuning
- DSR-D3 — LLM-detected satisfaction-suggestion pipeline (author-confirms)

---

## §7 — Boundary

NPC_003 owns:
- `NpcDesireDecl` shape + `NpcDesireId` newtype
- `npc.desires` field (extension to NPC_001 npc aggregate per I14 additive)
- RealityManifest `npc_desires` + `desires_prompt_top_n` extensions
- `Forge:ToggleNpcDesire` AdminAction sub-shape
- AssemblePrompt rendering contract (when/how desires appear in `[ACTOR_CONTEXT]`)
- DSR-* stable-ID namespace (DSR-D* deferrals + DSR-Q* open questions)

NPC_003 does NOT own:
- NPC core aggregate (NPC_001 owns; NPC_003 just adds field via additive I14)
- Quest system (V2 deferred — `13_quests/`)
- Quest reward tracking (V2 deferred)
- Objective state machine (V2 deferred)
- Automatic satisfaction detection (V1+ deferred)
- Faction-tier desires (V3 — `15_organization/` ORG)

When QST_001 (V2) ships:
- Quests may REFERENCE NPC desires (quest-giver's desire fulfilled by quest completion)
- QST owns objective tracking; NPC_003 desires remain narrative scaffolding
- Author may manually toggle desire satisfied as part of QST quest completion logic
- These are CONNECTED but DISTINCT — NPC_003 stays light even after QST exists

---

## §8 — Acceptance criteria (5 V1-testable scenarios)

### AC-DSR-1 — Author declares desires; LLM context includes them
- Setup: Reality with NPC Lão Vương; RealityManifest.npc_desires[lao_vuong] = 3 desires (intensity 8, 10, 5)
- Action: PC starts session with Lão Vương present
- Expected: AssemblePrompt for Lão Vương's NPCTurn includes `desires:` section with all 3 (sorted by intensity DESC)

### AC-DSR-2 — Top-N filtering
- Setup: NPC has 5 desires (intensity 9, 8, 7, 6, 5); RealityManifest.desires_prompt_top_n = 3
- Action: AssemblePrompt
- Expected: only top 3 (intensity 9, 8, 7) appear; intensity 6 + 5 omitted from prompt

### AC-DSR-3 — Multi-locale rendering
- Setup: Active locale = `vi`; NpcDesireDecl.kind = I18nBundle { default: "Find missing wife", translations: {"vi": "Tìm vợ thất lạc"} }
- Action: AssemblePrompt rendered for active locale
- Expected: prompt shows "Tìm vợ thất lạc" (Vietnamese); English-locale session would show "Find missing wife"

### AC-DSR-4 — Author Forge toggles satisfied
- Setup: NPC has unsatisfied desire `expand_tavern`; PC over many sessions narratively helps Lão Vương expand tiểu điếm
- Action: Author invokes `Forge:ToggleNpcDesire { npc_id: lao_vuong, desire_id: "expand_tavern", new_satisfied: true }`
- Expected: forge_audit_log records edit; npc.desires Vec entry now satisfied=true; subsequent AssemblePrompt shows `(satisfied)` marker; LLM may now narratively reference Lão Vương's pride about expansion

### AC-DSR-5 — Empty desires omits prompt section
- Setup: NPC with `desires: vec![]`
- Action: AssemblePrompt
- Expected: NO `desires:` line appears in `[ACTOR_CONTEXT]` (saves prompt budget for NPCs without declared desires)

---

## §9 — Deferrals

- **DSR-D1** (V1+) — Forge `AddNpcDesire` + `RemoveNpcDesire` for runtime authoring (V1 = bootstrap-declared only)
- **DSR-D2** (V1+) — Forge `EditNpcDesireIntensity` for runtime tuning
- **DSR-D3** (V1+30d) — LLM-detected satisfaction-suggestion pipeline (LLM proposes "this desire seems satisfied"; author confirms via Forge)
- **DSR-D4** (V2) — Bridge to QST_001 quest system (NPC desires can spawn related quests; quest completion can auto-toggle desire)
- **DSR-D5** (V2) — Multi-NPC shared desires (3 sect members all want "destroy rival sect"; distinct from individual desires)
- **DSR-D6** (V3) — Faction-tier desires (ORG factions have collective goals — NOT NpcDesireDecl; new shape)
- **DSR-D7** (V1+30d) — Per-locale prompt rendering optimization (cache rendered desire strings per locale)
- **DSR-D8** (V2) — Desire conflict detection (author-helper UI flagging contradictory desires within same NPC)

---

## §10 — Open questions

- **DSR-Q1** — V1 prompt-budget impact: 3 desires × ~30 tokens each = ~90 tokens per NPC per AssemblePrompt. Acceptable V1; revisit if NPCs in scene > 5.
- **DSR-Q2** — LLM compliance: does LLM actually reference desires in dialogue, or ignore them? Needs V1 prototype measurement (similar to A4 retrieval quality OPEN). Risk: low — LLM is generally good at character motivation when given clear goals.
- **DSR-Q3** — Author UX: how do authors discover desires need declaring? V1 minimum: documentation. V1+30d: Forge UI prompts at NPC creation.

---

## §11 — Status

- **Created:** 2026-04-26 by main session
- **Phase:** DRAFT 2026-04-26
- **Status target:** CANDIDATE-LOCK after AC-DSR-1..5 acceptance scenarios specified with concrete fixtures + closure pass
- **Co-locked changes in this commit:** `_boundaries/01_feature_ownership_matrix.md` (npc aggregate desires field note + DSR-* prefix) + `_boundaries/02_extension_contracts.md` §2 (RealityManifest npc_desires + desires_prompt_top_n) + `_boundaries/99_changelog.md` + `catalog/cat_05_NPC_systems.md` (NPC-3 entry) + `05_npc_systems/_index.md` (NPC_003 row) + WA_003 Forge §7 ForgeEditAction enum extension noted (downstream — actual WA_003 closure pass folds in)
- **Approx size:** ~280 lines (matches LIGHT feature target — 30% below RES_001's ~900-line foundation feature)
