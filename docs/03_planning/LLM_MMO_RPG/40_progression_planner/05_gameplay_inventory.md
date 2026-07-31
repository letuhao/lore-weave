# 40.5 — Gameplay inventory (SHALLOW): cultivation spine + the general-RPG delta

> **Status:** INVENTORY · **Date:** 2026-07-31 · **Prefix:** `GP-`
> **Purpose:** one flat, deliberately shallow list of every gameplay loop the cultivation genre
> contains, with a stable id per entry, so each can later be deep-dived into a contract spec.
> **This document does no analysis on purpose.** No classification, no ownership, no architecture,
> no pool slots. One line each. Depth comes per-entry, later, on direction.

Sources: the deep-end novels (*A Record of a Mortal's Journey to Immortality*, *Renegade Immortal*,
*Battle Through the Heavens*) plus the reference games that actually implemented these —
**Amazing Cultivation Simulator**, **The Scroll of Taiwu**, **Tale of Immortal** — and the genre
encyclopedias. Full links at the end.

**178 entries, 18 families** (counted from the file, not asserted: `grep -c "^| \`GP-"`). Part 1
(`GP-A`..`GP-K`, 112) is the cultivation genre. Part 2 (`GP-L`..`GP-R`, 66) is **what a general RPG has
that the cultivation lens does not surface** —
added 2026-07-31 after checking Part 1 against RPG/MMO system taxonomies and against this repo's own
[feature index](../features/_index.md).

Supersedes [`40.2` §1](02_outcome_contract.md)'s 18 loops, a first pass at the same question.

> **The two sets OVERLAP; neither contains the other.** Part 1 covers progression, economy, social,
> world and metaphysics richly, and holds things a generic RPG has no concept of — a depleting
> lifespan clock (`GP-H1`), generational succession (`GP-K1`), karma and tribulation (`GP-I*`). It is
> nearly silent on equipment, loot, combat resolution detail, quests, dialogue, party and daily needs.
> **A pool built from Part 1 alone would produce a world with a superb power ladder, no swords, no
> quests, and nothing to say when the player speaks to someone.**

---

## A · The core cultivation loop

| id | loop | one-line mechanic |
|---|---|---|
| `GP-A1` | meditation / qi accumulation | a meter fills over time while the actor is idle in a suitable place |
| `GP-A2` | realm breakthrough | discrete gated transition at the meter's cap; **may fail** |
| `GP-A3` | sub-level advance | minor steps inside a realm, usually named by a pattern |
| `GP-A4` | bottleneck | a stall state that blocks advance until a specific condition removes it |
| `GP-A5` | technique / manual mastery | a learnable art with its own proficiency track and prerequisites |
| `GP-A6` | body cultivation track | a parallel ladder for the physical body, different inflows |
| `GP-A7` | soul / divine-sense track | a third ladder governing perception, range and soul attacks |
| `GP-A8` | multi-track balancing | cross-caps: one track's ceiling depends on another's level |
| `GP-A9` | half-step / partial states | in-between states that are neither the old realm nor the new |
| `GP-A10` | cultivation-speed modifiers | place, pill, technique, partner and pet all multiply the rate |
| `GP-A11` | cultivation-method choice | competing methods trade speed against ceiling, risk or side effects |

## B · Talent, constitution & identity

| id | loop | one-line mechanic |
|---|---|---|
| `GP-B1` | spiritual root | innate element affinity + purity; sets base rate and available paths |
| `GP-B2` | special physique | a rare innate type unlocking otherwise-inaccessible options |
| `GP-B3` | bloodline awakening | a latent inheritance that activates at thresholds |
| `GP-B4` | comprehension / talent stats | innate scalars modifying learning and insight |
| `GP-B5` | five-element affinity | element identity with a counter-relation cycle |
| `GP-B6` | dao heart / temperament | a mental-resilience variable that gates and can regress |
| `GP-B7` | innate fortune / luck | a hidden scalar biasing random outcomes and encounters |
| `GP-B8` | non-combat attributes | appearance, charm, reputation-facing stats |

## C · Professions & crafting

| id | loop | one-line mechanic |
|---|---|---|
| `GP-C1` | alchemy | recipe + ingredients + furnace + success probability → pills |
| `GP-C2` | artifact refining | same shape; produces treasures with ranks and charges |
| `GP-C3` | talisman making | consumable one-shot effects, written not forged |
| `GP-C4` | formation arrays | placed, persistent, area-effect constructs |
| `GP-C5` | beast taming | capture, bond, raise, and deploy a companion creature |
| `GP-C6` | puppetry | constructed proxies that act semi-autonomously |
| `GP-C7` | spirit farming | grow, tend and harvest ingredients over time |
| `GP-C8` | scholarly / refined arts | music, chess, painting, medicine as non-combat disciplines |
| `GP-C9` | recipe & manual discovery | acquiring, deciphering and reverse-engineering knowledge |
| `GP-C10` | profession grade ladder | each craft has its own independent rank track |
| `GP-C11` | quality tiers on output | the same recipe yields graded results |
| `GP-C12` | failure & material loss | a failed craft consumes inputs, sometimes destroys the tool |

## D · Combat & conflict

| id | loop | one-line mechanic |
|---|---|---|
| `GP-D1` | technique execution | spend qi to apply an effect, with cast/recovery cost |
| `GP-D2` | treasure activation | equipped artifacts with ranks, charges and attunement |
| `GP-D3` | realm-gap dominance | a hard curve: a lower realm cannot meaningfully hurt a higher one |
| `GP-D4` | elemental counters | five-element advantage applied in resolution |
| `GP-D5` | injury by body part | wounds tracked per limb/region, separate from a hit-point pool |
| `GP-D6` | internal vs external injury | qi damage and physical damage heal on different clocks |
| `GP-D7` | duel / life-and-death challenge | a formalised one-on-one with declared stakes |
| `GP-D8` | sect war / faction battle | large-scale conflict between organisations |
| `GP-D9` | monster subjugation | hunting powerful beasts for materials and territory |
| `GP-D10` | tournaments & rankings | scheduled competitive events producing a public ordering |
| `GP-D11` | flight, pursuit & escape | movement speed as a combat-relevant progression stat |
| `GP-D12` | poison, curse & assassination | indirect attack vectors with delayed effect |
| `GP-D13` | group combat & formation roles | parties with complementary roles and shared formations |

## E · Economy & resources

| id | loop | one-line mechanic |
|---|---|---|
| `GP-E1` | spirit-stone currency | dual-purpose: a medium of exchange **and** burnable fuel |
| `GP-E2` | material gathering | ore, herb, beast-part collection from the world |
| `GP-E3` | markets & shops | fixed venues to buy and sell |
| `GP-E4` | auctions | scheduled competitive sales of rare goods |
| `GP-E5` | contribution points | a second, non-transferable organisational currency |
| `GP-E6` | barter & faction trade | non-currency exchange, reputation-gated |
| `GP-E7` | inventory & storage rings | carrying capacity as an upgradeable constraint |
| `GP-E8` | spirit-vein ownership | controllable resource nodes with recurring yield |
| `GP-E9` | upkeep sinks | pills consumed, artifacts repaired, formations maintained |
| `GP-E10` | crafting-material tiering | inputs graded, and grade gates what can be made |

## F · Social, sect & politics

| id | loop | one-line mechanic |
|---|---|---|
| `GP-F1` | sect membership & rank | join, advance, and unlock rank-gated privileges |
| `GP-F2` | disciple recruitment | evaluate and admit new members by talent |
| `GP-F3` | master–disciple bond | a directed relationship carrying teaching and obligation |
| `GP-F4` | missions & assignments | organisation-issued tasks with rewards |
| `GP-F5` | righteous / demonic alignment | a path axis that opens and closes options |
| `GP-F6` | faction reputation | per-organisation standing driving access and price |
| `GP-F7` | rivalries & grudges | persistent hostility, **heritable across generations** |
| `GP-F8` | marriage & dual cultivation | a partner bond with mechanical effect on rate |
| `GP-F9` | favour, gifts & friendship | positive relationship accumulation |
| `GP-F10` | betrayal, expulsion, defection | relationship state transitions with lasting consequences |
| `GP-F11` | sect founding & leadership | becoming the organisation rather than joining one |
| `GP-F12` | reputation & notoriety | a public, world-visible standing distinct from faction reputation |

## G · World, exploration & gated content

| id | loop | one-line mechanic |
|---|---|---|
| `GP-G1` | region gating by realm | whole areas refuse entry below a threshold |
| `GP-G2` | secret realms | instanced, time-windowed, high-yield content |
| `GP-G3` | ruins & inheritance sites | one-shot discoveries granting techniques or treasures |
| `GP-G4` | travel & flight | crossing distance, with speed itself a progression reward |
| `GP-G5` | exploration & map reveal | uncovering the world as an activity |
| `GP-G6` | forbidden / lethal zones | areas that punish rather than gate |
| `GP-G7` | geomancy of place | a location's ambient properties modify what happens there |
| `GP-G8` | random encounters | chance meetings that inject opportunity or danger |
| `GP-G9` | world events & invasions | scheduled or triggered global disruptions |
| `GP-G10` | cross-realm passage | moving between whole worlds/planes, hard-gated |

## H · Life, time & mortality

| id | loop | one-line mechanic |
|---|---|---|
| `GP-H1` | lifespan as depleting clock | a meter that only falls; exhaustion is death |
| `GP-H2` | lifespan grants per realm | each breakthrough refills the clock |
| `GP-H3` | aging & decline | physical stats degrade with age below a certain realm |
| `GP-H4` | death & what persists | which state survives, and for whom |
| `GP-H5` | seclusion | a deliberate long time-skip trading time for progress |
| `GP-H6` | time cost of actions | a calendar/turn economy where everything costs time |
| `GP-H7` | permanent injury | wounds that never fully heal and cap capability |
| `GP-H8` | illness, poison & curse | conditions that persist and worsen without intervention |

## I · Metaphysics & fate

| id | loop | one-line mechanic |
|---|---|---|
| `GP-I1` | heavenly tribulation | an escalating survival challenge at major thresholds |
| `GP-I2` | tribulation variants | lightning, heart-demon, elemental, spatial, karma — different resolutions |
| `GP-I3` | heart demon | an internal antagonist attacking resolve rather than body |
| `GP-I4` | karma | accumulated cause-and-effect debt that returns later |
| `GP-I5` | oaths & heart vows | self-binding promises with mechanical enforcement |
| `GP-I6` | divine retribution | punishment for violating a dao rule |
| `GP-I7` | enlightenment moments | discrete insight events granting non-linear progress |
| `GP-I8` | reincarnation | identity continuing into a new body/life |
| `GP-I9` | body seizing | taking another's body; soul track persists, body track resets |
| `GP-I10` | soul survival after death | existing without a body, temporarily or permanently |
| `GP-I11` | ascension / transcendence | the endgame exit condition |
| `GP-I12` | fate / destiny markers | a declared role or prophecy that biases world behaviour |

## J · Base & management layer

| id | loop | one-line mechanic |
|---|---|---|
| `GP-J1` | construction & placement | building structures on owned territory |
| `GP-J2` | feng shui / adjacency | what sits next to what changes its effect |
| `GP-J3` | disciple assignment | allocating members to jobs and stations |
| `GP-J4` | production chains | inputs flowing through facilities into outputs |
| `GP-J5` | defence against invasion | protecting the base from external attack |
| `GP-J6` | influence spread | claiming and holding map territory |
| `GP-J7` | cultivation facilities | buildings whose purpose is to raise a rate or cap |
| `GP-J8` | logistics & storage | moving and holding goods at organisation scale |

## K · Meta, generational & narrative

| id | loop | one-line mechanic |
|---|---|---|
| `GP-K1` | generational succession | play continues as an heir rather than one immortal |
| `GP-K2` | inheritance of skills & property | what an heir receives from a predecessor |
| `GP-K3` | heritable vendetta | a grudge that survives the person who earned it |
| `GP-K4` | autonomous NPC lives | NPCs age, cultivate, fall ill, die, and act without the player |
| `GP-K5` | world-state persistence | the world remembers what previous lives changed |
| `GP-K6` | story hooks & canon events | authored narrative anchored into the simulation |
| `GP-K7` | difficulty & run modes | rule variants selected before a run |
| `GP-K8` | character creation & origin | starting identity, talent roll and background |

---

# Part 2 — the general-RPG delta

Everything below was **absent or only incidental** in Part 1. Same shallow discipline: one line each.

## L · Character build & customisation

| id | loop | one-line mechanic |
|---|---|---|
| `GP-L1` | class / role / job | a declared archetype shaping what an actor is good at |
| `GP-L2` | role identity in a group | tank / healer / damage / support as a designed division |
| `GP-L3` | skill or talent tree | spend points on a graph of prerequisite-gated nodes |
| `GP-L4` | respec / reset | undoing build choices, at a cost |
| `GP-L5` | multiclass / path switching | changing or combining archetypes mid-life |
| `GP-L6` | appearance customisation | cosmetic identity, independent of stats |
| `GP-L7` | titles | earned labels displayed with the actor |
| `GP-L8` | loadout presets | saved configurations swapped per situation |
| `GP-L9` | attribute point allocation | distributing a budget across core stats |

## M · Equipment & items

| id | loop | one-line mechanic |
|---|---|---|
| `GP-M1` | equipment slots | a fixed set of positions an actor may fill |
| `GP-M2` | rarity tiers | a graded quality axis on items |
| `GP-M3` | drop tables & loot rolls | what an encounter yields, and with what probability |
| `GP-M4` | affixes / enchanting | modifiers layered onto a base item |
| `GP-M5` | sockets & gems | slotted sub-items that modify the host |
| `GP-M6` | set bonuses | rewards for wearing matched pieces |
| `GP-M7` | durability & repair | equipment degrades and must be maintained |
| `GP-M8` | item identification | unknown items requiring an action to reveal |
| `GP-M9` | weight / encumbrance | carrying capacity as a limiting resource |
| `GP-M10` | consumables | one-shot usable items outside the pill economy |
| `GP-M11` | binding / tradability | whether an item can change hands |
| `GP-M12` | upgrade / reforge | improving an existing item rather than replacing it |

## N · Combat resolution detail

| id | loop | one-line mechanic |
|---|---|---|
| `GP-N1` | vital pools | hit points, stamina, mana — spent and restored, distinct from progression |
| `GP-N2` | hit / miss / crit / dodge / block | the probabilistic layer of an attack |
| `GP-N3` | armour & mitigation | damage reduction, distinct from avoidance |
| `GP-N4` | buffs & debuffs | timed modifiers applied to an actor |
| `GP-N5` | damage-over-time & crowd control | effects that persist, or remove agency |
| `GP-N6` | cooldowns & rotation | per-ability availability windows shaping play |
| `GP-N7` | threat / aggro | how a hostile chooses whom to attack |
| `GP-N8` | turn order or real-time tempo | who acts when |
| `GP-N9` | targeting & area shapes | who an effect reaches |
| `GP-N10` | death penalty | what is lost on defeat |
| `GP-N11` | respawn & recovery | how an actor returns |
| `GP-N12` | revival by another actor | restoring a fallen ally |
| `GP-N13` | encounter tuning | how a challenge is scaled to the actor |

## O · Quests & narrative

| id | loop | one-line mechanic |
|---|---|---|
| `GP-O1` | quest structure | main / side / chain / repeatable / timed — each a different contract |
| `GP-O2` | objectives & completion conditions | what counts as done |
| `GP-O3` | tracking & journal | the record the player reads |
| `GP-O4` | branching dialogue | a conversation with player-chosen paths |
| `GP-O5` | state-gated dialogue | what the actor *is* lets them say things others cannot |
| `GP-O6` | choice & consequence | a decision that changes later world state |
| `GP-O7` | multiple endings | run-level outcomes that differ |
| `GP-O8` | scripted scenes | authored moments interrupting simulation |
| `GP-O9` | codex / lore collection | discoverable world knowledge as content |
| `GP-O10` | hidden & secret content | things found only by acting on a clue |

## P · Party & companions

| id | loop | one-line mechanic |
|---|---|---|
| `GP-P1` | companion recruitment | acquiring a persistent allied actor |
| `GP-P2` | loyalty & approval | a relationship track with mechanical effect |
| `GP-P3` | party composition | who travels together, and the constraints on it |
| `GP-P4` | companion AI & orders | how an ally behaves when not directly controlled |
| `GP-P5` | hirelings & mercenaries | temporary allies bought rather than earned |
| `GP-P6` | shared progression & loot rules | how gains are divided in a group |

## Q · World, time & environment

| id | loop | one-line mechanic |
|---|---|---|
| `GP-Q1` | day / night cycle | time of day changing what is available |
| `GP-Q2` | seasons & weather | environmental state with mechanical effect |
| `GP-Q3` | calendar & scheduled events | recurring dated occurrences |
| `GP-Q4` | fast travel & waypoints | shortening traversal once earned |
| `GP-Q5` | points of interest | authored landmarks worth going to |
| `GP-Q6` | environmental storytelling | meaning carried by the place itself |
| `GP-Q7` | persistence vs instancing | whether a space is shared or copied per group |
| `GP-Q8` | resource contention | many actors competing for the same finite thing |

## R · Daily life & needs

| id | loop | one-line mechanic |
|---|---|---|
| `GP-R1` | hunger, thirst, sleep | needs that degrade and must be met |
| `GP-R2` | fatigue & rest | an activity budget that recovers over time |
| `GP-R3` | mood & comfort | a state driven by conditions, affecting output |
| `GP-R4` | grain-avoidance | the genre cancelling `GP-R1`: high cultivation removes the need to eat |
| `GP-R5` | livelihood outside power | mundane work, income and station |
| `GP-R6` | NPC daily routines | non-player actors having schedules and places to be |
| `GP-R7` | environment-driven illness | health from conditions, distinct from `GP-H8`'s poison and curse |
| `GP-R8` | leisure | doing something for its own sake |

---

## Not gameplay — the service layer, listed once so nobody looks for it here

`GP-*` is about what the **rules** contain. These are real systems a shipped game needs and are **out
of scope for a manifest of game rules**: achievements & collections · save/load, checkpoints,
permadeath modes · tutorial & onboarding · settings & accessibility · chat, friends, grouping, LFG ·
leaderboards · moderation & anti-cheat · telemetry · monetisation, seasons, battle pass · server /
shard / instance topology · matchmaking. They belong to the platform, not to a reality's rules.

*(Judgement call, stated so it can be overruled: `GP-Q7` persistence-vs-instancing is listed as
gameplay because it changes what a player can encounter; the shard topology beneath it is not.)*

---

## Deliberately not done here

Classification, ownership, pool slots, contracts, module boundaries, which entries LoreWeave's
profile needs, and which are out of scope. Each entry gets its own deep-dive on direction.

## Sources

- [Amazing Cultivation Simulator (Steam)](https://store.steampowered.com/app/955900/Amazing_Cultivation_Simulator/) · [Wikipedia](https://en.wikipedia.org/wiki/Amazing_Cultivation_Simulator) — sect management, feng shui, formations, auctions, tribulations, spirit beasts, spirit flora, body refinement, soul cultivation, body possession
- [The Scroll of Taiwu: Beyond The Dome (Steam)](https://store.steampowered.com/app/838350/The_Scroll_of_Taiwu__Beyond_The_Dome/) · [injuries & healing](https://scrolloftaiwu.com/guides/injuries-and-healing) · [combat](https://scrolloftaiwu.com/guides/how-combat-works) · [the Taiwu bloodline & generations](https://dragonforge.cc/games/the-scroll-of-taiwu/culture/the-taiwu-lineage-and-generational-play) — body-part wounds separate from HP, heritable grudges, generational succession
- [Tale of Immortal (Steam discussions)](https://steamcommunity.com/app/1468810/discussions/0/3834297685611617107)
- [Extended Cultivation Encyclopedia — half-steps, loose immortals, body cultivation, spirit stones](https://xianxialitrpgwiki.com/cultivation-encyclopedia/) · [spiritual roots](https://xianxialitrpgwiki.com/spiritual-roots/)
- [Cultivation 101: How Xianxia Power Systems Actually Work](https://donghuawiki.com/guides/cultivation-explained) · [Cultivation realms guide](https://wuxiatales.com/cultivation/cultivation-realms-explained/)
- [Xianxia & Xuanhuan Cultivation & Power Systems](https://shapes.inc/fandom/xianxia-xuanhuan/cultivation-systems) — tribulation waves, sect resource competition
- [Spirit Cultivation Genre — TV Tropes](https://tvtropes.org/pmwiki/pmwiki.php/Main/SpiritCultivationGenre) · [Xianxia (Wikipedia)](https://en.wikipedia.org/wiki/Xianxia) — karma, dao rules, divine retribution
- [Xianxia video games guide](https://xiuxian0.com/modern-influence/xianxia-games-guide/) · [Cultivation games — Immortal Forge](https://immortalforgestudios.com/cultivation-games/) — five-element combat interactions, data-driven alchemy/crafting pipelines, pet taming frameworks

**Part 2 — the general-RPG delta:**

- [RPG Game Design: fundamentals, patterns, mechanics](https://gamedesignskills.com/game-design/rpg/) · [How to make an RPG game](https://game-ace.com/blog/how-to-make-an-rpg-game/) — inventory/equipment (slots, weight, sets, durability), combat (turn order, damage formulas, status effects, AI), quests & narrative (main/side, branching dialogue, faction reputation), save/load
- [CRPG Analyzer: a checklist for computer role-playing games](https://rpgwatch.com/forum/threads/crpg-analyzer-a-checklist-for-computer-role-playing-games.20485/)
- [A new taxonomy of RPGs](https://moegamer.net/2024/11/06/a-new-taxonomy-of-rpgs/) · [Status effect](https://en.wikipedia.org/wiki/Status_effect)
- [Hate / threat / aggro](https://en.wikipedia.org/wiki/Hate_%28video_games%29) · [The death-penalty mechanic and loss aversion](https://wolfsheadonline.com/the-death-penalty-mechanic-and-loss-aversion-in-mmo-design/) · [MMORPG feature directory](https://gamerguildhall.com/play/directory/gamefeaturesmmorpg.shtml)
- This repo's own [`features/_index.md`](../features/_index.md) — the folders `00_titles`, `00_resource`, `12_daily_life`, `13_quests`, `19_ability`, `07_social` and `08_narrative_canon` each named a system Part 1 had no entry for
