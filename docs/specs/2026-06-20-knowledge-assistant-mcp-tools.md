# Spec — Knowledge Assistant: MCP Tool Surface

**Date:** 2026-06-20 · **Status:** DESIGN (spec only, no code) · **Branch (build later):** với KG ontology epic (`feat/knowledge-graph-ontology`)
**Owning service:** `knowledge-service` (tools sống ở đây theo MCP-first; `ai-gateway` chỉ federate)
**Mirror pattern:** [`2026-06-20-glossary-assistant-tiered-tools.md`](2026-06-20-glossary-assistant-tiered-tools.md) (tiers R/W/C, `/mcp/admin` tách riêng + RS256, confirm-token §13). **Tích hợp:** [`2026-06-20-knowledge-graph-customizable-ontology.md`](2026-06-20-knowledge-graph-customizable-ontology.md) (lớp dữ liệu: graph schema tiered, views, triage).

---

## 1. Why

Knowledge-service **đã có** một MCP server (`app/mcp/server.py`) với 5 memory tool, federate qua ai-gateway. Nhưng:
- Bộ tool đó **chỉ biết thế giới memory phẳng** (search/recall/timeline + remember/forget). Không có graph read theo temporal/view, không có propose-write có version-check, **không** có tool nào cho ontology customizable mới (adopt graph template, sửa edge/vocab, views, triage), không có admin System-tier.
- Toàn bộ năng lực mới này là **agentic** (LLM quyết định adopt/sửa schema/resolve triage) → **bắt buộc** là MCP tool qua ai-gateway (MCP-first invariant), không được làm endpoint prompt riêng.

**Goal:** cho AI agent **toàn quyền, tenancy-safe, human-gated** trên knowledge graph qua 3 tier **System / User / Project** — đọc graph theo thời gian, đề xuất fact/edge, định hình ontology của project, chạy sync, build template ở user tier, và (admin) quản System template — mỗi năng lực là một MCP tool trên knowledge-service.

**Locked (2026-06-20):**
- Spec cả epic trước, build phase-by-phase (giống glossary).
- Scope key của knowledge = **`project_id`** (không phải book_id). Grant project View/Edit/Manage (knowledge đã có grant client).
- Admin/System: **CMS-surface only + RS256 + human-confirm**, tái dùng **nguyên** mô hình glossary §4/§13 (machinery riêng cho knowledge vì khác service/ngôn ngữ, nhưng **cùng contract**).

---

## 2. Current agentic surface (baseline — đã ship, 5 tool)

| Tool | Loại | Gate | Nguồn |
|---|---|---|---|
| `memory_search` | read (semantic passage) | service-token + per-call `X-User-Id` + project scope | [definitions.py](../../services/knowledge-service/app/tools/definitions.py) |
| `memory_recall_entity` | read (entity + relations by name) | như trên | |
| `memory_timeline` | read (events, lọc date/entity) | như trên | |
| `memory_remember` | **write-immediate** (fact, low-confidence, assistant-tagged, reviewable) | per-call user id | |
| `memory_forget` | write (invalidate fact by id) | per-call user id | |

**Đường đi THẬT (đã verify code 2026-06-20):** chat-service gọi tool **qua ai-gateway `/mcp` federation** — `knowledge_client.py:349` (list-tools) + `:407` (execute) đều trỏ `ai_gateway_url/mcp`; gateway federate knowledge `/mcp` (`config.ts:36 KNOWLEDGE_MCP_URL`). **ĐÃ conformant MCP-first từ P0 (2026-06-10).** Envelope: ai-gateway forward `X-Internal-Token` + `X-User-Id`/`X-Project-Id`/`X-Session-Id` (per-call, KHÔNG từ LLM). Executor validate `tool_args` Pydantic (`extra="forbid"`). **Giữ envelope này cho mọi tool mới.**

> **Legacy dual-run (gỡ trong epic này — KM0, KHÔNG defer):** knowledge còn giữ `routers/internal_tools.py` (`/internal/tools/execute` + `/internal/tools/definitions`) + chat-service `knowledge_client.py::execute_tool()` (parity cũ) — **không còn runtime caller** (grep-verify: chỉ test/docs). Docstring `definitions.py` ("the chat-service `/internal/tools/execute` envelope", design D3) đã **stale**. KM0 retire toàn bộ legacy path + sửa docstring (§8).

> Khác glossary: `memory_remember` là **write-immediate có review-sau** (low-confidence + pending_facts), không phải propose-trước. Giữ vậy cho fact rẻ; nhưng **graph edge / schema / adopt** (high-impact) theo đúng pattern propose/confirm của glossary.

---

## 3. Target tool inventory (gap → ~18 tool mới)

R = read trực tiếp · W = write trực tiếp (low-impact, reversible, grant/owner-gated) · C = confirm-token (LLM propose → human confirm; high-impact / destructive / shared-scope / **đổi shape graph** / System tier).

### 3a. Graph read (đọc graph theo view + thời gian) — spec ontology §3.6
| Tool | Wraps | Gate | Class |
|---|---|---|---|
| `kg_graph_query` | graph read `?view=&as_of_chapter=N` (nodes+edges lọc view + temporal as-of) | project `GrantView` | R |
| `kg_entity_edge_timeline` | `/entities/{id}/edges/{edge_type}/timeline` (vd drive arc) | `GrantView` | R |
| `kg_schema_read` | resolved project graph schema (edge/fact/vocab) | `GrantView` | R |
| `kg_list_templates` | system + caller's user templates adopt được | per-call user id | R |

### 3b. Graph write (agent đề xuất fact/quan hệ) — vào inbox, human review
| Tool | Wraps | Gate | Class |
|---|---|---|---|
| `kg_propose_fact` | pending_facts inbox (draft, schema-validated) | `GrantEdit` | W (draft, reversible) |
| `kg_propose_edge` | propose relationship edge (validated theo `kg_edge_types`; temporal-required nếu temporal) → inbox | `GrantEdit` | W (draft) |
| `memory_remember` / `memory_forget` | (đã có) | per-call user | W |

> `kg_propose_edge` **không** ghi thẳng Neo4j — nó là draft trong inbox; áp vào graph qua write-path tập trung sau khi human duyệt (giống glossary `propose_new_entity`). Edge lệch schema → triage (§3e), không silent.

### 3c. Project ontology (agent định hình graph schema của project) — spec ontology lớp 2
| Tool | Wraps | Gate | Class |
|---|---|---|---|
| `kg_adopt_template` | adopt copy-down system/user template → project (M1 **adopt-gated** qua glossary node-kind check) | `GrantManage` | **C** (scaffold lớn) |
| `kg_schema_edit` (`verb: add\|deprecate`, `level: edge_type\|fact_type\|vocab_value`) | sửa project schema — **bump `schema_version`** | `GrantManage` | **C** (đổi shape graph cả project; M3) |
| `kg_sync_available` | diff project schema vs upstream template (tree-granular) | `GrantView` | R |
| `kg_sync_apply` | apply per-node keep_mine/take_theirs (**rule-only, không retro-recompute**, M3) | `GrantManage` | **C** (overwrite adopted rows) |

### 3d. Views / lenses (per-user) — spec ontology lớp 3
| Tool | Wraps | Gate | Class |
|---|---|---|---|
| `kg_view_read` | list views của caller | `GrantView` (owner per-user) | R |
| `kg_view_upsert` / `kg_view_delete` | CRUD view (edge_type_codes + node_kind_codes) | owner == caller | W (reversible) |

### 3e. Triage resolution (agent gợi ý, human chốt) — spec ontology §11
| Tool | Wraps | Gate | Class |
|---|---|---|---|
| `kg_triage_list` | queue (group theo `signature`) | `GrantView` | R |
| `kg_triage_resolve` (`action`) | KG-local actions (map / re-target / dismiss) | `GrantEdit` | W |
| `kg_triage_resolve` (schema-mutating: add-to-vocab/schema, widen) | đổi schema | `GrantManage` | **C** |
| `kg_triage_handoff_glossary` | promote→glossary kind / demote→attribute = **glossary write do user khởi xướng** (trả `needs_glossary` để FE deep-link; KHÔNG service-to-service write) | `GrantManage` | **C** (cross-service, M1) |

### 3f. System-tier admin (CMS-surface only — `/mcp/admin`, §4) — spec ontology tier System
| Tool | Wraps (admin HTTP) | Identity | Class |
|---|---|---|---|
| `kg_admin_template_read` | đọc system templates | admin RS256 (`admin:write`) | R |
| `kg_admin_propose_template` (`verb: create\|patch\|delete`) | system graph template write | admin RS256 | **C** |

**Tổng: ~18 tool logic** (ít wire-tool hơn nếu gộp verb/level args — H7).

---

## 4. Authority & identity model

Tái dùng **nguyên** mô hình glossary §4 (load-bearing), chỉ đổi book→project:

- **4a. Project + User tier — extend envelope hiện có (no new trust).** Agent hành động thay user đã đăng nhập. `X-Internal-Token` + `X-User-Id` (+ `X-Project-Id`). Project tool `checkGrant(project, user, View|Edit|Manage)`; user-tier tool (views/templates) enforce `owner == X-User-Id`. **Không đổi trust model** → phase Project/User low-risk.
- **4b. System/admin tier — carry RS256 admin authority (KHÔNG trust `X-User-Id`).** Tái dùng `adminjwt.Verify` + `admin:write` (cùng cái HTTP admin route dùng), forward qua envelope `X-Admin-Token`. Mọi System write là **class C** (propose confirm-token → human admin confirm ở CMS). LLM không bao giờ trực tiếp mutate System.
- **4c. Tách endpoint vật lý — `/mcp/admin` ≠ `/mcp` (INV-T6, security-critical).** Giống glossary §4c: knowledge có **2 MCP server** —
  - **`/mcp`** (đang có): gate `X-Internal-Token` + `X-User-Id`. CHỈ chứa Project + User tool. Tên/schema/internals admin **không bao giờ** xuất hiện ở catalog này.
  - **`/mcp/admin`** (MỚI): transport middleware verify RS256 `X-Admin-Token` **trước `tools/list`** → no token = 401, không enumerate được. CHỈ chứa admin System tool.
  - ai-gateway federate 2 upstream tách biệt; chỉ dial `/mcp/admin` cho CMS surface khi cầm admin token. (Gateway đã có 2-catalog pattern từ glossary epic — tái dùng.)

> 3 rào cho mọi System mutation: (1) không tới được `/mcp/admin` nếu thiếu admin token verified, (2) admin tool vắng mặt khỏi `/mcp`, (3) mọi System write vẫn human-confirm. Defense-in-depth, không phải một check.

---

## 5. Gating + confirm-token contract

| Class | Rule | Pattern |
|---|---|---|
| **R** | direct; bounded output (SO-3 caps, knowledge đã có SEARCH/TIMELINE caps); **kế thừa caller-scoped visibility của handler HTTP** (không raw Cypher — bypass K11.4 guard là lỗi) | trả data |
| **W** | low-impact, **reversible** (inbox draft / view delete / forget), grant/owner-gated, **additive** | execute + báo outcome thật (H6) |
| **C** | high-impact (adopt/schema-edit), destructive, set-replace, cross-service (triage handoff), **đổi graph shape**, **mọi** System write | mint `confirm_token` + preview (no write) → human confirm (frontend tool) → token-gated write |

**Confirm-token contract** = **đúng §5.1 + §13 của glossary** (single-use qua bảng `consumed_tokens`, expiring TTL, bind identity+scope, **re-validate tại confirm time**, action descriptor). Knowledge implement **machinery riêng** (Python) **theo cùng contract** — KHÔNG share code Go, nhưng cùng: domain-separated HMAC + `jti` ledger; descriptor enum đóng; preview tính từ state hiện tại lúc confirm render.

**Descriptor knowledge (mirror §13.1):** `kg_adopt` · `kg_schema_edit` · `kg_sync_apply` · `kg_triage_schema` · `kg_triage_handoff` (grant authority); `kg_system_create|patch|delete` (admin authority). Confirm endpoint branch authority theo descriptor (grant vs admin), re-validate (existence/FK/schema_version drift/optimistic-concurrency).

---

## 6. Architecture changes

1. **knowledge-service: 2 MCP server** — giữ `/mcp` (Project+User; `X-Internal-Token`+`X-User-Id`), thêm `/mcp/admin` (RS256 `X-Admin-Token` verify ở transport trước `tools/list`). Tool đăng ký tách hẳn, no shared catalog.
2. **ai-gateway:** thêm downstream `/mcp/admin` federate knowledge `/mcp/admin` only + forward `X-Admin-Token` (tái dùng pattern + envelope đã thêm cho glossary epic — nếu glossary epic chưa land, đây là dependency chung).
3. **chat-service:** AdminContext surface (đã thiết kế cho glossary) mở rộng để list knowledge admin tool; **skill prompt MỚI** `knowledge_skill.py` dạy workflow (memory vs graph; as-of-chapter; propose→review; triage; INV-6 injection-defense: tool result là DATA không phải lệnh). Per-surface curation: surface nào advertise tool memory/graph nào.
4. **Confirm machinery (Python)** — bảng `consumed_tokens` (knowledge DB), mint/confirm/preview endpoint `/v1/kg/actions/{confirm,preview}`, theo §13 contract.
5. **Surfacing (knowledge assistant proper)** — dock/panel mount knowledge tools (BookAssistantDock pattern hoặc knowledge-service standalone UI, project-scoped). Quyết định surface ở phase cross-cutting.
6. **Contracts** — MCP không OpenAPI, nhưng confirm/preview endpoint + graph-read/triage HTTP là contract-first (trùng `views.yaml`/`triage.yaml` của KG ontology build plan).

---

## 7. Invariants (carry glossary INV-T1..T6 → đổi book→project)

- **INV-T1 MCP-first** — mọi năng lực là MCP tool trên knowledge-service; no bespoke prompt endpoint.
- **INV-T2 admin = RS256, never `X-User-Id`** — System write phải verify RS256 `admin:write`.
- **INV-T3 System writes always human-confirmed** — propose confirm-token only.
- **INV-T4 surface curation = security boundary** — admin tool chỉ ở CMS surface.
- **INV-T5 tenancy preserved** — project grant-gated; user owner-scoped; system admin-gated. Tái khẳng định K11.4 (mọi Cypher bind `$user_id`).
- **INV-T6 admin MCP = endpoint vật lý tách (`/mcp/admin`), transport-gated RS256** — admin internals không bao giờ ở `/mcp` catalog.
- **INV-K1 (mới, knowledge-specific) — graph write đi qua write-path tập trung + schema validation** — không tool nào ghi Neo4j edge lệch schema; lệch → triage. Stamp `schema_version`. (D5 + §11 spec ontology.)
- **INV-K2 — identity không từ LLM; scope từ envelope** (SEC-1, design D3 đã có).

---

## 8. Phasing (mỗi phase ≈ L, riêng `/loom`; **map vào lane KG ontology build plan**)

| Phase | Scope | Risk | Map lane (build plan) |
|---|---|---|---|
| **KM0 — Legacy path retirement (do-first)** | XÓA `routers/internal_tools.py` (`/internal/tools/execute` + `/internal/tools/definitions`) + đăng ký trong `main.py`; xóa chat-service `knowledge_client.py::execute_tool()` (dead parity) + test legacy (`test_internal_tools.py`, `test_mcp_envelope_parity.py`); sửa stale docstring `definitions.py` (design D3). **Precondition:** grep-verify 0 runtime caller (đã verify; cũng check `docker-compose.yml`/healthcheck). | low | **L1 foundation** (cùng chủ file `main.py`) |
| **KM1 — Graph read tools** | `kg_graph_query` (view+as-of-chapter) + `kg_entity_edge_timeline` + `kg_schema_read` + `kg_list_templates` | low (envelope sẵn) | sau **LD** (read contract) |
| **KM2 — Graph propose-write** | `kg_propose_fact` + `kg_propose_edge` → inbox (schema-validated, temporal) | low–med | sau **LB/LC** |
| **KM3 — Project ontology + sync tools** | `kg_adopt_template` (C) + `kg_schema_edit` (C) + `kg_sync_*` | med (confirm machinery) | = **LF** (chi tiết hoá) |
| **KM4 — Views + triage tools** | `kg_view_*` + `kg_triage_*` (+ handoff C) | med | = **LF/LH** |
| **KM5 — Admin/System + CMS surface** | `/mcp/admin` server + admin propose (C) + `X-Admin-Token` + CMS surface | **high** | mới (đồng bộ glossary T4) |
| **KM6 — Cross-cutting** | confirm machinery (Python, §13); `knowledge_skill.py` prompt; per-surface curation; surfacing dock; live-smoke mỗi surface | med | L7 + FE (LE) |

Thứ tự: **KM0 (cleanup, làm cùng L1 foundation)** → KM1→KM2 (giá trị compounding, no authority risk) → KM3/KM4 (confirm machinery) → KM5 cuối. `/review-impl` bắt buộc ở KM5 (auth boundary). VERIFY: unit + cross-service live-smoke (gateway→knowledge MCP); KM0 verify = full suite xanh sau khi gỡ legacy (chứng minh không có caller ẩn).

---

## 9. Relationship to other epics (alignment — đọc kỹ)

- **KG ontology epic** ([spec](2026-06-20-knowledge-graph-customizable-ontology.md) + [build plan](../plans/2026-06-20-knowledge-graph-ontology-build.md)) = **lớp dữ liệu + HTTP** (graph schema tables, resolution, adopt/sync HTTP, views, triage queue, extraction động). **Spec này = lớp agent (MCP)** phủ lên trên. Build plan lane **LF "MCP graph-schema tools" = phase KM3/KM4 ở đây**; lane **LH triage** cung cấp HTTP cho `kg_triage_*`. → cập nhật LF/LH trong build plan trỏ về spec này.
- **Glossary MCP epic** ([spec](2026-06-20-glossary-assistant-tiered-tools.md)) = domain song song. **Tái dùng chung:** envelope `X-Admin-Token`, ai-gateway 2-catalog `/mcp` + `/mcp/admin`, chat-service AdminContext surface, confirm-token §13 contract. Nếu glossary epic land trước → knowledge thừa hưởng gateway/chat infra; nếu không, đó là dependency chung (flag ở PLAN).
- **Two-layer:** node identity = glossary (anchor); graph shape = knowledge. Tool knowledge **không** tạo/sửa node kind — chỉ consume + (qua triage handoff) **đề nghị user** sửa bên glossary.

---

## 10. Edge cases & hardening (mirror glossary §11, knowledge-specific)

**🔴 Must specify:**
1. **Confirm-token là capability, re-validate tại confirm** (đặc biệt **`schema_version` drift**): giữa propose và confirm, schema project có thể đã bị edit/sync → confirm phải re-check `schema_version` + re-validate (M3). Stale → 422 re-proposable.
2. **`kg_propose_edge` không ghi Neo4j trực tiếp** — luôn qua inbox/write-path tập trung (INV-K1); edge lệch schema → triage, không silent-drop, không silent-write.
3. **Triage handoff cross-service không phải KG→glossary write ngầm** — trả `needs_glossary{book_id,kinds}` cho FE deep-link; item `pending_glossary`; KG re-process khi kind xuất hiện (M1 nguyên tắc).
4. **Read tools kế thừa caller-scoped visibility** — `kg_graph_query`/`triage_list` gọi đúng path scoped (K11.4 `$user_id`), không raw Cypher → không leak project khác.
5. **CMS surface federate `/mcp/admin` ONLY** — test: session book/reader không nhận admin tool; CMS không nhận project/user tool.

**⚠️ Resolve at phase:**
6. **Admin-token lifecycle** (15m TTL mid-session) → re-exchange `/v1/admin/session` on 401 (như glossary).
7. **Optimistic concurrency** graph-schema edit → `base schema_version`, 409 on drift.
8. **as-of-chapter với chapter ordinal chưa biết** → tool nhận chapter ordinal/id; validate; bỏ trống = latest.
9. **`kg_propose_edge` temporal-required** → nếu edge type `temporal=true` mà LLM không cấp `valid_from(chương)` → tool reject sớm (mint-time), không tạo edge không-dấu-chương (cảnh báo VCTĐ §2a).

**▫ Ergonomic:**
10. **Code-based addressing** — tool nhận `edge_type_code`/`view_code`/`template_code`/`entity_name`, resolve ID server-side (tránh LLM transpose UUID).
11. **Catalog discipline** — gộp verb×level (schema_edit, triage_resolve, admin_propose) giữ catalog nhỏ (H7); per-surface curation chặt.
12. **Closure ambiguity (F1)** — `kg_propose_edge` trên edge `single_active` → preview cho biết "sẽ đóng instance đang mở"; `multi_active` → không đóng (human quyết trong triage nếu mơ hồ).

**Validated sound (như glossary):** 2-endpoint admin separation, human-confirm là backstop chống injection, 3-class gating.

---

## 11. Open decisions (chốt ở phase CLARIFY)
1. **memory_remember vs kg_propose_fact** — giữ 2 đường (fact rẻ write-immediate + fact/edge propose-inbox) hay hợp nhất về propose? *Lean: giữ 2 (memory rẻ, graph propose).*
2. **Surfacing knowledge assistant** — reuse BookAssistantDock (project↔book) hay knowledge-service standalone UI? *Lean: dock cho project có book; standalone cho no-book project.*
3. **Verb-collapsing** schema_edit / triage_resolve / admin_propose — confirm 1 tool × arg.
4. **Confirm machinery** — port glossary §13 sang Python mới, hay tách thành lib chung? *Lean: port riêng (khác ngôn ngữ), cùng contract + cùng bảng-schema `consumed_tokens`.*
5. **memory_remember fact_type** hiện là `decision/preference/milestone/negation` (chat-memory) — có nên đổi sang narrative fact-type của project schema (realm_change…) không? *Liên đới spec ontology Q3.*

## 12. Out of scope
- Đổi lớp dữ liệu KG (thuộc KG ontology epic; spec này chỉ thêm lớp agent).
- Glossary tools (domain riêng).
- Extraction pipeline (không agentic → exempt MCP-first; thuộc lane LB).
- Graph partition `graph_id` (deferred lớp 4).
