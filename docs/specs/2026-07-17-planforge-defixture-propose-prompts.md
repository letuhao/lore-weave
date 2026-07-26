# PlanForge — de-fixture the LLM propose prompts (A2)

> **Status:** ✅ **BUILT (prompts) 2026-07-17.** Build-time finding LOWERED the risk: the PROD path
> already severed the fidelity-POC dependency (`plan_forge_service.py:772`, PF-19 — a plan is scored only
> against a PER-RUN rubric, else `fidelity_score=None`, never the POC fixture), and `eval_fidelity.py`'s
> scorer is already cfg-parameterized (expected values live in the rubric, not the code). So A2's real
> defect was the **PROMPTS telling every book to reproduce the POC**, which is now fixed + guarded.
> The residual `_check_arc2_events`/`min_arc2_events=7` in the scorer is cfg-gated + prod-unused (only
> fires when a rubric supplies arc-2 semantics = the POC fixture) — a minor optional cleanup, not the
> defect. Part of the PlanForge-v2 Proposer-Grounding track
> (`docs/plans/2026-07-17-planforge-v2-grounding-track.md`). **This is a real latent DEFECT, not just
> an enhancement** — the LLM-side of the same "fixture severing" bug `propose.py` already fixed for
> rules mode.

## 1 · The problem
`ANALYZE_SYSTEM` and `MATERIALIZE_SYSTEM` (`engine/plan_forge/prompts.py`) still carry POC-fixture rules
welded to ONE specific novel:
- "character name: use **'Nữ chính'** or source name" (prompts.py:56)
- "**Arc 2 MUST have exactly 7 events** (Nhập Môn … Quyết Định Tiếp Tục)" (prompts.py:57)
- "List ALL 5 core traits from §1.3: **Thực dụng, Bình dị, Tự giác giới hạn, …**" (prompts.py:25)
- "Event 3 Thử Nghiệm: must mention tốc độ, linh thạch, âm dương …" (prompts.py:58)

For ANY book, the model is told to reproduce another novel's arc-2 structure, that protagonist's traits,
and its event titles. This is exactly the **P-06 "silent success" bug** the rules-mode `propose.py`
module docstring describes ("it silently produced a plan for a DIFFERENT book") — but on the LLM path,
never fixed. In the PROPOSE-BLIND A/B it actively competed with + dominated the CONTINUITY grounding.

## 2 · The rule (mirror propose.py's fixture severing)
Rewrite both system prompts so they **describe the OUTPUT CONTRACT (schema + universal fidelity rules),
never one novel's content**: parse what the source says; emit nothing where it says nothing. Absent ≠
invented. The universal rules that STAY (they are book-agnostic): the JSON schema, ARC COVERAGE (every
arc ≥1 event), CONTINUITY (reference EXISTING STATE), `coupled_to_realm=false`, "don't drop
open_questions", "keep event titles in the source language". Everything naming a specific arc, trait,
event, or "Nữ chính" GOES.

Character naming after de-fixturing: "name the protagonist from the SOURCE; if the source doesn't name
them, leave the model's own choice / the normalize placeholder" — with CONTINUITY (A1) overriding for
grounded books.

## 3 · The hard part — re-baseline the fidelity eval (the reason this is L, not S)
The hardcodes are not free-floating: `eval_fidelity.py` SCORES against them. It is a **POC-specific
scorer** — `evaluate_analyze_fidelity` / `evaluate_spec_fidelity` check arc_2 has 7 events, the 5 named
traits, the specific event titles (`eval_fidelity.py:26,340,477`). Ripping the prompt hardcodes without
re-baselining the eval would red the fidelity suite. So A2 is two coupled changes:

1. **Prompts** — de-fixture (§2).
2. **Fidelity eval → generic** — the scorer must measure "did the plan faithfully transcribe ITS OWN
   source" (arc coverage, event count vs the source's stated events, traits present in the source), NOT
   "does it match the POC novel". The POC book (`story-plan-v1`) becomes ONE parameterised fixture whose
   *expected* values are DERIVED from its own source, not hardcoded in the scorer.

### 3.1 Impacted fixtures / tests (the re-baseline surface — verified)
- `tests/fixtures/plan-forge/story-plan-v1.fidelity.yaml`, `story-plan-v1.expectations.yaml`,
  `llm_mock_spec.json`, `llm_mock_analyze.json`, `hil_fidelity_script.yaml` — the POC expectations.
- `tests/unit/test_plan_forge.py`, `test_plan_forge_router.py` — assert the fidelity outputs.
- These move from "hardcoded POC values" to "values derived from the fixture's own source", so a SECOND
  book fixture can be added and scored by the same generic path.

## 4 · Acceptance criteria
1. A propose for a NEW book (not the POC) contains **no POC artifacts** — no "Nữ chính" unless the source
   uses it, no "Bước Lên Tiên Lộ"/"Nhập Môn" arc-2 titles, no borrowed traits. (Live smoke on a fresh
   braindump, diff the spec for the POC strings — must be absent.)
2. The fidelity eval scores the POC book the same as before (no regression) via DERIVED expectations,
   AND scores a second book fixture correctly (proving it is generic, not POC-welded).
3. ARC COVERAGE + CONTINUITY (the universal rules) are preserved verbatim.
4. The rules-path propose (`propose.py`, already de-fixtured) is untouched — this is the LLM-path catch-up.

## 5 · Test
- Unit: the two system prompts contain NO novel-specific literals (a guard test greps ANALYZE_SYSTEM /
  MATERIALIZE_SYSTEM for the banned POC strings — "Nữ chính", "Nhập Môn", the 5 trait names — and fails
  if present; mirrors propose.py's severing intent as an enforceable check).
- Generic fidelity eval unit tests over TWO book fixtures (POC + a second).
- Live smoke: fresh-book propose has zero POC bleed.

## 6 · Risk / size
L — the prompt rewrite is small, but re-baselining the fidelity eval + its fixtures/tests is the bulk
and the risk (a green fidelity suite today encodes the POC values). Do A2 BEFORE A1 so the deterministic
cast injection is measured against a clean, un-polluted output. No schema / service / provider change.
