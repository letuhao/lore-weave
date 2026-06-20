# Knowledge Graph — Customizable Ontology + Multi-Graph (design)

> **Trạng thái:** DESIGN — chưa đụng code. Implement ở session + branch khác sau.
> **Ngày:** 2026-06-20
> **Branch:** thiết kế trên `feat/glossary-assistant-coverage` (chỉ doc); implement sẽ ở branch riêng (đề xuất `feat/knowledge-graph-ontology`).
> **Phạm vi:** Biến KG trong `knowledge-service` từ **một ontology hardcode chung** thành **ontology customizable theo tier (system / user / project)**, với khả năng soi cùng dữ liệu theo nhiều **view/lens** (multi-graph v1) và để dành seam cho **graph partition** thật (deferred).
> **Quan hệ với glossary:** ĐỘC LẬP. Glossary là refactor riêng, đã xong (tiered genre·kind·attribute). KG **anchor** node kinds từ glossary nhưng **tự sở hữu** schema quan hệ/graph của mình. KHÔNG sửa glossary trong epic này.
> **Liên quan:** [`2026-06-12-van-co-than-de-entity-ontology.md`](2026-06-12-van-co-than-de-entity-ontology.md) (template mẫu), [`KNOWLEDGE_SERVICE_ARCHITECTURE.md`](../03_planning/KNOWLEDGE_SERVICE_ARCHITECTURE.md), CLAUDE.md "User Boundaries & Tenancy".

---

## 1. Vấn đề

KG hiện tại bị **hardcode một ontology chung**. Một đồ thị tri thức chỉ thật sự hữu ích khi được dựng để **giải một bài toán cụ thể** — bộ quan hệ, loại fact, vocab phải khớp với câu hỏi cần trả lời. Một ontology "general" thì khi đi vào bài toán cụ thể (vd huyền huyễn hậu cung VCTĐ) lại quá rộng + thiếu đúng chỗ → khó áp dụng.

Glossary đã giải bài toán "customizable" cho **node identity** (genre·kind·attribute, tiered system/user/book). KG cần điều tương tự cho **graph shape** (edge vocab, fact/state types, controlled vocab) — nhưng đây là domain của KG, không phải glossary.

### 1.1 Hiện trạng (kết quả review code 2026-06-20)

**Điểm mạnh — nền tảng giữ lại, KHÔNG đập:**

| Mặt | Trạng thái | Bằng chứng |
|---|---|---|
| Tenancy / isolation | Chắc | Mọi node Neo4j có `user_id` + `project_id`; safety wrapper K11.4 ép mọi query bind `$user_id` ([app/db/neo4j_helpers.py](../../services/knowledge-service/app/db/neo4j_helpers.py)); index prefix `user_id`. Không thấy IDOR. |
| Temporal + provenance | **Đã implement** (phần khó nhất) | `valid_from`/`valid_until` trên relations & facts; `:ExtractionSource` + edge `:EVIDENCED_BY(source_id=chapter_id)`; event có `event_order`/`chronological_order` ([app/db/neo4j_repos/relations.py](../../services/knowledge-service/app/db/neo4j_repos/relations.py), `provenance.py`, `events.py`). |
| Two-layer anchor | Có | Node neo về glossary qua `glossary_entity_id`. |
| Edge predicate mở | Linh hoạt | Predicate là free string (normalize snake_case), lưu `:RELATES_TO {predicate}`. |
| Project abstraction | Có | `knowledge_projects` có `project_type` (book/translation/code/general) + `book_id` optional + derivative projects. |

**Điểm yếu — đúng chỗ cần sửa:**

| Mặt | Trạng thái | Vấn đề |
|---|---|---|
| Ontology nằm trong extraction SDK | HARDCODED | Entity/event/fact kinds là Python `Literal` + nhúng vào prompt `.md` ([sdks/python/loreweave_extraction/extractors/entity.py](../../sdks/python/loreweave_extraction/extractors/entity.py), `event.py`, `fact.py`, `prompts/*.md`). Đổi = sửa code + rebuild SDK + deploy. |
| KG tự định nghĩa entity kind riêng, lệch glossary | Mâu thuẫn | SDK hardcode 6 kind generic (`person/place/organization/artifact/concept/other`); glossary tiered; VCTĐ định nghĩa 8. → 3 bộ ontology không khớp. |
| KHÔNG có edge ontology | Lỗ hổng lớn nhất | Predicate free string → không vocab per-project, không validate, không bộ edge đóng theo bài toán, không UI, không scope được. |
| Không có scope tier | Thiếu | Chỉ `(user_id, project_id)`. Không có system template / per-user ontology / adopt-copy-down. |
| Không multi-graph | Thiếu | 1 project = 1 graph ngầm; không tách "graph quan hệ" vs "graph cảnh giới"; không extend/branch. |
| Fact/event type sai miền | Lệch | `decision/preference/milestone/negation` kiểu chat-memory, không hợp KG tiểu thuyết. |

### 1.2 Mục tiêu

1. Ontology của KG (edge types, fact/state types, controlled vocab) trở thành **dữ liệu**, tiered **system → user → project**, có **adopt (copy-down) + sync** như glossary đã chứng minh.
2. Node kinds **lấy từ glossary** (sửa cái re-hardcode), không định nghĩa lại trong KG.
3. Một project soi được dữ liệu theo nhiều **view/lens** (tập edge + node-kind) để phục vụ từng bài toán — **không cần** `graph_id` ở v1.
4. Để dành **seam** cho `graph_id` partition (graph độc lập / branch) — thiết kế trước, build sau.
5. **Additive-first**: project cũ không đổi hành vi cho tới khi chủ động adopt schema mới.

### 1.3 Không thuộc phạm vi (non-goals)

- Không sửa glossary (kể cả "relation level" từng deferred ở SS-4 — bài đó nay thuộc KG).
- Không build `graph_id` partition trong v1 (chỉ design seam).
- Không đổi mô hình tenancy data nodes `(user_id, project_id)` — chỉ thêm tier cho **schema/ontology**.
- Không xây admin-identity epic; system-tier write tạm gate sau `requireAdmin` placeholder (giống glossary đã làm).

---

## 2. Mô hình 4 lớp

```
┌─ Lớp 1: NODE KINDS ────────── nguồn: GLOSSARY (đã tiered). KG chỉ consume + validate.
│
├─ Lớp 2: GRAPH SCHEMA ──────── net-new, KG sở hữu, TIERED system/user/project.
│        edge types · fact/state types · controlled vocab (vd drive) · extraction hints
│        adopt (copy-down) + sync giống glossary.
│
├─ Lớp 3: VIEW / LENS ───────── v1 multi-graph. Tập {edge-types + node-kind filter} có tên,
│        soi trên CÙNG một project graph. Không cần graph_id.
│
└─ Lớp 4: GRAPH PARTITION ───── DEFERRED. graph_id phân vùng EDGE (node dùng chung), branch được.
         Chỉ design seam ở v1. LƯU Ý: view (filter edge chồng lấn) ≠ partition (sở hữu edge rời) —
         KHÔNG phải một continuum; promote = một feature riêng, xem §10-C4.
```

### Lớp 1 — Node kinds anchor từ glossary

- Bỏ `Literal` entity-kind trong extraction SDK; node kind đến từ **book ontology của glossary** (`GET /v1/glossary/books/{book_id}/ontology` — đã tồn tại; cần thêm route `/internal/` cho KG gọi server-to-server, xem §6).
- KG **validate** node kind nhận vào theo bộ kind của book; kind lạ → đẩy triage (`unknown`), không tự sinh.
- Giữ đúng two-layer pattern (CLAUDE.md): glossary = SSOT identity; KG neo qua `glossary_entity_id`.

> Lưu ý: glossary chưa expose ontology qua `/internal/`. Đây là **dependency** của epic này (§6) — một internal read route, không phải sửa mô hình glossary.

### Lớp 2 — Graph Schema (đơn vị customizable)

Một **graph schema** mô tả "đồ thị này gồm những loại quan hệ/fact/vocab gì". Khai báo:

- **Edge types** — vocab quan hệ: `code`, `label`, hướng (directed/undirected), `source_node_kinds[]`/`target_node_kinds[]` (tham chiếu kind glossary), `temporal` (mutable theo arc hay invariant), `provenance_required`, mô tả.
- **Fact/state types** — narrative-appropriate (thay bộ chat-memory).
- **Controlled vocab sets** — vd `drive` với tập giá trị cố định (§3.4 VCTĐ). Extractor chỉ được *gán*, không tự sinh giá trị.
- **Extraction hints** — pull gì / bỏ gì; ưu tiên ngân sách node (vd VCTĐ §6).
- **Node-kind expectation (soft)** — schema có thể khai báo bộ kind nó kỳ vọng để validate + UX (anchor sang glossary; không sở hữu).

**Tiered** theo đúng luật user-boundary của CLAUDE.md:

| Tier | Owner | Ai WRITE | Ai thấy | Ví dụ |
|---|---|---|---|---|
| **System** | platform | admin only | mọi người (read) | template "xianxia-harem KG" (VCTĐ), "general KG" |
| **User** | `user_id` | chính user | chính user (+ grantee) | tùy biến edge vocab riêng của user |
| **Project** | `project_id` | owner + grantee | owner + grantee | ontology thực tế đang dùng của 1 truyện |

**Adopt (copy-down) + Sync** — tái dùng đúng mental model glossary đã chứng minh:
- Project **adopt** một system/user schema → deep-copy schema + edge_types/fact_types/vocab vào một row scope=project (`source_ref`, `source_hash`).
- Project edit bản copy tự do (boundary independence — sửa của project không đụng template).
- **Sync**: so `source_hash` với content hash hiện tại của source → "có cập nhật"; apply per-row `keep_mine`/`take_theirs`.
- **Deprecate-not-delete** (`deprecated_at`) để giữ tham chiếu lịch sử.

> Đây là chỗ tái dùng lớn nhất: copy *mô hình* tiering + adopt + sync của glossary, áp cho graph-schema-tree thay vì genre·kind·attribute.

### Lớp 3 — View / Lens (multi-graph v1)

Một **view** trong project = tập có tên `{edge_type_codes[], node_kind_codes[]}` soi trên cùng một project graph. Giải quyết ngay "build graph cho 1 bài toán" mà không cần partition:

- *Relationship/Hậu cung view* = {`LOVER_OF`, `BETROTHED_TO`, `DAO_COMPANION_OF`, `RIVAL_OF`, `BETRAYED`, `KILLED`}
- *Cultivation view* = {`PRACTICES`, `HAS_REALM`, `COMPREHENDS`} + node kinds {character, technique, concept}
- *Political view* = {`MEMBER_OF`, `LEADS`, `SUBORDINATE_OF`, `ALLIED_WITH`, `AT_WAR_WITH`} + {character, organization}

View là **READ-only lens** (chỉ filter lúc query). **Extraction LUÔN chạy whole resolved schema**, không scope theo view — vì extraction discover entity/edge từ text, scope theo view sẽ bỏ sót entity chỉ xuất hiện qua edge ngoài view + băm 1 pass đọc thành N (lý do: §10-C3).

### Lớp 4 — Graph partition (DEFERRED)

`graph_id` làm partition thật: **EDGE** thuộc về một graph cụ thể (**node dùng chung** giữa các graph); graph độc lập / branch được. **Không build v1.** Chỉ yêu cầu v1:
- Seam = cột `graph_id NULL` (default = graph mặc định của project) **trên EDGE** (không phải node — node chồng lấn nhiều view/graph; partition theo node sẽ vỡ, §10-C4).
- View và partition là **2 hình khác nhau** (view = filter edge chồng lấn; partition = sở hữu edge rời), KHÔNG phải continuum. "Promote view→partition" là feature riêng khi cần graph branch thật, không phải đường tiến hoá mặc định.

---

## 3. Data model (đề xuất)

Graph schema = config có cấu trúc, author bởi người dùng → **Postgres trong knowledge-service (SSOT)**; Neo4j vẫn derived. Bảng mới (prefix `kg_`):

### 3.1 Bảng graph schema (tiered)

```
kg_graph_schemas
  schema_id        uuid PK
  scope            text  CHECK (scope IN ('system','user','project'))
  scope_id         text  -- NULL khi system; user_id khi user; project_id khi project
  code             text
  name             text
  description      text
  schema_version   int   -- tăng mỗi lần schema đổi; STAMP lên edge/fact đã write (§10-B4)
  content_hash     text  -- cho Sync (md5 của surface ngữ nghĩa, giống glossary)
  source_ref       text  -- 'system:<id>' | 'user:<id>' | NULL nếu native
  source_hash      text  -- hash đông cứng lúc adopt (so với content_hash upstream)
  deprecated_at    timestamptz NULL
  created_at, updated_at
  UNIQUE (scope, scope_id, code)        -- scope-keyed, KHÔNG unique-global (tránh đúng bug glossary cũ)
```

### 3.2 Con của schema (FK schema_id → kế thừa scope của cha)

```
kg_edge_types
  edge_type_id     uuid PK
  schema_id        uuid FK kg_graph_schemas
  code             text          -- 'LOVER_OF', 'PURSUES', ...
  label            text
  directed         bool
  source_node_kinds text[]       -- mã kind glossary (soft ref)
  target_node_kinds text[]
  temporal         bool          -- true => mọi instance bắt buộc valid_from + EVIDENCED_BY
  provenance_required bool
  cardinality      text  CHECK (cardinality IN ('single_active','multi_active'))
                                 -- single_active => mở instance mới TỰ ĐÓNG instance cũ (valid_to);
                                 -- vd PURSUES có thể multi_active (nhân vật nhiều động cơ) — §10-F1
  description      text
  deprecated_at    timestamptz NULL
  UNIQUE (schema_id, code)

kg_fact_types
  fact_type_id     uuid PK
  schema_id        uuid FK
  code, label, description
  deprecated_at
  UNIQUE (schema_id, code)

kg_vocab_sets
  vocab_set_id     uuid PK
  schema_id        uuid FK
  code             text          -- 'drive'
  label, description
  closed           bool          -- true => extractor chỉ gán, không tự sinh
  UNIQUE (schema_id, code)

kg_vocab_values
  vocab_value_id   uuid PK
  vocab_set_id     uuid FK kg_vocab_sets
  code             text          -- 'godhood', 'revenge', ...
  label            text          -- nhãn hiển thị (có thể Tiếng Việt)
  metadata         jsonb         -- vd { axis, has_target, archetype } cho drive
  UNIQUE (vocab_set_id, code)
```

### 3.3 View (scope=project) — READ-only lens

```
kg_views
  view_id          uuid PK
  project_id       text
  user_id          text          -- owner; tenancy (view per-user trong project shared, §10-D4)
  code, name, description
  edge_type_codes  text[]
  node_kind_codes  text[]
  created_at, updated_at
  UNIQUE (project_id, user_id, code)
```

> View KHÔNG mang `graph_id` (seam lớp 4 nằm trên EDGE, không trên view — §10-C4). View chỉ là filter đọc.

### 3.4 Neo4j (derived) — thay đổi tối thiểu

- Edge `:RELATES_TO {predicate}` giữ nguyên cơ chế, nhưng `predicate` từ nay **validate theo `kg_edge_types` của schema đã resolve** (write 400 nếu edge không thuộc schema và schema không cho phép free edge).
- Edge `temporal=true` → **bắt buộc** `valid_from` + `:EVIDENCED_BY`(chapter_id) lúc write (đã có hạ tầng; thêm enforcement). `cardinality='single_active'` → write tự đóng instance đang mở (§10-F1).
- **STAMP `schema_version`** lên mỗi edge/fact lúc write (truy được data thuộc phiên bản schema nào — §10-B4).
- Seam lớp 4: thêm property `graph_id` (NULL default) **trên EDGE** (không trên node — node dùng chung giữa graph; §10-C4). Additive, chưa dùng ở v1.

### 3.5 Resolution merge (system → user → project)

Lúc extraction/query, resolve **graph schema hiệu lực** của project:
- Project adopt 1+ system/user schema → đã copy-down thành (các) row scope=project. Resolution v1: **một project-scoped schema "active"** (kết quả merge lúc adopt), shadow theo `code`: project > user > system. Đa-schema-active để dành lớp 4.
- Cache resolved schema (TTL ngắn) — extraction gọi nhiều.
- **Nguồn node-kind (gap draft-01, M1 refine):** book ontology nếu project có `book_id`; nếu **không có book** (project_type translation/code/general) → lấy từ **glossary standards của user** (user∪system tier — chính cái `/standards` glossary đã có). Adopt-gate + kind picker resolve theo nguồn này.

### 3.6 Temporal read — query "as-of-chapter" (gap draft-04)

Spec có **data model** temporal nhưng thiếu **read contract**. Bổ sung:
- `valid_from` / `valid_to` lưu **chapter ordinal (int)** (so sánh range được); `chapter_id` đi trong `:EVIDENCED_BY` cho provenance.
- Edge **hiển thị tại chương N** khi `valid_from <= N AND (valid_to IS NULL OR valid_to > N)`. Edge invariant (`temporal=false`) luôn hiển thị.
- Endpoint:
  - `GET /v1/kg/projects/{id}/graph?view={code}&as_of_chapter={N}` → nodes+edges lọc theo **view** (lớp 3) + temporal as-of.
  - `GET /v1/kg/entities/{entity_id}/edges/{edge_type}/timeline` → chuỗi instance temporal (vd drive arc revenge→seek_dao→transcendence).
- `as_of_chapter` bỏ trống = "mới nhất" (mọi instance đang mở). Đây là scrubber theo chương ở draft-04.

### 3.7 Bảng triage (gap draft-05)

Phần tử extraction KHÔNG khớp schema KHÔNG ghi thẳng vào Neo4j — **park vào triage** (Neo4j chỉ chứa edge hợp-schema). Workflow §11.

```
kg_triage_items
  triage_id      uuid PK
  user_id        text
  project_id     text
  source         jsonb         -- {run_id, chapter_id, chapter_ord}
  item_type      text  CHECK (item_type IN
                   ('unknown_node_kind','unknown_edge_type','edge_kind_mismatch',
                    'unknown_vocab_value','edge_cardinality_conflict'))
  payload        jsonb         -- phần tử extractor thấy (proposed kind/edge/drive, src/tgt, evidence)
  signature      text          -- hash chuẩn hoá để gom + batch re-apply (vd "drive:curiosity")
  status         text  CHECK (status IN ('pending','pending_glossary','resolved','dismissed'))
  resolution     jsonb         -- hành động + tham số (§11)
  schema_version int           -- schema lúc park
  created_at, resolved_at, resolved_by
  INDEX (user_id, project_id, status), INDEX (project_id, signature)
```

---

## 4. System template đầu tiên — Vạn Cổ Thần Đế (chốt)

Seed một system graph schema `code = "xianxia-harem"` từ [VCTĐ ontology](2026-06-12-van-co-than-de-entity-ontology.md):

- **Node kinds kỳ vọng** (anchor glossary, soft): character, organization, location, concept, technique, item, event, relationship (§2 VCTĐ).
- **Edge types** (~18, §4 VCTĐ) — đánh dấu temporal đúng spec:
  - Character→Character: `MASTER_OF`, `DISCIPLE_OF`, `FAMILY_OF` (invariant); `LOVER_OF`, `BETROTHED_TO`, `DAO_COMPANION_OF`, `RIVAL_OF`, `ENEMY_OF`, `ALLY_OF` (**temporal**); `KILLED`, `BETRAYED`, `SAVED` (**temporal**, trục báo thù).
  - Character→khác: `MEMBER_OF` (**temporal**), `COMPREHENDS` (invariant), `PRACTICES`, `WIELDS`, `PARTICIPATED_IN`, `FROM`, `PURSUES`/`DRIVEN_BY` (**temporal** — bản đồ động cơ).
  - Org/Location: `SUBORDINATE_OF`, `ALLIED_WITH`, `AT_WAR_WITH`, `PART_OF`.
  - `relationship --INVOLVES--> character`.
- **Vocab set `drive`** (closed, §3.4 VCTĐ) — 16 giá trị: `godhood, immortality, seek_dao, seize_treasure, revenge, protect, love, restore_clan, domination, uncover_truth, transcendence, usurp_heaven, survival, hedonism, bloodlust, freedom`. `metadata` mang `{axis, has_target, archetype}`.
- **Fact/state types** narrative (thay bộ chat-memory) — vd `realm_change`, `allegiance_shift`, `motivation_shift`, `death`, `breakthrough` (rút từ event_type + state-delta của VCTĐ).
- **Extraction hints**: ngân sách node §6 VCTĐ; quy tắc §5 (không entity-hóa bloodline/constitution/realm-rank/species; báo thù = `PURSUES→revenge` + `BETRAYED`, không trope).

Đồng thời seed một system schema `code = "general"` **tái tạo đúng ontology hardcode hôm nay** (6 entity kind generic + bộ fact hiện tại + edge free) → project cũ default vào đây, **zero behavior change** (xem §5).

---

## 5. Migration — additive-first (an toàn)

Thứ tự để không vỡ project đang chạy:

1. **K1 — Schema + seed (additive).** Tạo bảng `kg_*`; seed system template `general` (= hardcode hiện tại) + `xianxia-harem` (VCTĐ). Chưa ai đọc → không đổi hành vi.
2. **K2 — Internal ontology read từ glossary.** Thêm `/internal/books/{book_id}/ontology` ở glossary-service (read-only, network-isolated) + client trong KG. (Dependency lớp 1.)
3. **K3 — Resolution + validation layer.** KG resolve schema hiệu lực của project; mặc định `general` nếu chưa adopt. Validate edge/fact/node-kind theo schema (fail-soft: log + triage, chưa reject cứng).
4. **K4 — Extraction động.** Refactor extraction SDK build prompt + validation **từ schema đã resolve** thay cho `.md` tĩnh + `Literal`. Đây là slice nặng nhất → /amaw hoặc subagent; giữ `general` làm fallback để so sánh hành vi.
5. **K5 — Adopt + Sync API + tiering.** Endpoint adopt (copy-down), sync (diff/apply), CRUD per-tier; system-write sau `requireAdmin` placeholder.
6. **K6 — View/Lens.** `kg_views` CRUD + scope query/extraction theo view.
7. **K7 — Enforcement cứng.** Bật reject edge ngoài schema / temporal-required (drop-and-triage per-edge, KHÔNG fail cả batch — §10-B2); bật `graph_id` NULL seam **trên edge** (chưa dùng).
8. **(Deferred) K8 — Graph partition.** `graph_id` thật, promote view → partition, branch.

> **Quy tắc additive:** không bao giờ reject cứng trước K7; mọi project không-custom luôn rơi về `general` = hành vi cũ. Cutover dữ liệu (nếu cần) phải guarded giống bài học G4 glossary (TRUNCATE re-run data-loss).

---

## 6. Dependencies & rủi ro

| # | Hạng mục | Ghi chú |
|---|---|---|
| D1 | Glossary `/internal/.../ontology` read | Chưa tồn tại; read route mới, KHÔNG sửa mô hình glossary. **Dùng ở 3 chỗ** (gap draft-02): adopt-gate (§11/M1), schema-authoring kind-picker (draft-02), triage promote-to-kind (§11). → read nóng, **cache**. Cần 2 biến thể: book ontology (`/internal/books/{id}/ontology`) + user glossary standards (`/internal/users/{id}/glossary-standards`, cho project no-book). Block K2/K3. |
| D1b | Glossary write API cho triage hand-off | "Promote to glossary kind" / "demote to attribute" (§11) là **glossary write**, do **user khởi xướng qua gateway** (không phải KG service-to-service write — giữ nguyên tắc M1). Tái dùng route adopt-kind/create-attribute của glossary đã có. |
| D2 | Refactor extraction SDK (`loreweave_extraction`) — **MULTI-SERVICE** | Rủi ro cao nhất + **blast-radius 3 service** (verify 2026-06-20): SDK consume bởi knowledge-service **+ worker-ai + translation-service**, KHÔNG isolated. `Literal`→dynamic, prompt tĩnh→động. **Backward-compat bắt buộc:** `schema=None` → hành vi tĩnh hôm nay y hệt (worker-ai/translation không đổi 1 dòng). Golden-set baseline phải cover **cả worker-ai path**, không chỉ knowledge. (Chi tiết: build plan lane LB.) |
| D3 | Provider/model invariant | Extraction qua provider-registry; không hardcode model. Không vi phạm khi build prompt động. |
| D4 | Tenancy | Schema mới phải theo luật user-boundary (system admin-only, scope-keyed UNIQUE). Thêm deny-test cross-tenant (bài học e0-grant-mapping). |
| D5 | Neo4j enforcement | Validate predicate theo schema phải đi qua write path tập trung (relations repo) — tránh bypass. |
| D6 | MCP-first | Nếu graph-schema authoring/extraction có logic *agentic* (LLM quyết định) → phải là MCP tool qua ai-gateway, không HTTP raw-prompt (CLAUDE.md MCP-first). Extraction *pipeline* (không agentic) thì exempt. |

---

## 7. Milestones (đề xuất, cho plan session sau)

| MS | Tên | Size | Phụ thuộc |
|---|---|---|---|
| K1 | `kg_*` schema + seed `general` + `xianxia-harem` | M | — |
| K2 | Glossary internal ontology read + KG client | S | D1 |
| K3 | Resolution + fail-soft validation | M | K1, K2 |
| K4 | Extraction động (prompt + validation từ schema) | XL | K3, D2 |
| K5 | Adopt + Sync + per-tier CRUD (admin placeholder) | L | K3 |
| K6 | View/Lens CRUD + scoped query/extraction | M | K5 |
| K7 | Hard enforcement + `graph_id` NULL seam | M | K4, K6 |
| K9 | Triage queue + resolution workflow (§11) + as-of-chapter read (§3.6) | L | K4, K5 |
| K8 | (Deferred) Graph partition `graph_id` thật | XL | K7 |

Toàn epic: **XL, load-bearing** (schema + tenancy + migration + extraction cross-service). Spec + plan riêng mỗi milestone; /amaw cho K4/K5 (migration + cross-service).

---

## 8. Câu hỏi mở (chốt khi PLAN)

### MUST-ANSWER trước khi DESIGN-lock (rút từ §10, không được skip)

- **M1 (≙ §10-G1, CRITICAL) — reconciliation node-kind giữa glossary↔KG.** Adopt template KG khi book glossary CHƯA có kind tương ứng thì xử sao? **CHỐT: (b) adopt-gated** — adopt fail với "hãy adopt các kind này trong glossary trước" (không cross-service write ngầm). **Refine (gap draft-01):** project **no-book** → nguồn node-kind = glossary standards của user (§3.5); adopt-gate khi blocked **deep-link** sang glossary rồi re-check (idempotent).
- **M2 (≙ §10-C4, HIGH) — seam partition.** **CHỐT:** `graph_id` đặt **trên EDGE** (node dùng chung); "view→partition" KHÔNG phải continuum mà là feature riêng.
- **M3 (≙ §10-B4, HIGH) — schema versioning + edit policy.** **CHỐT:** `schema_version` stamp lên edge/fact; schema edit **additive** (thêm type OK; rename/remove = deprecate-only). **Refine (gap draft-06):** **sync-apply đổi RULE going-forward, KHÔNG retro-recompute data** mặc định; recompute là hành động **opt-in riêng** (dry-run + count), không nằm trong sync-apply.

### Còn lại

1. **Đa-schema-active per project**: v1 chốt "một project-schema active sau merge". Có cần adopt nhiều template song song (vd xianxia-harem + một template mystery) ngay v1 không, hay để lớp 4? *(liên đới Q5 — vocab collision, §10-F2)*
2. **Free-edge policy**: schema có cho phép edge ngoài vocab (free string như hiện tại) dưới một cờ `allow_free_edges` không, hay đóng hoàn toàn theo `kg_edge_types`?
3. **Fact/state types narrative**: chốt bộ fact-type chuẩn (mục §4 mới gợi ý) — cần PO duyệt danh sách.
4. **Grant-level cho schema write trong project shared**: mirror Manage-gate của glossary? View per-user hay project-wide? (§10-D3/D4)
5. **Drive vocab dùng chung hay per-template**: `drive` seed trong `xianxia-harem`; có nên có một vocab `drive` cấp `general`/system dùng lại được không?

---

## 9. Nguyên tắc rút gọn

- **KG sở hữu graph shape; glossary sở hữu node identity.** Không nhập nhằng ownership.
- **Schema là dữ liệu, tiered, adopt-copy-down + sync** — copy mental model glossary, không copy bảng.
- **Additive tới phút chót**; `general` template = lưới an toàn cho project cũ.
- **Temporal/provenance đã có** — tận dụng, chỉ thêm enforcement theo `temporal` flag.
- **View trước, partition sau** — giải nhu cầu "graph theo bài toán" rẻ; để dành `graph_id` seam (trên EDGE).
- **Không ghi rác vào graph** — phần tử không-hợp-schema park ở triage, không vào Neo4j (§11). Resolve cross-service do **user khởi xướng**, không write ngầm.

---

## 11. Triage & resolution workflow (gap lớn nhất — draft-05)

Đây là chỗ 2 hệ tiered (glossary node-kind ↔ KG graph-schema) **va nhau hằng ngày** lúc extraction, không chỉ lúc adopt. Spec cũ thiếu hoàn toàn.

### 11.1 Nguyên tắc
- **Neo4j chỉ chứa edge/fact hợp-schema.** Validation fail-soft (K3) KHÔNG ghi phần tử lệch vào graph — **park vào `kg_triage_items`** (§3.7). Extraction không bao giờ bị block.
- **Mọi resolution là human-gated.** Assistant có thể *đề xuất* (MCP tool, follow-up), nhưng v1 do người quyết.
- **Cross-service resolution do user khởi xướng qua gateway**, không phải KG write thẳng vào glossary (giữ nguyên tắc M1 "no hidden cross-service write").

### 11.2 Loại triage + hành động resolve

| `item_type` | Tình huống | Hành động (KG-local trừ khi ghi ✦glossary) |
|---|---|---|
| `unknown_vocab_value` | drive "curiosity" ngoài vocab `drive` (closed) | **map→** giá trị có sẵn (relabel element parked) · **add→vocab** (KG schema write, bump `schema_version`) · **dismiss** |
| `unknown_edge_type` | predicate không thuộc `kg_edge_types` | **map→** edge type có sẵn · **add→schema** (KG write) · **dismiss** |
| `edge_kind_mismatch` | `LOVER_OF: character→organization` (schema: char→char) | **re-target** endpoint · **widen** target_node_kinds (KG write) · **drop edge** |
| `edge_cardinality_conflict` | mở instance #2 trên edge `single_active` | **close-previous** (đóng cái cũ) · **đổi sang multi_active** (KG write) · **dismiss** |
| `unknown_node_kind` | "bloodline" — VCTĐ §5 nên là string/edge, kind không có trong glossary | ✦**promote→glossary kind** (glossary write, user khởi xướng) · ✦**demote→attribute** (glossary write) · **map→** kind có sẵn · **dismiss** |

✦ = hand-off glossary: item chuyển `status='pending_glossary'`; user thao tác bên glossary (deep-link); khi kind/attr xuất hiện trong glossary ontology → KG re-process element parked.

### 11.3 Batch re-apply
- Mỗi triage item có `signature` (vd `drive:curiosity`). Resolve **một** item kiểu signature → **áp cho mọi item cùng signature** đang pending (vd mọi mention "curiosity" → `uncover_truth`). Tránh resolve từng dòng.

### 11.4 Endpoints
```
GET    /v1/kg/projects/{id}/triage?status=pending           # queue (group theo signature)
POST   /v1/kg/projects/{id}/triage/{signature}/resolve      # {action, params, apply_to_signature:true}
POST   /v1/kg/projects/{id}/triage/{triage_id}/dismiss
```
- Resolve thành công + (nếu cần) re-process element parked → ghi edge/fact hợp-schema vào Neo4j (qua write path tập trung, D5).
- Resolve có glossary write → trả `needs_glossary: {book_id, kinds:[...]}` để FE deep-link; item ở `pending_glossary` tới khi glossary có.

### 11.5 Build (milestone K9)
- Lane **LH** (xem build plan): bảng `kg_triage_items` (đã ở K1/§3.7), router `routers/public/triage.py`, repo `repositories/triage.py`, re-apply qua write path. Phụ thuộc K4 (extraction park) + K5 (glossary client/hand-off).
- VERIFY: park đúng từng item_type; batch re-apply theo signature; cross-service hand-off (mock glossary) → pending_glossary → re-process; tenancy deny-test.

---

## 10. Edge cases, risks & resolutions (đánh giá đối kháng 2026-06-20)

Mô phỏng kịch bản + edge case trên mô hình §2–§5. Mức độ: 🔴 Critical · 🟠 High · 🟡 Med · 🟢 Low. Đã fold quyết định vào §2–§8.

### 🔴 G1 — CRITICAL: hai hệ tiered độc lập phải đồng thuận node-kind
Node kind sống ở **glossary** (adopt ở tier **book**, `book_id`, dùng chung giữa user). Graph schema sống ở **KG** (adopt ở tier **project**, `(user_id,project_id)`, per-user). Edge tham chiếu kind qua code.
**Kịch bản:** book glossary có {character, organization, location}; user adopt `xianxia-harem` (edge `COMPREHENDS: character→concept`) nhưng book CHƯA adopt `concept`. → edge không anchor được (glossary là SSOT của node identity, không biết `concept` cho book này).
**Quyết định (M1):** chốt **(b) adopt-gated** — adopt template KG fail sớm với thông điệp "adopt các kind X,Y trong glossary trước"; không cross-service write ngầm; phơi dependency cho user. (a=auto-adopt kind sang glossary — cần internal route write, coupling cao; c=advisory, kind thiếu→`unknown`/triage — mất giá trị.) Cần glossary internal ontology read (D1) để KG kiểm tra lúc adopt.

### 🔴 C4 — HIGH: "view → partition" KHÔNG phải continuum
**Kịch bản:** node `character` nằm trong CẢ *Relationship view* lẫn *Cultivation view* (view chồng lấn — cùng node, khác bộ edge). Nếu `graph_id` là khoá partition **trên node**, node không thể thuộc 2 partition.
→ view (filter edge chồng lấn) và partition (sở hữu node rời) là **2 hình khác nhau**.
**Quyết định:** seam `graph_id` đặt **trên EDGE** (node dùng chung); bỏ tuyên bố "promotion mượt" — partition là feature riêng. Đã sửa §2 lớp 4, §3.4, §5-K7.

### 🟠 B4 — HIGH: schema versioning vs data đã extract
**Kịch bản:** extract 50 chương dưới `xianxia-harem`, rồi user sửa schema (đổi tên edge / bỏ fact-type). Edge cũ validate theo schema CŨ; temporal stamp `chapter_id` nhưng KHÔNG có `schema_version`.
**Quyết định (M3):** thêm `schema_version` (§3.1), stamp lên edge/fact lúc write (§3.4). Edit policy **additive**: thêm type OK; rename/remove = deprecate-only hoặc migration tường minh. (Bài học G4 glossary: schema-change-vs-data là ổ data-loss.)

### 🟠 A3/A4 — MED: sync cho schema dạng CÂY + deprecate-with-data
Graph schema là cây (schema→edge/fact/vocab→vocab_value); glossary sync vốn per-row bảng phẳng.
**Kịch bản A3:** admin thêm `SWORN_SIBLING_OF` + sửa mô tả `LOVER_OF` → diff phải báo *added type* + *modified type* (+ *added vocab_value* nếu có); `keep_mine`/`take_theirs` áp **per-node-of-tree**.
**Kịch bản A4:** admin XOÁ một edge-type project đang có data Neo4j → `deprecated_at`, nhưng data edge vẫn còn (orphan so với schema).
**Quyết định:** sync diff/apply ở **granularity cây**; **deprecate-don't-delete** type-có-data (vẫn query được, không tạo mới được; view trỏ tới nó bị flag).

### 🟡 C3 — MED: extraction theo view là vô nghĩa
Scope **query** theo view OK (read filter). Scope **extraction** theo view sai: extraction discover từ text, lọc theo view sẽ bỏ sót entity chỉ hiện qua edge ngoài view + băm 1 pass thành N.
**Quyết định:** **view = READ-only lens; extraction LUÔN chạy whole resolved schema.** Đã sửa §2 lớp 3, §3.3.

### 🟡 B1 — MED: prompt token budget tỉ lệ kích thước schema
Prompt động nhúng 18 edge + 16 drive + node kind + fact type mỗi call — ngược lại chính mục tiêu token economy của VCTĐ §3.
**Quyết định:** chiếu **projection schema-cho-extraction** (chỉ phần extraction cần), soft cap + `log()` khi truncate. Đưa vào K4.

### 🟡 F1 — MED: chính sách đóng temporal edge
**Kịch bản:** main đi revenge→seek_dao→transcendence. Mở `PURSUES→seek_dao` có TỰ ĐÓNG `PURSUES→revenge` không? Hay nhân vật pursue nhiều drive đồng thời (thực tế: đa số có nhiều, một trội)?
**Quyết định:** thêm `cardinality` (`single_active`/`multi_active`) vào `kg_edge_types` (§3.2). `single_active`→write mới tự đóng cái cũ; `PURSUES` để `multi_active`.

### 🟢 LOW
- **B2 — partial-batch validation:** edge vi phạm ở K7 → **drop-and-triage per-edge**, không fail cả batch. (đã ghi §5-K7)
- **D3/D4 — grant & view ownership trong project shared:** schema write mirror **Manage-gate** glossary; view **per-user** trong project (UNIQUE project+user+code, §3.3). Chốt ở Q4.
- **A1 — materialize project schema:** no-adopt→edit `general` ⇒ **copy-on-write lazy** tạo row scope=project lúc edit đầu tiên.
- **F2 — vocab collision đa-template:** Q1 (multi-template) + Q5 (shared drive vocab) KHÔNG độc lập — chốt cùng nhau.

### Giữ vững (không chỉ teardown)
- **Additive-first + `general` fallback** sống sót mọi kịch bản migration — project cũ không đổi tới khi tự adopt.
- **Tenancy** chắc: scope-keyed UNIQUE + K11.4 query-guard sẵn → bảng tier mới thừa hưởng isolation đã chứng minh.
- **Tái dùng temporal/provenance** đúng đòn bẩy — F1 là gap *chính sách*, không phải thiếu cơ chế.
- **Ownership split** (KG=shape, glossary=identity) sạch, và chính nó biến G1 thành cái seam-cần-làm-đúng thay vì chỗ mập mờ.
