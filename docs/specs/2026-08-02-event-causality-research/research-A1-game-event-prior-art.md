# Prior Art: What "an event" IS, and what gets stored — game & simulation systems

Research brief A1. Scope: **game and simulation engines only** (a sibling agent covers enterprise
event-sourcing/CQRS). Sources are cited inline. Where a source states something, I say "states";
where I am reasoning past the source, I say **[INFERENCE]**.

Date of research: 2026-08-02.

---

## 0. Executive framing

Nothing in the surveyed corpus uses "event" as one concept. Every mature system splits the word into
**between three and six distinct kinds of thing**, and the split is almost always along the same three
axes:

1. **Lifetime** — one tick / one frame / until consumed / forever.
2. **Authority** — is this a *decision* (which must be adjudicated) or a *report* (which is already true)?
3. **Derivability** — can this be recomputed from other state, or is it the only witness to something?

The systems that got into trouble are, without exception, the ones that used *one* mechanism across
two of those axes. (See §F.)

---

## A. Taxonomy — what different systems call "an event"

### A.1 The seven senses of "event" found in the wild

| Sense | Canonical name(s) in the field | Lifetime | Who can create it |
|---|---|---|---|
| **1. Intent / command** | Paradox `decision`, GAS "ability activation request", AoE "command", MUD player command | transient, pre-adjudication | player/AI, *outside* the authority boundary |
| **2. Engine hook / on_action** | Paradox `on_action`, Bethesda Story-Manager `SM_Event`, LPMud `heart_beat`, Qud `MinEvent` | transient, intra-tick | the engine, at a named code site |
| **3. Rule-engine fact** | Valve "facts"/criteria, Ceptre linear-logic resource, Talk-of-the-Town belief | *long-lived*, queryable | the simulation, as a side effect |
| **4. Threshold / state derivation** | RimWorld Hediff *stage*, GAS attribute-crossing, Paradox `trigger` | **derived, never stored** | nobody — it is a function of state |
| **5. Status application** | GAS `GameplayEffect`, RimWorld `Hediff`, Paradox modifier/flag | durable while active | the rules layer |
| **6. Narrative occurrence** | Paradox `event`, RimWorld `Incident`, DF `historical_event`, Bethesda quest | durable (as a *record*) | the storyteller/director |
| **7. Presentation cue** | GAS `GameplayCue`, WoW combat-log line, DF legends text | transient, unreliable, cosmetic | derived from 5/6 |

### A.2 Where systems *disagree*, and why

**Disagreement 1 — is a status effect an event or a state?**
- **GAS says state.** A `GameplayEffect` with `Has Duration` or `Infinite` policy is put into the
  *Active Gameplay Effects Container* and is a live object; only an `Instant` effect "execute[s]
  immediately and never enter[s] the Active Gameplay Effects Container"
  (https://dev.epicgames.com/documentation/en-us/unreal-engine/gameplay-effects-for-the-gameplay-ability-system-in-unreal-engine).
  So GAS has a hard, explicit fork: *instant = an event*, *durational = an entity*.
- **RimWorld agrees**: a `Hediff` is an object on the pawn with a `severity` float, and its "stages"
  are re-derived from severity — "each stage is activated upon reaching a certain minimum severity"
  (https://rimworldwiki.com/wiki/Hediffs). The *stage* is never stored; the *severity* is.
- **Paradox disagrees in the other direction**: a modifier applied by an event is a durable scripted
  object, but the *event that applied it* leaves behind only a flag. Both `set_country_flag` /
  `set_variable` persist in the save; the event instance does not
  (https://eu4.paradoxwikis.com/Event_modding, https://github.com/jesec/ck3-modding-wiki/blob/master/wiki_pages/Scripting.md).

  **Why the disagreement matters:** GAS/RimWorld need to *tick* the status (duration, periodic
  application, severity progression), so it must be an object. Paradox mostly needs to *test* the
  status ("has this happened?"), so a flag suffices. **The fork is driven by whether the status has
  its own clock.**

**Disagreement 2 — does the log *cause* anything, or only *witness*?**
- **Dwarf Fortress**: the `historical_event` is a pure witness. Each carries `id`, `year`,
  `seconds72` ("There are 403200 seconds in a year"), and `type`, plus type-dependent references by
  id (`hfid`, `civ_id`, `site_id`, `artifact_id`) — ~48 type values including `hf_died`,
  `artifact_created`, `attacked_site`, `add_hf_entity_link`
  (https://dwarffortresswiki.org/index.php/v0.31:XML_dump). Legends mode reads this; the live
  simulation does not consult it to decide what happens next. **The log is downstream of causality.**
- **Valve's dynamic-dialog system inverts this**: the log *is* the query surface. World state is kept
  as a large set of facts and "hundreds of facts about the world [are matched] in a fuzzy pattern
  match against a database of thousands of possible lines"
  (https://www.gamedeveloper.com/design/video-valve-s-system-for-creating-ai-driven-dynamic-dialog,
  https://gdcvault.com/play/1015528/AI-driven-Dynamic-Dialog-through). Emily Short's account adds the
  key selection rule: "it prioritizes rules and applies the most specific one it can find, using
  less-specific ones as fall-backs" (https://emshort.blog/2012/03/16/gdc-2012-talk-on-dynamic-dialogue/).
- **Story sifting is the extreme of the witness position, retro-fitted into causality**: "events that
  emerge from simulation are stored in a database, and users create sifting patterns using a query
  language consisting of logic variables and their relationships"
  (https://mkremins.github.io/publications/Felt_SimpleStorySifter.pdf,
  https://dl.acm.org/doi/10.1145/3723498.3723809). Kreminski's *incremental sifting* then closes the
  loop: partially-matched patterns feed a drama manager that "intervene[s] to make those stories more
  likely to complete" (https://eprints.soton.ac.uk/482864/1/Awash.pdf).

  **This is the single most transferable idea in the corpus**: a durable event log with a *pattern
  query language over it* is a legitimate causality input, not merely an archive — but the systems
  that do this keep the query layer strictly separate from the tick layer.

**Disagreement 3 — is "the fact" and "the telling of the fact" one object?**
- **GAS says emphatically no.** `GameplayCue` is the presentation half and Epic frames it as "a
  network-efficient way to manage cosmetic effects, like particles or sounds"
  (Epic docs, above). The community documentation is blunter: "GameplayCues are not guaranteed" —
  they ride unreliable multicast (https://raw.githubusercontent.com/tranek/GASDocumentation/master/README.md).
  And the *shape* of the cue is derived from the effect's duration policy: "Instant `GameplayEffect`
  will call `Execute` on the `GameplayCue` `GameplayTags` whereas a `Duration` or `Infinite`
  `GameplayEffect` will call `Add` and `Remove`" (ibid).
- **WoW says no, by accident of architecture.** `COMBAT_LOG_EVENT_UNFILTERED` is a client-side ring
  buffer — "stores the last five minutes worth of raw combat events" — with a rigid
  prefix+suffix subevent naming scheme (`SPELL_DAMAGE`, `SWING_MISSED`) and a fixed 11-field header
  (timestamp, subevent, hideCaster, source GUID/name/flags/raidFlags, dest …)
  (https://warcraft.wiki.gg/wiki/COMBAT_LOG_EVENT). It is a *report of what the server already did*.
  Blizzard's ability to simply **remove addon access to it in patch 12.0.0** without changing any
  game rule is the proof that it was never load-bearing state.
- **EVE says "no — and that was our bug."** Killmails were originally *generated text mailed to
  players*. CCP: "I've ripped out the code that generated the text mails and replaced it with a new
  system that packages up the kill into the database in a relatively normalized format," which killed
  three whole failure classes: mails lost to NPCs, "Truncation. This is a thing of the past," and
  untranslatable text ("we can generate properly translated mails for all viewers")
  (https://www.eveonline.com/news/view/the-killmail-mk-1.5-project).

  **The EVE lesson stated plainly: they had stored the *rendering* instead of the *record*, and every
  problem they had came from that.** Store structured facts; render late.

### A.3 The one distinction nearly everyone converges on

**Intent ≠ occurrence.** Age of Empires' lockstep networks *commands* (intents), never resulting
state, and every machine derives the occurrence identically
(https://www.gamedeveloper.com/programming/1500-archers-on-a-28-8-network-programming-in-age-of-empires-and-beyond).
Factorio does the same: "deterministic lockstep to synchronize clients by sending only user inputs
rather than networking the state of game objects" (https://wiki.factorio.com/Desynchronization).
GAS separates it in the *other* direction — the client predicts the occurrence locally under a
`FPredictionKey` but "the server will have the final word"
(https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Plugins/GameplayAbilities/FPredictionKey,
https://dev.epicgames.com/documentation/unreal-engine/using-gameplay-abilities-in-unreal-engine).

---

## B. The persistence line — what is durable vs transient, per system

| System | **Durable (saved/DB)** | **Transient (in-tick/frame)** | **Derived — never stored** | Mechanism cited |
|---|---|---|---|---|
| **CK3 / EU4** | flags (`set_country_flag`, 32-bit ints, optional expiry days), global variables, **story-cycle objects**, `fire_only_once` marks, scheduled `trigger_event { days = N }` | the event instance itself; `save_scope_as` scopes; scripted lists | every `trigger` predicate; MTTH weights | https://eu4.paradoxwikis.com/Event_modding · https://ck3.paradoxwikis.com/Event_modding · https://github.com/jesec/ck3-modding-wiki/blob/master/wiki_pages/Scripting.md |
| **CK3 story cycles** | the whole cycle: "Story cycles persist as savegame objects tied to characters"; carries its own variables; survives owner death via `on_owner_death` | the per-pulse `effect_group` evaluation | `chance` rolls, `first_valid` selection | https://ck3.paradoxwikis.com/Story_cycles_modding |
| **Unreal GAS** | *runtime only, not a save format*: Attributes, the Active Gameplay Effects Container, granted tags, granted abilities. Persisting across respawn is achieved by **choosing where the ASC lives** (PlayerState). No built-in savegame serialization. | `GameplayEvent` payloads, prediction keys, Instant effects (never enter the container) | GameplayCues (cosmetic, unreliable, re-derivable from effects); `CurrentValue` (= BaseValue + modifiers) | https://raw.githubusercontent.com/tranek/GASDocumentation/master/README.md · Epic GE docs · https://forums.unrealengine.com/t/can-we-save-the-state-of-the-gameplay-ability-system/212853 |
| **RimWorld** | Storyteller `ExposeData` saves exactly three things: `"def"`, `"difficulty"`, `"incidentQueue"`. The queue is deep-serialized: `Scribe_Collections.Look<QueuedIncident>(ref this.queuedIncidents, "queuedIncidents", LookMode.Deep, …)`. Each `QueuedIncident` carries `FireTick`, `TriedToFire`, `FiringIncident`, `RetryDurationTicks`. Hediffs (severity) are saved on pawns. | the per-1000-tick candidate list from `MakeIncidentsForInterval()` | **threat points** — computed on demand by `StorytellerUtility.DefaultThreatPointsNow()` from wealth curve, colonist curve, adaptation lerp, `threatScale`, `pointsFactorFromDaysPassed`, then clamped `35f..20000f`. Hediff *stages* re-derived from severity. | https://github.com/josh-m/RW-Decompile/blob/master/RimWorld/Storyteller.cs · …/IncidentQueue.cs · …/StorytellerUtility.cs |
| **Dwarf Fortress** | `historical_event` rows, forever, with `id`/`year`/`seconds72`/`type` + id references; `historical_figure`, `historical_era`. Worlds "persist as long as you like, over many games, recording historical events". Legends XML dumps run to "a gigabyte or more". | live unit/item simulation (not in legends) | narrative *text* in Legends mode — generated from the structured record at read time | https://dwarffortresswiki.org/index.php/v0.31:XML_dump · https://dwarffortresswiki.org/index.php/DF2014:Legends |
| **EVE Online** | everything: "the SQL Server database cluster … is the persistence layer of EVE Online … pretty much everything to do with the game lives here"; ~250M transactions/day. Killmails as normalized rows. | in-node combat resolution | the *rendered* killmail text (now generated per-viewer, per-language) | https://highscalability.com/eve-online-architecture/ · https://www.eveonline.com/news/view/the-killmail-mk-1.5-project |
| **WoW** | server state (not exposed) | client-side combat log ring buffer, last 5 minutes | everything in the combat log — it is a report | https://warcraft.wiki.gg/wiki/COMBAT_LOG_EVENT |
| **Bevy** | nothing. `Events<T>` is a double buffer; "Each call to update swaps buffers and clears out the oldest one"; reading after two updates "guaranteed to drop all events" | all events | — | https://docs.rs/bevy/0.9.0/bevy/ecs/event/struct.Events.html |
| **Unity DOTS** | nothing. Community pattern is "entities as events": create an entity at end of frame, consume next frame, then a system strips the components | all events | — | https://discussions.unity.com/t/designing-an-event-system-for-ecs/824936 |
| **Caves of Qud** | nothing (events are **pooled** objects: `ModPooledEvent<T>` / `ModSingletonEvent<T>`, `FromPool()` → `HandleEvent(E)` → return to pool) | all MinEvents | — | https://wiki.cavesofqud.com/wiki/Modding:Events |
| **Ink** | global variables, read counts, the story pointer, the callstack. Notably `visitCounts`/`turnIndices` are **emptied on save** "as they are not used in the related features, and to keep the save state small" | evaluation stack | — | https://videlais.com/2022/02/11/ink-unity-story-saving-and-restoring-using-json-serialization/ · https://github.com/inkle/ink/blob/master/Documentation/ink_JSON_runtime_format.md |

### B.1 The pattern across the table

Three tiers appear everywhere, with different names:

- **Tier 1 — the scheduled/pending tier.** RimWorld's `IncidentQueue`, Paradox's `trigger_event { days = N }`,
  LPMud's `call_out()`, CK3 story-cycle `effect_group { days = { 30 60 } }`. **Always durable**, because a
  pending future occurrence has no other witness.
- **Tier 2 — the standing-condition tier.** GAS active effects, RimWorld hediffs, Paradox flags/variables,
  Ink read-counts. **Durable**, because it is state, not an event.
- **Tier 3 — the in-tick signalling tier.** Bevy events, DOTS one-frame components, Qud MinEvents,
  GAS GameplayEvents, EnTT `trigger()`. **Never durable.**

And separately, orthogonal to all three: **the chronicle** (DF `historical_event`, EVE killmails, WoW
combat log). Notice it is the *only* thing in the table whose contents are append-only and whose
consumers are outside the tick loop.

**[INFERENCE]** The clean reading is: *"event" as a durable row and "event" as an in-tick signal are
different objects that happen to describe the same occurrence, and the mature systems maintain both,
with an explicit projection from the signal to the row — never the reverse.*

---

## C. How chains/cascades are bounded

Every mechanism found, named:

| System | Bounding mechanism | Detail |
|---|---|---|
| **Bevy** | **Two-frame TTL** on buffered events | Two frames (not one) specifically so out-of-order parallel systems don't miss the event; after that they are *guaranteed* dropped. https://docs.rs/bevy/0.9.0/bevy/ecs/event/struct.Events.html |
| **Bevy observers** | **Explicit propagation chain + manual stop** | `EntityEvent` bubbles up `ChildOf`, tracks `original_target`, "continu[es] until the chain reaches a dead-end or the observer handling the propagation manually stops it". Nested triggers are recursively flushed with commands. https://docs.rs/bevy/latest/bevy/ecs/event/trait.EntityEvent.html |
| **Unity DOTS** | **One-frame deferral, structurally** | Events are entities created at end of frame, consumed next frame, then stripped. Cascade depth per frame is therefore 1 by construction. https://discussions.unity.com/t/designing-an-event-system-for-ecs/824936 |
| **Caves of Qud** | **Declared cascade level** | `CascadeLevel` constants (e.g. `CASCADE_EQUIPMENT`, `CASCADE_EXCEPT_THROWN_WEAPON`) cap how far an event propagates through parts/equipment. Historically "MinEvents were restricted to only being usable within their hardcoded cascade level … mostly for performance reasons". Later relaxed to allow out-of-range registration **with an explicit ordering**. https://wiki.cavesofqud.com/wiki/Modding:Events |
| **EnTT** | **Two explicit modes** | `trigger()` = immediate, order *not guaranteed*, for urgent messages; `enqueue()` = deferred until `update()`, "dispatch events once per tick to their systems". The API forces the author to choose. https://github.com/skypjack/entt/blob/main/docs/md/signal.md |
| **Paradox (EU4/CK2/CK3)** | **Pulse scheduling + `is_triggered_only`** | MTTH originally meant every event's trigger was re-evaluated on a fixed cadence; "Not having to check all events every day would help on game performance." They moved to **pulse events** — an on_action fires a pool at a scheduled cadence — and to `is_triggered_only = yes` events that can only be reached by explicit `trigger_event`. https://eu4.paradoxwikis.com/Events · https://eu4.paradoxwikis.com/Event_modding |
| **Paradox scripting** | **Hard iteration cap** | `while` loops are "limited to 1000 iterations by default, to avoid accidental infinite loops". https://github.com/jesec/ck3-modding-wiki/blob/master/wiki_pages/Scripting.md |
| **Paradox** | **Fire-once marks** | `fire_only_once = yes` — "after this event fires, regardless of for whom it fires, it will no longer fire again for any country." A durable dedupe key. https://eu4.paradoxwikis.com/Event_modding |
| **Paradox** | **Delay as a cycle-breaker** | Chains are `country_event = { id = x days = 300 }` — putting the consequent on the *scheduler* rather than the stack breaks recursion by construction. |
| **RimWorld** | **Points budget + retry window + expiry** | Incidents are gated by a points budget derived from wealth/colonists/adaptation; queued incidents retry stochastically (`TicksGame % 833 == Rand.RangeSeeded(0, 833, FireTick)`) and are dropped at `FireTick + RetryDurationTicks`. The storyteller runs every 1000 ticks, not every tick. RW-Decompile Storyteller.cs / IncidentQueue.cs |
| **L4D AI Director** | **Target band on a derived scalar** | Intensity is estimated per survivor and the director populates to hold it *in a range* — a closed-loop controller rather than a cascade. "When difficulty goes up in L4D, the amplitude of threats doesn't increase; the frequency does." https://steamcdn-a.akamaihd.net/apps/valve/2009/ai_systems_of_l4d_mike_booth.pdf |
| **Second Life** | **Bounded queue with silent drop** | "The event queue can hold up to 64 events, and if more than 64 events are waiting, new events are discarded"; single-threaded, FIFO, no interruption; **all queues cleared on state change**. https://wiki.secondlife.com/wiki/Category:LSL_Events |
| **Skyrim Papyrus** | **Suspended-stack ceiling + dump** | Latent calls accumulate; past a threshold the VM emits a stack dump. "The number of processes the game can suspend and stack is limited, and once that limit is reached, the game will dump it." https://www.nexusmods.com/skyrimspecialedition/articles/4625 |
| **Bethesda Story Manager** | **Single-winner decision tree** | "the Story Manager works through the decision tree in order to choose a **single** quest to start"; node conditions prune whole subtrees. Fan-out is capped at the routing layer, not the handler layer. https://ck.uesp.net/wiki/SM_Event_Node |
| **LPMud** | **Fixed heartbeat + call_out** | driver "ends its cycle by calling … heart_beat() in every object with a heart_beat() set and finally performing all pending call outs" — a two-phase tick, cascades land on the next beat. https://www.mars.org/home/rob/docs/IntermediateLPC/chapter2.html |

### C.1 The taxonomy of bounds

Reduced, there are exactly **five** bounding strategies in the corpus:

1. **Time-box** — the event only lives N frames/ticks (Bevy 2, DOTS 1, LSL until dequeued).
2. **Depth-box** — an explicit declared cascade level (Qud), or a propagation chain with a stop (Bevy observers).
3. **Defer-to-scheduler** — the consequent doesn't run now, it becomes a *pending record* with a fire time
   (Paradox `days=`, RimWorld IncidentQueue, LPMud `call_out`). **This is the only one of the five that also
   survives a restart**, and it is the one every persistent-world system uses.
4. **Budget** — a scalar resource that consequents consume (RimWorld points, L4D intensity band).
5. **Dedupe/once** — `fire_only_once`, a flag, a fired-set. Cheap and durable.

**[INFERENCE]** For a DB-backed, turn-based, persistent engine, (3) and (5) are the load-bearing pair;
(1) and (2) are the intra-tick pair. A design that has only one pair has an unbounded cascade in the
other regime.

---

## D. How a "trigger" is expressed — and what each cost

| System | Trigger language | What it cost them |
|---|---|---|
| **Paradox** | A full declarative predicate DSL (PDXScript): `trigger` blocks of nested boolean scopes, `weight_multiplier`, `mean_time_to_happen` with modifiers, scripted triggers with `$PARAM$` substitution | They **did** build the scripting language and it is the reason CK3 mods exist. The cost is stated in their own docs: "Script is slower than actual game code", script values "recalculate… on every frame" in UI, `while` needs a 1000-iteration guard, and MTTH's every-N-days re-evaluation of *every* event's trigger was expensive enough to force the move to **pulse pools**. Also a scoping foot-gun the wiki calls out: "The trigger is checked before the event fires, which means that you cannot use any of the scopes created in the Immediate block" (https://ck3.paradoxwikis.com/Event_modding). |
| **Unreal GAS** | **Tag match, not a predicate language.** `GameplayTag` hierarchies + `RegisterGameplayTagEvent(tag, EGameplayTagEventType::NewOrRemoved)`; ability triggers by tag; effects carry Application/Ongoing/Removal *tag requirements* | Refusing a scripting language bought network-cheap state (tags replicate as ints) and predictability. The cost: expressiveness escapes into C++ `UGameplayEffectExecutionCalculation` ("useful for defining complex equations that aren't adequately covered by Modifiers" — Epic docs), i.e. **the DSL boundary is a cliff, not a ramp**. Also the tag-requirement design produces re-application loops (see F.4). |
| **Bethesda** | **Condition rows on tree nodes** (Creation-Kit condition list) + Papyrus for the rest. "Node Conditions are conditions for the Story Manager to check—if the conditions are not valid, the Story Manager will not process this node (or any of its child nodes)" | The tree gives cheap pruning and a *single winner*, which is exactly what a quest system wants. The cost is that anything the condition rows can't express falls to Papyrus, whose VM then becomes the bottleneck (F.2). Also a coupling wart: to read event data you "must select the event type in the Event field on the Quest Data Tab" — the handler must statically declare the event shape. https://ck.uesp.net/wiki/SM_Event_Node |
| **Valve dynamic dialog** | **Criteria table over a fact dictionary** — no language at all. Rules are (key, comparison, value) rows; the matcher picks the rule with the most satisfied criteria; ties fall back to less-specific rules | This is the cheapest-to-author and cheapest-to-evaluate design in the corpus, and Ruskin's talk was explicitly pitched at "empower your writers". Cost: it gives "a strong illusion of situational awareness" but **no goal-directed behaviour** (Emily Short's assessment). It selects; it does not plan. |
| **Yarn Spinner (saliency)** | Same shape, modern: node groups with conditions, selected by "Random Best Least Recently Seen" — highest **complexity score** (most specific conditions) wins, then least-recently-seen, then random | And it documents the trap this shape has: **a condition function that mutates state breaks selection**, because every candidate's condition is evaluated before one is chosen. The fix is to force purity in the evaluation phase and mutate only in `ContentWasSelected`. https://yarnspinner.dev/blog/saliency-and-state-mutation/ |
| **Ceptre** | **Linear logic rules.** A rule's precondition *consumes* resources from the state; "Linear logic is unique among logics in its ability to model state change and actions without the need for a frame rule". A transition is an instantiated rule; the engine enumerates all possible transitions | This is the most principled answer to "what is an event": **an event is a rule application that consumes and produces facts.** Cost: it is a research language; the enumeration of all applicable transitions is the whole engine, and that does not scale to an MMO tick without indexing. https://www.cs.cmu.edu/~cmartens/ceptre.pdf |
| **Versu** | **Praxis**, a custom logic language over *exclusion logic*, with social practices and deontic ("should") operators; utility-based agents choose among permitted actions | Richard Evans built the language and the system was cancelled by Linden Lab in 2014 (https://www.ifwiki.org/Versu, https://versu.com/about/how-versu-works/). **[INFERENCE]** I found no post-mortem stating the DSL *caused* the cancellation — treat "they built a language and regretted it" as unsupported here. |
| **EnTT / Bevy / DOTS** | **Type-based subscription.** The trigger is the C++/Rust *type* of the event | Zero expressiveness, zero cost, no data-driven authoring. Which is fine, because these are libraries, not games. |
| **RimWorld** | **Two-stage: a C# `CanFireNow` gate + a data-driven `baseChance` weight, both under a points budget.** `IncidentDef` is XML (defName, category, targetType, workerClass, baseChance); `IncidentWorker` is the code | A deliberate hybrid: the *selection* is data, the *feasibility predicate* is code. **[INFERENCE]** This is the cheapest way to avoid building a predicate DSL while keeping designers in control of frequency — and it is the design closest to what a service-oriented engine can do with a rules table + a code-side validator. |

### D.1 The one trade-off everyone paid

Every system that made triggers **data-driven** had to answer *"when is this re-evaluated?"*, and every
one of them eventually answered it the same way: **not continuously.** Paradox went MTTH → pulse.
RimWorld runs the storyteller every 1000 ticks. GAS re-evaluates tag requirements only on tag change
(delegate-driven). Bevy/DOTS evaluate once per frame. **The systems that let a predicate be evaluated
"whenever" were the ones that had a performance wall.**

---

## E. Determinism and replay

| System | Can it replay? | What it constrained |
|---|---|---|
| **Age of Empires** | Yes — "synchronous recorded games provided a way to pass around reproducible bug cases because it was guaranteed to play out the exact same way every time" | Lockstep over *commands only*, ~200 ms turn duration; every machine must run the identical simulation. https://www.gamedeveloper.com/programming/1500-archers-on-a-28-8-network-programming-in-age-of-empires-and-beyond |
| **Factorio** | Yes — "Replays are possible because results remain consistent across runs, and tests and bug reports are perfectly reproducible from initial conditions" | Every tick identical on every client. They were worried about float divergence and "surprisingly hasn't been a major problem — they implemented their own trigonometric functions". The desyncs that did bite were **ordering**, not arithmetic: "an ambiguous sort comparator where C++ STL sort behaves differently across compilers for equal elements". https://wiki.factorio.com/Desynchronization · https://factorio.com/blog/post/fff-188 |
| **RimWorld** | Partially — the *queue* is deterministic given a seed. `Rand.RangeSeeded(0, 833, queuedIncident.FireTick)` seeds the retry roll **off the record's own FireTick**, so the retry schedule is a pure function of the stored row, not of call order | **This is a technique worth stealing**: seed the RNG from a stored identifier of the record, so a re-evaluation reproduces the same roll regardless of when or how often it runs. |
| **Dwarf Fortress** | Worldgen is seed-reproducible; live fortress play is not replayed. Legends is a *record*, not a replay input. | — |
| **Unreal GAS** | **No.** Prediction is a one-way optimism with server override; and crucially "you cannot predict the removal of `GameplayEffects`" — the workaround is "adding `GameplayEffects` with the inverse effects". Periodic effects "cannot be predicted". | The asymmetry (add is predictable, remove is not) is a direct consequence of the client not owning the authoritative container. |
| **Paradox** | No public replay. Saves are snapshots with flags/variables/pending events, not logs. | — |
| **Bevy / DOTS / EnTT** | No. EnTT explicitly: `trigger()` listener "order of execution not guaranteed". | An engine that does not guarantee handler order cannot replay. |

### E.1 The transferable constraints

1. **Replay requires that the log be of *intents*, not of *outcomes*** (AoE, Factorio) — or that outcomes be
   stored so completely that no recomputation is needed (EVE, DF legends). Mixing the two gives you neither.
2. **Ordering is the real determinism risk, not floating point.** Factorio's shipped desync was a sort
   comparator. **[INFERENCE]** For a DB-backed engine, this maps directly onto: *any query that feeds the tick
   must have a total order in its ORDER BY, including a tiebreaker on a unique id.*
3. **Seed RNG from stored identity, not from a stream.** RimWorld's `Rand.RangeSeeded(0, 833, FireTick)` makes
   the roll idempotent across retries. A stream-position RNG would not survive a crash-and-resume.

---

## F. Failure modes that actually shipped

**F.1 — Corrupted Blood (WoW, 13 Sep – 8 Oct 2005): a status effect with no scope boundary.**
The debuff was intended to stay inside Zul'Gurub. It escaped because *pets* carried it: players
dismissed an infected companion, moved to a city, resummoned, and "when reactivated in densely populated
non-combat zones, still carried the debuff, becoming disease vectors, while non-player characters became
asymptomatic carriers." Blizzard could not contain it and ended it by **resetting the servers** plus a
patch stopping pets carrying it out. https://en.wikipedia.org/wiki/Corrupted_Blood_incident
→ *The status was durable and the containment predicate was positional. Durability outlived the predicate.*

**F.2 — Papyrus stack dumps (Skyrim): unbounded event fan-in into a bounded VM.**
"concentration spells can spam events dozens of times each frame, and script calls begin to accumulate
until a stack dump is generated"; and the damage is *global* — "causing other scripted mods to suffer
script lag as well", with delays "sometimes up to 5 minutes or more".
https://www.nexusmods.com/skyrimspecialedition/articles/4625 ·
https://www.nexusmods.com/skyrim/articles/52598
→ *One noisy producer degrades every consumer, because the queue is shared and unprioritised.*

**F.3 — LSL's 64-event silent drop (Second Life).**
"If the event queue is filled, it will silently drop any new events" — no warning, no error. And "when
switching states, all event queues are cleared."
https://wiki.secondlife.com/wiki/Category:LSL_Events
→ *A bounded queue is correct; a bounded queue that drops silently is a correctness bug generator. The
cap must be observable.*

**F.4 — GAS effect re-application loops.**
Tag-requirement-gated effects: when the blocking tag goes away "the `GameplayEffect` will turn on again
and reapply its modifiers", so an effect whose own consequence removes its blocking tag oscillates.
https://raw.githubusercontent.com/tranek/GASDocumentation/master/README.md
→ *This is the "adjacent decision defeats it" shape: the tag system and the effect system are each
correct; their composition is the loop.*

**F.5 — Dwarf Fortress: cats dying of alcohol poisoning.**
Chain: drinks spill → spilled liquid sticks to paws → cats clean paws → ingestion applies a **full dose**
syndrome → blood-alcohol computed by body size → cat dies (and vomits, re-seeding the chain). Toady:
he "had never thought about activating inebriation syndromes back when he was adding the cleaning stuff."
https://www.pcgamer.com/how-cats-get-drunk-in-dwarf-fortress-and-why-its-creators-havent-figured-out-time-travel-yet/ ·
https://dwarffortressbugtracker.com/view.php?id=9195
→ *No individual rule was wrong. The failure is that a generic "apply syndrome" event carried no notion
of dose scaling, and nothing in the system bounded the composition.*

**F.6 — EVE killmails: storing the rendering instead of the record.**
Covered in A.2. Truncation, lost mails, untranslatable text — all three dissolved when the record became
structured. https://www.eveonline.com/news/view/the-killmail-mk-1.5-project

**F.7 — Ultima Online's virtual ecology.**
The popular story (players ate the ecosystem) is *wrong* per Raph Koster; the system "came out of the
game for economic and performance reasons" — a closed resource loop plus the cost of "radial searches
followed by pathfinding" for every mobile's needs-driven AI.
https://www.raphkoster.com/games/snippets/did-players-destroy-the-uo-ecology/
→ *A simulation layer whose events must be computed for every entity every tick will be cut, regardless
of how good the design is.* **[INFERENCE]** The survivable version of this is event-on-demand /
lazy evaluation, which is exactly what the pulse/queue designs do.

**F.8 — MTTH's evaluation cost (Paradox).**
Not a shipped bug but a shipped *architecture change*: "Not having to check all events every day would
help on game performance," which is why pulse pools exist. https://eu4.paradoxwikis.com/Events
→ *A per-entity × per-event × per-tick predicate evaluation is O(disaster). Invert it: events subscribe
to hooks; hooks fire rarely.*

**F.9 — Yarn Spinner's state-mutation-in-condition trap.**
If evaluating a candidate's condition mutates state, later candidates see a different world, and the
selection is wrong in a way that looks like a content bug.
https://yarnspinner.dev/blog/saliency-and-state-mutation/
→ *Triggers must be pure. This is a hard architectural requirement, not a style preference.*

---

## G. The 3–5 findings that most sharply apply to "what IS an event / what do we store"

### G1. "Event" is at least **four** separate objects, and the systems that named them separately survived; the systems that used one word for two of them shipped the bugs in §F.

Concretely, the split that recurs in *every* mature system:
**(a) Intent** — a submitted, un-adjudicated request (AoE command, GAS activation request).
**(b) Pending occurrence** — a durable row with a fire-time, not yet true (RimWorld `QueuedIncident{FireTick, TriedToFire, RetryDurationTicks}`, Paradox `trigger_event{days=N}`, CK3 story-cycle `effect_group`).
**(c) In-tick signal** — a transient, pooled, depth-bounded propagation object (Bevy `Events<T>`, Qud `MinEvent` with `CascadeLevel`, GAS `GameplayEvent`).
**(d) Chronicle record** — an append-only, immutable, typed fact with stable ids (DF `historical_event{id, year, seconds72, type, hfid…}`, EVE killmail row).
*Justification:* every failure in §F is traceable to two of these four sharing one representation — Corrupted Blood gave (c)'s scope to a (b)-lifetime object; EVE stored (d) as a rendered artefact; LSL made (c) silently lossy at a boundary where callers expected (b).

### G2. **A threshold being crossed is not an event and must never be stored** — store the quantity, derive the band.

RimWorld: severity is stored, the hediff *stage* is a function of severity (https://rimworldwiki.com/wiki/Hediffs).
RimWorld: threat points are computed on demand by `DefaultThreatPointsNow()` from wealth/colonists/adaptation
curves and are *nowhere* in `Storyteller.ExposeData()`, which saves only `def`, `difficulty`, `incidentQueue`.
GAS: `CurrentValue` is BaseValue + active modifiers; only `BaseValue` is durable, and only `Instant`
effects change it.
*Justification:* a stored threshold is a cache with no invalidation story, and it is the exact thing that
goes stale when the underlying quantity is edited by any other path.

### G3. **The presentation of an event is a separate, unreliable, re-derivable object — and it must be allowed to be lost.**

GAS makes this an architectural law: GameplayCues are "a network-efficient way to manage cosmetic effects"
(Epic) and "are not guaranteed" (tranek). WoW's combat log is a 5-minute client ring buffer that Blizzard
could revoke from addons in 12.0.0 without touching a single game rule. EVE's whole killmail rewrite was
the discovery that they had inverted this.
*Justification:* for the LoreWeave engine this means the *narrative rendering of a world occurrence* (the
siege as told) is downstream of, and regenerable from, the structured record — never the record itself.
This also buys per-user localisation and per-viewer perspective for free, which is precisely the win CCP
cited.

### G4. **Chains must be bounded by two independent mechanisms — one intra-tick (depth/TTL) and one cross-tick (a durable scheduler + a dedupe key) — because they fail differently.**

Intra-tick: Bevy's 2-frame TTL, DOTS's one-frame deferral, Qud's `CascadeLevel`, Bevy observers'
propagation-with-explicit-stop, Paradox's 1000-iteration `while` cap.
Cross-tick: RimWorld's `IncidentQueue` (with a retry window *and* an expiry), Paradox's `days=` delay and
`fire_only_once`, LPMud's `call_out()`.
*Justification:* an in-memory depth budget does nothing about a consequence scheduled for next Tuesday,
and a durable queue does nothing about a handler that re-fires itself synchronously. Every system in the
corpus that survived at scale has both; §F.2/F.3 are what having only one looks like.

### G5. **A durable, queryable, typed chronicle is a legitimate causality input — but only through a query layer that is separate from the tick and provably pure.**

Valve's dynamic dialog matches "hundreds of facts about the world … against a database of thousands of
possible lines", most-specific-rule-wins. Story sifting stores simulation events in a database and matches
declarative patterns over them; incremental sifting then feeds a drama manager that nudges the world toward
completing a partially-matched story (https://eprints.soton.ac.uk/482864/1/Awash.pdf). Yarn Spinner's
saliency does the same and documents the one hard rule: **the condition evaluation phase must not mutate
state**, or selection is silently wrong.
*Justification:* this is the strongest available prior art for an engine that wants "the log is the SSOT
and the world reacts to it" without re-entering the cascade problem — because the query layer reads and
the tick layer writes, and they never interleave.

### G6 (bonus, cheap and high-value). **Seed randomness from the stored identity of the record, not from a stream.**

`Rand.RangeSeeded(0, 833, queuedIncident.FireTick)` (RW-Decompile IncidentQueue.cs) makes a retry roll a
pure function of the row. And Factorio's real desync was a **non-total sort order**, not floats.
*Justification:* both translate directly into DB-backed rules — deterministic rolls keyed on `(record_id,
purpose)`, and every tick-feeding query carrying a total ORDER BY with a unique tiebreaker.

---

## H. What I could NOT establish (honest gaps)

1. **CK3 Dev Diary #30 (event scripting) is behind a Cloudflare browser check** — I could not read
   Paradox's own first-party rationale for the CK3 event architecture. Everything I have on CK3
   internals is from the community wiki, which is high quality but second-hand.
2. **The Caves of Qud modding wiki returns 403 to my fetcher.** The `MinEvent` / `CascadeLevel` /
   pooling details in §B and §C come from a search-result extract of that page, not from a direct read.
   The specific constant names (`CASCADE_EQUIPMENT`, `CASCADE_EXCEPT_THROWN_WEAPON`) should be
   re-verified before being quoted in a design doc.
3. **Ruskin's actual GDC slide deck exceeded my fetch size limit.** The fact-database / criteria-table
   description is assembled from Game Developer's write-up, the GDC Vault abstract, and Emily Short's
   contemporaneous summary. I could **not** confirm the concrete details I most wanted: the exact
   representation of a "fact" (I believe it is a symbol→float dictionary), the rule-sorting-by-criteria-count
   optimisation, or the memory/history fact scheme. Treat those as unverified.
4. **I found no first-party statement on how DF's live simulation relates to the `historical_event` store** —
   i.e. whether the live sim ever *reads* legends. My claim that legends is downstream-only is
   **[INFERENCE]** from the fact that it is an export format and Legends is a separate mode.
5. **No post-mortem attributing Versu's cancellation to Praxis.** The brief asked specifically for
   "anyone who ended up building a scripting language and regretted it." I did not find one that says so
   in those terms. Paradox is the closest thing to the opposite case (built one, kept it, paid for it in
   evaluation cost and added a 1000-iteration guard). **I am not able to supply a sourced "we regretted
   the DSL" data point.**
6. **No GDC post-mortem specifically about event-chain explosion / infinite trigger loops.** Searches
   surfaced adjacent material (AC Unity systemic crowd events; LeBlanc on feedback loops) but nothing
   on the specific pathology. The failure-mode evidence in §F is assembled from bug trackers, wikis and
   press, not from a talk devoted to the topic.
7. **GAS savegame persistence:** I could confirm there is *no built-in* serialization of the ASC and that
   the recommended durability trick is placing the ASC on the PlayerState, but I did not find an
   authoritative Epic statement enumerating what would need to be serialised. Community forum only.
8. **DikuMUD `spec_proc`** specifically — I got LPMud's `heart_beat`/`call_out` model from a good source
   but found nothing solid on DikuMUD special procedures. The MUD row in the tables is LPMud-only.
9. **RimWorld `StorytellerComp` subclass behaviour** (how each comp weights its incident pool) was not
   read directly; only `Storyteller.cs`, `IncidentQueue.cs`, `StorytellerUtility.cs`.
