# Creation-Unblock — Pre-Flight Checklist

> Sign-off BEFORE RAID cycle execution. Legend: **[x] verified now** · **[~] built in-cycle** · **[!] NEEDS USER (gating)**.
> Static checks drafted 2026-06-13; live checks to be run at sign-off.

## Design decisions — ALL LOCKED 2026-06-13 (CLARIFY complete; see OPEN_QUESTIONS_LOCKED)
- [x] Scope locked (writer + knowledge unblock + all net-new) — PO 2026-06-13.
- [x] dị bản = copy-on-write (composition-only schema) — locked.
- [x] **G1 World container** → LOCKED: `worlds` table + nullable `world_id` FK on `books` (book-service), additive; lore stays book_id-keyed; prose-less via chapterless bible book. *(code-grounded: no breaking queries.)*
- [x] **G2 dị bản delta** → LOCKED: derivative gets its own `project_id` = its own Neo4j partition (composition.project_id == knowledge.project_id confirmed 1:1). No knowledge schema change.
- [x] **G3 Branch-point** → LOCKED: chapter-level for M0.
- [x] **G4 Run posture** → LOCKED (PO 2026-06-13): **FULL autonomy C0→C21, no mid-run gate**; live UI smoke via **Playwright MCP screenshots** (test account). Human touchpoints = pre-flight + final report only.
- [x] **G5 Visual-graph** → LOCKED: read-only nav MVP, reuse `GraphCanvas`, build subgraph endpoint (C11), no new graph library.
- [x] **G6 Knowledge IA** → LOCKED (PO 2026-06-13): **book-workspace pattern** — project-detail-as-home
  (`/knowledge/projects/:projectId/:section`, C6 shell), C7 browser is the landing, Entities/Timeline/Raw
  render scoped inside the shell (project `<select>` removed when scoped). Cross-project view **kept as a
  demoted secondary search** only. A correction to the 2026-04-13 draft (which uses the flat-tabs+select model).
- **→ No outstanding design USER gates. The only remaining pre-flight items are runtime infra (L1–L4/L3) below.**

## Environment & isolation
- [~] On branch `feat/auto-draft-factory-gaps`; `.raid/active-task.yaml` points to `creation-unblock`.
- [x] **Stack up + healthy** (L3) — VERIFIED 2026-06-13: all services `/health`=200 (book:8205, glossary:8211,
  knowledge:8216, lore-enrichment:8221, composition:8217, provider-registry:8208) + gateway:3123/health=200 +
  pg/redis/neo4j/rabbitmq/minio/worker-ai all healthy (13h uptime).
  *(lore-enrichment + glossary back the curation flywheel C9–C11 — aggregate/deep-link, don't duplicate.)*
- [~] No edits to unrelated agents' work (world-service/game-server/etc.); shared-service edits additive only.

## Models / providers (resolved via provider-registry — no hardcoding)
- [x] **L1 local-rerank** — VERIFIED: `rerank_local/bge-reranker-v2-m3` registered + active, capability `rerank`
  (confirms the `rerank`/`reranker` drift — registered data uses `rerank`, matching the picker; C1 reconcile valid).
- [x] **L2 embedding + benchmark** — VERIFIED: `lm_studio/text-embedding-bge-m3` registered; project
  `019eb683…` (万古神帝) has `benchmark passed=true` + `extraction_status=ready` (a real built graph to smoke
  C8–C13/C18 against).
- [x] **L4 chat model** — VERIFIED: 4 active chat models (gemma-4-26b, qwen2.5-7b, gpt-4o).
- [x] (policy) provider-rule gate (`scripts/ai-provider-gate.py`) green.

## UI smoke (Playwright MCP — locked G4 verification method)
- [x] **Frontend reachable** — VERIFIED: `http://localhost:5174` → 200; redirects to `/login`.
- [x] **Test account login** — VERIFIED end-to-end via Playwright: navigate → Sign In → lands on `/books`
  (screenshot `preflight-books-loggedin.png`). Form pre-fills the test creds.
- [x] Playwright MCP available; screenshots filed per FE cycle + milestone.

## RAID operational
- [~] `.raid/active-task.yaml` validates → `python scripts/raid/task_config.py validate` exit 0.
- [x] Quota profile present (`contracts/raid/quota-profile.yaml`).
- [~] Runtime logs initialized under `docs/raid/` (CYCLE_LOG, ESCALATIONS, QUOTA_LOG, AUDIT_LOG, IN_PROGRESS).
- [x] pre-commit workflow-gate hook installed (warn-and-pass on no state).
- [x] Windows note: run the gate via `python scripts/workflow-gate.py` (bash wrapper unreliable on this box —
  per memory `workflow-gate-windows-invocation`).

## Per-cycle verify posture
- [x] FE cycles (C0,C1,C4,C5,C6,C7,C8,C10,C12,C14,C15,C17,C21): unit/component + manual smoke on a short viewport.
- [x] BE/cross-service cycles (C2,C3,C9,C11,C13,C16,C18,C19,C20): unit + **live-smoke token** at VERIFY.
- [x] Migration cycles (C13 world, C16 derivative): up/down clean + round-trip test.

---

## ⛳ Gating summary (2026-06-13 — DESIGN CLEARED + INFRA VERIFIED → /raid-READY)
- **Design: CLEARED.** All gates G1–G5 + knowledge cycle design + dị bản/world + the C12/C13 detailed design
  are LOCKED (code-grounded). Architecture adversarially reviewed; 3 fixes applied. **No outstanding design gates.**
- **Infra: VERIFIED 2026-06-13.** L3 stack healthy · FE reachable + Playwright login works · L1 rerank · L2
  embedding+passing-benchmark (+ a ready graph to smoke against) · L4 chat — **all green.**
- **→ The task is `/raid`-READY.** No outstanding pre-flight items. Awaiting the human launch.
- **Run behaviour (locked G4):** Coordinator runs **C0→C28 fully autonomously** (29 cycles), no mid-run gate;
  live UI smoke via **Playwright MCP screenshots** at each FE cycle + milestone (+ real API smoke on
  cross-service cycles).
- **If infra isn't bootable now:** the **no-infra FE subset** (C0, C1, C4, C5, C6, C7, C11, C15, C17) can run
  first (Playwright smoke still needs FE + gateway up); defer live-smoke cycles
  (C2/C3/C8/C9/C12/C13/C16/C18/C20/C25/C27) and the rest until infra is ready.
- **Human touchpoints:** this pre-flight sign-off (before) + final report with screenshots (after). Nothing in between.
