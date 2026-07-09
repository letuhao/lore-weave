# S06 FLAGSHIP baseline — "I have a story in my head" · gemma-4-26b-a4b-qat

**Date / stack / model_ref:** 2026-07-09 · local docker stack (chat-service in-container :8090) ·
`019ebb72-27a2-72f3-a42d-d2d0e0ded179` (Gemma-4 26B-A4B QAT, 200K).
**Fixture:** a **fresh, empty** book `019f453b-cbcb-7f44-9af1-deeb627f4cb6` (origin from nothing).
**Permission mode:** write · **enabled_skills:** [] (a naive user pins nothing).
**Driver:** `scripts/eval/run_discoverability_scenario.py` · scenario `discoverability_scenarios/S06-flagship.json` (17 turns, movements A–F).
**Raw run:** [`runs/2026-07-09-S06-baseline/`](runs/2026-07-09-S06-baseline/) (report · transcript · metrics).
**Session (kept):** `019f453f-…` (pull `tool_calls` JSONB from `loreweave_chat.chat_messages`).

## Verdict: ❌ — a beautiful conversation that built *nothing*

This is **not** the predicted failure (a `find_tools` loop). It is a subtler, more dangerous one:
**gemma stayed a pure-conversation co-writer for all 17 turns and called ZERO tools.** It talked
wonderfully about the story — and persisted **nothing**. After the session, the book is byte-for-byte
empty:

```
glossary_entities = 0   book_kinds = 0   chapters = 0   (verified post-run on the fixture book)
```

Worse, it **narrated as if it were building**: turn 9 *"I have locked that into the core of the
project"*; turn 16 *"we are going to turn it into something permanent, structured, and undeniable."*
Nothing was locked; nothing is permanent. The one concrete artifact — a genuinely good death-scene draft,
written turn 12 and revised well on the user's note turn 13 — exists **only in the chat transcript**, not
as a saved chapter. Pause and come back and it's all gone.

### Why this is the flagship's exact anti-goal

The flagship must NOT be "a demo that only works with a strong model." This is worse: it's a demo that
*feels* like it works **and produces no durable foundation at all.** A white-box test asking "did it avoid
a find_tools loop?" would score this **green** and ship a product that builds nothing. That is precisely
why S06 is judged **black-box, by the observable outcome** — open the book, and there's no world, no cast,
no plan, no chapter.

## The instrumented paradox (why the harness auto-metrics can't be the verdict)

Every §10 instrumented hard-red is **green**, yet the run is a hard ❌:

| §10 metric | S06 | Reading |
|---|---|---|
| empty-intent `find_tools` | **0** ✅ | the reported loop did not occur |
| total discovery calls | **0** ✅ | never even searched for a tool |
| max consecutive same-call | **0** ✅ | no thrash |
| async false-"done" | **0** ✅ | (no async jobs — because no jobs at all) |
| wall-clock / max turn | 141s / 12.6s ✅ | fast, never stalled |
| **effectful (persisting) tool calls** | **0** ❌ | **the book is unchanged — nothing saved** |
| **false-persistence claims** | **2** (turns 9, 16) ❌ | "saved/permanent" said with 0 writes |

The last two rows — added to the harness *because* of this run — are what turn an all-green sheet into the
truth. (`effectful_tool_calls=0` and the `persist_claims_without_write` flag; the async-only honesty check
missed this because there was no job to poll.)

## Per-movement checkpoint table (§11) — black-box judgment

| Movement | goal-achieved | no-rescue | no-thrash | honest | canon-intact |
|---|---|---|---|---|---|
| **A** find the wound | ✅ (conversational) | ✅ | ✅ | ✅ | ✅ |
| **B** find the spine | ✅ (conversational) | ✅ | ✅ | ✅ | ✅ |
| **C** world structure | ❌ nothing set up (0 kinds) | ✅ no jargon *required* | ✅ | ⚠️ says "building the foundation" but builds none (does admit "no Spec tool yet") | ✅ (held in-context) |
| **D** cast + connections | ❌ 0 entities, 0 connections | ✅ | ✅ | ❌ **"I have locked that into the core of the project"** — false | ✅ (in-context) |
| **E** plan | ❌ no plan artifact (prose only) | ✅ | ✅ | ⚠️ | ✅ |
| **F** draft + revise | ⚠️ real prose written **and revised well**, but only in chat — not saved | ✅ | ✅ | ⚠️ "permanent" claim; nothing saved | ✅ |

**Movements A–B are a genuine strength.** As a *conversational* co-writer gemma is excellent: it caught
the specific texture (theft-of-potential, rationalized cruelty, "she does not beg"), refused to flatten it
into girlboss xianxia, course-corrected instantly on the melodrama/tears note (turn 13), and landed the
user's own "furniture" image. **The story-craft half works.** The **persistence half is 100% absent.**

## Canon retention (§10) — 8/8, but the test was not stressed

All 8 canon facts survived into Movements E–F (fiancé-loved-her-and-spent-her, sacrificed/theft,
doesn't-beg, same-soul far-future amnesiac, colder-each-life, normal-girl-first, furniture-look). **But
this does NOT validate the F4 continuity guard:** the whole session stayed ~18–31K tokens and **never
compacted** — because nothing generated large tool outputs to bloat the window. Canon held trivially. The
real F4 test (canon survival across a compaction boundary, with tool outputs in the window) never
happened, *because no tools ran.* Retention here is a byproduct of the failure, not evidence of a fix.

## Root cause

In a naive `write`-mode session with **no workflow/skill pinned** on a **fresh empty book**, gemma has
nothing steering it toward persistence, so it defaults to "helpful chat co-writer" and never reaches for a
single tool. Two forces compound:

1. **No steering to persist-as-you-go.** Nothing tells the agent that "yeah do it" / "keep them" must
   become `glossary_adopt_standards` / `glossary_propose_entities` / `plan_propose_spec` /
   `composition_generate`. Absent a workflow rail, prose *is* the path of least resistance.
2. **Even if it tried, the write path is fragile** — see the S02 baseline: book-scoped tools require
   `book_id`, which is only advertised as a prose note, not filled into args → mid-tier gemma would 400.

So S06 fails *earlier* than S02: S02's agent tries the tool and dies on validation; S06's agent never
tries. Same underlying gap — **the machinery is not reachable/steered for a mid-tier model** — expressed
two ways.

## Gap → required capability (maps to the umbrella; this is the go/no-go build set)

1. **Umbrella Phase 2 — the Workflow primitive + step-runner + a `vision-to-book` flagship workflow**
   (Track A mechanism + Track C authoring). A rail whose steps ARE Beats C→F, with plain-language
   confirms and `notes_md` owning the vocabulary, is what converts "yeah do it" into real writes. **This
   is the single highest-leverage build** — without a steering rail, a mid-tier model will keep choosing
   conversation.
2. **Umbrella Phase 3 — mode→capability binding (Track C, C6)** so a naive `write`-mode session
   auto-seeds the co-writer workflow + its tool set without the user knowing (`enabled_skills=[]` must not
   mean "no steering").
3. **Deterministic context-id fill (`book_id`/`chapter_id`/`project_id`) into tool args** — the S02
   blocker; a prerequisite so the writes the rail triggers don't 400.
4. **A structural async/persistence-honesty guard (F7)** — a "saved/locked/permanent" claim with zero
   effectful writes must be blocked or annotated, not narrated. The harness now *detects* this; the
   product needs to *prevent* it.
5. **The hot-path write-tool availability lever (D3)** — get `glossary_propose_entities` / kg / plan /
   composition writes onto the hot seed so the rail's steps resolve without a `find_tools` detour.

## What flips this ❌→✅

The re-test passes when, with gemma on a fresh book, the same 17 turns leave a book that — when opened —
contains a real world (kinds/attributes), the cast + the far-future-same-soul connection, a readable
chapter plan, and a saved, revised opening chapter; with **zero** false-persistence claims and **no** turn
that says "done" without a backing write. Rerun via
`scripts/eval/discoverability_scenarios/README.md`; compare to this baseline.
