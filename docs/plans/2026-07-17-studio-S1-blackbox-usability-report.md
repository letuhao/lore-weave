# S1 · Manuscript & Compose — Blackbox Author-Role Usability Report

**Date:** 2026-07-17 · **Build:** isolated static (`dist-s1-iso`) on `:5209` (no HMR — the 8-session
shared `:5199` was excluded to avoid remount confounds, see lesson `multi-session-hmr-confound`).
**Tester stance:** role-play an author mid-novel — *"I'm writing chapter 3; I want the AI to help me
draft, I accept/revise, and I publish when it's ready."* Not a developer; discovers the UI as-is.
**Method:** a fresh exploratory drive of the real studio surface (screens captured live, in
`assets/2026-07-17-studio-S1-blackbox/`) **plus** direct observation from this session's full E2E run
(13 specs driving every flow live — ghost streaming, accept→editor, correction POST, gate transitions).
Generation *mechanics* are proven by the model-gated E2E; this report renders the **usability judgment**
(discoverability, coherence, dead-ends, felt-vs-silent) that assertions don't capture.

**Verdict scale:** `usable` / `friction (describe)` / `broken`.

---

## Headline verdict

**S1 is genuinely usable by an author — the compose → revise → assemble → publish loop closes entirely
inside the Studio, with strong "you can start now" guidance and no dead-ends.** It clears the bar S1
exists to satisfy (the failure mode was *"cho có và rời rạc"* — present-but-disjoint; it is neither).
The friction that remains is **coherence/polish**, not broken capability: two AI drafting surfaces that
look alike, a couple of gate reasons that are hover-only, one genuinely contradictory model indicator,
and an invisible (working) learning flywheel. None block the job; four are worth a tracked row or a PO
design call.

| BB | Scenario | Verdict |
|---|---|---|
| BB-1 | Draft the next scene with AI | **usable** (minor friction: two similarly-named compose entries; model must be picked) |
| BB-2 | Accept this draft into my chapter | **usable** (non-destructive keep-draft safety is a plus) |
| BB-3 | Try again / assemble the whole chapter | **usable + friction** (scene-compose vs chapter-assemble look near-identical; stitch-gate reason hover-only) |
| BB-4 | My edits should teach the AI | **friction (design opinion)** — the flywheel works but is invisible; zero felt signal |
| BB-5 | Publish my chapter | **usable** (unblock control co-located; reason hover-only) |
| BB-6 | Do the whole loop in the Studio | **usable** — the loop closes in-studio; power-surface overlap is the only cost |

---

## Per-scenario detail

### BB-1 · "Let me draft the next scene with AI." — **usable**
*Screens: `02-palette-compose-search`, `03-scene-compose-first-mount`, `01-studio-landing`.*

- **Discoverable.** `⌘⇧P → "compose"` returns two entries, disambiguated by subtitle:
  `Open Compose → "AI co-writer chat"` vs `Open Scene Compose → "Draft a scene with AI candidates"`.
  A guessed word ("compose") lands the author on the draft loop.
- **No dead-end on mount.** Scene Compose opens with a green banner —
  *"● Ready to draft — Grounding gets richer after you build a knowledge graph, but it is optional — you
  can write now"* — and an explicit *"Write your opening, then Generate — or Continue from your cursor in
  the editor."* This is excellent: it pre-empts the "do I need a KG first?" dead-end.
- **Multiple honest entry points.** The Editor itself carries `Continue from cursor` + inline
  Rewrite/Expand/Describe, so an author can draft from the panel *or* inline in the manuscript.

**Friction (minor):**
1. **`Compose` vs `Scene Compose` names are close** — the distinction (chat co-writer vs
   candidate-drafting loop) lives only in the subtitle. An author skimming may open the wrong one.
   *Mitigated* by the subtitle; a PO call on whether to rename `Compose`→`Co-writer Chat`.
2. **A model must be picked before Generate** (the test account has no default — CLAUDE.md caveat). The
   gate is *honest and visible* ("Pick a model" hint next to Generate), not a silent no-op. A real author
   with a default model wouldn't hit this.

### BB-2 · "Accept this draft into my chapter." — **usable**
*Proven live (E2E `studio-scene-compose`): ghost → Accept → prose lands in the Editor doc (char count
grows), correct chapter (chapter-mismatch guard S1-D4).*

- The **2-panel handoff is coherent**: Accept in Scene Compose, the prose appears in the Editor tab. The
  `editorBridge` handle is the Tier-4 manuscript-unit hoist, so the prose lands even if the Editor tab
  isn't in the foreground — the author doesn't have to pre-arrange panels.
- **Non-destructive safety (a real plus).** If there is no editor target on the composed chapter, Accept
  **keeps the draft** and toasts guidance instead of silently dropping the prose (the GAP-2 fix). An
  author never loses generated text to a mis-click.

**Friction (minor):** the landing is slightly *implicit* — beyond the toast there's no bold "inserted ✓"
confirmation in the Editor; the author infers success from the text appearing. Acceptable.

### BB-3 · "This draft is wrong — try again / assemble the whole chapter." — **usable + friction**
*Screens: `04-chapter-assemble-gate`. Proven live: Regenerate → correction POST + re-stream; stitch
gated until scenes done; mode toggle persists.*

- **Regenerate** re-streams a fresh draft (and feeds the flywheel — see BB-4).
- **Chapter-assemble** is understandable: a `Per-scene | Chapter` mode toggle, `Generate chapter`, and a
  `Stitch chapter` that is correctly gated until every scene is `done`.

**Friction:**
1. **Scene Compose and Chapter Assemble look near-identical** (`04` vs `03`): same header (scene select /
   +Scene / Mark done / Pick a model / Spawn what-if), same what-if row, same green "Ready to draft"
   banner. They differ only by tab title and the bottom action strip. An author could lose track of which
   panel they're in. *Recommend* a stronger visual identity per panel (a title/icon band, or hiding the
   what-if row in assemble). → **tracked row `D-S1-COMPOSE-ASSEMBLE-VISUAL-SAMENESS` (LOW, PO/design).**
2. **The stitch gate reason is hover-only.** `Stitch chapter` greys out when scenes aren't done, but the
   only *inline* text is "Pick a model"; the scenes-done reason isn't surfaced beside the button (the
   publish gate has the same hover-only pattern — see BB-5). → fold into the gate-reason row below.

### BB-4 · "My edits should teach the AI." — **friction (design opinion, not a defect)**
*The correction flywheel (Regenerate/Discard → `POST …/correction` → learning-service) is **proven to
fire** but is a **silent backend**.*

- The author performs the dissatisfaction action (Regenerate / Discard) and the correction is captured
  **invisibly** — no toast, badge, or "learning from this" hint. Accept-as-is is (correctly) *not*
  captured (H2 self-reinforcement guard), so there's no signal there either.
- **Judgment:** honest and arguably *right* not to nag — but it means the flagship "the AI learns from
  you" value is **entirely unfelt**. An author has no way to know the flywheel exists.
- **Recommendation (PO):** a subtle, non-blocking acknowledgement on Regenerate/Discard (e.g. a quiet
  "noted — this improves your co-writer" toast, dismissible/off-by-preference). → **tracked row
  `D-S1-FLYWHEEL-INVISIBLE` (LOW, PO design opinion).** Not a fix-now; the mechanic is correct.

### BB-5 · "Publish my chapter." — **usable**
*Screen: `05-editor-publish-gate`. Proven live: blocked (visible reason) → mark scene done → enabled →
publish POST 2xx. Captured reason string: `"1 of 1 scenes not yet done"`.*

- **Self-serve unblock is co-located.** The Scenes panel (right of the Editor) shows the scene with a
  `drafting` status dropdown the author flips to `done` — the exact control that unblocks Publish is *in
  the same view*, no hunting.
- The gate transitions correctly and publishes for real (button → "Re-publish").

**Friction (minor):** the publish reason lives in the button's `title` (hover-only), and the disabled
Publish button isn't strongly greyed — an author might click it, see nothing, and not know why. →
**tracked row `D-S1-GATE-REASON-HOVER-ONLY` (LOW):** surface disabled-gate reasons inline (a small caption
under the button) rather than tooltip-only, for both Publish and Stitch.

### BB-6 · "Do the whole loop in the Studio." — **usable (the ③ loop-closes goal is met)**
*Screens: `01-studio-landing`, `06-palette-guide`.*

- Deep-linking to a chapter opens a coherent workspace: Editor (with the chapter prose) + Scenes panel +
  manuscript navigator. **Scene Compose, Chapter Assemble, Editor inline-ghost, and Publish are all
  reachable via the Command Palette without ever touching the legacy `ChapterEditorPage`.** The
  draft → revise → assemble → publish spine closes in-studio.
- **Onboarding exists:** the palette offers `Open User Guide` ("Every Studio tool, grouped by area") and
  `Start Guided Tour` ("A quick tour of the core panels").

**Friction (the price of power):** there are **three overlapping AI-drafting surfaces** — the Editor
inline toolbar (Rewrite/Expand/Describe/Continue), Scene Compose (candidate loop), and Chapter Assemble.
Powerful, but a new author may not know which to reach for. The User Guide mitigates; still worth a PO
note on a recommended "default path."

---

## Concrete findings (ranked)

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | **MED** | **Contradictory model indicator.** The Editor status bar reads **"no model"** (bottom-right) while the inline AI toolbar shows **"Gemma-4 26B-A4B QAT"** selected (`01`,`05`). Two model concepts (the Work's resolved default vs the inline per-action pick) are shown side-by-side with no explanation — an author can't tell which model will actually run. | **Tracked row `D-S1-MODEL-INDICATOR-CONTRADICTION`.** Not a fix-now in the compose/assemble/inline/publish build slices — it's the editor's model-display, and the correct fix needs the Work-default ↔ inline-pick resolution surfaced coherently (settings/config clarity, likely a shared studio concern). Flag to PO; verify a real account *with* a default model doesn't show "no model". |
| 2 | LOW | **Gate reasons are hover-only** (Publish `title`, Stitch greyed). No inline caption; disabled buttons aren't strongly greyed. | `D-S1-GATE-REASON-HOVER-ONLY` — surface disabled reasons inline. |
| 3 | LOW | **Scene Compose ≈ Chapter Assemble visually.** Shared chrome makes the two panels hard to tell apart at a glance. | `D-S1-COMPOSE-ASSEMBLE-VISUAL-SAMENESS` — stronger per-panel identity. |
| 4 | LOW | **Flywheel is invisible.** Corrections are captured with zero felt signal; the "AI learns from you" value is unfelt. | `D-S1-FLYWHEEL-INVISIBLE` — optional subtle acknowledgement (PO design opinion). |
| 5 | INFO | `Compose` vs `Scene Compose` naming proximity. | PO call on a rename; subtitle currently disambiguates. |

**No `broken` verdicts.** Every capability an author reaches for works; the findings are coherence and
polish. Findings 2–5 are design/polish (PO calls or LOW tracked rows); finding 1 is the only one worth a
MED tracked row and a real-account re-check.

---

## What this pass could NOT freshly exercise (and why it's still covered)
- **Live streamed generation during this pass** — the local LM Studio queue was wedged from the E2E run's
  sustained back-to-back generations (lesson `lm-studio-queue-wedge`; not `lms reload`-ed — user infra).
  The generation *mechanics* (ghost stream, accept-insert, correction POST, regenerate) are nonetheless
  **proven green** by the model-gated E2E specs earlier this session; this pass judged the surrounding UX
  from the non-generation screens + prior direct observation, which is where the usability verdict lives.

## Recommendation to PO
Ship S1 — it is usable and the loop closes. Open the four tracked rows above (one MED, three LOW) in the
S1 RUN-STATE DEBT register; none gate the release. Prioritise **finding 1 (model indicator)** for the
next studio-settings pass, as a contradictory model display is the one item that could actually mislead
an author about what (and what cost) they're running.
