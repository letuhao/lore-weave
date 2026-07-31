# 40.9 — How a planner asks, answers itself, and knows when it is done

> **Status:** DESIGN · **Date:** 2026-07-31 · **Prefix:** `ASK-`
> **Specifies** the two `PlannerKind` methods [`40.7`](07_module_organisation.md) declared and left
> abstract — `ask()` and `open_rows()` — and adds the state machine neither had.
> **Worked entirely on `item_grade`**, the `Ladder` slot from [`40.6`](06_item_contract.md), because it
> is the hardest one: [the Fengshen corpus](../../../../services/lore-enrichment-service/tests/fixtures/fengshen/README.md)
> states outright that no such ranking exists.

---

## 0 — The question

> *"Teach the planner how to ask questions back to the user and answer itself, plus a state machine to
> answer 'is it enough yet?' — the question a game maker has to answer. Take grade as the example.
> What is a grade? How many grades should this book have? What does the user suggest? Can the planner
> suggest to the user itself? Not every book states how many grades its world has. Writing a game from
> Marvel, you are stuck: there is no grade concept, barely an item concept — Thor's hammer, the
> Infinity Gauntlet, and too little else."*

---

## 1 — `ASK-A1` — a grade is a GAME INSTRUMENT, not a fact about the fiction

Start here, because everything else follows and getting it wrong is what makes the question feel
unanswerable.

> **`ASK-A1`.** `item_grade` is not a property of the source world. It is a **partition the game
> imposes** on its item space, and it exists to do four jobs. The right question is never *"how many
> grades does this book have?"* — it is **"how many distinguishable steps does this game's item
> economy need?"**

| the job a grade does | what it costs if the count is wrong |
|---|---|
| **gate** access — cannot use/craft/obtain above your standing | too few: the gate is a wall. too many: the gate is noise |
| **compress** a continuous power axis into a small ordered set | too many and the player stops reading it |
| **pace** acquisition — grade is the unit of "I got better" | too few and progress feels flat |
| **signal** legibility — *"grade 4"* means something without reading stats | too many and the word stops meaning anything |

**This is why the Fengshen corpus saying 「寶各有用，未嘗較其次第」 is not a problem.** The novel is
telling the truth: *for a novel*, ranking treasures is pointless — the story wants each one to be
interesting, not ordered. A game needs the order for reasons the novel never had. The source is not
deficient; it is a different artifact with a different job.

So the corpus's silence is **expected and correct**, and the planner must treat it that way rather
than as a retrieval failure. This is the PO's *"I predicted the source book would not have enough
material to make a game, which is why I built the lore enrichment service."*

---

## 2 — `ASK-A2` — never ask a human for a NUMBER. Ask for the structure that determines it.

> **`ASK-A2`.** A quantitative slot is never resolved by asking *"how many?"* The planner asks the
> **structural questions whose answers determine the count**, computes the count, and presents it
> **with its derivation** for confirmation or override.

Three reasons, and the third is the one that matters here:

- **Humans are poor at absolute numbers and good at relative judgements.** *"How many item grades?"*
  has no anchor. *"Should each realm band have its own grade, or should several realms share one?"*
  has one, and anyone who has played a game can answer it.
- **A number picked from nothing is unauditable.** It cannot be reviewed, cannot be revisited when the
  ladder changes, and carries no reason. A derived number carries its inputs — change an input and the
  number moves, visibly.
- **It is what makes the planner able to answer itself.** If the count is a function of things already
  in the pool, the planner *computes* a proposal instead of guessing one. That is the whole difference
  between an assistant and a form.

### 2.1 What actually determines the number of item grades

Four inputs. The first three are in the pool or answerable; the fourth is a hard bound from outside.

| # | input | where it comes from | effect on the count |
|---|---|---|---|
| 1 | **length of the progression ladder** | `realm_tier` — already a filled slot | grades usually **cluster** realms, not mirror them |
| 2 | **whether items gate on progression at all** | a human design answer (yes / partly / no) | *no* ⇒ grade may not be needed at all |
| 3 | **how many distinct acquisition sources exist** | `acquisition` design answer — drop / craft / reward / found / bought | each source wants a band it characteristically yields |
| 4 | **legibility ceiling** | outside the pool, and it does not vary by reality | **~3 minimum, ~9 practical maximum** for a *named*, player-facing ordered set |

Input 4 is worth stating as a rule rather than a guideline, because it is the only one that is not
negotiable per project: **below 3 an ordered axis carries no information; above about 9 named tiers,
players stop distinguishing them and the names become decoration.** Games that appear to exceed it
almost always have *two* axes multiplied (a base tier × a quality roll), not one long ladder — which
is itself the right suggestion when a human asks for 20.

---

## 3 — The question ladder, worked on Fengshen

What the planner actually does for `item_grade`, in order. **Steps 1–2 need no human at all.**

**① PROBE — automatic, no human, no model judgement.**
`Ladder.probe()` runs boundary probes (`ENR-A2`): the ranking vocabulary, the ends of any ladder.
Result on this corpus: **nothing**, plus a *stated foreclosure* — the source says explicitly that no
ranking exists. That is a **stronger** result than silence and the planner must record which it got.

**② DERIVE — automatic, from the pool.**
`realm_tier` is filled. Read its arity. Read whether any filled slot already references `item_grade`.
The planner now knows the shape of the problem before asking anything.

**③ ASK — and these are the only questions a human sees.**

```
The source does not rank treasures — it says so directly (ch65: 「寶各有用，未嘗較其次第」).
That is normal: novels have no reason to order what a game has to. Three questions.

Q1  Do items gate on cultivation standing in your game?
      ( ) yes, strictly — you cannot use what you have not reached
      ( ) partly — a few landmark items gate, the rest are free
      ( ) no — items are power, standing is separate

Q2  Your reality has 9 realm tiers. Should item grades…
      ( ) mirror them 1:1                          -> 9 grades
      ( ) cluster them (about 2 realms per grade)   -> 5 grades      [suggested]
      ( ) mark only the landmarks                   -> 3 grades

Q3  Should the top grade be reachable in normal play, or is it story-only?
      ( ) reachable        ( ) story-only  -> adds 1 unreachable grade above the ladder
```

**④ COMPUTE + SUGGEST.** Answers *(partly, cluster, story-only)* ⇒ **5 + 1 = 6 grades**, and the
planner shows the arithmetic, not just the number.

**⑤ NAME — a separate question, and only now.** Cardinality first, names second. Names come from
provenance ③ if the source has any vocabulary to borrow, else rung 4 from the genre pack, else ①.
On Fengshen the source has treasure *nouns* but no ranking adjectives, so naming is largely enrichment
even though the objects are richly documented — a good illustration that **retrieval succeeding on
items does not mean it succeeds on the axis over items.**

> **Note what never happened: nobody was asked "how many grades?"** Three structural questions with
> closed answers produced the number, and the number arrived with its derivation attached.

---

## 4 — `ASK-A3` — "is it enough?" is THREE questions, and only the third is the game-maker's

Conflating them is how a pool ends up full and the game ends up broken.

> **`ASK-A3`.** A slot is sufficient only when all three hold, and they fail for different reasons and
> are found by different means.

| | sufficiency | asks | checked by | fails when |
|---|---|---|---|---|
| **S1** | **structural** | arity satisfied? order total? member fields typed? | the registry — machine, cheap | 1 grade in a `2..=16` slot |
| **S2** | **referential** | does everything pointing at this slot resolve? does everything it points at exist? | `pool_reference` — machine | an archetype references grade 6 of 5 |
| **S3** | **functional** | **does this slot do its job in the game?** | the profile's **competency questions** (`PPO-A6`) | 5 grades exist, and nothing in the world gates on any of them |

**S3 is the PO's question**, and it is the only one that cannot be answered by looking at the slot.
For `item_grade` its competency questions are concrete:

- *Given any two items, can the engine say which is better, and can the model say why in words?*
- *Does every band of the progression ladder have items available at its grade?* — the gap check
- *Is there at least one gate, anywhere in the manifest, that reads `item_grade`?* — **if not, the
  grades are decoration.** This is `PPL-A2` closure applied to a taxonomy slot rather than a variable.

A run where S1 and S2 pass and S3 fails is exactly POC-1's shape one layer up: **structurally complete,
functionally inert.**

---

## 5 — The state machine

Six states. The important ones are the two nobody designs for: `STARVED` and `REOPENED`.

```
                       ┌──────────────────────────────────────────────┐
                       │                                              │
   EMPTY ──probe──▶ PROBED ──hits──▶ PROPOSED ──approve──▶ SETTLED ───┤
                       │                 ▲    │                  │    │
                  no hits                │    └──reject/re-query─┘    │
                       ▼                 │                            │
                   STARVED ──────enrich──┘                            │
                       │                                              │
                       └──refuse-the-slot──▶ DECLINED                 │
                                                                      │
   REOPENED ◀── a new cross-module reference arrives (EPL-A8) ────────┘
       │
       └──▶ PROPOSED
```

| state | meaning | may the pool freeze? |
|---|---|---|
| `EMPTY` | registered, never touched | **no** |
| `PROBED` | searched; the query log exists (`ENR-A3`) | **no** |
| `STARVED` | searched, found nothing — *and this is a legitimate outcome, not an error* | **no** |
| `PROPOSED` | members exist, each labelled with provenance and enrichment rung | **no** |
| `SETTLED` | human-approved, S1+S2 pass | **yes**, if S3 also passes |
| `DECLINED` | the human decided this reality has no such axis — **recorded, with consequences** | **yes** |
| `REOPENED` | was `SETTLED`; a later cross-module reference demands a new member | **no** |

Three properties this buys:

- **`STARVED` is a state, not a failure.** POC-1 treated "nothing found" as an error to retry. It is
  information: it says *the source cannot answer this, move to enrichment*, and it is reached the same
  way every time.
- **`DECLINED` is reachable and legal.** A reality may genuinely have no item grades. What is forbidden
  is reaching that state *silently* — `DECLINED` records what the game gives up (§6).
- **`SETTLED` is not terminal.** `EPL-A8` guarantees reopening. A design that treats `SETTLED` as final
  freezes item's taxonomy before progression has finished demanding from it.

**"Is the pool done?"** = every slot in `{SETTLED, DECLINED}` **and** every `pool_reference` resolved
**and** the profile's CQs answerable. Three conditions, three different checks, and the third is the
one that takes a human's judgement.

---

## 6 — `ASK-A4` — the STARVED case, and Marvel is the honest test

The PO's example, and it is better than Fengshen for this because Fengshen at least has hundreds of
named treasures. A superhero source has **almost no generic item taxonomy at all**: a handful of
signature artefacts, no grades, no crafting, no drops. Retrieval will return nothing usable and the
genre pack will not help either, because the superhero genre *also* has no item-grade convention.

**A planner that produces five grades anyway has fabricated a game system out of nothing.** So
`STARVED` has three exits, tried in order, and the third one must stay available:

### ① Project an ANALOGOUS axis the source DOES populate

> The strongest move, and it is the *liaison* the LLM is actually good at: the source has no ranking
> **of items**, but it may rank **something else** that items could inherit.

A superhero source has no item grades and a very strong, universally-understood **power scale** —
street-level, city-level, planetary, cosmic. That is an ordered set with real evidence behind it. The
planner should say so:

```
No item ranking found in this source, and none in the genre pack.

But the source DOES rank power: characters are consistently described in bands
(street -> city -> planetary -> cosmic). 4 bands, cited.

Project that onto item grade?
   ( ) yes — grades inherit the power bands       -> 4 grades, provenance DERIVED-BY-ANALOGY
   ( ) no  — item grade is its own axis           -> back to Q1
```

**Provenance for a projection is its own thing** and must not masquerade as ③ CITED: the *bands* are
cited, the *projection onto items* is a design decision. Call it what it is and let a human approve it.

### ② Offer a bounded design choice with the consequences spelled out

Not *"how many?"* but three named options with what each costs, plus reference points from games the
human may know. This is `ASK-A2` with no structural input to derive from — the fallback, not the
default.

### ③ **DECLINE the slot, and say what the game loses**

> **`ASK-A4`.** A planner must be able to conclude that **this source cannot support this slot**, name
> what the game gives up, and stop. A planner that always produces something always produces slop.

```
DECLINED: item_grade — this reality has no item ranking.

What this costs, concretely:
  * no grade-gating: any actor may use any item they can obtain
  * loot tables lose their difficulty axis — a drop is a drop
  * crafting loses output tiering (item_archetype x item_grade collapses to archetype)
  * 3 competency questions become unanswerable: CQ-R4, CQ-A2, and "which of these two is better"

If that is the game you want, this is a correct answer, and some good games work this way.
```

That is a **real design outcome**, not a failure — and the Marvel case is probably where it is
*correct*. The signature artefacts are unique, story-gated and few; a grade axis over five objects is
ceremony. The right shape for that source is *unique named items with individual gates*, which is
`item_archetype` doing the work and `item_grade` declining — and the planner should be able to say so
rather than inventing an axis to fill a slot.

---

## 7 — What a suggestion must carry

The PO asked *"can the planner suggest to the user itself?"* Yes — and a suggestion is refused if it
is only a number. Four parts:

| part | `item_grade` example |
|---|---|
| **the value** | 6 grades |
| **the derivation** | 9 realm tiers, clustered 2:1 = 5, plus 1 story-only = 6 |
| **the consequence of moving it** | *down to 3:* gating gets coarse, most items feel alike · *up to 9:* each grade means less, and naming nine ranks is real authoring work |
| **a reference point** | *"most cultivation games land at 5–9; Diablo-likes use 3 base tiers × a separate quality roll rather than one long ladder"* — offered as an anchor, never as the answer |

The reference point is genre knowledge used **as a comparison the human can reject**, which is a
different act from genre knowledge used as a source (`ENR-A5` rung 4). Both are legitimate; conflating
them is not.

---

## 8 — Open

1. **Where does the legibility bound (§2.1 input 4) live?** It is not per-reality, so it is not a pool
   member; it is not engine behaviour, so it is not code. Probably a property of the **planner kind**
   — `Ladder` knows that named ordered sets have a usable range. First thing in this design that
   belongs to a *kind* rather than to a slot or a reality.
2. **Does `DECLINED` need a re-litigation path?** A human who declines `item_grade` in week one and
   wants it in week three is a normal thing. `REOPENED` handles the reference-driven case; a
   *human-driven* undecline is not specified.
3. **Who writes the consequence text in §6?** It is derived from which CQs become unanswerable and
   which references break — so it could be **computed**, not authored. That would be much better than
   a hand-written blurb per slot, and it is not obvious it is feasible.
4. **Analogy projection needs a guard.** §6① is powerful and therefore dangerous: almost any ordered
   set can be projected onto almost any other. What stops the planner projecting *faction rank* onto
   *item grade* because both happen to have five members? Probably a semantic-distance check the human
   confirms — but nothing here specifies it, and an unguarded version of this feature is a slop
   generator.
5. **Q2's cluster ratio was picked, not derived.** *"About 2 realms per grade"* came from nowhere. It
   should be measured against real games or dropped in favour of letting the human set the clustering
   directly.
