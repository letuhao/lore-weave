# RUN-STATE — The story seed layer (DESIGN)

> **Read this file FIRST after any compaction**, then `git log --oneline -15`, then continue.
> Never re-derive a sealed decision (§4) from memory — re-read it here.

**Started:** 2026-08-02 21:20 SEAST · **Branch:** `feat/game-logic` · **Size:** L
(files=6 logic=10 side_effects=0 — `workflow-gate.sh size L 6 10 0 55`)
**Base:** started at `50bff49a4`; **HEAD moved to `297a8bf23` at ~22:0x** — three commits from the
space-substrate peer session. Nothing this round depends on moved (verified, §6 `C-1`).

**Phase:** CLARIFY ✅ → DESIGN → REVIEW → **STOP at the PO checkpoint.** No code this round.

**Companion spec:** [`docs/specs/2026-08-02-story-seed-layer.md`](../specs/2026-08-02-story-seed-layer.md)
**Predecessor round:** [`2026-08-02-actor-substrate-RUN-STATE.md`](2026-08-02-actor-substrate-RUN-STATE.md) —
`D-1..D-121` are sealed there and are **inherited, not re-opened**. This round's ids are `SEED-D*` so the
two spaces never collide.

---

## 1. What this round is

Design the layer that makes the world **playable as a story** without the engine ever deciding what the
story is.

The PO's framing, stated across four turns and recorded verbatim in intent:

> *Roleplay with no story and no scenario is not playable. The problem is how to have story without
> forcing the outcome — a world simulator does not know what happens next, so you cannot force it. What
> we need is a **seed** for the story, not an outcome. A seed can be an origin seed, or a seed that pushes
> the plot onward. So how do we design this without it being so strict that it never fires?*

That last sentence is the round's engineering question. Everything else follows from it.

## 2. Standing invariants

1. **English in every persisted artifact** — docs, comments, commit messages, test names.
2. **No code this round.** The deliverable is a spec plus a RUN-STATE. `D-72`'s standing instruction
   applies: *do not implement yet; stub code and garbage cost a great deal to de-rot later.*
3. **`_boundaries/` is OFF LIMITS this round — the lock is held by a peer.** See §6 `B-1`.
4. **Do not touch the data-ingest tier** — no glossary-service, knowledge-service, extraction, KG.
5. **Never `git add -A`; never `--no-verify`.**
6. **Before citing any type or field as shipped, grep it in `crates/` and `services/` and require a
   non-zero, non-docs hit.** This is `DR-18`, opened after `granted`, `CausalityWaitTimeout` and
   `ModifierRow` were each cited as shipped while having zero occurrences. It binds this round hardest,
   because this round inherits heavily from a spec whose central struct does not exist in code.
7. **Do not decide a sealed question again.** §4 is the record; §5 is what is still open.

## 3. What is IN and what is OUT

| IN | OUT |
|---|---|
| The **seed** — its shape, how it applies pressure, how it ripens, how it casts roles | **Quest tracking / commitment** — the player-facing obligation and its log. A different feature (§4 `SEED-D6`). |
| The **selector** — how the engine ranks what wants to happen now | **Knowledge / who-knows-what** — a different feature, and the blocking question for it is parked (§5 `Q3`). |
| The **never-fired detector** — how a seed that can never ripen is made visible | **Dialogue content generation** — NPC_001 / NPC_002 / AIT_001 own persona and ordering. |
| The line between what the engine closes and what the author declares, per `D-2` + `D-98` | **Canon promotion (NAR L3→L2)** — `08_narrative_canon/` owns it; this round only states the boundary. |
| Where every piece attaches to the shipped-or-designed substrate, with a grep for each | Any implementation, any namespace registration (§6 `B-1`). |

## 4. Sealed decisions

Attribution is explicit throughout: **PO** = decided by the product owner in this session · **RESEARCH** =
established by measured external prior art (spec §2, with sources) · **DERIVED** = follows from an already
sealed `D-*` and is recorded so it is not re-argued.

| # | Decision | by |
|---|---|---|
| **SEED-D1** | **The missing thing is a SCENARIO/SEED layer, not a quest system.** *"Roleplay with no story and no scenario is not playable."* The `13_quests` reservation names a goal-tracking system; that is a different, smaller thing, and building it would not make the world playable. | **PO** |
| **SEED-D2** | **A seed seeds; the world decides the outcome.** A world simulator does not know what happens next, so an authored outcome is a lie the engine cannot keep. The authored artifact is the **initial condition and the tendency**, never the result. | **PO** |
| **SEED-D3** | **Two seed kinds: ORIGIN and PROPELLING.** An origin seed is the world's starting condition and fires trivially at t=0 — the never-fires problem does not exist for it. A propelling seed is the one that must fire *later*, and it is the whole difficulty. | **PO** |
| **SEED-D4** | **The acceptance criterion is NOT expressiveness — it is that a seed which can never ripen must be VISIBLE.** Over-strictness is not prevented by asking authors to be careful; it is caught by a mechanism. Per `non-vacuity.md`, a design that only *intends* not to over-constrain has no defence at all. | **PO** framing, **DERIVED** obligation |
| **SEED-D5** | **PRESSURE, NOT TRIGGER — and this is `SEED-D2` restated mechanically.** An outcome is what a trigger produces; a tendency is what a pressure produces. A trigger waits for a condition and may wait forever; a pressure *bends the world toward* the condition and can only be slow. **`SEED-D2` and `SEED-D5` are the same statement at two altitudes**, which is why the PO's requirement and the anti-starvation mechanism are one design and not two. | **DERIVED** from `SEED-D2` |
| **SEED-D6** | **The three words are three different tiers, and gathering them into one feature repeats `D-101`.** Apply the PO's own scoping test (`D-24`, *the game is playable without this feature*): remove **quest** ⇒ still a game (a lens is lost) · remove **dialogue** ⇒ **no game** — `Speak` is a `PL_005` `InteractionKind` and a `PL_001` turn kind, so it is **substrate** · remove **story** ⇒ the world is intact and the event log still holds every fact, so story is a **fold**. ⚠️ **Correction inside this row:** an earlier turn of this session applied the test to *scenario* and got *"still a game"*. That was wrong — `SEED-D1` is the PO's correction. Quest-tracking is removable; the **seed** is not, because it is the initial condition. | **DERIVED** + **PO** correction |
| **SEED-D7** | **What is genuinely unowned is KNOWLEDGE · COMMITMENT · SALIENCE.** Decomposing a quest gives seven parts and six already have owners (NPC_003 desires · `PL_005` interaction · `threshold_sets` · `statuses`→`lifecycle_machines` · RES_001 rewards · event log→NAR). A feature owning all seven is `D-99`'s `Ruleset` disease one tier up. *quest / dialog / story* are the **player-facing names for what those three mechanisms produce**. **This round builds only SALIENCE + the seed that feeds it.** | **DERIVED** |
| **SEED-D8** | **Nobody ships boolean-only gating for ambient story — four independent architectures, measured.** CK3 = **MTTH** (a mean time modifiers multiply, so the event cannot never-fire) · RimWorld = weighted lottery over colony state · L4D Director = an intensity curve with an authored **Relax** state · salience-based = most-specific-match. The only systems that gate hard are hand-authored beat systems, **and those are exactly the ones with the never-fires disease.** | **RESEARCH** |
| **SEED-D9** | **A monotone-rising term is mandatory, not optional.** RimWorld weights on *"how long since the last major event"* · CK3's MTTH is itself such a clock · Glass negatively weights already-used paths so the story cannot stall · **Tale of Immortal puts it inside the condition** — 大能传功奇遇 fires *"within 5 years of **not** having reached Crystal Formation"*, i.e. **it fires because the player is behind**. Four arrivals ⇒ `D-42` says structural, not stylistic. | **RESEARCH** |
| **SEED-D10** | **A seed NEVER names an instance; it declares ROLES and the engine casts at ripen time.** This kills the single worst failure mode in an emergent world — a seed naming an NPC who died in turn 3 is dead forever. Wildermyth declares **targets** (`Party`, `HERO`, `overlandTile`, `site`, `foes`, `npcId`) filtered on traits/relationships/hooks/stats with a `notAlreadyMatchedAs` clause; **roles are matched in declared order, most critical first, because later picks degrade into *"wishy-washy"* fits**; a role may be mandatory with a score threshold, and the story simply does not fire if the cast cannot be filled. Starfreighter binds the chosen entity **into the narration** as well as the condition. | **RESEARCH** |
| **SEED-D11** | **Tension must be able to FALL, and this is now an external arrival at `C-0`.** L4D writes **Relax** into the state machine; RimWorld eases off when the player is losing. `D-119` reached the same place from inside the corpus (*a pressure that only rises is a divergent series with no sink*). ⇒ the seed layer **requires the signed arrow**; `O-107`/`C-0` is a prerequisite, not an enrichment. | **RESEARCH** confirming **DERIVED** |
| **SEED-D12** | **Broad defaults, never uniform coverage.** *"It is relatively easy to build a rudimentary set of content with sensible broad defaults, then gradually add more salient content for individual situations. **You are never committed to having uniform coverage.**"* ⇒ the floor of this system is not *nothing happens*; it is the narrator improvising over the top-ranked pressures with **no state change**. Over-strictness degrades to **flavour**, not to **silence**. | **RESEARCH** |
| **SEED-D13** | **Symbolic conditions in the STATE path; the LLM only in the NARRATION path.** Drama Llama (2025) proves natural-language preconditions evaluated by an LLM are authorable and pleasant — and they are **non-deterministic**, so they cannot sit anywhere `D-36` requires a fold from the log. Its own authors report the cost: excessive effort on *"trigger consistency"*, with cooldowns and ordering constraints proposed as future work. **We take the authoring lesson and refuse the mechanism.** | **RESEARCH** + **DERIVED** from `D-36` |
| **SEED-D14** | **Rank, do not first-match — and the reason is observability, not quality.** Drama Llama fires the first trigger whose condition holds, ordered by the author. First-match produces **no number**, so `SEED-D4`'s detector would have no subject. Ranking makes *"seed S has never entered the top-K in N ticks"* a **measurable**, which is the only reason the acceptance criterion can be met at all. | **DERIVED** from `SEED-D4` |
| **SEED-D15** | **Rank by SPECIFICITY first; an authored weight only breaks ties.** Specificity is *counted*, not tuned, which removes the *"a soup of magic numbers nobody can tune"* risk this round opened against itself. Where CK3 and RimWorld use authored weights, salience-based systems use specificity and self-tune. | **RESEARCH** |
| **SEED-D16** | **A seed's `on_ripe` is a STATUS, never an outcome — which is what makes `SEED-D2` mechanical rather than a promise.** A seed may say *"succession instability is now high"*; it may **not** say *"the king dies."* `D-83` carries the rest: status → `TransitionDecl.trigger = OnStatus` → lifecycle transition → cascade. **The engine's existing lifecycle machine is also the guardrail against salience's one documented disease** — *The King of Chicago* could *"accidentally satisfy preconditions for unintended endings"*, and the defence is that only an **author-declared transition** can make anything irreversible. | **DERIVED** from `D-83` + **RESEARCH** |
| **SEED-D17** | **The never-fired detector is GENUINELY NEW WORK, not a port — stated so nobody later assumes it exists.** Searched specifically: Emily Short's practical storylet guidance offers **no tooling guidance**; Kreminski's survey covers authoring burden and **not** unreachability; Drama Llama **acknowledges it as an unaddressed limitation**. Three sources, no prior art. It is also the piece that makes this design pass `NV-1..6`, so it is not optional. | **RESEARCH** |
| **SEED-D18** | **Tale of Immortal answers `SEED-D3` most precisely, and its lesson is where the seed is RE-ISSUED.** Nature Destiny (3, chosen at character creation) = the origin seed · **Rewrite Destiny, chosen 1-of-6 at every major-realm breakthrough** = the propelling seed · Nurture Destiny (from quests/events) = short-lived pressure. **The propelling seed is re-issued at a PROGRESSION THRESHOLD, not at a story checkpoint** ⇒ narrative pacing rides on character progression, which this project already has (`threshold → status`), so **no separate story scheduler is needed**. And a Destiny is a **bundle of modifiers, not a plot** — it changes what is likely, never what happens: `SEED-D2` shipped in a real game. NPCs carry Rewrite Destinies too, which under `D-93` (a World **is** a locus-actor) means seeding the world and seeding an NPC are **one mechanism on different subjects**. ⚠️ **Confidence: MEDIUM** — the fandom Destiny page returned HTTP 402 and the Steam patch note yielded no body; this rests on search summaries and encounter guides. **Re-measure before any of it becomes load-bearing.** | **RESEARCH** |

### 4b. Added after the peer-session sweep — 2026-08-02 22:0x

| # | Decision | by |
|---|---|---|
| **SEED-D19** | **A ripening event refs the THRESHOLD CROSSING; the *why* comes from the pressure's PROVENANCE, never from an enumeration of causes.** A ripening seed is mechanically an `EVT-T5 Generated` — which is what `Scheduled:QuestTrigger` was reserved as — and `EVT-A6`+`EVT-L14` make causal-refs **required on `EVT-T5`, capped at 64**. **A pressure-driven ripening has no small enumerable cause set**; it is an integral over N ticks and an unbounded number of contributing rows. Referencing every contributor blows the cap and pays forever; referencing only the crossing is true but uninformative. **The third option is right and `D-46` already argued it** for the neighbouring problem (*"stamping a 32-byte digest on every event pays forever for a question the registry answers once"*): `ModifierRow.source` plus `D-28`'s same-commit rule already answer *"why is this pressure here"* **structurally**. ⇒ **causation by provenance, not by enumeration.** ⚠️ `ModifierRow` = 0 occurrences (`D-111`), so this rests on a drawing like everything else in spec §1. | **DERIVED** from `D-46`+`D-28`, prompted by the peer's `E-18` |

**Why this is worth a row rather than a footnote:** the event-model session recorded `EVT-A6`/`EVT-L14` as
*"contested rather than refuted"* and wrote **"the cost side was never weighed here. Weigh it before
re-locking."** The seed layer **is** that weight — the first designed consumer of `EVT-T5` whose causation
is an accumulation rather than an event. **Going second is a load test for the tier beneath**, which is
`D-66` for going first, arriving from the other end. This round offers the finding to that folder's owner
and **does not edit it** (§6 `C-1`).

## 5. Open — the spec must answer these

| # | Question |
|---|---|
| **Q1** | The seed's exact shape, field by field, with `D-27`'s test applied to each: does the engine fold this row without learning any word from the fiction? |
| **Q2** | Where the pressure is stored. `D-93` says a world-scoped quantity is an ordinary quantity on the World locus-actor — but `QTY-A6` caps a reality at **32 quantities total**, shared with hp/mana/qi/everything. Six narrative pressures is 19 % of the budget. **This is `O-97`'s width question arriving from a new direction and the spec must say so rather than spend the budget quietly.** |
| **Q3** | Whether an NPC may know something the player has told nobody. Parked from an earlier turn — **it no longer blocks the seed model** (which works under either answer) and it decides only whether knowledge is a real system. It belongs to the knowledge round. |
| **Q4** | What the closed **output vocabulary** of a ripened seed is. Wildermyth's is enumerated and mechanically simple; ours must be too, or `D-27` (*a contribution is data, never code*) is violated at the moment of ripening. |
| **Q5** | Cooldown / re-arming: `SEED-D9`'s monotone term makes seeds fire, and something must stop the same seed firing forever. §6 of the actor spec already declares hysteresis (distinct enter/exit values, coalescing in a window). Does it suffice unchanged? |
| **Q6** | Does the seed layer need `C-0` (the signed arrow) *before* it can be specified, or only before it can be built? `SEED-D11` says it is a prerequisite; the spec must state which kind. |

## 6. Blocked / parked

| # | Item | Why, and the trigger that clears it |
|---|---|---|
| **B-1** | **Namespace registration — the whole promotion checklist of [`00_V2_RESERVATION.md`](../03_planning/LLM_MMO_RPG/features/13_quests/00_V2_RESERVATION.md) §9** (catalog file · `01_feature_ownership_matrix.md` prefix row · `02_extension_contracts.md` namespace · promoting the reservation). | **Two conditions; the first has cleared, the second has not.** ① *(cleared 21:30)* `_boundaries/_LOCK.md` was held by the space-substrate (`SDF-*`) session, claimed ~21:1x and **released by 21:30 — `Owner: None`**. It was live when this round started, and the only reason that was noticed is that the file was read before being edited; the folder's history records **four** occasions of an agent editing it unlocked. ② **STILL BLOCKING — the prefix is not mine to choose.** `SEED-D1`/`SEED-D6` say this layer is **not** the quest feature, so claiming `QST-*` for it would register a name against the wrong concept and become rot on the day someone designs commitment. **A free mutex is not permission to decide what a feature is called.** **Trigger:** the PO names the prefix. Until then the spec lives in `docs/specs/`, exactly as the actor round's did, and registers nothing. |
| **B-2** | Re-measuring the Tale of Immortal destiny model (`SEED-D18`). | Two primary sources were unreachable (HTTP 402 / empty body). **Trigger:** the moment any `SEED-D*` depends on a ToI detail rather than merely being corroborated by one. |
| **C-1** | **CONCURRENCY — `07_event_model/` is being rewritten by a third session, live, in the working tree.** 8 files modified and uncommitted at 22:0x; they are **not** in the space-substrate session's release note, so this is a different writer. | **Checked, not assumed:** all four items this round cites survive unchanged in the working copy — `Scheduled:QuestTrigger` (3 hits) · `QuestOutcome` (4) · `EVT-T9 QuestBeat` withdrawn (1) · `BubbleUp:RumorBubble` (1). **This round edited nothing in that folder** and cites its findings read-only. ⚠️ `_LOCK.md` governs `_boundaries/` **content** and says nothing about this folder or about git's index — the hazard it already records (*"pathspec protects the peer from us; nothing protects us from the peer"*). **Re-verify these four before committing.** ⚠️ **The tree is RED right now and it is not this round's doing:** `design-lint` went OK → **FAIL, 10 findings, all `unregistered-prefix: EV-*` in `07_event_model/`** — the peer introduced an `EV-*` id space not yet in the id catalog. **Not ours to fix** (registering another session's prefix while they are mid-edit is the scope creep `_LOCK.md` exists to prevent); they will hit it at their own commit, which is the gate working. ~~**Consequence for us: this round cannot commit until that clears.**~~ ⚠️ **WRONG, corrected 22:3x — see `C-2`.** |
| **C-2** | 🔴 **THE INDEX ALREADY HOLDS 26 FILES FROM OTHER SESSIONS — this is the real hazard, and it is live.** Staging this round's two files showed **28** staged, not 2: an **item-substrate** session (`docs/specs/2026-08-02-item-data-structure.md`, `-item-dataflow.md`, its RUN-STATE, `PL_007*`) plus `CLAUDE.md`, three `crates/game-rules/` sources and 20 planning docs were **already staged before this round touched anything**. | **This is the incident `_LOCK.md` records verbatim:** *"git's **index, a shared resource with no mutex**, was swept wholesale: 23 files of this arc went in under a `sim-core` subject."* A bare `git commit` from this session would author **26 files of other people's work** under a story-seed subject. **Mechanism, not care:** commit by explicit pathspec in the same shell breath as the `add`, and re-read `git diff --cached --name-only` immediately before committing. This round staged 2, tested, and **restored the index to the 26 it found** — verified by count, not assumed. |
| **C-3** | ⚠️ **CORRECTION — `C-1` claimed this round could not commit while `design-lint` was red. That was wrong, by inference rather than measurement.** | The hook runs `design-lint.py **--staged --warn-check symbol**`, and **two independent reasons** make the peer's `EV-*` findings non-blocking: ① `--staged` examines staged files only, and the peer's `07_event_model/` edits are **unstaged**; ② `unregistered-prefix` belongs to the `symbol` check (`design-lint.py:84`), which the hook declares **warn-only**. **Measured, not reasoned:** the real `.githooks/pre-commit` was run end to end with this round's files staged — **exit code 0**, `design-lint: OK — no findings`. **The tell I missed:** I read a full-corpus run and reported it as the commit gate, without opening the hook line that invokes it — the same *read the table instead of the target* shape as `DR-17` and `SEED-DR-5`, now three times in one session. |

## 7. Slice board — `[ ]` todo · `[~]` in flight · `[x]` done (needs evidence) · `P` parked

| # | Slice | Done when |
|---|---|---|
| `[x]` **S0** | CLARIFY — the PO's framing, and the tree measured before designing | 4 turns; `13_quests` = reservation only, `08_narrative_canon`/`09_emergent` = index only, dialogue has no home folder, event model already split QuestBeat into T5+T1, code ≈ 0 (`quest.epic_started` is a **test fixture** in `world_kv`) |
| `[x]` **S1** | Prior-art measurement | 9 systems, sources recorded in spec §2; 4 convergences, 3 divergences, 1 gap nobody fills |
| `[x]` **S2** | This RUN-STATE | written; `SEED-D1..D18` sealed with attribution |
| `[x]` **S3** | The spec — [`2026-08-02-story-seed-layer.md`](../specs/2026-08-02-story-seed-layer.md) | `Q1`–`Q6` all answered (none escalated); `SEED-A1..A7` written for the red team; 9 sources. Invariant 6 applied to every cited type — **3 new docs-only findings** (`ActorKind` 0 code / 23 docs · `TierCapacityCaps` 0 code / 15 docs · `granted` = 1 doc-comment inside the `D-35` stub) |
| `[x]` **S4** | 2-stage self-review | **3 findings, all fixed in place, none deferred.** Stage 1 (spec compliance): the origin seed was named and then not specified — the PO's sentence says *"and no scenario"*, so §3.1 now splits situation (mechanism) from premise (narration, state-free). Stage 2 (quality): `SEED-DR-4` the phantom `size_of` gate · `SEED-DR-5` the over-claimed cascade chain, whose correction added the reward boundary `SEED-A7`. Gates: `amendment-rot` OK (380 docs) · `design-lint` OK · `deferral-gate` OK (5/23 mechanised) · Vietnamese-diacritic scan **0** in both new files |
| `[ ]` **S5** | PO checkpoint | design presented, PO signs off or redirects. **STOP HERE — nothing committed.** |
| `P` **S6** | Namespace registration | blocked on `B-1` |

## 8. Drift log — record the near-misses, because a clean drift log is a dishonest one

| # | Drift |
|---|---|
| **SEED-DR-1** | I applied `D-24`'s scoping test to *scenario* and concluded *"remove it and there is still a game"*, in the same turn I was using that test to police other people's scope. **The PO reversed it in one sentence** — *roleplay with no story and no scenario is not playable*. The tell I missed: I tested the **quest log** and reported the verdict for the **seed**, which are the two ends of `SEED-D6`. Sealed as the correction inside that row rather than quietly fixed. |
| **SEED-DR-2** | I opened this round intending to run the `13_quests` §9 promotion checklist, and **only discovered the boundary lock was held by a live peer session because I read the file before editing it.** Had I trusted the checklist and started editing, this would have been the fifth unlocked `_boundaries/` edit in the folder's recorded history — the one class of defect this repo has documented most and repeated most. The habit that saved it is the one `_LOCK.md` itself names four times: **open the target before acting on the table.** |
| **SEED-DR-3** | My first message this session offered the PO four architecture questions to choose between. They answered *"I don't know how to answer those accurately"* — correctly, because **two of the four were questions only the corpus could answer** and I had the corpus. Asking the PO to choose between salience and branching graphs was outsourcing a decision I was better placed to make; the useful question, which came later, was one sentence long and about how the game should **feel**. |
| **SEED-DR-4** | **I wrote `size_of::<ActorQuantities>()` as an operative gate — in the spec whose §1 exists to catch exactly that.** Caught in my own stage-2 review, not by anyone else, but it went in on the first draft *after* I had written three paragraphs about `granted`, `ModifierRow` and `ActorKind` being drawings. **Knowing the failure mode did not prevent committing it**, which is `non-vacuity.md`'s *intent is not a mechanism* observed on myself, one section after quoting it. The only thing that caught it was re-running the grep during review rather than trusting the paragraph I had just written. |
| **SEED-DR-5** | **I claimed `D-83`'s chain *"turns a status into every downstream consequence"*.** It does not — the cascade policy set is `Drop \| Cascade \| Suspend \| Keep`, which moves **held entities**, not rewards. The sentence was doing rhetorical work (making the one-variant output vocabulary sound costless) and I did not open `EF_001` before writing it. Same shape as `DR-17`: **I checked that a name was used consistently rather than what the thing actually does.** The correction improved the design — it forced the reward boundary to be stated (`SEED-A7`) instead of assumed. |
