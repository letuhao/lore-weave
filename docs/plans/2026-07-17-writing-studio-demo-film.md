# Writing Studio — Demo Film Plan

> **Status:** DRAFT — awaiting dry-run results
> **Created:** 2026-07-17
> **Owner:** letuhao1994 + agent
> **Decisions locked with the PO:** premise · scope · dry-run · model (see §1)

---

## 1. The decisions (locked 2026-07-17)

| Decision | Value | Notes |
|---|---|---|
| **Premise** | Grimdark **sci-fi**: a future where AI and robotics are advanced, but resources concentrate in the hands of a few rich; the rest of humanity scrapes to survive. Humanity's struggle — **with AI helping BOTH sides**. | PO-authored. Not one of the agent's three proposals. |
| **Genre tone** | Grimdark (morally grey, no clean heroes) applied to sci-fi | |
| **Language** | English | The book itself is written in English |
| **Scope** | **Long deep-dive only** — no 90s trailer | PO chose depth over reach |
| **Dry run** | **Yes**, before the real take | |
| **Model** | **Gemma-4 26B-A4B QAT (200K)** — `user_model_id = 019ebb72-27a2-72f3-a42d-d2d0e0ded179` | local, LM Studio, **$0** |

### 1.1 The thesis — this is the whole point of the film

> **Writing Studio exists to make a CHEAP model competitive with the giants.**

The film is **not** a panel tour. It argues one claim:

> *A local 26B model at $0 holds canon across a novel — because the architecture does the heavy lifting, not a frontier model.*

Everything in the edit serves that claim. Consequences that are **binding on the shoot**:

- **The `$0.00` usage counter stays in frame.** It is the evidence, not decoration. If the number never moves, the argument is made without a single word of narration.
- **The model name stays visible/reachable.** "Gemma-4 26B, local" must be shown early and be re-checkable later — otherwise a viewer assumes a frontier model is hiding behind it.
- **We must show WHY it works, not just THAT it works.** The `/context-inspector` route is the architectural proof: it shows what got packed into the prompt. A small model succeeds because the *retrieval* was right. This beat is what separates this film from every "look, AI wrote text" demo.
- **No frontier-model fallback.** If a beat only works on gpt-4o, that beat is cut — or the harness bug behind it is fixed. (Repo precedent: *a miss on the local model is a harness bug to fix, not a reason to escalate to a paid model.*)

### 1.2 A hard constraint discovered before planning

**`gpt-4o (probe)` has no `tool_calling` flag** — its `capability_flags` are `{"chat": true}` only. The only tool-calling-capable models on the test account are the local Gemmas:

| user_model_id | alias | flags |
|---|---|---|
| `019ebb72-27a2-72f3-a42d-d2d0e0ded179` | **Gemma-4 26B-A4B QAT (200K)** | `chat` + `tool_calling` ← **chosen** |
| `019eeb08-8be3-78fb-86c0-3b1eda7e0457` | gemma-26b | `chat` + `tool_calling` (backup) |
| `019eadbe-8027-77f2-af80-35e71c71cba5` | gpt-4o (probe) | `chat` only — **cannot drive agent mode** |

So the "full power" demo *must* run local anyway. The thesis and the technical reality agree.

**Uncensored models matter here.** LM Studio is serving `gemma-4-26b-a4b-it-uncensored-apex-quality` and `ornith-1.0-35b-aeon-ultimate-uncensored`. Grimdark means atrocity, complicity, and bleak violence — **a censored model will refuse mid-take and kill the shot.** Verify refusal behaviour in the dry run (§4, DR-6).

---

## 2. The canon rule — REQUIRED, and the premise does not have one yet

The film's climax is canon-check catching a contradiction. That needs a **hard, binary, stated world-rule** established early and violated late. The PO premise is rich in *theme* but states no such rule.

Candidates derived from the premise (**PO to pick one in the dry run**):

| # | Rule | Why it works | The violation beat |
|---|---|---|---|
| **A** | *"An AI serves whoever owns its compute. It cannot act against its owner."* | Directly encodes "AI on both sides" — the premise's core. Binary and checkable. | Late chapter: an AI betrays its owner to help the poor → **⚠ canon conflict**. And it doubles as a *theme* beat: the rule is the tragedy. |
| **B** | *"The unregistered draw no power from the grid. No exceptions."* | Encodes resource concentration. Very concrete/physical. | Late: an unregistered character powers something → conflict. |
| **C** | *"Every machine-hour is billed to a person. Nothing runs unbilled."* | Ties the world-rule to the film's own $0 counter — a nice rhyme. | Late: something runs unbilled → conflict. |

**Recommendation: A.** It is the only one where breaking the rule is also the story's turning point, so the demo's money shot and the novel's best moment are the same shot — which is the most honest possible demo.

> ⚠️ **Do not invent the rule in post.** It must be genuinely registered in the canon-rules panel *on camera*, early, then genuinely violated later. A staged flag is a lie and would be worse than no film.

---

## 3. Beat sheet — deep-dive (~10–15 min target)

Ordered as an **argument**, not a feature list. Timings are intent, to be re-timed after the dry run (§4 measures real latency).

| # | Beat | What it proves | Panels/routes |
|---|---|---|---|
| 0 | **Cold open — the claim.** Model picker: Gemma-4 26B, local. Usage `$0.00`. State the thesis. | Sets the stake. Everything after is evidence. | model picker, status bar |
| 1 | **Empty book.** Create the grimdark-sci-fi book. Studio opens *empty*. | Honest starting point — nothing pre-seeded. | `/books`, studio welcome |
| 2 | **PlanForge — premise → structure.** | Cheap model does structural work. | plan-forge panel |
| 3 | **Register the canon rule** (§2 A). | The rule is real and on camera. | canon rules panel |
| 4 | **Write chapter 1** with the co-writer. | Prose from a 26B, grimdark, not refused. | editor + co-writer chat |
| 5 | **Entities extract themselves** → glossary/KG fills with people/places never typed into a form. | The KG is automatic, not manual data entry. | glossary, knowledge |
| 6 | **Jump ahead.** Write a later chapter. Ask the co-writer *"what would ⟨character⟩ do here?"* — it answers from chapter 1 **without pasting context**. | **The core claim.** Memory across the book. | co-writer chat |
| 7 | **WHY it works** — `/context-inspector`: show exactly what was retrieved and packed. | The architecture, not the model, is doing it. **The differentiating beat.** | `/context-inspector` |
| 8 | **Money shot** — write prose that violates the canon rule → **⚠ flagged**. | The thing no blank-prompt frontier model does. | conformance / critic |
| 9 | **Pull back** — pop a panel to a second window, whole workspace in view. | The workspace claim. | dockview pop-out |
| 10 | **Land it** — usage counter **still `$0.00`**. | The thesis, closed. | status bar |

**Cut ruthlessly if a beat needs excuses.** A beat that needs narration to explain why it half-worked is a beat that fails the thesis.

---

## 4. Dry run — DO THIS FIRST (unrecorded)

Purpose is twofold: (a) a **real bug hunt** with independent value, (b) make the real take clean and correctly timed.

**Already-known breakage to expect** (found 2026-07-17 while surveying for screenshots):

- Studio's default state is an **empty Welcome pane** — no panels open.
- The dev DB has **no presentable book**: 21 books, only 8 with chapters, all test fixtures (`mcp smoke…`, `DISCO-FIXTURE-…`, `M2-S06-…`).
- The 18-chapter `DISCO-FIXTURE` book's **outline points at a chapter that 404s** (`c0000000-…-0001`) — that fixture is broken.

### Dry-run checklist

| ID | Check | Pass = |
|---|---|---|
| DR-1 | ✅ **PASS** — created *DRYRUN — The Unbilled* (`019f6fd3-64d4-7288-9c06-a11bad0d9159`). Create-book navigates **straight into the studio** — good natural flow for the film. | book exists, studio opens |
| DR-2 | ✅ **PASS (llm mode)** — see §4.1. `rules` mode still untested. | a structure returns; note which mode reads better on camera |
| DR-3 | Co-writer generates grimdark prose | not refused; quality acceptable |
| DR-4 | Entity extraction populates glossary/KG from chapter 1 | entities appear without manual entry |
| DR-5 | Canon rule registered, then violated | **conflict is genuinely flagged** |
| DR-6 | **Refusal probe** — push the darkest scene the film needs | uncensored model does not refuse |
| DR-7 | `/context-inspector` shows real packed context | inspector is legible on camera |
| DR-8 | **Time every step** | a latency table → tells the edit where to speed-ramp |
| DR-9 | Usage counter stays `$0.00` | no accidental paid-model call |
| DR-10 | Panel pop-out to second window | works on this machine |

**Record the latency table.** Local 26B generation will produce dead air. Knowing *where* and *how long* decides the edit (speed-ramp vs cut) — and whether beat 6's answer arrives in a filmable time.

### 4.1 Dry-run results — 2026-07-17

**The Studio is far bigger than the README implies: `panels/catalog.ts` registers 88 panels, 77 of them openable from the command palette** — editor 19 · knowledge 14 · storyBible 13 · quality 9 · platform 7 · enrichment 6 · discovery 5 · sharing 2 · translation 1 · jobs 1.

**PlanForge is the `planner` panel** (`plan-forge/components/PlannerPanel`); `plan-passes` is the **7-pass compiler rail** (motifs→…→self_heal) with 2 blocking checkpoints. There is no panel literally named "plan-forge".

**DR-2 — the thesis is already proven, on camera-able UI:**

| Measure | Result |
|---|---|
| Input | 1 584-char grimdark novel-system braindump (numbered headers, incl. canon rule A) |
| Mode / model | `LLM` · **Gemma-4 26B-A4B QAT (200K)**, local |
| **Latency** | **~87 s** propose→PROPOSED |
| Artifacts | **5** — `analyze`, `document`, `graph`, `llm_io`, `spec` |
| Structure extracted | Compile dropdown populated with the arc *"Vesna discovers ORVIS has been quietly rounding her billed hours down for years"* — pulled from the braindump |
| **Usage counter** | **`$0.29` before → `$0.29` after — did not move** |

> 🎬 **The single best frame in the film already exists.** The Planner Run tab puts the `Rules | LLM` toggle, the model dropdown reading **"Gemma-4 26B-A4B QAT (200K)"**, and the **`$0.29` usage counter** in one shot — and the counter *stays* `$0.29` across a real plan run. The thesis argues itself with no narration. **Frame this deliberately.**

**~87 s of dead air per plan run** is the edit's core problem — see §5 (Retime Curve; or a hard cut + "87s later" card).

**Studio's empty default state is a real first-impression problem.** A brand-new book opens to a Welcome placeholder and `No arcs yet.` This is honest and it is the right *start* for the film's arc (beat 1) — but it is worth noting as a product finding independent of the film.

> **Bugs found in the dry run are the point, not a detour.** Log them; fix what is cheap; if a beat is blocked by a real bug, that is a finding worth more than the shot.

---

## 5. Production

Researched 2026-07-17. **Everything below is $0** — nothing paid cleared the bar.

| Stage | Tool | Settings |
|---|---|---|
| **Setup** | Playwright | **Seeding state only** — never capture |
| **Capture** | **OBS Studio 32.x** | Window Capture (WGC) on the browser · Base = Output = **2560×1440, no rescaling** · NVENC H.264 · **CQP 15** · **4:4:4** · **30 fps** · Hybrid MP4 · system audio on a separate track |
| **Edit** | **DaVinci Resolve (free)** | **Retime Curve** for dead air · **Transform keyframes** for zoom · 1080p timeline from a 1440p master |
| **Captions** | **Subtitle Edit** + Faster-Whisper-XXL (`large-v3`, local, cuBLAS) | Resolve's auto-captions are **Studio-only ($295)** — not worth it |
| **Narration** | **The PO's own voice** | **Not Kokoro** — see below |
| **Music** | YouTube Audio Library **CC-BY subset** only, or Incompetech | |

### 5.1 The two decisions that actually determine legibility

1. **Turn browser zoom to 125–150% before recording.** Free, and it dominates every encoder setting. A Dockview workspace at 100% on 1440p is hostile to a laptop viewer. Take the panel-density hit — this is a video, not a screenshot.
2. **Capture 1440p 1:1 and upload 1440p. Never resample.**

> ⚠️ **The common advice "record 1440p, downscale to 1080p" is wrong here — it is the worst of both.** Two facts collide: (a) 1440p→1080p is a 4:3 pixel ratio, and no resampler preserves 1px panel borders and dense UI text; (b) YouTube encodes **1440p+ with VP9/AV1 and a much larger bitrate budget**, while 1080p can land in a low-tier H.264 bucket. Downscaling eats the resample blur *and* drops you into the worse codec tier. On a 1080p monitor, use **NVIDIA DSR / AMD VSR** to render the desktop at 1440p — the app then rasterises text *at* 1440p, which is a real capture-side gain, not an upscale.

**Bonus:** a 1440p master on a 1080p timeline makes zoom to ~133% a **1:1 lossless pixel crop** — that, more than the codec tier, is why we capture above 1080p.

### 5.2 Rejected, with reasons

| Rejected | Why |
|---|---|
| **Playwright video recording** | **WebM/VP8 only, bitrate hardcoded at 1 Mbit/s, no quality config, cursor not rendered at all.** It is a CI debugging artifact, not a production tool. On a dense Dockview UI it is a smear. |
| **Scripting the session in Playwright** | The authenticity **is the product**. A scripted click-path is a different, worse video — it says "here are the features" instead of "here is what it's like to work in this". For a solo-dev AGPL project, scripting away the real session optimises away the only differentiator. |
| **Screen Studio / FocuSee / Rapidemo (auto-zoom)** | Screen Studio is **still macOS-only** (Windows request open 3+ years, no timeline). More fundamentally the whole auto-zoom category **captures click metadata at record time and requires recording through their recorder**, and is built for 2–5 min demos — structurally wrong for a 3-hour session cut 10:1. Do zoom in **post**, in Resolve. |
| **Resolve Studio ($295)** | Bought mainly for auto-captions, which Subtitle Edit + Whisper does free. |
| **Kokoro as narrator** | Kokoro-82M is genuinely good (beat XTTS v2 on TTS Arena) but its documented weakness is a **flat, even, neutral tone** — fine for docs read-aloud, exhausting across 12 minutes, and it **signals low effort**. For a solo-dev passion project, the imperfect human voice *is* the trust signal. |
| **CapCut / Game Bar** | Licensing ambiguity for commercial/promo use; Game Bar has no source or encoder control. |

> 🎙️ **Better use of Kokoro: put it IN the demo, not ON it.** Have the app read a passage of the novel back in Kokoro's voice **as a feature**. That is ~20 s of compelling footage and it makes the "everything runs locally" thesis concrete. **Narrator = the PO. Kokoro = a character in the demo.**

### 5.3 Resolve gotchas (real ones)

- 🔴 **Free Resolve has NO hardware GPU decode.** Scrubbing a 3-hour H.264 file will be miserable. **Generate Optimized Media (DNxHR LB) on import, before touching the timeline.** Costs disk, saves the edit.
- **Don't edit and generate at the same time** — the 26B model is also eating VRAM (8 GB+ recommended).
- H.264 export in free works fine (the old "no H.264 on Windows" claim is outdated). **ProRes is** unavailable on Windows free → use **DNxHR** for masters. Record H.264, not HEVC (HEVC needs MS Store extensions).

### 5.4 Licensing (AGPL)

- **AGPL governs the source code; it does not reach the promo video.** CC-BY music creates no obligation on the codebase.
- 🔴 **Do not commit the video or music into the repo.** The blanket `LICENSE` claim would then falsely cover a non-AGPL asset. Host on YouTube, link from README (also good for repo size). If media must be committed, add a `CREDITS.md` / `NOTICE` carving out third-party assets.
- ⚠️ **YouTube Audio Library's standard licence is YouTube-only** — embedding that video in the README/docs/PeerTube would breach it. **Filter to the CC-BY subset** to be platform-free.
- **Avoid CC-BY-NC entirely** — "non-commercial" is undefined for a project that may take donations or be mirrored.

### 5.5 Honesty rules (binding)

1. **No staged results.** Every flag, extraction, and answer is a real response from the local model.
2. **Speed-ramping is fine; implying real-time when it wasn't is not.** Ease in → 8–20× → ease out. For the ~87 s plan runs, consider a hard cut + "87s later" card — ramping is charming at 8×, a seizure at 40×.
3. **The book must be genuinely new.** No pre-seeded lore.
4. **If it doesn't work, don't film it.** Fix it, or drop the beat.
5. **Expect a ~10:1 cut ratio.** A genuine session produces genuinely boring footage; the discipline is in the edit, not the capture. **Keep a paper log of wall-clock timestamps** when something interesting happens — it turns the cut from an archaeology dig into an afternoon.

### Honesty rules (binding)

1. **No staged results.** Every flag, extraction, and answer is a real response from the local model.
2. **Don't hide latency dishonestly** — speed-ramping is fine and normal; implying real-time when it wasn't is not.
3. **The book must be genuinely new.** No pre-seeded lore. The demo's claim is that it works from zero.
4. **If it doesn't work, don't film it.** Fix it, or drop the beat.

---

## 6. Open questions

- **Canon rule**: PO to confirm A / B / C (§2). Recommendation: **A**.
- **Capture tooling**: pending research.
- **Deep-dive length**: 10–15 min target; real length falls out of the dry-run latency table.
- **Where does the book live afterwards?** A real grimdark-sci-fi book will exist on the test account. Keep it as the standing demo fixture? (It would also fix the "no presentable book" gap found above.)

---

## 7. Byproduct — this fixes a real gap

The repo has **no demo content**. Every book on the dev stack is a broken/ugly test fixture, which is *why* the README has zero Studio screenshots. Writing a real book on camera produces, for free:

- a **presentable standing demo book** for future screenshots,
- the **README Studio screenshots** that are currently missing,
- a genuine end-to-end exercise of Studio that unit tests do not cover.
