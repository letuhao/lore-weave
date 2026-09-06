# `feat/frontend-tools-mcp-migration` — branch overview, written for the merge

Reconciles: none — it is a branch SURVEY, not a design: commit counts, a conflict-surface measurement and a list of predicted breakages, all derived from git at two named heads. `grep -nE '^\|' docs/standards/README.md` over the index finds no row that governs comparing two branches; the merge PLAN it feeds does cite three rows, and that is where the overlap lives.

**Written:** 2026-09-03 · **Head:** `73d3615d6` · **Merge-base with `origin/main`:** `de2e0416d` (2026-08-03)

This exists because the merge is the next task and the survey behind it must not have to be
redone. Everything below is derived from git at the head above, not from recollection.

## 1. Shape

| | |
|---|---|
| Commits ahead of `origin/main` | **1963** |
| Commits behind | **96** (the branch has not pulled main since 2026-08-03) |
| Files changed vs merge-base | 2048 · +6,160,818 / −2,940 |
| Span | 2026-07-26 → 2026-09-03, 34 active days |

**The insertion count is not code.** `docs/eval` alone is 5,875,845 of the 6,160,818 insertions
across 842 files — measurement artifacts from the tool loops. Add `contracts/*.json`
(`tool-deep-dive-ledger.json` is 2.9 MB by itself) and `scripts/toolloop` (316 files) and the
generated/measured material is ~97% of the diff. **Product code is roughly 296 added and 260
modified files** under `services/`, `frontend/`, `sdks/`, `infra/`.

Commit types: 631 `fix`, 455 `docs`, 399 `measure`, 214 `feat`, 109 `proof`, 68 `test`. The
largest single scope is `measure(toolloop)` at 363 — the branch is as much a measurement record
as a change.

## 2. What it actually did

1. **MCP architecture v1 → v2.** Retired chat-service's local "frontend tools" in favour of
   federated per-domain MCP servers. Ten services now expose one: agent-registry, book, catalog,
   glossary, provider-registry (Go); composition, jobs, knowledge, lore-enrichment, translation
   (Python).
2. **A new `agentruntime` package in chat-service** — 23 modules (`admission`, `surface`,
   `narrowing`, `refresolve`, `toolcontract`, `vocabulary`, `plan*`, …), ~21k lines with
   `stream_service.py`, which is now **14,490 lines** and holds the turn loop and every
   end-of-turn guard.
3. **Durable task gate + `confirm_token` fallback** (GATE-2, `docs/standards/mcp-tool-io.md`);
   the Postgres task stores were hoisted out of two services into the SDKs.
4. **The measurement apparatus** — `scripts/toolloop`, 38 contract files under `contracts/`, and
   the tool-deep-dive/journey/resolution ledgers. This is what `problem_remaining.py` and
   `gate.py` read.
5. **Two closed goals**, each with a report: `2026-09-03-retire-v1-FINAL-REPORT.md` and
   `2026-09-03-twelve-invariants-FINAL-REPORT.md`.

## 3. The conflict surface is small — 22 files

Main changed **710** files this branch did not; the branch changed ~2000 main did not. They
overlap on 22, and only a handful are hard:

| main +/− | branch +/− | file | note |
|---|---|---|---|
| 282/14 | 82/5 | `provider-registry-service/internal/api/server.go` | **heaviest two-sided churn — start here** |
| 5/0 | **7000/328** | `chat-service/app/services/stream_service.py` | textually trivial on main's side; semantically the branch's centre of gravity |
| 19/2 | 165/30 | `provider-registry-service/internal/provider/adapters.go` | |
| 44/4 | 80/1 | `provider-registry-service/internal/api/default_models_handler.go` | main reworked pricing/aliases here |
| 852/**10171** | 359/1 | `docs/sessions/SESSION_HANDOFF.md` | main *archived* its history; guaranteed conflict, but it is prose |
| 75/37 | 61/1 | `AGENTS.md` | both sides edited the rules |
| 21/1 | 51/0 | `infra/docker-compose.yml` | |
| 57/2 | 31/3 | `knowledge-service/app/routers/internal_job_control.py` | main added checkpoint-resume |
| 50/0 | 6/6 | `knowledge-service/app/routers/public/extraction.py` | |
| 37/1 | 68/2 | `glossary-service/internal/migrate/migrate.go` | **migration ledger — see §5** |

The remaining 12 are ≤ ~25 lines a side: `.gitignore`, `docs/standards/README.md`,
`frontend/src/features/settings/api.ts`, `book-service/internal/api/server.go`,
`chat-service/app/models.py`, `chat-service/Dockerfile`,
`glossary-service/internal/migrate/ledger.go`, `jobs-service/app/contract.py`,
`jobs-service/app/routers/jobs.py`,
`knowledge-service/app/db/repositories/extraction_jobs.py`,
`knowledge-service/app/routers/public/entities.py`,
`provider-registry-service/internal/migrate/migrate.go`.

**Renames and deletes are safe.** Main touched **none** of the six paths this branch moved or
removed, verified per-path:

- `contracts/frontend-tools.contract.json` → `contracts/browser-tools.contract.json` (R100)
- `book-service/…/mcp_gate_task_store.go` → `sdks/go/loreweave_mcp/pgstore/pg_task_store.go` (R077)
- `composition-service/app/mcp/pg_task_store.py` → `sdks/python/loreweave_mcp/pg_task_store.py` (R073)
- `chat-service/app/services/frontend_tools.py` → `chat-service/tests/_v1_tool_fixtures.py` (R059)
- deleted: `glossary-service/…/mcp_gate_task_store.go`, `chat-service/tests/test_frontend_tool_validation.py`

## 4. What main did in its 96 commits

37 `fix`, 19 `feat`, 8 `docs`, 8 `chore`, 5 `test`. Themes, in rough order of merge relevance:

1. **A full i18n system** — locale bundles for many languages, plus **two new gates**:
   `scripts/i18n-key-resolution-gate.py` and `scripts/i18n-completeness-gate.py`.
2. **EPUB v2 + FB2 import** — staging, recovery, rollback, shadow-corpus comparison. Large and
   entirely outside this branch's paths.
3. **Glossary ontology** — kind votes, collection hardening, genre attribute seeding, and a
   migration-ledger repair (`f38461950` restored a ledger `5afa6b3aa` reverted by accident).
4. **Provider registry** — OpenRouter alias resolution, model pricing/capability sync, cascade
   delete. This is why `server.go` churned 282 lines.
5. **Gates and CI hardening**, including two gates that were inventing findings under CI load,
   and a throwaway-DB safety guard moved into the helpers.
6. **Upstream fork syncs** (`a53addbbe`, `be835050a`, `e226e18c9`) — main tracks an upstream.

## 5. Predicted breakage that is not a text conflict

Recorded as predictions to check, not as findings.

1. **The i18n key-resolution gate will likely go red on this branch's frontend.** The branch
   added `DisambiguationCard.tsx` (7 `t()` calls) and edited `AssistantMessage.tsx` (25),
   `AgentModePanel.tsx` (4) and `DefaultModelsCard.tsx` (16), while touching **zero** files under
   `frontend/src/i18n/`. Main's gate asserts every literal `t()` key resolves in `en`. That gate
   did not exist when this code was written. **Check first, it is cheap.**
2. **Migration ledgers.** Both sides edited `glossary-service/internal/migrate/migrate.go` and
   main separately repaired an accidentally-reverted ledger. Repo lore already records that DDL
   added to an *applied* ledger step is a silent no-op, and that calling a step function directly
   reverts a later chain step. Merge these two files by reading the ledger, never by taking a side.
3. **`docker-compose.yml`** — the branch added 51 lines of service wiring for the federated MCP
   servers; main added 21. Neither is a superset.
4. **Main's new gates judge branch code that predates them** — the DB-safety guard and the two
   repaired gates included.

## 6. State at the time of writing

- Working tree clean; nothing unpushed.
- `cd scripts/toolloop && python problem_remaining.py` exits **0** (16/16 problems cleared,
  65/65 tools proven).
- Known residue, per the twelve-invariants report §5: the LM Studio TTL transport stall is
  diagnosed but **not fixed** (remedy is outside this repo, and the cold `--concurrency 1` control
  has never been run); P16 has no live evidence; seven live tools sit below the selection bar with
  `proven` predating the crossing; `scripts/` carries **18 pre-existing failures** (down from 22,
  none introduced here).
