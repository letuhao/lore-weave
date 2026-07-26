# Context Engineering Audit — LoreWeave (lore-weave-mvp)

> Đối chiếu Context Budget Law / Context Compiler (T0–T6) / Planner / KG RAG của `lore-weave-mvp` với các pattern đã kiểm chứng trong ngành (Claude Code, MemGPT/Letta, GraphRAG, HippoRAG). Không scan các repo đã clone trong workspace này — dựa trên kiến thức nền + đọc trực tiếp code/spec của lore-weave-mvp.
>
> **Repo:** `D:\Works\source\lore-weave-mvp` · **Ngày:** 2026-07-04 · **Phạm vi:** chat-service, knowledge-service, `sdks/python/loreweave_context`

**Chú giải trạng thái dùng trong báo cáo:**
- 🟢 Ngang tầm / vượt ngành
- 🟡 Có cơ chế, chưa nối hoặc chưa đo
- 🔴 Khoảng trống thật
- ⚪ Chủ động không làm — đúng đắn

---

## 00 — Kết luận nhanh

**Mức độ trưởng thành: cao hơn bạn nghĩ ở tầng budget/compiler, đòn bẩy còn lại nằm ở tầng KG retrieval.**

"Context Budget Law" không phải một ý tưởng non — cách bạn chia 6 quy tắc theo *khả năng cưỡng chế* (lint cứng / contract-snapshot / behavior đo bằng gate) là một kỷ luật kỹ thuật mà phần lớn "context rules" trong các tool khác chỉ nằm trong prompt hoặc wiki, không ai enforce.

Đọc trực tiếp `context-budget-law.md`, toàn bộ ladder T0→T6, `plan.py`, `compaction.py`, `entity_presence.py`, `subagent_runtime.py`, tầng KG RAG (`passages.py`, `entities.py`, `pass2_orchestrator.py`), và `stream_service.py` (nơi mọi thứ được lắp ráp mỗi turn), bức tranh chung là:

**Tầng điều phối context (budget/compiler/planner/compaction) đã ở mức ngang hoặc vượt các kỹ thuật phổ biến trong Claude Code và các framework memory-tiered (MemGPT/Letta).** Khoảng trống thật sự không nằm ở "quản lý ngân sách token" — nó nằm ở **tầng KG RAG chính nó**: retrieval tự động (eager grounding) hiện vẫn là "vector search có gắn nhãn graph", trong khi các primitive graph traversal thật (2-hop, n-hop ego-expansion) đã tồn tại trong code nhưng chưa được nối vào đường đi tự động — khoảng trống bạn đã tự phát hiện (`AW-2`) mà chưa đóng.

---

## 01 — Ngang tầm hoặc vượt ngành

| Thành phần của bạn | Đối chứng trong ngành | Đánh giá |
|---|---|---|
| **stable/volatile context split** (`KnowledgeContext.stable_context` / `volatile_context`, K18.9) | Anthropic prompt-caching cache-breakpoint pattern — cách Claude Code tách phần hệ thống ổn định khỏi phần biến động mỗi turn | 🟢 Ngang tầm |
| **Sub-agent isolation** (`subagent_runtime.py`: tool_scope = intersection, depth cap = 1, result cap) | Claude Code's Task/Agent tool — sandbox tool bên trong 1 sub-task, không rò context ra ngoài | 🟢 Ngang tầm, kỷ luật hơn — depth cap cứng = 1 chặn đệ quy fan-out, nhiều framework khác không ép điều này |
| **Reference-first + detail/fields/limit** (L1/L2, chốt bằng response-shape snapshot test) | Nguyên tắc "trả tóm tắt, để model tự hỏi chi tiết" mà Claude Code / Anthropic docs khuyến nghị | 🟢 Ngang tầm, có phần vượt — snapshot test chống drift là kỷ luật hiếm thấy được công khai ở nơi khác |
| **Core memory block** (`story_state`: deterministic, token-capped 1200, cadence refresh) + persisted compaction summary + `conversation_search` | MemGPT/Letta's 3-tier memory: core / archival / recall | 🟢 Ngang tầm cơ chế — khác biệt: core memory không agent-writable (xem mục 03) |
| **Deterministic breadcrumb** trước khi tóm tắt bằng LLM (số liệu/tên riêng regex-extract verbatim, dẫn đầu summary) | Hầu hết tool (kể cả `/compact` phổ biến) chỉ "model tóm tắt" thuần — lossy, variance cao | 🟢 Vượt thực hành phổ biến — bạn đã tự đo được 1/9→9/9 recall swing rồi mới thêm breadcrumb |
| **Atom-safe compaction** (không tách cặp `tool_calls`↔`role:tool`) | Yêu cầu cứng của Anthropic/OpenAI tool-calling API | 🟢 Ngang tầm — bắt buộc, không phải tùy chọn |
| **P0-5 injection neutralization** (khử prompt-injection trong context lấy từ KG/passages TRƯỚC khi ghép vào system prompt — `stream_service.py:1815-1834`) | Nguyên tắc "tool output / retrieved content = untrusted data" | 🟢 Vượt thực hành phổ biến — nhiều RAG stack KHÔNG làm bước này |
| **Two-layer entity anchoring** (`anchor_score`: glossary-anchored=1.0 vs discovered=mentions/max, trích dẫn GraphRAG/HippoRAG) | Ý tưởng anchor-weighting của GraphRAG (arXiv:2404.16130) / HippoRAG (arXiv:2405.14831) | 🟡 Đã lấy Ý TƯỞNG, chưa lấy CƠ CHẾ — xem mục 02 |

**Insight tái sử dụng được:** cách bạn phân loại 6 quy tắc của "Law" theo khả năng cưỡng chế (§6a lint thật / §6b contract-snapshot / §6c compiler-behavior đo bằng gate) — thay vì coi tất cả là lint như v1 — là nguyên tắc có thể áp dụng cho bất kỳ "context rule" nào trong tương lai: *một rule chỉ nên là lint nếu nó statically-decidable; nếu không, nó cần một test theo EFFECT, không phải theo signature.*

---

## 02 — Khoảng trống thật, xếp theo impact

### Đòn bẩy lớn nhất: graph traversal đã tồn tại nhưng chưa được dùng cho retrieval tự động

Trong `knowledge-service/app/db/neo4j_repos/relations.py` đã có `find_relations_2hop` (2-hop có predicate filter chống fan-out) và `get_project_subgraph` (n-hop ego-expansion, cap theo từng hop để tránh nổ trên hub-node) — nghĩa là bạn **đã có** phần "graph" thật của GraphRAG/HippoRAG, không chỉ trích dẫn suông.

Nhưng đường grounding tự động mỗi turn (`knowledge-service/app/context/selectors/passages.py`) chỉ làm: vector search trên `:Passage` → hub/recency penalty → MMR rerank. **Không có bước mở rộng graph nào trong pipeline này** — đúng như `ARCHITECTURE_WEAKNESSES.md` (AW-2) đã tự đặt câu hỏi mà chưa trả lời: "graph traversal có thực sự feed vào retrieval ranking không, hay Neo4j chỉ đang làm vector index?"

Với tiểu thuyết, đây chính xác là lớp câu hỏi mà vector-only RAG yếu nhất: quan hệ đa bước ("mối thù giữa gia tộc X và vương quốc Y bắt nguồn từ đâu", "ai đứng sau kẻ phản bội mà nhân vật chính tin tưởng") — vector search tìm ra đoạn văn *nhắc tên* hai thực thể, nhưng không nối được quan hệ giữa chúng nếu chúng không cùng xuất hiện trong một đoạn văn ngắn.

> **Khuyến nghị:** thêm một bước **1-hop expansion capped** ngay trong `_apply_post_filters`/pipeline của `passages.py`, seed từ top-K entity/passage hit của vector search, dùng lại `find_relations_2hop` hoặc một bản 1-hop rút gọn — giới hạn 1 hop, giới hạn degree, giữ ngân sách token nhỏ (vài trăm token cho danh sách quan hệ, không phải toàn bộ subgraph). Đây là **lắp ráp, không phải phát minh mới** — mọi mảnh ghép đã nằm trong repo.

### Các khoảng trống còn lại

| # | Khoảng trống | Vì sao đáng chú ý | Trạng thái |
|---|---|---|---|
| 2 | **Không có "global query" / theme-level summarization** kiểu Leiden-cluster summary của GraphRAG | Câu hỏi kiểu "phe phái chính trong sách là gì", "tóm tắt arc của nhân vật X tới giờ" không được top-k passage retrieval trả lời tốt. Bạn có L0/L1 summary + PlanForge arcs — cần xác nhận rõ cái nào (nếu có) đang phủ lớp câu hỏi "bức tranh lớn" này | 🔴 Cần làm rõ |
| 3 | **`retrieval_mode` khóa cứng ở "prepend" cho mọi model**, "pull" (JIT) bị hoãn tới "future strong-model capability" | Nhưng tool pull-mode (`story_search`, `memory_search`, `kg_graph_query`...) **đã tồn tại** (T1 Family-B). Cái thiếu không phải tool — là quyết định policy. Với model reasoning đang chạy (Qwen 3.5/3.6), pull-mode có thể thử ngay hôm nay | 🟡 Có cơ chế, chưa bật |
| 4 | **T5 intent-gate** đo được ~0% tiết kiệm — nhưng đo trên sách "thin" (KG mỏng); trên sách extract giàu, tiết kiệm chưa được đo (D-EVAL-BOOK gap) | Đây đúng là "unmeasured, not disproven" — đừng kết luận T5 vô dụng cho tới khi có 1 sách được extract đầy đủ để đo lại | 🟡 Chờ đo, không phải chờ sửa |
| 5 | **§13 CI meta-check không tồn tại** — checklist "Law" tự nhận cần 1 script parse §11a và fail build nếu item chưa có test proof-bound, nhưng không tìm thấy script này trong `scripts/` | Bạn đã bị chính hiện tượng này "cắn" một lần: doc `context-inspector-gui.md` nói field/trace/panel "còn thiếu" trong khi code đã ship đầy đủ (`stream_service.py:2816-2855`, FE panel đã đăng ký trong `catalog.ts:139`) | 🔴 Rẻ, nên làm |

---

## 03 — Chủ động không làm

### Một pattern ngành bạn KHÔNG cần bắt chước

**MemGPT/Letta cho phép model tự ghi vào core memory** (function `core_memory_append`/`replace`) — model tự quyết "sự kiện này quan trọng, tôi lưu lại". `story_state` của bạn thì ngược lại: deterministic, tự động re-project mỗi 5 turn hoặc khi có lore-gate/scene-change, không có tool nào để model "tự viết" vào đó.

Đây **không phải khoảng trống** — bạn giải quyết cùng bài toán bằng một cơ chế đáng tin cậy hơn: KG extraction pipeline đã là nguồn sự thật có cấu trúc (structured, versioned, có provenance), trong khi self-reported agent memory writes của MemGPT nổi tiếng dễ lỗi/lossy trong thực tế (model quên ghi, ghi sai, ghi trùng). Bạn không thiếu tính năng này — bạn có kiến trúc tốt hơn cho cùng mục tiêu. ⚪ Không nên đuổi theo pattern này chỉ vì nó phổ biến.

---

## 04 — Consumer wiring (chat-service)

### Đường đi thật mỗi turn, đọc trực tiếp từ `stream_service.py`

1. Load session + resolve reasoning effort (inline `/command` > per-message > session > platform)
2. Resolve grounding target (1 project hoặc union nhiều project — tránh salience misattribution khi multi-KG)
3. **T5 gate**: `detect_entity_presence()` quyết `grounding_needed` — thiên về mở (bias-to-include) khi nghi ngờ
4. `knowledge_client.build_context()` — luôn gọi (kể cả khi gate đóng, vẫn trả static path nhẹ), degrade êm về `mode="degraded"` ở MỌI loại lỗi (timeout/5xx/4xx/decode) — chat-service không bao giờ thấy exception từ tầng này
5. **P0-5**: khử prompt-injection trên `context`/`stable_context`/`volatile_context` lấy về — vì đây là nội dung KHÔNG đáng tin (LLM-extract hoặc user-authored fiction)
6. Resolve working-memory anchor (pinned đầu prompt cho primacy, tail ngay trước lượt user mới nhất cho recency) — cũng được neutralize injection riêng
7. Assembly lịch sử: nếu session có `compacted_before_seq`, chỉ fetch từ điểm đó + prepend `compact_summary` đã lưu làm 1 pinned message
8. `_PLANNER.plan()` — chuyển `grounding_needed` (bước 3) + config thành `task_weight`/`compact_target`
9. `compact_messages()` nếu vượt trigger
10. Emit `_trace_payload`/`_status_flags`/`raw_tokens` cho Inspector telemetry

**Nhận xét:** chuỗi này mạch lạc, không có bước nào thiếu error-handling, và nguyên tắc "dữ liệu lấy từ bên ngoài luôn là untrusted" được áp dụng nhất quán ở đúng 1 điểm vào (không rải rác nhiều nơi) — thiết kế phòng thủ tốt, không chỉ ở KG RAG mà ở toàn bộ input path.

---

## 05 — Punch list ưu tiên

| # | Việc | Impact | Effort |
|---|---|---|---|
| 1 | **1-hop graph expansion trong eager grounding path** — seed từ top-K vector hit, dùng lại `find_relations_2hop`/ego-expansion đã có. Biến "vector RAG gắn nhãn graph" thành GraphRAG-lite thật | Cao | Thấp–vừa |
| 2 | **Script CI meta-check cho §13 checklist** — parse checklist + fail build nếu thiếu test proof-bound. Bạn đã bị plan-doc nói sai trạng thái code một lần (Inspector GUI) | Vừa | Thấp |
| 3 | **Thử nghiệm pull-mode với model hiện có** — tool đã sẵn sàng (`story_search`, `kg_*`); không cần chờ "model mạnh hơn tương lai" | Vừa | Vừa |
| 4 | **Làm rõ ai phủ câu hỏi "bức tranh lớn"** — `story_state`/L1 summary có trả lời được "tóm tắt arc nhân vật X" hay không, hay là khoảng trống thật | Vừa | Cao |
| 5 | **Đo lại T5 trên một sách extract giàu** — kết luận "T5 tiết kiệm ~0%" chỉ đúng trên sách thin | Thấp (đến khi đo) | Thấp |

---

## 06 — Về lựa chọn KG RAG thay vì ATS

Quyết định dùng KG RAG thay vì retrieval kiểu lexical/tool-search (ATS — phù hợp cho code, nơi symbol match chính xác đủ dùng) là hợp lý cho tiểu thuyết: tên riêng có alias/biến thể dịch thuật (Việt/Trung), đại từ, quan hệ ngầm — thứ mà grep/lexical không nắm được. Blog nội bộ (`2026-06-10-...why-prompts-are-not-enough.md`) đã nêu đúng luận điểm này: "RAG là kỹ thuật tiêu thụ (layer 7 gọi layer 4), không phải kiến trúc nền" — và bạn đã xây SSOT + eval + graceful-degradation xung quanh nó, không chỉ "embed-chunk-search".

Một giới hạn đã tự trích dẫn và nên giữ nguyên kỳ vọng: paper KG-grounded generation (arXiv:2505.24803) nói rõ — **KG-grounding giúp plot/continuity, không giúp interiority** (nội tâm nhân vật). Điều này đã nằm trong lessons-adopted; chỉ nhắc lại để không kỳ vọng KG RAG tự giải quyết được các đoạn văn nặng nội tâm/giọng văn — giữ human-in-loop ở đó là quyết định đúng, không phải giới hạn cần "sửa".

---

## Cơ sở phân tích

Đọc trực tiếp: `docs/specs/2026-07-03-context-budget-law.md`, toàn bộ ladder T0–T6, `sdks/python/loreweave_context/*`, `services/chat-service/app/services/{stream_service,compact_service,token_budget,entity_presence,story_state,subagent_runtime}.py`, `services/knowledge-service/app/{context/selectors/passages,db/neo4j_repos/{entities,relations},extraction/{pass2_orchestrator,anchor_loader}}.py`, `docs/ARCHITECTURE_WEAKNESSES.md`, `docs/analysis/2026-06-29-ontology-extraction-bloat.md`, và 2 tài liệu prior-art/blog nội bộ.

So sánh ngành dựa trên kiến thức nền (Anthropic prompt caching, Claude Code subagent/tool design, MemGPT/Letta, GraphRAG arXiv:2404.16130, HippoRAG arXiv:2405.14831) — không scan các repo đã clone trong workspace này.
