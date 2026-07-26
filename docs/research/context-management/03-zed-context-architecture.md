# Context Management Architecture — Zed

> Smart-scan (không đọc toàn bộ repo) `D:\Works\source\context-management\zed` — tập trung vào `crates/agent/`, `crates/agent_settings/`, `crates/prompt_store/`, `crates/edit_prediction_context/`, `crates/zeta_prompt/`, `crates/context_server/`. Zed là editor native (Rust), agent AI + inline-completion "Zeta" tích hợp sẵn.

---

## 1. Agent chat context assembly

Có một struct trung tâm `Thread` (`crates/agent/src/thread.rs:1215`) sở hữu toàn bộ trạng thái hội thoại (`messages`, `project_context`, `context_server_registry`, các map token-usage...). Mỗi turn, `Thread::build_completion_request` (`thread.rs:3886`) build `LanguageModelRequest` qua `build_request_messages` → `build_request_messages_until` (`thread.rs:4115-4169`).

Thứ tự message cố định:
1. **System message** — render bằng Handlebars template `SystemPromptTemplate` (`agent/src/templates.rs:37`, template tại `system_prompt.hbs`), dựng lại **mới hoàn toàn mỗi request** từ: worktree của project, `AGENTS.md` toàn cục của user, nội dung rules-file của project, tên model, ngày, mô tả sandbox, tên các tool khả dụng, và catalog skills.
2. **History** — `extend_request_history_until` (`thread.rs:4650`), toàn bộ `Message::User/Agent/Compaction/Resume` trước đó qua `to_request()`.
3. **Pending message** (turn user đang gửi), append sau cùng.
4. **Tool definitions** gắn riêng vào `request.tools` (không interleave vào messages).

Message cuối cùng trong list được đánh dấu `cache = true` (`thread.rs:4164-4166`) — hint prompt-caching tường minh cho provider (kiểu cache-breakpoint Anthropic), đặt sau khối system+history để phần tiền tố tĩnh được cache, chỉ turn mới là "fresh".

**Gắn context (mentions):** file/directory/symbol/selection/diagnostic/thread/URL context được biểu diễn thành `UserMessageContent::Mention { uri: MentionUri, content }` (`thread.rs:267`). `UserMessage::to_request` (`thread.rs:261-460`) giữ nguyên text/link user gõ, nhưng **gom lại toàn bộ nội dung mention theo loại** thành các block tag tổng hợp (`<files>`, `<directories>`, `<symbols>`, `<selections>`, `<diffs>`, `<threads>`, `<fetched_urls>`, `<user_rules>`, `<diagnostics>`, `<skills>`, `<merge_conflicts>`) nối sau text gốc, tất cả bọc trong 1 envelope `<context>...</context>`. Đây là khái niệm "mention" để gắn context file/dir/symbol — **do user chủ động chọn** (`@file`, `@symbol`...), không phải retrieval tự động.

## 2. Token budgeting

**Không có tokenizer local/preemptive nào** cho đường chat — Zed dựa hoàn toàn vào số token-usage mà API của provider trả về SAU khi hoàn tất 1 lần completion (`TokenUsage`, lưu theo từng user-message trong `request_token_usage: HashMap<...>`, `thread.rs:1236`).

Công thức ngân sách nằm ở `auto_compact_threshold_token_count` (`thread.rs:4468-4479`) so với `model.max_token_count() - model.max_output_tokens()`. Ngưỡng cấu hình được (`AutoCompactThreshold::Percentage/TokensUsed/TokensRemaining`), mặc định **`Percentage(0.9)`** — tự động compact khi đã dùng 90% ngân sách input-token. Auto-compaction bị tắt hoàn toàn với model context nhỏ (`MIN_COMPACTION_CONTEXT_WINDOW: u64 = 80_000`) — với model đó UI chỉ cảnh báo gần giới hạn thay vì compact.

Có field `LanguageModelRequest.compact_at_tokens` (luôn `None` trong build hiện tại) — gợi ý một cơ chế compaction native phía provider/server đã được chuẩn bị chỗ đứng nhưng chưa nối dây.

## 3. History compaction / summarization

Zed **có** tóm tắt chủ động, không chỉ truncate:

- `compaction_message_target_ix` (`thread.rs:4222-4276`) quyết **khi nào** auto-compact: duyệt ngược tới user-message gần nhất có ghi usage, kiểm tra đã qua điểm compact trước đó, so `active_tokens` với ngưỡng đã tính.
- `build_compaction_request` (`thread.rs:4292-4315`) dựng 1 `LanguageModelRequest` bình thường từ toàn bộ message tới điểm chèn, cộng thêm 1 user message cuối chứa `COMPACTION_PROMPT` — yêu cầu "viết bàn giao cho agent tiếp theo" (mục Goal/State/Context/Next/Pitfalls).
- Response của model trở thành `Message::Compaction(CompactionInfo::Summary(text))`, chèn vào `self.messages` tại vị trí đã tính. Khi dùng lại, nó được tái chèn thành 1 synthetic user message: *"The previous conversation was compacted. Use this summary as context:\n\n{summary}"*.
- Ở request sau, `extend_request_history_until` tìm **compaction message mới nhất** và chỉ gửi message từ đó trở đi — về cơ bản drop mọi thứ trước đó — **NGOẠI TRỪ** còn gọi `retained_user_request_messages_before`, duyệt ngược từ điểm compact để include lại các user-message thô gần nhất, giới hạn bởi **byte budget `COMPACTION_RETAINED_USER_MESSAGES_BYTE_BUDGET = 80_000` byte** (heuristic 1 token ≈ 4 byte, ~20k token) — nghĩa là model vẫn thấy nguyên văn các câu hỏi user gần nhất kể cả sau compact, không chỉ summary.
- Có cả compact thủ công `Thread::compact()` với chiến lược chèn riêng (`Manual` vs `Auto`). Có thêm `CompactionInfo::ProviderNative { provider, items }` cho các provider có cơ chế context-management riêng thay thế summary text mặc định.
- Telemetry (`CompactionTelemetry`) ghi token trước/sau và trigger ("auto"/"manual").

Tóm lại: **không phải sliding truncation window thuần** — là summarize-rồi-splice kèm buffer giữ lại nguyên văn tin nhắn gần nhất có giới hạn, kích hoạt bởi ngưỡng % cửa sổ ngữ cảnh.

## 4. System prompt / rules construction (`crates/prompt_store/`)

- `RULES_FILE_NAMES` (`prompts.rs:21-30`) là danh sách cố định, có thứ tự các tên file rule Zed nhận diện theo từng worktree: `.rules`, `.cursorrules`, `.windsurfrules`, `.clinerules`, `.github/copilot-instructions.md`, `AGENT.md`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md` — **Zed đọc thẳng convention rules-file của các tool khác**, không chỉ của riêng mình.
- `ProjectContext` gom `WorktreeContext` (1 `RulesFileContext`/worktree, tối đa 1 file nội dung) + flag `skills`/`has_skills` cho template.
- Có `~/.config/zed/AGENTS.md` **toàn cục cấp user**, load riêng và đưa vào `build_request_messages_until`.
- Template `system_prompt.hbs` ghép các phần này lại với quy tắc ưu tiên nói rõ trong prompt: *"Project-specific rules below may override [personal AGENTS.md]"*.
- `prompt_store.rs` là 1 `PromptStore` backed bởi LMDB, lưu "Rules"/prompt do user đặt tên (tính năng legacy) — đang được migrate: rule không-mặc-định → Agent Skills (`~/.agents/skills/<slug>/SKILL.md`, gọi khi cần qua tool `skill`), rule mặc định (luôn bật) → gộp vào `AGENTS.md` toàn cục. Skill đưa vào system prompt có **ngân sách byte**: `select_catalog_skills` chỉ đóng gói tên+mô tả skill vào catalog khi còn dưới `MAX_SKILL_DESCRIPTIONS_SIZE` byte, skill nào tràn thì bị drop (và báo qua `SkillLoadingIssueData`) — ngân sách byte/token tất định, có thứ tự sort, tách biệt hoàn toàn với ngân sách token chat ở mục 2.

## 5. Edit-prediction (Zeta) context assembly

Đường này khác kiến trúc hẳn so với chat, và tường minh về ngân sách hơn nhiều:

- **Nguồn context**, kết hợp mỗi request:
  - Mở rộng excerpt cục bộ nhận biết cú pháp — `compute_editable_and_context_ranges` mở rộng vùng quanh con trỏ ra biên node cú pháp (tree-sitter), tôn trọng ngân sách token cứng cho từng vùng, fallback về mở rộng theo dòng nếu mở rộng theo cú pháp không vừa.
  - "Related excerpts" dựa trên LSP — `RelatedExcerptStore` trích định danh gần con trỏ (tối đa 32 định danh), gọi LSP go-to-definition/type-definition, debounce 100ms, cache theo định danh+range.
  - Retrieval BM25 thật — `bm25_context.rs` (k1=1.2, b=0.75) trên chunk file trên đĩa (chunk 40 dòng, overlap 10 dòng, tối đa 12 chunk tổng/3 chunk mỗi file, file cap 1MB), query bằng 20 dòng cuối quanh con trỏ + tối đa 8 mục edit-history gần đây.
  - Context từ git log/edit-history.
- **Ngân sách token tường minh, theo từng phiên bản format prompt**: `estimate_tokens(bytes) = bytes / 3` (heuristic rẻ, không phải tokenizer thật), margin an toàn 10%, trần token tối đa cứng theo format từ 4096–16384 (vd `V0327SingleFile => 16384`, `V0615HashRegions => 8000`). Ngân sách còn được **chia nhỏ thành editable-region vs context-region** theo từng format (vd `(350, 150)` cho hầu hết format seed-coder, `(8000, 0)` cho hash-regions). Excerpt file liên quan được nhồi vào ngân sách còn lại theo kiểu greedy, required-trước rồi theo score, dừng khi vượt ngân sách.
- Tóm lại đường này vừa nhận biết cây cú pháp, vừa nhận biết LSP/definition (một dạng "retrieval" nhẹ), vừa dùng keyword-retrieval (BM25), vừa dùng recency (edit history) — kết hợp rồi cắt cứng vào ngân sách token nhỏ, tối ưu độ trễ, tách biệt hoàn toàn kế toán context-window của chat agent.

## 6. External context servers (`crates/context_server/`)

`crates/context_server/` chính là **client MCP (Model Context Protocol)** của Zed — JSON-RPC qua stdio hoặc HTTP(S), có negotiate capability cho `Prompts`, `Resources`, `Tools`.

Trong agent, chỉ capability **Tools** thực sự được nối vào context assembly: `Thread::enabled_tools` liệt kê tool từ mọi context-server đã bật và gộp vào cùng danh sách tool gửi cho model, chịu bật/tắt theo profile và cơ chế khử trùng tên giới hạn bởi `MAX_TOOL_NAME_LENGTH = 64` — tức "ngân sách" duy nhất ở đây là **giới hạn độ dài TÊN tool** để khử trùng, không phải ngân sách nội dung/token. `Prompts` được dùng ở chỗ khác (dạng slash-command) nhưng không nằm trong context assembly tự động mỗi turn. `Resources` được negotiate nhưng **không tìm thấy** đường pull-tự-động nào trong `crates/agent` — tích hợp MCP của Zed là tool-call-driven (model tự quyết định pull gì, kết quả trở thành 1 tool-result message bình thường, chịu kế toán token chung ở mục 2), không phải một ngân sách resource riêng được quản lý.

---

## Ý tưởng đáng chú ý (so với 1 chatbot/RAG stack generic)

1. **Không có tokenizer local nào trong đường chat** — kế toán token hoàn toàn phản ứng (reactive), lấy từ số usage do chính provider trả về sau mỗi response, không dự đoán trước khi gửi. Quyết định compact/cảnh báo được đưa ra **sau khi đã biết** usage thật của turn trước.
2. **Compaction kiểu summarize-rồi-splice kèm buffer giữ nguyên văn có giới hạn** — thay vì sliding-window truncation thuần hay summarization thuần, Zed giữ lại phần đuôi user-message nguyên văn giới hạn theo byte (~80KB/~20k token) **cộng thêm** summary bàn giao do LLM viết, nên các câu hỏi gần nhất không bị nén mất thông tin.
3. **Hai chế độ ngân sách context hoàn toàn tách biệt cho 2 lớp độ trễ khác nhau**: chat agent tính ngân sách bằng token API thật, hậu-kiểm, ở ngưỡng ~90% cửa sổ; đường inline-completion (Zeta) tính trước ngân sách token ước lượng bytes/3 **trước khi** gửi request, chia nhỏ thành sub-budget editable-vs-context theo từng phiên bản format prompt, vì không đủ khả năng chờ round-trip hay "chờ xem rồi tính".
4. **Context code ưu tiên cây cú pháp, không ưu tiên embedding** — lựa chọn context cục bộ của Zeta mở rộng theo biên node tree-sitter trước, fallback dòng sau; tín hiệu "retrieval" là BM25 lexical chính xác trên file đã chunk, không phải vector embedding — đánh đổi có chủ đích để giảm độ trễ, không cần build index, phù hợp editor native tốc độ thấp.
5. **Mention được tái tổ chức theo cấu trúc, không để nguyên inline** — tham chiếu `@file/@symbol/@thread` của user bị viết lại phía server từ vị trí gõ literal thành các block tag gom theo loại, cho model 1 chỗ nhất quán, dễ parse để tìm "tất cả file," "tất cả diff," bất kể user gõ ở đâu.
6. **Lớp tương thích rule-file của đối thủ**: Zed đọc thẳng format rule-file của các tool khác (`.cursorrules`, `.windsurfrules`, `.clinerules`, `CLAUDE.md`, `GEMINI.md`) vào thẳng system prompt của mình, và đã migrate tính năng "Rules" cũ thành hybrid `AGENTS.md` luôn-bật + "Skills" theo yêu cầu (có ngân sách byte cứng riêng cho block mô tả catalog skill) thay vì giữ cơ chế inject rule riêng.
