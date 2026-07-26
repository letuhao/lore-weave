# Glossary-Assistant — Scenario Coverage & Gap Analysis (CLARIFY)

> **Date:** 2026-06-10. **Status:** CLARIFY / analysis — input to a follow-on build campaign.
> **Purpose:** enumerate the realistic user scenarios for the glossary-assistant, draft a test script per scenario, reconcile each against what the codebase actually has across **three layers**, and derive the BE+FE+MCP implementation backlog. Source: 3 parallel code-exploration passes (glossary CRUD, assistant MCP/FE tools, extraction+translation pipelines).
> **Scope note:** this covers the *assistant-driven* (chat) path AND the *manual UI* path, because a scenario is only "done" when the user can do it the way they expect — by asking the assistant.

---

## ▶ STATUS UPDATE — 2026-06-20 (post genre·kind·attribute re-arch + Tiered-MCP-Tools epic)

> The verdicts in Parts B/C below are **frozen at the original 2026-06-10 CLARIFY**. This block re-assesses S1–S26 against what is actually built now. **Method:** the doc's own L2 lens — *can the agent reach it?* — checked against the live MCP tool inventory (`mcp_server.go` + `book_tools.go` + `sync_tools.go` + `user_tools.go` + `admin_tools.go`) and the 3 chat-service frontend tools (`propose_edit`, `glossary_propose_entity_edit`, `glossary_confirm_action`).
>
> **Headline: the ONTOLOGY half is done; the PIPELINE half (extract / translate / research) and several query/UX scenarios are still agent-blind.** The Tiered-MCP-Tools epic (CP-0→CP-7) added the tiered System/User/Book CRUD + adopt + sync + the class-C confirm spine + admin tier — exactly the L2 gap this doc's headline flagged ("only 6 MCP tools exist"). It did **not** add extraction/translation/web-research tools.

**Agent MCP tool inventory now (glossary):** read — `glossary_search`, `glossary_get_entity`, `glossary_list_system_standards`, `glossary_book_ontology_read`, `glossary_user_standards_read`, `glossary_admin_standards_read`, `glossary_entity_get_genres`; write/propose — `glossary_propose_new_entity|kind|attribute`, `glossary_book_create|patch|delete`, `glossary_user_create|patch|delete|restore`, `glossary_admin_propose_create|patch|delete`, `glossary_adopt_standards`, `glossary_book_set_active_genres`, `glossary_book_set_kind_genres`, `glossary_entity_set_genres`; sync — `glossary_book_sync_available|apply`. (No merge / translate / extract / evidence / chapter-link / triage tool exists.)

| # | Scenario | 2026-06-10 | **Now** | What closed it / the remaining gap |
|---|---|---|---|---|
| S1 | Full CRUD (genre/kind/attr/entity) | PARTIAL | **✅** | book/user/admin create+patch+**delete** across tiers; entity create/edit via propose tools |
| S2 | New kind **+ its attributes**, one approval | PARTIAL | **⚠️** | per-level create tools + `adopt` copies a whole genre cell, but a *new* kind + N *new* attributes is still multiple confirm cards (no bundled multi-op card) |
| S3 | Optimize existing kind to genre | PARTIAL | **✅** | `book_patch` + `set_kind_genres` + `adopt`/`sync` |
| S4 | Translate entries via the assistant | PARTIAL | **❌** | backend (`glossary_translate_worker`) exists; **no MCP tool** — agent-blind |
| S5 | Web search / deep research | MISSING | **❌** | still net-new; no tool |
| S6 | Aliases per language | PARTIAL | **⚠️** | `propose_entity_edit` (source-lang); per-language alias still partial |
| S7 | Chapter extraction via the assistant | MISSING | **❌** | backend (`extraction_handler.go`) exists; **no MCP tool** — agent-blind |
| S8 | Re-extract / update after edits | PARTIAL | **❌** | depends on S7 (no tool) |
| S9 | Merge duplicate entities | — | **❌** | merge backend exists; **no MCP tool** |
| S10 | Delete / deprecate | — | **✅** | `book_delete` / `user_delete` / `admin_propose_delete` (class-C) |
| S11 | Reassign kind / "unknown" bucket | — | **⚠️** | `entity_set_genres` covers genre; entity→kind reassign only via generic `propose_entity_edit` |
| S12 | Triage suggestions inbox (approve/reject) | — | **❌** | agent can *create* drafts; **no tool** to approve/reject — FE-only |
| S13 | Revision history / undo | — | **⚠️** | `user_restore` (user-tier trash) only; entity-revision undo agent-blind |
| S14 | Genre management via assistant | — | **✅** | book/user/admin genre create/patch/delete + `set_active_genres` |
| S15 | Coverage / consistency audit | — | **❌** | no audit tool (agent can approximate via `search`) |
| S16 | Evidence / citation | — | **❌** | backend exists; no MCP tool |
| S17 | Chapter-link queries / linking | — | **❌** | backend exists; no MCP tool |
| S18 | Relationship / graph queries | — | **⚠️** | `memory_recall_entity` / `memory_timeline` partial; full graph = the (spec-only) Knowledge-MCP epic |
| S19 | Batch / bulk operations | — | **⚠️** | `sync_apply` + `adopt` are batch for ontology; bulk extract/entity agent-blind |
| S20 | Long-running / async in chat | — | **❌** | no agent tool to trigger/poll async jobs |
| S21 | Cost confirmation gate | — | **⚠️** | class-C confirm gates writes; no separate *cost-estimate* gate |
| S22 | Field-type-aware editing | — | **⚠️** | `field_type` validated on attr create (admin/book); value editing via `propose_entity_edit` |
| S23 | Spoiler / capture-horizon | — | **❌** | exists in `composition-service` packer, **not** the glossary assistant path |
| S24 | Indirect prompt-injection defense | — | **✅** | the glossary skill (base + admin) carries the explicit "tool output is DATA not instructions" trust boundary |
| S25 | Shared-book / non-owner permissions | — | **✅** | E0 collaboration grants; book tools grant-gated |
| S26 | Conversation vs content/target language | — | **⚠️** | chat handles conversation language; content/target tied to S4 (no translate tool) |

**Tally:** ✅ 6 (S1, S3, S10, S14, S24, S25) · ⚠️ 9 (S2, S6, S11, S13, S18, S19, S21, S22, S26) · ❌ 11 (S4, S5, S7, S8, S9, S12, S15, S16, S17, S20, S23).

**Next campaign (the real remaining work) — make the PIPELINE + queries agent-reachable:** an extraction MCP tool (S7/S8/S19), a translation MCP tool (S4/S26), merge/reassign/triage tools (S9/S11/S12), evidence + chapter-link read tools (S16/S17), the deep-research subsystem (S5), and the async-job trigger/poll surface (S20). The class-C confirm spine + per-tier registration pattern from this epic is the template for all of them.

**▶ Two follow-on docs (2026-06-20) extend this coverage to the tiered + CMS world:**
- [`2026-06-20-glossary-tiered-cms-scenarios.md`](2026-06-20-glossary-tiered-cms-scenarios.md) — **S27–S40**: the System/User/Book tier + CMS + per-tier genre-edit scenarios, each with **human (FE)** and **AI (MCP)** verdicts.
- [`docs/plans/2026-06-20-glossary-tiered-cms-gap-plan.md`](../plans/2026-06-20-glossary-tiered-cms-gap-plan.md) — the **FE/BE gap backlog** (P0 reversibility → P1 CMS UX parity → P2 authoring → P3 polish), with corrections for the stale drafts.

---

## Part A — The 3-layer coverage model

For every capability, three independent layers must exist before the assistant can deliver it:

| Layer | Meaning | Where |
|---|---|---|
| **L1 — Backend** | An HTTP endpoint (`/v1` JWT or `/internal` service-token) that performs the operation, with ownership + concurrency guards. | `services/glossary-service`, `translation-service`, etc. |
| **L2 — Agent-reachable** | An **MCP tool** (read/write-proposal, via `ai-gateway`) OR a **chat-service frontend-tool** (suspend→card→Apply) that lets the LLM drive L1. **This is the MCP-first invariant.** | `glossary-service/internal/api/mcp_server.go`, `chat-service/app/services/frontend_tools.py` |
| **L3 — FE surface** | The rendered UI — either a manual panel in the glossary feature, or the assistant **card** (DiffCard / SchemaConfirmCard) that gates the write. | `frontend/src/features/glossary/*`, `frontend/src/features/chat/components/*` |

**Key reconciliation finding:** the glossary backend (L1) is *broad* — full CRUD on entities, kinds, attributes, genres, **per-language translations**, evidence, chapter-links, revisions, merge, recycle-bin. The bottleneck for the assistant is overwhelmingly **L2**: only 6 MCP tools + 2 frontend-tools exist, so most L1 capability is unreachable by the agent today.

### Current L2 inventory (what the agent can actually do)

**Glossary MCP tools** (`mcp_server.go`): `glossary_search`, `glossary_get_entity`, `glossary_list_kinds` (read); `glossary_propose_new_entity` (write-draft); `glossary_propose_new_kind`, `glossary_propose_new_attribute` (mint confirm-token, no write).
**chat-service frontend-tools** (`frontend_tools.py`): `glossary_propose_entity_edit` (→ GlossaryDiffCard → `apply-edit`), `glossary_confirm_schema` (→ SchemaConfirmCard → `/v1/glossary/schema/confirm`).
**knowledge MCP tools** (federated): `memory_search`, `memory_recall_entity`, `memory_timeline`, `memory_remember`, `memory_forget`.

---

## Part B — The 8 user scenarios

Each scenario: a test script (Given/When/Then), then per-layer coverage and the gap.

### S1 — Full CRUD of genre, kind, attribute, glossary entity

**Test script**
- Given a book I own, When I create/list/read/update/delete a **genre**, a **kind**, an **attribute (def + value)**, and a **glossary entity** (incl. aliases), Then each operation persists, is ownership-checked, and (for entity/attr-value) version-guarded.

**Coverage**

| Target | L1 Backend | L2 Agent | L3 Manual UI | L3 Assistant card |
|---|---|---|---|---|
| Genre | ✅ List/Create/Update/Delete (no single-read) | ❌ no tool | ✅ GenreGroupsPanel | ❌ |
| Kind | ✅ List/Create/Update/Delete/Reorder | ⚠️ create-only (propose_new_kind); no update/delete | ✅ kind editor | ⚠️ schema-confirm (create) |
| Attribute def | ✅ Create/Update/Delete/Reorder | ⚠️ create-only (propose_new_attribute); no update/delete | ✅ embedded | ⚠️ schema-confirm (create) |
| Attribute value | ✅ Patch (If-Match) | ✅ propose_entity_edit | ✅ entity editor | ✅ DiffCard |
| Entity | ✅ full + merge/revisions/recycle-bin | ⚠️ create+edit; no delete/merge/reassign | ✅ full | ✅ DiffCard |
| Alias (per-entity) | ✅ as `aliases` attribute value | ✅ via propose_entity_edit | ✅ entity editor | ✅ DiffCard |

**Gaps:** assistant cannot **delete** (entity/kind/attr), **update kind/attr metadata**, or **CRUD genres**. Manual UI is largely complete. Backend missing: kind-alias update/delete; single-read endpoints (minor).

**Verdict: PARTIAL** — manual CRUD ≈ complete; assistant CRUD is read+create+edit only.

---

### S2 — Suggest a NEW kind for a specific genre (with attribute list) → user reviews draft → approve → kind created + applied to book

**Test script**
- Given book B with genre "Xianxia", When I ask "đề xuất một kind mới cho truyện tu tiên này, kèm các attribute phù hợp", Then the assistant proposes a kind **with its attributes in one reviewable draft**, I approve once, the kind + all attributes are created, tagged with the book's genre, and become usable in B.

**Coverage**
- L1: ✅ `/v1/glossary/schema/confirm` creates kind; attributes created via separate confirm. `genre_tags` settable on kind.
- L2: ⚠️ `glossary_propose_new_kind` mints a token for the **kind only**; each attribute needs its own `glossary_propose_new_attribute` + its own `glossary_confirm_schema`.
- L3: ⚠️ SchemaConfirmCard confirms **one op at a time**.

**Gap — the headline UX problem:** a "new kind + 8 attributes" request becomes **9 separate confirm cards**. There is no **bundled schema proposal** (one card = kind + N attributes, one approval, one transactional create). Also "applied to book": kinds are **global**, not per-book — `genre_tags` is the only book-affinity; confirm should set it from the book's genre, and the user should understand the kind is global.

**Verdict: PARTIAL** — works mechanically, terrible UX for the realistic "kind + attributes" ask. **Needs: bundled schema-proposal tool + multi-op confirm card + transactional multi-create endpoint.**

---

### S3 — Optimize an EXISTING kind to fit the book's genre

**Test script**
- Given kind "Character" and book B (genre "Wuxia"), When I ask "tối ưu kind Character cho truyện võ hiệp này", Then the assistant proposes adds/edits/removes of attributes (e.g. add `martial_school`, retire `magic_level`), I review the full change-set, approve once, and the kind reflects it.

**Coverage**
- L1: ✅ attr create/update/delete + kind patch (`genre_tags`, name, etc.) all exist.
- L2: ⚠️ can only **add** attributes (propose_new_attribute). **No tool to edit or remove** an existing attribute, or to patch kind metadata.
- L3: ⚠️ single-op confirm only.

**Gap:** "optimize" = add **and** modify **and** remove, presented as one change-set. Today the agent can only add, one at a time. **Needs: propose-attribute-edit + propose-attribute-remove (or a unified "propose schema change-set") tool + a multi-row schema diff card.** Removal is destructive (drops attr values) → needs its own confirmation semantics.

**Verdict: PARTIAL (add-only).**

---

### S4 — Translate one/many glossary entries, user suggests preferred name translations

**Test script**
- Given 5 entities with Chinese names, When I ask "dịch tên 5 nhân vật này sang tiếng Việt; với 焰魔 tôi muốn 'Diễm Ma'", Then the assistant proposes target-language names (honoring my override), I review, approve, and the translations persist per-language at `confidence != machine`.

**Coverage** *(corrected after reconciliation)*
- L1: ✅ **per-language translation CRUD EXISTS** — `POST/PATCH/DELETE /v1/glossary/books/{b}/entities/{e}/attributes/{av}/translations` with `language_code` + `confidence`; never overwrites `verified`. FE `api.ts` has `createTranslation/patchTranslation/deleteTranslation`.
- L2: ❌ **no agent tool writes translations.** `glossary_propose_entity_edit` targets `short_description` + attribute `original_value` only — **not** the `translations` sub-resource.
- L3: ⚠️ translation editing is embedded in the entity editor (no dedicated translate dialog); **no batch translate UI**; no per-language **alias** variants in UI (aliases are a single source-language `tags` value).

**Gap:** the data layer is ready; the assistant simply has **no path to propose/write a translation**, and there's **no batch translation flow** (translate N entities at once with per-entity overrides). **Needs: a translation propose tool (extend propose_entity_edit with a `translation` target, or a new `glossary_propose_translation`) + a translation-review card + a batch surface.**

**Verdict: PARTIAL** — backend ready, agent-blind, no batch UX.

---

### S5 — Use web search / deep research to inform suggestions

**Test script**
- Given an entity "Nezha", When I ask "tra cứu thêm về nhân vật này và bổ sung mô tả có dẫn nguồn", Then the assistant performs a web search / deep-research pass, proposes an enriched description **with source URLs as evidence**, I review + approve.

**Coverage**
- L1/L2/L3: ❌ **entirely MISSING.** No web-search/research integration anywhere in the backend (no Tavily/Perplexity/Bing/SerpAPI; grep-clean). knowledge `memory_search` is **internal project memory only**. No MCP research tool. No evidence-from-URL flow.

**Gap — the largest new build.** Requires: a research capability **routed through `provider-registry`** (per the provider-gateway invariant — no direct SDK), exposed as an MCP tool (`web_search` / `deep_research`), plus a **cost/confirmation gate** (research is expensive + outward-facing), plus a path to attach fetched sources as **evidence** on the proposed change. Indirect-injection defense (INV-6) becomes critical — fetched web text is hostile DATA.

**Verdict: MISSING — net-new subsystem.**

---

### S6 — Add/edit one or many aliases in a specific language

**Test script**
- Given entity 焰魔, When I ask "thêm alias tiếng Việt 'Diễm Ma' và 'Ma Lửa', sửa alias tiếng Anh 'Flame Demon'→'Flame Fiend'", Then aliases are stored **scoped by language**, reviewable as a diff, approved once.

**Coverage**
- L1: ⚠️ aliases are stored as a **single `aliases` attribute value** (a `tags` array) in the source language. Per-language alias = `attribute_translations` on that `aliases` attr value (language_code) — **mechanically possible but never modeled/used as "aliases per language".**
- L2: ✅ for source-language aliases (edit the `aliases` value via `propose_entity_edit`). ❌ for **per-language** aliases (no translation-target tool — same gap as S4).
- L3: ⚠️ source-language only; no per-language alias editor.

**Gap:** "alias in a specific language" is **not a first-class concept**. Either (a) define per-language aliases as translations of the `aliases` attribute and build tooling/UI for it, or (b) introduce a proper alias model with a language field. This is a **data-model decision** before tooling. Source-language alias edit already works via the diff card.

**Verdict: PARTIAL (source-language only).**

---

### S7 — Extract glossary for one/many chapters

**Test script**
- Given chapters 1–10 of book B, When I ask the assistant "trích xuất glossary cho chương 1–10", Then an extraction job runs (cost shown/confirmed), entities are upserted as `draft`/`ai-suggested`, and I see the created/updated counts + a link to review.

**Coverage**
- L1: ✅ full pipeline exists — FE `ExtractionWizard` → `POST /v1/extraction/books/{b}/extract-glossary` (translation-service) → RabbitMQ → worker → LLM → `POST /internal/books/{b}/extract-entities` (glossary writeback). Cost estimate + job status + WebSocket progress.
- L2: ❌ **no MCP tool to trigger extraction.** Extraction is **wizard/pipeline-driven only** — the agent cannot start it, cannot report progress, cannot return results.
- L3: ✅ ExtractionWizard (manual, 5 steps). ❌ no assistant-initiated path.

**Gap:** the entire extraction pipeline is **invisible to the assistant**. Per MCP-first, "ask the assistant to extract" needs an MCP tool that creates the job + a way to surface async progress/results in chat (long-running op → job-handle pattern; the chat turn can't block on a multi-chapter LLM job). This is a meaningful **agent-async** design problem, not just a missing endpoint.

**Verdict: MISSING for the assistant** (manual UI complete).

---

### S8 — Re-extract / update glossary for chapters after optimizing a kind or editing attributes (partial vs full update / merge)

**Test script**
- Given I just added attribute `martial_school` to kind Character, When I ask "cập nhật lại glossary cho chương 1–20 với attribute mới này, chỉ điền chỗ trống" (fill) — or "ghi đè toàn bộ" (overwrite), Then re-extraction runs with the chosen **merge mode**, existing entities get the new attribute, human-verified values are protected, and overwrites are audit-logged.

**Coverage**
- L1: ✅ merge semantics fully implemented — `attribute_actions[kind][attr] = fill|overwrite` per attribute; `fill` writes only if empty; `overwrite` writes + `extraction_audit_log`; evidence/chapter-links append-only; `ai-rejected` tombstone respected; profile re-resolves new attributes dynamically.
- L2: ❌ same as S7 — no agent trigger; agent has no exposure to `attribute_actions` modes.
- L3: ⚠️ wizard supports per-attribute fill/overwrite/skip, **but no "overwrite all" preset** and **no post-kind-edit "re-extract affected chapters?" prompt**; no "refresh all chapters for kind X" shortcut; no kind-version tracking to know what's stale.

**Gap:** mode logic (partial/overwrite/merge) is **already correct and rich at L1** — the gaps are (a) agent can't drive it, (b) UX friction (manual per-attribute toggles, no staleness signal after a schema edit). **Needs: extraction MCP tool exposing mode + chapter selection; FE staleness prompt + bulk-mode presets.**

**Verdict: PARTIAL** — backend strong, agent-blind, UX gaps.

---

## Part C — Additional scenarios (answering "còn kịch bản gì khác?")

These are realistic and **not** in the original 8. Most are L1-present / L2-missing — i.e. the assistant can't do them yet.

**Glossary-management scenarios**
- **S9 — Merge duplicates.** "tìm và gộp các nhân vật trùng" → backend merge + merge-candidate inbox exist (L1✅); **no agent tool** (L2❌). Destructive → needs confirm card.
- **S10 — Delete / deprecate.** Delete an entity; delete/deprecate a kind or attribute. L1✅ (soft-delete + recycle-bin + delete guards); L2❌. Destructive → confirm + undo story (recycle-bin/revisions exist).
- **S11 — Reassign kind / resolve unknown bucket.** "nhân vật này bị xếp nhầm loại, đổi sang Character" or "xử lý các entity unknown". L1✅ (reassign-kind, kind-aliases, unknown-entities); L2❌.
- **S12 — Approve/reject the AI-suggestions inbox.** "duyệt các entity AI đề xuất, chấp nhận cái tốt". L1✅ (draft + ai-suggested + AiSuggestionsPanel + tombstone); L2❌ — assistant can't triage its own drafts.
- **S13 — Revision / undo.** "khôi phục entity này về bản trước", "có gì thay đổi". L1✅ (revisions + restore + merge-journal revert); L2❌.
- **S14 — Genre management via assistant.** "tạo nhóm genre Tiên Hiệp và gắn cho các kind phù hợp". L1✅; L2❌ (genre has no agent tool at all).

**Read / QA / consistency scenarios**
- **S15 — Coverage / consistency audit.** "nhân vật nào thiếu mô tả", "ai xuất hiện trong chương nhưng chưa có trong glossary", "attribute nào mâu thuẫn". Mostly **no tool**; needs read/aggregate tools (some derivable from raw-search + glossary_search).
- **S16 — Evidence / citation read + write.** "đoạn nào chứng minh điều này", "thêm trích dẫn nguồn cho attribute". L1✅ (evidence CRUD); L2❌ (glossary_get_entity may not even return evidence — confirm; no evidence write tool).
- **S17 — Chapter-link queries.** "X xuất hiện ở những chương nào", "liên kết entity này với chương N". L1✅; L2❌.
- **S18 — Relationship / graph queries.** "ai là sư phụ của X", quan hệ giữa các nhân vật. Partly via knowledge `memory_recall_entity` + a `relationship` kind; cohesion unclear.

**Cross-cutting concerns (apply to many scenarios)**
- **S19 — Batch / bulk operations.** translate-all, re-extract-all-for-kind, apply-attribute-to-all-entities-of-kind, backfill a new required attribute. Today = **N sequential tool calls** (no batch tool). Needs a batch-proposal pattern + partial-failure reporting.
- **S20 — Long-running / async ops in chat.** Extraction, deep-research, batch translate are async/expensive → the chat turn can't block. Needs a **job-handle + progress-in-chat** pattern (the assistant starts a job, returns a handle, surfaces status). This is a prerequisite design for S5/S7/S8/S19.
- **S21 — Cost confirmation gate.** Extraction + research + batch translate cost money/tokens → confirm-before-run card with an estimate (extraction already estimates cost at L1; assistant path has no gate).
- **S22 — Field-type-aware editing.** Editing a `select` attribute must validate against `options`; `tags` vs `number` vs `date` vs `boolean` must render/validate correctly in the diff card. Partial today.
- **S23 — Spoiler / capture-horizon.** When the assistant describes an entity, bound info to chapters the reader has reached (the wiki spoiler concept) — relevant once the assistant summarizes lore.
- **S24 — Indirect prompt-injection from untrusted text.** Already defended (INV-6) for glossary/chapter text; **becomes load-bearing** the moment web-search (S5) ingests hostile external content.
- **S25 — Shared-book / non-owner permissions.** Operating on a book shared with me (not owned). Ownership is fail-closed today; "shared editor can use the assistant" is untested.
- **S26 — Conversation vs content language.** User speaks Vietnamese, names are Chinese, translations English — the assistant must not confuse "language of my request" with "target translation language."

---

## Part D — Consolidated implementation backlog (BE + FE + MCP)

Grouped by the dominant gap. Priority is a suggestion, not a commitment.

### Group 1 — L2 read/write tools for already-built L1 (highest leverage, lowest risk)
The backend exists; we only add MCP/frontend tools + cards. Unlocks S1, S9–S14, S16, S17.
- **MCP write-proposal tools** (mint-or-suspend, human-gated): delete-entity, merge-entities, reassign-kind, restore-revision, genre CRUD, kind/attr **update + delete**.
- **MCP read tools:** read evidence, read chapter-links, read revisions, read AI-suggestions inbox, list unknown entities.
- **FE:** generalize the confirm/diff card family for destructive ops (delete/merge) with undo affordance.

### Group 2 — Schema change-sets (fixes S2, S3)
- **BE:** transactional multi-create/edit/remove schema endpoint (kind + N attributes + attribute edits/removals in one tx, token-gated).
- **L2:** a **bundled** `glossary_propose_schema_change` tool (one token, full change-set incl. removals).
- **FE:** a multi-row **schema change-set card** (adds/edits/removes in one approval).

### Group 3 — Translation tooling (fixes S4, S6)
- **Decision first:** model per-language **aliases** (translations-of-aliases vs new alias model).
- **L2:** translation propose tool (extend `propose_entity_edit` with a `translation` target, or new tool) — writes `attribute_translations` at `confidence='draft'` honoring the no-overwrite-verified rule.
- **FE:** translation-review card + a **batch translate** surface (N entities, per-entity override, partial-failure report).

### Group 4 — Assistant-driven extraction (fixes S7, S8) + async pattern (S20, S21)
- **L2:** MCP tool to **create an extraction job** (chapter selection + `attribute_actions` mode) → returns a **job handle**, not a blocking result.
- **Chat/async:** a progress-in-chat pattern (poll job status, surface counts on completion) — reuse the existing WebSocket job channel.
- **FE:** cost-confirmation card; post-kind-edit **"re-extract affected chapters?"** prompt; "overwrite all" / "fill all" presets; optional kind staleness signal.

### Group 5 — Web search / deep research (fixes S5) — net-new
- **BE:** research capability **via `provider-registry`** (no direct SDK); cost metering.
- **L2:** `web_search` / `deep_research` MCP tool; attach fetched sources as **evidence** on proposals.
- **Security:** harden INV-6 for hostile external text; cost-gate (S21); outward-facing-call confirmation.

### Group 6 — QA / consistency (fixes S15, S18) — research-y
- Aggregate read tools (missing-description, mentioned-but-absent, contradiction) layered on glossary_search + raw-search + knowledge graph.

---

## Part E — Open questions — RESOLVED 2026-06-10

> All resolved by the user. See the **LOCKED architecture decisions (D1–D8)** + **revised build order** in the companion doc [`2026-06-10-glossary-assistant-extended-scenarios.md`](2026-06-10-glossary-assistant-extended-scenarios.md). Summary: cover ALL scenarios easy→hard (D1); first-class alias table (D2); Path B async (D3); confirm-card+undo (D4); glossary-SSOT relationships (D5); staged web research (D6); honor share-grants (D7); global kinds + additive per-book derived layer (D8). Foundational phase F1–F5 precedes Group 1.

<details><summary>Original open questions (now answered)</summary>

1. **Priority order:** is the goal "assistant can do everything the UI can" (Group 1 first — cheap, high coverage), or chase the headline features (S2/S5)?
2. **Per-language aliases (S6):** treat as translations of the `aliases` attribute, or introduce a first-class alias model with a `language` column? (data-model decision, blocks tooling)
3. **Web/deep research (S5):** in scope now, or defer? If in scope — which provider, routed through provider-registry, and what cost ceiling per request?
4. **Schema change-sets (S2/S3):** are you OK with kinds staying **global** (genre_tags = the only book affinity), or do you want a notion of "kind belongs to / is enabled for this book"? (bigger model change)
5. **Async ops in chat (S7/S8/S19):** acceptable to have the assistant **start a job and report later** (handle pattern), vs. expecting an inline synchronous result?
6. **Destructive ops via assistant (S9/S10):** how much guard — single confirm card + recycle-bin/undo, or extra friction (typed confirmation)?

</details>

---

## Appendix — key file references

- Glossary MCP tools: `services/glossary-service/internal/api/mcp_server.go`
- Schema confirm: `services/glossary-service/internal/api/schema_confirm_handler.go`, `apply_edit_handler.go`
- Extraction writeback (fill/overwrite/merge): `services/glossary-service/internal/api/extraction_handler.go` (`bulkExtractEntities`, `mergeExtractedEntity`, `findEntityByNameOrAlias`)
- Per-language translation CRUD: `services/glossary-service/internal/api/attribute_handler.go` (translation create/patch/delete)
- Extraction job + worker: `services/translation-service/app/routers/extraction.py`, `app/workers/extraction_worker.py`, `app/workers/glossary_client.py`
- Frontend tools / cards: `services/chat-service/app/services/frontend_tools.py`, `frontend/src/features/chat/components/{GlossaryDiffCard,SchemaConfirmCard,AssistantMessage}.tsx`
- Glossary skill: `services/chat-service/app/services/glossary_skill.py`
- Manual glossary UI: `frontend/src/features/glossary/` (api.ts, components/, hooks/)
- Extraction wizard UI: `frontend/src/features/extraction/ExtractionWizard.tsx`, `frontend/src/pages/book-tabs/GlossaryTab.tsx`
