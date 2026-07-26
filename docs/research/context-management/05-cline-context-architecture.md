# Context Management Architecture — Cline

> Smart-scan `D:\Works\source\context-management\cline` — monorepo mới restructure sang "Agent SDK". Logic context-management thật nằm ở `sdk/packages/core/src/extensions/context/{compaction,agentic-compaction,basic-compaction,compaction-shared}.ts`, `sdk/packages/core/src/session/services/message-builder.ts`, và `sdk/packages/agents/src/agent-runtime.ts` — không phải ở `apps/vscode/src/core/task/` như các bài viết cũ về Cline mô tả (phần đó đã bị extract ra SDK).

---

## 1. Task-loop message assembly

Một chỗ trung tâm duy nhất: `sdk/packages/agents/src/agent-runtime.ts`, method `generateAssistantMessage()` (~dòng 773).

Mỗi iteration:
1. `AgentRuntime.state.messages` được clone vào 1 request mới: `{systemPrompt, messages: cloneMessages(...), tools, options}` (dòng 785-797). System prompt tĩnh cho cả run trừ khi bị viết lại.
2. Nếu `iteration > 1`, 1 "steer" message của user đang chờ được chèn vào.
3. `request = await this.prepareTurnForModelRequest(request)` — đây là **hook compaction** (`prepareTurn`), nối vào `createContextCompactionPrepareTurn`. Có thể thay thế toàn bộ `state.messages` và viết lại `systemPrompt`.
4. Hook `beforeModel` chạy → gọi `prepareMessagesForModelRequest` → chạy các `messageBuilder` do plugin đăng ký, rồi `MessageBuilder.buildForApi()` built-in. Đây là **1 pass riêng, LUÔN CHẠY** (độc lập với việc compaction có kích hoạt hay không):
   - cắt giữa (middle-truncation) mọi nội dung tool_result về tối đa 8.000 ký tự
   - viết lại **file read đã cũ (stale)** thành `"[outdated - see the latest file content]"` (xem mục 4)
   - cap text assistant (200k ký tự) và markup tool-call lặp lại (12k ký tự)
   - áp ngân sách byte text tổng cộng 6MB cho toàn transcript như van an toàn cuối cùng, cắt tool-result/assistant-text/tool-args lớn nhất trước
   - áp ngân sách byte cho ảnh/media
   - sửa cặp tool_use/tool_result mồ côi (tổng hợp result thiếu)
5. Request gửi qua `this.config.model.stream(request)`.

Vậy có **2 lớp cơ chế xếp chồng**, không phải 1: (a) compaction (`prepareTurn`) — co cấu trúc/thay thế mảng message khi vượt ngưỡng token, và (b) `MessageBuilder.buildForApi` — chạy **mọi turn** bất kể ngưỡng, để chống payload đơn lẻ quá khổ và read đã cũ. Compaction chạy trước; message builder luôn chạy sau.

## 2. Ngân sách context-window

Công thức ở `resolveTriggerState()` (`compaction.ts:183-222`):

- `inputTokens` = tổng `estimateMessageTokens(message)` trên toàn bộ `apiMessages` — heuristic rẻ `JSON.stringify(message).length / CHARS_PER_TOKEN`, memoized theo object — **không phải** usage do provider trả về.
- `maxInputTokens` từ `resolveMaxInputTokens()`: min của override cấu hình, `maxInputTokens` của model, hoặc `contextWindow` (chỉ dùng nếu `contextWindow - maxOutputTokens ≥ 0.5 * contextWindow`). Fallback `DEFAULT_MAX_INPUT_TOKENS = 200_000`.
- Ngưỡng trigger mặc định: `DEFAULT_THRESHOLD_RATIO = 0.9`, `DEFAULT_RESERVE_TOKENS = 16_384`. Điểm trigger = `min(maxInputTokens - 16384, maxInputTokens * 0.9)`. **Compaction kích hoạt khi `inputTokens > triggerTokens`** — tức khoảng 90% utilization hoặc "còn cách trần 16k token dự phòng", cái nào bảo thủ hơn.
- Config có thể chỉ định thẳng `reserveTokens`/`thresholdRatio`, ghi đè công thức mặc định.
- **Đường auto-trigger này TẮT MẶC ĐỊNH.** `compaction: {enabled: true, strategy}` chỉ được thêm vào session config nếu `useAutoCondense` (mặc định `false`, user phải tự bật).
- Số % utilization hiển thị trên UI là cosmetic — lấy từ `tokensIn/tokensOut` thật do provider trả, dùng cho 1 cảnh báo `>50%` chèn vào 1 tool-error message cụ thể (`CONTEXT_WINDOW_WARNING_THRESHOLD_PERCENT = 50`), **không** dùng để trigger compaction.

## 3. Compaction 2 tầng: basic vs agentic

Chọn qua `userCompaction?.strategy ?? "basic"`. Mặc định toàn cục là `"basic"`.

**`basic` (`basic-compaction.ts`)** — tất định, không gọi LLM:
- Chia transcript thành `protectedTail` (turn gần nhất, luôn giữ nguyên văn) và `compactable` (phần còn lại).
- Dựng "candidate" theo chi phí token từng message, xóa theo thứ tự ưu tiên cố định để đạt `targetTokens`: (1) assistant message không phải cuối, (2) user message giữa (không đầu/cuối), (3) assistant message cuối, (4) user message cuối (không phải đầu) — dùng `removeCandidatesByPredicate` đi theo **chuỗi cặp tool_use/tool_result** nên tool call không bao giờ bị xóa mà thiếu result đi kèm (tránh lỗi API do block mồ côi).
- Nếu xóa vẫn chưa đủ ngân sách, fallback cắt giữa (middle-truncate) từng token các message còn lại, rồi phương án cuối cùng cắt cả user-message đầu tiên (task gốc) trừ khi đã ≤ kích thước trigger.
- Tỷ lệ mục tiêu: `DEFAULT_TARGET_RATIO = 0.7` của trigger token bình thường, nhưng nếu hội thoại đã dài (≥5 cặp user/assistant) và `maxTokens` (reserve output) của model nhỏ hơn đáng kể `maxInputTokens`, mục tiêu chuyển thành **`LONG_CONVERSATION_TARGET_RATIO = 0.5`** của cả window — cắt mạnh tay hơn cho hội thoại đã chạy lâu.

**`agentic` (`agentic-compaction.ts`)** — tóm tắt bằng LLM:
- Tìm điểm cắt qua `findCutIndex`: duyệt ngược từ đuôi cộng dồn token tới khi đạt `preserveRecentTokens` (mặc định `20_000`), rồi chốt tới boundary bắt-đầu-turn gần nhất để không tách cặp tool_use/tool_result.
- Mọi thứ trước điểm cắt serialize thành text thuần, gửi cho LLM với prompt cố định yêu cầu tóm tắt cấu trúc "Goal / State / Highlights / Next / Files"; hỗ trợ tóm tắt lại tăng dần (chỉ gộp message MỚI kể từ summary trước).
- Summarizer có thể dùng **model khác, rẻ hơn** model chat chính, `thinking: false`, `maxOutputTokens` cap `DEFAULT_SUMMARY_MAX_OUTPUT_TOKENS = 1024`.
- Kết quả: `[summaryMessage(role:"user", metadata.kind="compaction_summary"), ...messages.slice(cutIndex)]` — 1 synthetic user message chứa summary, theo sau là đuôi giữ nguyên văn.
- Nếu lời gọi LLM fail/rỗng → trả `undefined`, turn tiếp tục KHÔNG compact (không tự fallback về `basic`).

**Logic trigger giống hệt nhau cho cả 2 strategy** — strategy chỉ quyết *cách* co lại khi `resolveTriggerState()` báo đã tới lúc; `mode` (`auto`/`manual`) chỉ đổi *kích thước mục tiêu*, không đổi việc có áp ngưỡng hay không.

## 4. File-context staleness — 2 cơ chế độc lập, gần như tách rời nhau

**(a) Cơ chế đang sống — `MessageBuilder` viết lại read đã cũ**, `message-builder.ts`. Đây là thứ thực sự ảnh hưởng tới những gì model thấy, mỗi turn:
- Đánh index mọi tool_use/tool_result `read`/`read_files` theo `(path, startLine, endLine)`.
- `isOutdatedReadLocator()`: 1 read bị coi là cũ nếu có message sau đó đọc TOÀN BỘ file cùng path với tool_use_id khác, hoặc có read cùng range chính xác dưới id khác.
- Staleness được xử lý **theo lô, không tức thời**: `commitOutdatedRewrites()` chỉ commit khi byte có thể thu hồi từ các read mới-cũ vượt **`DEFAULT_MIN_OUTDATED_REWRITE_BYTES = 65_536` (64KB)** — comment giải thích cố ý tránh làm mất hiệu lực prompt-cache của provider mỗi lần đọc lại.
- Sau khi commit, nội dung cũ được thay tại chỗ bằng chuỗi literal `"[outdated - see the latest file content]"` — **thay thế nội dung âm thầm, không phải warning message** cho model.
- Có nhận biết rollback: nếu 1 locator trở nên hiện hành trở lại (vd sau checkpoint restore) thì un-commit.

Giải quyết bài toán "model thấy file X, X đổi trên đĩa (hoặc đã bị thay bởi read mới hơn), đừng để model hành động trên byte cũ" — nhưng thuần từ re-read TRONG hội thoại, không so sánh mtime/hash thật trên đĩa.

**(b) Cơ chế legacy/di tích — `FileContextTracker`**, `apps/vscode/src/core/context/context-tracking/FileContextTracker.ts`. Class này THẬT SỰ theo dõi filesystem (`chokidar`), đánh dấu metadata `active`/`stale`, có method rõ ràng để inject warning nội dung cũ và 1 chuỗi prompt dựng sẵn (`formatResponse.contextTruncationNotice()`). **Tuy nhiên** grep toàn repo cho thấy `getAndClearRecentlyModifiedFiles`, `detectFilesEditedAfterMessage`, `storePendingFileContextWarning`, `retrieveAndClearPendingFileContextWarning` **không có caller nào** ngoài chính class và unit test. Caller sản xuất DUY NHẤT của `FileContextTracker` là `core/mentions/index.ts`, gọi `trackFileContext(path, "file_mentioned")` thuần để đăng ký file đã hiển thị cho model qua `@mention` (feed watcher và metadata, nhưng output stale-detection của nó không được dùng ở đâu cả). **Điều này gợi ý mạnh rằng UX "file đổi trên đĩa, cảnh báo model" kiểu cũ đã bị thay thế bởi cơ chế viết-lại-âm-thầm của SDK (4a), và phần fs-watcher/warning giờ là dead code ở tầng VS Code**, giữ lại vì unit test hoặc có thể còn dùng ở đường checkpoint-restore chưa tìm thấy trong lần scan này.

## 5. Mentions / hệ thống gắn context

`apps/vscode/src/core/mentions/index.ts`, hàm `parseMentions()` — **giải quyết ngay lập tức, đồng bộ, tại thời điểm dựng message**, không hoãn lại:
- Regex quét text user tìm mention, thay token bằng label ngắn dễ đọc (vd `'@/foo.ts' (see below for file content)'`), rồi **append** nội dung đã resolve thành text block vào cuối CÙNG message string.
- Xử lý theo loại: `@file`/`@folder` → đọc qua `extractTextFromFile` (folder: chỉ 1 cấp, không đệ quy); `@url` → `UrlContentFetcher.urlToMarkdown` (mở headless browser); `@problems` → `diagnosticsToProblemsString`; `@terminal` → output terminal gần nhất; `@git-changes`; chuỗi hex 7-40 ký tự → coi là git commit hash.
- **Giới hạn kích thước**: nội dung file/folder qua `truncateContent()` — **cap cứng 400KB/file** (≈100.000 token), cắt từ đầu kèm thông báo ở cuối. **Không có** cap cứng tương tự cho `@url`, `@problems`, `@terminal`, `@git-changes` trong file này — chúng chỉ chịu ngân sách chung của `MessageBuilder` (mục 1) nếu lỡ quá lớn.
- Multi-root workspace: cú pháp `@workspace:name/path`; mention không rõ workspace ở chế độ multi-root fan-out song song tất cả root, nhúng 1 block `<file_content>` mỗi workspace nếu file tồn tại ở nhiều nơi.
- Có guard chặn thẳng mention `@/"` để tránh dump đệ quy toàn bộ workspace-root.

Vì nội dung resolve trở thành text block THƯỜNG trong chính message của user (không phải content-block loại `tool_result`/`file` riêng), nó **không** chịu cap 8k-ký-tự của tool-result hay cap file-block từ `MessageBuilder`; chỉ chịu cap 400KB/mention ở trên và ngân sách byte tổng 6MB như phương án cuối.

## 6. Lệnh thủ công `/condense`

`slash/condense.ts` → `controller.compactTask()` → `sdk-compaction-coordinator.ts` → `sdk-compaction.ts`. Khác biệt so với compaction tự động:

1. **Bỏ qua hoàn toàn kiểm tra ngưỡng.** `if (mode === "auto" && !triggerState.shouldCompact) return undefined;` — gate này bị bỏ qua khi `mode === "manual"`, nên `/condense` LUÔN compact, kể cả khi mới dùng 5% ngân sách.
2. **Ép bật compaction** dù user đã tắt `useAutoCondense`/chưa cấu hình gì — override `enabled: true`.
3. **Công thức mục tiêu khác**: `resolveManualTargetState()` nhắm `min(autoTriggerTokens, currentInputTokens * manualTargetRatio)` với `manualTargetRatio` mặc định `0.5` (kẹp `[0.05, 0.95]`) — tức giảm khoảng một nửa usage hiện tại, nhưng không bao giờ vượt quá mục tiêu mà auto-compaction đã nhắm.
4. **Dùng bất kỳ `strategy` nào đang cấu hình toàn cục** (`basic` mặc định hoặc `agentic` nếu user chọn) — không có "manual strategy" riêng; `mode: "manual"` chỉ ảnh hưởng việc kẹp `preserveRecentTokens` với agentic mode (không được giữ nhiều hơn cả ngân sách trigger).
5. **Cơ chế giao hàng khác về cấu trúc**: thay vì compact tại chỗ giữa turn, `SdkCompactionCoordinator.runCompaction()` đọc toàn bộ transcript, compact, rồi **dỡ bỏ và khởi động lại toàn bộ SDK session** với message đã compact làm `initialMessages`, tái dùng cùng `sessionId`/task identity. Từ chối chạy khi đang có turn in-flight, tuần tự hóa các yêu cầu manual-compaction đồng thời. Có comment ghi lại đây là fix cho bug cũ (CLINE-2503): `/compact` trước đây gửi thẳng chuỗi `"/compact"` cho model, model "ứng biến" ra 1 summary giả vì SDK không đặc biệt hóa chuỗi đó thành lệnh.
6. Emit cùng telemetry event `task.compaction_executed`/`task.compaction_skipped` như auto-compaction, gắn tag `mode: "manual"` vs `"auto"`.

---

## Ý tưởng đáng chú ý (so với Continue / Zed / Aider)

1. **2 lớp phòng thủ độc lập, xếp chồng thay vì 1 pipeline compaction duy nhất**: 1 compactor cấu trúc kích hoạt theo ngưỡng token (`prepareTurn`, basic-hoặc-agentic) **cộng thêm** 1 pass `MessageBuilder.buildForApi` riêng, LUÔN CHẠY mỗi turn, cap kích thước từng tool-result/assistant-text, viết lại read cũ, áp ngân sách byte tổng như van cuối — bất kể compaction có kích hoạt hay không. Continue/Zed/Aider chỉ có 1 bước summarize-hoặc-prune, không có tuyến phòng thủ thứ 2 chống 1 tool-result đơn lẻ quá khổ.
2. **2 strategy cắm-được, user chọn** (`basic` prune tất định vs `agentic` tóm tắt LLM) sau 1 bề mặt config, `basic` là mặc định an toàn, `agentic` opt-in — thay vì mỗi tool chốt cứng 1 cách tiếp cận (Continue/Zed nghiêng hẳn về LLM-summary; Aider chỉ có recursive-summary).
3. **Xóa nguyên tử nhận biết cặp tool-call**: `collectAtomicRemovalCandidates` của basic compaction đi theo graph liên kết id tool_use/tool_result nên xóa 1 message sẽ kéo theo xóa cả partner ghép cặp, đảm bảo không bao giờ gửi block tool mồ côi cho provider — vấn đề đúng đắn mà 3 tool kia giải quyết thô hơn (cắt cả turn) hoặc không cần giải quyết theo cách này.
4. **Viết lại nội dung cũ theo lô, nhận biết prompt-cache**: thay vì cắt/cảnh báo ngay khi 1 file read trở nên lỗi thời, Cline tích lũy staleness và chỉ commit rewrite khi ≥64KB byte có thể thu hồi đã dồn lại, cố ý để tránh làm mất hiệu lực prompt/prefix-cache của provider mỗi lần đọc lại — 1 chính sách staleness có ý thức về chi phí cache mà 3 tool kia không đề cập.
5. **Manual compact ≠ "compact ngay với cùng luật"** — là 1 mode riêng bỏ qua gate ngưỡng, ép bật compaction dù auto đang tắt hoàn toàn, nhắm tỷ lệ cố định của usage HIỆN TẠI thay vì điểm trigger tự động, và **khởi động lại toàn bộ agent session** với transcript đã compact làm `initialMessages` mới thay vì sửa state giữa vòng lặp.

**Không tìm thấy sau khi scan có mục tiêu**: bất kỳ đường code nào đọc mtime/hash thật của file trên đĩa để so với những gì đã hiển thị cho model rồi inject cảnh báo "file này đã đổi" vào hội thoại đang chạy — hệ thống watcher/warning của `FileContextTracker` tồn tại nhưng dường như không còn caller nào nối output của nó ngược lại vào prompt trong snapshot này.
