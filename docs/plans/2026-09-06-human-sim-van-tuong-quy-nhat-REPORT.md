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

**F-A. Three AI-write paths into the manuscript exist. Every one is gated, and no gate is visible —
so from inside the product the capability is indistinguishable from absent. (#19)**

> **CORRECTED 2026-09-12 by codebase recon.** This finding originally read *"The app's own AI
> cannot write directly into the manuscript."* **That was wrong**, and the correction matters
> because it changes the fix from a feature build to a day of un-gating. The observed behaviour was
> real and is unchanged; the mechanism behind it was not what this report claimed. Corrected text
> follows.

Every in-Editor generation control tested (the "AI" writing toggle, "✦ Continue from cursor,"
"✦ Suggest scenes," the "✨" narration-attach icon) either stayed disabled or produced nothing, and
Co-writer Chat stated explicitly, in the book's own language:
<!-- doc-language-gate: ok -- the model's verbatim reply IS the evidence this finding rests on;
     paraphrasing it would destroy the quotation. English meaning given immediately after. -->
*"Tôi không có quyền truy cập trực tiếp vào Manuscript editor để viết vào đó."*
<!-- doc-language-gate: end -->
— *"I do not have direct access to the Manuscript editor to write into it."* So the run's
conclusion — that a human must hand-paste every scene of a 5-arc, 28-chapter book — was correct
**as an account of what happened**. What was wrong was *why*:

1. **`book_chapter_save_draft` is a real Tier-A MCP tool that writes prose straight into
   `chapter_drafts.body` — the Manuscript editor's own canonical document.** It is registered at
   `services/book-service/internal/api/mcp_server.go:342-355`, handled at
   `mcp_tools_write.go:778-877`, and named in the co-writer skills
   (`chat-service/app/services/book_skill.py:102`, `composition_skill.py:57`). **But it is
   deliberately lazy on the editor/studio surface**, reachable only via a `find_tools` round-trip.
   The design note says so outright at `chat-service/app/services/tool_discovery.py:341-347`:
   *"The editor's extra capability (prose write-back) is the `propose_edit` FRONTEND tool … NOT a
   backend domain — so composition / book tools stay lazy there too."* The model's claim that it
   had no access was therefore **plausibly true of its own context at that moment.**
2. **`propose_edit`** (`ai-gateway/src/mcp/propose-edit-tool.ts:27`) is the intended editor
   write-back — but it is client-applied and needs the editor open with a live cursor/selection.
3. **"✦ Continue from cursor" has a real handler**, not a stub
   (`frontend/src/features/composition/components/InlineAiLayer.tsx:79-87`). It was disabled by
   `canContinue` (`hooks/useInlineGhost.ts:40`), which requires `modelRef` — and `modelRef`
   resolves only from a persisted `settings.default_model_ref` or from the user having *exactly
   one* active chat model (`EditorPanel.tsx:272-275`). With several models registered and no
   persisted default it is null forever. The explanation exists, in a `title` tooltip on a
   `disabled` button — the one place a user cannot hover-discover it.

**The corrected finding is narrower and worse in a different way:** the product ships the
capability its pitch depends on, and then hides every route to it. A tester who spent days inside
the Studio never found it. That is a reachability-and-disclosure defect, not a missing feature —
and it is cheap to fix, which the original framing obscured.

**F-B. The product's own quality-flywheel instrumentation never sees content written through the
path a human actually uses. (#26, ties to #23)** Conformance reported "Realized: Not written yet"
for all 5 scenes of a chapter that was fully drafted, Workflow-reviewed, ACCEPTED, and marked
"Done" in its own Scene Inspector. Corrections shows "No generations yet." Motif Library/binding is
unusable for tracking a story's own recurring imagery because it is a different feature entirely (a
plot-shape template picker for an automated planner pathway).

> **CORRECTED 2026-09-12 by codebase recon.** This finding originally attributed "Not written yet"
> to a null `written_scene_id`/`written_at` linkage. **Conformance never consults `written_*` at
> all.** There are *two independent* dead signals, not one — which is why the conclusion held even
> though the mechanism was wrong.

The two signals, and why neither can reach human-authored prose:

| Signal | The only thing that populates it | Who reads it |
|---|---|---|
| `realized.has_prose` — the one Conformance actually uses (`composition-service/app/routers/conformance.py:288-291`, via `latest_completed_by_nodes` at `:191-229`) | a **completed per-scene `generation_job`** whose `result.text` is non-empty | the Conformance panel |
| `written_scene_id` / `written_at` (`app/db/models.py:266-268`) | book-service parse/import writing `scenes.source_scene_id` → a `chapter.scenes_linked` event → reconcile at `app/db/repositories/written_verdict.py:56-73` | the Plan Hub "written" badge (`routers/outline.py:335`) |

"Chat draft → human pastes → save draft" produces **neither**. So a third, manuscript-derived
signal is what is actually needed — and the ingredients already exist (`BookClient.get_draft`,
`tiptap_doc_to_text`, and server-side heading→scene matching at
`app/engine/prose_doc.py:58-78`); only the per-scene segmentation is missing.

**Net effect, unchanged and still the most important finding here: an author who completes an
entire book the only way currently possible gets zero of the product's own consistency/quality
signals.** Two whole feature surfaces are validated against a pathway this testing could not
exercise even by trying.

**Related discovery the run never saw.** The scene decompiler *computes* the back-link mappings
that would populate `written_*`, and **no caller anywhere writes them back** — even though
`app/engine/scene_decompile.py:284` documents an intended, idempotent-on-retry write-back
(*"so a retry after a failed write-back returns the SAME mappings"*). The frontend caller reads
only `work_resolved` and discards `res.mappings`. That is the missing human-driven path into the
entire `written_*` chain, and it is a small change.

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

**F-L. Conformance's chapter picker labels all 28 chapters "Untitled chapter," (#25)** even though
the exact same title data renders correctly one panel away. Recon found the cause: the picker uses
its own field precedence — `c.title || c.original_filename || #sort_order`
(`QualityConformancePanel.tsx:52-56`) — instead of the sidebar's `chapterDisplayTitle()` helper
(`features/studio/manuscript/partsTree.ts:26-30`), which deliberately never falls back to a storage
filename. **The same defect is copy-pasted into two sibling panels**, `QualityCriticPanel.tsx:54-58`
and `QualityHealPanel.tsx:110-114`.

> **CORRECTED 2026-09-12 by codebase recon — and the other half of this finding was promoted out of
> MEDIUM, see F-M.** F-L originally bundled the promise-coverage message in here as a second "rough
> edge," described as the analysis *"correctly reporting nothing to cover."* It is not correct, and
> it is not a copy problem.

**F-M. `no_tracked_promises` is reported identically whether the spec genuinely declares no
promises or the extraction call failed. (#24, promoted from F-L)** `extract_tracked_promises`
returns `[]` on **any** failure — including the truncated / unusable-content path
(`composition-service/app/engine/promise_audit.py:276-287`, `:290-310`) — and downstream that
becomes `error="no_tracked_promises"` (`app/engine/quality_report.py:255-262`). One code, two
opposite meanings, indistinguishable to every caller including the UI.

That is **the same silent-failure-reported-as-a-clean-empty-result shape** as F-C/F-D and the
save-on-blur family, and it belongs with them in severity rather than among cosmetic copy issues.
Separately, the UI discards the machine-readable code that is already on the wire —
`BookPromiseCoverageSection.tsx:50-54` branches on `c.error` and renders a fixed string — so the
user cannot distinguish "not set up yet" from "this feature is broken" without dev tools.

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

---

## 5. Verdict re-derived after the 2026-09-12 corrections

The corrections to F-A, F-B and F-L/F-M were significant enough that leaving §4 as the standing
recommendation would misinform the next reader. **The verdict does not flip. Its reasoning changes
substantially, and the work it implies gets much cheaper.**

**Re-derived verdict: NO-GO stands for the in-manuscript AI-authoring claim — but as a
reachability-and-disclosure failure, not a capability gap.**

What changed:

- **§4's first bullet under the NO-GO is now wrong as written.** It says *"the advertised in-Editor
  generation controls do not work at all."* They exist and are wired; each is gated behind an
  unmet, undisclosed precondition (F-A). The lived experience it described was accurate; the
  diagnosis was not.
- **Recommendation (1), "an actual working in-Editor AI-write path," is no longer the work.**
  The path exists. The work is un-gating it, disclosing why a control is disabled, and making
  `book_chapter_save_draft` reachable from the surface an author actually writes in.
- **Recommendation (2) is unchanged but re-aimed.** Conformance needs a manuscript-derived signal;
  it was never keyed to `written_*` as §4 implied.
- **One claim was checked and cleared.** The README advertises an *"Auto-Draft Factory — run a
  whole drafting campaign across chapters."* The tester never found it, so it was worth ruling out
  as a missed path. It is **real, production-grade, tested, and has a verified live run** — but its
  stages are `knowledge`, `translation`, `eval` only (`campaign-service/app/migrate.py:19`), its
  book-service client is GET-only, its output lands in `chapter_translations.translated_body`, and
  its own completion CTA points at the translation tab. It is a translation batch engine wearing a
  drafting name. **It does not refute this report's central finding**, and it adds two of its own:
  the name overclaims, and its only link lives in a Sidebar the Writing Studio never renders, so a
  user inside the Studio cannot reach it at all.

**What this means for the release decision.** The bar the PO set is *"a version that is really
usable, like the README marketing."* Measured against that, two README claims are flatly false
today — *"a co-writer that **can't** contradict your canon"* (the co-writer contradicted committed
canon in the same turn it was told it, #17; no critic ever fired) and *"conformance checking
against what you actually wrote"* (F-B: structurally impossible). Four more are reachable but
undisclosed, or misnamed.

The remediation is tracked in
[`2026-09-12-human-sim-remediation.md`](2026-09-12-human-sim-remediation.md), whose release gate is
this claims audit rather than a task count. Because F-A is a gating problem rather than a build,
**the flagship claim is recoverable in roughly a day of work** — which the original framing of this
report actively obscured, and which is the single most useful thing these corrections buy.
