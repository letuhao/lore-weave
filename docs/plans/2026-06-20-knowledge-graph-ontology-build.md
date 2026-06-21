# KG Customizable Ontology — Build Plan (parallel-safe)

> **Trạng thái:** PLAN — chưa code. Thiết kế chi tiết + ranh giới file + DAG chạy song song.
> **Ngày:** 2026-06-20
> **Spec nguồn:** [`2026-06-20-knowledge-graph-customizable-ontology.md`](../specs/2026-06-20-knowledge-graph-customizable-ontology.md)
> **Branch:** implement trên branch riêng `feat/knowledge-graph-ontology` (KHÔNG trên branch glossary). Mục tiêu: chạy **song song nhiều lane** mà không đụng độ file với branch glossary / admin-CMS.
> **Quy mô:** XL, load-bearing (schema + tenancy + migration + extraction cross-service). /amaw hoặc /warp cho các lane migration.

---

## 0. Nguyên tắc parallel-safe (đọc trước)

1. **Contract-first, freeze trước khi fan-out.** Mọi API (knowledge ontology, glossary internal-ontology read) đông cứng ở **L0** dưới dạng OpenAPI. Lane build theo contract + **mock** cho tới composition point — không lane nào chờ code lane khác để bắt đầu.
2. **Một file = một lane.** Mỗi lane sở hữu tập file **rời nhau** (§5 matrix). File dùng chung (`models.py`, `migrate.py`, `neo4j_schema.py`, `server.go`, i18n/route registry) chỉ được sửa ở **lane foundation (L1)** hoặc **lane tích hợp cuối (L7)**, KHÔNG sửa ở lane song song.
3. **Code mới → file mới.** Logic mới đặt trong **module/file mới** thay vì chèn vào file lớn sẵn có → tránh xung đột line-number.
4. **Cross-branch choke point = glossary `server.go`.** Route internal-ontology của glossary (LG) làm **trên branch glossary** như một commit nhỏ biệt lập (1 handler file mới + 1 dòng đăng ký). KG side coi đây là **dependency ngoài (D1)**, build client + mock cho tới khi route về.
5. **Worktree cho lane mutate song song.** Lane đụng cùng repo-state (đặc biệt LB extraction) chạy trong **git worktree** riêng để không giẫm nhau.

---

## 1. Design-lock (S0) — chốt trước khi fan-out

3 must-answer của spec §8 + đề xuất default cho Q còn lại. **S0 = stop point con người duyệt cả khối này.**

| # | Quyết định | Chốt (đề xuất) |
|---|---|---|
| **M1 / G1** | Reconciliation node-kind glossary↔KG | **🔒 LOCKED S0 — adopt-gated PER-KIND STRENGTH**: mỗi expected kind mang `strength` (`kg_schema_node_kinds`, spec §3.2b). Adopt **BLOCK** nếu thiếu kind `required`; thiếu kind `optional` → warn + `unknown_node_kind` triage. Không cross-service write ngầm. Cần D1 (glossary internal-ontology read) để check. `xianxia-harem`: required = character/organization/location/concept/technique; optional = item/event/relationship. |
| **M2 / C4** | Seam partition | `graph_id` **trên EDGE** (node dùng chung). View = read-only lens. View≠partition (không continuum). |
| **M3 / B4** | Schema versioning | `schema_version` trên `kg_graph_schemas`, **stamp lên edge/fact** lúc write. Edit additive; rename/remove = deprecate-only. |
| Q1 | Đa-schema-active/project | **v1: một project-schema active** (merge lúc adopt). Đa-template → để lớp 4. |
| Q2 | Free-edge policy | **🔒 LOCKED S0: `allow_free_edges=true` mặc định** (giữ hành vi free-string hiện tại); siết theo `kg_edge_types` là opt-in per-schema. Tránh vỡ project cũ. |
| Q3 | Fact-type narrative | **🔒 LOCKED S0** — `xianxia-harem` seed 9 type: `realm_change, allegiance_shift, motivation_shift, death, breakthrough, battle_outcome, betrayal, bloodline_awakening, oath_or_vow`. `general` giữ bộ cũ. |
| Q4 | Grant-level schema-write trong project shared | **Manage-gate** (mirror glossary). View **per-user** (UNIQUE project+user+code). |
| Q5 | Drive vocab dùng chung | **v1: per-template** (`drive` trong `xianxia-harem`). Cấp system-shared để lớp sau (liên đới Q1). |

> Output S0: spec §8 cập nhật "LOCKED" + 2 contract YAML đông cứng (§4). Cho tới khi S0 pass, KHÔNG mở lane.

---

## 2. Milestone → Lane map

| MS (spec §7) | Lane | Loại | Phụ thuộc |
|---|---|---|---|
| K1 schema+models+seed | **L1 Foundation** | SYNC (trunk) | S0 |
| K2a glossary internal route | **LG** | ASYNC (branch glossary) | contract (L0) |
| K2b KG glossary client | trong **LA** | ASYNC | contract (L0) |
| K3 resolution + validation | **LA** | ASYNC | L1 |
| K4 extraction động | **LB** (worktree) | ASYNC (dài nhất) | L1 + LA + K2b |
| K5 adopt/sync/CRUD API | **LC** | ASYNC | L1 (+LA read) |
| K6 views + as-of-chapter read | **LD** | ASYNC | L1 |
| FE ontology UI | **LE** | ASYNC | contract → API thật ở C3 |
| MCP graph-schema tools | **LF** | ASYNC | contract → API thật ở C3 |
| K9 triage queue + resolution (spec §11) | **LH** | ASYNC | L1 → tích hợp K4(park)+K5(hand-off) ở C4 |
| K7 enforcement + seam | **L7 Integration** | SYNC (compose) | LA+LB+LC+LD+LG |
| K8 partition | — | DEFERRED | — |

---

## 3. Thiết kế chi tiết per lane (file mới + endpoint + logic)

### L1 — Foundation (SYNC, trunk; chỉ lane này sửa file DB dùng chung)
**Mục tiêu:** mọi bảng + seed sẵn sàng; additive, zero behavior change.
- **Sửa (file dùng chung — độc quyền L1):**
  - `app/db/migrate.py` — thêm bước migration tạo `kg_*` + gọi seed.
  - `app/db/neo4j_schema.py` — additive: property `graph_id`(edge, NULL), `schema_version`(edge/fact), index liên quan.
  - `app/main.py` — (KM0) **gỡ đăng ký router legacy** `internal_tools`; (sau) là chỗ pre-register router mới (xem fix router-choke bên dưới).
- **File mới:**
  - `app/db/ontology_models.py` — định nghĩa `kg_graph_schemas`, `kg_edge_types`, `kg_fact_types`, `kg_schema_node_kinds` (M1 strength, §3.2b), `kg_vocab_sets`, `kg_vocab_values`, `kg_views` (DDL §3 spec; scope-keyed UNIQUE). Import 1 dòng vào `models.py`.
  - `app/db/seed_graph_schemas.py` — seed system `general` (= ontology hardcode hiện tại) + `xianxia-harem` (VCTĐ §4 edges + §3.4 drives).
  - `app/db/repositories/graph_schemas.py` — **read + resolution query** (dùng bởi LA; read-only cho các lane khác).
- **KM0 — Legacy MCP path retirement (do-first, spec MCP §8):** XÓA `app/routers/internal_tools.py` (`/internal/tools/execute` + `/internal/tools/definitions`) + đăng ký trong `main.py`; XÓA chat-service `app/client/knowledge_client.py::execute_tool()` (dead parity) + test legacy (`test_internal_tools.py`, `test_mcp_envelope_parity.py`); sửa stale docstring `tools/definitions.py`. **Precondition:** grep-verify 0 runtime caller (done) + check `infra/docker-compose.yml`/healthcheck. **Tại sao ở L1:** đụng `main.py` (cùng file router-registration) → gộp vào trunk, không để lane song song đụng.
- **Router-registration choke point (fix):** `main.py` là file dùng chung mọi router lane (LC/LD/LH) phải wire. **L1 pre-register sẵn router stub rỗng** cho `ontology`/`graph_views`/`triage` → các lane chỉ điền handler vào file router riêng, KHÔNG đụng `main.py`.
- **VERIFY:** ephemeral DB test bảng + seed; **full suite green sau khi gỡ legacy** (chứng minh không caller ẩn); project cũ default `general` (chưa ai đọc → no behavior change).
- **Composition C1:** L1 merge vào branch → mở fan-out.

### LA — Resolution + validation core (ASYNC)
- **File mới (độc quyền LA):**
  - `app/ontology/__init__.py`
  - `app/ontology/resolver.py` — resolve `system→user→project` theo `code`, cache TTL ngắn. Trả "resolved schema" (edge types, fact types, vocab, node-kind expectation).
  - `app/ontology/validation.py` — validate edge/fact/node-kind theo resolved schema. **Fail-soft (K3): log + triage**, chưa reject (reject bật ở L7).
  - `app/clients/glossary_ontology_client.py` — **K2b**: gọi glossary internal-ontology read (D1); 2 nguồn node-kind — book ontology nếu có `book_id`, else **user glossary standards** (project no-book, spec §3.5/M1-refine); mock-able tới khi LG về.
- **Dùng:** `repositories/graph_schemas.py` (L1, read-only).
- **VERIFY:** unit resolver (shadow precedence), validation fail-soft, client với fake glossary.
- **Composition C2:** resolver API ổn → LB tích hợp, LC dùng cho gate.

### LB — Extraction động (ASYNC, **worktree**, lane dài nhất — ⚠ MULTI-SERVICE RISK)
> **⚠ SDK KHÔNG isolated (verify 2026-06-20):** `sdks/python/loreweave_extraction` được consume bởi **3 service** — knowledge-service, **worker-ai** (`app/decoupled_extract.py`, `runner.py`, `llm_client.py`, `clients.py`) và **translation-service**. → LB **KHÔNG low-risk**; blast-radius cross-service. Bất kỳ branch nào động vào worker-ai/SDK = xung đột tiềm tàng.
- **Sửa (độc quyền LB — không lane nào khác đụng extraction):**
  - `sdks/python/loreweave_extraction/extractors/{entity,event,relation,fact}.py` — bỏ `Literal` cứng → validation động theo schema truyền vào.
  - `sdks/python/loreweave_extraction/prompts/__init__.py` — builder dựng prompt **từ resolved schema** thay vì `.md` tĩnh.
  - `sdks/python/loreweave_extraction/prompts/*.md` — templatize (chừa slot cho kind/edge/fact/vocab).
  - `sdks/python/loreweave_extraction/resolve_config.py` — mở rộng (đã có priority user>book>system).
  - `app/extraction/pass2_orchestrator.py`, `app/extraction/pass2_writer.py` — truyền resolved schema vào pipeline; **projection schema-cho-extraction** (§10-B1 token budget).
- **Dùng:** `ontology/resolver.py` (LA, C2) + `glossary_ontology_client.py`.
- **🔒 BACKWARD-COMPAT RULE (bắt buộc):** chữ ký SDK mới phải **default về hành vi tĩnh hôm nay khi KHÔNG được truyền schema** (`schema=None` → prompt/validation = bản `.md`+`Literal` cũ). worker-ai + translation-service gọi SDK **không đổi 1 dòng** và ra output y hệt. Thay đổi của LB chỉ "kích hoạt" khi knowledge truyền resolved schema vào.
- **Golden-set eval (sub-task LB-G, có chủ + sizing — KHÔNG hand-wave):**
  1. Chọn corpus cố định (vài chương đại diện, ≥1 VCTĐ + ≥1 bộ khác).
  2. Capture **baseline** output extraction TRƯỚC khi đổi, **cho CẢ knowledge-service VÀ worker-ai path** (vì cùng SDK).
  3. Sau đổi: chạy lại `schema=None` → **byte/však-diff = 0 so baseline** (backward-compat proof cho worker-ai/translation).
  4. Chạy `schema=xianxia-harem` → assert edge/drive đúng schema.
- **VERIFY:** golden-set #3 (parity `general`/`schema=None` cả 2 path) + #4 (xianxia-harem) ; **live-smoke worker-ai extraction không regress** (không chỉ knowledge); live-smoke 1 chương knowledge.
- **Stop point S2-LB:** POST-REVIEW (dynamic extraction là shippable milestone; review phải xác nhận worker-ai/translation không đổi hành vi).

### LC — Adopt / Sync / CRUD API (ASYNC)
- **File mới (độc quyền LC):**
  - `app/routers/public/ontology.py` — endpoint (theo contract §4):
    - `GET /v1/kg/graph-schemas?scope=` (list/merged)
    - `POST /v1/kg/projects/{project_id}/adopt` (copy-down; **M1 adopt-gated** check qua glossary client)
    - `GET /v1/kg/projects/{project_id}/sync/available`, `POST .../sync/apply` (tree-granular, §10-A3)
    - CRUD `/v1/kg/graph-schemas/...` (user/project tier; **Manage-gate**, Q4) + recycle bin (deprecate)
    - `POST /v1/kg/system/graph-schemas` (admin-only sau `requireAdmin` placeholder)
  - `app/db/repositories/ontology_mutations.py` — adopt deep-copy, sync diff/apply, CRUD writes, `content_hash`/`source_hash`.
- **Dùng:** `resolver.py` (LA, read), `graph_schemas.py` (L1, read).
- **VERIFY:** adopt copy-down + idempotent; sync diff/apply tree-level; tenancy deny-test (user B không đụng schema user A — bài học [[e0-grant-mapping-test-pattern]]); adopt-gated per-kind strength: **422 khi thiếu kind `required`**, **proceed+warn khi chỉ thiếu kind `optional`** (M1).
- **Stop point S2-LC:** POST-REVIEW (adopt/sync usable).
- **Composition C3:** API thật → LE/LF bỏ mock.

### LD — Views + as-of-chapter read (ASYNC)
- **File mới (độc quyền LD):**
  - `app/routers/public/graph_views.py` — CRUD `/v1/kg/projects/{project_id}/views` (per-user, Q4) + **graph read** `GET /v1/kg/projects/{id}/graph?view=&as_of_chapter=` + `GET /v1/kg/entities/{id}/edges/{edge_type}/timeline` (spec §3.6).
  - `app/db/repositories/graph_views.py`.
  - `app/ontology/view_filter.py` — build filter query-scope theo view (READ-only; **không** scope extraction, §10-C3) + **temporal as-of**: `valid_from<=N AND (valid_to IS NULL OR valid_to>N)`.
- **VERIFY:** view CRUD per-user tenancy; query scoped đúng edge/kind; as-of-chapter resolve đúng (đóng/mở instance); view trỏ deprecated type bị flag (§10-A4).

### LH — Triage queue + resolution (ASYNC, spec §11)
- **File mới (độc quyền LH):**
  - `app/routers/public/triage.py` — `GET /v1/kg/projects/{id}/triage`, `POST .../triage/{signature}/resolve`, `POST .../triage/{triage_id}/dismiss`.
  - `app/db/repositories/triage.py` — park (gọi từ LB extraction fail-soft), group theo `signature`, batch re-apply, status `pending_glossary` cho hand-off.
  - `app/ontology/triage_apply.py` — re-process element parked → ghi edge/fact hợp-schema **qua write path tập trung** (D5).
- **Tích hợp ở C4:** LB park vào triage (gọi `triage.repo`); LC glossary client cho hand-off promote-to-kind/demote-to-attr (`needs_glossary` → FE deep-link).
- **VERIFY:** park đúng 5 `item_type`; batch re-apply theo signature; cross-service hand-off (mock glossary) → `pending_glossary` → re-process; tenancy deny-test ([[e0-grant-mapping-test-pattern]]).

### LE — Frontend ontology UI (ASYNC, theo contract)
- **File mới dưới `frontend/src/features/knowledge/` (độc quyền LE):**
  - `api/ontology.ts` (client riêng, KHÔNG đụng `api.ts` dùng chung)
  - `hooks/useGraphSchema.ts`, `hooks/useOntologyAdopt.ts`, `hooks/useGraphViews.ts`, `hooks/useOntologySync.ts`
  - `components/ontology/*` (Adopt picker, Schema manage, Sync diff, View builder) — theo MVC rule (<100 LOC/component).
- **File dùng chung (CHỈ ở commit tích hợp cuối, append-only, coordinate):** i18n namespace `kgOntology` ×4 locale, app route, sidebar entry.
- **VERIFY:** vitest hooks/components; build theo mock tới C3 rồi nối API thật.

### LF — MCP tool surface (ASYNC, theo contract)
> **Spec riêng:** [`2026-06-20-knowledge-assistant-mcp-tools.md`](../specs/2026-06-20-knowledge-assistant-mcp-tools.md) — toàn bộ ~18 tool (graph read/propose/ontology/views/triage/admin), tiers R/W/C, `/mcp/admin` + RS256, confirm-token. LF = phase KM1–KM4 của spec đó; KM5 (admin `/mcp/admin`) + KM6 (skill prompt, confirm machinery) là phase riêng đồng bộ glossary T4/T5.
- **File mới (độc quyền LF):**
  - `app/tools/graph_schema_tools.py` — định nghĩa + handler tool (graph_query/adopt/schema_edit/views/triage…), import 1 dòng vào `tools/definitions.py` + `executor.py` (dòng đăng ký = commit tích hợp cuối).
  - (KM5) `app/mcp/admin_server.py` + transport RS256 gate; (KM6) `app/ontology/confirm.py` (consumed_tokens + mint/confirm/preview, port glossary §13).
- **MCP-first:** mọi tool agentic qua ai-gateway (CLAUDE.md). Extraction pipeline (không agentic) exempt.
- **VERIFY:** tool schema valid; executor dispatch; ownership per-tool; confirm-token single-use/re-validate; CMS-surface curation test (admin tool vắng `/mcp`).

### LG — Glossary internal-ontology read (ASYNC, **branch glossary**, EXTERNAL)
- **File mới:** `services/glossary-service/internal/api/internal_ontology_read.go` — `GET /internal/books/{book_id}/ontology` (read-only, network-isolated, trả node-kinds của book).
- **Sửa choke point (commit nhỏ cuối, biệt lập):** `server.go` +1 dòng đăng ký trong block `/internal` (dòng ~118-164).
- **Contract:** thêm path vào `contracts/api/glossary-service/`.
- **Coordinate:** owner branch glossary làm; KG dùng mock tới khi merge. **Đây là điểm đồng bộ cross-branch duy nhất.**

### L7 — Integration + hard enforcement (SYNC, composition cuối)
- **Sửa (trunk, sau khi mọi lane về):**
  - `app/db/neo4j_repos/relations.py` (+`facts.py`) — bật **validate theo schema** + **cardinality closure** (single_active tự đóng) + **stamp `schema_version`** + temporal-required; **drop-and-triage per-edge** (§10-B2).
  - `app/ontology/validation.py` — lật fail-soft → hard.
  - Bật seam `graph_id` (edge, vẫn NULL/default).
- **File mới:** `infra/kg-ontology-live-smoke.ps1` — cross-service: adopt (gated qua glossary) → extract 1 chương động → edge/drive đúng schema + temporal stamp → view query.
- **VERIFY:** full suite + **live-smoke ≥2 service** (knowledge+glossary) — token bắt buộc (CLAUDE.md VERIFY).
- **Stop point S3:** POST-REVIEW cuối + live-smoke evidence.

---

## 4. Contracts đông cứng ở L0 (điều kiện fan-out)

| Contract | File | Dùng bởi |
|---|---|---|
| KG ontology API | `contracts/api/knowledge-service/ontology.yaml` (dir MỚI) | LC, LE, LF |
| KG views + graph read (as-of-chapter) | `contracts/api/knowledge-service/views.yaml` | LD, LE |
| KG triage API | `contracts/api/knowledge-service/triage.yaml` | LH, LE |
| Glossary internal-ontology read (book + user standards) | thêm path vào `contracts/api/glossary-service/` | LA(client), LG |

> Freeze = không đổi shape sau khi mở lane (đổi → quay lại S0). Đây là cái cho phép LE/LF/LC/LD/LG chạy song song với mock.

---

## 5. File-boundary matrix (chứng minh rời nhau)

| Lane | File/dir SỞ HỮU (ghi) | Đọc (không ghi) | Cross-branch? |
|---|---|---|---|
| **L1** | `db/migrate.py`, `db/neo4j_schema.py`, `app/main.py` (router register/unregister), `db/ontology_models.py`*, `db/seed_graph_schemas.py`*, `db/repositories/graph_schemas.py`*, +1 dòng `models.py`; **KM0:** xóa `routers/internal_tools.py` + chat-service `knowledge_client.py::execute_tool()` + legacy tests + `definitions.py` docstring | — | KM0 đụng chat-service (cùng trunk, do-first) |
| **LA** | `app/ontology/{resolver,validation,__init__}.py`*, `app/clients/glossary_ontology_client.py`* | `repositories/graph_schemas.py` | no |
| **LB** | `sdks/.../extractors/*`, `sdks/.../prompts/*`, `sdks/.../resolve_config.py`, `app/extraction/pass2_{orchestrator,writer}.py` | `ontology/resolver.py`, glossary client | **YES — SDK chung worker-ai + translation; bắt buộc backward-compat (schema=None→no-op)** |
| **LC** | `routers/public/ontology.py`*, `db/repositories/ontology_mutations.py`* | resolver, graph_schemas | no |
| **LD** | `routers/public/graph_views.py`*, `db/repositories/graph_views.py`*, `app/ontology/view_filter.py`* | resolver | no |
| **LE** | `features/knowledge/{api/ontology.ts,hooks/use*,components/ontology/*}`* | contract | no |
| **LF** | `app/tools/graph_schema_tools.py`* | contract | no |
| **LH** | `routers/public/triage.py`*, `db/repositories/triage.py`*, `app/ontology/triage_apply.py`* | resolver, validation, glossary client | no |
| **LG** | `glossary/internal/api/internal_ontology_read.go`*, +1 dòng `server.go` | — | **YES (branch glossary)** |
| **L7** | `neo4j_repos/relations.py`, `neo4j_repos/facts.py`, `ontology/validation.py` (flip), `infra/kg-ontology-live-smoke.ps1`* | tất cả | no |
| **integration commit** | i18n registry, app route, sidebar, `tools/definitions.py`+`executor.py` (dòng đăng ký) | — | coordinate (append-only) |

`*` = file mới. **Quy tắc:** không lane song song nào ghi cùng một file. `relations.py`/`facts.py` ghi ở L1 (additive props) rồi L7 (enforcement) — **tuần tự cùng trunk**, không song song.

---

## 6. DAG chạy song song — sync/async + stop/composition

```
        ┌─────────────── S0 (STOP: human design-lock + freeze contracts) ───────────────┐
        │                                                                                 │
        ▼ SYNC                                                                            
   ┌─ L1 Foundation (trunk) ─┐                                                            
   │  schema+models+seed     │── C1 (compose: L1 merged) ─────────────────────────────┐  
   └─────────────────────────┘                                                         │  
        │                                                                              ▼  
        │  ── S1 (STOP: human review foundation) ──                          FAN-OUT (ASYNC, song song)
        │                                                                              
        ├──► LA resolution+validation ──┐                                              
        │                               │── C2 (compose: resolver ready) ──► LB extraction (worktree, dài)
        ├──► LC adopt/sync/CRUD ────────┤                                   │  └─ S2-LB (STOP: POST-REVIEW)
        │        └─ S2-LC (STOP: POST-REVIEW)                               │
        ├──► LD views + as-of-chapter ──┤── C3 (compose: API thật) ──► LE FE ─┐
        │                               │                            └► LF MCP ┤
        ├──► LH triage queue ───────────┤── C4 (compose: LB park + LC hand-off) ┤
        └──► LG glossary route (branch glossary, EXTERNAL) ─────────────────────┘
                                                                              │
                                          ┌───────────────────────────────────┘
                                          ▼ SYNC
                                   ┌─ L7 Integration ─┐
                                   │ enforcement+seam │── live-smoke ≥2 svc
                                   │ +compose all     │
                                   └──────────────────┘
                                          │
                                   ── S3 (STOP: final POST-REVIEW + live-smoke) ──
```

**Stop points (con người):** S0 design-lock · S1 foundation · S2-LC + S2-LB milestone POST-REVIEW · S3 final.
**Composition points (merge/reconcile):** C0 contracts frozen · C1 foundation trunk · C2 resolver→LB/LC · C3 API thật→LE/LF · C4 LB-park+LC-handoff→LH triage · (L7) all→enforcement.

**Song song thực tế:**
- Sau C1: **LA, LC, LD, LE, LF, LG, LH chạy đồng thời** (7 lane). LE/LF dùng mock tới C3; LH dựng queue/router rồi tích hợp park+hand-off ở C4.
- LB bắt đầu plumbing SDK ngay sau C1, **tích hợp resolver ở C2** (không chờ LA xong hẳn để khởi động).
- LG hoàn toàn lệch nhịp (branch khác) — chỉ cần về trước L7.

---

## 7. Cross-branch conflict protocol

| Branch | Đụng gì | Tránh đụng KG bằng |
|---|---|---|
| **glossary refactor** | `services/glossary-service/*`, `frontend/features/glossary/*`, `contracts/api/glossary-service/*` | KG chỉ chạm glossary qua **LG** (1 handler mới + 1 dòng `server.go`) — làm trên branch glossary, biệt lập. KG dùng `frontend/features/knowledge/*` (rời glossary). |
| **admin-CMS** | (đang dev) admin surface | KG admin schema-write tạm sau `requireAdmin` placeholder; không build admin-identity ở epic này. |
| **shared FE files** | i18n registry, app route, sidebar | KG dùng **namespace riêng `kgOntology`** + route riêng; chèn ở **commit tích hợp cuối**, append-only. |
| **extraction SDK (worker-ai/translation)** | `sdks/python/loreweave_extraction/*` consume bởi worker-ai + translation-service | **LB backward-compat rule** (schema=None → hành vi cũ) = worker-ai/translation **không cần đổi 1 dòng**; golden-set baseline cover cả 2 path. **Coordinate timing nếu branch khác đang sửa worker-ai/SDK** — chạy LB trong worktree, merge SDK sớm + báo các consumer. |

---

## 8. Thứ tự khuyến nghị (nếu 1 người / ít agent)
S0 → L1 → (LA ∥ LC ∥ LD) → C2 → LB → (LE ∥ LF nối API) → LG về → L7 → S3.
**Nếu /warp nhiều agent:** L1 solo; rồi 6 lane worktree song song; LB worktree riêng vì dài + đụng SDK.

## 9. Việc CHƯA làm (deferred, không trong epic)
- K8 graph_id partition thật + promote view→partition.
- Đa-template-active/project (Q1 lớp 4).
- Admin-identity epic (system schema-write hiện sau placeholder).
- Shared system-level `drive` vocab (Q5).

---

## 10. Status log (branch `feat/knowledge-graph-ontology`)

> KG-specific session record (the shared `SESSION_HANDOFF.md` is intentionally
> NOT touched on this branch — cross-branch discipline §0/§7).

**2026-06-20 — S0 + C0 + KM0 + L1 DONE.**
- **S0 design-lock** committed (`273801a1`): M1 revised to per-kind strength
  (`kg_schema_node_kinds`), M2/M3/Q1/Q2/Q3/Q4/Q5 locked. Human-signed-off.
- **C0 contracts frozen** under `contracts/api/knowledge-service/`:
  `ontology.yaml` (12 paths) · `views.yaml` (4) · `triage.yaml` (3) +
  `_deps/glossary-ontology-read.yaml` (KG-side mock; LG implements on glossary
  branch). Sync tree-diff + triage signature shapes spiked into the contracts.
- **KM0 (legacy retirement)**: deleted `routers/internal_tools.py` +
  `test_internal_tools.py`, removed `main.py` import+register, fixed
  `definitions.py` docstring + the dual-run comment. **Correction vs spec:**
  chat-service `execute_tool()` never existed (only live `mcp_execute_tool`);
  `test_mcp_envelope_parity.py` is a LIVE MCP test → KEPT (spec's delete-list
  was pre-verification). KM0 scope = knowledge-service only.
- **L1 Foundation (trunk)**: 8 `kg_*` tables in `migrate.py` (scope-keyed
  UNIQUE NULLS NOT DISTINCT); `ontology_models.py` + 1-line `models.py` import
  (module import to dodge the `FactType` Literal collision); additive Neo4j
  `RELATES_TO` seam indexes (`graph_id`, `schema_version`); `seed_graph_schemas.py`
  (idempotent hash-gated seed of `general` + `xianxia-harem`) wired into lifespan
  (module-level import for test patchability); `repositories/graph_schemas.py`
  (tier-aware read + resolution); 3 empty public router stubs registered.
- **VERIFY**: unit suite **2634 passed** (incl 3 lifespan tests updated for the
  new seed step + 10 new KG seed-content tests proving the S0 locks); KG
  integration DB tests written (6, skip without `TEST_KNOWLEDGE_DB_URL` — live
  infra unavailable at dev time); provider-gate clean; single-service change
  (no cross-service live-smoke needed).

**2026-06-20 — /review-impl on L1 (HIGH fixed, live-PG verified).**
- **HIGH (fixed):** concurrent multi-replica cold start raced the seed →
  `UniqueViolationError` on `idx_kg_graph_schemas_scope_code` → crashed startup.
  Reproduced with a gather() race test, then fixed: existence-check moved inside
  the txn behind a per-template `pg_advisory_xact_lock(_SEED_LOCK_NS, hashtext(code))`.
- **Live-PG VERIFY (D-KG-L1-DB-SMOKE → DONE):** ran the 7 KG integration tests
  against the running stack's PG18 (`loreweave_knowledge_test`, host :5555) — DDL +
  seed + repo SQL all green (was skip-only at first commit). This closed the
  "SQL never executed" coverage gap.
- **MED (documented, for LC/LD):** `resolve_for_project` / `list_visible(project_id)`
  load by caller-supplied `project_id` WITHOUT a grant check — the router MUST
  grant-gate before calling (contract noted in the repo docstring; add a deny-test
  in LC/LD per [[worker-loaded-id-needs-parent-scoping]]). Added a deterministic
  resolution tiebreaker (`ORDER BY updated_at DESC, schema_id DESC`).
- **LOW (deferred):** stale comment in chat-service `knowledge_client.py:172`
  ("GET /internal/tools/definitions") — non-breaking (live path is MCP list-tools);
  track as `D-KM0-CHAT-STALE-COMMENT`, fix when chat-service is next touched.

**2026-06-20 — C1 fan-out WAVE 1 DONE (LA ∥ LD ∥ LH).** Three independent
backend lanes built as parallel worktree agents off `ae76ece7`, merged
disjoint (zero conflicts), composed + verified:
- **LA** (`app/ontology/resolver.py` + `validation.py` + `app/clients/glossary_ontology_client.py`):
  TTL-cached resolver (system→user→project; node-kind source = book ontology
  else user glossary-standards, glossary client injectable + faked till LG);
  pure fail-soft validation (never raises) emitting the 4 §3.7 triage classes
  by signature + a non-triage `validation_fact_type` diagnostic. 23 unit + 3 int.
- **LD** (`graph_views.py` router + `repositories/graph_views.py` + `ontology/view_filter.py`):
  per-user views CRUD (owner-scoped), temporal as-of-chapter graph read +
  edge timeline (View-gated, K11.4 `$user_id`-bound Cypher). 38 unit + 6 int.
- **LH** (`triage.py` router + `repositories/triage.py` + `ontology/triage_apply.py`):
  triage queue grouped by signature, batch resolve, dismiss, glossary hand-off
  (M1: pending_glossary + needs_glossary, never a KG→glossary write); dynamic
  Edit/Manage grant-gating. 18 unit + 9 int.
- **Compose VERIFY**: 25 KG live-PG integration + **2713 unit** green (app builds
  with all 3 routers); provider-gate clean. **review-impl**: grant-gating
  fail-closed (resolve-to-owner; non-grantee→404, under-tier→403) + validation
  fail-soft verified by me.
- **New deferred rows** (from the lanes, to clear in later waves):
  `D-KG-LD-NEO4J-SMOKE` (live graph-read smoke — TEST_NEO4J_URI unset; faked
  driver covers wiring) · `D-KG-LD-GRANTEE-TIMELINE` (grantee cross-owner entity
  timeline — no Neo4j cross-owner read path today) · `D-KG-LH-NEO4J-REAPPLY`
  (triage re-apply Neo4j write — seam, integrates C4/L7 w/ LB) ·
  `D-KG-LH-LC-SCHEMA-WRITE` (triage schema-mutating write belongs to LC's
  ontology_mutations).

**2026-06-20 — C1 fan-out WAVE 2 DONE (LC ∥ LB ∥ LE).** Three more disjoint
lanes built as parallel worktree agents, merged clean, composed + verified:
- **LC** (`routers/public/ontology.py` + `repositories/ontology_mutations.py`):
  adopt copy-down (replace-on-adopt → keeps one-active invariant), M1 adopt-gate
  (422 needs_glossary on missing `required` kind via the glossary client; fail-OPEN
  when glossary unavailable → don't false-block, runtime parks to triage),
  tree-granular sync diff/apply (rule-only forward, 409 on base_source_hash drift),
  per-tier child CRUD (additive + deprecate-only), Manage-gated. 7 unit + 16 int.
- **LB** (extraction SDK + `app/extraction/pass2_*`): dynamic prompt/validation
  from a resolved-schema projection; **backward-compat PROVEN byte-identical** for
  `schema=None` (4 SHA-256 prompt snapshots match pre-change) via APPEND (not a
  .md slot, which would break worker-ai's strict loader); worker-ai (0 schema=
  sites) + translation (own pipeline) verified unaffected; §10-B1 token soft-cap.
  28 dynamic + 305 SDK pass (4 fails PRE-EXISTING, confirmed at base) + 3 writer.
- **LE** (`frontend/src/features/knowledge/*`): MVC api/types/hooks/components for
  adopt/schema-edit/sync/views; `kgOntology` i18n ×4 locales (unregistered);
  INTEGRATION.md lists C3 wiring. 28 vitest + 667 knowledge suite green; tsc 0.
- **Compose VERIFY**: 41 KG live-PG integration + **2723 knowledge unit** + SDK 305
  green; provider-gate clean. review-impl: LC tenancy fail-closed (Manage-gate);
  glossary fail-open is a deliberate additive tradeoff.
- **New deferred rows:** `D-KG-LC-REVADOPT-LOSS` (re-adopt replaces → drops a user's
  prior schema customizations; warn in UI later) · `D-KG-LC-ROUTE-LIVE-TEST` (LC
  route handlers unit-tested with a fake repo — asyncpg/TestClient loop conflict;
  repo live-tested separately; add live HTTP route test) · `D-KG-LB-CACHE-SCHEMA-KEY`
  (extraction cache task_id omits schema — safe under per-book/project, revisit if
  cross-project text sharing appears) · `D-LB-LIVE-SMOKE` · `D-KG-LE-BROWSER-SMOKE`.

**2026-06-20 — L7 enforcement MECHANISM done + live-smoked (Neo4j + PG).**
- **Stamp (M2/M3):** `create_relation` now stamps `schema_version` + `graph_id`
  (NULL seam) on the edge; `schema=None`/legacy → NULL (no change). Added a clean
  `schema_version` field to the SDK `ExtractionSchema` projection; the writer passes
  `schema.schema_version`. **Live-Neo4j verified** (stamp persists; legacy NULL).
- **Drop→triage (C4 compose):** `write_pass2_extraction` now PARKS an off-schema
  edge (the closed-edge guard's drop) to `kg_triage_items` (unknown_edge_type,
  `edge:<predicate>`) via an optional `triage_repo` (TriageParkProtocol) — fail-soft
  (a park error never breaks the batch); `triage_repo=None` → today's drop+log.
- **L1 Neo4j seam live-applied:** the additive `relates_to_schema_version` /
  `relates_to_graph_id` indexes apply cleanly on the running Neo4j (schema test 4/4).
- **VERIFY:** 2725 unit (incl 2 new L7 writer tests: stamp pass-through + drop→park)
  + live-Neo4j stamp test + 471 extraction/writer green; provider-gate clean.
- **Deferred `D-KG-L7-ACTIVATE`:** the enforcement is built + tested but DORMANT in
  production — nothing constructs the resolver→`ExtractionSchema` projection in the
  live extraction entry point yet, and `triage_repo` isn't threaded through the
  orchestrator's write calls. Activating per-project (resolve schema at job start →
  pass `schema=` + `triage_repo=` into `write_pass2_extraction`) + a full-pipeline
  cross-service live-smoke is the remaining switch. `single_active` cardinality
  auto-close stays dormant (all seeded edges multi_active) → `D-KG-L7-CARDINALITY`.

**2026-06-20 — LF (MCP tool surface) DONE + merged + reviewed.**
- 12 tools registered (`app/tools/graph_schema_tools.py` + appended to
  `definitions.py`/`executor.py`/`mcp/server.py`): **R** = kg_graph_query,
  kg_entity_edge_timeline, kg_schema_read, kg_list_templates, kg_sync_available,
  kg_view_read, kg_triage_list; **W (reversible)** = kg_propose_fact,
  kg_propose_edge, kg_view_upsert, kg_view_delete, kg_triage_resolve (KG-local).
- **Class-C correctly DEFERRED to KM6** (adopt/schema_edit/sync_apply/
  schema-mutating-triage/handoff/admin) — NOT registered; a unit test asserts
  zero leak into the catalog (an LLM cannot mutate schema/adopt without the
  confirm-token backstop). `D-KG-LF-KM6`.
- **review-impl (security surface):** INV-K1 holds — `graph_schema_tools.py`
  imports only `run_read`/`neo4j_session`, so `kg_propose_edge` parks (never
  writes Neo4j); every project tool grant-gates via `_resolve_project_owner`
  (resolve-to-owner); identity from envelope + `extra="forbid"`.
- **MED `D-KG-LF-PROPOSE-EDGE-INBOX`:** on-schema (valid) proposed edges are
  parked into `kg_triage_items` as `edge_cardinality_conflict` (no dedicated
  edge-draft inbox exists) — overloads the triage taxonomy. Human-gated, no
  integrity risk; fix = a proper edge-propose status/inbox distinct from the
  extraction-mismatch item_types.
- **Compose VERIFY (LF + L7 together):** 2781 knowledge unit + 95 MCP catalog
  (no class-C leak, no scope leak, inputSchema mirror) + 4 live-PG MCP green;
  provider-gate clean.

**2026-06-20 — /review-impl (4 cold reviewers) + fixes.** Ran 4 independent
adversarial reviewers (tenancy/IDOR · adopt-sync correctness · LB-backcompat/L7 ·
MCP/LF). MCP security surface + LB backward-compat **confirmed solid** (dormancy
true, INV-K1 holds, class-C no-leak with a failing-if-added test). Fixed:
- **HIGH-1 (cross-tenant leak):** `adopt` fetched the source by id with NO scope
  check → a user could deep-copy/read another tenant's private user-tier template
  by UUID. Added `_assert_source_adoptable` (system | own-user | own-project).
- **HIGH-2 (data loss):** sync taking a newly-`added` upstream vocab_set inserted
  an EMPTY closed set (values dropped). `_take_vocab_set` now copies the values.
- **HIGH-3 (A4 violation):** `removed_upstream` vocab_value hard-DELETEd. Added
  `kg_vocab_values.deprecated_at` + deprecate-not-delete + exclude deprecated from
  reads (resolver + `_tree_surface`).
- **MED-4 + deeper bug:** added a per-project advisory lock to adopt/sync_apply
  (TOCTOU) AND made `idx_kg_graph_schemas_*_scope_code` **partial (WHERE
  deprecated_at IS NULL)** — replace-on-adopt's deprecate+reinsert-same-code (incl
  the M1 fill-glossary-then-re-adopt flow) was hitting a unique violation; now
  uniqueness is among ACTIVE rows only.
- **MED-5:** corrected the false `_tree_surface` "mirrors the seed hash" docstring
  (the two hash families intentionally differ; never cross).
- **MED-6:** hardened triage-park `user_id` coercion — a non-UUID id is logged
  distinctly + skips the park (was swallowed by the best-effort `except` → silent loss).
- **VERIFY:** 49 KG live-PG integration (incl 4 new HIGH/MED tests + a concurrent-
  adopt race test) + 2782 unit green; provider-gate clean.

**Deferred (tracked, lower severity):** `D-KG-L7-ACTIVATE` now also covers the
R3 activation-time MEDs (SDK pre-drops off-schema edges before the writer's
triage-park → wire so the park still fires; `schema_version` ON CREATE only —
re-matched edges stay NULL) · `D-KG-LD-VIEWS-GRANT` (views CRUD lacks the project
grant the LF tool has) · `D-KG-LF-PROPOSE-VALIDTO` (propose-edge no valid_to<from
guard) · `D-KG-SYNC-DIFF-LABEL` (node_kind diff mislabels strength as 'label' —
apply-safe).

**REMAINING → S3:** `D-KG-L7-ACTIVATE` · `LG` glossary internal-read (glossary
branch) + `D-KG-LG-REAL` · KM5/KM6 (admin MCP + confirm machinery for class-C) ·
`D-KG-LF-PROPOSE-EDGE-INBOX`. Data layer, HTTP surface, resolution, adopt/sync,
extraction plumbing, frontend, enforcement mechanism, and the safe MCP tier are
BUILT + live-verified + adversarially reviewed.

---

**2026-06-20 — D-KG-L7-ACTIVATE Milestone A (write-boundary activation) — DONE (unit), live deferred.**
The enforcement was DORMANT: `/persist-pass2` (the live worker-ai persist path)
passed neither `schema=` nor `triage_repo=`. Milestone A activates the write
boundary, **knowledge-service only** — no SDK/worker-ai changes, so NO pre-drop
tension (the SDK isn't schema-aware here → every candidate reaches the writer,
which is the sole enforce+park point).
- **A1 — projection helper** (`app/ontology/extraction_projection.py`):
  `ResolvedSchema` → SDK `ExtractionSchema` dict. `advisory=False` carries the
  schema's real `allow_free_edges` (write boundary = authoritative); `advisory=True`
  forces it True (the Milestone-B SDK-prompt posture — hint, never pre-drop).
  `event_kinds` projects empty (not modeled → SDK keeps static event behavior).
- **A2 — resolve at persist** (`internal_extraction.py`): `_resolve_schema_for_persist`
  resolves the project's effective schema via `GraphSchemasRepo.resolve_for_project`,
  projects it (authoritative), and `/persist-pass2` passes `schema=` + a `TriageRepo`
  to the writer. 30s TTLCache keyed by `(user_id, project_id)` (mirrors `_anchor_cache`)
  so a bulk job doesn't re-resolve per chapter; adopt/sync picked up within the TTL.
  Fail-soft: no project / resolve error → `schema=None` (today's behavior); `TriageRepo`
  guarded like the JobLogsRepo producer (pool-absent → None, harmless since the writer
  only parks inside the closed-edge guard). **Net effect now LIVE:** M3 `schema_version`
  stamped on every edge; closed-edge projects drop+park off-schema edges to triage.
- **A3 — ON-MATCH stamp fix** (`relations.py`, R3 MED): `create_relation` stamped
  `schema_version`/`graph_id` ON CREATE only → re-matched edges stayed NULL. Added
  `r.schema_version = coalesce($schema_version, r.schema_version)` to ON MATCH —
  backfills a pre-activation edge on re-extraction, and a legacy NULL persist NEVER
  wipes an existing stamp. `graph_id` intentionally NOT touched on MATCH (NULL at v1;
  don't clobber a future M2 partition assignment).
- **VERIFY:** 2788 knowledge unit green (+6: 4 projection + 2 persist-wiring), full
  suite no-regression; provider-gate clean. **`live infra unavailable: docker daemon
  hung this session`** — the written live tests (`test_L7_create_relation_stamps_
  schema_version_on_match` + the persist closed-edge park/stamp smoke) must run when
  the stack is up → `D-KG-L7A-LIVE-SMOKE`.

**2026-06-20 — D-KG-L7-ACTIVATE Milestone B (SDK-prompt activation) — DONE (unit), live deferred.**
Makes the LLM emit the project's vocab (the precision half of activation). The
R3 pre-drop is reconciled by construction: the SDK is fed an **advisory**
projection (`allow_free_edges` forced True) so it injects vocab as a prompt hint
but never pre-drops; the writer (Milestone A) resolves the AUTHORITATIVE schema
server-side and stays the sole enforce+park point.
- **B1 — KS internal endpoint** `POST /internal/extraction/resolve-schema`
  (X-Internal-Token): resolves the project schema → returns the advisory projection
  (`has_schema=False` for no project / resolve error → static prompt). Internal
  endpoint (not in the public OpenAPI, like the sibling /internal/extraction/*).
- **B2 — worker-ai** (`clients.py` + `runner.py`): `KnowledgeClient.resolve_extraction_schema`
  fetches the advisory schema; the runner resolves it **once per job** (pinned like
  the config snapshot) and threads `schema=` into `extract_pass2` on BOTH the sync
  `_extract_and_persist` (chapters + chat turns) and the decoupled path.
- **B-decoupled** (`decoupled_extract.py`): the schema dict is stashed in
  `resume_state["_schema"]`; `_schema_from` rebuilds it and
  `assemble_entity_submit`/`assemble_trio_submits` pass it into the four
  `build_*_system` seams (all of which already accept `schema=`, lane LB) → vocab
  reaches the prompt on the decoupled fan-out too.
- **B3 — reconciliation:** advisory projection ⇒ SDK `_closed_edge_vocab` returns
  None ⇒ no SDK pre-drop ⇒ the writer's triage park always fires.
- **B4 — `/extract-item` legacy path:** intentionally **left dormant** (Phase 4b-γ
  replaced it with persist-pass2; worker-ai no longer calls it). If revived it needs
  the same advisory-to-SDK / authoritative-to-writer split → `D-KG-L7B-EXTRACT-ITEM`.
- **VERIFY:** worker-ai 280 + KS unit 2792 green (+9 worker-ai: 4 client + 5 decoupled;
  +4 KS resolve-schema endpoint); provider-gate clean. **`live infra unavailable:
  docker daemon hung this session`** → the full-pipeline cross-service live-smoke
  (job → resolve-schema → vocab-in-prompt → persist stamp/park) deferred to
  `D-KG-L7-LIVE-SMOKE` (consolidates the Milestone-A `D-KG-L7A-LIVE-SMOKE`).

**D-KG-L7-ACTIVATE — both milestones BUILT + unit-verified.** Remaining: the
consolidated cross-service live-smoke (`D-KG-L7-LIVE-SMOKE`, blocked on a live
stack) + the dormant legacy `/extract-item` (`D-KG-L7B-EXTRACT-ITEM`).

**2026-06-20 — `D-KG-L7-LIVE-SMOKE` write-boundary half CLEARED (live PG + Neo4j).**
Docker recovered; brought up infra postgres+neo4j and ran the KG integration suite.
- **Live Neo4j ON-MATCH stamp** (`test_L7_create_relation_stamps_schema_version_on_match`):
  pre-activation edge (NULL) → re-extraction backfills `schema_version=5` on MATCH →
  later legacy NULL persist COALESCE-preserves it; `graph_id` untouched. **PASS.**
- **Stitched end-to-end** (`test_l7_persist_activation.py`, NEW): ONE real
  `write_pass2_extraction` with a CLOSED schema → on-schema edge written + stamped
  `schema_version=42` in Neo4j, off-schema edge count=0 (dropped) + parked to real
  `kg_triage_items` (`unknown_edge_type`, `edge:forbidden_pred`, schema_version=42,
  pending) via the real `TriageRepo`. **PASS** — proves the whole Milestone-A chain
  in one call (the unit writer tests mock these seams).
- **Full KG live suite green:** 77 integration (relations + triage + graph_schemas +
  ontology_mutations + resolver) on real PG+Neo4j. Component pieces all live-proven:
  create_relation stamp (relations), TriageRepo.park→kg_triage_items (triage),
  resolve_for_project (graph_schemas/resolver).
- **B1 endpoint LIVE-PROVEN** on the real rebuilt knowledge-service container
  (`:8216`, the first request 404'd → confirmed the running image was stale →
  `docker compose up -d --build knowledge-service` → healthy): `POST
  /internal/extraction/resolve-schema` for a random project returns the `general`
  fallback advisory projection — `has_schema=true`, 6 entity_kinds, 5 fact_types,
  `allow_free_edges=true`, `schema_version=1`, `label=<project>@v1`. Proves the
  endpoint is registered, resolves the schema, and emits the advisory projection.
- **Live-LLM vocab-emission residual — now CLEARED 2026-06-20** (see the entry
  below). Everything around it was already proven: B1 endpoint live, write-boundary
  stamp/park live, worker-ai HTTP wiring + SDK prompt injection unit-proven
  (worker-ai 280).

**2026-06-20 — small-deferred SWEEP (4 rows CLEARED).**
- **`D-KG-LD-VIEWS-GRANT`** — views CRUD (create/upsert/delete) lacked the project
  grant the LF `kg_view_upsert` tool has → a caller could mint views against a
  project they can't reach. Added `require_project_grant(VIEW)` to all three
  (project_id → UUID, repo still owner-scopes the row; `list_views` stays ungated —
  reveals only the caller's own rows). 404/403 via the gate.
- **`D-KG-LF-PROPOSE-VALIDTO`** — `kg_propose_edge` had no `valid_to >= valid_from`
  guard. Added a Pydantic `model_validator` rejecting a closing ordinal before the
  opening one at mint (equal allowed — opens+closes same chapter).
- **`D-KG-SYNC-DIFF-LABEL`** — `_diff_list(pair=True)` hardcoded the 2nd field as
  `"label"`, mislabelling a node-kind's *strength* in the sync diff. Added a
  `pair_field` param; node_kinds now diff under `"strength"` (fact_types keep
  `"label"`). Apply-safe; cosmetic-but-misleading fix.
- **`D-KG-LF-PROPOSE-EDGE-INBOX`** — an on-schema agent-proposed edge parked as
  `edge_cardinality_conflict` (a stateful condition the tool can't check, INV-K1),
  overloading the taxonomy. Added a dedicated `proposed_edge` item_type (Literal +
  **migration**: widened the `kg_triage_items` item_type CHECK idempotently;
  `SUGGESTED_ACTIONS["proposed_edge"]=["dismiss"]` — the "place into Neo4j" confirm
  is the un-wired central write path KM6, deliberately not offered yet).
- **VERIFY:** 2794 knowledge unit (incl new propose-edge `proposed_edge`/`valid_to`,
  views `404`/owner-scope, sync-diff `strength`) + 30 live integration (triage incl
  the widened-CHECK `proposed_edge` park + mutations sync_diff) green; provider-gate
  clean. Single-service (knowledge-service) — no cross-service token needed.

**2026-06-20 — `D-KG-L7-LIVE-SMOKE` residual CLEARED (live-LLM vocab emission).**
Full stack up (infra postgres+neo4j+rabbitmq+provider-registry+ai-gateway+knowledge
+worker-ai). **First, the stale-image trap fired exactly as `live-smoke-rebuild-
stale-images-first` warns:** the running `infra-worker-ai-1` image PRE-DATED Milestone B
(`grep resolve_extraction_schema` → 0; bundled SDK had no `ExtractionSchema`). Rebuilt
+ recreated worker-ai → Milestone B code now live. Used the **already-registered
LM Studio BYOK** for `claude-test` (no new provider).
- **Seed (reproducible):** a project-scoped CLOSED custom schema for synthetic project
  `1111…1111` — `kg_graph_schemas(scope='project', allow_free_edges=false,
  schema_version=77)` + edge types `WORSHIPS/GUARDS/SEALED_BY`, node kinds
  `deity/relic/bloodline`, fact types `curse/prophecy`. Distinctive vocab the LLM
  would not emit by default → emission is provable. (Seed removed after the run.)
- **[1] Live resolve-schema** (real `KnowledgeClient.resolve_extraction_schema` →
  `POST /internal/extraction/resolve-schema`): returned the project's vocab,
  `label=…@v77`, `schema_version=77`, **`allow_free_edges=true`** even though the DB
  row is `false` — proving the **advisory projection forces free-edges True** live
  (the R3 reconciliation; the writer stays the authoritative closed enforce+park).
- **[2] Prompt injection proven:** `append_schema_constraints` appended a
  `## Project ontology (custom schema)` block to the relation system prompt listing
  `GUARDS, SEALED_BY, WORSHIPS` as preferred predicates.
- **[3] LIVE `extract_pass2(schema=…)`** → loreweave_llm SDK → provider-registry →
  **LM Studio `qwen2.5-7b-instruct`** on the passage *"…priestess Lyra worshipped the
  storm-god Aolen… the relic Heartstone was guarded by the dragon Vorth… the Targon
  bloodline sealed the Heartstone to contain its curse."* Emitted:
  - **Entity kinds 3/3 exact** — every entity classified with a *project* kind
    (`Aolen=deity`, `Heartstone=relic`, `Targon bloodline=bloodline`); ZERO generic
    `character`/`organization`.
  - **Relation predicates** — `Lyra -[worships]-> Aolen` ✓, `Targon bloodline
    -[sealed_by]-> Heartstone` ✓ (exact project vocab), `Heartstone -[guarded_by]->
    Vorth` (a coined variant of `GUARDS`). The coin is CORRECT under advisory mode
    (`allow_free_edges=True` permits coining); `/persist-pass2`'s authoritative closed
    schema would then park `guarded_by` as off-schema — the advisory-SDK /
    authoritative-writer split working exactly as designed.
- **RESULT: PASS** — the project vocab flows seeded-schema → live resolve-schema →
  SDK prompt → REAL LLM → emitted output. With the write-boundary half already live
  (PG+Neo4j stamp/park), **`D-KG-L7-LIVE-SMOKE` is fully closed.** Driver was a
  throwaway in-container script (hardcoded dev-box user/model UUIDs, not portable) —
  not committed; the recipe above is the reproduction record.

**D-KG-L7-ACTIVATE — COMPLETE.** Both milestones built, unit-verified, and fully
live-proven (write-boundary + live-LLM emission). Remaining KG epic deferrals are
unrelated: `D-KG-L7B-EXTRACT-ITEM` (dormant legacy path), KM5/KM6 (class-C MCP tools
+ confirm spine), `LG`/`D-KG-LG-REAL` (glossary branch), `D-KG-LE-BROWSER-SMOKE` (FE).

**2026-06-20 — KM6-M1: class-C confirm-token machinery foundation + `kg_schema_edit`
canary — BUILT + live-proven.** Plan: `docs/plans/2026-06-20-kg-confirm-token-machinery.md`.
Spec §5/§13. Knowledge-service ONLY (zero glossary code touched — its §13 Go machinery
is the read-only port reference). The generalized class-C spine:
- **Token codec** `app/ontology/confirm.py` — port of glossary `action_confirm_token.go`:
  domain-separated HMAC (`kg-action-confirm:v1|`, keyed by `jwt_secret`), `ActionClaims`,
  closed descriptor enum (live = `{kg_schema_edit}`; reserved fail closed at mint+verify),
  constant-time verify, 10-min TTL. Security-keystone TDD (11 unit incl tamper/expiry/
  domain-separation/fail-closed).
- **`consumed_tokens` ledger** (migration, mirrors glossary) + `ActionTokenRepo.consume`
  (atomic `INSERT … ON CONFLICT DO NOTHING`; real-PG: first wins, replay loses,
  concurrent double-claim → exactly one winner).
- **`/v1/kg/actions/{preview,confirm}`** (`routers/public/kg_actions.py`) — JWT-gated;
  decode → authority re-check (proposer-bind + MANAGE; admin→501) **before** the jti
  claim → re-validate drift → effect. Preview is non-consuming, current-state.
- **`kg_schema_edit` effect** (`app/ontology/schema_edit_effect.py`) — add/deprecate
  edge_type|fact_type via the existing `OntologyMutationsRepo` (bumps schema_version),
  with optimistic-concurrency re-validate (captured `schema_id`+`expected_schema_version`
  vs live → drift = re-proposable 422).
- **`kg_schema_edit` MCP tool** (the FIRST live class-C tool) — MINTS a confirm-token
  (NO write; INV-K1/INV-T3), MANAGE-gated, requires an adopted project schema (never
  edits System `general`). Registered in the catalog (now 18 tools).
- **VERIFY:** 2828 knowledge unit (+~32 new) + real-PG integration (ledger atomicity,
  effect add/deprecate/drift, preview) green. **Live-smoke on the running stack**
  (rebuilt knowledge-service:8216, real JWT + real PG): preview→confirm(add WORSHIPS,
  v1→v2)→replay 422→stale-drift 422→wrong-user 403; live schema_version=2, edge landed.
  `/review-impl` (auth boundary): **no HIGH/MED**; 1 LOW fixed (descriptor-dispatch
  tripwire test); 2 cosmetics accepted. Single-service change. `D-KG-LF-KM6` partially
  cleared (spine + first descriptor); **still deferred:** the other descriptors
  (`kg_adopt`/`kg_sync_apply`/`kg_triage_*`), KM5 admin `/mcp/admin` + RS256 + the
  admin authority branch (currently 501), and the FE confirm card.

**2026-06-21 — deferred SWEEP (verified vs code; 6 rows CLEARED).** After KM5 (M1–M3
backend + M4a skill + M4b gateway admin federation) shipped, swept this branch's open
deferrals and verified each against the current code:
- **`D-KG-LF-KM6`** ✅ CLEARED — KM6 confirm machinery + all 3 class-C descriptors
  (`kg_schema_edit`/`kg_adopt`/`kg_sync_apply`) shipped; the LF MCP tools' class-C writes
  now route through the confirm spine.
- **`D-KM5-M4B-GATEWAY-ADMIN-FED`** ✅ CLEARED — ai-gateway federates knowledge `/mcp/admin`
  (multi-provider `adminProviders`, `kg_` prefix; commit `2f22bdfa`/`490adde7`, 53 jest).
- **`D-KM5-M4C-CHAT-CMS`** ✅ CLEARED — the chat admin surface's `get_admin_tool_definitions`
  lists the merged gateway `/mcp/admin` catalog, so `kg_admin_*` tools appear on CMS
  automatically (no chat change needed; `knowledge_skill` stays OFF the admin surface).
- **`D-KG-LF-PROPOSE-VALIDTO`** ✅ CLEARED — the propose-edge `valid_to < valid_from`
  guard exists (`graph_schema_tools.py` arg-model validator, raises on inversion).
- **`D-KG-SYNC-DIFF-LABEL`** ✅ CLEARED — `_diff_list` takes a `pair_field` ("strength"
  for node_kinds, "label" for fact_types) in `ontology_mutations.py`; no longer mislabels.
- **`D-KM0-CHAT-STALE-COMMENT`** ✅ CLEARED — the stale `/internal/tools/definitions`
  comment in chat `knowledge_client.py` corrected to the MCP `tools/list` source (KM0 retired
  the HTTP path).

**2026-06-21 — design/feature deferred CLEARANCE (8 rows, fan-out + batched).** Spec
`docs/specs/2026-06-21-kg-deferred-clearance.md`. Built as 6 lanes across 2 waves (wave-1
parallel worktree agents A/B/C/D/F merged into the branch; wave-2 lane E serial in the main
checkout), each TDD + 2-stage review; `/review-impl` on the security-relevant lanes (C, F, A, E).
- **`D-KG-L7-CARDINALITY`** ✅ — `single_active` edge auto-close in `create_relation`
  (`_CLOSE_PRIOR_SINGLE_ACTIVE_CYPHER`, same-Tx, before MERGE); `ExtractionSchema.edge_cardinalities`
  threaded from the resolver → writer. Semantic: a subject holds ≤1 open instance of the predicate
  (close = same subject+predicate, any object, own-id excluded). Cross-user AND cross-project
  non-leak proven (project-scoped `entity_canonical_id` makes the subject node project-unique).
- **`D-KG-LB-CACHE-SCHEMA-KEY`** ✅ — `compute_task_id` gains `schema_key` (= schema label
  "project@vN"); `_p2_cache_wrap` derives it via `_p2_schema_key` at both call sites. Empty/None
  ⇒ byte-identical legacy hash. (Wave-1 agent shipped a no-op on a stale base; redone on the
  merged base so the schema is actually in scope — commit `5da9954d`.)
- **`D-KG-LD-GRANTEE-TIMELINE`** ✅ — grant-gated cross-owner edge-timeline read
  (`get_entity_by_id_any_owner` + resolve-to-owner gate mirroring `_resolve_owner`; cypher binds
  the OWNER). 404/403 discipline + cross-book denial unit-proven. `/review-impl`: clean.
- **`D-KG-L7B-EXTRACT-ITEM`** ✅ — `/extract-item` (NOT dead — composition C27 calls it) given
  the L7 advisory-SDK / authoritative-writer schema split, resolved internally; contract unchanged.
- **`D-KG-LH-NEO4J-REAPPLY`** ✅ — real `Neo4jReapplyWriter` over `create_relation`, injected into
  the triage resolve route (owner-scoped, fail-soft per item); `close_previous` reuses the L7 close.
- **`D-KG-LF-PROPOSE-EDGE-INBOX`** ✅ — `proposed_edge` apply wired as class-C
  `DESC_TRIAGE_PROPOSED_EDGE` (`triage_proposed_edge_effect.py`); `kg_triage_place_edge` MCP tool
  MINTS only (INV-K1, `assert_not_called` locked); `place_edge` added to SUGGESTED_ACTIONS.
- **`D-KG-LH-LC-SCHEMA-WRITE`** ✅ — schema-mutating triage routed through `ontology_mutations`
  via class-C `DESC_TRIAGE_SCHEMA_WRITE` (`triage_schema_write_effect.py`, optimistic-concurrency
  drift→422); `set_edge_cardinality`/`widen_edge_target_kinds` additive repo methods; resolved
  items get the new schema_version stamped (tenant-scoped).
- **VERIFY:** full knowledge unit suite **2965 passed**; provider-gate clean; the cardinality /
  reapply / schema-write live integration tests collect + skip (infra down) → fold into the §6 E2E.
- **`/review-impl` (4 cold reviewers across C/F/A/E): ZERO real bugs.** Class-C spine verified
  (jti consume-before-effect, descriptor↔authority pairing, HMAC param integrity, cross-tenant
  gating, drift revalidation). Landed hardening: cross-project cardinality lock test, adopt-preview
  route cross-tenant test, `get_entity_by_id_any_owner` `__all__` export, gate-assumption docstrings.

**Still open (genuinely-remaining — all infra/another-branch):**
- **Live-smokes (need the multi-service stack up):** the consolidated `§8` E2E (spec
  `2026-06-21-kg-deferred-clearance.md`) will tick `D-KM5-M3-LIVE-SMOKE`, residual `D-KG-L7-LIVE-SMOKE`,
  `D-KG-L7A-LIVE-SMOKE`, `D-KG-LD-NEO4J-SMOKE`, `D-KG-LC-ROUTE-LIVE-TEST`, `D-KG-LE-BROWSER-SMOKE`,
  `D-LB-LIVE-SMOKE`, plus the new cardinality/reapply/schema-write/grantee-timeline live tests.
- **Not ours:** `D-KG-LG-REAL` (glossary-branch internal-read dependency).

Net: the **pure-code deferred surface for this branch is fully cleared.** What remains is the one
consolidated live E2E (stack) + the glossary-branch row.

**2026-06-21 — live E2E (data layer + deployed routes) GREEN.** Brought up the full infra
stack (postgres+neo4j+rabbitmq+provider-registry+ai-gateway+knowledge+worker-ai). Ran the
KG integration suite on a throwaway test DB (`loreweave_knowledge_e2e`, dropped after) + the
live Neo4j (`bolt://localhost:7688`): **101 passed** — cardinality A (incl. cross-user +
cross-project boundary locks), reapply E1 (map/close_previous/dismiss Neo4j writes), proposed-
edge E2 park, schema-write E3 (add_to_vocab bumps version, drift→422, set_multi_active/widen),
adopt-preview F (+ route cross-tenant denial), resolver/views/schemas/persist-activation. The
run **caught a real stale assertion** the unit suite couldn't (proposed_edge suggested_actions
still encoded dismiss-only → fixed to `[dismiss, place_edge]`, commit `68411c6a`) — the exact
cross-layer gap the E2E exists for. Rebuilt the knowledge-service image + recreated the
container (`:8216`, healthy); the new routes are registered + reachable live (POST
`/v1/kg/projects/{id}/adopt/preview` and GET `/v1/kg/entities/{id}/edges/{type}/timeline`
both 401 unauth'd, not 404). **Cleared:** `D-KG-LD-NEO4J-SMOKE`, the cardinality/reapply/
schema-write live halves, `D-KG-LC-ROUTE-LIVE-TEST` (new routes live-reachable + repo logic
live-tested).
**Still needing the heavy cross-service/LLM/UI tier (next opt-in):** `D-KM5-M3-LIVE-SMOKE`
(CMS RS256 → gateway `/mcp/admin` → `kg_admin_*`), `D-LB-LIVE-SMOKE` (real-LLM vocab emission
through the cache-key path), `D-KG-LE-BROWSER-SMOKE` (Playwright adopt-loss warning UI). These
need BYOK model availability + a `frontend` image rebuild + browser automation.

**2026-06-21 — heavy live tier (admin RS256 + real-LLM extraction; browser blocked).**
- **`D-KM5-M3` admin gate — PASS (live).** Found + fixed a real **deployability gap**: the
  knowledge-service compose block never wired `ADMIN_JWT_PUBLIC_KEY_PEM`, so `/mcp/admin` was
  permanently 503 in the deployed stack (the verifier code shipped in KM5-M1/M3 but the env
  passthrough didn't). Added it (defaults empty → no behavior change unless set). Generated a
  dev RS256 keypair, set the key, recreated knowledge-service, minted a real admin JWT, and
  drove the DEPLOYED `/mcp/admin` over real HTTP via the MCP client: valid internal+admin token
  → `tools/list` = `kg_admin_propose_template` + `kg_admin_template_read`, `kg_admin_template_read`
  returned the real System templates (incl `general`); **missing-admin / missing-internal /
  tampered / wrong-kid all rejected (401).** The ai-gateway federation hop (M4b) is the
  53-jest-unit-proven transparent proxy over this exact endpoint. Key removed + stack restored
  after the run.
- **`D-LB` — D-lane `/extract-item` LLM→Neo4j pipeline PASS (live).** Drove a real `/extract-item`
  against the deployed container with the BYOK LM-Studio `qwen2.5-7b-instruct`: resolved the
  schema internally (my D lane) → LLM extracted (5 entities, 5 relations, 2 events) → wrote to
  Neo4j (verified 5 entities + 5 relations for the synthetic project; cleaned by project_id
  after). Proves the schema-split extraction pipeline live end-to-end. **Note:** the
  schema-aware cache key (B) is NOT exercised by `/extract-item` (the `extraction_leaves` cache
  is keyed on `book_id`+`chapter_id`, used by the worker/persist-pass2 path), so B stays
  unit-proven (8 tests incl. cross-schema discrimination + byte-identical legacy); cardinality
  auto-close is live-proven at the write boundary (the 101-test run). Live LLM vocab emission
  was already cleared in the earlier `D-KG-L7-LIVE-SMOKE`.
- **`D-KG-LE-BROWSER-SMOKE` — BLOCKED (not runnable).** The KG knowledge-ontology FE
  (`AdoptPicker` + the lane-F loss warning) is built as MVC components + vitest-proven (10
  AdoptPicker + 9 hook tests) but is **NOT imported by any page/route** — the "C3 wiring" the
  LE `INTEGRATION.md` defers was never done, so the component is unmounted and unreachable in
  the running app. A Playwright smoke has nothing to navigate to; a `frontend` rebuild wouldn't
  help. Reclassified: blocked on KG-ontology FE route integration (a feature-wiring task, NOT a
  lane-F bug) → tracked as `D-KG-ONTOLOGY-FE-WIRING` (supersedes `D-KG-LE-BROWSER-SMOKE`, which
  presumed a mounted UI).

**2026-06-21 — D-KG-LG-REAL + D-KG-ONTOLOGY-FE-WIRING + D-KG-LE-BROWSER-SMOKE CLEARED (live).**
- **`D-KG-LG-REAL`** ✅ — the knowledge KG resolver/adopt-gate's `glossary_ontology_client`
  (real `HttpGlossaryOntologyClient`) targeted two glossary `/internal` endpoints that never
  existed (the planned "LG") → 404→None degrade. Added them (additive: `internal_ontology_read.go`
  + 2 server.go registrations, reusing `loadBookOntology`/`loadKinds`): `GET /internal/books/
  {id}/ontology` + `GET /internal/users/{id}/glossary-standards`. LIVE: user-standards→200 + 12
  System kinds; book→200 source=book; no-token→401; **S2S from inside the knowledge container →
  glossary-service:8088 → 200 real kinds** (the resolver now reads real node-kinds). Commit `b56edc09`.
- **`D-KG-ONTOLOGY-FE-WIRING` + `D-KG-LE-BROWSER-SMOKE`** ✅ — wired the lane-LE ontology UI into
  a "Graph Schema" book tab (`KnowledgeOntologyTab` composing adopt/schema/views/sync; resolves
  the book's project via `book_id`); consolidated the `kgOntology` i18n into the registered locale
  files (×4) + a page shell; commit `c7cb1aaa`. The in-browser smoke then caught **two more real
  gaps** (unit/vitest couldn't): the App router had no `/books/:bookId/kg-ontology` route (tab
  404'd), and **the BFF proxied only `/v1/knowledge`, not `/v1/kg`** (every ontologyApi call 404'd
  at the gateway) — fixed both (commit `eb39a3ca`). LIVE browser (claude-test, real stack): the
  Graph Schema tab loads, AdoptPicker lists real templates (general/xianxia-harem); seeded a
  book-linked project + adopted general + a custom edge, then selecting general rendered the loss
  warning listing "smoke_custom_edge (edge type) removed" with the adopt button GATED until "I
  understand, proceed" → enabled. Seed cleaned up.

**2026-06-21 (later) — D-KG-LG-REAL user-tier-kind UNION refinement CLEARED (live).**
- `/internal/users/{id}/glossary-standards` now returns the user's RESOLVED kind catalog —
  System defaults UNION the user's own per-user `user_kinds` tier, per-user shadowing System by
  `code` (CLAUDE.md › User Boundaries resolution rule), instead of System-only. Additive: the
  handler builds a `byCode` slot index over the System rows, then overlays active non-trashed
  `user_kinds` (owner-scoped) — matching code → overwrite in place (tier flips to `user`, no
  dup), new code → append. Degrades to System-only on a missing `user_kinds` table (42P01) so an
  un-migrated glossary DB still serves the baseline rather than 500.
- Tests: `internal_ontology_read_test.go` — 3 unit (token gate ×2, bad-UUID 400) + a real-PG
  integration proving union + shadow-by-code (no dup, count unchanged) + tenant-isolation (user
  B never sees A's per-user kinds). All green (integration vs a throwaway PG on infra:5555).
- LIVE S2S (rebuilt glossary image): seeded a `user_kinds` row for claude-test, called the
  endpoint from inside the knowledge container → `glossary-service:8088` → 200, count 13 (12
  System + 1), user-tier list showed the seeded kind AND a pre-existing `character` user-kind
  **shadowing** the System "character" (tier=user). Seed cleaned up.

**KG epic deferred surface: FULLY CLEARED + live-proven** — every tracked KG deferred row,
including `D-KG-LG-REAL`'s user-tier-kind union refinement, is cleared.
