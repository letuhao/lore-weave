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

## Phase 2 — stitch baseline measured (self-heal step 1) — 2026-06-30
Ran the EXISTING 1-pass `stitch` on ch1 (3 fresh scene drafts, Gemma) and diffed vs raw concat
(`poc/io/stitch_ch01_{raw_concat,stitched}.txt`, harness `phase_stitch`):

| metric | raw concat | stitched | read |
|---|---|---|---|
| chars | 7921 | 13305 | stitch **expands ~68%**, does NOT tighten/merge-down |
| scene_title_markers | **0** | **0** | the drafts are title-less prose |
| "phế vật" | 2 | 3 | ~flat density (0.25→0.23/1k) — **not deduped** |
| "lạnh" | 9 | 14 | still ~1.1/1k — motif overuse **not reduced** |
| "Cửu U Ma Cơ" | 1 | 2 | foreshadow **not thinned** |

**Finding A — the "scene-titles mid-chapter" complaint (reviewer #1's top defect, planned as pass L1)
was a POC HARNESS ARTIFACT, not a pipeline defect.** The drafter emits title-less prose; the titles
were injected by the harness `to_tiptap_doc` (heading-per-scene). ⇒ **L1 is dropped from Phase 2** —
the fix is a one-line harness change (don't insert per-scene headings), not a self-heal pass.

**Finding C — `stitch` has a LENGTH-INFLATION weakness (the 68% expansion is real, not a bug in our
code).** Verified: NOT slice-2 (threading doesn't touch stitch), NOT a measurement artifact (raw + the
stitch input are the same 3 drafts), and **0 duplicate paragraphs** — the model wrote genuinely NEW
prose (35 → 61 distinct paragraphs), un-truncated (`finish_reason≠length`, max_out=2100 tok). Root
cause is `engine/stitch.py`'s prompt: it states a merge+dedup intent BUT the dial-guard is one-sidedly
anti-shortening ("do NOT flatten… do not shorten or blandify") with **no length-preservation / no-new-
content constraint**, so a capable model (Gemma) re-writes a fuller chapter instead of joining +
de-duplicating. Net: stitch **fails 2 of its 3 jobs** — dedup ✗ (motif counts UP), length-neutral ✗
(+68%); only transitions ✓. ⇒ **the first self-heal fix is to REPAIR stitch** (add a length-band +
"join & de-duplicate only, add no new events/description" constraint; rebalance the guard; make the
seam-dedup actually bite), higher-leverage than bolting on a new L3 — re-measure for ratio→~1.0 and
"lạnh" density down. THEN the targeted L2/L4 passes for what stitch still can't do.

**Finding C-2 — the prompt fix did NOT work; root cause is deeper (the LLM rewrites, it doesn't
merge).** Applied a sound prompt cleanup to `engine/stitch.py` (length-band + "add no new content";
rebalanced the one-sided anti-shorten guard; dropped the `style_directive` "write lush prose" — wrong
for a merge; made seam-dedup directive). **Controlled A/B (identical DB drafts, only the stitch prompt
changed): 13305 → 13294 chars — essentially UNCHANGED** (the 11-char delta proves a real re-gen, not a
cache). Ground truth from the job: `finish_reason=stop` (NOT truncated), max_out = 3×700 = 2100 tok;
Gemma turned ~1,220 input tokens into ~2,050 output tokens and stopped on its own. ⇒ **the model
rewrites-and-expands by nature and ignores the length/no-new-content instruction.** The output token
cap is NOT a clean lever either: it's already ≈input-sized, and lowering it to force brevity just
TRUNCATES (finish=length → degrade to raw concat), not a graceful shorter chapter. (Note: per-word
repetition DENSITY was ~flat, not worse — lạnh 1.14→1.05/1k; stitch added prose without deduping.)

⇒ **Fixing stitch needs a STRUCTURAL change, not prompt tuning (gate #2 — a design decision for the
PO). Options:**
- **(A) Seam-only stitch** — keep each scene body VERBATIM, have the model rewrite ONLY the ~600-char
  boundary windows between scenes (transitions). Bounds length by construction; biggest change to
  `stitch.py`.
- **(B) In-code deterministic dedup** — apply `repetition_findings` deletions in code (like the
  `_DedupLLM` test models) + a tiny transition-insert; reliable, less "smooth", no rewrite.
- **(C) Two-pass** — keep stitch for transitions, add a separate "compress/tighten" pass with a hard
  length target measured against the input.
- **(D) Accept it** — if a fuller chapter at flat repetition-density is acceptable, the only real
  defect left is logic/continuity (L4), and we skip length control.

**Finding B — `stitch` covers TRANSITIONS/FLOW but is NOT a dedup/repair pass.** The stitched head
reads as continuous prose (no concatenation seams) and even *adds* foreshadow (the black qi seeping
into Lâm Tử Hàn's meridians). But it preserves/expands the over-used motifs, re-explained facts, and
repeated foreshadow — it does not reduce them. ⇒ the multi-pass layers **L2 (info/emotion dedup),
L3 (prose-motif dedup), L4 (continuity/logic repair)** are GENUINELY missing; only the
"hard scene break" defect is already handled by stitch. **Next POC pass: L3 prose-motif-dedup** (the
"lạnh" overuse — most measurable: density target) or **L2 info-repetition dedup** ("phế vật").

## Phase 2 — SATELLITE EDITING is the answer (POC validated) — 2026-06-30
PO insight: don't rewrite the whole text — **edit only a tiny region** ("sửa vệ tinh"), which big
models do well; can a SMALL model? Two mechanisms, and model size matters differently:
- **(1) Trust the model** (whole doc in + "change only X" instruction): big models comply; **small
  models DON'T** — already proven by the stitch test (whole chapter in, "change nothing but dedup" →
  Gemma rewrote + inflated 1.68×).
- **(2) Structural isolation** (send ONLY the span [+ read-only grounding], get back ONLY the span,
  splice in code): the rest is untouched BY CONSTRUCTION — works at any model size.

**POC (mechanism 2, `selection-edit` on an isolated 446-char `lạnh`-dense span of ch1, Gemma):**

| | whole-chapter stitch (mech 1) | isolated span edit (mech 2) |
|---|---|---|
| length | 7921 → 13294 (**×1.68**) | 446 → 449 (**×1.01**) |
| motif "lạnh" | 9 → 14 (not reduced) | 2 → **0** (clean: "cái lạnh"→"cái buốt giá", "lạnh lẽo"→"tê tái") |
| meaning/voice | rewritten | preserved |

**Same model.** Structure makes the difference. ⇒ **VERDICT: a small model DOES satellite editing well —
via mechanism (2) only.** `selection-edit(rewrite/expand/describe, selection, guide)` already implements
it. This **unifies the whole self-heal design**:

> **Every self-heal pass = an LLM JUDGE that reads the chapter and LOCATES the defective span(s) +
> `selection-edit` (satellite) with a per-defect `guide` + splice back.** Not 5 separate whole-chapter
> rewrite passes.

**⚠ The DETECTOR must be an LLM, NOT rule-based code (PO correction).** Literature is open-ended — code
rules (n-gram repetition, keyword motif-density) only catch the tiny *enumerable* slice. The real
defects (logic holes, flat characters, pacing, tonal drift, over-used foreshadow) need **semantic
reading** → an LLM judge. So the pipeline has **TWO LLM roles**, and the asymmetry is the whole point:

| Role | Input | Output | Mechanism | Expansion risk |
|---|---|---|---|---|
| **JUDGE** (detector) | WHOLE chapter | a small structured findings list — each `{defect_type, VERBATIM span to fix, fix instruction}` | reads everything (mech-1 input) but emits only findings | none (output is tiny) |
| **EDITOR** (fixer) | ONE isolated span + guide | the edited span only | mech-2 (isolation) | none (×1.01 proven) |

Code's ONLY remaining jobs: (1) **locate** the judge's verbatim span in the text (string/fuzzy match
→ offsets) and (2) **splice** the edited span back. Cheap rule detectors (n-gram repetition) are an
optional *add-on* pre-filter, never the main detector.

- **A (seam-only stitch)** = satellite-edit the SEAM spans (tail of A + head of B), bodies verbatim.
- **C (tighten)** = judge flags verbose/repetitive spans → satellite-edit each (no whole-doc rewrite).
- **L2/L3/L4** = the JUDGE locates the spans (semantic), satellite-edit fixes each. L3 (motif-dedup
  EDITOR step) is already proven; the JUDGE step is the next unproven half.
- The orchestrator = judge → locate → satellite-edit each finding (confidence-gated, advisory) →
  re-judge loop. Whole-chapter `stitch` rewrite is RETIRED as the assembly primitive.

**⚠ Key handoff risk to POC next:** the judge must return **verbatim** span quotes (or offsets) so code
can locate them — LLMs often paraphrase quotes. POC the JUDGE: can Gemma read ch1 and return real
defects each with a locatable verbatim span?

### JUDGE POC RESULT — validated 2026-06-30 (the pipeline is now proven end-to-end)
Ran a judge prompt on ch1 raw_concat via the composition `LLMClient` (Gemma, in-container). **7 findings,
valid JSON, and the defects are REAL — they match the reviewer critiques and then some:**
1. motif repetition (bóng tối/nuốt chửng) — L3 · 2. info-repetition (expulsion re-stated) — L2 ·
3. flat/abrupt villain (huynh trưởng ôn nhu→khinh miệt) — L5 · 4. **logic hole** (why destroy an
expellee's linh thạch?) — L4 · 5. emotion-loop ("đau đớn/tuyệt vọng" sáo rỗng) — L2 (the "tua băng
cảm xúc") · 6. pacing (chuyển cảnh dàn trải) · 7. **the fall-physics logic hole** (kình lực from where?
— the EXACT defect reviewers flagged) — L4, with a concrete fix (tie it to a pursuer's strike).

The L4 logic holes (#4, #7) are precisely what rule-based code could NEVER find — the LLM judge is
essential. Each finding came with an actionable `fix` (the satellite-edit guide, for free).

**LOCATE-RATE: 7/7 — but only 3/7 EXACT; 4/7 needed FUZZY (whitespace-norm + 5-word shingle).** ⇒ the
handoff risk is REAL but mitigated: **the locate step must use fuzzy/shingle matching, not exact**
(the judge abbreviates with "…" and tweaks spacing). With fuzzy match, every span located.

⇒ **The full pipeline is now proven end-to-end on a small model:**
`LLM JUDGE (real defects + fixes, 7/7 locatable fuzzy) → fuzzy-locate (code) → satellite-edit
(×1.01, surgical, proven) → splice`. The remaining work is the ORCHESTRATOR (glue + a re-judge loop),
not any unproven capability.

## Phase 2 — ORCHESTRATOR built + live-validated — 2026-06-30
`engine/self_heal.py` (`run_self_heal`): judge → fuzzy-`locate_span` → satellite-edit (via
`build_selection_messages`, mech-2) → splice (rightmost-first, non-overlapping) → re-judge. Advisory:
a finding that won't locate / overlaps / whose edit runs away in length is SKIPPED (original kept).
12 unit tests (locate exact/ws/ellipsis/shingle/miss; tolerant parse; splice; the 3 skip guards;
degraded-rejudge→None).

**Live run on ch1 (Gemma, in-container):** judge=6 findings, **located 6/6**, **4 edits applied**, 2
runaway expansions correctly guard-rejected. **Whole-chapter length ratio = 1.014** (vs the stitch's
1.68 — the satellite approach holds at chapter scale). Diff shows surgical on-target edits — the best:
the "abrupt one-note villain" finding → added *"bỗng thoáng qua một tia đau đớn xót xa trước khi trở
lại vẻ lạnh lùng"* (a flicker of pain before the coldness). Artifacts: `poc/io/healed_ch1.txt`.

**Honest caveats (found by verifying, not assuming):**
- The in-run `rejudge_after=0` was a **false zero** — an independent re-judge of the healed text found
  **6** findings. Root cause: a degraded re-judge call parsed to `[]`. **Fixed:** `_judge` returns
  `None` on a degraded call so `rejudge_after` stays `None`, never a false 0.
- **Re-judge is NOT a clean convergence metric** — the judge is non-deterministic + demanding, so it
  always surfaces ~6 things. Self-heal is **iterative** (one pass fixes specific spans, doesn't zero
  the chapter). The real quality gate is the human read + per-edit inspection.
- Minor: an edit occasionally leaves a punctuation artifact (".,") at the splice boundary — a cheap
  cleanup nicety, deferred.
- Not yet wired to an endpoint/worker — validated via the in-container script; HTTP/worker exposure is
  the hardening step after the PO evaluates output quality.

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

---

## Cheap quality stack — judge upgrade (IMPLEMENTED 2026-07-01)

**Problem found by the PO:** the bare self-heal judge was *blind* — it returned **0 findings on
CH1** while the chapter held real xưng-hô + canon errors (false-negative), and when prompted as an
"outside reader" it **confabulated** contradictions that the text actually explains (false-positive).
Root cause = no canon grounding + a too-broad single question + freedom to free-associate. The lever
is **architecture, not model size** (same $0 local Gemma throughout).

**POC verdict (data in `poc/io/poc_stack_out.json`)** — on CH1, grounded judge × vote(5) gave the 3
real xưng-hô/canon errors at **5/5 stability** while the ungrounded judge gave **0/5** real + surfaced
confabs; **voting alone does NOT kill systematic confab** (an ungrounded judge repeats the same wrong
read 2–3/5) — only **grounding** suppresses it at the source and **skeptical verify** refutes the
leak. Single-call-per-axis decomposition was unreliable (2/3 axes returned empty) → dropped; a grounded
COMBINED judge is the win.

**Shipped in `engine/self_heal.py` (all default-OFF ⇒ legacy single-shot byte-identical):**
- `canon` — grounds BOTH the judge and the satellite editor in a story bible (convention + per-character
  canon) + two false-positive guards (no out-of-text inference; already-explained ⇒ not a defect).
- `vote_k`/`min_votes` — run the grounded judge K× (temp 0.7), keep findings recurring in ≥min_votes;
  unlocatable spans never vote (must-quote / L2 folded in).
- `verify` — skeptical refute-or-confirm pass, fail-OPEN on degrade.
- `prefilter` — deterministic `code_mechanical_edits` (dup-word) + full-recall `code_pronoun_findings`
  (modern-pronoun closed class the voting judge under-detects; replacement stays contextual).
- `_snap_to_sentence` — widens every edit span to its enclosing sentence so the satellite editor
  rewrites a COHERENT unit (kills the `…dốc lòng. che chở` splice artifact).

**CH1 result (full stack, $0 local):** 7 known defects → near-zero, **x0.997** (no inflation):
`ông`×2→`y`, `Bà`×2→`Thị`, `mẫu thân ngươi`→`của ta`, the **canon contradiction** (`từng dốc lòng che
chở` → `luôn khinh miệt`, fixed by the grounded editor), `từng từng`→`từng`. Remaining: one cosmetic
blank-line collapse + one borderline cross-paragraph repetition that verify conservatively kept — left
for the human / stronger-model gate (the explicit goal: *fewest errors, then gated*, not perfection).
