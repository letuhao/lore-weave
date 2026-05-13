# 17_time_dilation — Index

> **Category:** TDIL — Time Dilation (architecture-scale; 4-clock relativity model for cross-realm time + cultivation rate variance + xuyên không clock-split)
> **Catalog reference:** [`catalog/cat_17_TDIL_time_dilation.md`](../../catalog/cat_17_TDIL_time_dilation.md) (27 entries; 17 V1 ✅ + 6 V1+30d 📦 + 4 V2/V3+ 📦; 10 axioms TDIL-A1..A10)
> **Purpose:** Defines how fiction-time flows differently across realms/cells/actors. Solves 4 user-raised concerns: (1) tu tiên cultivation rate mismatch (newbie vs 元嬰 incompatible same-clock); (2) multi-realm time variance (Tây Du Ký 天上一日人間一年); (3) time chambers (Dragon Ball 精神時光屋); (4) PvP newbie-gank prevention. Architecture maps cleanly to Einstein's special + general relativity (proper time vs coordinate time). 4-clock model (realm + actor + soul + body) generalizes twin paradox to soul-body separation (xuyên không clock-split).

**Active:** (empty — folder closure 2026-04-27)

**Folder closure status:** **COMPLETE 2026-04-27** — TDIL_001 **CANDIDATE-LOCK 2026-04-27** (DRAFT bdc8d8e1 → CANDIDATE-LOCK closure pass single combined `[boundaries-lock-claim+release]` commit; Phase 3 detected no drift). Q1-Q12 ALL LOCKED via 4-batch deep-dive (zero revisions). 17 V1 catalog entries TDIL-1..TDIL-17 + 6 V1+30d TDIL-18..23 + 4 V2/V3+ TDIL-24..27. 10 axioms TDIL-A1..A10. 4 V1 reject rule_ids in `time_dilation.*` namespace + 6 V1+30d reservations. 5 RealityManifest extensions OPTIONAL V1. Cross-feature closure-pass-extensions to PROG_001 / RES_001 / AIT_001 confirmed applied at DRAFT promotion via `bdc8d8e1` (mechanical day-boundary → turn-boundary semantic per TDIL-A3). 10 V1 acceptance scenarios AC-TDIL-1..10 walkthrough verified.

**LOCK target after** AC-TDIL-1..10 V1-testable scenarios pass integration tests + V1+ TDIL-D1..D5 ship (Forge:AdvanceActorClock + Option B subjective rate + DilationTarget enum + soul wandering — V1+30d items). Implementation phase post-CANDIDATE-LOCK consumes `time_dilation.*` namespace + `actor_clocks` aggregate + 5 RealityManifest extensions.

**NOT a foundation tier feature:** Foundation tier remains 6/6 (closed at PROG_001). TDIL_001 is **architecture-scale Tier 5+ Actor Substrate scaling/architecture feature** (mirrors AIT_001 pattern). Opt-in per reality — modern social reality = no time dilation; tu tiên reality = rich time dilation config.

---

## Why this folder exists

User raised 4 interconnected concerns 2026-04-27 (during AIT_001 closure window):

> "ví dụ cột mốc thời gian trong Tiên Nghịch hoặc Tây Du Ký
> nếu 1 turn (page-flip effect) cho 1 người chơi đều là cố định thì có 1 vấn đề là hệ thống tu luyện không thể hoạt động được
> ví dụ bạn không thể tu tuyện cùng thời gian với 2 người khác cảnh giới được
>
> thần tiên trên trời và phàm nhân dưới đất thuộc 2 thế giới khác nhau có khái niệm thời gian khác nhau
> và ngay cả cùng 1 thế giới thì mỗi người có thời gian trôi qua khác nhau (như câu chuyện phòng tập thời gian trong dragon ball)
>
> nếu chúng ta không giải quyết được điều này thì game tu tiên rất vô lý, ngoài ra nếu giải quyết tốt thì sẽ hạn chế việc mấy người chơi tu vi cao cứ canh ở làng tân thủ đi giết người chơi tu vi thấp"

Translation: cultivation game broken without time variance. Heaven realm vs mortal realm = different time concepts. Same realm + different individuals = different time experiences (Dragon Ball time chamber). Anti-grief: high-cultivators camping newbie zones disincentivized via time variance.

User then refined via 4 architectural insights during deep-dive 2026-04-27:

1. **Generators fire per-turn O(1), NOT per-day** — replacing PROG/RES/AIT day-boundary semantic. 1 turn = 1 generator trigger; computation = `base_rate × elapsed_time × multiplier`.
2. **Atomic-per-turn travel** — actor in one channel for entire turn; no mid-turn cross-channel.
3. **Per-realm turn streams** — heaven_clock advances only on heaven activity; independent from mortal_clock.
4. **4-clock model** — realm clock + actor clock + soul clock + body clock; soul/body separability enables xuyên không state preservation.

→ TDIL_001 owns the time-relativity layer: `time_flow_rate` per channel + `actor_clocks` aggregate + per-turn O(1) Generator semantic guidance + cross-realm observation rules.

---

## Feature list

| ID | Conversational name | Title | Status | File | Commit |
|---|---|---|---|---|---|
| (concept) | **00_CONCEPT_NOTES.md** — TDIL_001 brainstorm + Einstein relativity analysis + 4-clock model | CONCEPT 2026-04-27 — captures user 4 concerns + physics-aligned semantics + 12 open questions | [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) | (this commit) |
| TDIL_001 | **Time Dilation Foundation** (TDIL) | (awaiting Q1-Q12 lock) — 4-clock relativity architecture: realm clock (per channel) + actor_clock (proper time integrated) + soul_clock (BodyOrSoul::Soul progressions) + body_clock (BodyOrSoul::Body progressions + future aging). `time_flow_rate: f32` per channel + cell-level override (Convention B physics-aligned: proper time per wall time; >1 fast like Dragon Ball chamber, <1 slow like Tây Du Ký heaven). Per-turn O(1) Generator semantic (corrects PROG/RES/AIT day-boundary lock). Atomic-per-turn travel. Per-realm turn streams (heaven_clock independent from mortal_clock). Cross-realm observation O(1) materialization. xuyên không clock-split (soul brings soul_clock; body keeps body_clock). LLM context dilation-aware (~30-50 tokens per non-default actor). Replay determinism free V1 (static rates). | NOT YET DRAFTED | (to be created) | n/a |

---

## Why this folder is concept-first

TDIL_001 has heavy cross-cutting impact. Per concept-notes-first discipline established by RES_001 / PROG_001 / AIT_001:

1. Capture user's 4 concerns + 4 architectural insights (verbatim Vietnamese)
2. Reference patterns (Einstein SR/GR + 5 reference games/stories)
3. 4-clock spec sketch (realm/actor/soul/body)
4. Convention B `time_flow_rate` semantic with worked examples
5. Boundary intersection (heavy: PROG/RES/AIT need closure-pass revision)
6. Critical scope questions (Q1-Q12) for V1 minimum + V1+ extensibility
7. Reference materials slot for incoming research

Mirror successful pattern (PROG_001 6-batch deep-dive; AIT_001 4-batch).

---

## Kernel touchpoints (anticipated; finalized at TDIL_001 DRAFT)

- `06_data_plane/02_invariants.md` — DP-A14 scope/tier annotations on actor_clocks aggregate
- `07_event_model/03_event_taxonomy.md` — Generator semantic revision (per-turn O(1) instead of per-day)
- `_boundaries/01_feature_ownership_matrix.md` — `actor_clocks` aggregate + TDIL-* prefix at DRAFT
- `_boundaries/02_extension_contracts.md` §1.4 — `time_dilation.*` rule_id namespace
- `_boundaries/02_extension_contracts.md` §2 — RealityManifest extensions (channel-level + cell-level rate)
- `00_progression/PROG_001` — closure-pass revision: Q3f day-boundary → turn-boundary; ProgressionInstance reads body_clock or soul_clock per BodyOrSoul
- `00_resource/RES_001` — closure-pass revision: Q4 day-boundary → turn-boundary; channel-bound generators read wall_clock; actor-bound generators read body_clock
- `16_ai_tier/AIT_001` — closure-pass revision: §7.5 materialization O(1) instead of per-day replay
- `04_play_loop/PL_001 Continuum` — fiction_clock per channel unchanged; per-turn ActorClocks advancement integrated
- `04_play_loop/PL_005 Interaction` — combat formula reads body_clock for V1+ reaction speed
- `00_entity/EF_001 Entity Foundation` — entity_binding location change cascades clock-channel context
- `00_place/PF_001 Place Foundation` — PlaceType cell-level rate override
- `00_map/MAP_001 Map Foundation` — channel-level rate declaration
- `02_world_authoring/WA_001 Lex` — Lex axiom for tier-locked zones (anti-grief Option E)
- `02_world_authoring/WA_006 Mortality` — V2+ aging reads body_clock
- `06_pc_systems/PCS_001 brief` — §S8 xuyên không mechanic clock-split semantics

---

## Naming convention

`TDIL_<NNN>_<short_name>.md`. Sequence per-category. TDIL_001 is the foundation; future TDIL_NNN reserved for V1+ extensions (per-actor subjective rate / soul wandering / time travel V2+).

## How to add a feature

See root [`../_index.md`](../_index.md) § "How to add a new feature".

---

## Coordination note

TDIL_001 is the **second architecture-scale feature** (after AIT_001). Mirrors AIT_001 pattern:
- Opt-in per reality (modern social default = no dilation; tu tiên rich config)
- Cross-cutting boundary impact requiring multi-feature closure passes
- Reserves `actor_clocks` aggregate
- Per-channel + per-cell extensions on RealityManifest

User's deep-dive 2026-04-27 surfaced architectural revision affecting LOCKED features:
- **PROG_001 Q3f + §10 + §12**: day-boundary Generator → per-turn O(1) — closure-pass revision needed
- **RES_001 Q4 + §10**: 4 day-boundary Generators → per-turn O(1) with appropriate clock — closure-pass revision needed
- **AIT_001 §7.5**: per-day materialization replay → O(1) computation — closure-pass revision needed

These are **mechanical revisions** (no semantic change to user-facing behavior) but boundary-coordinated. Recommended sequence:
1. TDIL_001 concept-notes (this commit; non-boundary)
2. Q-deep-dive batched (mirror PROG/AIT pattern)
3. PROG/RES/AIT closure-pass revisions + TDIL_001 DRAFT (single combined boundary commit)

Subsequent priorities per existing roadmap:
- After TDIL_001 DRAFT: PCS_001 PC Substrate kickoff (consumes 6 foundations + IDF/FF/FAC/AIT/TDIL clocks)
- Future V1+: CULT_001 / REP_001 / V2 AGE feature (aging per body_clock)
