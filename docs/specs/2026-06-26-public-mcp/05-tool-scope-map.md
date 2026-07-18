# Public MCP — Authoritative Tool Scope-Map

- **Date:** 2026-06-26
- **Source:** 8-provider classification audit (book, glossary, knowledge, translation, composition, jobs, settings, lore-enrichment), one read-only agent per service, common schema.
- **Purpose:** the single source of truth for **what the public edge advertises and how it gates each tool**. Drives P2 (scope filter) + P3 (spend gate) + the per-provider hardening fanout. Each tool's `public_scope_rec` is what the edge's scope-filter keys on.
- **Policy recap (LOCKED):** owned-books-only · BYOK-only spend (PUB-12) · paid tools gate on `incurs_cost` regardless of tier (PUB-10) · Tier-W → human-approve by default (OD-2) · admin/secret/Tier-S ungrantable.

---

## 1. Counts

| Provider | Tools | R | A | W | Paid | Ungrantable | Hardening needed |
|---|---|---|---|---|---|---|---|
| book | 21 | 5 | 7 | 9 | 3 (cover/media/audio, UI-bounce) | 2 (delete, purge) | idempotency on creates |
| glossary | ~40 + 5 admin | ~18 | ~7 | ~15 | 3 (web_search, plan, deep_research) | 5 admin | idempotency on link/evidence/propose |
| knowledge | 24 (+kg_admin) | 8 | — | 16 (kg confirm) | 3 (build_graph/build_wiki/run_benchmark) | kg_admin | **H-U: 5 memory_* missing project-owner guard** |
| translation | 14 | 4 | 4 | 6 | 5 (start/retransl/extract/resume/retry) | — | extract is cross-domain |
| composition | 18 | 5 | 11 | 2 | 1 (generate) | — | idempotency on outline/rule/link creates |
| jobs | 3 | 3 | — | — | — | — | **H-N: add cancel/pause MCP**; H-F domain filter |
| settings | 12 | 5 | 6 | 1 | 0* | secret-create (UI-only) | secrets redacted ✓ |
| lore-enrichment | 1 | — | 1 | — | **1 (auto_enrich — paid Tier-A!)** | — | **reclassify: paid+non-idempotent** |
| **Total** | **~133** | ~48 | ~36 | ~49 | **~16 paid** | admin+delete+secret | — |

\* settings `provider_inventory`/`model verify` read cached, no upstream spend.

---

## 2. Classification by `public_scope_rec` (what the edge advertises)

### `read` — Tier-R, no cost → advertise to any key with the domain `read` scope
- **book:** `book_list`, `book_get`, `book_list_chapters`, `book_get_chapter`, `book_list_revisions`
- **glossary:** `glossary_search`, `glossary_get_entity`, `glossary_list_system_standards`, `glossary_book_ontology_read`, `glossary_entity_get_genres`, `glossary_list_merge_candidates`, `glossary_list_chapter_links`, `glossary_list_entity_revisions`, `glossary_list_unknown_entities`, `glossary_get_entity_evidence`, `glossary_list_ai_suggestions`, `glossary_book_sync_available`, `glossary_user_standards_read`
- **knowledge:** `kg_graph_query`, `kg_entity_edge_timeline`, `kg_schema_read`, `kg_list_templates`, `kg_sync_available`, `kg_view_read`, `kg_triage_list` *(properly guarded)* — **plus `memory_search`/`memory_recall_entity`/`memory_timeline` ONLY after H-U guard added**
- **translation:** `translation_coverage`, `translation_segment_status`, `translation_list_versions`, `translation_job_status`
- **composition:** `composition_get_work`, `composition_list_outline`, `composition_get_prose`, `composition_list_canon_rules`, `composition_get_generation_job` — **plus motif library (W4+):** `composition_motif_search`, `composition_motif_get`, `composition_motif_suggest_for_chapter`, `composition_arc_suggest`, `composition_motif_link_list`, `composition_motif_book_list`, `composition_get_mine_job` *(BE-7c: resource scope is **user**, not book — a mine/import job is Work-LESS, so it gates on `created_by`; takes `job_id` only)*
- **jobs:** `jobs_list`, `jobs_summary`, `jobs_get` *(filter to key's domain scopes — H-F)*
- **settings:** `settings_get_profile`, `settings_list_providers`, `settings_list_models`, `settings_get_defaults`, `settings_provider_inventory` *(secrets redacted ✓)*

### `paid_read` — Tier-R but **incurs cost** → requires `paid_read` scope + BYOK + spend pre-check (PUB-10/12)
- **glossary:** `glossary_web_search` ⚠️ *(Tier-R, NOT confirm-gated, paid — the canonical PUB-10 case)*

### `write_auto` — Tier-A, no cost → requires domain `write_auto` scope
- **book:** `book_create`*, `book_update_meta`, `book_chapter_create`*, `book_chapter_bulk_create` (idempotent ✓), `book_chapter_update_meta`, `book_chapter_restore_revision`, `book_chapter_save_draft` (base_version ✓)
- **glossary:** `glossary_book_create`*, `glossary_book_patch` (version-gated), `glossary_book_set_active_genres`, `glossary_book_set_kind_genres`, `glossary_entity_set_genres`, `glossary_create_chapter_link`*, `glossary_create_evidence`*, `glossary_propose_new_entity` (dedup ✓), `glossary_propose_translation`, `glossary_propose_aliases`, `glossary_user_create`*, `glossary_user_patch`, `glossary_user_delete`, `glossary_user_restore`
- **knowledge:** `kg_view_upsert`, `kg_view_delete`, `kg_triage_resolve`, `kg_triage_place_edge`, `kg_adopt_template`(token), `kg_sync_apply`(token) — **plus `memory_remember`/`memory_forget` ONLY after H-U guard (EDIT)**
- **translation:** `translation_set_active_version`, `translation_save_edited_version`, `translation_patch_block`, `translation_update_settings`, `translation_job_control`(cancel/pause)
- **composition:** `composition_create_work`* (idempotent ✓), outline_node create*/update/delete/restore, scene_link create*/delete, canon_rule create*/update/delete, `composition_write_prose` (version-checked ✓) — **plus motif library (W4+):** `composition_motif_create`*, `composition_motif_patch` (version-checked ✓), `composition_motif_archive`, `composition_motif_bind`, `composition_motif_unbind`, `composition_motif_link_create`*, `composition_motif_link_delete` *(motif_bind stores agent-supplied role→entity ids; it does NOT call glossary → composition-local)*
- **settings:** `settings_update_profile`, `settings_model_register`, `settings_model_update`, `settings_model_set_favorite/active/default`

\* = **not idempotent → needs `idempotency_key` (H-G)** before headless exposure.

### `write_confirm` — Tier-W → **human-approve by default (OD-2)**; `allow_self_confirm` opt-in; priced ones also need spend gate
- **Non-priced W:** `book_chapter_publish`, `book_chapter_unpublish`, `book_chapter_delete`, `book_chapter_purge` (Manage), `glossary_adopt_standards`, `glossary_book_delete`, `glossary_book_revert`, `glossary_propose_status_change`, `glossary_propose_restore_revision`, `glossary_propose_reassign_kind`, `glossary_propose_merge`, `glossary_propose_new_kind`, `glossary_propose_kinds`, `glossary_propose_new_attribute`, `glossary_book_sync_apply`, `kg_propose_fact`, `kg_propose_edge`, `kg_schema_edit`, `kg_triage_schema_write`, `kg_project_create`, `composition_publish`, `composition_motif_adopt` *(tenancy/quota clone — no LLM spend)*, `composition_arc_import_analyze` *(LLM deconstruct of the user's own imported text — composition-local)*
- **Priced W (BYOK + spend pre-check + re-price H-J):** `translation_start_job`, `translation_retranslate_dirty`, `translation_start_extraction` *(cross-domain→glossary)*, `translation_job_control`(resume/retry), `glossary_plan`, `glossary_deep_research`, `kg_build_graph`, `kg_build_wiki`, `kg_run_benchmark`, `composition_generate` *(cross-domain→glossary/knowledge)*, `composition_motif_mine` *(cross-domain→knowledge: reads :Event beats + writes mined_motif_code tags)*, `composition_conformance_run` *(cross-domain→knowledge: reads thread/causal/realized tags)*

### ⚠️ Needs reclassification before exposure
- **`lore_enrichment_auto_enrich`** — internally Tier-**A** but **paid + non-idempotent**. For public: treat as **priced write requiring spend pre-check + (OD-2) human-approve**, and add idempotency (dedup on book_id+targets). **Do NOT expose as `write_auto`** — a paid auto-tool violates the money model.

### `ungrantable` — never advertised to a public key
- All `glossary_admin_*` (5) + `kg_admin_*` (2) — `/mcp/admin`, RS256, the edge has no route there (PUB-9).
- `book_delete`, `book_purge` — owner-only destructive; keep off the public surface (or owner-only + human-approve if ever needed).
- Provider-credential **secret** create/update — UI-only, never an MCP arg (settings confirmed).

---

## 3. Cross-cutting findings → hardening worklist

| ID | Finding | Tools affected | Action | Phase |
|---|---|---|---|---|
| **H-U** 🔴 | project-scoped tools trust `ctx.project_id` with **no owner check** | `memory_search/recall_entity/timeline/remember/forget` (knowledge) | add `_resolve_project_owner(VIEW|EDIT)` to the 5 handlers (executor.py:209/273/315/365/434) | **P2 — gates knowledge public** |
| **PUB-10** 🔴 | paid tools at R/A tier defeat tier-based spend gate | `glossary_web_search` (R), `lore_enrichment_auto_enrich` (A) + all priced W | spend-gate on per-tool `incurs_cost`, not tier; `paid_read` scope | **P3** |
| **PUB-12** 🔴 | BYOK-only, no platform/free-tier | all ~16 paid tools | edge rejects 402 if model resolves to platform/free-tier | **P3** |
| **H-C** 🔴 | per-key spend attribution | all paid tools | `X-Mcp-Key-Id` header → ai-gateway forward → kits → job_meta → usage_logs | **P3 — gates priced public** |
| **H-G** 🟠 | non-idempotent creates duplicate on headless retry | book_create, glossary create_chapter_link/evidence/propose_new_entity/user_create, composition outline/rule/link/work creates, lore_auto_enrich | `idempotency_key` arg + edge dedup `(key_id,tool,args_hash)` | P2/P4 |
| **H-N** 🟠 | no MCP job-cancel except translation | jobs_* (read-only) | add `jobs_cancel`/`jobs_pause` Tier-A MCP tools | P4 |
| **H-F** 🟡 | `jobs_*` cross-domain by design | jobs_list/summary/get | edge filters results to key's domain scopes | P2 |
| **UI-bounce** 🟡 | confirm returns `open_ui`, not headless-executable | book_set_cover, book_media_generate, book_audio_generate | mark "requires browser"; advertise as propose-only or exclude headless | P2 |
| **cross-domain** 🟡 | tool writes another domain | translation_start_extraction→glossary, composition_generate→glossary/knowledge, lore_auto_enrich→glossary/knowledge | scope by domains-touched (H-F), not prefix; key needs both domain scopes | P2 |
| **H-I** 🟡 | project_id from header | all kg_* (required), memory_* (optional) | edge accepts agent-supplied `project_id` → sets `X-Project-Id`; H-U guard makes it safe | P2 |

---

## 4. Per-provider fanout task (P2, one worktree agent each)

Each agent owns ONE service, runs the same DoD (kit changes are a **separate pre-step**, §5):
- **book** — add `idempotency_key` to `book_create`/`book_chapter_create`; mark media/audio/cover as UI-bounce (exclude from headless); confirm delete/purge stay ungrantable.
- **glossary** — add `idempotency_key` to create_chapter_link/create_evidence/propose_new_entity/user_create; tag `glossary_web_search`+`glossary_plan`+`glossary_deep_research` `incurs_cost`.
- **knowledge** 🔴 — **add `require_project_owner` to the 5 `memory_*` handlers (H-U)**; ensure `project_id` is an ownership-checked arg path (H-I); tag build_graph/build_wiki/run_benchmark `incurs_cost`. *(security-critical → /review-impl or /amaw on this one.)*
- **translation** — tag the 5 priced tools `incurs_cost`; mark `start_extraction` cross-domain (needs glossary scope too).
- **composition** — add `idempotency_key` to outline/rule/link/work creates; tag `composition_generate` `incurs_cost` + cross-domain.
- **jobs** — add `jobs_cancel`/`jobs_pause` Tier-A MCP tools (H-N); support edge domain-filtering.
- **settings** — confirm redaction holds (✓); ensure user-scope guard surfaces to the edge as `user` scope.
- **lore-enrichment** — reclassify `auto_enrich` as priced+confirm for public; add dedup (H-G); tag `incurs_cost`.

## 5. Kit pre-step (SERIAL, before the §4 fanout)
One agent does the shared changes the providers depend on (avoids the kit-conflict hazard):
- `sdks/go/loreweave_mcp` + `sdks/python/loreweave_mcp`: (a) lift `X-Mcp-Key-Id` → ctx; (b) an **owner-only resolver variant** / context flag (OD-8); (c) a reusable `require_project_owner` helper (for H-U).
- `ai-gateway`: forward `X-Mcp-Key-Id` (additive) + constant-time internal-token compare.
- `provider-registry` submit chokepoint: merge `X-Mcp-Key-Id` into `job_meta` (mimic `campaign_id`).

## 6. v1 public exposure recommendation (staged)

1. **Wave A (after P0–P2):** `read` scope only — all Tier-R non-paid tools, **knowledge memory_* held until H-U lands**. Safe, zero spend, immediate value.
2. **Wave B (after P3):** `write_auto` (idempotency-hardened) + `paid_read` (`glossary_web_search`) + per-key spend gate + BYOK-only enforced.
3. **Wave C (after P4):** `write_confirm` with human-approve default; priced tools opened per-provider as their `incurs_cost`/attribution live-smoke passes; `allow_self_confirm` opt-in.

**Never:** admin, secret-create, `book_delete`/`book_purge` via public key.
