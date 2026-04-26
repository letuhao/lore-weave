# REP_001 Reputation Foundation — Reference Games Survey

> **Status:** DRAFT 2026-04-26 — companion to `00_CONCEPT_NOTES.md`. Surveys reputation system patterns across CRPGs, MMORPGs, strategy/sim games, and wuxia-genre titles to inform Q1-Q10 V1 scope locking. Augments user-provided references when supplied.
>
> **Method:** Cross-reference market patterns. Highlight insights for V1 scope. Identify defer-V1+/V2 patterns. Map to wuxia narrative requirements (primary V1 use case).

---

## §1 — Pattern taxonomy (4 categories)

| Pattern | Examples | Shape | V1 fit |
|---|---|---|---|
| **Discrete tier-based** | D&D 5e Faction Renown / WoW Reputation / Fallout: NV | Bounded score → engine-fixed tier label; gameplay gates per tier | ✅ STRONG V1 fit (engine-fixed simple) |
| **Continuous score (single axis)** | Bannerlord Renown / Skyrim hold bounty | Unbounded numeric score; displayed as raw number | ⚠ V1+ enrichment (loses tier mapping clarity) |
| **Multi-axis** | CK3 Prestige + Piety + Renown / Stellaris Diplomatic Stance | Separate axes for different rep kinds | ❌ V2+ deferred (RES_001 SocialKind enum reservation) |
| **Empire-empire** | Stellaris / Total War 3K / Civilization | Faction-vs-faction relations matrix | ❌ V2+ DIPL_001 deferred |

REP_001 V1 = discrete tier-based (D&D + WoW pattern).

---

## §2 — D&D 5e Faction Renown (PRIMARY REFERENCE — V1 anchor)

### Core mechanic

Each character has separate Renown score with each major faction. Renown gained from completing missions for that faction.

| Renown | Tier | Status | Privileges |
|---|---|---|---|
| 0 | Hated | Banished from faction | None |
| 0-2 | Disliked | (not member) | None |
| 3-9 | Neutral | (not member) | Basic interaction |
| 10-24 | Friendly | Member, low rank | Cheap room/board; access to faction safe houses |
| 25-49 | Honored | Trusted member | Reduced market prices; recommendation letters |
| 50+ | Revered | Legendary | Free magic items at shrines; high-tier missions |

### Key insights for REP_001 V1

- ✅ **Bounded score range (0-50+)** but unbounded upper end → REP_001 V1 chooses bounded i16 [-1000, +1000] (Q3-A) for full Hated→Exalted spectrum
- ✅ **Tier-based gameplay gates** — Honored+ unlocks special privileges; pattern works for Wuxia sect-quest gating (V1+ via WA_001 requires_reputation hook)
- ✅ **Separate score per faction** (PC has Lords Alliance Renown 25 + Harpers Renown 0 simultaneously) — confirms per-(actor, faction) sparse storage (Q2-A)
- ❌ **No negative renown V1** in D&D 5e (Hated is treated as 0 + faction status flag; not a separate negative score)
- ❌ **No decay** in D&D — Renown is permanent record (matches REP_001 Q7-A no decay V1)
- ❌ **No cascade** in D&D — completing Lords Alliance mission doesn't reduce Zhentarim renown automatically (matches REP_001 Q6-A no cascade V1)

### Wuxia adaptation

D&D 5e tier-based Renown → REP_001 V1 8-tier extended spectrum (Hated→Exalted) for wuxia narrative range:
- "Đại Thánh nhân" (saint of sect) ≈ Exalted (Revered+)
- "Outer disciple" ≈ Friendly (+101..+250)
- "Sect rival" ≈ Hostile (-500..-251)
- "Demonic sect kế thù" ≈ Hated (-1000..-501)

---

## §3 — World of Warcraft Reputation (8-tier extended)

### Core mechanic

Each character has Reputation score with dozens of factions. 15 tiers of 6000 each (-42000 to +42000), but 8 named tiers visible to player.

| Score range | Tier | Privileges |
|---|---|---|
| -42000..-6001 | Hated | Faction guards attack; cannot interact |
| -6000..-3001 | Hostile | Guards attack; cannot trade |
| -3000..-1 | Unfriendly | No trade; some quests blocked |
| 0..2999 | Neutral | Default; basic interaction |
| 3000..8999 | Friendly | Trade enabled; some quests open |
| 9000..20999 | Honored | Discounts; honored-only quests |
| 21000..41999 | Revered | More discounts; revered-only quests |
| 42000+ | Exalted | Tabard / mount / rare items |

### Key insights for REP_001 V1

- ✅ **8-tier spectrum (Hated/Hostile/Unfriendly/Neutral/Friendly/Honored/Revered/Exalted)** — REP_001 V1 adopts EXACT same 8 tiers (Q3-A)
- ✅ **Symmetric negative side** (Hated/Hostile/Unfriendly mirror Friendly/Honored/Revered+Exalted asymmetrically) — REP_001 V1 maps i16 [-1000, +1000] to 8 tiers (asymmetric for Exalted apex)
- ✅ **Bounded range (-42000..+42000)** — REP_001 V1 chooses smaller i16 [-1000, +1000] (storage minimal; same expressivity)
- ⚠ **No cascade** in WoW — but rival-faction grinding affects rep gain rate (e.g., Aldor↔Scryers mutual exclusion); REP_001 V1+ via Q6-A enrichment
- ❌ **No decay** — WoW rep is permanent (matches REP_001 Q7-A V1 no decay)
- ❌ **Daily quest rep cap** mechanic — anti-grinding; not relevant to LLM-MMO single-player narrative

### Tier mapping precise thresholds (REP_001 V1 proposed)

```
ReputationTier::Hated      → -1000..=-501  (asymmetric: 500 range = stronger negative)
ReputationTier::Hostile    → -500..=-251   (250 range)
ReputationTier::Unfriendly → -250..=-101   (150 range)
ReputationTier::Neutral    → -100..=+100   (200 range = wide center; default)
ReputationTier::Friendly   → +101..=+250   (150 range)
ReputationTier::Honored    → +251..=+500   (250 range)
ReputationTier::Revered    → +501..=+900   (400 range = harder to reach)
ReputationTier::Exalted    → +901..=+1000  (100 range = apex; rare)
```

Asymmetric thresholds match wuxia narrative (rare to reach Exalted; easy to dip to Hated; Neutral as wide default zone).

---

## §4 — Fallout: New Vegas Faction Reputation (7-tier dual axis)

### Core mechanic

Each major faction (NCR / Caesar's Legion / Mr. House / Yes Man / Boomers / etc.) has TWO axes:
- **Fame** (positive deeds): 0-100
- **Infamy** (negative deeds): 0-100

Tier computed from BOTH axes:

| Fame | Infamy | Tier |
|---|---|---|
| 0 | 0 | Mixed (newcomer) |
| Low | High | Vilified |
| Med | High | Hated |
| Med | Med | Mixed |
| Med | Low | Accepted |
| High | Low | Liked |
| High | Very Low | Idolized |

### Key insights for REP_001 V1

- ❌ **Dual-axis (Fame + Infamy)** rejected for REP_001 V1 — adds complexity; single signed score [-1000, +1000] captures equivalent semantic
- ✅ **Per-faction reputation** (NCR rep + Legion rep separate) — confirms per-(actor, faction) (Q2-A)
- ⚠ **Disguise mechanic** (Legion armor disguises NCR fame) — not relevant V1; V2+ stealth/disguise feature
- ❌ **No decay** — matches REP_001 Q7-A V1 no decay
- ✅ **Quest reward = rep change** — direct mechanic; REP_001 V2+ via 13_quests integration (REP-D12)

### Why single-axis wins V1

- LLM narrative emits "Lý Minh insults Đông Hải elder" → -100 rep with Đông Hải; clear single-axis delta
- Dual-axis Fame/Infamy creates LLM ambiguity (does "saving sect from demon" grant Fame +50 OR reduce Infamy by 50? → ambiguity rejected)
- V1 simplicity > narrative completeness; V1+ can split if needed (REP-D-N)

---

## §5 — Skyrim Bounty + Faction Quest Renown (per-hold)

### Core mechanic

**Bounty per hold (9 holds in Skyrim):** Each crime has gold value; bounty per hold accumulates; pay/jail/fight to clear.

**Faction quest progression:** Companions / Thieves Guild / Dark Brotherhood / College of Winterhold / Imperial Legion / Stormcloak — each has progression story line (not numeric rep; quest-driven).

### Key insights for REP_001 V1

- ✅ **Per-region (per-hold) reputation** — anti-pattern to global rep; REP_001 V1 = per-(actor, faction) where faction can model "Whiterun Hold" or "Eastmarch Guards" if author declares
- ❌ **No numeric rep with most factions** — quest-flag-based; REP_001 V1 = numeric scalar (more flexible)
- ⚠ **Bounty is integer (gold value)** — unbounded; not capped; matches RES_001 Currency::gold pattern (NOT REP_001)
- ✅ **Forgiveness mechanic** (pay bounty → reset to 0) — REP_001 V1 Forge:ResetReputation pattern (Q5-B)

### Wuxia adaptation

Skyrim bounty pattern → REP_001 V1+ "infamous deed" event sources (kill innocent → bounty rep with Đông Hải Đạo Cốc; pay restitution → admin SetReputation reset).

---

## §6 — Crusader Kings 3 (Prestige + Piety + Renown — multi-axis)

### Core mechanic

CK3 has THREE separate reputation axes per character:
- **Prestige** (martial + secular) — gained from war + tournaments + heir titles
- **Piety** (religious) — gained from pilgrimages + crusades + tithe
- **Renown** (dynasty fame) — accumulated via dynasty-level achievements; unlocks dynasty perks

Each axis has tier breakpoints (e.g., Lifestyle level 1 = 100 Prestige; level 2 = 1000; etc.).

### Key insights for REP_001 V1

- ❌ **Multi-axis rejected V1** — too wide; RES_001 SocialKind enum already reserves Prestige + Piety V2 (RES_001 §3.2)
- ✅ **Tier breakpoints per axis** — D&D-pattern; matches REP_001 V1 8-tier
- ⚠ **Decay via lifestyle drift** — not raw decay; lifestyle changes shift rep accrual rate; complex; defer V2+
- ❌ **Renown is dynasty-wide** (not per-character) — REP_001 V1 is per-(actor, faction); dynasty-rep is V2+ via FF_001 dynasty integration

### Multi-axis defer pattern

REP_001 V1 single-axis i16 score per (actor, faction). V2+ multi-axis activation:
- RES_001 SocialKind expansion: Reputation + Prestige + Piety + Influence
- REP_001 schema: `score: HashMap<SocialKind, i16>` (replaces single i16) — additive migration

---

## §7 — Mount & Blade: Bannerlord (Renown + Relations)

### Core mechanic

- **Renown** (per-character): Unbounded integer; gained from battles + tournaments + quests; unlocks clan tier (army size cap)
- **Relations** (per-character ↔ per-NPC): -100..+100 per NPC; bilateral

### Key insights for REP_001 V1

- ⚠ **Renown unbounded** — Bannerlord pattern; rejected for REP_001 V1 (bounded simpler)
- ✅ **Per-NPC relations -100..+100** — matches NPC_001 NpcOpinion pattern (NOT REP_001)
- ⚠ **Decay over time** (relations drift toward 0) — matches REP_001 Q7-A V1+ decay enrichment
- ✅ **Clan tier unlock** (Renown 1000 → Clan Tier 4 → bigger army) — REP_001 V1+ via WA_001 requires_reputation gating pattern

### Distinction note

Bannerlord Renown = global character fame (≈ RES_001 SocialCurrency::Reputation, NOT REP_001).
Bannerlord Relations = per-(character, NPC) bilateral (≈ NPC_001 NpcOpinion, NOT REP_001).
Bannerlord has NO direct REP_001 analog (faction reputation per-character per-faction).

---

## §8 — Sands of Salzaar / Path of Wuxia (sect reputation)

### Core mechanic (Sands of Salzaar)

- **Faction reputation** per sect (8 factions): -100..+100; tier-based
- **Sect membership grants base rep** with own sect (+50 starting) — Q4-C hybrid pattern
- **Rival-sect rep cascade** — kill rival sect leader → -rep with rival + +rep with allies (V1+ Q6-B cascade pattern)

### Core mechanic (Path of Wuxia)

- **Sect reputation per sect** — gained from missions, training, fighting rivals
- **Sect quests gated by reputation** (Honored+ unlocks advanced cultivation; Q3-A tier gating pattern for V1+ WA_001 hook)

### Key insights for REP_001 V1

- ✅ **Wuxia-genre confirmation: per-(actor, sect) reputation primary mechanic** — confirms REP_001 V1 scope
- ✅ **Cascade rep is wuxia-canon** (Q6-B is the natural design; V1+ enrichment) — REP-D2 cascade pattern matches
- ✅ **Sect-quest gating via reputation tier** — V1+ via WA_001 requires_reputation hook (REP-D8)
- ✅ **Initial rep from sect membership** — Q4-C hybrid pattern (declared override → membership-derived → 0)

### Wuxia narrative authenticity

Sands of Salzaar + Path of Wuxia validate REP_001 V1 design:
- 8-tier spectrum captures wuxia narrative range
- Per-(actor, sect) sparse storage matches in-game player experience (most factions Neutral default)
- Tier-based quest gating enables V1+ WA_001 hook (Q3-A confirmed)

---

## §9 — Stellaris (empire-empire diplomatic relations) — V2+ DIPL_001

### Core mechanic

- **Empire-empire opinion** matrix: -200..+200 per pair
- **Sources**: rival ideology + border friction + trade deals + alliances + wars
- **Decay** toward 0 over time

### Key insights for REP_001 V1

- ❌ **Empire-empire deferred V2+ DIPL_001** — REP_001 is per-(actor, faction); inter-faction is DIPL_001 territory
- ❌ **Decay** — Q7-A V1+ via REP-D3 (Stellaris pattern is V1+ enrichment)

### Why this is DIPL_001 not REP_001

REP_001 = "How does Đông Hải feel about Lý Minh personally?"
DIPL_001 = "How does Đông Hải feel about Tây Sơn collectively?"

Different keys (actor vs faction); different aggregates. REP_001 V1 doesn't ship faction-faction; FAC_001 default_relations is the V1 static stand-in.

---

## §10 — Total War 3K / Imperator: Rome (faction-vs-faction relations) — V2+ DIPL_001

Similar to Stellaris pattern. DIPL_001 territory; REP_001 V1 doesn't address.

---

## §11 — Pillars of Eternity / Tyranny / Pathfinder: WotR (faction reputation)

### Core mechanic (Pillars of Eternity)

Per-faction reputation with 4-tier values (Hostile/Mixed/Cordial/Friendly) + numeric scores + flag-based historical events ("you saved their leader in Act 2").

### Core mechanic (Tyranny)

Dual-axis per-faction: **Loyalty** + **Fear**. Player can choose to pursue either axis with each major faction.

### Key insights for REP_001 V1

- ✅ **Faction reputation per-(actor, faction)** — confirms V1 scope
- ⚠ **Tyranny dual-axis (Loyalty + Fear)** — interesting but REJECTED V1 (single-axis simpler; V1+ via SocialKind enum if needed)
- ⚠ **Flag-based historical events** — REP_001 V1+ via separate event log query (REP-D15 audit trail)

---

## §12 — Mass Effect / Dragon Age (Paragon/Renegade) — global character axis

### Core mechanic

Mass Effect: Paragon (good) + Renegade (bad) — DUAL-AXIS GLOBAL alignment, NOT per-faction.

Dragon Age: Approval per companion (per-NPC, NOT per-faction).

### Key insights for REP_001 V1

- ❌ **Paragon/Renegade is global character alignment, not faction-specific** — closer to RES_001 SocialCurrency::Reputation pattern (NOT REP_001)
- ❌ **Dragon Age Approval is per-companion, not per-faction** — closer to NPC_001 NpcOpinion (NOT REP_001)

These reinforce 3-layer separation discipline:
1. NPC_001 NpcOpinion = Dragon Age Approval pattern
2. RES_001 SocialCurrency::Reputation = Mass Effect Paragon/Renegade pattern (single-axis adaptation)
3. REP_001 actor_faction_reputation = D&D 5e Faction Renown pattern

---

## §13 — Wuxia novel canon (non-game references)

### Source pattern

Wuxia novels (Jin Yong's "Demi-Gods and Semi-Devils" / "The Heaven Sword and Dragon Saber" / Gu Long's works) consistently use:

- **Per-sect reputation** ("danh tiếng trong môn phái") — central narrative mechanic
- **Wulin reputation** (江湖名声) — global wuxia-world fame ≈ RES_001 SocialCurrency::Reputation
- **Sect alliance rep** ("Wulin Meng" alliance member factions accumulate joint rep) — V1+ DIPL_001 + REP_001

### Insights for REP_001 V1

- ✅ **Per-sect reputation as primary wuxia mechanic** — REP_001 V1 lock
- ✅ **Tier-based "thanh dự" levels** (Đại Thánh nhân / Tôn sư / Trưởng lão / Đệ tử / Người lạ / Kẻ thù / Nghịch tặc / Đại nghịch) ≈ REP_001 8-tier (Exalted/Revered/Honored/Friendly/Neutral/Unfriendly/Hostile/Hated)
- ✅ **Cascade rep via sect alliance** — V1+ via REP-D2 cascade enrichment
- ✅ **Sect-quest gating** — V1+ via WA_001 requires_reputation (REP-D8)

### Wuxia tier mapping (proposed Vietnamese display)

| Score range | English tier | Vietnamese tier (Wuxia) |
|---|---|---|
| -1000..=-501 | Hated | Đại nghịch (mortal enemy) |
| -500..=-251 | Hostile | Nghịch tặc (rebel/enemy) |
| -250..=-101 | Unfriendly | Kẻ thù (foe) |
| -100..=+100 | Neutral | Người lạ (stranger) |
| +101..=+250 | Friendly | Đệ tử (disciple) |
| +251..=+500 | Honored | Trưởng lão (elder) |
| +501..=+900 | Revered | Tôn sư (master) |
| +901..=+1000 | Exalted | Đại Thánh nhân (saint) |

Display tier names per faction via I18nBundle (V1+ enrichment) — engine-fixed thresholds; author-customizable display labels per faction at V1+.

---

## §14 — Comparison table (10 dimensions)

| Game | Per-faction? | Range | Tier? | Decay? | Cascade? | V1 fit |
|---|---|---|---|---|---|---|
| **D&D 5e** | ✓ | 0-50+ | 6-tier | ✗ | ✗ | ★★★★★ V1 anchor |
| **WoW** | ✓ | -42000..+42000 | 8-tier | ✗ | ⚠ (Aldor↔Scryers) | ★★★★★ tier spectrum |
| **Fallout: NV** | ✓ | 0-100 dual | 7-tier | ✗ | ✗ | ★★★ dual-axis rejected |
| **Skyrim** | ✓ (per-hold) | gold | flag | ✗ | ✗ | ★★ flag-based |
| **CK3** | ✗ (multi-axis) | unbounded | tier | ⚠ | ✗ | ★★ V2+ multi-axis |
| **Bannerlord** | ✗ (Renown global) | unbounded | tier | ✓ | ✗ | ★★ Renown ≠ REP_001 |
| **Sands of Salzaar** | ✓ | -100..+100 | 5-tier | ✗ | ✓ | ★★★★★ wuxia anchor |
| **Path of Wuxia** | ✓ | tier | tier | ✗ | ⚠ | ★★★★★ wuxia anchor |
| **Stellaris** | ✗ (empire-empire) | -200..+200 | tier | ✓ | ✗ | ★ V2+ DIPL_001 |
| **Pillars of Eternity** | ✓ | 4-tier + numeric | 4-tier | ✗ | ✗ | ★★★ |
| **Tyranny** | ✓ (Loyalty+Fear dual) | -3..+3 dual | tier | ✗ | ✗ | ★★ dual-axis rejected |
| **Mass Effect** | ✗ (Paragon/Renegade global) | bar | bar | ✗ | ✗ | ★ ≠ REP_001 |
| **Dragon Age** | ✗ (per-companion) | -100..+100 | tier | ✗ | ✗ | ★ ≠ REP_001 (NPC_001 instead) |
| **Wuxia novels** | ✓ | tier | 8-tier | ⚠ | ✓ | ★★★★★ V1 anchor |

REP_001 V1 = D&D 5e + WoW + Sands of Salzaar + Wuxia novels hybrid. 8-tier spectrum [-1000, +1000] sparse per-(actor, faction) bounded.

---

## §15 — Recommendations summary (feeds Q1-Q10 §5 of CONCEPT_NOTES)

| Question | Recommendation | Reference anchor |
|---|---|---|
| Q1 Aggregate vs projection | (A) Materialized aggregate | FAC_001 Q1 LOCKED + storage cost discipline |
| Q2 Sparse vs dense | (A) Sparse | WoW per-faction; AI Tier scaling |
| Q3 Range + tier | (A) Bounded i16 [-1000, +1000] + 8-tier engine-fixed | WoW + D&D 5e + Wuxia novels hybrid |
| Q4 Default initial | (C) Hybrid (declared → membership-derived → 0) | Sands of Salzaar; Path of Wuxia |
| Q5 V1 runtime events | (B) Forge admin V1 + canonical seed V1; runtime gameplay V1+ | FAC_001 V1 pattern + narrative authoring needs |
| Q6 Cascade rep | (A) No cascade V1; V1+ enrichment | Cascade design wide; defer |
| Q7 Decay | (A) No decay V1; V1+ enrichment | D&D + WoW pattern; defer |
| Q8 Cross-reality | (A) V1 strict single-reality; V2+ Heresy | IDF + FF + FAC discipline |
| Q9 Synthetic actor | (A) Forbidden V1 | Universal V1 substrate discipline |
| Q10 RES_001 reconciliation | (A) Coexist (3-layer separation) | RES_001 Sum scalar + NPC_001 opinion + REP_001 per-(actor, faction) |

All 10 recommendations align with established discipline + market patterns. Q-deep-dive may revise.

---

## §16 — Status

- **Created:** 2026-04-26 by main session (commit this turn)
- **Phase:** REFERENCE — companion to `00_CONCEPT_NOTES.md`
- **Coverage:** 14 game references + Wuxia novel canon + 10-dimension comparison table
- **Augmentation slot:** awaits user-provided references if any
- **Next action:** Feed §15 recommendations into Q-deep-dive discussion → user "A" approval (or revisions) → §7 V1 scope LOCKED in CONCEPT_NOTES → DRAFT promotion
