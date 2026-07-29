# POC — can a weak model READ the author's raw material?

**Status:** MEASURED 2026-07-28 · local Gemma-4 26B QAT, $0 · N=4 runs
**Origin:** the PO's scope correction to `2026-07-28-intent-collection-fsm.md`:

> planforge đã làm đủ tốt nếu có plan sẵn rồi. cái chúng ta đang build là khiến model giúp human
> tạo lên nguyên liệu cho chính planforge — và planforge không chỉ consume markdown, nó build lên
> architecture để compiler khai thác.

---

## 0 · The correction that reframed the POC

The intent FSM (`7e68b98bd`) collects `outline_node` slots — which are the **output** of PlanForge's
`scenes` pass. It is a refine-**after**-plan tool. The gap is upstream: the material PlanForge
consumes to build its architecture at all.

And the first measurement inverted the assumption behind that too. The problem is not that the
author has not produced material. **It is that the machine cannot read the material they already
wrote.**

## 1 · The document, and what the live path does with it

The author's real Mị Đế planning document (`plan_run.source_markdown`, 4,279 chars, 14 headings):
premise, cast of four, relationships, the inciting incident, the opening arc, the long-range seeds,
the soul-layer system.

`ingest._parse_top_sections` requires `^# <n>. Title` — a **numbered** top-level heading. The author
wrote `# Bối cảnh`, `# Nhân vật`, `# Arc mở đầu`.

```
sections parsed by the live rules-mode ingest:  0
```

Fed through the real `propose_spec`: **0 characters · 0 mechanics · 0 variables · 0 arcs · 0 events**.
An entirely empty spec, no error, status `proposed`.

**This already happened on the live book.** `plan_run` holds a `rules | proposed | 4278` row for
Mị Đế. The author ran it, got nothing, and moved to `llm` mode (which reads the raw markdown and
bypasses the parser) — `llm | compiled | 4278`. They worked around a silent failure, probably
without knowing what it was. Across the whole DB, **rules is 251 of 281 runs**.

## 2 · Phase 1 — classification

Same document, split on *any* `#` heading (a deliberately dumb splitter — the model must do the
classifying, not the harness), the six kinds taken from `ingest.SECTION_KIND_MAP` rather than
restated.

| | regex (live) | gemma |
|---|---|---|
| sections recovered | **0 / 9** | **8 / 9** |
| calls | — | 1, no retry, 5.2 s |

`Bối cảnh` → `mechanics` · `Quan hệ` → `character_seed` · `Giọt nước tràn ly` → `arc_overview`.
Those are interpretive judgements, not pattern matches.

Its own missing-report — `planner_variables`, `writing_principles`, `open_questions` — **matched the
computed truth exactly.** So the coverage board can be driven by the model's self-report.

**A gap in the closed set, not in the model:** section [0] (`Mị Đế — Ý tưởng khởi đầu`, holding
`## Mục tiêu`: genre, tone, the world's cruelty) was classified `other` — correctly, because **none
of the six kinds is a home for premise/genre/tone.** The author's opening statement of what the book
IS has nowhere to go.

## 3 · Phase 2 — fixing the classifier is NOT enough

Same document, same `propose_spec`, only the classifier swapped:

| | regex | llm-classified |
|---|---|---|
| characters | 0 | **1 — named `[TBD]`** |
| mechanics | 0 | 3 |
| arcs | 0 | **0** |

`propose._characters()` returns **at most one** character — hardcoded `id="protagonist"`, read from a
`Name:`/`Tên:` field line. Four named characters collapse to one placeholder. `_parse_arcs_and_events`
needs an `Arc N: Title` header.

Rules mode is **format-bound to the fixture it was written against**, which `validate.py` already
confesses in a comment: *"this whole module started as the POC's OWN golden-fixture acceptance test
and its run_rules got reused directly as the LIVE per-user gate without ever being generalized."*

## 4 · Phase 3 — extraction, and the grounding test that decides it

Given the author's **prose**, emit the structured seeds. N=4 runs, byte-stable output:

| | rules mode (live) | gemma |
|---|---|---|
| characters | 1 (`[TBD]`) | **4** — Lâm Uyên · Tô Thanh Dao · Lâm Trạch · Huyết Vô Thường |
| arcs | 0 | 1 (`Arc mở đầu`) |
| mechanics | 3 section *titles* | 3 with actual rules (Tu luyện · Thanh Tâm Ấn · Thiết lập linh hồn) |
| calls | — | 1, ~8 s, $0 |

**Grounding — 4/4, zero invention in all four runs.** Checked mechanically by diacritic-folded
substring against the author's own text, never by a judge model (a judge asked "is this grounded?"
is the thing under test grading itself).

**My grounding check was wrong, and the record should say so.** It flagged
`Huyết Vô Thường (Huyết Chủ)` as invented. Both names are in the document —
`## 4. Huyết Vô Thường` and `# Seed quan trọng cho Huyết Chủ` — and the author does use them for the
same character. The model **merged two real aliases**, which is correct; my check demanded one
canonical surface form. Same lesson as the entity highlighter: a grounding check must match **all
surface forms**, not one string.

## 5 · What this answers

The PO's original question was *does gemma + a state machine understand and exploit, or only obey?*

**It understands.** Classifying setting-prose as mechanics, relationship-prose as cast, and
recognising two names as one character are judgements. And across four runs it **never invented** —
the failure mode that would have made this untrustworthy did not occur.

So the machine to build is **not** an interrogation:

```
READ what the author already wrote  →  show the coverage board  →  ask ONLY for what is genuinely absent
```

For this document that is 3 questions, not 10 — and the author has already done most of the work.

## 6 · Limits of this measurement, stated

- **One document, one book, one model.** Vietnamese, xianxia, one author's style. Nothing here says
  it generalises; the next arm should be a *badly*-structured document (a wall of prose with no
  headings at all), which is the real cold-start case.
- **Half B is unmeasured.** The conversation that asks for the three absent kinds has not been run.
  Everything above is the READ half.
- **Temperature 0.2**, and stability was measured (4/4 identical), but only on one prompt.
- `run_rules` moved 5/11 → 6/11 total, hard rules 1/3 → 1/3. The hard rules are the fixture-bound
  ones `validate.py` demoted to advisory — a genuinely general validator is separate work.

## 6b · Half B — the conversation. It failed, and the failure is the finding.

Half A measured the READ. Half B measured the loop that turns a gap into a filled section:

```
READ → for each absent kind, SEARCH what the author already wrote → ask ONLY for what is missing
     → compose → RE-INGEST → did the gap actually close?
```

**Three failures, one of them mine three times over.**

### The search step, and the two-step trap

The first search returned **0 of 3** — including for `writing_principles`, whose material is
demonstrably in the document (`Thế giới cực kỳ tàn khốc, lấy lợi ích và sinh tồn làm trung tâm`, and
the author's own blockquote `> Lòng tốt thường bị xem là điểm yếu.`).

Controlled arms found the cause, and it was not attention or context size:

| arm | change | writing_principles recovered |
|---|---|---|
| phase-4 | "is content of this kind ALREADY THERE?" — a yes/no gate | 0 |
| A | "quote the sentences of this kind" — same call, same document | **3** |
| B | one kind per call + a worked example | 0 |
| C | numbered sentences, answer = indices (selection) | 0 |
| **D** | quote-first · one kind per call · **no example**, **no gate** | **3/3 probes** |

Two mechanisms, both mine:

1. **A weak model offered an easy "no" takes it.** Retrieval and absence-adjudication had been
   fused into one step, and the adjudication half swallowed the retrieval half.
2. **A worked example is double-edged.** Adding one narrowed recall to lines *resembling the
   example*; the author's real lines look nothing like it, so they were dropped.

Note that arms B and C were my "shrink every decision" hypothesis, straight from §5 of the FSM spec.
**They made it strictly worse.** §5's lever is real for *choosing from a set*; it is not a general law.

### The question step — diagnosed and fixed

The prompt was handed `md[:2500]`: **42% of the document truncated**, and the last thing inside the
window was the betrayal plot. Two of three questions came back as *the same trap question*.

| arm | cross-kind overlap | grounded in the story |
|---|---|---|
| A · truncated + thin prompt | **100%** | 0/3 |
| B · full doc + on-topic constraint + example | 7% | 1/3 |
| **D** · full doc + constraint + **no example** + must name something real | 13% | **3/3** |

### The round-trip caught what classification hid

The composed `open_questions` section re-ingested under the right kind (94% author-word overlap — no
laundering) and `propose_spec` still extracted **zero**: `_extract_open_questions` required `- [ ]`
checkboxes. **The gap looked closed at the classifier and stayed open at the compiler** — the same
format-bound disease, one layer deeper and far better hidden. Fixed (checkboxes still win; bullets
are the fallback).

### The decisive result: it reads, it does not judge

Fixing recall cost precision — with no way to say "nothing here", retrieval returns *something* for
every kind. The obvious repair is retrieve-then-verify. **It failed, and then failed in every
direction**, on the same six lines with a human labelling written down first:

| verifier framing | kept correct | false keeps | **missed** |
|---|---|---|---|
| strict + examples of wrong kinds | 0/3 | 0/3 | **3/3** |
| permissive, non-exclusive | 3/3 | 3/3 | 0 |
| ranked 0–3 | 3/3 | 2/3 | 0 |

Strict says **no** to everything. Permissive says **yes** to everything. Ranked scores almost
everything a 3. In 18 calls it discriminated **once**. The prompt decides *which degenerate answer
you get*, not whether there is discrimination at all.

**So this is not a prompting problem.** On this task the weak model has no usable category boundary —
and it could not, because the boundary is not in the text: `Lòng tốt thường bị xem là điểm yếu` is
simultaneously a world rule and a tone principle. Forcing an exclusive verdict destroys it either way.

⇒ **The machine must never adjudicate.** — **This conclusion was WRONG. See §6c.**

**Capability map, measured:**

| the model is GOOD at | the model FAILS at |
|---|---|
| classifying a section (8/9) | judging whether something is absent (0/3, then all-yes) |
| extracting entities, grounded (4/4, 4 runs, zero invention) | category boundaries on multi-category text (1 discrimination in 18) |
| retrieving by kind with high recall (3/3 probes) | asking a good question **unless** constrained + fully-informed + told to name something real |

## 6c · §6b's conclusion was wrong. The lever is the QUESTION SHAPE.

§6b concluded, from three verifier framings that each collapsed to a constant, that *the weak model
has no usable category boundary and must never adjudicate*. That conclusion was **not safe**, and it
is now retracted: all three arms asked the same question shape — **binary membership on one item in
isolation** — so what they measured was that shape, not the model.

Reframed as the task the model demonstrably already does well (§2 measured classification at 8/9),
the identical judgement scores **macro F1 0.85**.

| method | mechanism | result |
|---|---|---|
| binary · strict + reject-examples | membership | F1 **0.00** — degenerate all-no |
| binary · permissive | membership | 0.55 — degenerate all-yes |
| binary · ranked 0–3 | membership | 0.60 |
| binary · **thinking ENABLED** | membership | 0.50 |
| self-consistency vote ×3 | membership | 0.29 |
| rank the list, take top-k | comparative | fails to emit an ordering at all |
| few-shot, positive AND negative | membership | 0.86 *(8 lines)* |
| **classify · 6-way, single label** | **closed-set assignment** | **0.83** *(18 lines)* |
| **classify · 6-way, MULTI label** | **closed-set, non-exclusive** | **0.85** |

Measured on 18 lines from the author's real document, labelled before the run, macro-F1 so a
degenerate arm cannot score well.

### The residual is one kind, and the label was at fault — not the model

Errors are not spread. `character_seed`, `arc_overview`, `open_questions` all score **1.00**;
everything hard is `writing_principles` (0.67 single-label). Because
`Thế giới cực kỳ tàn khốc, lấy lợi ích và sinh tồn làm trung tâm` **is** a statement of how the world
works *and* a statement of the story's tone. A single-label classifier must destroy one of them, and
which one is a coin toss dressed as a decision. Allowing overlap: **0.67 → 0.86**.

### Reasoning does not help here — measured, because the PO asked

Every call this session ran with `_NO_THINK` (`reasoning_effort: "none"`), so it was the one variable
never varied. Turning it on: **macro F1 0.83 → 0.83**, and on the hardest kind **0.67 → 0.40** — with
thinking on it reclassified the author's own tone lines as `other`. It became more literal, not more
discerning. Worth knowing; not the lever.

### The pattern that actually generalises

**Every hand-authored steering instruction I added made it worse. Four times:**

| what I added | intent | effect |
|---|---|---|
| a worked example of the kind | define the target | recall → 0 (narrowed to things resembling the example) |
| "be strict" + examples of wrong kinds | raise precision | **all-no**, including the author's own emphasised blockquote |
| a tie-break rule for the recurring collision | resolve ambiguity | `writing_principles` 0.86 → **0.60** |
| thinking enabled | better judgement | hardest kind 0.67 → **0.40** |

**Every improvement was structural** — a change to the shape of the question, or the removal of an
artificial constraint: binary → closed-set assignment; exclusive → multi-label; drop the example;
drop the yes/no gate. Not one of them was a better instruction.

### And my instrument was wrong more often than the model was

Recorded because it is the more useful lesson:

- a grounding check flagged `Huyết Vô Thường (Huyết Chủ)` as invention — both names are the author's,
  merged correctly (§4);
- the rank arm was scored **0.00 twice** on two different parser bugs (prose around the JSON, then a
  bare array where I only handled an object). Re-run properly it is still poor — the model does not
  emit an ordering — but I had dismissed it for the wrong reason;
- "grounded in the cast" was used as a question-quality metric; the questions were grounded **and**
  off-topic, so it measured nothing.

**What this changes for the design.** The machine *can* adjudicate — ask it as a classification, let
labels overlap. Propose-to-the-author remains right, but for the reason the FSM spec gave in the
first place (authorial taste, and trust), **not** because the model is incapable of judging.

## 6d · Constrain the output (the PO's correction) — and an arm I had dismissed twice comes back

Every call in this POC used `response_format: {"type": "text"}` and then hand-parsed the reply. That
single decision produced **three measurement bugs** — and twice I scored an arm 0.00 and dismissed a
working method because my own parser failed.

`provider-registry`'s `forwardOptionalChatFields` passes `response_format` **and `seed`** straight
through to LM Studio, where llama.cpp enforces the schema at the **grammar layer**. Parse failure
stops being a possible outcome.

| | text + hand parser | `json_schema` enforced |
|---|---|---|
| parse failures | **2** (in this run alone) | **0** |
| macro F1 | 0.88 | 0.86 — *unchanged, within noise* |
| same seed, second run | — | **identical 18/18** |
| RANK arm, precision@4 | 1/4 | **3/4** |

Three things worth separating:

1. **Enforcement does not cost quality.** The worry that constrained decoding fights the model's own
   next-token preference did not materialise here.
2. **Determinism is the real prize.** A fixed seed reproducing 18/18 means a change in a number is a
   change in the system, not sampling noise. Given how much of this POC turned out to be *my
   instrument* rather than the model, that matters more than the F1.
3. **The rank arm was never broken.** It failed to emit an ordering; with a schema forcing a full
   permutation it puts 3 of the 4 true lines in the top 4. I had dismissed a working method twice.

**Shipped into the intent FSM** (`slots.value_schema` / `candidates_response_format`): a closed-set
slot's enum is now a **decoder constraint** rather than a post-filter, derived from the registry so
`beat_role` carries the book's own beat keys and `tension` carries an *integer* enum. Live-proven —
`beat_role` returned 2 valid keys in 1.3 s, `tension` returned real integers in 2.1 s, `llm_calls 1`
on both.

Two deliberate limits, because the constraint must not become a new hole:
- the post-filter **stays** — a provider that ignores `response_format` must not silently pass an
  invalid value through;
- a provider that **rejects** the schema falls back to free-form instead of failing the slot, since
  `response_format` support is not a platform requirement. Same shape as
  `translation-service._entity_response_format`, which already does enum + fallback.

## 6e · The loop rebuilt on what won, and the cold-start arm

Both run with **only** the framings that won their controlled arm — multi-label classify,
quote-first search with no gate and no example, the constrained-and-grounded question — every call
grammar-enforced at a fixed seed, and **no model verification step at all** (three framings of it
each collapsed to a constant, and the one tie-break rule I hand-wrote cost 0.26 F1).

### Arm 1 · the author's structured document — **zero questions asked**

Multi-label covers **5 of 6 kinds**, against 3 under the single-label read. The lift comes entirely
from letting a section be two things: `Mị Đế — Ý tưởng khởi đầu` is *mechanics AND
writing_principles*; `Hàng vạn năm sau` is *arc AND character AND open_questions*.

`planner_variables` was the only kind reported absent — and the search found it **already written**.
So the loop asks the author **nothing**. Everything they needed was in the document; the machine
simply could not read it.

**And that result is partly too good, which the record has to say.** Removing the yes/no gate bought
recall at a measured cost in precision, and here is that cost at loop level: the line retrieved for
`planner_variables` (*"Chỉ có Chân Linh là bất biến"*) is a rule about soul layers, **not a state
variable**. The loop concluded "nothing to ask" on a false positive.

So the failure mode has *inverted*, not vanished: it used to **over-ask** (3 questions, 2 off-topic);
it now **under-asks**. Both are wrong, and which is worse is an author's call — which is precisely
why the retrieved lines must be shown for a keep-or-drop rather than acted on.

### Arm 2 · cold start — a wall of prose, every heading stripped

Same content, 3,204 chars, no headings, no bullets. The real ingest reads **0 sections** and now
*says so* (the guard shipped in `6bc2ed59a`). Segmented into 18 four-sentence groups — there is no
structure to lean on — and classified: **5 of 6 kinds reconstructed.**

Fed back through the **real** `ingest` + `propose_spec`, against the author's own document:

| | author's doc | cold-start reconstruction |
|---|---|---|
| sections | 9 | **5** |
| characters | 4 | **1** ← |
| mechanics | 2 | 1 |
| arcs | 1 | 1 |

**Cold start half-works, and the gap is exact.** From nothing readable at all it produces a document
PlanForge parses — but the four named characters collapse to one.

The cause is not the model. The reconstruction files every character group under one `# Nhân vật`
heading as flowing prose, and `propose._characters` needs `## ` sub-blocks to see more than one
person. **The format-binding fixed for the author's hand-written document bites again on
machine-written text.**

⇒ Grouping by kind is not enough: the reconstruction must emit the **sub-structure the extractors
read**, not merely the right heading. That is a bounded, known piece of work rather than an open
question — and it is measurable to the character.

## 7 · Deferred / follow-ups this produced

| id | finding | gate |
|---|---|---|
| `D-PLANFORGE-RULES-INGEST-SILENT-ZERO` | a 0-section ingest produces an empty spec with no signal — the author cannot tell a failed read from an empty book | fix-now candidate: it is a guard, not a refactor |
| `D-PLANFORGE-RULES-FORMAT-BOUND` | `_characters` caps at one; arcs need `Arc N:`; the extractors only fit the original fixture | large/structural (gate 2) — the LLM read is the replacement, not a patch |
| `D-PLANFORGE-NO-PREMISE-KIND` | the six ingest kinds have no home for premise/genre/tone; the author's opening section is dropped as `other` | small — widen `SECTION_KIND_MAP` |
| `D-COLDSTART-SUBSTRUCTURE` | a reconstruction from headingless prose files each kind under one heading, so `_characters` (which needs `## ` sub-blocks) reads 1 person where the author's own document yields 4. Measured exactly: sections 9→5, characters 4→1 | not blocked — emit the sub-structure the extractors read |
| `D-SEARCH-OVER-RETRIEVES` | removing the yes/no gate bought recall at a measured precision cost; at loop level that turned "over-ask 3 questions" into "under-ask zero" on a false positive. The retrieved lines must be shown to the author for keep-or-drop, never acted on | design, not a bug — the propose-to-author step already planned |
| ~~`D-LLM-TEXT-FORMAT-HAND-PARSE`~~ | **CLEARED** — not deferred: it was unbuilt work, not debt. A shared `engine/llm_json.call_json` (schema-first, free-form fallback, post-filter retained) plus every site with a REAL closed set migrated: `plan` beat_keys · `world_plan` WORLD_KINDS · `promise_audit` verdicts · `motif_mine` kinds+actants · the intent FSM's slot enums. All four production schemas live-verified against the real provider. The shape-only sites keep text+tolerant-parse **on purpose**: with no enum, enforcement buys shape alone, and the measured win was the enum | — |
