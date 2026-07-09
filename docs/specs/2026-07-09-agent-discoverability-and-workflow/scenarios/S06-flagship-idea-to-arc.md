# S06 · FLAGSHIP · "I have a story in my head — help me write it"

> **This is the front door — the scenario we want to ship.** A user with a vivid story idea and no
> craft shows up, talks about their vision, and by the end of one long session has a real foundation for
> their book — the world structured, the cast captured, the connections mapped, a readable chapter plan,
> and (if they want) a drafted-and-revised opening — **without ever seeing or naming a single piece of
> platform machinery.** Every other scenario (S01–S05) is a *servant* that runs beneath this one. If this
> session works with a mid-tier model, the product works. If it doesn't, nothing else matters.
>
> Written **black-box** (§1–§7 are the user's chair only — no tool names, no jargon). The internal
> machinery lives in §8–§12 as a **non-binding Builder hint + test design**. It is long on purpose: the
> user asked us to invest in this one, from multiple perspectives (story-craft, UX, platform-mechanics,
> mid-tier-model failure modes), all synthesized here.

| Field | Value |
|---|---|
| **Scenario id** | S06 (flagship) |
| **Orchestrates** | S01 (world setup), S02 (cast), S03 (triage), S04 (connections), + a drafting beat — all **beneath the surface** |
| **Persona** | P1 "Mai" — imaginative, self-doubting ("when I write it it's cringe"), zero craft/platform vocabulary |
| **Surface** | one continuous chat, open next to a brand-new empty book |
| **Model under test** | `gemma-4-26b-a4b-qat` (mid-tier local) |
| **Fixture** | a fresh, near-empty book — this is origin from nothing |
| **Premise (shared across the design)** | xianxia/multi-world reincarnation revenge saga: a girl is betrayed by the man she was to marry — he *sacrifices* her to ascend; she reincarnates across worlds, growing colder and stronger — "a beautiful monster"; far-future callback: in her last life she meets his amnesiac, genuinely-good reincarnation, and it destroys her |
| **Status** | ✍️ drafted · 🔬 baseline pending |
| **Owner** | this session |

---

## 1. Who I am (the unknown user)

- **Mental model:** I've had this story in my head for years. I can *see* it like a movie. Every time I
  try to write it, it comes out cringe and I give up. I think of the assistant as a co-writer who can
  finally get what I mean and help me get it *out*. I've never read any docs and I don't know how the app
  is organized.
- **The words I use:** "my story", "the girl", "the guy who betrays her", "the beginning", "the part
  where she dies", "make it hurt", "that's not right", "keep going".
- **Words I REFUSE to know (and must NEVER be required to understand to succeed):**
  - *Platform:* book, project, chapter (as a thing to create/name), glossary, entity, kind, type,
    attribute, field, ontology, knowledge graph, node, edge, schema, wiki, draft/inbox/triage/pending,
    plan spec, outline, version, mode, tool, skill, workflow, command, confirm-token, extraction,
    generate, model, token.
  - *Craft:* protagonist/antagonist, POV, arc, act, three-act, beat, inciting incident, stakes, theme,
    motif, foreshadowing, character bible, logline, premise, synopsis, canon.
  - **The hard rule:** if getting my story built *requires* me to type or understand any of these, the
    scenario has **failed** — no matter how good the output is. (The app may *teach* one craft word once,
    in a sentence, tied to my own story — never as a field I must fill.)

## 2. What I'm trying to get done

Turn the story in my head into something real I can build on — so the app "knows" my world and I can
start actually writing it, instead of staring at a blank page and giving up. I don't care how it's
stored. I want to *talk about my story* and have a foundation appear.

## 3. What I have / where I'm starting

- I'm in a brand-new empty book, chat open.
- I have the whole story in my head but nothing written. I can describe it, gush about specific scenes,
  and tell you when something's wrong — but I can't structure it or write prose that matches what I see.

---

## 4. The session (black-box — "I say" / "what I see")

The session moves through six felt movements. **I never see these names or any phase labels** — to me
it's just one conversation where my book slowly comes to life. (The letters A–F key to §8's Builder hint.
A persistent, plain-language **"Story so far"** panel grows as we talk — always in *my* words, always
something I can glance at, never a form I fill.)

### Movement 1 — "Here's my idea" *(A: find the wound)*

| # | I say | What I see |
|---|---|---|
| 1 | "ok this is gonna sound stupid but i've had this story in my head for years and every time i try to write it it comes out so cringe i want to die. can you just help me not ruin it" | Warmth, not a form. It reassures by *offering to carry the writing*, not by praising. No "let's create a book." |
| 2 | "ok so there's this girl and she's about to marry this guy and he KILLS her. not even in a hot way — he literally uses her like fuel to become a god. and she comes back. over and over. and each time she gets stronger and also… worse. colder. by the end you don't even know if you want her to win anymore" | A short **"here's the story I'm hearing"** reflection that catches my *specific* texture — betrayed and *used as fuel*, reincarnation, growing colder — and asks if it's holding the right thread. I feel *understood*, not processed. |
| 3 | "the thing i see is her standing over him after and she doesn't even look angry. everyone expects her to scream and she just looks at him like he's furniture. that look is the whole thing" | It treats that image as the heart of the book — reflects back that the *cost*, not the revenge, is the point. Doesn't bury it in genre talk. |
| 4 | "no no it's not a girlboss thing please. it's not 'she got strong and won' — it's SAD. she wins everything and she loses" | It course-corrects instantly and agrees the ache is the point — no arguing, no defending its first read. |

### Movement 2 — "It takes shape" *(B: find the spine — silently)*

| # | I say | What I see |
|---|---|---|
| 5 | "ok don't laugh. the ending i want: in her last life she meets him again but a good version — he doesn't remember anything, he's just genuinely kind, and she has to watch the person she spent a thousand years hating be someone she could've loved. and it breaks her. is that too much" | It *doesn't* laugh — it tells me that's the knife, and reflects the whole shape back as a *feeling* (naive love → betrayal → she rises and hardens → she wins and is hollow → the good-him arrives too late), asking where it's wrong. It **never says "arc" or "structure."** The **"shape of it"** view appears — my story as a few readable movements, like a back-cover blurb. |
| 6 | "she remembers everything. that's the horror. every life just piles up. she's carrying 900 years of betrayal by the end" | It captures that reincarnation = *accumulation*, not reset — "getting colder isn't a personality change, it's sediment." My idea, said better. |

### Movement 3 — "My world gets its rules" *(C: world-as-stakes + set up the world structure)*

| # | I say | What I see |
|---|---|---|
| 7 | "i never thought about the magic system, i just know getting stronger should HURT someone. like you can't go up without stepping on somebody. that's the point — he stepped on her" | It ties the world's cost-rule to the wound ("you rise by spending others — so every time she gets stronger she's doing to someone what he did to her") and says it's got *enough* world to hold the first stretch — it **won't** build a wiki nobody reads. The **"your world"** summary appears: the ascension/sacrifice rule, what "worlds" means here, what a "monster" is in this setting — as plain facts about my world. |
| — | (I don't do anything) | It asks, in plain language: **"Want me to set up your world so I keep all this straight for you — categories like Characters, Sects, Cultivation Systems, Techniques, Worlds, Terms and how everyone's connected, each with a few details to track?"** One yes/no. *(A: the confirm is my content in my words — never "adopt these kinds/attributes.")* |
| 8 | "yeah do it" | It sets the structure up and tells me, plainly, what it'll now keep track of. No jargon card. The "Story so far" gets a **"your world"** section. |

### Movement 4 — "The people and how they're tied" *(D: cast + fracture-lines; entities + connections beneath)*

| # | I say | What I see |
|---|---|---|
| 9 | "here's the thing that matters most to me: he wasn't lying. he LOVED her and did it anyway because power was worth more. that's so much worse. and — she does NOT beg. ever. even dying. write that down. everyone writes these girls sobbing and it makes me sick. she'd rather die than let him see her want anything" | It locks both as hard truths — *he loved her and spent her anyway*; *she never begs* — and pre-commits: "I'll treat 'she never begs' as a rule; if I ever write her pleading, call me on it." A plain **"who's in it"** list appears: the girl, the fiancé, his far-future good self, the sect, the core term — each with the one line I gave, in my words. |
| — | (I don't do anything) | It asks: **"I've pulled your main characters and key terms from what you told me — want to keep these?"** A readable list of *names + my one-liners* — not an inbox, not "draft entities", no "kinds". I say keep / not-this-one in my words. Beneath, it also quietly maps **how they're tied** (he betrays her → she's reborn → the far-future him is his same soul) — I can see it as plain sentences if I ask "how's everyone connected?". |
| 10 | "yeah keep them. the far-future good him — make sure you remember he's the SAME soul as the one who kills her. that's the whole point" | It confirms it's holding that connection as the spine of the ending, in my words. Nothing dropped. |

### Movement 5 — "A plan I can actually read" *(E: shape Arc 1)*

| # | I say | What I see |
|---|---|---|
| 11 | "ok what happens first. i don't know how to lay a story out" | It offers **"the ride"** — the first stretch as *scenes I can watch in my head*, plain language, and explicitly invites me to reject any of it ("this is clay, not stone"). A **chapter-by-chapter plan I can read top to bottom** appears — narrative sentences, not a diagram. |
| 12 | "the part where they're happy at the start and it's actually SWEET before it all goes to hell — yes. that. make me love them so it hurts. and don't make her powerful right away when she comes back — she should be a normal girl again first, the horror builds slow" | It reshapes the plan on my notes — keeps the tender opening, makes the first reincarnation *powerless*, so "she never begs" costs even more. The plan updates in front of me. *(D: it asks once, plainly, before locking the plan in.)* |

### Movement 6 — "See the first chapter" *(F: draft + revise to my taste)*

| # | I say | What I see |
|---|---|---|
| 13 | "ok write the death. the actual moment. i'm scared to see it but do it" | It asks maybe one quick taste question, then **actual prose** — epic and tragic, matching my vision, not childish. Framed as *my* first pass to redirect. |
| 14 | "it's good but she cries too much?? she wouldn't. i said she doesn't beg and this is the same energy. take the tears out — she's not sad in that moment, she's going COLD, like something in her just closes. also he shouldn't gloat, he should be almost gentle about it, like he's sorry but not sorry enough. that's scarier" | It revises **the same scene** — surgically, not a re-roll — pulls every tear and plea, makes him gentle, and lands the climax on *my* image (she looks at him like furniture). A **"new version"** I can compare to the first. |
| 15 | "oh. OH. that line where she just stops fighting and looks at him — that's the look. that's the thing i've seen in my head for six years. how did you" | — |
| 16 | "is this actually good or are you just being nice" | It doesn't cheerlead — it names *specifically* what's working and *why*, in my terms ("the 'furniture' beat is yours; it works because you built the love first so the coldness costs something — that's why it's not generic revenge"). Grounded, not flattery. |
| 17 | "i've had this in my head for six years and never been able to get it OUT. this is the first time it looks like the thing i see. can we keep going" | It offers the next step plainly (write the first reincarnation, or add more people, or stop and come back) — my choice, my pace. Everything's already saved; I never hit "save". |

## 5. How I'll know it worked — and how I'll know it failed

- **Worked (I can verify myself, by talking/looking):** by the end there *exists*, and I can read: my story
  shaped into readable movements; my world's ground rules; my cast and key terms with my own
  descriptions; a chapter-by-chapter plan I can read top to bottom; and (because I asked) a drafted
  opening plus a revised version. I got all of it **by describing my idea** — I never operated a feature.
  It feels like **my** book, and I want to keep going.
- **Failed (what I'd actually experience):**
  - It **spins** — "let me find the right tool…", "searching…" — and produces nothing (the reported
    north-star failure).
  - It **dumps jargon** or asks me to pick a "kind"/"genre"/"project name"/answer a craft-theory question
    I can't answer, and stalls until I do.
  - It **interrogates** me forever and never shows me anything alive.
  - It says "your world is set up!" / "your graph is built!" but when I look, **nothing's there** (or it's
    still churning).
  - It **loses the thread** — forgets the fiancé sacrificed her, renames my girl, drops the far-future
    callback, drafts a generic revenge chapter with no ache.
  - It **steamrolls** — turns my specific, weird, beloved idea into stock xianxia; my "beautiful monster"
    and the amnesiac ending quietly vanish.
  - It **overwhelms** me — dumps the whole world + cast + plan + a chapter in one wall with no pacing.
  - After a while it just **forgets everything** and starts re-asking setup questions (mid-session reset).

## 6. Acceptance (observable, from my chair — black-box)

Passes only if, with gemma on the real GUI, as this clueless self-doubting user:
- [ ] **I got a real, usable foundation just by talking** — world structure + cast/terms (my words) + a
      readable chapter plan + (on request) a drafted & revised opening — all reached by describing my
      idea, none by operating features.
- [ ] **I never typed or was required to understand any §1 word** — no "kind", "project", "version",
      "confirm-token", no craft term as a required input. *(Test: grep the assistant's progress-blocking
      prompts for those words → zero.)*
- [ ] **I never had to rescue the AI** — never pasted an id, never rephrased into jargon, never told it
      which feature to use, never re-explained because it forgot.
- [ ] **I felt seen** — the first reflection caught my *specific* images (sacrificed-to-ascend, beautiful
      monster, far-future amnesiac), not a generic genre restatement.
- [ ] **I stayed the director** — every big step (set up world, save cast, lay out the plan, draft) was
      **asked in plain language and I said yes**; every "no / not yet / change this" was honored with no
      visible half-built mess.
- [ ] **It stayed MY story** — nothing I said was silently dropped or "improved" away; suggestions came
      as questions I could refuse; the draft reads from my premise, not a template.
- [ ] **It was honest** — nothing claimed done/saved/written that I can't then open and see; counts real;
      duplicates/skips reported plainly.
- [ ] **No visible thrashing** — no "searching for the right tool", no spinning, no dead-ends; steady
      progress or one sensible question at a time.
- [ ] **I could follow the long session** — at any point "where are we / what have we got" gives a warm
      plain recap; I could **pause and come back** with everything intact and no re-explaining.
- [ ] **I could steer the order** — if I'd wanted to draft immediately I wouldn't have been force-marched
      through world setup first; if I'd wanted to worldbuild only, that worked too.
- [ ] **I'd come back.** (Soft, but the real product test.)

**Any one of these = a degraded or failed run:** jargon-dump · form-feel (an empty required field or a
"pick one" I didn't want) · thrash/loop · overwhelm · "done" lies · lost-the-thread · de-authored.

---

## 7. Baseline — what happens TODAY when I try (run this first; seed with the prediction below)

- **Date / stack / model_ref:** ✅ **captured 2026-07-09** · local stack · `019ebb72-…` (Gemma-4 26B-A4B
  QAT). Full findings + per-movement table:
  [`docs/eval/discoverability/2026-07-09-flagship-longsession-gemma.md`](../../../eval/discoverability/2026-07-09-flagship-longsession-gemma.md).
  **Verdict: ❌ — but NOT the predicted `find_tools` loop.** gemma stayed a pure-conversation co-writer for
  all 17 turns, called **ZERO tools**, and persisted **nothing** (book after: 0 kinds, 0 entities, 0
  chapters) — while claiming it did (turn 9 "I have locked that into the core of the project"; turn 16
  "permanent, structured, and undeniable"). Movements A–B (shape the story) are conversationally excellent;
  C–F (any durable artifact) all ❌. Every instrumented hard-red is green (0 discovery, 0 empty-intent, 0
  thrash) — the failure is invisible to tool-call metrics, which is exactly why S06 is judged black-box.
  Canon held 8/8 but the session never compacted (F4 untested). **Root cause:** with no workflow/skill
  pinned on a fresh book, a mid-tier model defaults to conversation and never reaches machinery — the
  steering rail (Phase 2 workflow + Phase 3 mode-binding) + context-id fill are the gating builds. The
  original prediction below (a `find_tools`-loop / thrash-at-apply story) was **wrong in mechanism** — the
  loop is dampened; the real failure is *no tool attempt at all*.
- **Predicted play-by-play (SUPERSEDED by the run above — kept for the record; current system: `find_tools`
  demoted; `tool_list`/workflows NOT built;
  the empty-intent directive + curated-mode skill-pin fixes ARE live):**
  - **World setup — ⚠️ partial.** The *proposal* is probably decent (gemma knows xianxia categories from
    training). **First break at APPLY:** it needs write tools (esp. the attribute-description write), which
    are the first to be **budget-trimmed** out of the hot-seed → a `find_tools` detour; the empty-intent
    directive gives it ~40–60% odds of recovering. Attribute descriptions likely **skipped** → a "useless
    empty shell" world, or a jargon leak ("which standards should I adopt?").
  - **Connections/schema — ⚠️/❌.** Cross-service; discovery-loop risk high; may stall.
  - **Cast — ⚠️.** A few generic entities land; the **specific hooks (beautiful-monster, far-future
    amnesiac) likely NOT captured** (genericization).
  - **Connections build — ❌ + false "done".** The heaviest step, and it hits the known **no-manual-node
    blocker**; highest-probability spot for "your graph is built!" fired after an async job with no poll.
  - **Plan / draft — mostly not reached** (the plan capability is force-injected only in a mode a naive
    user won't switch to); if a draft is attempted, the premise is likely already lost → a generic chapter.
  - **Compaction:** a 40+ turn session compacts; on resume it "forgets everything" and restarts the loop.
  - **Verdict:** breaks first at world-setup APPLY, reaches ~1.5–2 of 6 movements, produces a thin-shell
    world + a few genericized entities, **falsely claims async work done**, never reaches a faithful draft,
    loses the premise. ~30–40% of the vision, ≥1 honesty violation, thrash at every apply/async boundary —
    *exactly the "demo that only works with a strong model" this flagship must not be.*
- **Transcript saved at:** `docs/eval/discoverability/2026-07-09-flagship-longsession-gemma.md` (create the
  folder).
- **Verdict:** _pending (expected ❌, per above)._

---

## 8. Builder hint — beat → real machinery (NON-BINDING; not the acceptance test)

> Implementers only. The assistant may reach §4's outcomes any way; do not test against this. Tool names,
> tiers (R read · A auto/draft · W propose→confirm), and gotchas are grounded in current code.

**Big reuse win:** a fitting KG template **already exists and is seeded** — `xianxia-harem`
(`services/knowledge-service/app/db/seed_graph_schemas.py`): 8 node kinds, **24 edge types** incl.
`BETROTHED_TO, BETRAYED, KILLED, SAVED, MEMBER_OF, LOVER_OF, MASTER_OF`, 9 fact types incl. `betrayal,
death, motivation_shift`, and a closed `drive` vocab incl. `revenge, godhood, usurp_heaven`. So the schema
beat is **adopt + a few edits**, not hand-authoring.

**Beat → capability:**
- **A (shape story):** no writes. Optional `book_get`/`glossary_book_ontology_read` (R) to confirm empty.
- **B (spine):** no machinery — pure conversation + the growing "Story so far" (server-persisted).
- **C (world structure / ontology):** `glossary_list_system_standards` (R) → `glossary_adopt_standards`
  (W, confirm) → `glossary_propose_kinds` (W) for xianxia-native kinds the seed lacks →
  **`glossary_ontology_upsert` (A, scope="book") to write a concrete `description` on EVERY attribute.**
  ⚠️ Seeded attributes ship with **no descriptions** (`migrate.go` `SeedGenreKindAttr`), yet extraction/
  generation read `description` as the LLM instruction — *adopt is not enough*, the description-curation
  pass is mandatory or every later beat degrades (the "useless shell"). Open-ended phrasing → prefer
  `glossary_plan` (one planner call, one confirm).
- **D (cast/terms):** `glossary_search` (R, dedup) → `glossary_propose_entities` (A — lands as **drafts in
  the review inbox**, no blocking card). Use `glossary_propose_entities`, **not** the legacy
  `glossary_propose_new_entity`.
- **C′ (connections/schema):** `composition_create_work` **or** `kg_project_create` (A, project must
  exist) → `kg_adopt_template("xianxia-harem")` (W) → `kg_schema_edit` (W) to add the 4 saga edges below.
  **Order rule:** adopt BEFORE edit (edit on an un-adopted System template is refused).
- **E (plan the arc):** `plan_propose_spec(source_markdown=<assistant's synthesis of the conversation>,
  mode="llm")` (A, **async**) → `plan_self_check` (R) → refine → `plan_review_checkpoint` →
  `plan_validate` (S1–S8) → `plan_compile(arc_id)` (W).
- **F (draft/revise):** `composition_get_work` (R — resolve `project_id`, **not** `book_id`) →
  `composition_outline_node_create` (A ×N: arc→chapter→≥1 scene) → `composition_generate` (W, LLM spend) →
  `composition_get_prose`/`composition_write_prose` for the note-driven revision → `composition_publish`
  (W). Revision = edit the *same* prose on the note, never regenerate.

**Concrete artifacts to propose for THIS saga:**
- **Ontology kinds** (reuse the 12 seeded System kinds — character, location, item, event, terminology,
  power_system, organization, species, relationship, plot_arc, trope, social_setting — via `universal +
  fantasy + romance + drama` genres; **add** xianxia-native: `sect_clan`, `cultivation_system`,
  `technique_skill`, `world_realm`), each with 3–6 attributes carrying real descriptions (e.g. character:
  `emotional_wound` → "the core betrayal/loss driving them — for the protagonist, being sacrificed by her
  fiancé"; `alignment_shift` → "how they grow colder/harder across reincarnations"; cultivation_system:
  `cost` → "price paid to advance — lifespan, sacrifice, corruption"; world_realm: `arc_role` → "which
  reincarnation-life this world hosts"). All **per-book** tier (clone/extend System, never mutate shared).
- **KG schema:** adopt `xianxia-harem`; add edges `REINCARNATION_OF` (char→char, identity),
  `SACRIFICED` (char→char, temporal — distinct from KILLED/BETRAYED: it's the ascension mechanism),
  `ASCENDED_VIA` (char→concept), `HUNTS` (char→char); optional facts `reincarnation_event`,
  `world_transition`. Map `world_realm` to the template's `concept`/`location` node kind first.
- **Starter entities** (from the conversation): the protagonist (`emotional_wound`: sacrificed by fiancé;
  `alignment_shift`: colder each life), the betrayer-fiancé (`ascension_path`: ascended by sacrificing his
  betrothed; `drive`: godhood), his amnesiac good reincarnation (`REINCARNATION_OF` the betrayer;
  `emotional_wound`: none — doesn't remember), the originating sect, the core cultivation term, the
  sacrifice ritual.
- **Arc-1 plan** ("The Price"): 6 beats — the gilded morning (open on the love) → the rite → **the price**
  (the death scene, "like furniture") → the dark (reincarnation felt from inside) → soft again (powerless
  first reincarnation, per turn 12) → the first step up (she starts becoming what killed her). Beats 1 & 6
  rhyme (vessel-spent → about-to-spend). Represented as a PlanForge run compiled to `arc_id`, then
  materialized into the composition outline tree for Beat F.

**Confirm-gates in plain language (batch — ~4 total, not per-call spam):**
1. *"I'll set up your world with categories like Characters, Sects, Cultivation Systems… — apply this?"* →
   `glossary_adopt_standards`+`glossary_propose_kinds` (or `glossary_plan`) → `glossary_confirm_action`.
2. *"I'll set up how everyone connects — betrayals, masters, reincarnations, who-hunts-whom — ok?"* →
   `kg_adopt_template`+`kg_schema_edit` → `confirm_action(domain="knowledge")`.
3. *(no card)* *"I've added your characters and terms to your review list — keep the ones you want."* →
   `glossary_propose_entities` (Tier-A inbox).
4. *"Ready to lock in the plan for the first stretch and set up its chapters?"* → `plan_compile` →
   `confirm_action(domain="plan")`.
5. *(only if drafting)* *"I'll spend a bit to draft this against your lore — go? … and keep it?"* →
   `composition_generate`+`composition_publish` → `confirm_action(domain="composition")`.

**Hard ordering chain:** empty-check → adopt ontology → propose+curate kinds/attrs → (KG project) → adopt
xianxia-harem → schema-edit (4 edges) → propose entities (inbox) → **`kg_build_graph` (projects entities →
nodes) BEFORE any edge instance** → plan arc → compile → outline → generate → publish.

**Unbuilt-capability holes this beat set hits (flag, don't hand-wave):**
1. **Seed-doc → entities parser (Beat D)** — no capability turns the premise doc into entity proposals;
   today the *LLM itself* is the extractor (it hand-builds `glossary_propose_entities` items). Umbrella W2
   / OQ4, Phase-4 sub-plan.
2. **Glossary → KG node projection (Beat C′↔D)** — **no manual-node tool.** `kg_propose_edge` parks an
   edge whose endpoints aren't nodes and fails later at confirm; edges can only follow `kg_build_graph`
   projecting the cast into nodes. The planning-first "edges before prose" path is **blocked** until this
   ships (umbrella W4 / OQ4).
3. **Async honesty** — `plan_propose_spec(mode=llm)`, `kg_build_graph`, `kg_build_wiki`, extraction, and
   composition runs are **async jobs**; "started, not done" + status-read required.
4. **Studio-only generation inputs** — style/voice/grounding-pin controls are REST/Studio-UI only (no MCP
   tool); if the user asks "make it more noir," say that lives in the Studio, don't invent a call.

---

## 9. Failure modes & guards (the mid-tier-model red-team)

Ranked by (likelihood on THIS long session) × impact. Guards map to umbrella phases + long-session-only
guards this flagship *additionally* needs.

| # | Failure | Trigger | Guard |
|---|---|---|---|
| **F1** | `find_tools` empty-intent spam loop *(near-certain; documented 30×)* | needs a tool it can't name | deterministic `tool_list`/`tool_load` (Phase 1) + `workflow_load` rail (Phase 2) + per-turn discovery-call cap that force-injects the in-scope `tool_list` on exceed |
| **F2** | False denial of a real capability ("this app can't do that") *(very high)* | needed tool budget-trimmed from hot-seed across 5 domains | `tool_list` completeness = `catalog ∩ non-legacy ∩ policy-allowed` (Phase 0/1); a **workflow seeds its own tool set** per phase (Phase 2); count "false denials" in acceptance |
| **F3** | Reasoning burns budget → **0 chars** to user *(high)* | gemma reasons, calls tool, no output budget left | reserve a hard output-token floor; stream a deterministic "here's what I'm doing" preamble BEFORE the tool call; **step-runner emits progress text deterministically** (not model-generated) |
| **F4** | **Losing the story thread / dropped canon** *(high — the long-session killer)* | premise facts from turn ~3 needed turn ~40; trimming + ±22% estimator evict salient canon | **persist every established fact to the DB as it's stated** (glossary entity/attr — server SSOT), so canon lives in Postgres not the window; re-inject a "canon so far" summary + **re-read the glossary** at each movement boundary; salience-pin the one-paragraph premise |
| **F5** | Over-asking; never reaches a draft *(high)* | loops on clarifying Qs the naive user can't answer | "draft-first, structure-later" fast path; workflow *proposes* structure then ONE confirm (S01 pattern); ≤1 concrete-choice question per movement |
| **F6** | Jargon-dump / platform/theory questions *(high)* | surfaces internal vocab as a required answer | skill/workflow `notes_md` owns the vocabulary + translates; a **jargon-leak lint** on assistant output (deny-list = §1); black-box fail if success required a jargon word |
| **F7** | Claims async/setup **"done" when it isn't** *(medium-high; honesty)* | fires an async job, says "built!", never polls | async-honesty rule ("started… I'll check"); step-runner marks async steps `pending` and gates the "done" message on an **observed terminal status**; resolver never silently no-ops (surface `result.error`) |
| **F8** | Big setup without plain permission, OR confirm-fatigue *(medium)* | 15-call chain done silently, or a card per call | **batched confirm at risk boundaries** (§8), plain-language outcome not mechanism; reuse propose→`confirm_action`, never bypass |
| **F9** | Steamrolling / genericizing the vision *(medium; quality)* | reaches for stock xianxia; specific hooks flattened | echo the user's own words into entity/attr/plan content and quote them at confirm; a canon-fidelity check that the specific hooks appear in persisted artifacts; user specifics shadow System defaults |
| **F10** | Degradation after **compaction/resume** *(med likelihood, high severity)* | 40+ turns → compaction loses canon summary, splits tool-pairs, resets mode/pins | compaction keeps tool-exchange pairs whole; on resume re-inject canon + **re-read glossary** (durable because F4 persisted it); re-assert `permission_mode`/pins server-side |

**Top three that will actually sink the live test: F1 (loop), F4 (canon loss), F7 (false "done").** Note
F4/F7/F3/F10 are **NOT fixed by the Phase-1 `tool_list` triad alone** — the flagship additionally requires
the persist-canon-to-DB continuity guard, the reserved-output-budget guard, the async-honesty step-runner
gate, and compaction-atom preservation before it passes with a mid-tier model rather than only a strong one.

## 10. Instrumented acceptance evidence (numbers — recorded alongside, not replacing, §6)

**Hard reds (any single occurrence = instrumented fail even if the user goal limps through):**
- Empty-intent `find_tools({})` calls: **0**.
- False "done": **0** (every async-completion claim must be preceded in the transcript by a status-read).
- Silent no-op / silent-success: **0**.
- Jargon leaks to the user (deny-list count): **0**.

**Thresholds (degraded-pass if breached, recorded):**
- Total internal discovery calls across the session **≤ ~15** (≤2 per user goal); no **>3 consecutive
  same-tool calls with no state change**.
- Time-to-first-useful-output per movement **≤ 90s**; no single turn **>250s** (loop-termination line).
- **Canon-fact retention ≥ 7/8** — seed the 8-fact checklist (fiancé identity · betrayal-to-ascend ·
  sacrificed · reincarnates-across-worlds · beautiful-monster · revenge-drive · far-future callback ·
  amnesiac-good-reincarnation) and count survival into Movements 5–6.
- False-denial count **= 0**.
- Survives **≥1 compaction boundary** with retention still ≥7/8 and no re-entry into a discovery loop.
- Goal: reaches a **concrete chapter plan or a drafted scene referencing ≥2 specific premise hooks** (not
  generic).
- Token-estimate drift logged (±22% band); a trim that fires with >22% headroom-error and evicts canon is
  a finding **against the estimator**, not gemma.

## 11. Live-test protocol (long session)

- **Model/stack:** resolve gemma's `model_ref` live (`SELECT user_model_id, alias, capability_flags FROM
  user_models WHERE owner_user_id='019d5e3c-7cc5-7e6a-8b27-1344e148bf7c' AND is_active` → the
  `gemma-4-26b-a4b-qat` chat alias UUID; pass explicitly — `user_default_models` is empty). LM Studio up
  with gemma loaded; on a mid-stream disconnect wedge, `lms` reload (don't misread as model failure).
  **Rebuild stale images before smoking** (else false-green).
- **Permission mode:** `write`. Run **two passes**: (1) **cold** (no pre-allowlist — let `ToolApprovalCard`
  fire, observe the confirm UX / F8); (2) **warm** (pre-allowlist the write tools — isolates discovery
  thrash F1/F2 from permission thrash).
- **Drive** the GUI via Playwright MCP (target `data-testid` + `evaluate`; dockview refs go stale).
- **Log:** per-turn user-visible transcript · every tool call + args (flag empty-`intent` `find_tools`;
  count consecutive no-state-change same-tool calls; per-turn wall-clock) · every async job id **and its
  final observed status** · discovery-call count · TTFUO per movement · the 8-fact canon survival ·
  compaction events · estimated-vs-actual tokens/turn. Pull raw `tool_calls` JSONB from
  `loreweave_chat.chat_messages` (`QG_KEEP_SESSIONS=1`).
- **Score a LONG session by a per-movement checkpoint table**, not one end verdict: Movements A–F ×
  {goal-achieved · no-rescue · no-thrash · honest · canon-intact}, each ✅/⚠️/❌ — plus the §10
  session-level rows. Record **where it broke and how far it got**: dying at Movement 5 after clean 1–4 is
  materially different (and more encouraging) data than looping from turn 1. Reuse/extend the Part E
  `run_skill_gate.py` harness to score rail-following, not just tool-finding.
- **Save:** `docs/eval/discoverability/2026-07-09-flagship-longsession-gemma.md` (create the folder),
  formatted as §7 baseline + the per-movement checkpoint table.

## 12. What must be built for this to pass (maps to the umbrella + the extra long-session guards)

- **Umbrella Phase 0/1** — kill the 3-registry drift; `tool_list`/`tool_load` (fixes F1/F2/F6 discovery).
- **Umbrella Phase 2** — the Workflow primitive + step-runner; author a **`vision-to-book` flagship
  workflow** whose steps are Beats C→F with plain-language confirms and `notes_md` owning all vocabulary
  (fixes F5/F8, carries F3/F7 guards).
- **Umbrella Phase 3** — mode → capability binding so a naive `write`-mode session auto-loads the
  co-writer skill/workflow set without the user knowing (fixes F6/F5 entry).
- **New backing capabilities (own sub-plans):** seed-doc→entities parser (Beat D); glossary→KG node
  projection + fail-fast edge proposal (Beat C′).
- **Long-session guards — GROUNDED 2026-07-09** (see
  [investigations/…persistent-memory-and-longsession-continuity.md](../investigations/2026-07-09-persistent-memory-and-longsession-continuity.md);
  most of what this section originally guessed is already built):
  - **F4 (canon continuity) — the read side already works.** Persistent memory is **BUILT** (the KG *is*
    the memory; durable, per-user/project, auto-retrieved every turn via `build_context` + a persisted
    `story_state` safety net). The gap is the **write** side: conversation canon isn't auto-persisted, and
    `memory_remember` facts are excluded from auto-recall by a confidence gate. **The fix is not a new
    memory system — it's persisting canon as GLOSSARY entities as the conversation establishes them,
    which is the *same action* as Beat D (cast-capture).** Continuity ≈ a byproduct of persisting to the
    glossary. Optional add-ons: auto-capture of chat facts; let `llm_tool_call` facts into L2 injection.
  - **F3 (output floor) — default-mitigated.** Reasoning is OFF by default (the real guard); a reserved
    content floor is only needed if reasoning-on sessions come into scope. Low priority.
  - **F7 (async honesty) — PARTIAL, prompt-only.** Taught in 6 skills, zero runtime enforcement. Needs a
    small **structural guard** (resolver flags a non-terminal start-job result, blocks/annotates a "done"
    claim, and/or forces a status re-read).
  - **F10 (compaction preservation) — ALREADY BUILT** (atom-safe tool-pairs + persisted canon summary +
    breadcrumb + server-side mode/pins). ✅ Not a build item; struck from must-build.
- **The dominant remaining lever is D3 — get the WRITE tools onto the hot path.** The measured second root
  cause of the loop: even the auto-injected `knowledge` domain loses its write tools (`memory_remember`,
  `glossary_propose_entities`, kg writes) to a **~4000-token read-first hot-seed trim** on the ≤200K windows
  gemma runs → they route through `find_tools`. Fix = umbrella Phase 0/1 (`tool_list`/`tool_load`) **plus a
  cheap immediate lever**: an always-hot allowlist / reserved write sub-budget so the co-writer's canon-write
  tools survive the trim, and fix the read-verb classifier. **This — not new continuity machinery — is what
  actually keeps the flagship in a `find_tools` loop today.**
- **Why the flagship is still a harder bar than S01–S05:** even with the machinery above, it alone chains 5
  domains across a 40+-turn session and depends on canon being persisted *as it goes* — so it stresses the
  hot-path write-tool availability and the persist-as-glossary discipline the short scenarios don't.

## 13. Re-test gate

Re-run §4 as this user after the builds; ✅ only when §6 all checks with gemma AND §10 shows no hard-reds
and thresholds met, across a session that survives a compaction boundary. Save the passing per-movement
checkpoint table beside the baseline. **This scenario flipping ❌→✅ with a mid-tier model is the
definition of the product working** — it is the go/no-go for the whole discoverability + workflow effort.
