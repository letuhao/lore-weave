# Glossary Pipeline M3/M4 — re-plan after the `main` (MCP fan-out) merge

> **Status:** DESIGN — awaiting PO sign-off before BUILD.
> **Why this doc:** the pre-merge handoff line *"M3/M4 async extract/translate — last"* predates the MCP-fanout merge, which added the exact async/job/cost substrate M3/M4 needs. This reconciles M3/M4 against what now exists so we build against the current architecture, not a stale plan.
> **Source map:** post-merge code exploration (extraction, translation, jobs MCP) — see refs inline.

---

## 1. What the merge already solved (so M3/M4 shrink)

| Capability M3/M4 needed | Pre-merge | Post-merge — EXISTS |
|---|---|---|
| Async **job-handle + progress-in-chat** (S20) | missing (design problem) | ✅ `jobs-service` MCP `jobs_list`/`jobs_summary`/`jobs_get` over the unified job projection ([jobs-service/app/mcp/server.py:83-203](../../services/jobs-service/app/mcp/server.py#L83)); the `glossary_extraction` kind is wired into the projection ([jobs-service/app/contract.py](../../services/jobs-service/app/contract.py), [control.py](../../services/jobs-service/app/control.py)) |
| Per-service **start-job + confirm-token + cost gate** pattern (S21) | missing | ✅ `translation-service` MCP `translation_start_job` (estimate → mint confirm token → `confirm_action(domain=translation)` → `/v1/translation/actions/confirm`) ([translation-service/app/mcp/server.py](../../services/translation-service/app/mcp/server.py)) |
| **Prose** translation via agent | missing | ✅ `translation_*` MCP family (start/status/control/retranslate) |
| Extraction **trigger endpoint** + cost estimate + job row + event emit | ✅ REST only | unchanged: `POST /v1/extraction/books/{id}/extract-glossary` (EDIT grant, cost-estimate before run, emits kind `glossary_extraction`/service `translation`, poll `GET /v1/extraction/jobs/{id}`) ([translation-service/app/routers/extraction.py:60-200](../../services/translation-service/app/routers/extraction.py#L60)) |

**Net effect:** M3 is now *"wrap an existing REST trigger as one MCP tool, mirroring `translation_start_job`, and reuse `jobs_get` for progress."* No new async/cost/job infra. M4 is a glossary-domain write tool with one data-model decision to scope around.

---

## 2. Decisions (the re-plan)

### D1 — Extraction trigger MCP tool lives on **translation-service**, not glossary-service
The extraction pipeline (trigger → `extraction.job` queue → worker → LLM → glossary `/internal/.../extract-entities` writeback) is **owned by translation-service**, which already hosts the MCP server, the cost estimator, and the `translation_start_job` confirm-token pattern. Per MCP-first ("domain owns its tools") and main's per-service pattern, the new tool is **`translation_start_extraction`** on translation-service's MCP. **glossary-service needs zero new code for M3.**

### D2 — Cost-confirm gate (S21) = class-C confirm token via the translation actions seam
Mirror `translation_start_job`: the tool estimates cost, mints a confirm token (descriptor e.g. `extraction.start`), returns a confirm card; the human confirms → `/v1/translation/actions/confirm` runs the existing `create_extraction_job` trigger. Reuses the merged confirm seam (BFF proxy + JWT-gating already live-fixed on `main`). Satisfies "extraction costs money → confirm before run."

### D3 — Progress (S20) = reuse `jobs_get` (kind `glossary_extraction`)
The confirm result returns `job_id`; the agent polls `jobs_get`/`jobs_list` (already surfaces the kind). **No new progress surface, no glossary code.** The universal skill already teaches the find_tools → start → poll pattern from the merge.

### D4 — Re-extract merge mode (S8) = thread the existing `extraction_profile` (fill|overwrite) through the tool params
L1 already implements per-attribute `fill`/`overwrite` + `extraction_audit_log` + verified-value protection ([extraction.py](../../services/translation-service/app/routers/extraction.py)). The tool just exposes `chapter_ids` + the profile + `model_ref`. No backend change.

### D5 — M4 glossary-entry translation MCP tool lives on **glossary-service**, scoped to attribute-value translations; **per-language aliases (S6) deferred**
New tool **`glossary_propose_translation`** writes per-language values to `attribute_translations` (table + `confidence` enum `machine|draft|verified`; upsert **never overwrites `verified`** — [attribute_handler.go:340-415](../../services/glossary-service/internal/api/attribute_handler.go#L340)). Because it is **additive + reversible + never clobbers verified**, it is **class W** (Edit), matching the M2 precedent (additive Edit writes = class W, not the confirm spine). Batch (N entities, per-entity override) is a single tool call returning per-entity results.
**Deferred — `D-GLOSSARY-PERLANG-ALIASES` (S6):** "alias in a specific language" is not a first-class concept today (aliases = one source-language JSON array on the `aliases` attr value). Modeling per-language aliases is a **data-model decision** (translations-of-the-aliases-attr vs a new alias model) — out of M4 scope so M4 ships unblocked. Source-language alias edit already works via the existing entity-edit path.

---

## 3. Build slices (proposed, pending sign-off)

| Slice | Service | Tool(s) | Class | Reuses |
|---|---|---|---|---|
| **M3a** | translation-service | `translation_start_extraction` (chapter_ids, extraction_profile fill\|overwrite, model_ref) | **C** (cost confirm) | `create_extraction_job` core, `translation_start_job` mint pattern, `/v1/translation/actions/confirm` |
| **M3b** | — (verify) | progress via `jobs_get` | — | merged jobs MCP; live-smoke the kind surfaces |
| **M4** | glossary-service | `glossary_propose_translation` (entity_id(s), language_code, value/overrides) | **W** (additive, never overwrites verified) | `createTranslation` core (extract a core like M2) |

**Out of scope (tracked):** per-language aliases (S6 → `D-GLOSSARY-PERLANG-ALIASES`); deep-research subsystem (S5); a translation **review card** FE (S4 L3) — agent path first, FE polish later.

---

## 4. Open questions for PO sign-off

1. **D1 placement** — agree the extraction trigger tool belongs on **translation-service** (owns the pipeline), keeping glossary-service untouched for M3? (Alternative: a thin glossary-side proxy tool — rejected: violates domain-owns-tools + duplicates the cost/confirm seam.)
2. **D5 class W for `glossary_propose_translation`** — OK that draft/machine translation writes are direct Edit (never overwrite verified = reversible), not class-C? (Consistent with M2 chapter-link/evidence.)
3. **S6 deferral** — OK to ship M4 for attribute-value translations only and defer per-language aliases as a separate data-model task?
4. **Sequencing** — M3 then M4, or only one this pass?

On sign-off → PLAN + BUILD the agreed slice(s) (TDD, /review-impl the confirm/cost path on M3).
