# Chapter Synthesis & Self-Healing — multi-pass refinement (diffusion-style)

> **Date:** 2026-06-30 · Status: DESIGN DIRECTION (PO-prioritized over further GUI work) ·
> **Related:** [`2026-06-30-editor-compose-overhaul/`](2026-06-30-editor-compose-overhaul/) (GUI track),
> [`2026-06-05-composition-controlled-auto-correction-flywheel.md`](2026-06-05-composition-controlled-auto-correction-flywheel.md).
> **Origin:** two independent reader critiques of the POC's generated Chapter 1 (Lâm Uyển) — both
> diagnosed the same thing: it reads like 4 independently-generated scenes concatenated, with the
> AI-pipeline seams showing.

## The problem (reader critiques — accurate)
Per-scene quality is high (~8.5/10) but the **assembled chapter** reads ~6/10 because of cross-scene
defects:
- **Scene titles** left mid-chapter (reads like an outline, not prose).
- **Plot discontinuity** — expulsion → sudden pursuit with no cause/transition.
- **Timeline breaks** — morning → "ban trưa" → night with no transition.
- **Info repetition** — "phế vật / no spirit root" re-explained every scene (scenes generated blind to
  each other).
- **Foreshadow over-repetition** — the succubus (Cửu U Ma Cơ) appears 3× across consecutive scenes,
  killing the reveal.
- **Continuity holes** — the grimoire/token appear/shatter with no prior setup.
- **Flat supporting cast** — everyone is "cold"; no distinct personalities (NPC effect).
- **Prose-motif overuse** — "lạnh lùng / lạnh lẽo / lạnh như băng…" (model sampling tell).
- **Repeated pacing pattern** — describe→dialogue→suffering→monologue→cliffhanger, ×4.

**Root cause:** the pipeline is **autoregressive** (Outline → Scene 1..N → concatenate). Each scene is
frozen once generated; nothing does a **global, multi-pass** correction over the whole chapter.

## ⚠ ORDERING — fix the PLANNING first (PO, root cause), THEN polish
> "Một phần của vấn đề là **tính liên kết của scene**. Phải tăng chi tiết mô tả mỗi scene và làm cho
> chúng nhất quán trước (tương tự arc, beat…), rồi mới tạo chapter và cải thiện chất lượng. Nếu ngay từ
> đầu các scene đã chẳng liên quan gì nhau thì làm sao tạo chapter tốt được." — PO

**The self-healing/polish layer is DOWNSTREAM. The root fix is upstream, at planning.** Evidence from
`engine/plan.py` (decompose):
- A scene is only `{title, intent(1-2 sent), tension, present_entities}`; the **synopsis == that 1-2
  sentence intent** (`plan.py:237 synopsis=intent.strip()`) — far too thin to ground continuity.
- Scenes are generated **per-chapter, independently** (`build_scene_decompose_messages` "breaking ONE
  chapter into scenes") → **chapter N's scenes never see chapter N-1's outcomes** (no cross-chapter
  continuity / shared timeline / carried state).
- **No connective tissue:** no entry-state, no causal link to the prior scene, no exit-state /
  what-changes, no time marker. `scene_links` (setup→payoff graph) exist but decompose doesn't populate
  them. Beat/arc laddering is a single `beat_role` tag, not enforced coherence.

⇒ the drafter receives a thin, disconnected synopsis and **invents** the missing links (sudden pursuit,
grimoire from nowhere). **Polish cannot repair what was never planned to connect — garbage in, garbage
out.**

### The corrected pipeline order
0. **Planning connectivity & detail (DO FIRST)** — enrich decompose to emit **connected, detailed
   scene specs**: richer synopsis (goal · conflict · outcome/change) **+ continuity fields**
   (`entry_state`, `caused_by`/link to prior, `exit_state`, `time_marker`); generate **continuity-aware**
   (condition each scene/chapter on a running state-so-far summary); **populate `scene_links`**; enforce
   scene→beat→arc coherence (same enrichment for arc/beat). Scenes become coherent **by construction**.
1. **Draft** — cowrite each scene grounded on its now-rich spec + the carried state.
2. **Chapter synthesis + multi-pass self-healing** — the diffusion-style loop below handles only the
   **residual** seams, not the structural disconnection.

### Exploit glossary + KG — the latent state already powers DRAFTING; wire it into PLANNING
The asymmetry is the unlock:
- **Drafting** already pulls **5 KG lenses** per scene via `packer/pack.py` — `present` (entity+state),
  `canon`, `lore`, **`open_promises`** (setups awaiting payoff), `timeline`. Drafting IS KG-grounded.
- **Planning** (`plan.py` decompose) is **KG-blind** — it uses premise + cast roster only (no
  `knowledge_client` calls). **This is the unexploited gap.**

**Exploitation = feed the SAME KG lenses into decompose**, which maps the PO's keyframe idea onto real
state:
- **KG snapshot after chapter N = the "previous frame"** → use it as chapter N+1's `chapter_entry_state`
  keyframe (entity states, recent events, timeline). Literally "frame trước làm nguyên liệu cho frame
  sau".
- **`open_promises` lens** → the planner enforces **setup-before-payoff** (the grimoire is set up before
  it glows) and **thins duplicate foreshadow** (Cửu U Ma Cơ once, not 3×).
- **`timeline` lens** → consistent `time_marker` (morning→noon→night).
- **`present`/entity-state lens** → distinct supporting-character states (less "everyone is cold").

**The loop already exists — the extraction FLYWHEEL:** draft chapter → extract (glossary + KG; POC
proved 20 entities) → KG enriched → grounds the next chapter. It runs for drafting today but is **open
on the planning side** — closing it = part of the "exploit the KG" work.

### ⚠ But KG is COMPLEMENTARY, not the backbone (PO correction)
KG is **situational + partial**, so it must NOT be the primary continuity carrier:
- **Situational** — empty for chapter 1 of a new book; only populated from chapter 2+ (post-extract).
- **Partial** — extraction captures entities/events/relationships/timeline, but **NOT** the fine-grained
  continuity that matters most between adjacent scenes: immediate emotional beat, physical state ("she
  is now holding the shard"), action momentum, prose-level detail. KG abstracts these away.

⇒ **Two-layer continuity substrate, previous-scene first:**

| Layer | Source | Nature | Availability |
|---|---|---|---|
| **Backbone** | **previous scene's `exit_state` (raw, fine-grained)** | immediate emotional/physical/action state | **ALWAYS** — incl. chapter 1 (scene N-1 → N) |
| Enrichment | **KG snapshot** (entities/events/open-promises/timeline) | structured, coarse, global | chapter 2+ (after extract) |

Decompose chains each scene's `entry_state` from the **prior scene's `exit_state`** (always on); the KG
snapshot is **added on top** when available. Chapter 1 runs on pure previous-scene chaining + premise;
from chapter 2 the KG joins as enrichment. This matches **Narrative Interpolation** (conditions on the
previous scene *raw*, not just an abstracted state) — the PO's "previous frame as material" is the
**core**; KG is the bonus layer.

### Human-in-the-loop CONTEXT DIRECTOR (not full automation) — PO principle
**You cannot let the model select all context.** Auto-retrieval (RAG/KG) fails on long-range recall —
e.g. *"describe a character who first appeared in chapter 500; we are now at chapter 3200."* No
embedding/graph query reliably surfaces ch-500's context 2700 chapters later. **A human must be able to
direct what context is loaded.** So the pipeline is **assistive, not autonomous**: the author declares
"this scene involves character X / callback to event Y", and the engine then pulls X/Y's full history.

**The mechanism largely EXISTS — it just needs to be human-drivable + surfaced:**
- `outline_node.present_entity_ids` (the scene's declared cast) already drives the grounding `present`
  lens — declaring an entity present makes the packer pull its KG state/history.
- grounding **pins/excludes** (`setGroundingPin`) + the **references** shelf = manual context injection.
- ⇒ "context director" = let the author **add a long-dormant entity / a past event as present/pinned**
  for a scene → the engine pulls its full history. This is exactly where the **GUI overhaul matters**
  (Story-Bible/cast + grounding controls = the director's console). Engine + GUI meet here.

**POC must exercise this:** simulate a returning character (declare a ch-1 entity present in a later
scene, or pin a past event) and verify the grounding pulls its history — proving the human can steer
context the model wouldn't retrieve on its own.

Everything from here down is **Phase 2** — necessary, but only after Phase 0 lands.

## Market & research validation (web search, 2026-06-30)
- **Commercial tools** (Sudowrite, Novelcrafter, NovelAI) = Story-Bible/Codex + previous-N-chapters
  context + relevance/keyword injection (autoregressive + memory). **Still fail at scale** — a 25-chapter
  test found 4/5 contradict themselves ([Novarrium](https://novarrium.com/blog/ai-writing-tools-keep-contradicting-themselves)).
  ⇒ a story-bible (which Lore Weave has) is necessary but **not sufficient**.
- **Academic standard = multi-pass:** **Re3** (Plan→Draft→Rewrite→Edit; rerank coherence + edit
  consistency, [arXiv:2210.06774](https://arxiv.org/abs/2210.06774)) and **DOC** (Detailed Outline
  Control, [arXiv:2212.10077](https://arxiv.org/pdf/2212.10077)). = our Phase 2 "diffusion-of-edits".
- **Text diffusion** sees the whole sequence (no causal mask) → good for global coherence, but pure
  text-diffusion hurts fluency → **hybrid** (AR structure + diffusion refine) wins; incl.
  [Segment-Level Diffusion](https://arxiv.org/pdf/2412.11333) for long-form. ⇒ the diffusion intuition
  is right, but the practical form is **hybrid / diffusion-of-edits**, not token-diffusion of the novel.

### Verdict on the PO's keyframe-interpolation idea: SOUND + already named
"Use the previous frame as material for the next, steering toward a final (start→end) frame" = two
published techniques:
- **Narrative Interpolation** ([arXiv:2008.07466](https://arxiv.org/pdf/2008.07466)) — condition on the
  previous + next anchor, fill the gap ("in-betweening" between plot points). Exactly the PO's idea.
- **Ending-guided generation** — steering toward a target ending beats storyline-only; RL reaches the
  target ending 98.73% of the time ([arXiv:2112.08593](https://arxiv.org/pdf/2112.08593)).

⇒ Conditioning each scene on the prior scene's exit-state **and** steering toward the chapter/beat
**target end-state** is a validated design — and it is a **PLANNING-time** technique (set keyframes →
interpolate), i.e. **Phase 0**. It does NOT compete with the multi-pass polish; they are different
layers and the PO's ordering (interpolation/planning first, polish second) matches the field.

## The framing (PO): treat it like diffusion, not one-shot autoregression
A real novelist drafts → re-reads the whole chapter → fixes pacing, cuts repetition, adds
foreshadowing, smooths transitions — **iterative refinement over the global work**. That is much closer
to **diffusion** (each denoise step sees the whole image; a region can be fixed at step 30 because
another region changed) than to one-shot left-to-right generation.

**Proposed:** Outline → rough scenes → **N single-purpose refinement passes**, each reading **global
chapter state**, optionally **confidence-driven** (only refine low-confidence scenes×dimensions — like
diffusion only denoising still-noisy regions), with **multi-scale attention** (early passes over scene
windows; final pass over the whole chapter).

## What ALREADY exists (the building blocks — ~70% is composition)
| Capability | Engine (composition-service) | Role in the loop |
|---|---|---|
| Merge / dedup / transitions (1 pass, advisory) | `engine/stitch.py` (`stitch_chapter` + W-STITCH: repetition_findings, detect_over_resolve, boundary_windows) | a denoise step |
| Prose quality judge (coherence/voice/pacing/canon) | `engine/critic.py` | confidence/noise map |
| Continuity check (gone-chars, canon) | `engine/canon_check.py` / `canon_reflect.py` | confidence + fix |
| Foreshadow/promise debt | `engine/narrative_thread.py` | confidence + fix |
| Structure adherence | `engine/arc_conformance.py` | confidence |
| Chapter summary / compression | `engine/compress.py` | latent chapter state |
| Per-scene grounding (present entities, canon, timeline-so-far) | `packer/pack.py` + grounding | denoise context |
| "Latent state" | knowledge event log / snapshots / chunks, glossary cast, timeline | the chapter's latent the passes read |

> **Note:** the POC harness did **raw concatenation** (never called `stitch`), which overstated the
> seams. But `stitch` is **one** advisory pass — the **multi-pass, confidence-driven self-healing loop
> is genuinely missing.**

## The gap → the new layer
An **orchestrated multi-pass Chapter Refinement / Self-Healing engine** that, after scenes are drafted:
1. **Measures** a **confidence map** per (scene × dimension) using the existing judges
   (critic, canon_check, narrative_thread, arc_conformance) + new cheap detectors (timeline coherence,
   prose-motif density, scene-title presence, info-repetition n-gram overlap).
2. **Refines** low-confidence regions with single-purpose passes (each reads global chapter state):
   `de-title/merge` · `dedup` · `timeline+transition` · `naming/cast-personality` · `foreshadow-thin` ·
   `prose-motif-dedup` · `continuity-repair`.
3. **Re-measures** and repeats until confidence ≥ threshold or a pass budget is hit (the diffusion
   denoise schedule), **multi-scale** (windows → whole chapter).
4. **Self-healing:** a pass only *proposes* edits gated by the judges (no silent degradation — mirrors
   stitch's advisory invariant); a pass that lowers a dimension's confidence is rolled back.

### New pieces (~30%)
- The **orchestrator** (pass schedule + confidence-map loop + rollback).
- **timeline+transition** pass (detect time/space jumps from the timeline state → insert transitions).
- **prose-motif-dedup** pass (detect over-used phrases → vary).
- **scene-title strip / merge** as a deterministic presentation step (cheap, no LLM).
- The **confidence map** model (per scene×dimension scores + thresholds).

## Why this before more GUI
The GUI overhaul makes the tools *reachable*; this layer makes the *output good*. Per-scene content is
already ~8.5/10 — almost all the lost quality is post-processing/global-linking, which the critiques
estimate recovers to **~8.5–9/10** after one automatic "chapter polish". That is the product's core
value; GUI polish over outline-like chapters does not win.

## Phase 0 — slice 1 (prompt enrichment) RESULT — validated 2026-06-30
Enriched `build_scene_decompose_messages` (goal·conflict·outcome + continuity + causality +
ending-guided; `l2_max_tokens` 1536→2560) on branch `feat/editor-compose-overhaul`. Re-ran decompose
on the Lâm Uyển premise. **Intra-chapter connectivity is fixed at the planning layer:**
- Causes now established — the expulsion is *caused* by hiding the brother's cultivation secret.
- Explicit chaining — scene 2 opens *"Tiếp nối từ cú rơi từ vách đá…"*; scene 2 *sets up* the rising
  demonic qi before scene 3.
- Setup-before-payoff — the grimoire is now *"hệ quả từ việc linh căn bị phá hủy"*, not from nowhere.
- ⇒ the 3 worst reviewer defects (causeless pursuit, grimoire-from-nowhere, disconnected scenes) are
  resolved **at planning**, prompt-only (no engine rewrite).

**Next defect surfaced (expected):** chapters 1/2/3 **repeat the same arc** (expulsion→fall→grimoire)
because decompose still generates each chapter **independently**. ⇒ **Phase 0 slice 2 = cross-chapter
sequential threading** (chapter N receives chapter N-1's exit-state / running "story-so-far", per the
two-layer substrate: prev-scene/chapter exit-state backbone + KG enrichment when built).

## Phase 0 — slice 2 (cross-chapter threading) RESULT — validated 2026-06-30
Implemented the typed-state / event-sourcing refinement at the decompose layer
(`engine/plan.py`, gated behind `thread_state`, default OFF ⇒ today's concurrent fan-out
byte-identical):
- New `ChapterExitState` (typed buckets **characters / world / plot** + `advances` list), emitted by
  the **same** L2 call (no extra round-trip) as a `chapter_exit` delta — the event-sourcing "emit the
  change, not the whole prose".
- When `thread_state` is ON the invent path runs **sequentially in chapter order**; each chapter is
  conditioned on `render_story_so_far(prev_exit, used_advances)` = the **previous chapter's full exit
  state** (fine-grained backbone) **+ the cumulative spent-developments list** (coarse global
  anti-repeat). Chapter 1 threads nothing (empty ⇒ non-threaded prompt shape) but still emits its exit
  so the chain starts. Degrade-safe: an L2 failure keeps the last good `prev_exit`.
- Wired through worker (`run_decompose` reads `input.thread_state`) + router (`DecomposeRequest.thread_state`,
  additive optional) + POC harness (`thread_state: true`).

**Live result (worker path, Gemma, thread_state=True, 12ch/36sc):** the cross-chapter repetition is
**resolved** — every chapter now opens *"Tiếp nối từ…"* (continuing from) the prior chapter's
exit-state and advances to new ground:
- CH1 humiliation→expulsion→pursuit→Ma path; CH2 *"Tiếp nối từ trạng thái trọng thương tại vực thẳm"* →
  body re-creation + Ma-Cơ link (NOT a re-expulsion); CH3 ma-khí absorption mechanism; CH4 Ma Đan +
  inner-demon trial → re-infiltration. `exit_state.advances` show monotonic progression, no repeats.
- ⇒ the slice-1 fix made scenes connect WITHIN a chapter; slice-2 makes chapters connect ACROSS the
  book. Validated at synopsis level (the PO's validate-first gate) before any drafting.

**Tests:** `tests/unit/test_plan.py` +5 (parse_chapter_exit tolerance, render_story_so_far, the
emit/continue-from prompt switches, the sequential threading + thread-forward, thread-off back-compat);
full composition unit suite 1180 passed; fixed 5 pre-existing `test_worker_jobs.py` `cancel_check`
fake-signature drift (unrelated to this slice, fix-now hygiene).

**Known follow-ups (not blockers):** (a) `thread_state` + `motifs_enabled` together still uses the
motif `prev_effects` carry only — combined typed-state threading on the motif path is a follow-up;
(b) scenes/chapter dropped toward `min_scenes` under the richer prompt — a pacing/scene-count knob, a
separate concern from connectivity; (c) intra-chapter telescoping (CH1 packs many beats) — an L1
beat→chapter mapping concern, addressed by the planning-cast/structure layer, not threading.

## Round-2 reviews of the re-drafted chapter (3 reviewers) — 6.5/7 → 8.5/10
Consistency jumped a full grade from one **pipeline** change (no model change). Confirmed wins: scenes
now "remember" the prior scene (carry-over), emotional momentum preserved across scene boundaries, no
longer "each scene is a mini-story", context propagation works (spirit-root destroyed → empty dantian →
demonic qi enters ruined meridians). The remaining defects are **finer** and split cleanly by aspect →
they justify the PO's point: **several single-purpose self-healing layers, not one**.

### Phase 2 = MULTI-LAYER self-healing (one pass per aspect) — derived from the reviews
| Pass | Fixes (reviewer-cited) | Engine |
|---|---|---|
| **L1 Presentation** | strip **scene titles** → weave transitions (top complaint; titles "kill the flow") | deterministic + `stitch` |
| **L2 Emotion-loop dedup** | the betrayal→pain→hate **loop** repeats every scene ("tua băng cảm xúc") | critic + a dedup pass |
| **L3 Prose rhythm / motif** | concept-cramming (đôi mắt/thức hải/đan điền/ma khí/kinh mạch…) + monotone sentence length → vary long/short | style/voice pass |
| **L4 Continuity / logic repair** | **Ma Cơ "teleport"** (remnant + grimoire conveniently waiting; MC names her before being told) needs a CATALYST (abyss = her tomb/seal, or blood-awakened relic); **fall-physics** (a now-mortal survives a 10,000-zhang fall) needs a cause (demonic-qi cushion) | canon_check + continuity pass |
| **L5 Character depth** (harder) | flat one-note villains; betray too fast; low originality | planning-level (Phase 0 cast) |
Each pass single-purpose, reads global chapter state, proposes-only (advisory), confidence-gated.

### ARCHITECTURE refinement (PO insight) — typed STATE + per-scene DELTA = event-sourcing / ResNet
The "previous scene as material" is really a shift from autoregressive `Scene_i → Scene_{i+1}` to
**`Scene_i → Δ → State → Scene_{i+1}`**. Don't feed the whole prior scene — keep **typed state** and
have each scene emit a **delta**:
- **Character State** (per entity): emotion, goal, belief, relationships, power/HP.
- **World State**: location, time, weather, key objects.
- **Plot State**: secrets, open foreshadow, active conflicts.

Scene N+1 reads **Character+Plot state + only the TAIL of scene N** (not the whole scene) → tokens drop
sharply. Each scene emits a **delta** (emotion: angry→more-angry; relationship: trust→broken; power:
Qi3→Qi4); the system applies it = **event sourcing for characters** (ResNet-style: generate the
*change*, not re-derive the whole state). **Lore Weave's append-log + snapshot + context-chunk infra
fits this exactly** — this is more promising than merely growing the context window. ⇒ refines Phase 0
slice 2 (cross-chapter threading): the "running state" is **typed state + deltas**, not a flat summary.

## Open questions for PO
- [ ] **SH-D1** — build this as a new **engine track** (composition-service) prioritized ahead of
  GUI slices? (GUI continues after / in parallel as smaller slices.)
- [ ] **SH-D2 (REVISED — planning first, keyframe-interpolation)** — first concrete step is **Phase 0**,
  not polish. Implement the PO's keyframe idea at the decompose layer:
  **(a)** define per-chapter **keyframes** = `chapter_entry_state` (carried from the prior chapter's
  exit) + `chapter_target_end_state` (toward the beat/arc goal); **(b)** generate scenes by
  **interpolating** between them — each scene emits a richer synopsis (goal·conflict·outcome) + continuity
  fields (`entry_state` from prior scene, `caused_by`, `exit_state`, `time_marker`), **ending-guided**
  toward the chapter target; thread a running "state-so-far" so chapter N flows from N-1; **(c)** re-run
  the POC decompose on the Lâm Uyển premise and read the new specs — does the expulsion now *cause* the
  pursuit? is the grimoire *set up* before it glows? do scenes share a timeline? Validate at the
  **synopsis level** before any drafting. _Only after Phase 0 reads coherent_ → (d) re-draft, (e) measure
  the `stitch` baseline, (f) build the confidence map + first self-healing pass (Re3/DOC-style).
- [ ] **SH-D3** — confidence-driven selective refinement (diffusion-style) vs fixed pass pipeline for v1?

## Verification (when built, per pass — validate-first)
Run the pass on POC Chapter 1 → diff before/after → confirm the targeted defect drops (e.g.
timeline pass: the morning→night jump gets a transition; dedup pass: "phế vật" count drops) **without**
lowering other dimensions' confidence. Reader re-rates the assembled chapter.
