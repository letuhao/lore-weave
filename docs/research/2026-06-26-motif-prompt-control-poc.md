# POC — Motif/Arc Prompt-Control Feasibility (weak local model)

> **Date:** 2026-06-26 · **For:** [`docs/specs/2026-06-26-narrative-motif-library.md`](../specs/2026-06-26-narrative-motif-library.md) (feasibility gate before BUILD).
> **Question:** does injecting an **abstract arc template** (roles + ordered beats + pre/effect + tension) let a deliberately **weak local model** PLAN structurally and COMPOSE on-beat — and does the structure **transfer across a re-skin** (setting + cast + **gender** changed) without leaking the source (the copyright + "Lego-block reuse" claim)?
> **Model:** `google/gemma-4-26b-a4b-qat` via LM Studio (OpenAI-compatible, `localhost:1234`). A **4B-active** MoE (26B total) — intentionally weak, the "self-host planner" class the whole feature targets.
> **POC script:** `scratchpad/poc_motif_control.py` (throwaway). **NB:** it calls LM Studio **directly** — that is a feasibility probe only; the real planner MUST resolve the model via **provider-registry** (BYOK credential + `user_models` row), per the ENFORCED provider invariant. Do NOT copy the direct-call pattern into service code.

---

## §0 Verdict — **FEASIBLE.** ✅

A 4B-active local model, given the abstract arc template, produced a **structurally tight, correctly-bound, faithfully-re-skinned 5-chapter plan** (all 5 beats in order, tension T2→T5 rising, roles bound to the supplied cast, zero source-genre leakage, female lead) **in ~7s** — and an on-beat scene. With **thinking enabled** (the PO-requested planner config), the model **explicitly verifies pre/effect per beat, checks the constraints, and self-corrects** against the template. The control layer is the difference between *a one-off the model happened to make* and *a bindable, verifiable, reusable plan*.

---

## §1 Setup

**The control (an abstract arc template — the "data architecture as a prompt"):** the classic *rise-from-humiliation / three-year-pact* revenge-cultivation arc, **abstracted** (NOT copied) to:
- **roles** (Greimas actants): protagonist / mentor / rival / ally
- **5 ordered beats** (Propp-style), each with **tension 1-5 + precondition + effect** (plot-graph): HUMILIATION → FORTUITOUS ENCOUNTER → BITTER ASCENT → BREAKTHROUGH → RETURN & REVERSAL
- **pacing**: rising, peak at beat 5

**The re-skin (change setting + cast + GENDER):** female lead **Vesna Calder**, a **sci-fi** orbital colony ("Tier Spires"), power = **psionic resonance ranks** (Null→Spark→Current→Surge→Nova), mentor = a dormant **neural-ghost** (Echo of Sera), rival = Castellan Roin, ally = Juno. Tone: "no magic, no qi, no sects, no cultivation vocabulary."

**Conditions compared:** **A** = control plan (structure injected) · **B** = baseline plan (same goal, NO structure) · **C** = scene compose (one beat realized as prose). Planner re-run with **thinking off / medium / high** + raised budget.

---

## §2 Results

### A — Control plan (structure injected) — **strong, on every axis**
All 5 beats present **in order**, each tagged with its beat + tension, every scene binding the **supplied** cast, full sci-fi skin, female lead. Excerpt:
```
Chapter 1: The Zero-Sum Duel — Beat: HUMILIATION (T2)
  S1 Vesna fails to maintain resonance in a public duel, vulnerable to Roin's sabotage. (Vesna, Roin)
  S3 Stripped of status, Vesna swears a debt of vengeance against the Roin lineage. (Vesna)
Chapter 2: The Dead Signal — Beat: FORTUITOUS ENCOUNTER (T3)
  S2 Vesna awakens the Echo of Sera, which begins uploading forbidden resonance patterns. (Vesna, Echo of Sera)
...
Chapter 5: The Nova Protocol — Beat: RETURN & REVERSAL (T5)
  S2 Vesna challenges Roin to a psi-duel, exposing his illegal amplification tech. (Vesna, Roin)
  S3 Vesna achieves "Nova", overwhelming Roin's signal and reclaiming her status. (Vesna, Roin, Juno)
```
Beat order ✓ · tension T2→T3→T3→T4→T5 ✓ · role-binding to given cast ✓ · effect→precond chain (vow → legacy+cost → trained → threshold → stronger-than-rival) ✓ · **no qi/sect/cultivation leak** ✓ · female lead ✓. **7.2s.**

### A2/A3 — Control plan **with thinking** (the PO-requested planner config) — **adds explicit conformance reasoning + self-correction**
With `chat_template_kwargs.thinking=true` + `reasoning_effort` med/high + raised `max_tokens`, the **reasoning channel** shows the model treating the template as a **checklist it verifies against** — the strongest evidence for "thinking → higher accuracy":
```
Chapter 2: Fortuitous Encounter (T3)
   Pre: Vesna is isolated.            ← reads the template's precondition
   Effect: Hidden power + secret tie to mentor.   ← and its effect
...
Check against "No magic/qi/cultivation" rule. Use "Resonance," "Neural-ghost," "Spike"...
Check against "Bind roles" rule.
Self-Correction during drafting:
   Wait, Chapter 3 (Bitter Ascent) is a "montage" beat. I should make the scenes reflect the progression.
   Chapter 4 (Breakthrough) needs to be a "major threshold." Let's make it a survival/syncing moment.
```
The final plan is **tighter / more disciplined** (consistent full-name binding, no invented extras) than no-think. → thinking turns the abstract control into an **explicit pre/effect + constraint verification at plan time** — exactly the conformance the §14 design wants, done up-front.

### B — Baseline plan (NO structure) — decent shape, but **uncontrollable + unverifiable**
The model **did** produce a coherent revenge-rise arc unprompted — the trope is internalized. **But:**
- It **invented its own cast** (Elara, Kaelen, a "blind hermit") — it could **not be bound** to the supplied Vesna/Roin/Echo cast.
- **No beat tags, no tension** — nothing to **verify conformance against**; structure is implicit and the model's choice, not a control.
- It is a **one-off** — not reusable as a template, can't swap a beat, can't mine/share it.
→ **The control layer's value is not "a weak model can't do revenge" (it can).** It is **bindability + verifiability + reusability + guaranteed structure** — which matter most on **non-cliché arcs, weaker models, and when you must *prove* the arc was followed**.

### C — Scene compose (beat 2 → prose) — **on-beat, skin-consistent**
Given the beat + bindings, the realized scene depicts the full motif: isolation after the fall → meets the mentor (Echo of Sera) → it **tests** her ("you're leaking… fractured") → grants a **hidden legacy** ("forbidden… Nova-tier harmonics forced into her suppressed mind") → **at a cost** ("now I am anchored to your heartbeat. We are one"). Effect = hidden power + a **secret tether** (the motif's "secret debt", seeding the long arc). Skin consistent, female lead. **4s.**

---

## §3 Copyright validation (confirms spec §12.6)

The output reuses the **structure** (the 5 abstract beats) and **zero source expression** — new world, new cast, new gender, no source proper nouns, no genre vocabulary. The idea/structure transferred; the expression is entirely new. This is the live demonstration of "templates are ideas, not the source's expression."

---

## §4 Config recommendation (folds back into the planner design)

| Setting | Recommendation | Evidence |
|---|---|---|
| **thinking** | **ON for the planner** (PO 2026-06-26) | the reasoning channel performs explicit pre/effect + constraint verification + self-correction (§2 A2/A3) |
| **reasoning_effort** | **medium** default (~15-20s) · **high** for hard cases (~33s) | medium already self-corrects; high spends 3× thinking tokens for marginal gain on this strong-trope arc |
| **max_tokens** | **raise to ≥4-6k** and **capture `content` + `reasoning_content` separately** | the FIRST run truncated: thinking ate a 1900-tok budget, `content` came back empty (scene) / cut (plan). Never let thinking starve content. |
| **scene compose** | **no-think** | prose realization needs no deep reasoning; 4s, on-beat (§2 C) |

(The codebase's `engine/plan.py _NO_THINK` was the *opposite* default — correct for that legacy path, but the **motif planner should think**. Raise the budget when you do.)

---

## §5 Caveats / what the POC does NOT prove

- **One arc, one strong trope, one model, qualitative judging.** A non-cliché or multi-thread arc, or a 1-2B model, would stress it harder — that is exactly where the control layer should matter *more* (B shows the baseline only coasts on strong tropes).
- **No structured-output parse yet** — the plan came as markdown; the real planner needs a **JSON schema + tolerant parse** (the `LLM-schema-tolerate-filter` lesson) + **role-name→glossary-entity-id** resolution + the **B≠C** chapter reconciliation (A3 decompose already has these).
- **No automated conformance score** — §2 conformance was read by hand; the real loop needs the `motif_conformance` judge dim (§14) for an objective gate.
- **Provider invariant** — the POC's direct LM Studio call is a probe; production resolves the model via provider-registry (a BYOK `user_models` row), never a direct endpoint in service code.

**Net:** the **prompt-control core is proven feasible** on a weak local model — structure binds, transfers across a full re-skin, verifies under thinking, and composes on-beat. The remaining work is the **engineering wrap** (structured parse, entity resolution, the judge gate), not the core hypothesis.

---

## §6 Complexity stress test — palace-intrigue (宫斗) class arc

The §2 arc was a simple linear 5-beat revenge. **Does the architecture hold for a high-complexity arc** — many interacting threads, nested scheme/counter-scheme cycles, **information asymmetry** (dramatic irony — reader knows, victim doesn't), alliance reversals, sawtooth pacing? (PO ask: 延禧攻略 / 宫斗 / psychological-social drama.) POC 2 (`scratchpad/poc_complex_arc.py`): a **12-beat, 5-thread intrigue template** with explicit genre primitives (SCHEME+info-asymmetry, REVERSAL, ALLIANCE-SHIFT), **re-skinned to a modern corporate drama** (palace → media-finance conglomerate "Griffin-Hale").

### §6.1 Verdict — **it HOLDS, with new primitives.** ✅
The same 4B-active model, thinking-medium, produced a **structurally sophisticated 12-chapter plan** (33s) that kept:
- **All 12 beats in order**, threads (T1-T5) tagged per chapter and **shifting** across the arc.
- **Explicit information-asymmetry** on every scheme — e.g. ch11: *"KNOWS: Maren, Noah · DECEIVED: Ada, Sylvie, Sterling · the gap: the Board thinks Maren is exposing financial fraud; she is actually exposing the murder/suicide cover-up."* The 信息差 essence, captured.
- **Named reversals / alliance-shifts** (ch6: patron Holt **Ally→Threat**).
- **Double-peak sawtooth pacing** (mid-betrayal #6-8, final #11-12) — not a single rising curve.
- **Full corporate re-skin** (résumé fraud, board votes, SEC, market manipulation) — zero palace leakage; female lead; a **morally-grey** protagonist (ch5: manipulates Noah's affection for vault access).

The complex **scheme scene** (POC 2 E) nailed the dramatic irony in prose: Maren detects the planted error mid-meeting, turns it back **deniably** ("auto-corrected from the outdated index — the one Sylvie's team finalized") without openly accusing, with interiority ("*I see you… I'm not going down like Lia did*"). The reader feels the gap between what she shows and what she knows.

### §6.2 What the complexity surfaced — NEW architecture primitives (→ spec §15)
The model held the complexity **because the template carried genre primitives the current spec lacks**. These are the concrete additions:
1. **`scheme` motif kind + an `info_asymmetry` annotation** (`{knows:[], deceived:[], gap}`) — the heart of intrigue/宫斗; not in the current `kind` set, and there is no knowledge-state field. **#1 addition.**
2. **`reversal` / `alliance_shift` beat annotations** — a beat that flips a thread's advantage / a relationship's polarity (names the affected thread or relationship).
3. **Cross-thread triggers** — the model tags *which* threads advance but the causal link (a scheme reveal in T3 *causes* the alliance shift in T4) is implicit; an optional arc_template edge could make it explicit.
4. **Sawtooth / multi-peak pacing** — already expressible (pacing JSONB is freeform) — confirmed, no change.

### §6.3 Honest limits
- **Interiority is NOT controlled by the architecture — and shouldn't be.** The research warned KG-grounding doesn't help interiority; the scene shows the model *produces* interiority when the prose prompt carries emotional stakes. The control scaffolds **plot**, leaves **interiority to the prose** — it neither supplies nor suppresses it. Correct division; don't over-claim plot control as emotional control.
- **Tension tagging drifted slightly** (template beat-tension vs the model's per-chapter number, e.g. ch1 beat t2 but "Tension 1"). The structured-output parse + the planner's own per-scene tension (A3 already emits it) reconciles this.
- **Still one arc.** A full 宫斗 novel chains MANY such arcs (episodic scheme cycles ×dozens). The `arc_template` *composes* (`composed_of`), but **novel-scale arc-chaining** is the next scale up — where the §12.4 map-reduce + arc composition earns its keep.
- **The culprit was invented** (Sterling, CFO) — fine for a probe, but a real book binds it to a glossary entity (the role-resolution the spec already specifies).

**Net (complexity):** the arc-template model **scales to intrigue-class complexity** once it carries `scheme`+info-asymmetry, `reversal`, and `alliance_shift` primitives — a small, additive set the POC validated. The weak model plans and writes the intrigue faithfully when given them. Folded into spec **§15**.

---

## §7 Final POC — compose 2 full chapters · consistency + length

Plan-fidelity is proven; the last question is **prose**: compose **2 real chapters** scene-by-scene (the way the engine works — each scene an independent call), and check **(a) consistency** across the chapter boundary and **(b) length vs the standard**. POC 3 (`scratchpad/poc_compose_chapters.py`) generated chapters 1-2 of the corporate-drama arc — 4 scenes, each fed only the **story bible + the plan + the previous scene's tail** (≈ the real packer: canon + present-entities + prior context).

### §7.1 Length (measured)
| | scenes | words |
|---|---|---|
| Scene 1 / 2 / 3 / 4 | — | 834 · 1009 · 913 · 1028 |
| **Chapter 1** | 2 | **1,843** |
| **Chapter 2** | 2 | **1,941** |
| avg/chapter | 2 | **~1,900** |
~10s/scene on the 4B-active local model.

### §7.2 The length standard (the answer to "what is it?")
| Format | Words / chapter | Note |
|---|---|---|
| Chinese web-novel (网文) | 2,000-4,000 字 (≈ words), **daily 3k-8k** | serialized; "黄金三章" opening |
| English web fiction (Royal Road / Wattpad) | 1,500-5,000, **~2,500 typical** | reader-session sized |
| Trade / traditional novel | 2,500-5,000, **~3,500 avg** | 70k-120k total |
| Light novel | 3,000-5,000 | — |

**Verdict on length:** ~1,900 words/chapter is **at the short end — an acceptable minimum, below the ~3,000 comfort target.** It is **not a model limit**: chapter length = `scenes_per_chapter × words_per_scene`. The scenes here were ~950 words (healthy); the plan gave only **2 scenes/chapter**. To hit ~3,000: raise the planner's **`plan_*_scenes_per_chapter`** to 3-4 (A3 config already exists) and/or set a **per-scene word target** (~1,000-1,200). Length is a **config knob**, met trivially.

### §7.3 Consistency (the answer to "is it consistent?") — **YES, at this scale**
Across **4 independently-generated scenes + the chapter boundary**, everything held:
- **Names/titles/world/gender** — Maren, Lia, Sylvie Quan, Director Holt, Griffin-Hale, Ada/Noah referenced consistently; no rename, no re-gender, no world contradiction.
- **Facts** — the false-résumé-on-Lia's-credentials thread, Lia's death/files, Sylvie-as-rival all persist; ch1 scene 2 even **plants Sylvie's name in Lia's notebook**, which ch2's scheme pays off (emergent foreshadow).
- **Voice/tone** — uniform tense psychological register; **callbacks emerged unprompted**: *"The data is the only narrative"* (ch1 interview line → ch2 internal mantra), the **ghost/"Ghost Resume"** motif, Lia's desk "as if it were a gallows."
- **Beat + info-asymmetry realized** — ch2 executes FIRST-SCHEME with the dramatic irony intact: Maren *knows* it's Sylvie's setup, reports the breach first, and **never reveals she knows who planted it** ("might have been the logistics team or the cleaning shift") — the reader holds the gap.

**What made consistency work:** the **bible (fixed cast/world) + the plan (beats) + the rolling prior-scene tail** — i.e. the architecture's own `canon_rule` + `present_entities` + prior-context packer. The control layer is *also* the consistency anchor, not just the structure.

### §7.4 Honest limits
- **2 chapters is a small consistency test.** The research's **theme/character drift** is a **multi-dozen-chapter** phenomenon; it did NOT appear at 2 chapters with a bible, but the real guard is the L0-L3 memory + the conformance loop (§14) over a long book.
- **The model invented "Sterling"** (a firm name) — the bible didn't name it, so the model filled the gap. In production the **glossary/entity resolution** (the spec's role→entity binding) supplies these so names never drift or get invented.
- **Length target needs the config** — out-of-the-box the plan gave 2 scenes → short chapters; the standard is met by the scenes-per-chapter + word-target knobs (§7.2), not automatically.
- Single genre/model/arc; no automated `motif_conformance` score (read by hand).

### §7.5 Net — feasibility CONFIRMED end-to-end
A weak 4B-active local model, under the motif/arc control + a bible, produced **2 consistent, on-beat, dramatically-ironic chapters of ~950-word scenes** in ~40s total. **Plan → compose → consistent prose** holds. The length standard (~3,000 words/chapter) is a **config knob** (scenes × word-target), and consistency holds at 2-chapter scale via the bible+plan+context packer — with long-range drift handled by the §14 conformance loop + L0-L3 memory, not the prompt alone.

**Overall POC verdict (all 3):** the LoreWeave motif/arc **prompt-control thesis is feasible** — structure binds, transfers across full re-skins (setting/cast/gender), scales to intrigue-class complexity (with `scheme`/info-asymmetry primitives), verifies under thinking, and composes consistent on-standard prose — **all on a deliberately weak self-host model.** The remaining work is engineering (structured-output parse, glossary entity resolution, the conformance judge, the length/scenes config), not the hypothesis.

---

## §8 Long / detailed chapter — beating "lost in the middle" (POC 5)

PO finding: ask an LLM for a long chapter **in one shot** and the **middle degrades** (rushing, thinning, repetition) — lost-in-the-middle — and quality collapses; we must control a standard-or-long, detailed chapter (仙逆 / Renegade-Immortal scale). POC 5 (`scratchpad/poc_long_chapter.py`): the **same ~3000-word breakthrough chapter** (6 sub-beats: seclusion → bottleneck → insight → tribulation → crisis → breakthrough), generated **two ways** on the weak model.

### §8.1 Measured
| | words | vs 3000 target | per-beat avg | repetition (4-gram) | time |
|---|---|---|---|---|---|
| **A · one-shot** (whole chapter, 1 call) | **2,357** | **−21% (undershot)** | ~393 | 0.017 | 22s |
| **B · scene-decomposed** (6 scenes, assembled) | **3,241** | **+8% (hit)** | ~540 (uniform 500-570) | 0.030 | ~40s |

### §8.2 What it shows
- **One-shot can't sustain length** — asked for ~3000, it **rushed to finish at 2357** and **rationed ~393 words/beat**. The prose is coherent, but each beat — especially the **middle** ones (insight/tribulation/crisis) — is **compressed**, denied the slow-burn detail the genre needs. (The catastrophic mid-collapse worsens at 5000+ words / long packed context; even here the early symptoms — undershoot + rationing — are clear.)
- **Decomposition defeats it** — 6 **short** scenes, each generated at **full attention** (no mid-generation sag) and **uniform ~540 words** (+37%/beat vs one-shot), **hit the target length**, and gave each **middle** beat its full detailed treatment. A short scene has no "middle" to get lost in.
- **The cost is SEAMS** — independently-generated scenes show **higher self-repetition (0.030 vs 0.017)** and a tendency to **over-resolve** (a crisis scene drifting into the breakthrough) or reuse imagery across the boundary. → this is exactly why a **consistency / stitch edit pass** is required after assembly.

### §8.3 The architecture this confirms (PO-proposed): **decompose → generate scenes → assemble → STITCH**
The answer to *both* lost-in-the-middle *and* length control is the scene-decomposition the engine already uses, plus one new step:
1. **Decompose** the chapter into fine motif sub-beats — *more/finer scenes for a longer or more detailed chapter* (the planner's `scenes_per_chapter` + §16 `target_words`).
2. **Generate each scene SHORT** (well-attended, beginning-to-end) with bible + plan + prior-tail.
3. **Assemble.**
4. **STITCH / consistency-edit pass** (NEW) — a chapter-level revision over the assembled scenes: smooth transitions, dedup repeated imagery, fix over-resolving / continuity seams. Reuses the **generate→critique→revise** loop the prior-art doc validated (Re3/Dramaturge) + the §14 conformance signals, applied as a seam-smoother.

→ Folded into spec **§17**. Net: **a long, detailed, standard-or-仙逆-scale chapter is controllable** — not by a longer single prompt (which loses the middle), but by **finer decomposition + per-scene full-attention generation + a stitch pass**. The weak model produced a 3,241-word detailed cultivation chapter with full middle-beat depth this way.
