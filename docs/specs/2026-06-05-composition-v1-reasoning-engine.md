# Composition V1 — Orchestrated Reasoning Engine (design)

> **Status:** DESIGN **LOCKED** (LOOM, 2026-06-05) — research-grounded + /review-impl-hardened + PO decisions D1–D6 resolved (§9). Ready for PLAN. Deepens [`2026-06-02-composition-design.md`](2026-06-02-composition-design.md) §8.3 (autonomous loop). Does **not** restate §8.1 schema / §8.2 fork / §8.4 voice / §8.6 sweep — references them. **Research-grounded:** §1 = verified deep-research (Re3/DOC/Dramatron); §5.1/§5.2/§7 = targeted research fold (FactTrack/SCORE/ConStory/CFPG/split-softmax/DOME, 2026-06-05). **/review-impl applied (2026-06-05):** 3 HIGH (split-softmax inapplicable → §7; per-scene check cost → §5.1/§9 D1; YAGNI → §8 validate-first) + 6 MED folded; §9 D1–D6 = remaining PO cost/quality decisions.
> **Thesis (PO):** automated authoring = **orchestrated reasoning**, not free generation. A free-running LLM "authors nothing of value" because it ignores constraints (continuity, foreshadowing debts, voice, escalation). The engine's job is to make those constraints **first-class** and coordinate reasoning to satisfy them.
> **Deliverable:** a small composable **primitive set** + a **craft-method recipe library** (implement ALL common methods, as data) + a **constraint engine** (canon/KG/foreshadow), so §8.3's `Plan→[Retrieve→Draft→Critique→Revise→Commit]` becomes a real reasoning architecture rather than a single generate-then-check.

---

## §0 What this adds over the existing §8

§8 already locks the **studio mechanics**: schema (`scene_variant`/`voice_profile`/`style_profile`/`reference_source`/`generation_run`), the fork engine (branches/takes), the autonomous-loop *shape*, voice integration, the consistency sweep. This spec fills the **inside** of that shape:

| §8 has (mechanics) | This spec adds (reasoning) |
|---|---|
| §8.3 loop = `Retrieve→Draft→Critique→Revise` (one draft) | **diverge→score/converge** (N candidates, rerank) inside the loop — the empirically load-bearing step |
| §8.2 takes = author-facing N-parallel | the **same engine** used *internally* as the loop's selection primitive |
| `structure_template` = beat lists (V0) | **craft-method recipes** = beat lists **+ executable reasoning operators + constraints** |
| §8.6 sweep = post-hoc canon check | **constraint-check as a first-class loop primitive**, grounded in the external KG (the LoreWeave extension) |
| Planner drafts an outline | **decompose with top-down conditioning** + "push complexity upstream into the plan" (the strongest empirical lever) |

---

## §1 Empirical grounding (verified research, 2026-06-05 deep-research)

Three published long-form LLM narrative systems converge on the same architecture, and it **measurably beats free-running generation** on human eval. This is the backbone of the design — we are not inventing, we are adopting + extending.

- **F1 — free-running fails.** LLMs "lack long-range semantic coherence, limiting their usefulness for longform creative writing" (Dramatron, DeepMind, CHI'23, [arXiv:2209.14958](https://arxiv.org/abs/2209.14958)); still unsolved in 2024–25 (SCORE arXiv:2503.23512; ICLR'25 long-form bench). → motivates the whole engine.
- **F2 — orchestration = decompose + recursively reprompt + re-inject state.** Re3 (EMNLP'22, [arXiv:2210.06774](https://arxiv.org/abs/2210.06774)) = **Plan → Draft → Rewrite → Edit**, "repeatedly injecting contextual information from both the plan and current story state into a language model prompt." Coherence lives in the *orchestration*, not the context window.
- **F3 — coherence is enforced OUTSIDE the base model, by SELECTION.** Re3 Draft generates **N candidates**; Rewrite **reranks for plot coherence + premise relevance**. Result: **+14% coherence, +20% premise-relevance** vs same-model direct generation. → `diverge` and `score/converge` are distinct primitives.
- **F4 — constraint-check is a SEPARATE pass, downstream of selection.** Re3 Edit = "editing the best continuation for factual consistency" (contradiction-detect + correct), run *after* rerank. → `constraint-check/revise` is its own primitive; **this is the hook for our canon checker.**
- **F5 — push complexity UPSTREAM into a detailed plan.** DOC (ACL'23, [arXiv:2212.10077](https://arxiv.org/abs/2212.10077)) = detailed-outliner + controller; beats Re3 **+22.5% plot coherence, +28.2% outline relevance, +20.7% interestingness** (human pairwise). Principle: "shift creative burden from drafting to the planning stage." → tighter upstream constraints win → **structure-template/recipe-driven outline-first.**
- **F6 — hierarchical decomposition, top-down conditioning.** Dramatron: log line → title+characters → beats → locations → dialogue; each layer grounds the one below. → the **primitive-layering / recipe** approach.

**The LoreWeave extension (beyond all prior art):** every system above *self-generates* its plan/world; **none ground against an external author-defined canon / KG.** Re3's Edit (self-consistency) is the closest analog. Our `constraint-check` primitive grounds against the **real KG (entities/relations/timeline) + `canon_rules`** — that is the novel, load-bearing contribution.

> Caveats (honest): DOC numbers are pairwise win-rate *increases*, not absolute; all three pre-date frontier models (gains may shrink, but coherence is still open); none used an external canon. Research layers 1–3/5 (craft methods, reasoning frameworks, CoT/ToT/GoT) were *gathered but not adversarially verified* (harness bug, not factual refutation) — treated below as established knowledge, anchored to the fetched primary sources.

---

## §2 The spine — the human authoring loop (what we encode)

The orchestrator is a faithful encoding of how an author reasons per scene. Every step maps to a primitive (§3) and is parameterized by a craft recipe (§4) + constraints (§5).

```
1. INTENT      what must this scene accomplish?        (advance plot / reveal / pay off / escalate)
2. RECALL      what's established?                      → ground   (packer §2, V0 ✓)
3. CONSTRAIN   canon, voice, foreshadow owed, spoiler  → constraint set (§5)
4. DIVERGE     what COULD happen? (N options)          → diverge  (F3)
5. CONVERGE    which best serves intent+constraints?   → score/converge (F3 rerank)
6. DRAFT       render prose in voice                   → ground+generate (V0 stream ✓)
7. CRITIQUE    coherence / voice / pacing / canon      → constraint-check (V0 critic ✓ → hard gate)
8. REVISE/BACK fix, or backtrack to 4–5                → revise + branch-search (F4)
9. COMMIT      scene → canon-in-progress; update state → recursively re-inject (F2)
```

V0 already implements 2, 6, 7 (advisory), 9 (publish→flywheel). **V1 adds 4–5 (diverge/converge — the empirically decisive step), 1+3 as explicit structured inputs, and the 8 backtrack.**

---

## §3 The composable primitive set — ATOMICS + COMBINATORS

Pressure-test finding (§10.1): the original 7 conflated two levels — `branch-search` is not a peer primitive, it's *control flow over* diverge+score; and a primitive was **missing** (`compress`, the state re-injection F2 demands). Split cleanly:

### §3a Atomic operations (each = one model call OR one deterministic op)

| Atomic | Signature | What it is | Backed by | V0 reuse |
|---|---|---|---|---|
| **decompose** | `goal → subgoal[]` | break arc→chapter→scene→beat (top-down, higher grounds lower). *Distinct from `generate` by ROLE not mechanism (review M6): it is a structured-output `generate` whose output is the **plan tree the `pipeline` iterates** — kept separate because the whole loop is built on its result, and it runs once-per-level not once-per-unit.* | F5, F6; HTN | Planner §8.3, `outline_node` |
| **ground** | `(node, state) → context` | retrieve + assemble scoped (OI-A1) canon/recent/voice **+ the constraint set** | F2; RAG [2312.10997] | **packer §2 ✓** |
| **generate** | `context → candidate` | produce ONE option (prose / beat / take) | F2 | `/v1/llm/stream` + completion ✓ |
| **score** | `(candidate[], rubric) → ranked` | rank candidates vs intent+constraints | F3 (Re3 rerank) | critic rubric §4 |
| **check** | `(text, constraints) → violation[]` | detect violations vs canon-KG/foreshadow/voice (NLI + symbolic + judge, §5.1) | F4 + KG ext | `judge_prose` ✓ |
| **revise** | `(text, violations) → text'` | repair against violations as hard constraints | F4; Reflexion | §8.3 Revise ✓ |
| **compress** | `state → re-injectable summary` | keep the running plan+state+open-promises inside the budget for re-injection | DOME [2412.13575], RecurrentGPT [2305.13304] | *NEW* (uses KG SVO+timeline) |

### §3b Combinators (control flow over atomics — this is where "methods" live)

| Combinator | Definition | The "method" it IS |
|---|---|---|
| **diverge(k)** | `generate × k` (fan-out) | divergent thinking; N-takes (§8.2) |
| **converge** | `score → pick \| merge` | Re3 rerank; GoT aggregate [2308.09687] |
| **reflect(N)** | `loop[ check → revise ] ≤ N` | Reflexion / self-critique |
| **search** | `loop[ diverge → converge → check → (commit \| backtrack) ]` | Tree-of-Thoughts [2305.10601]; the §8.2 fork engine used *internally* |
| **pipeline** | `a ▷ b ▷ c …` (sequence, re-inject between) | the per-scene loop (§6) |

**Orthogonality + completeness (the #1 clearance):** every named technique = a combinator config over the 7 atomics — **CoT** = one `generate` at high `reasoning_effort` (V0 auto-reasoning ✓); **ToT** = `search`; **GoT** = `converge` with merge; **multi-agent debate / Six Hats** = `diverge` with role-diverse `generate` prompts + `converge`; **Plan-and-Solve / Least-to-Most** = `decompose ▷ pipeline(per-subgoal)`; **SCAMPER / lateral-thinking** = `diverge` with operator-seeded prompts. We implement **7 atomics + 5 combinators once**; we never implement CoT/ToT/GoT/debate/SCAMPER as separate features. Completeness verified by compiling every §2 loop step + every §4 craft recipe down to this set (§10.1).

**Execution substrate:** each atomic = an LLM call (or fan-out) via `loreweave_llm` SDK + gateway; `diverge` = N parallel completion jobs (§8.2); `ground`/`compress` reuse the packer + KG; auto-reasoning sets per-atomic CoT depth. No new transport.

---

## §4 The CRAFT-METHOD recipe library (implement ALL common — as DATA)

**Decision (PO): implement the full common library**, the way V0 already ships 6 `structure_template`s — as **recipes (data + small operators)**, not code. A recipe = `{ scaffold (beats/phases), operators (how to diverge/score this kind of unit), constraints it imposes, where it plugs into the loop }`. Recipes compile down to §3 primitives. Different genres/authors select different recipes; they **compose** (a structure recipe + a scene recipe + causal + payoff recipes run together).

### 4a. Structure scaffolds (macro — extend V0 `structure_template`)
Already 6 in V0 (save_the_cat / hero_journey / story_circle / kishōtenketsu / web_novel / generic). Add Freytag, 7-point, Fichtean. **Operational rule:** each = an ordered beat list with a *function* per beat (setup/catalyst/midpoint/crisis/climax/resolution). Plugs into **decompose** (arc→beats) + supplies the **intent** of each scene. (Anchor: Save the Cat / Story Circle / Hero's Journey are codified beat sheets; Kishōtenketsu = ki-shō-ten-ketsu 4-part, conflict-optional.)

### 4b. Scene engine (micro — Scene–Sequel / MRU)
**Scene** = Goal → Conflict → Disaster; **Sequel** = Reaction → Dilemma → Decision (Dwight Swain; Motivation–Reaction Units, [helpingwritersbecomeauthors.com/motivation-reaction-units](https://www.helpingwritersbecomeauthors.com/motivation-reaction-units/)). **Operational rule:** a scene-node's `diverge` is constrained to produce a goal-conflict-disaster shape; the next sequel-node must open with reaction. → parameterizes **diverge** + a **constraint-check** ("does this scene end on a disaster/value-shift?").

### 4c. Causal connective — "But / Therefore"
Beats must connect by **but** or **therefore**, never "and then" (Trey Parker/Stone, [nathanbweller.com/...but-therefore-rule](https://nathanbweller.com/creators-of-south-park-storytelling-advice-but-therefore-rule/)). **Operational rule:** a **constraint-check** over consecutive beats: the transition must be a reversal (but) or consequence (therefore). A failing transition → revise. Cheap, high-leverage logical-causality lock.

### 4d. Promise / Progress / Payoff + Chekhov bookkeeping
Sanderson's plot framework ([brandonsanderson.com 2025 plot lecture 2](https://www.brandonsanderson.com/blogs/blog/brandon-sandersons-2025-guide-to-plot-lecture-2)): every **promise** (planted setup/expectation) must show **progress** and a **payoff**; "Chekhov's gun" — planted elements must fire. **Operational rule:** a **constraint ledger** of open promises/setups (§5) — a global constraint-check that no promise is dropped and payoffs are earned. This is the foreshadowing-debt bookkeeping (failure mode §7).

### 4e. MICE quotient + try-fail cycles
Milieu / Inquiry / Character / Event threads nest like brackets — open in order, **close in reverse** (Orson Scott Card, [writingexcuses.com/16-35-the-m-i-c-e-quotient](https://writingexcuses.com/16-35-what-is-the-m-i-c-e-quotient/)). Try-fail cycles: a goal attempt yields "no, and" / "yes, but" before resolution. **Operational rule:** a **thread-nesting constraint** (a MICE thread opened must be closed, LIFO) + a try-fail **diverge** operator (attempts escalate). 

### 4f. Character GMC (a recipe) — voice/POV (a CONSTRAINT, not a recipe)
Character **Goal / Motivation / Conflict** *is* a recipe — it shapes `diverge` (options must serve the POV character's goal under their conflict). **Voice/POV consistency is NOT a recipe** (review M7): it composes to nothing on its own — it's a **constraint** (§5) fed by `voice_profile`/`style_profile` (§8.4) into `ground` (draft prompt) + `check(voice_match)`. Listed here only for cross-reference; it lives in §5, not the recipe library.

> **Recipe data model (review M8 — consistent with §10.3):** `structure_template` (V0) **stays** = the `structure` layer (drives `decompose`). A **new `craft_recipe`** table holds the OTHER layers only — `{ kind, layer: scene|causal|payoff|thread, scaffold, operators[], constraints_emitted[] }`, owner NULL = built-in, user = custom. A Work selects **1 structure_template + N craft_recipes**; the orchestrator composes them. Voice/style are NOT recipes (they're `voice_profile`/`style_profile`, §8.4). Mirrors the V0 template pattern → "implement all" = seed rows, not code paths.

---

## §5 The CONSTRAINT engine (the LoreWeave extension)

This is where we go beyond Re3/DOC/Dramatron (which only self-consistency-check). Constraints are **typed, checkable predicates** maintained in a **constraint ledger** that is re-injected into every primitive (F2) and enforced by `constraint-check`.

| Constraint type | Source | Checked by | Failure mode it guards |
|---|---|---|---|
| **Canon facts** | KG entities/relations/timeline (knowledge-service) | NLI/contradiction-detect vs retrieved facts (à la Re3 Edit) | continuity error |
| **Canon rules** | `canon_rules` (author) | rule-as-constraint in critic | author-law violation |
| **Spoiler cutoff** | two-axis story/reading order (V0 packer ✓) | grounding window + check | future-canon leak |
| **Foreshadow / promise** | promise ledger (§4d) | global payoff check | dropped setup (§7) |
| **Thread nesting** | MICE stack (§4e) | LIFO close check | unresolved thread |
| **Voice / style** | `voice_profile` / `style_profile` (§8.4) | voice_match dim | voice drift (§7) |
| **Escalation** | tension curve from structure recipe | pacing dim + monotone check | sagging middle |

### §5.1 Canon-fact check — mechanism (research-grounded, fold 2026-06-05)

Two implementable patterns from the literature, both **externalize world state** (the right call — LLMs' implicit world model is self-conflicting: only 2/9 models consistent, [arXiv:2408.07904](https://arxiv.org/html/2408.07904v1)):

- **FACTTRACK pattern** ([arXiv:2407.16347](https://arxiv.org/html/2407.16347v1)) — decompose each event into directional **pre-facts / post-facts** with **time-aware validity intervals** on the timeline; detect contradictions among overlapping facts via a **fine-tuned NLI model** (separate thresholds for *update* vs *contradiction*). LLaMA2-7B reached GPT-4-Turbo-level contradiction scoring. → **the closest match to our character-state + timeline + who-knows-what need.** Maps onto our KG (entities/relations) + the dual-order timeline (V0 already has `event_order`/`chronological_order`).
- **SCORE pattern** ([arXiv:2503.23512](https://arxiv.org/html/2503.23512v1)) — **symbolic dynamic state tracking**: each tracked item carries `state ∈ {active, lost, destroyed}`; flag a continuity error when an item is `active` after being `lost/destroyed`. Reported 98.3% item-status accuracy, 41.8% fewer hallucinations. → cheap deterministic guard for object/character status, complements the NLI check.
- **Contradiction taxonomy** — adopt the **ConStory** ([arXiv:2603.05890](https://arxiv.org/abs/2603.05890), early-2026 preprint, real but unreplicated) **5×19 class checklist** as the `constraint-check` rubric: Timeline-&-Plot-Logic · Characterization (incl. *memory* + *knowledge* = who-knows-what) · World-building · Factual-Detail · Narrative-&-Style. Errors "accumulate ~linearly with length, cluster at 40–60% position" → check density rises mid-book.

**Engine decision (→ §9 D1/D2; corrected per review M4).** We have **no fine-tuned NLI**, and "NLI via an LLM-judge" is NOT cheap. So the **cost-aware default** on the local target: (1) **SCORE-style symbolic status guard** as the deterministic, near-free PRIMARY gate on every candidate (item/character status, timeline order — pure code over the KG); (2) **LLM-judge** canon-check (ConStory taxonomy as the rubric, reusing the eval/judge infra) **only on the converged winner**, not all K candidates (review H2); (3) a trained NLI is a **V1.5 bet**, not a V1 dependency. Retrieve KG facts for the winner's entities → judge → emit violations with the span → `revise`.

### §5.2 Promise / foreshadow ledger — mechanism

- **CFPG pattern** ([arXiv:2601.07033](https://arxiv.org/abs/2601.07033), early-2026 preprint, **single-source, metrics unverified — adopt the pattern, not the numbers**) — maintain a **"foreshadow pool" of structured `(Foreshadow, Trigger, Payoff)` triples**; an eligibility module **deterministically fires triggers** (executable causal predicates) to condition the next continuation toward payoff. → this IS the promise-ledger (§4d): commit opens triples; a scene that should fire a trigger but doesn't → violation; an unpaid triple at arc-end → flagged debt.
- **Memory / re-injection (F2)** — **DOME** ([arXiv:2412.13575](https://arxiv.org/html/2412.13575v1)): a temporal-KG cache of `⟨subject, action, object, chapter_index⟩` quadruples + entity-retrieval + dynamic outline update (−15.2% conflict rate). **RecurrentGPT** ([arXiv:2305.13304](https://arxiv.org/abs/2305.13304)): human-editable natural-language long/short memory. → the `ReasoningState` re-injected each step (F2) is exactly this; we already have the temporal-KG (knowledge-service) — DOME's quadruple is our existing SVO+timeline.

> **Honest note:** the foreshadow-tracking and per-character belief-state ("who-knows-what") literature is **thin and very new** — CFPG is essentially the only explicit prior art, and no system maintains a first-class per-character knowledge/belief graph. These are **genuine gaps → LoreWeave contribution opportunities**, not solved problems we're copying.

---

## §6 Orchestration recipes (composing it all)

The per-scene loop (§8.3) becomes a recipe-driven composition of primitives. Example — **"grounded scene, Scene–Sequel + But/Therefore + payoff-aware, N=3 takes"**:

```
decompose(arc, structure_recipe)              → scene nodes w/ intent + tension target
for each scene:
  ground(node, state)                          → canon + recent + voice + open-promises
  constraints = canon ∪ canon_rules ∪ spoiler ∪ voice ∪ promises ∪ scene_shape(Scene–Sequel)
  diverge(k=3)= generate×3                       → 3 candidate beats (try-fail shaped)
  converge   = score(candidates, rubric=         → pick best
     coherence + but/therefore + escalation + voice + canon)
  generate(winner, voice)                        → prose (stream in co-write / job in auto)
  v = check(prose, constraints)                  → violations (KG contradiction, dropped promise…)
  reflect(N): loop[ check → revise ] ≤ N          → repair; still failing → search or flag human
  commit(prose) → update state (close promises, push MICE) ▷ compress  → next scene grounded richer
```

- **Co-write (V0 path):** the human is `converge` + `commit` (accept). V1 just adds the optional `diverge` (show 3 takes) + the promise-aware constraint set.
- **Autonomous (V1):** the loop runs unattended with the critic as a **hard gate** (§8.3), capped (`generation_run`), human checkpoints per chapter.
- **Backtrack:** when `reflect` fails N times, don't just stop — the `search` combinator re-enters `diverge` at this scene (or the prior one) with the violation as a new constraint. This is the §8.2 fork engine used *internally*.

---

## §7 Failure modes + mitigations (research-backed)

| Failure | Why free-gen fails | Mitigation (this design) | Source |
|---|---|---|---|
| **Long-range incoherence** | context window can't hold the book | decompose + re-inject plan+state every step; selection rerank | F2, F3 (Re3) |
| **Weak/incoherent plot** | single greedy draft | diverge→converge (rerank N) + detailed upstream outline | F3, F5 (Re3/DOC) |
| **Continuity / canon error** | model invents facts | constraint-check vs external KG (contradiction-detect) + revise | F4 + KG extension |
| **Foreshadow drop** | no memory of planted promises | `(Foreshadow,Trigger,Payoff)` triple pool (§5.2); deterministic trigger-firing + unpaid-debt flag at arc-end | CFPG [2601.07033] |
| **Voice drift** | attention to the early voice/persona prompt **decays as history grows** (split-softmax [2402.10962] diagnoses the cause) | voice_profile **re-injected every step** (F2) + `check(voice_match)` flag → `revise`. **NOTE (review H1):** split-softmax's *fix* (attention re-weighting) needs logit/attention access we DON'T have through the LM-Studio/gateway/BYOK black-box API — inapplicable here; we use it only as the diagnosis (re-inject, don't let it decay) | §8.4; voice is a **constraint** (§5), not a recipe |
| **Mid-book error spike** | contradictions accumulate ~linearly, cluster 40–60% | raise constraint-check density mid-book; symbolic status guard (SCORE) | ConStory [2603.05890]; SCORE |
| **Sagging middle** | no escalation pressure | tension curve from structure recipe as a monotone constraint | §4a/§5 |

---

## §8 Mapping to V0 + V1 milestones

**Reused from V0 (already built):** packer/`ground`, critic/`constraint-check` (advisory), auto-reasoning (CoT depth), `structure_template` (recipe seed), takes/fork schema (§8.2), publish→flywheel (commit→state).

**V1 build order — VALIDATE-FIRST (revised per review H3, YAGNI).** The cited evidence (Re3/DOC) backs only the *core* loop; the recipe library + thread ledger are intuition, not evidence. So **prove the core beats V0 on eval before building the speculative surface**:

- **Phase A — evidence-backed core (≈ Re3/DOC), measured.**
  1. **diverge→converge** in the loop (F3 — the single highest-yield addition; generalize §8.2 takes into the internal selection primitive).
  2. **check→revise vs KG** (F4 — the canon differentiator; symbolic-guard-primary, §5.1/§9).
  3. **detailed decompose** (F5 — push complexity into the outline).
  4. **Gate:** run the eval harness (KS-style) — does A beat the V0 `Retrieve→Draft→Critique` loop on coherence/canon-consistency on **our local models**? If not, stop and rethink before Phase B.
- **Phase B — composable surface (only if A wins).**
  5. **craft_recipe library** (§4) + recipe→primitive compiler — seed **ONE** recipe first (Scene–Sequel or But/Therefore), measure its marginal lift, THEN expand to the full library. "Implement all" = the *target*, reached incrementally with per-recipe eval, not big-bang.
  6. **narrative_thread ledger** (§10.2) — foreshadow/MICE; ship **advisory** first (review M5), harden to gate only if detection proves reliable.
  7. **Autonomous loop + backtrack** (§6) + **voice/style** (§8.4, prompt-reinjection only — review H1) + **consistency sweep** (§8.6, reuses check).

**Open questions — RESOLVED by targeted research (2026-06-05), folded into §5.1/§5.2/§7:**
- **#2 ✓** External-world-state grounding has real prior art: FACTTRACK (NLI + validity intervals), SCORE (symbolic item-state), StoRM/GraphPlan/NGEP (KG/event-graph conditioning), EntNet (entity-slot memory). Mechanism for §5 = FactTrack NLI + SCORE status-guard + ConStory taxonomy.
- **#4 ✓** Voice-drift = split-softmax attention re-anchoring (the one mechanistic result); foreshadow = CFPG `(F,T,P)` triple pool; memory = DOME temporal-KG cache + RecurrentGPT NL-memory.

**LoreWeave contribution opportunities (genuine literature gaps the research surfaced):**
- **Per-character belief state ("who-knows-what")** is under-served — no system maintains a first-class per-character knowledge/belief graph (knows / doesn't-know / was-told). We already have the KG + actor provenance → natural extension.
- **Long-form narrative-voice anchoring for fiction** has no mature dedicated paper (style work is dialogue-persona/TTS). Our `voice_profile` + split-softmax + voice_match is a contribution surface.
- These two are **opportunities, not blockers** — V1 ships the adopted patterns; the contributions are V1.5/V2 research bets.

---

## §9 Decisions — RESOLVED with PO (2026-06-05). Spec is LOCKED for PLAN.
Engineering #1/#4/#5 cleared (§10); review H1/M4/M6/M7/M8 folded. PO cost↔quality decisions on the **local-LLM-first** target:
- **D1 ✓** Check the **converged winner only** (not all K); SCORE symbolic guard batched on candidates. (§5.1)
- **D2 ✓** Canon-engine = **LLM-judge (eval infra) + SCORE symbolic fast-path**; trained NLI = V1.5 bet, not a V1 dep. (§5.1)
- **D3 ✓ ADAPTIVE K** — K is **derived from the scene's structural weight + tension target that `decompose` already emits**: climax/midpoint/crisis beats → high K (e.g. 3); connective/transition scenes → K=1. **No new model** — importance = the beat function + tension from the structure recipe (§4a). Budget cap (`generation_run`) clamps total K spend. Co-write surfaces K as optional takes (D3-co-write); auto uses the adaptive schedule.
- **D4 ✓** **HARD gates** (block commit) = canon-fact contradiction + spoiler-leak only. **ADVISORY** (flag + author-override) = escalation, pacing, but/therefore, **and the entire narrative_thread ledger** (PAY/DEBT detection is fuzzy, review M5). Hard gates bounded by the §10.1 backtrack budget → no deadlock.
- **D5 ✓** Recipe selection **static per-Work** for V1; per-scene override = V1.5.
- **D6 ✓** **Validate-first, eval-gated incremental library** (§8 Phase-A/B): prove the core beats V0 on eval, then expand recipes one-at-a-time with per-recipe lift measurement. "Implement all" remains the target; timing is incremental, not big-bang.

## §10 Design clearances (pressure-test, 2026-06-05)

### §10.1 #1 — primitive set is orthogonal + complete (compile test)
Restructured to **7 atomics + 5 combinators** (§3). Findings: (a) `branch-search` was a combinator (`search`), not an atomic — demoted; (b) a primitive was **missing**: `compress` (state re-injection, F2 — DOME/RecurrentGPT). Completeness shown by compiling every §2 loop step **and** every §4 craft recipe to the set: Scene–Sequel → `decompose` shape + `check`; But/Therefore → `check` over beat pairs; Promise/Payoff → `check` vs ledger + `compress` maintains it; MICE → `decompose` nesting + `check` LIFO; structure scaffold → `decompose`. No craft method needs an 8th atomic. **Backtrack budget:** `search` caps total re-entries per scene (`generation_run.cap`) so hard gates (§9.6) can't deadlock — exceed cap → flag human.

### §10.2 #4 — promise/foreshadow/MICE ledger — data model + lifecycle
**New durable table `narrative_thread`** (per-work; the §5.2/§4d ledger):
`{ id, work_id, kind: promise|foreshadow|question|mice_thread, status: open|progressing|paid|dropped, opened_at_node, payoff_node?, trigger (text/predicate), nesting_depth (mice), priority, summary }`.
**Lifecycle:** (1) **OPEN** — on `commit`, an extraction-style structured-output pass (reuse the knowledge-extraction pattern) detects new setups → insert `open` rows. (2) **PROGRESS** — a later scene references it. (3) **PAY** — a scene fires the trigger + delivers → `paid`, `payoff_node` set. (4) **DEBT** — at chapter/arc end, `open` rows that should have paid → `check` violation (foreshadow-drop §7). The **open-set is cached in `ReasoningState`** and re-injected (F2); `compress` keeps it bounded. MICE = `kind=mice_thread` with LIFO `nesting_depth` (innermost must close first). Detection reuses existing extraction infra → no new LLM pattern.

### §10.3 #5 — schema delta vs §8 (additive, §8-compatible)
| Object | Decision |
|---|---|
| `structure_template` (V0) | **keep** — it IS the `layer=structure` recipe (drives `decompose`) |
| `craft_recipe` (NEW) | other layers only (scene/causal/payoff/thread/voice); a Work selects 1 structure_template + N craft_recipes |
| `narrative_thread` (NEW) | the constraint ledger (§10.2) |
| `generation_run.state JSONB` (NEW column) | persisted `ReasoningState` for resumable auto-runs |
| canon facts / canon_rules / voice_profile / style_profile / scene_variant | **reused as-is** (KG + §8.1) — no change |

Total delta = 2 new tables + 1 column. All additive (LoreWeave invariant). No V0 migration. `craft_recipe` mirrors the `structure_template` pattern (built-in owner NULL + user rows) → "implement all common methods" = seed rows, not code.
