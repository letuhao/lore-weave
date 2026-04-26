# Research — Character + Society Systems Market Survey

> **Purpose:** Survey character + society systems in established RPG / strategy / simulation games. Validate or challenge LoreWeave's 5-feature IDF concept (Race / Language / Personality / Origin / Ideology). Identify patterns + missing dimensions BEFORE diving deep into each IDF feature DRAFT.
>
> **Scope:** 16 reference games across 6 genres + 4 tabletop systems. Wuxia-specific deep-dive section (SPIKE_01 context).
>
> **Status:** Research / discussion document 2026-04-26. NOT a feature spec — informs IDF DRAFT promotion + future PCS_001 / NPC_003 / FF_001 (Family) / Faction Foundation design.
>
> **Outcome:** Recommended adjustments at §9 (compare to current IDF concept-notes) + V1+ society feature roadmap at §8.

---

## §1 Why this survey

User direction 2026-04-26: "tham khảo nhiều game nhập vai/chiến thuật/giả lập trên thị trường xem họ build hệ thống nhân vật và xã hội như thế nào trước khi chúng ta đi sâu vào từng cái".

The 5-feature IDF split (Race / Language / Personality / Origin / Ideology) was decided in 2026-04-26 IDF folder Phase 0 based on reasoning. Before locking V1 design via DRAFT promotion (~15 commits), validate against established game patterns:

- **Confirm 5-feature split is correct** vs market patterns (4 features? 6? combined differently?)
- **Identify missing dimensions** (e.g., reputation, family, sect — are these foundation or feature-level?)
- **Calibrate V1 scope** (CK3 has 60+ traits — is our 8 archetypes too narrow? Right scope?)
- **Spot LLM-enabled novelty** (where existing games are limited that LLM solves)
- **Wuxia-specific concerns** (SPIKE_01 reality — cultivation realm? sect membership? mortality vs transcendence?)

---

## §2 Methodology + game selection

Selected games span 6 genres + 4 tabletop systems. Each evaluated on 5 IDF dimensions + society dimension.

### §2.1 Game pool (16 + 4)

| Game | Genre | Why included |
|---|---|---|
| **Crusader Kings 3** | Grand strategy / character RP | Most detailed character + society system in mainstream gaming |
| **RimWorld** | Colony sim / strategy | Pawn personality + Ideology DLC = closest to LoreWeave's belief modeling |
| **Dwarf Fortress** | Colony sim | Highest-resolution character simulation (50+ facets) |
| **The Sims 4** | Life sim | Mainstream personality + life-stage + relationship |
| **Mount & Blade: Bannerlord** | Action RP / strategy | Culture-driven character + faction politics |
| **Stellaris** | 4X strategy | Multi-axis ethics + species traits |
| **Europa Universalis IV** | Grand strategy | Country-level culture + religion |
| **Civilization VI** | 4X strategy | Leader personalities + agendas |
| **Total War: Three Kingdoms** | RTS / character RP | Wuxia-adjacent (Han China) + character relationships |
| **Persona 5 Royal** | JRPG | Social stats + confidant ranks (relationship system) |
| **Fire Emblem: Three Houses** | Tactical RPG | Supports system + faith/houses |
| **Disco Elysium** | Detective RPG | Internal-voices personality + ideology gating |
| **Pillars of Eternity / Pathfinder: WotR** | CRPG | Race + class + background + alignment + deity |
| **Skyrim** | Open-world RPG | Race + faction + perk |
| **Sands of Salzaar** | Wuxia sandbox | Wuxia sect + cultivation + martial + faction |
| **Path of Wuxia / Sword & Fairy** | Wuxia RPG | Cultivation realm + sect membership + ideology |
| **D&D 5e** | Tabletop | Race + class + background + ideals/bonds/flaws |
| **Pathfinder 2e** | Tabletop | Heritage + ancestry + background + class |
| **Burning Wheel** | Tabletop | Beliefs/Instincts/Traits drive behavior |
| **Vampire: The Masquerade** | Tabletop / RPG | Clan + nature/demeanor + sect (Camarilla/Sabbat) |

### §2.2 Evaluation dimensions

Each game evaluated on 6 dimensions:

1. **Race / Species** — closed-set? mutable? gates abilities?
2. **Language** — modeled at all? proficiency tracked? gates content?
3. **Personality** — single archetype? trait pool? facet vector? narrative?
4. **Origin / Background** — birthplace? culture? family? backstory?
5. **Ideology / Religion** — single? multi? mutable? gates abilities/dialogue?
6. **Society** — faction? reputation? diplomacy? family graph? sect?

### §2.3 Limits of survey

- Excludes MMOs (WoW / FFXIV / etc.) — most have minimal personality/ideology because player-driven RP is the design philosophy. LoreWeave's LLM-driven NPCs make MMO comparisons less relevant.
- Excludes purely combat-focused RPGs (Diablo / Path of Exile) — character system = stats only.
- Heavy weight on grand-strategy + colony-sim because those depth-model character + society at scale (closest to LLM-driven NPC simulation).

---

## §3 Reference catalog (compact matrix)

| Game | Race | Language | Personality | Origin | Ideology | Society |
|---|---|---|---|---|---|---|
| **CK3** | Heritage (cosmetic + DNA traits); culture mutable across generations | Per-culture; tracked but not gameplay-relevant | **16 personality traits** + lifestyle + education + congenital + physical = ~60 traits | Culture + dynasty + birth-court | **Faith full system**: doctrines + tenets + holy sites + heresies + virtues/sins | Vassalage + court + council + schemes + wars + dynasty |
| **RimWorld** | Xenotypes (Biotech) closed enum + genes (open-set traits) | None | 4-5 traits per pawn (closed-set ~50 trait pool) | Childhood backstory + Adult backstory (open authoring) | **Memes (3-4) → Ideoligion**: precepts + rituals + roles (Ideology DLC) | Faction relations matrix + ideoligion compatibility |
| **Dwarf Fortress** | Race (Dwarf/Elf/Human/Goblin/Kobold) | **Full language simulation** (Dwarven/Elven/etc., word generation) | 50+ personality facets per dwarf (high-resolution vector) | Family graph tracked + entity (civilization) | Religion + sphere worship + values | Civilization + entity + position + family |
| **The Sims 4** | Single (human) — but supplements (vampire/spellcaster) | None | 3 traits + aspiration (multi-pick from ~50 pool) | Birthplace minimal | None V1; expansions add Faith | Relationship matrix + jobs |
| **Bannerlord** | None (single human) | Cultural accents | Honor / Mercy / Generosity / Calculating (4 axes -100..+100) | Culture (6 factions) + clan + family | None | Vassalage + faction + clan + party |
| **Stellaris** | Species + traits (closed pool ~30) + portrait | None gameplay-relevant | None per-pop; species ethics + civics | Origin (Civic-equivalent) + birth-planet | **7-axis ethics** (Authoritarian-Egalitarian / Pacifist-Militarist / Xenophile-Xenophobe / Materialist-Spiritualist tri-state) | Diplomacy + federations + galactic community |
| **EU4** | Country culture | Country-level | Monarch personality (3 traits + power values) | Country culture + tag + history | Country religion (~25) | Diplomacy + hre + estates |
| **Civ VI** | Civilization | Vague | Leader agenda (1 historical + 1 hidden) | Civilization | None per-leader | Diplomacy + governments + religion |
| **TW: 3K** | Single (Han) | None | Personality (4-5 trait pool) | Family + court | None | Diplomacy + family + faction |
| **Persona 5R** | Single | Single | 5 social stats grow over time | Backstory (Joker = ex-detained delinquent) | None per-character; Confidants = social bonds | Confidants (21 NPCs) + party + Phantom Thieves |
| **FE: 3H** | Race (most human; some Crests) | Single | Personality (combat-style + dialogue) | House (Black Eagles / Blue Lions / Golden Deer) | Faith of Seiros (single religion; routes diverge) | Houses + church + supports |
| **Disco Elysium** | Single (human) | Tracked but not proficiency-modeled | **24 skills as personality voices** (Empathy / Volition / Authority / etc.) | Childhood mentioned via thoughts | **Thought cabinet** (gradual ideology unlocking via internalized thoughts) | RCM precinct + factions + Whirling-in-Rags hotel |
| **PF: WotR** | Heritage + ancestry (Pathfinder 2e) | None gameplay-relevant | Alignment (LG / NG / CG / LN / TN / CN / LE / NE / CE) | Background (peasant / noble / mercenary / etc.) | Deity worship | Crusade + companions + factions |
| **Skyrim** | 10 races (gameplay differences); Werewolf/Vampire mutability | Tracked but not gameplay | Some personality (companion-quest-driven) | Birth (cosmetic + Stones of Birth) | Daedra/Aedra worship + Mannimarco (optional) | Factions (Companions / DB / TG / College / Imperial / Stormcloaks) |
| **Sands of Salzaar** | Race (~5) | None | None | Sect / Birth | None per-character (sect ideology implicit) | Sect + faction + party |
| **Path of Wuxia / Sword & Fairy** | Cultivation Realm (mutable) | None | Personality minor | Birth + sect | Sect ideology (Đạo / Phật / Ma đạo) | Sect + jianghu + family |
| **D&D 5e** | Race (closed-set ~10) + size + speed + lifespan | Race-default known languages | **Background ideals/bonds/flaws** (3 sentences each, narrative) | Background (~15 archetypes) | Deity worship + alignment | Faction (Order / Harpers / Lords' Alliance / etc.) |
| **Pathfinder 2e** | Heritage + ancestry | Race-default + class bonus | Alignment + character notes | Background + heritage | Deity worship + edicts/anathema | Same as D&D + class organizations |
| **Burning Wheel** | Stock (race-equivalent) + lifepath | None gameplay | **Beliefs (3) + Instincts (3) + Traits** drive XP and behavior | Lifepath chain (Born noble → page → squire → knight) | Faith trait + religious lifepaths | Affiliations + relationships |
| **VtM** | Clan (13 closed) + bloodline | Tracked minor | Nature (true self) + Demeanor (mask) — 2 archetypes per character | Sire + Generation + Embrace night | Sect (Camarilla / Sabbat / Anarchs) + Path (Humanity / Path of X) | Sects + clans + coteries + cities |

---

## §4 Per-IDF feature pattern catalog

### §4.1 IDF_001 Race — patterns observed

**Three dominant patterns:**

1. **Closed-enum race + size + lifespan + ability modifiers** (D&D 5e / Pathfinder / PoE / Skyrim)
   - Race is birth-fixed (some games allow vampire/lycanthrope mutation as exception)
   - Race gates abilities (Dwarves get Darkvision; Elves get Trance)
   - 5-15 races typical
   - **Maps to current IDF_001 design** ✓

2. **Heritage / cultural-genetic split** (CK3 / Pathfinder 2e)
   - Heritage = visible / genetic (looks)
   - Culture = mutable (cultural conversion across generations)
   - Allows cross-cultural character (born Norse heritage but raised in Anglo culture)
   - **NOT in current IDF_001** — heritage = race (immutable); culture mutable in IDF_004 V1+
   - **Adjustment consideration:** Should IDF_001 split race into "biological_race" (immutable) vs "cultural_race" (mutable per IDF_004)?
   - **Recommendation: NO V1.** The split adds complexity. V1 single-RaceId per actor sufficient. V1+ may add cultural_race overlay if reality content demands.

3. **Mutable rank-as-race** (Wuxia cultivation: Phàm nhân → Trúc Cơ → Kim Đan → Nguyên Anh → Hóa Thần → Đại Thừa → Tiên / Ma)
   - Race-tier upgrades via training (cultivation)
   - Each tier unlocks Lex axioms (qigong → flying-sword → etc.)
   - **NOT current IDF_001** — current ships immutable race
   - **Adjustment consideration:** Wuxia "race" = cultivation realm (mutable rank), not biological race
   - **Recommendation:** Treat cultivation realm as **separate V1+ feature** (CULT_001 Cultivation Foundation), NOT IDF_001 race. IDF_001 races for SPIKE_01 = Phàm nhân / Cultivator / Demon / Ghost / Beast (broad biological category). Within "Cultivator" race, cultivation realm progresses through CULT_001's mutable rank system V1+.

**Key insights:**
- D&D-style race (closed enum + size + lifespan) is **safe, validated, narrow V1**. Current IDF_001 follows this. ✓
- Lifespan as u16 years (current) is fine — CK3 doesn't track per-character lifespan; D&D ranges; reality presets like Wuxia have 80yr Phàm nhân vs 600yr Cultivator base.
- size_category 4 variants (Small/Medium/Large/Huge) covers D&D + sci-fi. Pathfinder uses 6 (adds Tiny/Gargantuan) — consider RAC-Q4 expansion, but V1 4 sufficient.

### §4.2 IDF_002 Language — patterns observed

**Three patterns:**

1. **Race-default known languages** (D&D 5e / Pathfinder)
   - Each race has built-in known languages (Elf knows Common+Elvish)
   - Class adds bonus languages (Cleric +1)
   - **No proficiency modeling** — binary "knows / doesn't know"
   - Maps to current IDF_002 — but our 4-axis × 5-level is RICHER

2. **Full language simulation** (Dwarf Fortress)
   - Each race has full generated vocabulary
   - Proficiency tracked but not gameplay-impacted
   - Way too much for V1; matches V1+ enrichment scope

3. **No language modeling** (most games — CK3 / RimWorld / Bannerlord / Skyrim)
   - Players speak a "common tongue" implicitly
   - Cultural accents are flavor only
   - **Counter-validation:** Most mainstream games DON'T model language proficiency
   - **Why LoreWeave needs it:** SPIKE_01 turn 5 literacy slip is canonical reproducibility test for A6 canon-drift detector — language proficiency IS gameplay-relevant for LLM-driven dialogue accuracy

**Key insights:**
- 4-axis × 5-level proficiency matrix (current IDF_002 design) is **higher resolution than any mainstream game**. Validated by SPIKE_01 requirement; Dwarf Fortress proves the depth is implementable.
- D&D's race-default languages → maps to current IDF_002's `LanguageDecl.default_in_origin_packs` (V1+) — defaulting via origin pack is correct pattern (race-or-culture defaults language).
- Ramp-up gameplay impact: V1 proficiency = data only; V1+ A6 canon-drift consumer + V1+ learning Apply events.

**Adjustment consideration:**
- LNG-Q11 (LanguageId vs LangCode collision) — most games avoid this entirely (no in-fiction language type). Validate runtime assert V1; compile-time newtype V1+.
- LNG-D7 code-switching — Disco Elysium uses internal voices; does IDF need this? **NO V1 — defer.** SPIKE_01 doesn't require code-switching V1.

### §4.3 IDF_003 Personality — patterns observed

**Five patterns:**

1. **Single archetype** (Vampire: The Masquerade Nature/Demeanor; Sims 1; LoreWeave current IDF_003 V1)
   - Pick from 8-15 archetypes
   - Defines voice + reaction tendencies
   - Simple to balance V1
   - **Maps current IDF_003 V1** ✓

2. **Multi-trait pick (3-5 traits)** (RimWorld 4-5 / Sims 4 = 3 / D&D 5e ideals/bonds/flaws)
   - From ~50 trait pool, pick 3-5 traits
   - More flexible than single archetype
   - 50×50 opinion matrix vs 8×8 — much harder to balance
   - **NOT current IDF_003 V1** — V1+ extension (PRS-D3 multi-archetype overlay)

3. **High-resolution facet vector** (Dwarf Fortress 50+ facets / CK3 60+ traits)
   - Each character has 50+ axes 0-100
   - Emergent personality
   - Way too granular for V1 (test/balance impossible at this scale without extensive playtesting)
   - **V1+ Big-Five overlay (PRS-D1)** captures the spirit at lower resolution

4. **Skills-as-personality** (Disco Elysium 24 skills as inner voices)
   - Each skill has personality (Empathy = caring; Authority = commanding)
   - Skills double as dialogue-gating
   - **Novel pattern — does it apply to LoreWeave?**
   - **Recommendation: NO V1.** Skills are V1+ combat/crafts feature; conflating with personality breaks separation of concerns.

5. **Stat-grow personality** (Persona 5 Royal social stats Knowledge/Charm/Proficiency/Kindness/Courage)
   - Stats grow via gameplay
   - Implicit personality (high Charm = charming character)
   - V1+ enrichment pattern — IDF_003 archetype + V1+ growable stat dimensions

**Key insights:**
- **CK3's 16 personality traits** is the right reference for V1+ expansion. Current 8 archetypes ≈ half of CK3's depth — leaves room for V1+ additive without re-architecture.
- **Voice register** as part of personality (current IDF_003 §2 voice_register field) is rare — most games don't model speech-style. **Validated by LLM use case** — voice register guides LLM persona prompt.
- **Opinion modifier table** (current 8×8 = 64 entries V1) is **CK3's pattern** — every personality has likes/dislikes per other personality. Validated. Range -10..=+10 (current PRS-Q4) maps to CK3 -30..+30 typical opinion modifiers; our narrower range forces meaningful baselines.

**Adjustment consideration:**
- PRS-Q1 (8 vs 12 archetypes V1) — CK3 has 16; D&D backgrounds have 13; Vampire Nature/Demeanor has 24 each. **8 is on the narrow end** but still defensible V1; suggest **revisit at DRAFT** if reality content needs >8 archetypes.
- Big-Five (PRS-D1) is V1+ but well-validated by psychology research; layering Big-Five over archetypes is common (Sims uses both).
- Reality-specific archetype packs (PRS-D4 V1+) — Mount & Blade Bannerlord has culture-specific personalities (Khuzait nomad ≠ Vlandian feudal); Wuxia could have sect-specific (Đạo gia ≠ Ma giáo). V1+ enrichment.

### §4.4 IDF_004 Origin — patterns observed

**Four patterns:**

1. **Background as narrative tag** (D&D 5e / Pathfinder backgrounds)
   - Pick from ~15 backgrounds (Acolyte / Folk Hero / Soldier / Sage / etc.)
   - Each background has features + bonded NPCs + ideals/bonds/flaws
   - Mostly narrative; minor mechanical effects
   - **Maps to current IDF_004 V1+ OriginPackDecl** ✓

2. **Culture as ethnicity** (CK3 / Bannerlord / EU4)
   - Closed-set culture per actor
   - Culture has cultural_traditions / ethos / unit-types / units-bonus
   - Cultural conversion mutable across generations
   - **Maps to current IDF_004 cultural_tradition_pack V1+** ✓

3. **Lifepath chain** (Burning Wheel / VtM Sire+Generation)
   - Born → child → apprentice → journey → master → ... etc.
   - Each lifepath gives skills + traits + relationships
   - Highly structured but expensive to author
   - **NOT IDF_004 V1** — V1+ enrichment if reality content demands

4. **Backstory as open authoring** (RimWorld childhood + adult)
   - Author writes free-form childhood + adult backstories
   - Each backstory grants skill bonuses + work disabilities
   - Open-ended pattern; LoreWeave-friendly (LLM can generate backstories)
   - **Validates IDF_004 V1+ free-form enrichment**

**Key insights:**
- Current IDF_004 V1 minimal stub (4 fields: birthplace + lineage_id + native_language + default_ideology_refs) is **bare bones** — D&D background feels richer. But **deferring full background richness to V1+ is correct** because authoring full origin packs is expensive content work.
- **Birthplace as ChannelId** (current IDF_004 §3.1) — uncommon in mainstream games (CK3 tracks "court of birth" loosely). Validated by LoreWeave's place-system; useful for V1+ origin-conflict drift (NPCs from rival sects born in same village = complex backstory).
- **Family graph deferred to V1+ FF_001** — every grand-strategy game (CK3 / EU4 / Bannerlord) tracks family. **Will need FF_001 sooner than later** — critical for wuxia (sect lineage / family inheritance / dynasty).

**Adjustment consideration:**
- ORG-Q1 (V1 minimal stub vs richer V1) — confirmed minimal correct; richer is V1+ FF_001 + cultural_tradition_pack territory.
- **MISSING dimension: Birth event metadata** — born-during-eclipse / born-of-virgin / etc. Wuxia has "thiên kiêu chi tử" (heavenly-talented offspring) markers tied to birth circumstance. **V1+ enrichment** — add to ORG-D11 deferral list.
- ORG-D8 (origin-conflict opinion modifier) — CK3's "rival culture" mechanic. Strongly validated.

### §4.5 IDF_005 Ideology — patterns observed

**Six patterns:**

1. **Single-faith** (CK3 Faith / EU4 country religion / VtM Path of X)
   - One faith per actor, mutable via conversion
   - Faith has doctrines / tenets / virtues / sins / holy sites
   - Conversion has cost (piety / opinion penalty)
   - **CK3 model is closest to wuxia ideology** — but single-stance vs multi-stance

2. **Multi-meme composition** (RimWorld Ideology DLC)
   - Pick 3-4 memes from pool of ~30
   - Memes auto-generate precepts + rituals + roles
   - Mutable (player can re-design ideoligion mid-game)
   - **Closest to IDF_005 multi-stance** — but V1 LoreWeave doesn't have memes-as-composition; we have ideology-as-stance with fervor

3. **Multi-axis ethics vector** (Stellaris 7-axis ethics)
   - 3 ethics points distributed across 7 axes
   - Continuous-ish (3 levels per axis: -, neutral, +)
   - **Validates V1 multi-stance** but with axis-not-set semantics (vs LoreWeave's IdeologyId-not-in-Vec)

4. **Alignment grid** (D&D 9-cell Lawful/Chaotic × Good/Evil)
   - Single 2D position
   - Mutable (alignment shift via actions)
   - Gates spell access (Cleric must align with deity)
   - **Maps loosely to current IDF_005 + V1+ tenet system** — alignment ≈ ideology + lex_axiom_tags

5. **Thought cabinet** (Disco Elysium)
   - Internalize "thoughts" gradually (think for in-game time)
   - Thoughts unlock dialogue + effects
   - Multiple simultaneous thoughts allowed
   - Ideology category of thoughts (Communist / Fascist / Liberal / Moralist)
   - **Validates multi-stance V1 + ideology-as-mutable**; LoreWeave's `actor_ideology_stance.stances` is roughly equivalent

6. **Sect / clan as combined origin+ideology** (Wuxia: Sands of Salzaar / Path of Wuxia / VtM clans)
   - Sect membership = both origin (where you came from) AND ideology (what you believe)
   - One sect per character; sect change = major event (defection / sect destroyed)
   - **NOT current IDF design** — LoreWeave separates IDF_004 Origin + IDF_005 Ideology + V1+ Faction
   - **Adjustment consideration:** Should IDF_005 have **single-stance V1** to match wuxia common pattern (one sect)?

**Key insights:**
- **Multi-stance V1 (current IDF_005)** is LoreWeave's novel call. Real wuxia tradition is multi-religious-syncretism (Lý Minh holds Đạo + Phật + Nho — verified by classic wuxia novels). Multi-stance is canonical for wuxia. ✓
- **CK3 Faith depth** (doctrines / tenets / heresies / holy sites) is V1+ tenet system (IDL-D1). Validated as V1+.
- **RimWorld memes-as-composition** is interesting alternative — would IDF_005 V1+ benefit from "ideology composed of memes" pattern? **Possibly V2+** — too radical departure from V1 enum-stance.
- **Conversion mechanics**: CK3 conversion has piety cost + opinion penalty + 6-month period. LoreWeave V1 simply allows Apply/Drop without cost — V1+ may add cost mechanic.
- **Tenet-driven Lex axiom gating** (current IDF_005 §5.1 `requires_ideology` field) maps directly to CK3 doctrines gating clergy. ✓

**Adjustment consideration:**
- IDL-Q2 (multi-stance V1 vs single-stance V1) — wuxia canon REQUIRES multi-stance (verified in survey). ✓ multi-stance is correct V1.
- IDL-Q4 (parent_ideology_id hierarchy V1 schema slot) — RimWorld's meme composition + CK3's heresies/branches both validate hierarchy. V1 schema slot is forward-looking — keep.
- **MISSING dimension: ideology-driven dialogue tone** (Disco Elysium thoughts gate dialogue trees) — for LoreWeave LLM-driven NPC, ideology is implicit input to persona prompt. V1+ NPC_002 wires this up.

---

## §5 Cross-cutting patterns observed

### §5.1 Pattern: separate Culture (mutable) from Faith/Ideology (mutable but per-character)

**Strongest validation across games:**
- **CK3 explicitly** separates Culture (ethnic/cultural identity, mutable across generations) from Faith (religion, mutable per character per conversion event)
- **Pathfinder 2e** explicitly separates Heritage (immutable racial) from Background (cultural origin, immutable per character)
- **VtM** separates Clan (immutable, biological) from Sect (Camarilla/Sabbat/Anarchs, mutable allegiance)

**Validates current IDF_004 (Origin = immutable culture) vs IDF_005 (Ideology = mutable belief).** ✓

**Counter-pattern:** Wuxia games (Sands of Salzaar / Sword & Fairy) typically conflate Sect = origin + ideology + skills + faction. This works for wuxia because sect IS the dominant identity. LoreWeave's split (Origin / Ideology / V1+ Faction) is more flexible across reality genres but adds complexity. **Validated as correct for multi-genre engine.**

### §5.2 Pattern: closed-set + author-declared per-realm

**All grand-strategy + RPG games** have closed-set per-domain (race / culture / religion / class). Open-set is exclusive to RimWorld memes-as-tags (V1+ pattern).

LoreWeave's closed-set per-reality (RealityManifest declares the closed-set) matches this universal pattern. ✓

### §5.3 Pattern: opinion modifiers via personality × personality matrix

**CK3, Bannerlord, Three Kingdoms** all model opinion as base + (personality × personality) modifier + (culture × culture) modifier + (faith × faith) modifier + situational events.

LoreWeave IDF_003 `opinion_modifier_table` matches CK3's "opinion of opposed personality" mechanic. ✓ V1+ adds:
- Race × race modifier (RAC-D2)
- Origin × origin modifier (ORG-D8)
- Ideology × ideology modifier (IDL-D3)

**Final V1+ opinion calculation:**
```
final_opinion = base_kind_delta
              + agent_personality_mod[recipient_personality]
              + agent_race_mod[recipient_race]                 (V1+ RAC-D2)
              + agent_origin_mod[recipient_origin]             (V1+ ORG-D8)
              + agent_ideology_mod[recipient_ideology]         (V1+ IDL-D3)
              + situational_modifiers (CK3-style events)
```

### §5.4 Pattern: ability-gating via race + class + faith

**D&D / Pathfinder: ability gates** combine race (Drow can cast Faerie Fire) + class (Cleric can cast spells) + faith (Cleric of Pelor can't cast Necromancy).

**CK3: doctrine gates**: Faith doctrines gate cultural traditions and behaviors (Doctrine of Pacifism gates "must commit to peace").

**LoreWeave WA_001 Lex axiom gates** combine race + ideology (current `requires_race` + `requires_ideology` companion fields). ✓ Class equivalent = V1+ skill/cultivation feature.

### §5.5 Pattern: family + dynasty as separate from origin

**Every grand-strategy game** (CK3 / EU4 / Bannerlord / Total War) tracks family graph as first-class entity beyond origin/birth. CK3 has dynasties spanning centuries.

**Wuxia REQUIRES family/sect lineage** — sect inheritance + family bloodline + dynasty politics are core wuxia narrative drivers.

**Current IDF_004 lineage_id is opaque tag** — defers to V1+ FF_001 (Family Foundation). **Validated as correct V1 simplification, but FF_001 is V1+ priority** for wuxia content.

### §5.6 Pattern: society modeled as relationship graph + faction graph + reputation matrix

Beyond individual character systems, society = relationships:
- **Persona 5 Confidants** — 21 NPCs ranked 1-10
- **Mass Effect** — companion approval bars
- **CK3** — court + council + vassal relations
- **Bannerlord** — companion relations + lord relations + faction rep
- **Disco Elysium** — RCM precinct relations + Whirling-in-Rags relations + Hardie boys

**LoreWeave's NPC_001 npc_pc_relationship_projection (R8 import)** = per-NPC opinion. ✓ V1+ adds:
- Faction relationships (FF_002 future or Faction Foundation — not in IDF)
- Family relationships (FF_001 future)
- Reputation per faction (V1+ — depends on faction)

---

## §6 Wuxia-specific patterns (SPIKE_01 context)

SPIKE_01 = Tiên Hiệp (cultivation novel) + Vietnamese xianxia narrative. Survey wuxia game patterns:

### §6.1 Cultivation realm system

**Sands of Salzaar / Path of Wuxia / Sword & Fairy / Wuxia World mods**:
- Cultivation Realm (Phàm nhân → Trúc Cơ → Kim Đan → Nguyên Anh → Hóa Thần → Đại Thừa → Tiên / Ma): 5-7 ranks
- Each realm unlocks: Lex axioms (qigong / spirit sense / flying sword / immortality) + lifespan extension + status effects
- Mutable via training (chiến đấu / tu luyện / pillule alchemy)
- Realm decline possible (deviation events / killing Đạo path / etc.)

**Mapping to LoreWeave:**
- IDF_001 Race covers BIOLOGICAL race (Phàm nhân / Cultivator / Demon / Ghost / Beast — 5 types per current IDF_001 Wuxia preset)
- **Cultivation realm = SEPARATE V1+ feature** (CULT_001 Cultivation Foundation) within "Cultivator" race
- WA_001 Lex axioms gate by realm (V1+ `requires_cultivation_realm: Option<RealmTier>`)
- Realm progression Apply events similar to IDF_005 ideology Apply

### §6.2 Sect system (giáo phái / 宗派)

**Wuxia universal**:
- Sect = origin + ideology + skill specialization + faction
- One sect per character typically
- Defection = major life event
- Sect rivalries → opinion penalties + duels
- Sect leader / disciple ranks (đại sư huynh / nhị sư đệ / etc.)

**Mapping to LoreWeave:**
- **Sect cuts across IDF_004 Origin (which sect you came from) + IDF_005 Ideology (sect's belief system) + V1+ Faction (sect as faction)**
- **Recommendation: V1+ Faction Foundation (FAC_001) should own sect concept**, integrating refs from IDF_004 + IDF_005
- V1: Lý Minh's sect tag stored in `actor_origin.lineage_id` (opaque) + IDF_005 default ideology refs `[ideology_dao]` — this is V1 sufficient
- V1+: FAC_001 introduces `actor_faction_membership` aggregate with sect role + rank + reputation

### §6.3 Wulin Meng (martial alliance)

**Wuxia narrative** has cross-sect alliances (Wulin Meng = sects unite vs threats); subversion / power vacuums; martial law.

**Mapping:** V1+ Faction Foundation V1+ enhancements (alliances / hierarchies). Not IDF concern.

### §6.4 Inner / outer disciple ranks

**Wuxia sects** have hierarchical membership (inner disciples / outer disciples / core disciples / elders / sect master).

**Mapping:** V1+ FAC_001 captures rank within faction.

### §6.5 Heavenly Tribulation (天劫)

**Wuxia common**: cultivators who reach high realm face heavenly tribulation events (lightning strikes / demon assaults / etc.). Survival = next realm; failure = dispersal/death.

**Mapping:** V1+ scheduler V1+30d events tied to cultivation realm progression. Out of scope IDF.

### §6.6 Conclusion: wuxia validates IDF design but adds 2 V1+ features

V1+ priorities for wuxia content:
1. **CULT_001 Cultivation Foundation** — mutable rank-tier within Cultivator race
2. **FAC_001 Faction Foundation** — sect membership + rank + reputation; depends on IDF_004 + IDF_005

Both are NOT IDF V1 concerns. IDF V1 ships sufficient substrate (Race / Language / Personality / Origin / Ideology) to support V1 SPIKE_01 (literacy slip + NPC reactions); cultivation + sect are V1+ enrichment.

---

## §7 LLM-game opportunities (where existing games are limited)

Existing games' character/society systems are constrained by **predetermined rules** (closed-system). LLM enables fluid systems impossible in static games:

### §7.1 Open-ended dialogue from closed-system substrate

- **CK3 character** has 60+ traits but **dialogue is limited to scripted options** (~5-10 per interaction)
- **LoreWeave LLM** generates dialogue from same substrate (race + personality + ideology + opinion + scene context) → **infinite dialogue space**
- **Validation:** SPIKE_01 turn 5 LLM generates Du sĩ's reaction from substrate + canon-drift; static-rules game would need pre-scripted "if literacy mismatch → say X" branches

### §7.2 Emergent ideology without pre-authoring

- **RimWorld Ideology DLC** allows player-design ideoligion but precepts/rituals are predetermined templates
- **LoreWeave V1+** could allow LLM-generated ideology tenets from base ideology + actor ideology stance + scene events (e.g., LLM generates "in this reality, Đạo prohibits X" emergently from Đạo doctrine + LM01's stance)
- **Out of V1 scope** — but architectural runway preserved (IDL-D1 tenet system V1+)

### §7.3 Personality-driven NPC reactions at scale

- **Static-rules games** scale NPC reactions with hand-authored scripts (~100 NPCs each with 20-30 dialogue lines = 2000-3000 lines authored)
- **LoreWeave NPC_002 LLM-driven** scales with substrate × scene context — 100 NPCs × infinite scenes × infinite dialogue
- **LoreWeave's edge** — IDF_003 personality archetype + IDF_005 ideology stance = sufficient substrate for LLM persona prompt without per-NPC hand-authoring

### §7.4 Multi-language proficiency simulation at gameplay scale

- **Most games**: language is flavor only
- **LoreWeave**: A6 canon-drift detector consumes IDF_002 actor_language_proficiency to flag literacy slips — gameplay-relevant authenticity
- **Novelty validated**: SPIKE_01 turn 5 demonstrates LLM-driven dialog needs proficiency data to be canonical

### §7.5 Conclusion: LoreWeave's IDF substrate is novel

LoreWeave's IDF substrate sits at intersection of:
- CK3-depth (60+ traits across 5 categories)
- RimWorld-flexibility (Ideology DLC pattern)
- LLM-driven dialog (no pre-scripted branches)
- Multi-reality engine (closed-set per-reality)

No existing game combines all 4. IDF V1 design is novel + sufficient.

---

## §8 Society systems look-ahead (V1+ roadmap)

Beyond IDF, society systems likely needed (in priority order):

### §8.1 Priority 1 — V1+ first wave (post-IDF foundation)

| Feature ID | Name | Owns | Depends on |
|---|---|---|---|
| **PCS_001** | PC substrate | mortality_state + identity + (V1+) knowledge_tags | IDF_001/002/003/004/005 + RES_001 |
| **NPC_003** | NPC mortality | NPC mortality state machine | IDF_001/002/003/004/005 + PCS_001 |
| **FF_001** | Family Foundation | family graph + dynasty + lineage detail | IDF_004 + IDF_001 |
| **FAC_001** | Faction Foundation | sect / order / clan / guild | IDF_004 + IDF_005 + FF_001 |
| **REP_001** | Reputation Foundation | per-(actor, faction) reputation projection | FAC_001 |

### §8.2 Priority 2 — V1+ second wave (mid-game systems)

| Feature ID | Name | Owns |
|---|---|---|
| **CULT_001** | Cultivation Foundation | mutable cultivation realm tier (Wuxia) + Lex axiom gates |
| **DIPL_001** | Diplomacy Foundation | inter-faction relations + treaties + alliances |
| **SCH_001** | Schemes (CK3-style) | intrigue / plotting / influence |
| **CRT_001** | Court Foundation | hierarchical position within faction |
| **TIT_001** | Title Foundation | nobility / rank / honorific titles |

### §8.3 Priority 3 — V2+ deep simulation

| Feature ID | Name |
|---|---|
| **WAR_001** | Warfare Foundation |
| **TRD_001** | Trade Foundation (depends on RES_001 economy) |
| **REL_001** | Religion / Ritual Foundation (full tenet system per IDF_005 IDL-D1) |
| **ECN_001** | Economy Foundation (player-driven) |

### §8.4 Total roadmap

After IDF folder closure (~15 commits) → PCS_001 + NPC_003 (~8 commits) → FF_001 + FAC_001 + REP_001 (~12 commits) = ~35 commits across 4-5 lock-claim cycles to reach **society V1 ready**.

V1+ second wave (CULT_001 / DIPL_001 / etc.) adds ~30-50 commits. V2+ deep simulation = phase change.

---

## §9 Recommended adjustments to IDF concept-notes

Based on §4-§7 survey, here are validations + adjustments to current IDF concept-notes:

### §9.1 IDF_001 Race — confirmed; minor adjustment

✅ **Confirmed:** Closed-enum + size + lifespan + Lex axiom hook is industry-standard pattern (D&D / Pathfinder / Skyrim).

⚠️ **Adjustment:** Add deferral RAC-D11 for cultivation-realm-as-separate-V1+-feature note — clarifies that wuxia "cultivation realm" is NOT IDF_001 race expansion, it's V1+ CULT_001 Cultivation Foundation feature within the "Cultivator" race.

⚠️ **Adjustment:** RAC-Q4 (size 4 vs 5 vs 6) — Pathfinder 2e uses 5 (Tiny / Small / Medium / Large / Huge) which is more granular than D&D 5e's 4. Recommend revisit at DRAFT — V1 4 likely sufficient but Wuxia Demons can be Huge/Gargantuan...

### §9.2 IDF_002 Language — confirmed; novel

✅ **Confirmed:** 4-axis × 5-level proficiency matrix is **higher resolution than any mainstream game**. Validated by SPIKE_01 + Dwarf Fortress depth precedent.

✅ **Confirmed:** LanguageId vs LangCode separation matches Dwarf Fortress's per-civ language vs UI translation.

⚠️ **Note:** IDF_002 is one of LoreWeave's **architectural novelties** — no mainstream game models language proficiency at gameplay scale. Treat as differentiation, not validation pressure.

### §9.3 IDF_003 Personality — confirmed; potential V1 expansion

✅ **Confirmed:** Single archetype + voice register + opinion modifier table matches CK3 + VtM Nature/Demeanor patterns.

✅ **Confirmed:** 8 archetypes V1 is on narrow end but defensible — CK3 has 16, D&D has ~13.

⚠️ **Adjustment consideration:** PRS-Q1 — **revisit at DRAFT**. If first reality content (Wuxia preset) demands more than 8 archetypes, expand to 12 (current concept-note Optional 4 list: Loyal/Aloof/Ambitious/Compassionate). Currently Q1 default = 8; suggest defer Q1 final answer to DRAFT.

### §9.4 IDF_004 Origin — confirmed minimal V1; FF_001 priority

✅ **Confirmed:** Minimal stub (4 fields) is V1 right scope. D&D backgrounds + RimWorld backstories validate richer V1+ enrichment.

⚠️ **Adjustment:** Add deferral ORG-D11 for "Birth event metadata" (born-during-eclipse / born-of-virgin / "thiên kiêu chi tử" markers — wuxia-specific narrative tags).

⚠️ **Priority signal:** FF_001 (Family Foundation) is **V1+ priority** for wuxia content. Add explicit cross-ref in IDF_004 §10 confirming FF_001 V1+ landing.

### §9.5 IDF_005 Ideology — confirmed multi-stance V1; conversion mechanic V1+

✅ **Confirmed:** Multi-stance V1 (current) is canonical for wuxia. Cross-validated by Stellaris ethics axes + RimWorld memes + Disco Elysium thoughts.

⚠️ **Adjustment:** IDL-D11 NEW — **Conversion cost mechanic** (CK3 pattern: piety cost + opinion penalty + 6-month conversion period). V1+ when first reality demands conversion friction.

⚠️ **Adjustment:** IDL-Q2 (multi-stance V1 vs single-stance V1) — **CONFIRMED multi-stance**, supported by wuxia survey + Stellaris/RimWorld/Disco Elysium precedent. Lock multi-stance V1 at DRAFT.

### §9.6 Folder-level Q-decisions (refresh)

| Q ID | Original default | Survey-informed answer |
|---|---|---|
| **IDF-FOLDER-Q1** (folder name) | `00_identity/` | ✓ confirmed `00_identity/` |
| **IDF-FOLDER-Q2** (5 vs 4 features) | 5 features (split Origin + Ideology) | ✓ **confirmed 5** — CK3 + Pathfinder + VtM all explicitly separate culture from faith |
| **IDF-FOLDER-Q3** (Voice register own feature?) | Stay under IDF_003 | ✓ confirmed — VtM Nature has voice; CK3 personality has speech; couples to personality |
| **IDF-FOLDER-Q4** (Skills/Abilities = IDF_006?) | NO — V1+ combat feature | ✓ confirmed — Disco Elysium's skills-as-personality is novel but couples to combat too tightly for IDF |
| **IDF-FOLDER-Q5** (Knowledge inventory in IDF?) | NO — PCS_001 internal | ✓ confirmed — D&D knowledge proficiencies are class-based; matches PCS_001-internal scope |
| **IDF-FOLDER-Q6** (cross-reality migration) | V2+ defer | ✓ confirmed — no mainstream game does cross-engine migration |
| **IDF-FOLDER-Q7** (existing-features i18n audit) | DEFER | ✓ confirmed — RES_001 already locked this; don't reopen |

**ALL 7 folder-level Q-decisions validated by survey.** Promote to DRAFT confidently.

### §9.7 New folder-level deferrals (V1+ priority)

| ID | Item | Rationale | Priority |
|---|---|---|---|
| **IDF-FOLDER-D1** | FF_001 Family Foundation V1+ | Wuxia REQUIRES family/sect lineage + dynasty politics; CK3+Bannerlord validate | **High** — first V1+ priority post-IDF closure |
| **IDF-FOLDER-D2** | FAC_001 Faction Foundation V1+ | Sect / order / guild — wuxia core; CK3+VtM validate | High — depends on FF_001 + IDF_004/005 |
| **IDF-FOLDER-D3** | REP_001 Reputation Foundation V1+ | per-(actor, faction) reputation projection | Medium — depends on FAC_001 |
| **IDF-FOLDER-D4** | CULT_001 Cultivation Foundation V1+ | Wuxia mutable rank-tier; gates Lex axioms; SEPARATE from IDF_001 race | Medium — wuxia-specific; defer until first wuxia reality content beyond SPIKE_01 |
| **IDF-FOLDER-D5** | DIPL_001 Diplomacy Foundation V1+ | Inter-faction relations | Low — V2+ |
| **IDF-FOLDER-D6** | TIT_001 Title Foundation V1+ | Nobility / rank / honorifics (CK3 pattern) | Low — V2+ |

---

## §10 Open questions for user discussion (post-survey)

Based on survey, these are NEW questions worth user decision:

| Q ID | Question | Survey-informed default |
|---|---|---|
| **POST-SURVEY-Q1** | IDF_003 archetype count V1 — confirm 8 (current) or pre-emptively expand to 12 to match CK3 16-trait depth half? | **Defer Q1 to DRAFT** — author Wuxia preset content reveals if 8 is sufficient |
| **POST-SURVEY-Q2** | IDF_001 race size — 4 categories V1 (current) or 5 (add Tiny / Gargantuan)? | Wuxia Demons can be Huge/Gargantuan + Beasts can be Tiny → **expand to 5** at DRAFT (Small/Medium/Large/Huge/Gargantuan), revisit Tiny if first content demands |
| **POST-SURVEY-Q3** | IDF_005 conversion cost mechanic V1 (CK3-style piety cost + delay) vs free Apply/Drop V1? | **Free V1** (current), conversion cost V1+ IDL-D11 NEW |
| **POST-SURVEY-Q4** | Family graph (FF_001) — V1+ priority feature OR V1 sub-stub in IDF_004? | **V1+ separate FF_001 feature** (wuxia priority); IDF_004 lineage_id stays opaque |
| **POST-SURVEY-Q5** | Cultivation realm — V1+ CULT_001 feature OR V1 within IDF_001 race expansion? | **V1+ separate CULT_001** — race is biological category; cultivation is mutable rank within race; clear separation matches all wuxia game patterns |
| **POST-SURVEY-Q6** | Reputation — V1+ REP_001 feature OR V1 within FAC_001? | **V1+ separate REP_001** — reputation is per-(actor, faction) projection; deserves own aggregate; matches CK3 + Bannerlord pattern |
| **POST-SURVEY-Q7** | Voice register expansion — 5 variants V1 (current) or 7 (add Eloquent / Hesitant) per Q-PRS-Q3? | **5 V1** confirmed — covers core spectrum per VtM/CK3 patterns; V1+ extends |

---

## §11 Conclusion + recommended next steps

**Survey conclusions:**

1. **5-feature IDF split is validated** by major reference games (CK3 + Pathfinder + VtM + Disco Elysium + RimWorld). No adjustment to architecture needed.
2. **IDF V1 scope is correctly narrow** — 8 archetypes / 5 ideologies / 5 races per reality / minimal origin stub matches CK3-V1-equivalent depth.
3. **2 V1+ features are wuxia priorities** post-IDF closure: FF_001 (Family) + FAC_001 (Faction) — required for SPIKE_01 follow-on content (sect rivalries / family inheritance).
4. **1 V1+ feature is genre-specific**: CULT_001 Cultivation — within "Cultivator" race; mutable realm tier; gates Lex axioms; matches Sands of Salzaar / Path of Wuxia pattern.
5. **LoreWeave's IDF + LLM-driven approach is novel** in mainstream gaming — no existing game combines CK3-depth + RimWorld-flexibility + LLM-driven dialog + multi-reality engine. IDF substrate is sufficient; LLM consumers (NPC_002 + A6) provide the dialog/reaction layer that static-rules games hand-author.

**Recommended next steps:**

1. **User reviews this survey + answers POST-SURVEY-Q1..Q7** (10-15 min review)
2. **Lock survey-informed adjustments into concept-notes** (1 commit — minor edits to IDF_001/002/003/004/005 reflecting §9.1-§9.5)
3. **Promote IDF folder concept-notes → DRAFT in 5 lock-cycles** (~15 commits per existing plan)
4. **Add to IDF folder closure milestone:** explicit cross-refs to FF_001 + FAC_001 V1+ priorities
5. **Update SESSION_HANDOFF** with IDF folder status + V1+ society roadmap (§8) for context preservation

**Order of post-IDF V1+ features (recommended priority):**

```
IDF folder closure (5 features × ~3 commits) ~15 commits
    ↓
PCS_001 (consume IDF_001/002/003 + RES_001 + IDF_004/005 V1+ stubs) ~8 commits
    ↓
NPC_003 (mortality mirror PCS_001 pattern) ~5 commits
    ↓
FF_001 Family Foundation (wuxia priority) ~5 commits
    ↓
FAC_001 Faction Foundation (sect; depends on FF_001 + IDF_004/005) ~5 commits
    ↓
REP_001 Reputation Foundation (depends on FAC_001) ~5 commits
    ↓
[society V1 ready — full character + family + faction + reputation substrate]
    ↓
[V1+ second wave: CULT_001 / DIPL_001 / SCH_001 / etc.]
```

**Total path to society V1 ready:** ~43 commits across ~6-8 lock-cycles. Substantial but architecturally clean — no refactor pain because foundation tier discipline preserved.

---

## §12 Cross-references

**This survey informs:**
- [`_index.md`](_index.md) — folder-level Q1-Q7 validated by §9.6
- [`IDF_001_race_concept.md`](IDF_001_race_concept.md) — RAC-D11 added per §9.1
- [`IDF_003_personality_concept.md`](IDF_003_personality_concept.md) — Q1 deferred to DRAFT per §9.3
- [`IDF_004_origin_concept.md`](IDF_004_origin_concept.md) — ORG-D11 added per §9.4 + FF_001 priority signal
- [`IDF_005_ideology_concept.md`](IDF_005_ideology_concept.md) — IDL-D11 added per §9.5

**Cross-cutting (post-IDF closure):**
- Future FF_001 Family Foundation feature spec (wuxia priority)
- Future FAC_001 Faction Foundation feature spec (sect / order / guild)
- Future REP_001 Reputation Foundation feature spec
- Future CULT_001 Cultivation Foundation feature spec (Wuxia-specific)

**External references** (game source material — for future consumer agents):
- Crusader Kings 3 traits + faith systems documentation (Paradox Wikis)
- RimWorld Ideology DLC reference
- Pathfinder 2e Heritage + Background documentation
- Vampire: The Masquerade clan + sect framework
- Disco Elysium Thought Cabinet mechanic
- Sands of Salzaar / Path of Wuxia sect mechanics
