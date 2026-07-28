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

⇒ **The machine must never adjudicate.** Retrieve with high recall, show the author, let them keep or
drop. That is one glance for them and it is the only step that can actually decide. It is also what
the intent-FSM spec already said — *the agent proposes, the author corrects* — except this is now
measured, and the measurement says the judging step must **not exist**, not merely be reviewable.

**Capability map, measured:**

| the model is GOOD at | the model FAILS at |
|---|---|
| classifying a section (8/9) | judging whether something is absent (0/3, then all-yes) |
| extracting entities, grounded (4/4, 4 runs, zero invention) | category boundaries on multi-category text (1 discrimination in 18) |
| retrieving by kind with high recall (3/3 probes) | asking a good question **unless** constrained + fully-informed + told to name something real |

## 7 · Deferred / follow-ups this produced

| id | finding | gate |
|---|---|---|
| `D-PLANFORGE-RULES-INGEST-SILENT-ZERO` | a 0-section ingest produces an empty spec with no signal — the author cannot tell a failed read from an empty book | fix-now candidate: it is a guard, not a refactor |
| `D-PLANFORGE-RULES-FORMAT-BOUND` | `_characters` caps at one; arcs need `Arc N:`; the extractors only fit the original fixture | large/structural (gate 2) — the LLM read is the replacement, not a patch |
| `D-PLANFORGE-NO-PREMISE-KIND` | the six ingest kinds have no home for premise/genre/tone; the author's opening section is dropped as `other` | small — widen `SECTION_KIND_MAP` |
