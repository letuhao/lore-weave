# Context Management Architecture — Continue

> Smart-scan (không đọc toàn bộ repo) `D:\Works\source\context-management\continue` — tập trung vào `core/context/`, `core/autocomplete/`, `core/llm/`, `core/indexing/`. Mục tiêu: nắm cơ chế quản lý context window thật, có file:line, để đối chiếu với kiến trúc context của LoreWeave.

---

## 1. System prompt / chat context assembly

Có một hàm "compile" trung tâm phía client: `constructMessages()` (`gui/src/redux/util/constructMessages.ts:37`), chạy 1 lần/turn trước khi request đi tới core, dựng mảng theo thứ tự cố định:

1. **System message** (`constructMessages.ts:214-222`): `baseSystemMessage` + text của các **rules** áp dụng được + `"Previous conversation summary:\n\n{summary}"` nếu có compaction summary (dòng 198-212).
2. **History** duyệt theo thứ tự gốc (dòng 67-176):
   - message `user`: context items được **chèn thẳng làm text part vào cùng message** (không phải message riêng) — dòng 83-92.
   - message `assistant`: pass-through (hoặc convert sang text-based tool-call format nếu `useSystemToolsFramework`, dòng 107-123).
   - message `tool` tổng hợp được chèn lại sau tool-call của assistant (dòng 130-160), kể cả placeholder giả `"Tool cancelled"` để không bao giờ có tool-call thiếu response tương ứng.
3. Kết quả được đưa vào `.chat()/.streamChat()` của LLM, nơi có **pass compile thứ hai phía core**: `compileChatMessages()` (`core/llm/countTokens.ts:422`) — đây mới là nơi token-budget pruning thật sự xảy ra (xem mục 2).

Pipeline: **rules → system prompt → history đã gắn context → token-budget compiler → formatter theo provider**.

Việc match rules cũng không tầm thường: `getSystemMessageWithRules()` (`core/llm/rules/getSystemMessageWithRules.ts:276-369`) lọc rule theo `alwaysApply`, glob pattern khớp file path (rút từ code block trong message + từ URI của context item), và optional content regex — tức là system prompt được ghép **theo path/content mỗi turn**, không phải string tĩnh.

## 2. Token budgeting

Có, tường minh, với thiết kế **reserve-cho-response**, không chỉ là hard cap.

`compileChatMessages()` (`core/llm/countTokens.ts:422-551`) coi `system message + tool schema + chuỗi user/tool-call cuối` là **bất khả xâm phạm**, phần history cũ hơn là phần được phép cắt.

Công thức ngân sách (dòng 481-494):
```
contextLength = knownContextLength ?? 128_000 (DEFAULT_PRUNING_LENGTH)
countingSafetyBuffer = min(1000, contextLength * 0.02)
minOutputTokens = min(1000, maxTokens)
inputTokensAvailable = contextLength - countingSafetyBuffer - minOutputTokens
                       - toolTokens - systemMsgTokens - lastMessagesTokens
```
- Nếu biết `knownContextLength` và `inputTokensAvailable < 0` → **throw** (dòng 497-508) — system + tool + turn cuối phải vừa, hoặc request fail hẳn (không âm thầm cắt tin nhắn user vừa gửi).
- Ngược lại: **pop history từ đầu cũ nhất** (`historyWithTokens.shift()`, dòng 522) tới khi vừa ngân sách, và drop luôn `tool` message mồ côi phát sinh (dòng 527-530). Thứ tự drop: **cũ nhất trước**; system prompt/tool schema/turn cuối không bao giờ bị drop.
- Trả về `{compiledChatMessages, didPrune, contextPercentage}` — `contextPercentage` feed vào thanh đo context-usage trên GUI (chỉ hiện khi ≥60% đầy hoặc đã prune, `ContextStatus.tsx:33-35`).
- Đếm token (`countChatMessageTokens`, dòng 179-218) cộng thêm overhead per-message/tool-call/tool-output (`BASE_TOKENS=4`, `TOOL_CALL_EXTRA_TOKENS=10`, `TOOL_OUTPUT_EXTRA_TOKENS=10`) mô phỏng overhead per-message của OpenAI, dùng tiktoken hoặc llama tokenizer tùy model. Ảnh tính phẳng 1024 token/ảnh.
- Các helper prune string thô (`pruneStringFromTop/Bottom`, `pruneLinesFromTop/Bottom`) được tái dùng ở autocomplete path (mục 6) cùng hàm safety-buffer.

## 3. Context providers architecture

Kiến trúc plug-in phẳng (flat concatenation), với **một ngoại lệ có ngân sách riêng thật sự**.

- `BaseContextProvider` (`core/context/index.ts:10-38`): abstract class tối giản — `getContextItems(query, extras)` + `loadSubmenuItems()` tùy chọn. ~30 provider built-in (files, codebase, docs, terminal, diff, folder, git commit, GitHub issues, Jira, MCP, HTTP/custom, OS, problems, repo map, search, URL/web...), gọi đồng nhất qua cơ chế `@` mention.
- **Không có bộ phân bổ ngân sách chéo-provider** — mỗi provider trả về `ContextItem[]` tùy ý, `constructMessages.ts:83-92` chỉ nối tất cả context item của 1 turn thành text part. Trần ngân sách duy nhất là pass `compileChatMessages` (mục 2), prune theo **message**, không theo item.
- Provider duy nhất có ngân sách nội bộ là **`@codebase`** (`retrieveContextItemsFromEmbeddings`, `core/context/retrieval/retrieval.ts:11-130`) — comment gốc: *"Fill half of the context length, up to a max of 100 snippets"*:
  ```js
  const tokensPerSnippet = 512;
  const nFinal = options?.nFinal ?? Math.min(25, contextLength / tokensPerSnippet / 2);
  const nRetrieve = useReranking ? (options?.nRetrieve || 2 * nFinal) : nFinal;
  ```
  tức reserve ~`contextLength/2` cho snippet, ~512 token/snippet, cap 25 snippet cuối, over-retrieve 2× khi có reranker.
- MCP server cũng chỉ là 1 provider khác, cùng contract `getContextItems`.

## 4. Codebase retrieval (đường "@codebase" RAG)

Hybrid lexical + semantic, chunking nhận biết tree-sitter, có tầng rerank tùy chọn.

- **2 pipeline**, chọn theo có cấu hình rerank model hay không: `RerankerRetrievalPipeline` vs `NoRerankerRetrievalPipeline` (cùng kế thừa `BaseRetrievalPipeline.ts:60`).
- **Nguồn retrieval fan-out rồi merge** (`RerankerRetrievalPipeline._retrieveInitial`, dòng 13-86):
  - Full-text search (trigram-tokenized, stemmed bằng wink-nlp-utils + n-gram(3)).
  - Vector search qua `LanceDbIndex.retrieve()` — chỉ khi có embed model.
  - Chunk từ file vừa sửa/mở gần đây (đọc từ LRU cache, chunk tươi, không qua index).
  - Repo-map chunk (LLM-assisted repo-map lookup).
  - Tool-calling retrieval tùy chọn (`retrieveWithTools`, gated bởi `config.experimental.codebaseToolCallingOnly`) — để chính LLM chọn dùng `globSearch/grepSearch/ls/readFile/viewRepoMap/viewSubdirectory`.
  - Toàn bộ dedup + filter theo `filterDirectory`.
- **Rerank** (`_rerank`, dòng 88-124): gọi `config.selectedModelByRole.rerank.rerank(...)`, sort giảm dần theo score, cắt còn `nFinal`. Lọc theo ngưỡng score và mở rộng bằng embedding sau rerank **đã được cài nhưng hiện đang bị comment out** trong `run()` — chỉ còn retrieve → rerank → truncate là live.
- **Chiến lược chunking** (`core/indexing/chunk/chunk.ts` + `code.ts`): dùng tree-sitter `codeChunker` cho ngôn ngữ có grammar (trừ CSS/HTML/JSON/YAML/TOML dùng `basicChunker`); `codeChunker` **collapse đệ quy** thân function/class thành `{ ... }`/`...`, bắt đầu từ child ít quan trọng nhất, tới khi vừa `maxChunkSize` (mặc định 384 token). Chunk nào vẫn vượt sau khi chunk thì bị **âm thầm drop**.
- **Trừu tượng hóa embedding provider**: bất kỳ `ILLM` có role `embed` đều dùng được — interface chỉ là `embed(chunks: string[]): Promise<number[][]>`; `LanceDbIndex` provider-agnostic, lưu vector trong bảng LanceDB nhúng theo từng cấu hình embed-model+chunking.
- Kết quả được format kèm message hướng dẫn *"Use the above code to answer... don't reference files outside of what's shown... reference filenames"*, sort theo filepath trước khi trả về.

## 5. History compaction / conversation memory

Có compaction bằng summarization thật, nhưng là **thủ công/user-trigger, không tự động** — ngoài ra hệ thống dựa vào hard token-budget pruning (mục 2), không phải sliding-window truncation.

- `compactConversation()` (`core/util/conversationCompaction.ts:19-112`), gọi qua IPC `conversation/compact`, chỉ trigger khi user bấm nút compaction trên GUI.
- Cơ chế: lấy `history[0..index]`, tìm `conversationSummary` gần nhất trong slice đó và chỉ feed message SAU điểm đó (re-compact không làm lại từ đầu), dựng lại placeholder tool-call bị hủy giống `constructMessages`, prepend summary cũ làm 1 synthetic user message nếu có, rồi **hỏi chính model chat hiện tại** tạo structured summary theo prompt cố định (overview / active development / tech stack / file operations / solutions / outstanding work). Summary lưu vào field `conversationSummary` của history item đó — **không xóa message, chỉ đánh dấu điểm cắt**.
- Cả `constructMessages.ts` (GUI) và `compactConversation.ts` (core) độc lập implement cùng logic "tìm `conversationSummary` mới nhất, cắt sau nó" — đây chính là sliding-window: mọi thứ trước điểm đánh dấu được thay bằng summary gộp vào system message, mọi thứ sau giữ nguyên (chịu token-budget compiler ở mục 2).
- **Không có auto-compaction theo ngưỡng** — `contextPercentage` chỉ lái UI indicator, không tự trigger compact. Vượt ngân sách ngoài điểm compact thủ công → xử lý thuần bằng oldest-first pruning của `compileChatMessages`.

## 6. Autocomplete-specific context assembly

Autocomplete có hệ ngân sách riêng, tối ưu độ trễ, theo tỷ lệ phần trăm — hoàn toàn tách khỏi compiler chat.

- **Ngân sách prefix/suffix** — `HelperVars.prunePrefixSuffix()` (`core/autocomplete/util/HelperVars.ts:85-110`): `maxPrefixTokens = maxPromptTokens * prefixPercentage`, `maxSuffixTokens = min(...)`, dùng prune theo dòng (không cắt giữa dòng). Mặc định: `maxPromptTokens: 1024`, `prefixPercentage: 0.3`, `maxSuffixPercentage: 0.2` — ~30% ngân sách cho prefix, ~20% cho suffix, còn lại cho snippet chèn vào.
- **Thu thập snippet** (`core/autocomplete/snippets/getAllSnippets.ts`): fan-out tới recently-edited ranges, recently-visited ranges, recently-opened files, clipboard, git-diff, import-definition, "root path", static-context, và LSP/IDE definitions nếu bật — mỗi nguồn được bọc `racePromise(timeout=100ms)` để 1 provider chậm (vd LSP) không làm treo completion; có thêm `showWhateverWeHaveAtXMs: 300` và `modelTimeout: 150` chặn tổng độ trễ.
- **Đóng gói kiểu knapsack ưu tiên vào ngân sách còn lại** — `getSnippets()` (`core/autocomplete/templating/filtering.ts:44-207`): mỗi loại snippet có `defaultPriority` (clipboard=1, recentlyOpenedFiles=2, recentlyVisitedRanges=3, recentlyEditedRanges=4, diff=5, base/root-path+imports+static=99). Tính `remainingTokenCount`, rồi thêm snippet theo thứ tự ưu tiên, mỗi cái tốn `countTokens(snippet) + 10 (buffer)`, dừng khi hết ngân sách — **first-fit theo priority**, không phải global-optimal pack.
- Còn path xếp hạng cũ/deprecated (`core/autocomplete/context/ranking/index.ts`) dùng **Jaccard symbol-overlap similarity** (không phải embedding) giữa snippet ứng viên và cửa sổ trượt quanh con trỏ — rẻ, đồng bộ.
- Assembly cuối (`core/autocomplete/templating/index.ts`): `renderPromptWithTokenLimit()` dựng prompt; nếu vẫn vượt `contextLength - reservedCompletionTokens - safetyBuffer` (tái dùng CÙNG hàm safety-buffer với chat compiler) thì **co tỷ lệ prefix/suffix theo tỷ trọng token** rồi render lại 1 lần.

## Ý tưởng đáng chú ý (so với 1 RAG chatbot generic)

1. **Compiler token 2 tầng, đối xứng qua mọi provider** (`compileChatMessages`) — coi system prompt + tool schema + turn cuối là bất khả xâm phạm, reserve safety-buffer theo % + sàn token tối thiểu cho response, chỉ prune history cũ — dùng chung logic (`getTokenCountingBufferSafety`) giữa chat path và autocomplete path.
2. **Compaction hội thoại do user điều khiển, resumable** thay vì auto/silent summarization — điểm compact là marker lịch sử tường minh (`conversationSummary`) mà cả message-constructor lẫn compaction routine độc lập nhận ra và resume từ đó, nên 1 session có thể compact nhiều lần ở nhiều điểm khác nhau mà không tóm tắt lại phần đã tóm tắt.
3. **"Rules" system-prompt theo scope path/content mỗi turn** dựa trên glob match + content regex đối với cả file user tham chiếu lẫn context item trước đó — system prompt động, có điều kiện, không phải string tĩnh.
4. **Chunk collapsing nhận biết ngữ nghĩa cho embedding**: thay vì cửa sổ text cỡ cố định, chunker tree-sitter giữ signature function/class và collapse dần các block con ít liên quan nhất thành `{ ... }` tới khi vừa ngân sách token của embed model.
5. **Đóng gói ưu tiên theo tier, giới hạn độ trễ cho autocomplete** — mỗi nguồn snippet bị time-box (~100ms race) rồi fill vào ngân sách còn lại nghiêm ngặt theo tier ưu tiên (clipboard > open files > visited ranges > edited ranges > diff > còn lại) — đánh đổi tường minh completeness lấy tốc độ tương tác, khác hẳn hybrid-search có rerank nặng hơn dùng cho `@codebase` chat.
