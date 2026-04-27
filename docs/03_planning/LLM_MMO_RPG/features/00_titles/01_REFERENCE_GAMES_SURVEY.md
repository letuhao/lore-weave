# TIT_001 Title Foundation — Reference Games Survey

> **Status:** DRAFT 2026-04-27 — Phase 0 reference materials capture; informs Q-deep-dive batched decisions.
> **Companion docs:** [`_index.md`](_index.md) (folder index) + [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) (concept brainstorm + Q1-Q10)
> **Methodology:** Survey 9 reference systems; identify patterns relevant to TIT_001 V1 scope; flag what each system does well and what falls outside V1 scope.

---

## §1 — Crusader Kings III (CK3) — PRIMARY REFERENCE

**Genre:** Grand strategy + dynasty simulation
**Why primary:** CK3's title system is the gold standard for political titles + succession laws + vassalage hierarchy. Mature mechanics across 1000+ playtest hours per typical user. Closest match to LoreWeave's Wuxia + D&D + modern political needs.

### What CK3 does

**Title hierarchy** (vassalage tree):
- Barony → County → Duchy → Kingdom → Empire (5 levels of vassalage; each title is HELD by 1 character at a time)
- Each title has a "Liege" (the title holder above) and "Vassals" (title holders below)
- Title de-jure boundaries (geographic claims; defined per map cell)

**Succession laws** (8 variants — reality-author choice per title or per dynasty):
1. **Confederate Partition** — split title among all eligible heirs
2. **Partition** — primary heir gets primary title; others get demesne
3. **High Partition** — primary heir keeps more
4. **Single Heir Primogeniture** — eldest son inherits everything (gender-locked)
5. **Single Heir Ultimogeniture** — youngest son inherits (rare)
6. **Elective** — vassals vote on heir from candidates
7. **Feudal Elective** — primary council elects (heretic/HRE-style)
8. **Open Succession** — chaos — every dynasty member candidate

Each succession law has gender variants: agnatic / agnatic-cognatic / cognatic / enatic / enatic-cognatic.

**Title-grant authority**:
- Holding a title grants real authority (de-jure rule of vassal lands)
- Vassals owe taxes / levies / opinions to liege
- Title-loss = loss of authority + dynasty prestige hit

**Title decay**:
- Titles can be revoked (with prestige hit + tyranny + vassal opinion drops)
- Title destruction (rare; "Destroy Empire of Britannia" is a decision)

**De jure vs de facto**:
- De jure title = "this title rightfully claims X land"
- De facto holder = "this character actually holds the title now"

### What we KEEP for TIT_001 V1

| CK3 pattern | LoreWeave V1 mapping |
|---|---|
| Title-as-discrete-holding (atomic grant) | ✅ TIT_001 actor_title_holdings sparse aggregate |
| Succession law per title | ✅ SuccessionRule enum (Eldest / Designated / Vacate; V1+ FactionElect) |
| Title-holder grants authority (role) | ✅ TitleAuthorityDecl.faction_role_grant V1 |
| Vacancy semantic | ✅ VacancySemantic per-title (PersistsNone / Disabled / Destroyed) — Q9 D pre-rec |
| Multi-title hold cap | ✅ MultiHoldPolicy per-title (Exclusive / Stackable / Cap-N) — Q5 C pre-rec |

### What we DEFER from CK3

| CK3 feature | Defer to | Why |
|---|---|---|
| Vassalage hierarchy (5-level tree) | V2+ TIT_002 | Adds title-tree concept; large schema; V1 keeps flat per-title list |
| 8 succession law variants | V1+30d enrichment | V1 ships 3 (Eldest / Designated / Vacate); CK3-equivalent gender variants V1+ if needed |
| De jure vs de facto distinction | V2+ if vassalage ships | Requires geographic claim layer (PF_001 PlaceTypeRef cross-feature) |
| Title destruction with prestige hit | V1+ alongside REP_001 runtime delta milestone | REP_001 V1 doesn't have runtime delta yet |
| Title decay / drift over time | V1+ if needed | Most LoreWeave titles are static-until-death; CK3 decay rare |

---

## §2 — Mount & Blade II: Bannerlord

**Genre:** Sandbox medieval simulation + warband management
**Why surveyed:** Bannerlord's lord title system separates clan (family) from title (rank) cleanly — directly relevant to FAC_001 + TIT_001 boundary discipline.

### What Bannerlord does

**Lord title** = noble rank (lord / king / queen / mercenary captain):
- Title is held by 1 character; tied to a "Clan" (family/retinue)
- Clan owns settlements (fiefs); lord title-holder rules clan
- Multiple clans coexist in a kingdom; one clan's lord = king

**Title-grant**:
- King grants fiefs (settlement title) to vassal clan lords
- Vassal lord rules fief; pays taxes; supplies levies
- Title can be lost in war (settlement captured by enemy clan)

**Succession**:
- On lord death, clan's heir (designated by player; CK3-pattern) inherits
- Heir = next clan member (oldest son/daughter; or player-designated)
- If no heir, clan dissolves; vassals reabsorbed by liege

**Companion to clan**:
- Clan = family + retinue (FF_001 family_node + FAC_001 actor_faction_membership in LoreWeave)
- Title = lord/king rank (TIT_001 separate from clan)
- Bannerlord blends Bannerlord clan + lord title; LoreWeave separates cleaner

### What we KEEP for TIT_001 V1

| Bannerlord pattern | LoreWeave V1 mapping |
|---|---|
| Title separate from clan/family | ✅ TIT_001 actor_title_holdings ≠ FF_001 family_node ≠ FAC_001 actor_faction_membership |
| Clan-bound title (lord of clan X) | ✅ TitleBinding::Dynasty (LoreWeave family_patriarch_li title bound to lineage_li dynasty) |
| Player-designated heir | ✅ Forge:DesignateHeir admin (Q6 C pre-rec — author + Forge both supported) |
| Title loss = clan dissolution → title destroyed | ✅ VacancySemantic::Destroyed for clan-dissolution titles |

### What we DEFER

| Bannerlord feature | Defer to | Why |
|---|---|---|
| Settlement-attached titles (fief lord) | V2+ vassalage hierarchy alongside TIT_002 | Geographic claim layer; complex |
| Tax/levy mechanics | V2+ ECON | Not core TIT_001 V1 |
| Mercenary captain title (paid contract) | V2+ contract feature | Not core wuxia/D&D V1 |

---

## §3 — Game of Thrones / political fantasy (NARRATIVE PATTERN)

**Genre:** TV series / book franchise (not a game; pattern reference only)
**Why surveyed:** GoT's title-and-succession drama informs narrative-quality requirements for TIT_001 V1 LLM narration.

### What GoT does narratively

**Iron Throne succession** (chaos-pattern):
- King's death → multiple claimants (eldest son / brother / cousin / illegitimate child)
- War of Five Kings = 5 simultaneous claimants
- Designated heir (Crown Prince) often killed; backup heirs activated; SuccessionRule = Eldest with cascading fallbacks

**Lord paramount titles** (regional):
- House Stark = Warden of the North; House Tully = Lord of Riverrun
- Title bound to House (LoreWeave: Dynasty); succession Eldest within house

**Granted honors** (king's favor):
- "Lord Commander of the Kingsguard" — grants prestige; revocable
- Knight titles ("Ser") — granted by knighting ceremony; near-permanent

**Title-as-narrative-device**:
- Characters' titles foreshadow plot (Daenerys "Khaleesi" → "Mhysa" → "Queen of the Seven Kingdoms")
- Title loss = character arc beat ("Theon" loses Stark identity, gains "Reek")

### What we KEEP for TIT_001 V1

- ✅ **Narrative hint per title** (TitleAuthorityDecl.narrative_hint: I18nBundle) — LLM uses for persona briefing + dialogue generation
- ✅ **Designated heir + cascading fallbacks** (Q6 C pre-rec — author canonical + Forge runtime; if designated dies, FF_001 dynasty traversal V1+ fallback)
- ✅ **Granted-honor titles** (TitleBinding::Standalone with Vacate succession; modeled as VacancySemantic::PersistsNone for revivable honor)

### What we DEFER

- ❌ **Title-loss character arc tracking** (V2+ narrative state machine; out of TIT_001 scope)
- ❌ **Multiple claimants War-of-Five-Kings simulation** (V2+ political simulation; very complex)

---

## §4 — Wuxia novels (PRIMARY GENRE CANON)

**Genre:** Chinese xianxia + wuxia + xuanhuan literature
**Why primary:** LoreWeave is wuxia-genre-prioritized per user direction; titles in wuxia carry cultural weight (sect-master = political authority + martial-arts authority + cultivation tier; emperor = mandate of heaven).

### Common wuxia titles + patterns

| Title (Chinese) | Vietnamese | Binding | Succession |
|---|---|---|---|
| 掌门 Chưởng môn (Sect Master) | "Đông Hải Đạo Cốc Chưởng Môn" | Faction (sect) | Designated by previous master OR sect council (FactionElect V1+) |
| 长老 Trưởng lão (Elder) | "Đông Hải Đại Trưởng Lão" | Faction (sect) | Designated by sect master |
| 皇帝 Hoàng đế (Emperor) | "Hoàng Đế Đông Phong" | Standalone OR Dynasty | Eldest son (Crown Prince Designate) |
| 太子 Thái tử (Crown Prince) | "Thái Tử" | Dynasty | Eldest son of emperor (designated) |
| 王 Vương (King) | "Đông Hải Vương" | Dynasty OR Standalone | Eldest |
| 公主 Công chúa (Princess) | "Đông Hải Công Chúa" | Dynasty | Position-only; doesn't usually inherit |
| 族长 Tộc trưởng (Family Patriarch) | "Lý Gia Gia Trưởng" | Dynasty (clan) | Eldest son OR family elder council |
| 大侠 Đại hiệp (Great Hero) | "Đại Hiệp" | Standalone | Vacate (achievement-only; rep-gated) |
| 武林盟主 Wulin Pháp Thần | "Võ Lâm Minh Chủ" | Standalone | FactionElect (Wulin council vote V1+) |
| 圣女 Thánh nữ (Sacred Maiden) | "Thánh Nữ" | Faction (cult/sect) | Designated by cult/sect leaders |

### Wuxia-specific patterns

**Cultivation-tier-coupled titles**:
- "Hóa Thần Trưởng Lão" (Spirit-Severing Elder) — title implies min cultivation tier
- LoreWeave V1 may add `min_progression_tier: Option<ProgressionTierGate>` field on TitleDecl
- DECISION: defer to Q-list addition? OR omit V1 (per PROG-A1 "no central level")? Lean omit V1; reality author can declare via Forge admin enforcement

**Inheritance-via-master-disciple** (sect-master succession):
- 掌门 inherits to top disciple; disciple-master bond (FAC_001 master_actor_id field per FAC-D7 closure)
- Eligible heir = top disciple with min cultivation + min rep + sect approval
- LoreWeave V1: SuccessionRule::Designated covers; FactionElect V1+ for council-vote variant

**Sect-elder council**:
- "长老团" (Council of Elders) — collective decision body
- Sect-master succession may require council vote (FactionElect V1+)
- Elder titles often Stackable (sect can have 5+ elders)

**Imperial mandate of heaven**:
- 天命 (mandate of heaven) — emperor legitimacy depends on cosmic alignment
- Title-loss = mandate withdrawal (signs in heavens / disasters)
- LoreWeave V1: pure narrative_hint; V2+ cosmic events feature could trigger title revocation

### What we KEEP for TIT_001 V1

- ✅ **Faction-bound + Dynasty-bound + Standalone three-axis** (Q2 B pre-rec — Discriminated TitleBinding enum)
- ✅ **Designated succession via master-disciple** (Q3 A pre-rec — Designated as V1 variant)
- ✅ **Multi-elder titles via StackableUnlimited** (Q5 C pre-rec — per-title MultiHoldPolicy)
- ✅ **I18nBundle for Chinese + Vietnamese + English display** (matches RES_001 i18n contract)
- ✅ **Min reputation gate per title** (Q4 C pre-rec — schema-active V1)

### What we DEFER

- ❌ **Cultivation-tier gating on title** — V1+ if needed; V1 omits to honor PROG-A1; reality author can declare via Forge
- ❌ **Cosmic mandate-of-heaven mechanic** — V2+ cosmic-events feature
- ❌ **Wulin council Faction Elect** — V1+ DIPL_001 procedural voting (V2+)
- ❌ **Position-only titles that don't inherit** (Princess) — covered by VacancySemantic::Destroyed pattern; V1 supported

---

## §5 — Imperator: Rome (Paradox)

**Genre:** Grand strategy + Roman politics
**Why surveyed:** Senate-titles + magistrate succession patterns relevant to non-monarchy political realities.

### What Imperator does

**Magistrate titles**:
- Consul (1-year term) / Praetor (1-year term) / Aedile (5-year? term) / Senator (life)
- Election-based succession; senate votes
- Term-limited: title auto-vacates after fiction-time elapsed

**Senator title**:
- Life-long; granted by family wealth + influence
- Senator can hold multiple magistracies in lifetime
- Ranked by speaking order (seniority)

**Office-as-power-base**:
- Holding title grants senate vote weight
- Loss of office = loss of political power
- Faction (Optimates / Populares) influence depends on members holding titles

### What we KEEP

- ✅ **Election-based succession** — Q3 V1+ FactionElect variant (deferred to DIPL_001)
- ✅ **Multi-title hold (senator + consul simultaneously)** — Q5 C MultiHoldPolicy::StackableMax(N)

### What we DEFER

| Imperator feature | Defer to | Why |
|---|---|---|
| Term-limited titles (1-year consul) | V2+ if needed | Requires fiction-time bound on title; complex; V1 titles are "until death/revoke" |
| Senate vote weight | V2+ DIPL_001 | Political simulation feature |
| Speaking order seniority | V2+ | Niche feature |

---

## §6 — Stellaris (Paradox)

**Genre:** Grand strategy + space empire
**Why surveyed:** Ruler/leader trait system + multi-title pattern relevant.

### What Stellaris does

**Ruler title** (Emperor / President / Chairman):
- Government-form-dependent title (Empire = Emperor; Democracy = President; Hive Mind = collective)
- Succession depends on government form (hereditary / elected / appointed)

**Leader-trait inheritance**:
- Ruler accumulates traits over lifetime ("Charismatic" / "Iron Fist")
- New ruler inherits some traits via founding civic OR education
- Traits influence empire policy options

**Multi-title** (rare):
- "Custodian of the Galactic Community" — temporary emergency title
- Held in addition to ruler title

### What we KEEP

- ✅ **Government-form-dependent succession** — modeled via per-reality TitleDecl.succession_rule (each title has own rule)
- ✅ **Temporary emergency title** — V1+ VacancySemantic::Destroyed after fiction-time-window (V2+)

### What we DEFER

- ❌ **Trait-based inheritance** — V2+ if needed; out of TIT_001 V1
- ❌ **Government-form mechanics** — V2+ POLITY feature

---

## §7 — World of Warcraft (Blizzard)

**Genre:** MMORPG
**Why surveyed:** Achievement-title pattern (informational; not for V1 mechanics).

### What WoW does

**Achievement titles**:
- "Slayer of the Lich King" — earned by defeating raid boss
- Pure cosmetic; no mechanical authority
- Multiple titles can be held; player picks 1 to display

**Honor-rank titles** (PvP):
- "Field Marshal" / "Commander" / "Lieutenant General" — ranked by PvP score
- Decay over time (rank 1 → rank 5 if inactive)
- Mostly cosmetic; small bonuses

### What we KEEP

- ✅ **Achievement-only titles** (TitleBinding::Standalone + SuccessionRule::Vacate + VacancySemantic::PersistsNone — multiple holders OK)
- ✅ **Multi-hold display** (LoreWeave: actor_title_holdings allows multiple; LLM persona briefing can use any/all)

### What we DEFER

- ❌ **Title decay over time** — V2+ if needed
- ❌ **PvP-ranked titles** — V2+ if PvP feature ships

---

## §8 — Dwarf Fortress (Bay 12)

**Genre:** Roguelike fortress simulator
**Why surveyed:** Noble succession + position-management mechanics.

### What Dwarf Fortress does

**Noble positions** (auto-appointed):
- Mayor / Captain of the Guard / Bookkeeper / Manager / etc.
- Auto-appointed when fortress meets criteria (population threshold)
- Held by 1 dwarf at a time; dwarf must meet skill requirements

**Succession**:
- Noble dies → next eligible dwarf auto-appointed
- Player can manually appoint via menu (Forge:GrantTitle pattern)

**Position-grants-authority**:
- Mayor sets export quotas; Captain of Guard schedules patrols
- Position abuse triggers tantrums + unrest

### What we KEEP

- ✅ **Auto-appointment via SuccessionRule::Eldest fallback** (LoreWeave: if Designated heir invalid, fall back to FF_001 dynasty Eldest)
- ✅ **Skill requirements for position** — V1+ progression tier gate (deferred Q-decision)

### What we DEFER

- ❌ **Auto-appointment threshold** (population-based) — V2+ procedural triggers
- ❌ **Position-abuse unrest** — V2+ social simulation

---

## §9 — D&D 5e (TTRPG)

**Genre:** Tabletop RPG
**Why surveyed:** Noble background + lord-title mechanics (informational; not for V1 mechanics).

### What D&D 5e does

**Noble background feature**:
- "Position of Privilege" — granted by noble birth (FF_001 dynasty member)
- Grants social access (commoners defer; nobles accept hospitality)
- No succession mechanics; static social position

**Lord titles** (campaign-specific):
- DM grants lord/lady/baron/etc. as quest rewards
- Pure narrative; sometimes mechanical (vassal levies in Strongholds & Followers)

### What we KEEP

- ✅ **Static social position via narrative_hint** (TitleAuthorityDecl.narrative_hint for LLM)
- ✅ **DM/Forge admin grants title** (Forge:GrantTitle V1)

### What we DEFER

- ❌ **Vassal levy mechanics** — V2+ ECON
- ❌ **Background-feature integration** — covered by IDF_004 origin_pack default_titles V1+ (REP-D14 pattern)

---

## §10 — Anchor pattern for TIT_001 V1

Synthesizing all 9 references:

**TIT_001 V1 = CK3 + Wuxia hybrid**:
- **CK3 patterns kept**: title-as-discrete-holding + per-title succession_rule + multi-hold policy + vacancy semantic + author-declared per-reality
- **Wuxia genre canon**: faction-bound (sect-master) + dynasty-bound (emperor/family-patriarch) + standalone-honor (Đại Hiệp); I18nBundle for Chinese + Vietnamese + English
- **Bannerlord lesson**: TIT_001 separate from FF_001 family + FAC_001 faction (cleaner than Bannerlord's clan/lord blend)
- **GoT narrative**: title narrative_hint for LLM persona briefing + dialogue generation
- **Imperator/Stellaris/WoW/D&D defer**: term-limits / vassalage / decay / political-simulation all V2+

**Out of V1 scope (per references)**:
- ❌ Vassalage hierarchy (CK3 5-level tree) — V2+ TIT_002
- ❌ Term-limited titles (Imperator consul) — V2+ if needed
- ❌ Trait-based inheritance (Stellaris) — V2+
- ❌ De jure vs de facto (CK3) — V2+ alongside vassalage
- ❌ Title decay over fiction-time — V2+
- ❌ PvP-ranked titles (WoW) — V2+ if PvP ships
- ❌ Cultivation-tier gating (wuxia) — defer to author canonical seed validation V1; engine doesn't gate

**V1 scope confirmed minimal + per-reality discipline preserved.**

---

## §11 — Cross-references

- [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) — concept brainstorm + Q1-Q10 critical questions
- [`_index.md`](_index.md) — folder index
- `features/00_family/01_REFERENCE_GAMES_SURVEY.md` — FF_001 reference survey (CK3 dynasty patterns lifted here)
- `features/00_faction/01_REFERENCE_GAMES_SURVEY.md` — FAC_001 reference survey (Bannerlord clan patterns; "Bannerlord clan = FF + FAC + V1+ TIT_001" already noted)
- `features/00_reputation/01_REFERENCE_GAMES_SURVEY.md` — REP_001 reference survey (CK3 prestige; not lifted to TIT_001 V1)
