# PlanForge POC — PO Semantic Review

> **Date:** 2026-07-01 · **Reviewer:** Developer-led PO proxy (evidence-based) · **Fixture:** `story-plan-v1.md`  
> **LLM artifacts:** fresh `run_poc_llm.py` run + Phase C stability (`out/eval/`)

## Phase A — Automated reverify

| ID | Check | Result | Evidence |
|----|-------|--------|----------|
| A1 | Rules S1–S8 | **PASS** | `out/validation_report.md` |
| A2 | LLM S1–S8 | **PASS** | `out/validation_report.llm.md` |
| A3 | L1–L5 | **PASS** | 2 `llm_io/*.json`, exit 0 |
| A4 | Audit trail | **PASS** | `001_analyze.json`, `002_materialize.json` with `usage` |
| A5 | `notes_linked` without manual normalize | **PASS** | ratio=1.00 on fresh LLM run |
| A6 | Unit tests | **PASS** | 10 passed (`-m "not live"`) |

## Phase B — Semantic rubric (1–5)

Scored against [`fixtures/story-plan-v1.md`](../../../scripts/plan-forge-poc/fixtures/story-plan-v1.md) and fresh LLM outputs.

| ID | Criterion | Score | Notes |
|----|-----------|-------|-------|
| B1 | 4 biến PA/HA/CD/THR + luật chuyển | **5** | Khớp §4; `not_coupled_to` / `coupled_to_realm: false`; ngưỡng PA theo tầng Đạo Hóa |
| B2 | Arc 2 = discovery, không power fantasy | **5** | `arc_kind=discovery`, theme "Discovery and Price"; synopsis framing cơ hội + chi phí thẩm mỹ |
| B3 | Event fidelity (7 events arc_2) | **4** | **6/7** events — thiếu **Thử Nghiệm** ổn định trên full fixture (3/3 stability runs). Không hallucinate event lạ |
| B4 | THR long-game | **5** | `forbids` + planner notes "do not explain"; evt_2_4 foreshadow only |
| B5 | Open questions §7 | **5** | 8 mục, không bịa câu trả lời |
| B6 | Compile usability | **4** | `planning_package.llm.json` — 6 chapters, premise 510 chars, constraints + planner_state hợp lệ; thiếu chapter cho Thử Nghiệm |

**Average: 4.67** · Min score: 4 · **No item ≤ 2**

### Artifact highlights

- **`plan_analyze.json`:** Bắt Đạo Hóa, bí kíp giả, 4 biến, arc theme, planner secrets — không cần TOC parser
- **`novel_system_spec.llm.json`:** Charter forbids/style khớp §6; mechanics secrets khớp §2–3
- **`llm_vs_rules_report.md`:** ID overlap 0%, title overlap ~86% (6/7), variable overlap 100%

## Phase C — Stress scenarios

| Scenario | Result | Detail |
|----------|--------|--------|
| C1 Stability 3× full fixture | **PASS (2/3 golden)** | `out/eval/phase_c_report.json` — run 1 S3 fail (5 anchors), runs 2–3 full S1–S8 PASS; 3/3 `notes_linked` + vars_four |
| C2 Braindump no TOC | **PASS** | `fixtures/story-braindump-smoke.md` → analyze: 4 vars, **7/7** arc_2 titles including Thử Nghiệm |
| C3 Alt model | Skipped | Not required |
| C4 JSON repair | Covered | Mock path in unit tests |

**Stability finding:** Gemma đôi khi bỏ Event 3 (Thử Nghiệm) trên full 22k doc nhưng vẫn pass golden (min 5 events). Braindump ngắn giữ đủ 7 — gợi ý prompt/materialize cần explicit event checklist.

## Phase D — Decision

| Gate | Outcome |
|------|---------|
| Phase A | PASS |
| Phase B avg ≥ 4, no ≤ 2 | PASS (4.67) |
| Phase C | PASS with noted event-drop variance |

### **Verdict: GO — Promote engine pattern**

**Rationale:** NL → analyze → materialize workflow đủ tin cậy cho fixture acceptance. Golden S1–S8 pass trên LLM path; semantic rubric ≥ 4. Event dropout là **iterate item** (prompt), không block promote.

**Iterate before/during promote (non-blocking):**

1. Materialize prompt: explicit 7-event checklist for arc_2 (include Thử Nghiệm)
2. Anchor language policy (VN vs EN) — product decision
3. Canonical event ID scheme (`arc_2_event_N` or title-slug map)
4. Citation spans for hallucination audit (post-promote)

**BLOCK items:** None

## PO sign-off

- [ ] Human PO confirms rubric scores (optional override)
- [x] Automated + developer proxy review complete — **GO** recorded 2026-07-01

## Next

**Blueprint shipped:** [`09_PLANFORGE_BLUEPRINT.md`](09_PLANFORGE_BLUEPRINT.md) — implement session SSOT. Promote detail: [`docs/plans/2026-07-01-plan-forge-promote.md`](../../plans/2026-07-01-plan-forge-promote.md).

## Appendix — HIL refine POC (2026-07-01)

**PASS** — [`05_HIL_POC_EVAL.md`](05_HIL_POC_EVAL.md): scripted human-in-the-loop added Thử Nghiệm (6→7 events) with golden S1–S8 intact. `run_poc_hil.py` + `accept_refine` gate validated.
