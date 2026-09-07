# Human-simulation authoring run — "Vạn Tượng Quy Nhất," 2026-09-07

Reconciles: the `/human-sim` request to play a human author against Writing Studio + PlanForge,
write a real 5-arc web novel through the app's OWN AI, review it via the Method's Workflow
multi-lens pattern, and deliver a written feedback report + go/no-go for the pre-release →
release decision. Full raw evidence (build logs, chapter-by-chapter review verdicts, exact
findings text) lives in [`2026-09-06-human-sim-van-tuong-quy-nhat.md`](2026-09-06-human-sim-van-tuong-quy-nhat.md)
— this report synthesizes it into something a reviewer can act on without reading the whole run.

**Persona:** an author outlining and drafting a 5-arc web novel from a pre-written premise doc
(`D:\Stories\story-plan-v1.md`), using PlanForge for structure and Co-writer Chat for prose.
**Target:** book `Vạn Tượng Quy Nhất` (`01a07780-172b-70fa-bf11-cbf261fa3e91`), protagonist Trần
An Nhiên. **Scope achieved: all 5 arcs outlined (28 chapters total, ≥5 scenes/chapter), one
chapter per arc fully drafted through Co-writer Chat and reviewed via a 4-lens + synthesis
Workflow (steering-bible consistency, plot logic, prose quality/length, continuity)** — a
deliberate sampling choice (5 of 28 chapters) once the review loop's behavior had converged,
not a scope cut forced by a blocker. Two product bugs were CRITICAL enough to fix inline and are
already merged, filed, and verified in a rebuilt container; everything else below is reported,
not fixed, per this run's own branch discipline.

---

## 1. What worked

- **The planning → outline → chapter/scene structure is real and durable.** All 5 arcs, 28
  chapters, ≥5 scenes each exist as actual `StructureNode`/`OutlineNode` rows with Goal/Synopsis
  fields, survived across the whole multi-day run, and round-tripped correctly through the API
  every time they were re-read for a chapter draft.
- **Co-writer Chat, driven with a specific per-chapter Goal quoted from Steering, produces
  genuinely good prose.** Every one of the 5 sampled chapters passed its review after at most one
  revision cycle — plot logic and continuity scored 8-9/10 on 4 of 5 chapters on the FIRST pass.
- **The review-and-revise loop is load-bearing, not theater.** Every single sampled chapter needed
  at least one real fix (a continuity slip, a steering violation, a characterization gap, a
  length/craft issue); none passed clean on the first try. The loop caught things a skim would
  have missed, including two separate name collisions the model reintroduced into its OWN revision
  after being told to fix them.
- **Two CRITICAL correctness bugs were found, root-caused, fixed, and verified in a live rebuilt
  container inside this same run** — not just filed and walked past:
  - Steering rules silently truncated to ~3 of 8 rules below an undersized token cap, invisible
    anywhere in the UI ([#223](https://github.com/letuhao/lore-weave/issues/223)).
  - An over-long (but entirely reasonable) Arc/Chapter "Goal" field write corrupts the READ of
    every arc in the whole book, 500-ing the Plan Hub for the entire project
    ([#224](https://github.com/letuhao/lore-weave/issues/224)).
- **The backend's safety nets for agentic writes are good engineering when they fire.**
  Placeholder-id rejection and an arc_id≠run_id loop-guard both caught bad tool calls by name with
  clear, specific messages (see Finding 11) — the gap is what happens after they fire, not that
  they exist.

---

## 2. Findings, by severity

Full text and reproduction evidence for every numbered item is in the plan doc's FEEDBACK LOG;
numbers below (`#N`) point there.

### BLOCKING for the product's own stated pitch

**F-A. The app's own AI cannot write directly into the manuscript. (#19)** Every in-Editor
generation control tested (the "AI" writing toggle, "✦ Continue from cursor," "✦ Suggest scenes,"
the "✨" narration-attach icon) either stayed disabled or produced nothing. Co-writer Chat itself
confirmed it explicitly: *"Tôi không có quyền truy cập trực tiếp vào Manuscript editor để viết vào
đó."* The only demonstrated path for a full run, top to bottom, is: draft in chat → human reads →
human manually retypes/pastes into the correct anchored heading in the Editor. That hand-off is
real, unautomated work for every single scene of a 5-arc, 28-chapter book, and nothing in-product
tells a new author this is the intended flow — the more discoverable controls all look like they
should do this and don't.

**F-B. The product's own quality-flywheel instrumentation never sees content written through that
same only-working path. (#26, ties to #23)** Conformance reported "Realized: Not written yet" for
all 5 scenes of a chapter that was fully drafted, Workflow-reviewed, ACCEPTED, and marked "Done"
in its own Scene Inspector — because Conformance keys off a `written_scene_id`/`written_at`
linkage that only a different (Planner/Diverge-driven) generation path sets. Corrections shows "No
generations yet" for the identical reason. Motif Library/binding is unusable for tracking a
story's own recurring imagery because it's a different feature entirely (a plot-shape template
picker for that same unused Planner path). **Net effect: an author who completes an entire book
the only way currently possible gets zero of the product's own consistency/quality signals.** This
is the single most important finding in this report — it means two whole feature surfaces
(conformance tracking, the correction-rate learning loop) are validated against a pathway this
testing could not exercise even by trying, because that pathway doesn't work yet (F-A).

### CRITICAL (found, fixed, and verified this run — listed for completeness, not open)

**F-C. Steering rules silently truncated below a 2000-token cap, invisible in the UI. (#10)**
Fixed: cap raised 2000→8000, tests updated, verified against the real 8-rule bible in a rebuilt
container. Filed as [#223](https://github.com/letuhao/lore-weave/issues/223). Residual, deferred:
no UI indicator when truncation DOES happen for a genuinely oversized bible.

**F-D. An over-long Arc/Chapter Goal field write corrupts reads of the WHOLE book's arc list. (#12)**
Fixed: response-model cap widened 2000→20000 to match the write-side schemas, all 6 equivalent MCP
tool-arg fields given a matching write-side bound, verified against the actual corrupted row in a
rebuilt container. Filed as [#224](https://github.com/letuhao/lore-weave/issues/224). Residual,
deferred: `title`/`summary` on the same schemas have the identical unguarded-write shape, just not
yet hit by real content.

### HIGH

**F-E. PlanForge's automated propose→approve→compile pipeline never reaches compile. (#11)** A
genuinely excellent, fully-consistent AI-authored arc proposal was approved twice (spec + review
checkpoint) and then failed 3 consecutive times at the compile step — sending a literal
placeholder id, then an id the backend's own loop-guard correctly refuses by name, then repeating
the same mistake a third time after an explicit human correction. The backend's rejections are
each individually well-designed; the model never adapts across them, and the turn reports partial
success rather than "compile failed." Worked around by building the arc manually from the AI's own
proposed content — reliable, but it means the flagship "AI plans your book" pipeline was not
usable end-to-end at any point in this run.

**F-F. A book's auto-created Knowledge Project is never renamed when the book is renamed, and a
create-when-one-exists call silently no-ops. (#6, #7)** Together these produced a ~20-minute dead
end: the real project existed but was unfindable by the book's current name, and the "just create
a new one" recovery path returned `200 OK` while discarding everything typed, with no error toast.
Recovered via Edit on the existing (old-named) record instead of Create.

**F-G. Three dead ends before finding the real path to AI-generated arc structure on a blank
book. (#9)** "Create a plan with AI," "Organise into storylines," and "Suggest arcs" all sound like
what an author wants and are not it — the actual free-text, agentic arc-generation capability is
gated behind attaching a specific skill to Co-writer Chat, with no signpost from any of the three
more-obvious entry points.

### MEDIUM

**F-H. Save-on-blur can silently DISCARD unsaved text in one field when a different field is
saved afterward — a data-loss shape, not just a stale-cache one. (#13)** Confirmed via API: typing
a 1686-char Goal, then saving a different field, left the Goal field truly empty server-side.
Recurs for every node unless a specific fill-order workaround is followed by hand.

**F-I. Prose length is reproducibly under the requested word count, and only partially
self-corrects when told explicitly. (#20)** Three independent measurements this run, all short:
an initial ask landed at ~25-40% of the requested length; an explicit expand-and-enrich follow-up
still landed short; a batched multi-scene ask landed ~15% under even a modest 400-600-word target.
The first fully-drafted chapter of the run finished under this plan's own web-novel-standard
target — not a one-off.

**F-J. Co-writer Chat occasionally keeps generating past its own stop, drifting into unrelated
leftover content from an earlier turn in the same conversation. (#22)** Reproduced across two
separate chapters: a correct, complete response for the CURRENT request was immediately followed
by a fresh, verbatim regeneration of a DIFFERENT, earlier request's draft, with no boundary marker
beyond the model's own staleness disclaimer. A reader skimming only the start of a long response
could easily ship the wrong tail content.

**F-K. Plan Hub's canvas and completion counters silently go stale after mutations made through
their own adjacent controls. (#14, #15, #21)** A new chapter is created correctly server-side but
never appears on the canvas without a full reload; the Arc Inspector's chapter roll-up shows a
count and "no chapters assigned" at the same time; a scene-status dropdown's own toolbar counter
doesn't reflect the write it just made. Confirmed via direct API reads in all three cases that the
underlying data was correct — these are render/cache-invalidation gaps, not data bugs.

**F-L. Two Quality-tab rough edges found while triaging Phase 4's panels. (#24, #25)** Story
coverage's promise analysis correctly reports "nothing to cover" when zero promises are tracked,
but surfaces it as an unhelpfully generic "unavailable" instead of pointing at the Promises panel.
Conformance's own chapter picker labels all 28 chapters "Untitled chapter," even though the exact
same title data renders correctly one panel away.

### LOW / notable, not actionable on their own

- Co-writer Chat's first-turn latency (48s TTFT) on a large tool/skill context (#2); a confused
  trailing disclaimer appended after an otherwise-complete answer (#3); an intermittent SSE
  notification-stream drop, twice (#4); an unexplained second, unrequested extraction job
  alongside a requested one (#8); a model that re-derives its own diverging version of
  already-committed canon rather than trusting a human's stated facts, while honestly disclosing
  it might be stale (#17).

---

## 3. Prose-quality defect taxonomy (the review loop's own findings about itself)

Every one of the 5 sampled chapters needed revision; tracking what recurred across all 5 is itself
a finding about how far prompting alone can close a gap:

| defect | fixable via prompting? | evidence |
|---|---|---|
| flash-forward / narrator-voice foreshadowing | yes, via a targeted cut | recurred 5+ times across the run despite explicit warnings each time |
| direct/explicit action violating a chapter's own interior-only lock | yes, via a rewrite modeled on another scene in the same chapter | 1 chapter, fully resolved on re-check |
| a characterization/logic gap (ignoring a self-observed clue) | yes, via a reasoned in-character addition | 1 chapter, fully resolved on re-check |
| "không phải X, mà là Y" antithesis + abstract-noun-stacking prose tic | **no** — survived two independent, increasingly specific correction attempts | background noise in 4/5 chapters, DOMINANT defect in the 5th; the second correction attempt reproduced the exact flagged construction inside brand-new content written specifically to remove it |

The last row is the one demonstrated limit of "review, then ask the model to fix it": three defect
classes closed reliably; one did not, even with a scene-targeted, specifically-worded correction.

---

## 4. Go / No-Go

**Conditional GO for the underlying planning/outline system and its review-and-revise loop; NO-GO
for the product's flagship pitch of AI-assisted in-manuscript authoring, as currently wired.**

Reasoning:

- The parts of this run that map to "can an author, with this tool, produce a structurally sound,
  internally consistent 5-arc outline and get real editorial value from an automated review pass"
  — yes, cleanly, on every one of 5 independent samples, including catching this run's own
  self-introduced mistakes (Finding #16) and reproducing exactly across the whole run when tried
  again (the antithesis prose tic, §3).
- The parts that map to "can an author use Writing Studio's OWN advertised AI-authoring surfaces
  to actually write the book" — no. F-A means the advertised in-Editor generation controls do not
  work at all; the only demonstrated path (chat, then hand-copy) is unautomated manual labor for
  every scene of a real book, and nothing tells a new author that's the intended flow. F-B means
  that even when an author completes a book through that one working path, the product's own
  quality/consistency tooling never sees it.
- Two CRITICAL bugs (F-C, F-D) would have blocked this very run from continuing at all had they
  not been fixed inline — both are now fixed and verified, so they are not blockers for release,
  but their SHAPE (write succeeds silently, read explodes or truncates later, with no UI signal
  either way) recurred independently at LOW/MEDIUM severity three more times this run (F-H, F-K,
  the Arc-1 Summary save-on-blur gap noted in T2.1) and is worth a dedicated audit before release,
  not just point-fixes as each instance is hit.
- F-E (PlanForge compile never completing) and F-G (three dead ends before the real AI-arc-
  generation path) mean the "AI plans your book for you" pitch is also not reliably reachable yet,
  independent of F-A/F-B.

**Recommendation:** do not release on the strength of "AI writes your novel for you" as currently
implemented — F-A and F-B together mean that claim is not true end-to-end today. The outline/
structure layer and the Workflow-style review pattern this run validated ARE release-quality and
are the part of the pitch that currently holds up under real use. Prioritize before the next
go/no-go pass: (1) an actual working in-Editor AI-write path, (2) wiring Conformance/Corrections/
Motif tracking to whatever authoring path ships as the real one, (3) closing or clearly signposting
the PlanForge compile pipeline. Everything in the MEDIUM/LOW tier is real friction but not release-
blocking on its own.
