# Context Management Architecture — Aider

> Smart-scan `D:\Works\source\context-management\aider` — tập trung `aider/repomap.py`, `aider/coders/base_coder.py`, `aider/history.py`, `aider/models.py`, `aider/sendchat.py`. Repo Python nhỏ hơn nhiều so với Continue/Zed nên scan sâu hơn một chút. Aider nổi tiếng vì **không dùng vector RAG** — dùng "Repo Map" (tree-sitter + PageRank) làm cơ chế thay thế.

---

## 1. Prompt/message assembly per turn

`format_chat_chunks()` (`aider/coders/base_coder.py:1226`) dựng dataclass `ChatChunks` (`chat_chunks.py:6`), `format_messages()` (`base_coder.py:1333`) là wrapper mỏng thêm header prompt-caching. `ChatChunks.all_messages()` (`chat_chunks.py:16-26`) cố định thứ tự:

```
system
+ examples
+ readonly_files
+ repo            # repo-map, giả lập thành 1 cặp trao đổi user/assistant
+ done            # lịch sử hội thoại trước đó (hoặc bản tóm tắt)
+ chat_files      # nội dung ĐẦY ĐỦ các file đã add vào chat
+ cur             # message user của turn hiện tại (+ assistant đang generate dở)
+ reminder        # system_reminder, thêm nếu còn chỗ
```

- System prompt: `fmt_system_prompt(gpt_prompts.main_system)` + tùy chọn `system_prompt_prefix`/`system_reminder`.
- Repo-map được inject như **1 cặp trao đổi giả**: `user: <repo map text>` / `assistant: "Ok, I won't try and edit those files without asking first."` (`get_repo_messages`, `base_coder.py:750-761`).
- File read-only và file chat (editable) mỗi loại cũng là 1 cặp trao đổi giả riêng.
- Lịch sử (`done`) là `self.done_messages`, đổ vào bởi `move_back_cur_messages` mỗi khi 1 reply hoàn tất — nguyên văn hoặc (nếu trigger) đã được LLM tóm tắt.
- Reminder chỉ thêm nếu `total_tokens < max_input_tokens`.

Trước khi gửi, `check_tokens()` (`1396-1417`) ước lượng `main_model.token_count(messages)` so với `max_input_tokens` và **hỏi user xác nhận** nếu đã vượt — **không tự cắt gì cả**.

## 2. Cơ chế Repo Map (`aider/repomap.py`) — đóng góp đặc trưng nhất của Aider

**Trích xuất tag** — `get_tags_raw` (`repomap.py:279-363`) parse mỗi file bằng tree-sitter với file query `*-tags.scm` theo ngôn ngữ, sinh ra `Tag(rel_fname, fname, name, kind, line)` cho định nghĩa (`def`) và tham chiếu (`ref`). Tag được cache trên đĩa (SQLite `diskcache`, key theo mtime).

**Xếp hạng bằng graph + PageRank** — `get_ranked_tags` (`365-574`) dựng `networkx.MultiDiGraph`: node là file, cạnh `referencer_file -> definer_file` theo từng định danh, trọng số:
- `mul = 1.0`, `×10` nếu định danh được nhắc thẳng trong message user, `×10` nếu "trông giống" định danh thật (snake/kebab/camel case, dài ≥8), `×0.1` nếu bắt đầu bằng `_`, `×0.1` nếu định danh được định nghĩa ở >5 file.
- **`×50` thêm nếu file tham chiếu đang mở trong chat** — file đã mở trở thành "booster" mạnh cho những gì nó tham chiếu tới, dù bản thân nó không xuất hiện trong output.
- Số lần tham chiếu được giảm dịu bằng `sqrt(num_refs)` để 1 file nhắc `foo` 100 lần không lấn át file chỉ nhắc 1 lần.
- **Personalized PageRank**: `nx.pagerank(G, weight="weight", personalization=..., dangling=...)` — personalization cho trọng số ưu tiên thêm (`100/num_files`) cho file đang mở trong chat, được nhắc thẳng, hoặc tên/path khớp định danh được nhắc.
- Rank phân phối lại từ mỗi node nguồn qua các cạnh ra tỷ lệ theo trọng số cạnh, gộp theo cặp `(file định nghĩa, định danh)`, sort giảm dần — tức là **xếp hạng centrality toàn cục của graph**, không phải similarity theo từng query như embedding.

**Vòng lặp fit ngân sách token** — `get_ranked_tags_map_uncached` (`629-706`) làm **binary search trên số lượng ranked tag đưa vào**:
```python
middle = min(int(max_map_tokens // 25), num_tags)   # ước lượng khởi điểm ~25 token/tag
while lower_bound <= upper_bound:
    tree = self.to_tree(ranked_tags[:middle], chat_rel_fnames)
    num_tokens = self.token_count(tree)
    pct_err = abs(num_tokens - max_map_tokens) / max_map_tokens
    if (num_tokens <= max_map_tokens and num_tokens > best_tree_tokens) or pct_err < 0.15:
        best_tree = tree; best_tree_tokens = num_tokens
        if pct_err < 0.15: break
    ...
```
— binary search cổ điển, hội tụ trong 15% so với token mục tiêu, render tree ứng viên bằng `grep_ast.TreeContext` (pretty-print "dòng quan tâm" kèm ngữ cảnh scope xung quanh), cắt mọi dòng về tối đa 100 ký tự để chống dòng minified/khổng lồ. `token_count` tự nó dùng **ước lượng sampling** (cứ N dòng đếm 1, ngoại suy) thay vì tokenize toàn bộ, để nhanh.

**Co giãn thích nghi theo ngân sách khả dụng**: `get_repo_map` (`103-167`) — khi chat KHÔNG có file nào, map được **phóng to**: `target = min(max_map_tokens * map_mul_no_files, max_context_window - 4096)` (multiplier mặc định 2 qua CLI, hoặc 8 mặc định class). Cache toàn bộ map đã render, refresh theo `--map-refresh` (`auto` bỏ qua tính lại trừ khi lần tính trước >1s). Gặp `RecursionError` (repo khổng lồ/bệnh lý) → tắt hẳn map (`max_map_tokens = 0`).

## 3. Token budgeting (`models.py`)

Aider **không có** 1 bộ chia ngân sách hợp nhất — mỗi subsystem tự tính phần của mình từ `max_input_tokens` (lấy từ DB model của litellm):

- Token repo-map: `Model.get_repo_map_tokens()` = `max_input_tokens/8`, kẹp `[1024, 4096]`.
- Ngưỡng tóm tắt lịch sử: `Model.max_chat_history_tokens` = `max_input_tokens/16`, kẹp `[1024, 8192]`.
- Kiểm tra cứng toàn cục: `check_tokens()` so token của TOÀN BỘ message đã ghép với `max_input_tokens`, cảnh báo/hỏi tiếp tục nếu vượt — **chỉ mang tính khuyến cáo, không tự cắt**.
- Không trừ riêng dòng "reserve cho output token" khỏi ngân sách input (chỉ xét sau khi xảy ra lỗi, xem mục 6); `ChatSummary.summarize_real` tự reserve 512 token khỏi `max_input_tokens` cho margin an toàn khi tự tóm tắt đệ quy.

Tóm lại: repo-map ≈ 1/8 context (tối đa 4KB), lịch sử trước khi bị tóm tắt ≈ 1/16 context (tối đa 8KB), nội dung file + message hiện tại lấy **phần còn lại, không giới hạn** — nếu không vừa, user được cảnh báo chứ không bị tự động cắt.

## 4. Tóm tắt/nén lịch sử chat (`aider/history.py`)

`ChatSummary` (`history.py:7-123`) trigger từ `summarize_start()`, gọi mỗi turn từ `move_back_cur_messages()` ngay sau khi message của turn hiện tại được append vào `done_messages`. Chỉ thực sự chạy nếu `summarizer.too_big(done_messages)` — token count của `done_messages` vượt `max_chat_history_tokens`. Chạy trên **background thread** (`summarize_worker`), join/apply lười biếng ở đầu `format_chat_chunks()` lần **kế tiếp** — không bao giờ block reply hiện tại.

Thuật toán (`summarize_real`, `history.py:33-96`):
- Nếu tổng ≤ `max_tokens` ở depth 0 → giữ nguyên văn.
- Ngược lại chia head/tail: duyệt ngược cộng dồn token tới `half_max_tokens`, chốt điểm cắt sao cho kết thúc ở message `assistant` — **tail (message gần nhất) giữ nguyên văn**.
- Nếu điểm cắt quá sớm (≤4 message) hoặc depth đệ quy >3 → gộp hết bằng `summarize_all`.
- Head được cap lại `model_max_input_tokens - 512` rồi đưa cho `summarize_all`, gửi cho LLM với `prompts.summarize` làm system prompt, trả về 1 message role `user` duy nhất tiền tố `prompts.summary_prefix` — **lời gọi tóm tắt dùng chính model (yếu) đang chat**, không phải heuristic riêng.
- Nếu `summary + tail` vẫn vượt `max_tokens` → đệ quy lại (`depth+1`) với cùng quy trình chia/tóm tắt.

Pattern: turn gần đây giữ nguyên văn, turn cũ hơn gộp thành 1 "recap" tổng hợp, nén đệ quy tiếp nếu vẫn còn lớn.

## 5. Chiến lược đưa nội dung file vào

- **Không chunk/truncate file trong chat.** `get_abs_fnames_content` đọc **toàn bộ** file, `get_files_content` bọc full text mỗi file trong code block kèm path — luôn 100% file, bất kể kích thước. File không đọc được thì bị âm thầm bỏ khỏi chat kèm cảnh báo.
- File read-only cũng full-content, chỉ khác prefix/reply pair để model biết không được sửa.
- **Tương tác với repo-map — khử trùng lặp tường minh, nhiều lớp:**
  - `get_repo_map()` (`base_coder.py:709-748`) tính `chat_files = abs_fnames ∪ (abs_read_only_fnames ∩ repo_files)`, chỉ đưa `other_files = all_repo_files - chat_files` vào `RepoMap.get_repo_map` — file đã full trong chat thậm chí không phải ứng viên của map.
  - Lớp bảo hiểm kép trong `repomap.py`: `get_ranked_tags` bỏ qua hẳn việc sinh tag entry cho `chat_rel_fnames`, `to_tree` cũng bỏ qua tag nào thuộc file đang trong chat.
  - Nhưng file đang chat **không bị loại khỏi ranking graph** — theo mục 2, cạnh xuất phát từ file-trong-chat được boost `×50`, nên file đang mở vẫn mạnh mẽ đẩy các file KHÁC mà nó tham chiếu tới lên map, dù bản thân nó bị loại khỏi output render.

## 6. Phát hiện tràn context / hành vi retry

Có 1 vòng lặp auto-retry-với-context-sửa-đổi tổng quát (`self.reflected_message`), nhưng chỉ dùng cho: tự thêm file LLM nhắc tới nhưng chưa có trong chat, đề nghị tự sửa lỗi lint, test fail, và lỗi parse edit-format. **Không dùng cho tràn context window.**

Với lỗi tràn context thật sự từ API: vòng lặp retry của `send_message` bắt riêng `ContextWindowExceededError` từ litellm → `exhausted = True; break` — **không có biện pháp giảm nhẹ tự động nào** (không drop repo-map, không cắt lịch sử, không chia nhỏ request, không retry). Tương tự `FinishReasonLength` (chạm giới hạn token OUTPUT) thì hoặc cứu bằng prefill-continuation (nếu model hỗ trợ), hoặc cũng chỉ đánh dấu `exhausted = True`. Sau vòng lặp, `show_exhausted_error()` tính lại ước lượng token input/output/total so với giới hạn model và in ra chẩn đoán + gợi ý khắc phục thủ công (`/tokens`, `/drop`, `/clear`, tách file) — **thuần thông tin**, không có gì thích nghi tự động xảy ra. Aider phát hiện tràn nhưng giao việc sửa lại cho người dùng thay vì tự chữa.

---

## Ý tưởng đáng chú ý (so với vector-RAG / Continue-style embedding+chunk / Zed-style BM25)

1. **Không vector index, không embedding, không similarity search nào cả.** Repo-map được dựng thuần từ graph phân tích tĩnh (def/ref tree-sitter) + PageRank — 1 cấu trúc toàn cục được cache gần-như-một-lần, không phải tra cứu nearest-neighbor theo từng query.
2. **Xếp hạng centrality toàn cục của graph, cá nhân hóa theo từng turn.** Thay vì hỏi "cái gì semantically giống câu hỏi này", Aider hỏi "code nào quan trọng về mặt cấu trúc trong toàn repo, thiên vị về cái đang mở/được nhắc" qua personalized PageRank với heuristic chất lượng định danh tinh chỉnh tay (boost snake/camelCase, phạt `_private`, phạt fan-out cao, giảm dịu bằng `sqrt`).
3. **Bộ fit ngân sách token bằng binary search, không phải top-K cố định.** Thay vì chọn "top N chunk vừa ngân sách", nó binary-search số lượng ranked tag để đưa vào, đối chiếu với đếm token (ước lượng sampling) thật, hội tụ trong 15% ngân sách — đánh đổi tối ưu tuyệt đối lấy tốc độ.
4. **File đang mở trong chat chủ động định hình map thay vì chỉ là nội dung retrieve riêng.** Một file mở không chỉ "được đưa full-text vào" — cạnh tham chiếu RA của nó được boost 50x trong ranking graph, nên mở 1 file sẽ kéo *dependency* của nó vào map, còn bản thân file bị loại khỏi output để tránh trùng lặp.
5. **Quản lý context gần như hoàn toàn phản ứng/thủ công, không phải compiler/planner.** Không có 1 bộ phân bổ ngân sách hợp nhất giữa repo-map/history/file/output — mỗi phần tự suy ra 1 lát cắt từ `max_input_tokens` (1/8, 1/16...), tràn ngân sách chỉ được chẩn đoán SAU khi xảy ra bằng heuristic fudge-factor, và khắc phục giao lại cho user (`/drop`, `/clear`) thay vì tự động — cách tiếp cận nén đơn giản có chủ đích (1 lời gọi summarizer LLM), không phải một planner/compiler có cấu trúc.
