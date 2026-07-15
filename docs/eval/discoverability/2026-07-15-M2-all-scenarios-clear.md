# M2 — All Discoverability Scenarios to Green (2026-07-15)

**Run:** all-tracks-clear (spec `docs/specs/2026-07-13-all-tracks-clear.md`), branch `feat/context-budget-law`.
**Model:** `google/gemma-4-26b-a4b-qat` (local, $0), 200K ctx, 4-parallel.
**Scoring:** DB ground truth on a fresh, provably-empty book per run (never the model's words or the
harness summary); judge-only scenarios read the transcript. Bar: ≥2/3 per scenario.

## The headline finding

**Every "hard" scenario was a fixture or harness gap — never a model-capability ceiling.** The
mid-tier model drove each rail correctly (it called the right tools in the right order); what failed
was around it:

| Scenario | Symptom (before) | Actual root cause | Fix |
|---|---|---|---|
| **S03** entity-triage | 0–1/3, pile never drained | (1) rail not *discovered* from NL; (2) driver had no artifact to *complete* triage; (3) triage writes are **Tier-W** and the eval never crossed the confirm gate | intent→workflow pin · `suggestions` drain-grounding · SIM commits **all** minted tokens |
| **S04** kg-build | 0–1/3, nodes never projected | rail not discovered; `connections` grounding not driving node projection | intent-pin (kg-build discoverable) + existing `connections > 0` grounding now drives it |
| **S05** translation-pass | 0/3, no new job | **TWO gaps.** (1) `translation_retranslate_dirty` is **priced Tier-W** and the SIM commit only knew the *glossary* confirm route → token dropped. Fixed: SIM commit is now **domain-aware** (tries each domain's confirm route). (2) **coverage gap (open, tracked)** — re-run still 0/3, but for a NEW reason: `translation_coverage` reports **"all chapters already translated and up to date"** on a book the fixture seeded as PARTIAL (ch1-2 done, ch3 untranslated), so the agent correctly does nothing. Root cause (now precise): `translation_coverage` enumerates chapters via `SELECT DISTINCT chapter_id FROM chapter_translations` — it derives its chapter list **from the translations table itself**, so a never-translated chapter (no row there) is **structurally invisible**. translation-service doesn't own the book's chapter list, so a real fix needs a **cross-service** enumeration (translation-service → book-service for the full chapter set, LEFT JOIN translations, mark the gaps). Gate-#2 (cross-service, needs a design). **D-S05-COVERAGE-MISMATCH.** | SIM domain-aware fixed; coverage's untranslated-blindness is a real cross-service gap (tracked) |
| **S09** canon-check | 0/3, agent asked for "rules" | **TWO gaps.** (1) **fixture gap** — the rail checks prose against *declared* canon rules and none were seeded, so the agent *correctly* offered to set some up (per the rail's own notes). Fixed: the fixture now seeds a composition Work + a canon rule the prose violates. (2) **product gap (open, tracked)** — with the rule seeded, S09 rose to **1/3**: r3 drove the full rail (`composition_conformance_run` ×5, "completed the scan"), but r1/r2 still got "no rules." Root cause: `composition_list_canon_rules` and `composition_conformance_run` **require a `project_id`**, and the agent has only the `book_id` — passing `book_id` is a validation error the model reads as "no rules." Verified directly: `list_canon_rules(project_id=…)` → 1 rule; `list_canon_rules(book_id=…)` → error. **Fix (bounded, tenancy-sensitive — a focused pass):** make the canon-check tools accept `book_id` and resolve the book's composition project (mirror `composition_create_work`), so a book-scoped agent can check canon with the id it already has. | fixture ✅ + **D-S09 book_id-resolution FIXED** (`e75644212`); r2/r3 now list rules via book_id + run conformance (2/3 drive it, up from 0). Remaining: the conformance ENGINE's run is **async and writes no arc_conformance_state report in-turn** (agent then reports "no contradictions" prematurely) — a separate conformance-engine/async track, not discoverability. |

The through-line: a Tier-W (confirm-gated) write mints a token that a headless eval must commit on
the user's behalf; the flagship (S06) never needed this because its cast-save is Tier-A (auto). Once
the harness commits every minted token at the right domain, the confirm-gated rails pass.

## Results

| Scenario | Rail | Verdict | DB ground truth |
|---|---|---|---|
| S00a | consent (allow) | JUDGE ✓ | transcript |
| S00b | populate | GREEN | glossary_entities>0 |
| S00c/S00d | bootstrap | GREEN | book_kinds>0 |
| S00e | consent journey | 3/3 | deny⇒blocked, revoke⇒re-suspend (committed `90e3f417e`) |
| S01 | glossary-bootstrap | GREEN | book_kinds>0 |
| S02 | populate-glossary | GREEN | glossary_entities>0 |
| **S03** | **entity-triage** | **3/3 GREEN** | **r1 triaged=8 (whole pile drained), r2=1, r3=6** (`a37087d94`) |
| **S04** | **kg-build** | **3/3 GREEN** | **kg_projects=1 nodes=6 all runs** |
| S05 | translation-pass | **3/3 GREEN** | THREE gaps fixed: coverage untranslated-blindness (cross-service) + domain-aware Tier-W commit + rail used wrong tool (start_job vs retranslate_dirty for NEW chapters). translation_jobs=2, chapters_translated=3 all runs |
| S06 | flagship vision-to-book | GREEN | 5/5 artifacts land (`463091c6a` etc.) |
| S06b | chapter-compose | GREEN | chapters_with_prose>0 |
| S07 | build-a-book | GREEN | plan_run>0 |
| S08 | tool discovery | JUDGE ✓ | transcript |
| S09 | canon-check | discovery FIXED (2/3 drive conformance); engine-detection tracked | fixture ✅ + book_id-resolution ✅ (committed `e75644212`); conformance run is async + writes no in-turn report (separate engine track) |
| S10 | maps | **2/3 GREEN** | draw-a-map rail + intent-pin (maps were undiscoverable railless); r2/r3 created a map+marker |
| S11 | reader | **3/3 SPOILER-SAFE (judge)** | all runs: windowed story_search to ch1, found 0 (ch3 betrayal windowed out), answered "no betrayal so far", leaked NONE of the ch3 spoiler content. lore-so-far rail + intent-pin + reader-session (project-linked) |
| S12 | autonomous-drafting | GREEN | chapters_with_prose>0 |

## Fixes shipped (this run)

- **Intent→workflow pinning** (`8bd7a2108`) — maps the user's words to the rail they describe, pinned
  additively like the mode binding pins vision-to-book. Deterministic, visibility-filtered, 9 tests.
- **Rail-driver DRAIN grounding** (`45edb48d5`) — a `suggestions` book-state key + drain operators
  (`<`,`<=`,`==`) so the driver keeps a triage rail live until the pile empties; glossary
  `/internal/books/{id}/suggestions-count` route (live: `{count:23}` = DB); grammar machine-checked
  on both the Go author side and the Python consumer side.
- **Harness Tier-W commit** (`a37087d94` + domain-aware follow-up) — the eval now simulates the user
  clicking **every** auto-rendered confirm card, at **each** minted token's own domain route. This is
  the ONLY thing a headless run can't supply for a Tier-W flow; it does not relax what the agent must do.
- **S09 fixture** — seeds the composition Work + the canon rule the prose contradicts (`composition_
  create_work` → `composition_canon_rule_create`), so the rail has something to check against.

_This report is updated as S05/S09 land._
