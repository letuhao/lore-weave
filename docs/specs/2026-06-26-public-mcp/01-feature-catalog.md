# Platform Feature Catalog (per-endpoint / per-tool)

- **Date:** 2026-06-26
- **Scope:** All backend services + the frontend feature surface. **Excludes** the game/world (LLM-MMO-RPG) frontend per the request. Game/world **backend** services and ops/infra services are summarized in §13, not enumerated route-by-route.
- **Method:** 7 parallel code deep-dives (route registration files, OpenAPI in `contracts/api/`, FE `api.ts` files, MCP tool registries). Counts are approximate where a service has many sibling sub-routes.

> Legend for **Surface**: **FE** = reachable through the frontend · **MCP** = exposed as an MCP tool · **INT** = internal-only (`/internal/*`, service-to-service) · **PUB-REST** = public `/v1/*` REST (JWT). A capability often has several. The decision table is [02-interface-matrix.md](02-interface-matrix.md).

---

## 0. Service inventory

| # | Service | Lang | Public prefix(es) (via gateway) | MCP server | Role |
|---|---|---|---|---|---|
| 1 | api-gateway-bff | TS/NestJS | (all `/v1/*`) | — (proxy only today) | External entry; pass-through proxy + WS/SSE |
| 2 | ai-gateway | TS/NestJS | none (internal :8210) | `/mcp`, `/mcp/admin` (federator) | Internal MCP federation + grounding |
| 3 | auth-service | Go/Chi | `/v1/auth`,`/v1/account`,`/v1/me`,`/v1/users`,`/v1/admin` | — | Identity, JWT, sessions, admin tokens |
| 4 | book-service | Go/Chi | `/v1/books`,`/v1/worlds`,`/v1/book/actions` | `/mcp` | Books, chapters, drafts, revisions, import, media, worlds |
| 5 | glossary-service | Go/Chi | `/v1/glossary` | `/mcp`, `/mcp/admin` | Glossary entities/kinds/genres/attrs + **wiki** |
| 6 | catalog-service | Go/Chi | `/v1/catalog` | — | Public book catalog |
| 7 | sharing-service | Go/Chi | `/v1/sharing` | — | Visibility + unlisted tokens; public-id resolver |
| 8 | provider-registry-service | Go/Chi | `/v1/model-registry`,`/v1/settings/actions`,`/v1/llm` | `/mcp` (settings) | BYOK credentials, user_models, LLM job gateway, provider proxy |
| 9 | usage-billing-service | Go/Chi | `/v1/model-billing` | — | Usage metering, spend guardrails, balances |
| 10 | translation-service | Py/FastAPI | `/v1/translation`,`/v1/extraction`,`/v1/glossary-translate` | `/mcp` | Translation pipeline (v3 translator/verifier/corrector) |
| 11 | knowledge-service | Py/FastAPI | `/v1/knowledge`,`/v1/kg` | `/mcp`, `/mcp/admin` | Knowledge graph (Postgres SSOT + Neo4j) + memory + wiki-gen |
| 12 | chat-service | Py/FastAPI | `/v1/chat` | — (MCP *client*) | LLM chat, tool-loop, voice, the universal agent surface |
| 13 | composition-service | Py/FastAPI | `/v1/composition` | `/mcp` | LOOM co-writer (outline, prose, canon, generate) |
| 14 | lore-enrichment-service | Py/FastAPI | `/v1/lore-enrichment` | `/mcp` | Gap-detect + auto-enrich + proposals |
| 15 | jobs-service | Py/FastAPI | `/v1/jobs` | `/mcp` | Unified job control plane + SSE |
| 16 | notification-service | Go/Chi | `/v1/notifications` | — | Notification center + RabbitMQ→SSE bridge |
| 17 | statistics-service | Go/Chi | `/v1/leaderboard`,`/v1/stats` | — | Leaderboards + public stats |
| 18 | learning-service | Py/FastAPI | `/v1/learning` | — | Corrections, eval runs, data-mining (read API) |
| 19 | campaign-service | Go | `/v1/campaigns` | — | Auto-draft factory saga |
| 20 | roleplay-service | Rust | `/v1/roleplay` | — | Roleplay scripts + start orchestration |
| 21 | video-gen-service | Py/FastAPI | `/v1/video-gen` | — | Media generation gateway |
| — | game/world + ops/infra | mixed | (see §13) | — | Out of catalog scope |

**MCP server count: 10** (knowledge, glossary, book, composition, translation, jobs, provider-registry/settings, lore-enrichment, + knowledge-admin + glossary-admin surfaces). **Total MCP tools: ~100** (see §12).

---

## 1. auth-service

### Public `/v1/*`
| Method | Path | Description | Auth |
|---|---|---|---|
| POST | `/v1/auth/register` | Register (email+password) | rate-limited/IP |
| POST | `/v1/auth/login` | Login → access+refresh tokens | rate-limited |
| POST | `/v1/auth/refresh` | Refresh access token | refresh token |
| POST | `/v1/auth/logout` | Revoke current session | JWT |
| POST | `/v1/auth/change-password` | Change password (revokes other sessions) | JWT |
| POST | `/v1/auth/verify-email/request` | Send verification email | JWT + rate-limited |
| POST | `/v1/auth/verify-email/confirm` | Confirm email by token | none |
| POST | `/v1/auth/password-reset/request` | Send reset email | rate-limited |
| POST | `/v1/auth/password-reset/confirm` | Reset password by token | none |
| GET/PATCH | `/v1/account/profile` | Read/update profile | JWT |
| GET/PATCH | `/v1/account/security/preferences` | Email-verify-required, reset method, alerts | JWT |
| GET/PATCH | `/v1/me/preferences` | UI preferences JSON blob (multi-device sync) | JWT |
| DELETE | `/v1/account` | Soft-delete account | JWT |
| GET | `/v1/users/{user_id}` | Public profile | optional JWT |
| POST/DELETE | `/v1/users/{user_id}/follow` | Follow / unfollow | JWT |
| GET | `/v1/users/{user_id}/followers` · `/following` | Social graph lists | none |
| POST | `/v1/admin/session` | Admin self-mint RS256 token (CMS) | JWT + `admin_principals` |

### Internal `/internal/*`
| Method | Path | Description |
|---|---|---|
| GET | `/internal/users/{id}/profile` | Basic profile (X-Internal-Token) |
| GET | `/internal/users/by-email` | Email → user_id (E0 collaborator invite) |
| GET/PATCH | `/internal/users/{id}/full-profile` | Editable profile for settings MCP |
| POST | `/internal/admin/token` | Mint admin JWT (`ADMIN_TOKEN_ISSUER_SECRET`) |
| POST | `/internal/admin/break-glass-token` | Dual-actor break-glass admin JWT |

**Tokens:** access = **HS256**, `{sub,sid,iat,exp}`, signed with shared `JWT_SECRET`. Refresh = opaque 32-byte, SHA-256 hashed in `sessions`. Admin = **RS256** via KMS, `{sub,role,scopes,break_glass,jti}`.

---

## 2. book-service

### Public `/v1/books` (88 routes — grouped)
- **Books:** `POST /v1/books`, `GET /v1/books`, `GET /v1/books/{id}`, `PATCH /v1/books/{id}`, `DELETE` (trash), `POST .../restore`, `DELETE .../purge`, `GET /v1/books/trash`, `GET /v1/books/storage-usage`, `GET /v1/books/reading-history`, `GET /v1/books/favorites`.
- **Per-book:** `GET .../search` (FTS), `POST/DELETE/GET .../favorite`, `GET/PUT .../reader-language`, `GET/POST/DELETE .../cover`, `POST .../view`, `GET .../progress`, `GET .../stats`.
- **Collaborators (E0):** `GET/POST .../collaborators`, `PUT/DELETE .../collaborators/{user_id}`.
- **Chapters:** `GET/POST .../chapters`, `POST .../chapters/bulk`, `GET/PATCH/DELETE .../chapters/{id}`, `POST .../restore`, `DELETE .../purge`, `GET .../content`, `GET .../export`, `GET/PATCH .../draft` (version-checked), `GET .../revisions`, `GET .../revisions/compare`, `GET .../revisions/{id}`, `POST .../revisions/{id}/restore`, `POST .../publish`, `POST .../unpublish`, `POST .../progress`.
- **Media/Audio:** `POST .../media`, `POST .../media-generate`, `GET/POST/DELETE .../media-versions[/{id}]`, `GET/POST/DELETE .../audio[...]`, `GET .../audio/{seg}`, `POST .../block-audio`.
- **Import:** `POST .../import`, `GET .../imports`, `GET .../imports/{id}`.
- **Worlds:** `POST/GET /v1/worlds`, `GET/PATCH/DELETE /v1/worlds/{id}`, `GET/POST .../books`, `DELETE .../books/{id}`.
- **Confirm-card actions:** `/v1/book/actions/*` (generic Tier-W confirm endpoint for book MCP tools).

### Internal `/internal/*` (14)
`GET .../projection` · `GET .../access` (E0 grant resolver: none/view/edit/manage/owner) · `GET .../reader-language` · `GET /internal/worlds/{id}/books` · `GET /internal/book/jobs` (job reconcile) · `GET .../lexical-search` · `GET .../chapters[...]` · `.../blocks` · `.../scenes` · `.../draft-text` · `.../revisions/{id}/text` · `.../hierarchy` · `POST /internal/chapters/titles` · `POST /internal/chapters/sort-orders` · `PATCH /internal/imports/{id}`.

### MCP (`/mcp`) — `book_*`
See §12. R: list/get book+chapters+revisions. A: create/update book+chapter, save-draft, bulk-create, audio/media-generate (cost-gated). W: publish/unpublish, restore-revision, delete/purge.

---

## 3. glossary-service (+ wiki)

### Public `/v1/glossary/*` (110+ routes — grouped)
- **Kinds/genres/attributes (3 tiers):** system (`/system-kinds`,`/system-genres`,`/system-attributes-admin` — admin RS256), per-user (`/user-kinds`,`/user-genres`,`/user-attributes` + their trash/restore/purge + genre links), per-book (`/books/{id}/ontology/{kinds,genres,attributes}` + revert-to-parent + sync available/apply + adopt).
- **Actions:** `POST /v1/glossary/actions/{preview,confirm}` (HS256 user confirm token), `.../actions/admin/{preview,confirm}` (RS256 admin).
- **Entities:** `GET/POST .../entities`, `GET/PATCH/DELETE .../entities/{id}`, `POST .../bulk-status`, `POST .../apply-edit` (atomic multi-field), `POST/DELETE .../pin`, `POST .../reassign-kind`, `POST .../merge`, `GET/PUT .../genres`, chapter-links CRUD, evidences CRUD, revisions list/get/restore, attribute-value PATCH + multirow items + translations CRUD + evidences CRUD.
- **Entity batch ops:** `entity-names`, `translation-languages`, `translation-candidates`, `apply-translations`, `unknown-entities`, `merge-candidates` + dismiss, `merge-journal/{id}/revert`, `recycle-bin` list/restore/purge.
- **Research jobs:** `POST/GET .../kinds/{id}/research-jobs`, `research-estimate`, list/get/pause/resume/cancel.
- **Export/profile:** `GET .../extraction-profile`, `GET .../export`, `POST .../adopt`.
- **Wiki (hosted here, not a separate service):** `GET/POST .../wiki`, `POST .../wiki/generate`, `GET .../wiki/gen-config`, `GET .../wiki/job`, `POST .../wiki/job/{id}/{resume,cancel}`, `GET .../wiki/staleness[...]` (+ sweep, dismiss, dismiss-batch, diff), `GET .../wiki/suggestions`, `GET .../wiki/public[/{id}]`, `GET/PATCH/DELETE .../wiki/{id}`, `POST/PATCH .../wiki/{id}/suggestions[/{id}]`, `GET .../wiki/{id}/revisions[/{id}]`, `POST .../revisions/{id}/restore`.
- **Public profile:** `GET /v1/glossary/users/{user_id}/wiki-contributions`.

### Internal `/internal/*` (~24)
`translation-glossary` (compact for translation) · `select-for-context` · `known-entities` · `extract-entities` (bulk write-through) · `entities/by-ids` · `entity-display-names` · `entities/stats` · `merge-candidates` · `dedup-name-variants` · `canon-content` get/set · `enrichments` upsert/delete · `enrichment-coverage` · `wiki/articles` (KG writes article) · `wiki/staleness-sweep` · `wiki/gold-pairs` · `ontology` · `users/{id}/glossary-standards` · entity-count, etc.

### MCP (`/mcp`, `/mcp/admin`) — `glossary_*`, `glossary_admin_*`
~30 tools + 5 admin. See §12.

---

## 4. catalog-service
| Method | Path | Description |
|---|---|---|
| GET | `/v1/catalog/books` | List public books (filters: language, genre, author, sort) |
| GET | `/v1/catalog/books/{id}` | Public book detail |
| GET | `/v1/catalog/books/{id}/chapters` | Public chapter list |
| GET | `/v1/catalog/books/{id}/chapters/{id}` | Public chapter body |

No MCP, no internal. Reads from sharing-service public-id resolver + book projections.

---

## 5. sharing-service
| Method | Path | Description |
|---|---|---|
| GET/PATCH | `/v1/sharing/books/{id}` | Get/set visibility (private/unlisted/public) + unlisted token |
| GET | `/v1/sharing/unlisted/{token}` (+ `/chapters[/{id}]`) | Token-gated unlisted access (no JWT) |
| GET | `/internal/sharing/public` | List public book ids (catalog) |
| GET | `/internal/sharing/public/{id}` | Verify public |
| GET | `/internal/sharing/books/{id}/visibility` | Visibility resolver |

---

## 6. provider-registry-service

### Public `/v1/model-registry/*`
Providers CRUD + health + inventory (`/providers[/{id}][/health][/models]`); user-models CRUD + activation + favorite + tags + verify (`/user-models[/{id}][/activation][/favorite][/tags][/verify]`); default-models get/set per capability; platform-models (admin); `models/{ref}/context-window`; **`/v1/model-registry/proxy/*`** (transparent BYOK proxy).

### LLM job gateway `/v1/llm/*`
`POST /v1/llm/stream` (SSE, no timeout) · `POST /v1/llm/jobs` (async: chat/embedding/image/audio/tts/rerank) · `GET /v1/llm/jobs/{id}` · `DELETE /v1/llm/jobs/{id}`.

### Settings actions
`POST /v1/settings/actions/{preview,confirm}` (Tier-W confirm-token).

### Internal `/internal/*`
`credentials/{src}/{ref}` (secret resolve) · `models/{src}/{ref}/info` · `proxy/*` · `embed` · `rerank` · `web-search` · `default-models/{cap}` · `planner-model` · `billing/estimate` · `llm/stream`, `llm/jobs[...]`.

### MCP (`/mcp`) — `settings_*` (12 tools). See §12.

---

## 7. usage-billing-service
| Scope | Routes |
|---|---|
| Public `/v1/model-billing` | `usage-logs[/{id}]`, `usage-summary`, `GET/PATCH guardrail`, `platform-balance`, `admin/usage` (admin), `admin/reconciliation` (admin) |
| Internal | `record`, `guardrail/reserve`, `guardrail/reconcile`, `guardrail/release` |

The **reserve → reconcile → release** USD hold cycle is the platform's spend gate (used by every priced job). No MCP.

---

## 8. translation-service
### Public (24)
Jobs (`POST/GET .../books/{id}/jobs`, `GET .../jobs/{id}`, `.../jobs/{id}/chapters/{id}`, `POST .../jobs/{id}/cancel`) · retranslate-dirty · versions list/get/set-active/publish/patch-block/edit · `translate-text` (sync) · extract-glossary start/cancel/status · glossary-translate start/cancel/status · coverage + segment-coverage + segment status · preferences get/set · book settings get/set · `actions/{preview,confirm}`.
### Internal (11) — dispatch, job-control, extraction-cache replay/merge/retention/offload, languages, active-text.
### MCP (`/mcp`) — `translation_*` (14). See §12.

---

## 9. knowledge-service
### Public `/v1/{knowledge,kg}/*` (50+) — grouped
Projects CRUD + extraction-config + delete (cascades Neo4j) + schema read/adopt/sync/custom + graph slice/query + views CRUD · extractions start/cancel/status/list/resume/retry/settings (project- and book-scoped) · entities list/get/create/merge/delete + me/entities + gap-report + entity-statuses + entity-facts · pending-facts list/confirm/reject + facts/relations create · graph-schemas CRUD + system create · triage list/resolve/place-edge · passages + `books/{id}/search` (hybrid drawer) + index-drafts · summaries list/get/global+project update/versions/rollback + regenerate-bio · timeline list/create/edit + world timeline rollup · costs + budget · benchmark status/run · logs · drawer search · user-data export/delete · `kg/actions/{preview,confirm}`.
### Internal (20+) — extract, set-campaign-models, extraction-status/cancel, extract-entities (to glossary), wiki generate/job/resume/cancel + kg-hashes + source-text + gen-config, backfills, fact-for-check, parse, summarize, timeline, enriched writeback/promote/retract, coref/detect, context/build + glossary-semantic, job-control.
### MCP (`/mcp`, `/mcp/admin`) — `memory_*`, `kg_*`, `kg_admin_*` (~26 + 2 admin). See §12.

---

## 10. chat-service
### Public `/v1/chat/*` (20)
Sessions CRUD + search · messages list/**POST (SSE turn)**/delete · branches · **`POST .../tool-results`** (resume agent run after frontend-tool execution) · outputs list/get/patch/delete/download · export · voice-message + generate-tts + audio-segments · feedback.
### Internal — `POST /internal/chat/sessions`, `GET /internal/chat/turns/{id}/text`, `POST /internal/chat/evaluate`.
### MCP — **none hosted.** chat-service is the MCP *client* (the agent tool-loop) that calls `ai-gateway/mcp`. It is the reference "internal consumer" the public-MCP design must replace for headless agents.

---

## 11. composition-service
### Public `/v1/composition/*` (38) — works, outline nodes + scene-links, prose get/put, generate (chapter + work + selection-edit + stitch), canon-rules CRUD + templates, style/voice profiles, references + grounding + grounding-pins, approve, narrative-threads, progress, critique/correction/dismiss-violation/correction-stats, suggest-cast, jobs get/persist, decompose + commit, `actions/{preview,confirm}`.
### Internal — pairwise-judge, promise-audit/extract/coverage, job-control.
### MCP (`/mcp`) — `composition_*` (15). See §12.

---

## 12. The MCP tool catalog (~100 tools)

Identity is **envelope-only** (`X-Internal-Token` service auth + `X-User-Id` acting user; `X-Project-Id`/`X-Session-Id`/`X-Trace-Id` optional). All arg models are `extra="forbid"`. Anti-oracle: not-found ≡ not-owned ≡ not-accessible. **Tiers:** **R** read (auto) · **A** auto-write + `undo_hint` · **W** confirm-token-gated · **S** schema/secret 2-step.

### `memory_*` (knowledge) — R
`memory_search`, `memory_recall_entity`, `memory_timeline`, `memory_get_entity`, `memory_forget`.

### `kg_*` (knowledge)
- **R:** `kg_schema_read`, `kg_list_templates`, `kg_view_read`, `kg_graph_query`, `kg_entity_edge_timeline`, `kg_sync_available`, `kg_triage_list`.
- **A:** `kg_adopt_template`, `kg_schema_edit`, `kg_view_upsert`, `kg_view_delete`, `kg_propose_fact`, `kg_propose_edge`, `kg_triage_resolve`, `kg_triage_place_edge`, `kg_sync_apply`.
- **W (cost/confirm):** `kg_project_create`, `kg_build_graph`*, `kg_build_wiki`*, `kg_run_benchmark`*, `kg_triage_schema_write`.  *(* = priced/cost-gated)*

### `glossary_*` (glossary)
- **R:** `glossary_search`, `glossary_get_entity`, `glossary_list_system_standards`, `glossary_list_merge_candidates`, `glossary_list_chapter_links`, `glossary_list_entity_revisions`, `glossary_list_unknown_entities`, `glossary_list_ai_suggestions`, `glossary_get_entity_evidence`, `glossary_book_ontology_read`, `glossary_user_standards_read`, `glossary_web_search`.
- **A:** `glossary_create_chapter_link`, `glossary_create_evidence`, `glossary_propose_translation`, `glossary_adopt_standards`, `glossary_book_set_active_genres`, `glossary_book_set_kind_genres`, `glossary_entity_set_genres`.
- **W (confirm):** `glossary_propose_new_entity`, `glossary_propose_aliases`, `glossary_propose_new_kind`, `glossary_propose_kinds`, `glossary_propose_new_attribute`, `glossary_propose_status_change`, `glossary_propose_restore_revision`, `glossary_propose_reassign_kind`, `glossary_propose_merge`, `glossary_plan`, `glossary_book_create`, `glossary_book_patch`, `glossary_book_delete`, `glossary_book_revert`, `glossary_user_create`, `glossary_user_patch`, `glossary_user_delete`, `glossary_user_restore`, `glossary_book_sync_apply`, `glossary_deep_research`*.

### `book_*` (book)
- **R:** `book_list`, `book_get`, `book_list_chapters`, `book_get_chapter`, `book_list_revisions`.
- **A:** `book_create`, `book_update_meta`, `book_set_cover`, `book_chapter_create`, `book_chapter_update_meta`, `book_chapter_save_draft`, `book_chapter_bulk_create`, `book_audio_generate`*, `book_media_generate`*.
- **W:** `book_chapter_publish`, `book_chapter_unpublish`, `book_chapter_restore_revision`, `book_chapter_delete`, `book_chapter_purge`, `book_delete`, `book_purge`.

### `composition_*` (composition)
- **R:** `composition_get_work`, `composition_list_outline`, `composition_get_prose`, `composition_list_canon_rules`, `composition_get_generation_job`.
- **A:** `composition_create_work`, outline_node create/update/delete/restore, scene_link create/delete, canon_rule create/update/delete, `composition_write_prose`.
- **W:** `composition_publish`, `composition_generate`*.

### `translation_*` (translation)
- **R:** `translation_coverage`, `translation_segment_status`, `translation_list_versions`, `translation_job_status`.
- **A:** `translation_set_active_version`, `translation_save_edited_version`, `translation_patch_block`, `translation_update_settings`.
- **W:** `translation_start_job`*, `translation_retranslate_dirty`*, `translation_start_extraction`*, `translation_job_control` (cancel/pause = A, resume/retry = W).

### `jobs_*` (jobs) — R, user-scoped
`jobs_list`, `jobs_summary`, `jobs_get`.

### `settings_*` (provider-registry) — user-scoped
- **R:** `settings_get_profile`, `settings_list_providers` (secrets redacted), `settings_list_models`, `settings_get_defaults`, `settings_provider_inventory`.
- **A:** `settings_update_profile`, `settings_model_register` (no secret), `settings_model_update`, `settings_model_set_favorite`, `settings_model_set_active`, `settings_model_set_default`.
- **W:** `settings_model_delete`. **S (UI-only):** provider credential secret creation is **never** an MCP arg.

### `lore_enrichment_*` (lore-enrichment) — W
`lore_enrichment_auto_enrich`*.

### Admin (`/mcp/admin`)
`glossary_admin_standards_read` (R), `glossary_admin_propose_{create,patch,delete,restore}` (W), `kg_admin_template_read` (R), `kg_admin_propose_template` (W). Gated by RS256 `X-Admin-Token`.

**Cost-gated tools** (`*`): `kg_build_graph`, `kg_build_wiki`, `kg_run_benchmark`, `composition_generate`, `translation_start_job`, `translation_retranslate_dirty`, `translation_start_extraction`, `glossary_deep_research`, `lore_enrichment_auto_enrich`, `book_audio_generate`, `book_media_generate`. Each returns an estimate + `_meta.confirm_token`; **only** the `/v1/<domain>/actions/confirm` endpoint re-prices and spends.

---

## 13. Out-of-catalog services (summary only)

- **Game / world (LLM-MMO-RPG):** `game-server` (Colyseus WS — the *sanctioned 2nd public entry*), `world-service`, `tilemap-service`, `travel-service`. The `world` **FE** feature is out of scope by request. These have their own auth edge (WS ticket + per-message authz, see `docs/03_planning/LLM_MMO_RPG/.../S12_websocket_security.md`).
- **Ops / infra (no user-facing surface):** admin-cli, alert-recorder, archive-worker, backup-scheduler, breach-notifier, canary-controller, incident-bot, integrity-checker, meta-outbox-relay, meta-worker, migration-orchestrator, postmortem-bot, publisher, retention-worker, slo-budget-calculator, statuspage-updater, worker-ai, worker-infra. Background workers / SRE automation; not part of the public API surface.

---

## 14. Frontend feature surface (26 features, game FE excluded)

Each FE feature is a `features/<name>/` MVC module (hooks/context/components/api.ts). The full per-feature API-call listing is in the deep-dive; summarized here by the BE it drives:

| FE feature | Drives (BE) | Notable |
|---|---|---|
| books | book-service + sharing + catalog | core CRUD, chapters, media, collaborators, import |
| browse / catalog | catalog + statistics | public discovery |
| chat | chat-service (+ ai-gateway tools, pending-facts) | the agent surface; tool-results resume |
| composition | composition-service | LOOM studio, SSE generate, human-gate corrections |
| translation | translation-service | coverage matrix, v3 QA loop, versions |
| glossary / standards | glossary-service | entities/kinds/attrs; assistant confirm cards |
| glossary-translate | translation-service | batch entity translation |
| wiki | glossary-service (wiki) + knowledge (gen) | articles, revisions, suggestions, staleness |
| knowledge | knowledge-service | projects, graph canvas, timeline, drawer search, budget |
| extraction | translation/knowledge | start/cancel KG extraction |
| enrichment | lore-enrichment-service | gap-detect, proposals, sources |
| campaigns | campaign-service | auto-draft factory + report |
| roleplay | roleplay-service + chat | persona scripts, evaluate |
| jobs | jobs-service | unified job console + SSE |
| notifications | notification-service | center + SSE |
| usage | usage-billing-service | logs, summary, guardrail |
| ai-models / settings | provider-registry + auth | BYOK, models, defaults, account |
| profile | auth + statistics + glossary | public profile, follow, contributions |
| leaderboard | statistics-service | rankings |
| raw-search | book + knowledge | lexical + hybrid search |
| video-gen | video-gen-service | video generation + poll |
| grammar | (LanguageTool, local) | client-side, not a platform BE |
| onboarding | (gates on flag) | first-run fork |
| trash | book-service | unified trash view |

**FE↔agent integration today:** only via chat-service's tool-loop. The FE never calls `/mcp` directly; `ai-gateway` is not reachable from the FE.
