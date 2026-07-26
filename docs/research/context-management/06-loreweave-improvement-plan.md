# Đề xuất cải thiện Context Management — LoreWeave

> Tổng hợp hành động từ `01-loreweave-context-audit.md` (đối chiếu ngành) + `02`–`05` (kiến trúc Continue/Zed/Aider/Cline). Kết luận của đợt khảo sát: phần lớn kỹ thuật của 4 tool kia LoreWeave đã có bản tương đương hoặc tốt hơn — chỉ 2 ý tưởng thật sự đáng nhập vào, còn lại là tự hoàn thiện phần đã tự nhận diện. File này là kế hoạch hành động cụ thể, không lặp lại phần lý luận đã có ở file 01.

---

## Nguyên tắc chỉ đạo

1. **Không thay thế, chỉ bổ sung.** Không có đề xuất nào ở đây đòi thay kiến trúc nền (Budget Law / Compiler ladder / Planner / KG RAG) — tất cả là phần thêm vào chỗ trống đã xác định, dùng lại primitive đã có trong repo.
2. **Ưu tiên lắp ráp hơn phát minh.** Đề xuất #1 và #2 dưới đây chỉ nối các hàm đã tồn tại (`find_relations_2hop`, `get_project_subgraph`, `tool_result_content()`) theo cách mới, không viết thuật toán mới.
3. **Giữ nguyên ranh giới KG RAG vs ATS.** Không đề xuất nào ở đây đề nghị bỏ vector search để thay bằng graph-centrality thuần túy (kiểu Aider) — tiểu thuyết cần semantic match (alias, đại từ, bản dịch) mà graph/lexical không thay được. Xem mục "Không nên làm" cuối file.

---

## R1 — [Ưu tiên cao nhất] 1-hop graph expansion + boost theo phạm vi làm việc hiện tại

**Vấn đề:** `passages.py` chỉ làm vector search + hub/recency penalty + MMR — không bước nào mở rộng qua graph, dù `relations.py` đã có `find_relations_2hop` và `get_project_subgraph` (n-hop ego-expansion, capped theo từng hop). Đây là gap tự nhận (`AW-2`) đã nêu ở file 01.

**Nguồn cảm hứng:**
- *GraphRAG/HippoRAG* (đã trích dẫn sẵn trong code): phần "graph" thật của 2 paper này chưa chạy, chỉ mới lấy ý tưởng anchor-weighting.
- *Aider* (`04-aider-context-architecture.md`, mục 2): file đang mở trong chat được boost `×50` lên các entity nó tham chiếu trong ranking graph, dù bản thân file không nằm trong output — đây là cơ chế "ưu tiên theo phạm vi làm việc hiện tại" (working scope), không phải chỉ recency.

**Đề xuất cụ thể (2 phần, làm cùng lúc vì chung 1 điểm sửa):**

| Phần | Việc làm | File/hàm liên quan |
|---|---|---|
| 1a. Graph expansion | Thêm bước sau MMR trong `_apply_post_filters`/pipeline: với top-K entity/passage hit, gọi 1-hop lookup (rút gọn từ `find_relations_2hop`, giới hạn 1 hop) lấy các quan hệ trực tiếp — cap số quan hệ/anchor, cap ngân sách token (vài trăm token, không phải toàn subgraph) | `services/knowledge-service/app/context/selectors/passages.py`, `db/neo4j_repos/relations.py` |
| 1b. Working-scope boost | Khi `editor_context.book_id/chapter_id` có mặt (đã thread sẵn theo ARCH-1 C6), boost `anchor_score`/hub_penalty của entity thuộc scene/chapter đang mở — tương tự Aider boost file-đang-mở lên entity nó tham chiếu | `_HUB_PENALTY`/scoring trong `passages.py`, `anchor_score` trong `entities.py` |

**Vì sao gộp chung:** cả hai đều trả lời câu hỏi "context nào liên quan tới THỨ ĐANG LÀM ngay bây giờ, không chỉ liên quan tới CÂU HỎI vừa gõ" — 1a mở rộng theo quan hệ đồ thị, 1b mở rộng theo phạm vi biên tập đang mở. Sửa cùng 1 lượt tránh phải回 lại pipeline 2 lần.

**Impact:** Cao — đúng lớp câu hỏi quan hệ đa bước ("mối thù gia tộc X-Y từ đâu") mà vector-only yếu nhất, và đúng lớp câu hỏi "nhân vật trong chương này liên quan gì" mà editor cần nhất.
**Effort:** Thấp–vừa — mọi mảnh ghép đã có sẵn.

---

## R2 — [Rẻ, nên làm sớm] Trần cứng vô điều kiện cho mọi tool-result (defense-in-depth)

**Vấn đề:** L3 lint (`tool_result_content()`) đảm bảo `ensure_ascii=False` + drop-None; L1/L2 (`apply_response_contract`) đảm bảo `detail`/`fields`/`limit` tồn tại — nhưng cả hai đều **phụ thuộc tool có tuân thủ đúng contract hay không**. Chưa có 1 trần cứng, vô điều kiện, áp dụng bất kể tool mới/lỗi có implement đúng T1 refactor hay không. Đây chính là lớp rủi ro đã gây ra vụ 146K ban đầu (một tool dump toàn bộ outline) — T1 đã vá tool đó cụ thể, nhưng chưa có lưới an toàn chung cho tool tiếp theo mắc lỗi tương tự.

**Nguồn cảm hứng:** *Cline* (`05-cline-context-architecture.md`, mục 1 & "Ý tưởng đáng chú ý" #1) — `MessageBuilder.buildForApi()` chạy **mọi turn, độc lập với compaction có kích hoạt hay không**: cap tool_result 8.000 ký tự (cắt giữa), cap assistant text 200k ký tự, và ngân sách byte tổng 6MB cho cả transcript như van an toàn cuối. Đây là lớp phòng thủ thứ 2 mà LoreWeave hiện chưa có — L1/L2/L3 là "hợp đồng", không phải "van an toàn vô điều kiện".

**Đề xuất cụ thể:** thêm vào `tool_result_content()` (`app/services/tool_result_wire.py`) 1 bước cắt giữa (middle-truncation, giữ đầu+cuối) vô điều kiện nếu payload sau `json.dumps` vượt 1 ngưỡng cứng (vd 8–15K ký tự tùy đo thực tế), kèm counter tổng byte/turn để cảnh báo nếu nhiều tool cộng dồn vượt 1 trần lớn hơn. Đặt đúng ở điểm funnel hiện có (đã dùng chung cho `stream_service.py`, `voice_stream_service.py`, `subagent_runtime.py`) nên không cần sửa 3 chỗ.

**Impact:** Vừa (giá trị bảo hiểm — chặn class lỗi 146K tái diễn từ tool mới, không phải tool đã biết).
**Effort:** Thấp.

---

## R3 — §13 CI meta-check (đã có trong audit gốc, nhắc lại vì rẻ và cấp thiết)

Script parse checklist §11a của `context-budget-law.md`, fail build nếu item chưa có test proof-bound. Bạn đã bị chính hiện tượng doc/code drift "cắn" một lần (`context-inspector-gui.md` nói thiếu trong khi code đã ship). Không cần chi tiết thêm — xem file 01 mục 02/05.

**Impact:** Vừa. **Effort:** Thấp.

---

## R4 — Thử nghiệm pull-mode với model hiện có

`retrieval_mode` khóa cứng `"prepend"` cho mọi model (`config.py:133`); D1 (retrieval-mode-by-tier) hoãn tới "future strong-model capability". Nhưng các tool pull-mode (`story_search`, `memory_search`, `kg_graph_query`, `kg_entity_edge_timeline`...) **đã tồn tại** từ T1 Family-B. Đề xuất: pilot với model reasoning đang chạy (Qwen 3.5/3.6) — prepend 1 "stub" rất nhỏ (glossary badge/one-liner), để model tự pull chi tiết qua tool khi cần, thay vì chờ "model mạnh hơn tương lai" mà không rõ mốc nào là "đủ mạnh".

Đây cũng biến `retrieval_mode` từ config phẳng thành 1 quyết định thật sự do Planner sở hữu — đúng tinh thần D8 ("Planner owns the SEED") mà spec đã đặt ra nhưng chưa implement.

**Impact:** Vừa-cao (tiết kiệm token không cần hạ tầng mới). **Effort:** Vừa — cần 1 kế hoạch đo A/B giống cách bạn đã đo T5/T2.

---

## R5 — Làm rõ ai phủ câu hỏi "bức tranh lớn"

Xác nhận tường minh: `story_state`/L0-L1 summary có trả lời được "tóm tắt arc nhân vật X tới giờ", "phe phái chính trong sách" hay không. Nếu xác nhận là KHÔNG (khả năng cao, vì `passages.py` scoped theo entity/passage, không theo cluster chủ đề), cân nhắc 1 lớp "theme/faction cluster summary" nhẹ — kiểu community-summary của GraphRAG — nhưng tính **offline theo từng lần extract lớn**, không phải mỗi turn, để không đụng vào ngân sách token per-turn đang được quản lý chặt.

**Impact:** Vừa (chờ xác nhận có phải gap thật không). **Effort:** Vừa-cao.

---

## R6 — Đo lại T5 trên sách extract giàu

Việc còn treo, không mới: chờ `D-EVAL-BOOK` gap được giải quyết (1 sách qua full pipeline extraction) rồi đo lại tiết kiệm của T5 intent-gate. Kết luận "T5 ~0% tiết kiệm" hiện chỉ đúng trên sách thin.

**Impact:** Thấp (tới khi đo). **Effort:** Thấp — cơ hội, không cấp thiết.

---

## Thứ tự triển khai đề xuất

1. **R2** (trần cứng) — 1 điểm sửa, rủi ro thấp, làm ngay tuần này.
2. **R1** (graph expansion + working-scope boost) — impact cao nhất, làm cùng lúc vì chung pipeline `passages.py`.
3. **R3** (CI meta-check) — song song với R1, không phụ thuộc.
4. **R4** (pilot pull-mode) — sau khi R1 ổn định, vì cần đo A/B tương tự cách đã làm với T2/T5.
5. **R5** (global-query) — chạy song song như nghiên cứu, không chặn các mục khác.
6. **R6** (đo lại T5) — bất cứ khi nào có sách extract giàu, không cần lên lịch riêng.

---

## Không nên làm — dù các tool kia có làm

| Kỹ thuật | Tool | Vì sao KHÔNG áp dụng cho LoreWeave |
|---|---|---|
| Bỏ vector RAG, chỉ dùng graph-centrality (PageRank) thuần | Aider | Tiểu thuyết cần semantic match cho alias/đại từ/biến thể dịch thuật (Việt/Trung) mà graph/lexical không thay được — đây chính là lý do bạn chọn KG RAG thay ATS ngay từ đầu. Chỉ lấy phần *personalization* (R1b), không lấy phần "bỏ vector". |
| Model tự ghi vào core memory (`core_memory_append`) | MemGPT/Letta | `story_state` deterministic + KG extraction pipeline là nguồn sự thật có cấu trúc, đáng tin hơn self-reported writes vốn dễ lỗi/lossy. Đã nêu ở file 01 mục 03. |
| Rule-file theo glob path + mention system tái tổ chức theo tag | Continue, Zed | Domain khác hẳn (code path/symbol vs entity tiểu thuyết) — không có tương đương tự nhiên trong ngữ cảnh viết văn. |
| Kế toán token hoàn toàn phản ứng (post-hoc, dựa vào usage API) | Zed | LoreWeave cần quyết định **trước khi gọi** có nên pull grounding hay không (T5 gate) và target ngân sách task-elastic (Planner) — không thể chờ biết usage sau response như Zed vì đó là quyết định *trước* request, không phải *sau*. Đừng thoái lui về reactive-only. |
| Compaction hoàn toàn thủ công, không có Planner/Law tự động | Aider | LoreWeave đã tự động hóa tốt hơn (Planner + compaction + C_persist đã đo A/B) — đây là hướng bạn đã vượt qua, không phải học lại. |
