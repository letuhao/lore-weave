# Work Assistant Mode — spec set

An all-day personal work companion built on LoreWeave: chat/voice capture → private diary → per-user
knowledge graph → recall + coaching. This feature is **large** (XL umbrella), so it is decomposed into an
overview + per-sub-feature **detailed** design docs, rather than one flat spec.

**Status (2026-07-11):** overview at **v4** — **RED-TEAMED**. Four adversarial reviewers + 2 verifiers found
**18 P0s** (all code-verified) across the three new specs. See **[`RED-TEAM-2026-07-11.md`](RED-TEAM-2026-07-11.md)**
— read it before building anything. Three brand-new locked decisions came out of it (**D16** diary-taint,
**D17** memory amendment, **D18** erasure-is-unbuilt), and three existing ones were **reversed** (D6 was
fail-open on a privacy flag; D9's temporal model made diary facts invisible to recall; D10 guarded 2 of 7
egress paths). `01-data-architecture` §6 and §8 rewritten. `08-coaching` re-scoped (P1 = reflection, not
coaching). Detail docs `02`–`13` to follow. UI drafts: `design-drafts/work-assistant/`.

> ⚠️ **Two red-team findings are live platform holes today, independent of this feature** — the wiki's
> unauthenticated auto-generated per-entity articles, and the public-MCP gateway's domain-only (never
> per-resource) scoping. They deserve a fix track regardless of whether the assistant ships.

---

## How to read this folder

| Doc | What it is | Read when |
|---|---|---|
| [`00-overview.md`](00-overview.md) | The umbrella: 15 locked decisions (D1–D15), architecture map, phasing, edge cases, the v1→v3 review record. **The single source of decisions.** | Start here for scope + the "why" |
| [`01-data-architecture.md`](01-data-architecture.md) | Cross-cutting data model: every new/changed table + column + event + index across all services, tenancy scope keys, the temporal (wall-clock valid-time) model, the retention/erasure copy-set. Extends `docs/DATA_ARCHITECTURE.md`. | Before any BUILD that touches storage |
| `02`…`13` (below) | **Detailed** design per sub-feature — contracts, schemas, prompts, sequence, acceptance. Each is buildable on its own. | When implementing that sub-feature |

Detail docs never re-decide what `00-overview.md` locks; they *implement* it. If a detail doc needs to
change a decision, it amends `00-overview.md` (with a review-record line), not silently.

### ⚠️ Prerequisite — build this FIRST, before any assistant code

[`docs/specs/2026-07-11-publish-independent-kg-indexing.md`](../2026-07-11-publish-independent-kg-indexing.md)
— spun out of §4.7/D15 because it is **platform-wide** (it changes how *every* book builds its KG, not just
the diary). Publish stops gating extraction; an explicit "index / add to knowledge" action drives it. The
diary's "keep entry" is merely its first consumer. **This ships before the assistant feature.**

### Method — the self-ask loop (apply to every detail doc)

Each detail doc is written as a chain of *questions we must answer before building*: **what is it exactly ·
what data · what algorithm · what is the LLM's role · where does the "truth" come from · how does it fail?**
Each is answered concretely; anything unanswerable becomes an explicit open decision, never a silent
assumption. [`08-coaching-reflection.md`](08-coaching-reflection.md) is the worked example — it is where the
question *"where does the true knowledge to detect problems come from — model knowledge, or cited sources?"*
is answered (short version: **evidence** comes from the user's own data, **the standard** comes from a
versioned rubric stored as data, and **advice** must cite a curated KB or a web source; the strong model is a
*reasoning* engine, never the source of the standard).

---

## Sub-feature decomposition

Each row is a **big** sub-feature with its own detailed-design doc and its own UI-draft subfolder. Phase and
dependencies come from `00-overview.md` §8.

**All 13 detail docs are now written** (✅). Every one is red-team-corrected.

| # | Detail doc | Sub-feature | Phase | Key decisions | UI drafts |
|---|---|---|---|---|---|
| 01 | **[`01-data-architecture.md`](01-data-architecture.md)** ✅ v2 | **Data architecture** — §6 temporal + §8 erasure **rewritten** post-red-team | all | D1,D5,D6,**D9,D18** | — |
| 02 | **[`02-assistant-mode-session.md`](02-assistant-mode-session.md)** ✅ | **Assistant mode & session** — nav + C22 5th intent, provisioning (idempotent, identity, tz, **partial-failure state**), session binding, **multi-device write serialization**, home strip | P1 | D7,D12,D13 | `assistant-home/`, `onboarding/` |
| 03 | **[`03-book-kinds-diary-gui.md`](03-book-kinds-diary-gui.md)** ✅ | **Book kinds & diary GUI** — `books.kind` + **DB-trigger immutability**, all **4** create paths, diary reuse of the book workspace, **hidden from the library grid** | P1 | D10,D14,**D16** | `diary/` |
| 04 | **[→ own spec](../2026-07-11-publish-independent-kg-indexing.md)** | **Publish-independent KG indexing** (platform change — *spun out, ships first*) — `kg_indexed_revision_id` + own KG sweep, "add to knowledge" action, new `chapter.kg_indexed` event, `kg_exclude` | **Prereq** | D15, §4.7 | `diary/` (index action) |
| 05 | **[`05-work-capture-ontology.md`](05-work-capture-ontology.md)** ✅ | **Work capture & ontology** — work kinds seed, `flavorWorkCapture` (kind-resolved server-side), **two-colleagues-named-Minh disambiguation**, `statement` fact type, no trait facts about third parties, capture-decision data path | P1(entities)/P2(facts) | D4,D5,D6 | `review/` |
| 06 | **[`06-journal-distiller.md`](06-journal-distiller.md)** ✅ | **Journal distiller** — **map-reduce** (not 1 call), durable chunk checkpoints, **write-time `local_date`**, bounded catch-up sweep (period digest, not 21 jobs), **injection laundering** guard, giant-paste guard | P1 (lite) / P2 (extract) | D3,D8,D9 | `diary/`, `review/` |
| 07 | **[`07-recall-search.md`](07-recall-search.md)** ✅ | **Recall & search** — the ordinal fix (**the headline promise had no query**), date-filtered `:Fact` read, `chat_search_sessions` + trgm, **`memory_*` diary leak**, contradiction/supersession | P1 | D1,**D9,D16,D17** | `assistant-home/` |
| 08 | **[`08-coaching-reflection.md`](08-coaching-reflection.md)** ✅ | **Coaching & self-reflection** — splits *reflection* (user thinks, we scaffold) from *coaching* (we judge, rubric-grounded); deterministic detectors + cite-or-drop; honesty constraint (never judge a meeting we didn't observe); rubric-as-data; cited coaching KB | P1 (reflection + templates) / P2 (rubrics+KB) / P5 (longitudinal) | D13, §4.5, PUX-4 | `coaching/` |
| 09 | **[`09-settings-consent-privacy.md`](09-settings-consent-privacy.md)** ✅ | **Settings, consent, privacy & erasure** — owns the red team's biggest findings: the **7 egress paths** (wiki, public-MCP, `memory_*` leak, notifications, listings), consent one-home + fail-closed gate, **egress disclosure** (D4 gates the write, not the send), spend degrade ladder, **erasure is unbuilt** (D18), memory amendment (D17), the **operator** adversary | **P1** (settings + all egress guards) / P2 (erasure) | D6,D7,D9,D10,**D16,D17,D18** | `settings/` |
| 10 | **[`10-cost-spend-lane.md`](10-cost-spend-lane.md)** ✅ | **Cost & spend lane** — corrected envelope (**90–120 calls/day**, not 30–50), generic lane column ×3 tables + **daily** sub-cap, and the **degrade ladder** when the cap dies at 2pm | P2 | §6 | `settings/` |
| 11 | **[`11-scheduler-proactive.md`](11-scheduler-proactive.md)** ✅ | **Scheduler & proactive** — the one true platform hole; headless runs **cannot pass confirm gates** (⇒ draft-into-inbox); **content-free notifications**; don't nag a person on holiday | P3 | D4,D8,**D16** | `assistant-home/` |
| 12 | **[`12-voice-parity.md`](12-voice-parity.md)** ✅ | **Voice all-day** — why it's P4: voice turns are journaled but **never captured** and **billed 0/0**; route through the text agent loop; never ambient | P4 | D2,D11 | `assistant-home/` |
| 13 | **[`13-frontend-shell-mobile.md`](13-frontend-shell-mobile.md)** ✅ | **Frontend shell & mobile** — 🔴 the FE loads only the **first 50 messages** (an all-day session is unreadable); responsive shell is net-new shared infra; every mandatory review gate currently **dead-ends on mobile** | P1 | D12 | all subfolders |

**Build order:** **[publish-independent-kg-indexing](../2026-07-11-publish-independent-kg-indexing.md) (prereq — ships first)** →
`01`/`03`/`02`/`05(entities)`/`07`/`08(reflection)`/`13` (P1) → `05(facts)`/`06`/`08(rubrics+KB)`/`09(retention)`/`10` (P2)
→ `11` (P3) → `12` (P4) → `08(longitudinal)` (P5).

---

## UI drafts (detailed, per sub-feature)

`design-drafts/work-assistant/` currently holds the **north-star gallery** (4 overview screens). Because each
sub-feature is big, detailed screens live in per-area subfolders (mirroring the decomposition), each with its
own `index.html`:

```
design-drafts/work-assistant/
  index.html              ← gallery / north star (the 4 overview screens)
  01-assistant-home.html  02-diary-timeline.html  03-end-of-day-review.html  04-weekly-reflection.html
  assistant-home/         ← detail: empty (week-1) · active capture · end-my-day · voice-disabled · mobile
  diary/                  ← detail: timeline · entry detail · edit · supplement entry · "add to knowledge" · mobile
  review/                 ← detail: full flow · low-signal day · flood/bulk · rejected/tombstone · mobile
  coaching/               ← detail: reflection · scorecard · practice session · "what I know" map · trend
  settings/               ← detail: assistant settings · consent (fail-closed) · timezone · delete-my-day · spend
  onboarding/             ← detail: C22 5th intent → provision flow → first session
```

Each detail-design doc (`02`…`13`) links its matching UI-draft subfolder; each screen carries a
`draft/screen X/Y` frame note and cites the decision(s) it realizes.

---

## Open PO questions (carried from `00-overview.md` §12 + UI drafts)

1. Trust-tier auto-accept across the 3 review gates (touches the LOCKED write-gating law).
2. Which 2–3 work-coach templates ship first.
3. Retention defaults (proposed: 90-day raw sessions; diary + KG until user-deleted).
4. BL-15 amendment wording for the 5th onboarding intent.
5. (from drafts) Activity heatmap/streak — motivating or pressuring? Nightly review — opt-in or nudge?
   Inline forget/correct from "what I know about your work"?
6. (structural) Should `04-publish-independent-indexing.md` graduate to its own top-level spec, since it is a
   platform change affecting all writers, not just the assistant?
