# LoreWeave — Phân Tích Thị Trường & Hướng Phát Triển

## Document Metadata
- Document ID: LW-11
- Version: 1.2.0
- Status: Approved
- Owner: Business Analyst
- Last Updated: 2026-03-21
- Approved By: Governance Board
- Approved Date: 2026-03-21
- Summary: Market landscape, gap analysis, and build/borrow strategy context.

## Change History
| Version | Date | Change | Author |
|---|---|---|---|
| 1.2.0 | 2026-03-21 | Updated approval metadata to Approved with Governance Board sign-off | Assistant |
| 1.1.0 | 2026-03-21 | Added governance metadata header and migrated to numbered docs structure | Assistant |
| 1.0.0 | 2026-03-21 | Baseline content established before docs reorganization | Assistant |

> **Mục đích tài liệu:** Tổng hợp phân tích cạnh tranh OSS, xác định khoảng trống thị trường, và đề xuất kiến trúc hybrid cho LoreWeave với trọng tâm là creative continuation.
>
> **Ngày:** Tháng 3, 2026 | **Giai đoạn:** Pre-development (pipeline cũ làm baseline)

---

## 1. Bối cảnh & Câu hỏi cốt lõi

LoreWeave được thiết kế như một platform đa tác nhân (multi-agent) cho workflow tiểu thuyết đa ngôn ngữ — bao gồm dịch thuật, phân tích, xây dựng knowledge base, và hỗ trợ sáng tác. Trước khi bắt đầu build, câu hỏi quan trọng nhất cần trả lời:

> *"Thị trường đã có sản phẩm nào làm được điều này chưa? Nếu có, có lý do gì để xây dựng lại không?"*

Kết luận ngắn: **Chưa có sản phẩm nào kết hợp đủ ba trụ cột — dịch thuật nhất quán + story knowledge base + creative continuation — trong một unified platform.** Thị trường hiện tại bị chia thành hai thế giới riêng biệt và không giao nhau.

---

## 2. Bản Đồ Cạnh Tranh

### 2.1 Nhóm Translation-focused (CLI/Script)

#### `andrewyng/translation-agent`
- **Repo:** github.com/andrewyng/translation-agent | **Stars:** ~5,700 | **License:** MIT
- **Mô tả:** Agentic translation pipeline của Andrew Ng với reflect-improve loop — model dịch, sau đó tự phản hồi và cải thiện.
- **Điểm mạnh:** Kỹ thuật reflect-improve đã được validate, glossary cơ bản, code sạch và dễ đọc.
- **Điểm yếu:** Tự nhận là "not mature software" — proof of concept, không phải production tool. Không có UI, không có story-specific knowledge, không có entity extraction hay wiki building.
- **Đánh giá với LoreWeave:** Borrow pattern, không build lại.

#### TransAgents (Monash University / Tencent)
- **Nguồn:** Research paper, không phải production software
- **Mô tả:** Mô phỏng công ty dịch thuật với 5 vai: CEO, Senior Editor, Translator, Localization Specialist, Proofreader.
- **Điểm mạnh:** Kết quả chất lượng văn học cao, có paper đánh giá nghiêm túc.
- **Điểm yếu:** BLEU score kém hơn GPT-4 Turbo và Google Translate thẳng. Chỉ là nghiên cứu, không deployable.
- **Đánh giá với LoreWeave:** Tham khảo phương pháp đánh giá, không dùng code.

#### `Open-Translator` (5-agent pipeline)
- **Mô tả:** 5 agent: Organizer, Source Collector, Executor, Validator, Editor. Có REST API, Translation Memory, glossary.
- **Điểm mạnh:** Gần nhất với pipeline hiện tại của LoreWeave về mặt kỹ thuật translation.
- **Điểm yếu:** Hoàn toàn tập trung vào translation, không có story knowledge hay creative assistance. Không có platform layer.
- **Đánh giá với LoreWeave:** Tham khảo design agent, không thay thế được.

#### `llm-novel-translator` (Chrome Extension)
- **Mô tả:** Extension dịch novel trên trình duyệt, có auto-glossary extraction.
- **Điểm mạnh:** UX đơn giản, phù hợp casual reader.
- **Điểm yếu:** Không phải platform, không có knowledge base, không extensible.
- **Đánh giá với LoreWeave:** Khác segment hoàn toàn.

---

### 2.2 Nhóm Creative Writing (CLI)

#### StoryCraftr
- **License:** MIT | **Interface:** CLI + VSCode extension
- **Mô tả:** Tool worldbuilding và viết chapter từ đầu — outline, characters, world rules, interactive chat.
- **Điểm mạnh:** Approach có cấu trúc cho sáng tác mới, tích hợp editor tốt.
- **Điểm yếu:** Chỉ dành cho *sáng tác từ đầu*, không phân tích novel sẵn có, không dịch, không RAG trên canon.
- **Đánh giá với LoreWeave:** Khác use case. LoreWeave làm việc với novel *đã tồn tại*.

#### LibriScribe
- **Mô tả:** Multi-agent system: Concept Generation, Outlining, Character, Worldbuilding, Chapter Writing, Review, Style Editing.
- **Điểm mạnh:** Pipeline multi-agent hoàn chỉnh cho book generation.
- **Điểm yếu:** Tạo novel từ idea, không có grounding vào canon đã có, không có RAG, không dịch.
- **Đánh giá với LoreWeave:** Khác hoàn toàn.

#### NovelGenerator / AIStoryWriter (Ollama-based)
- **Mô tả:** Các tool viết novel dùng local LLM qua Ollama.
- **Điểm mạnh:** Self-host, privacy-friendly.
- **Điểm yếu:** Không có story knowledge, không có consistency enforcement, không có translation.
- **Đánh giá với LoreWeave:** Borrow Ollama integration pattern, không dùng logic.

---

### 2.3 Nhóm Platform/UI với RAG

#### ReNovel-AI
- **Nguồn:** GitHub (tiếng Trung) | **Interface:** Desktop app
- **Mô tả:** Desktop app với RAG long memory dùng ChromaDB, ba chế độ (writer/editor/assistant), card-based editor, tự vector hóa novel.
- **Điểm mạnh:** **Gần LoreWeave nhất** về mặt RAG + editing. Đã validate ChromaDB hoạt động tốt cho novel context.
- **Điểm yếu:** Focus vào *chỉnh sửa/tinh chỉnh* text — không có translation pipeline, không có story knowledge graph, không có canon safety, không có multi-user platform.
- **Đánh giá với LoreWeave:** Học cách dùng ChromaDB cho novel, không thay thế được.

---

### 2.4 So sánh tổng hợp

| Tính năng | andrewyng | TransAgents | Open-Translator | StoryCraftr | ReNovel-AI | **LoreWeave** |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| Multi-agent translation | ✅ | ✅ | ✅ | ❌ | ❌ | ✅ |
| Glossary / entity consistency | Một phần | ❌ | ✅ | ❌ | Một phần | ✅ |
| Story knowledge base (wiki, timeline) | ❌ | ❌ | ❌ | Một phần | Một phần | ✅ |
| RAG grounding | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ |
| Canon safety constraint | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Creative continuation agent | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ |
| Platform UI (multi-user, sharing) | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Self-host / OSS | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ (planned) |

---

## 3. Khoảng Trống Thị Trường

Sau khi phân tích, có thể xác định rõ khoảng trống mà không sản phẩm nào hiện tại lấp đầy:

**Khoảng trống thực sự:** Một platform có thể (1) nhận một tiểu thuyết đã tồn tại, (2) xây dựng knowledge base từ nó — nhân vật, timeline, world rules, quan hệ — rồi (3) dùng knowledge base đó để vừa dịch nhất quán, vừa hỗ trợ sáng tác tiếp theo đúng với canon.

Không có sản phẩm nào làm cả ba điều này trong một unified workflow. Đây là lý do LoreWeave có lý do để tồn tại.

---

## 4. Chiến Lược Hybrid: Build vs Borrow vs Reuse

Thay vì build từ đầu, LoreWeave nên áp dụng chiến lược hybrid — chỉ build những gì thực sự unique.

### 4.1 Reuse — Giữ nguyên từ repo hiện tại

Những phần này đã chạy tốt, không cần rewrite:

- **`translate_pipeline.py`** — stage order, chunking, retry logic → wrap thành LangGraph nodes
- **`llm_client.py`** — OpenAI-compatible gateway → thêm LiteLLM router lên trên
- **`prompts/`** — stage templates → chuyển thành versioned prompt registry
- **Existing JSONL artifacts** (timeline, metadata, scenes) → seed data cho RAG indexing

### 4.2 Borrow — Tích hợp OSS thay vì tự build

| Component | Tool | Lý do chọn |
|---|---|---|
| Graph + vector RAG | **LightRAG** (Apache 2.0) | Kết hợp graph traversal + semantic search — lý tưởng cho entity relationships trong novel |
| Vector store | **ChromaDB** | Self-host dễ nhất, đã validate với novel context (ReNovel-AI) |
| Model routing & self-host | **Ollama + LiteLLM** | Ollama chạy local models, LiteLLM làm unified gateway để route theo cost/quality |
| Workflow orchestration | **LangGraph** | State machine, retry, branching — không tự viết |
| Reflect-improve pattern | **andrewyng/translation-agent** | Borrow kỹ thuật, không dùng code nguyên xi |

### 4.3 Build — Chỉ phần unique value

Đây là ba thứ không có ở bất kỳ OSS nào và là lý do LoreWeave tồn tại:

**`StoryWikiBuilderAgent`**
Pipeline chuyển JSONL artifacts thành structured wiki pages với entity relationships, confidence scores, và source evidence pointers. Đây là "brain" của platform — prerequisite cho mọi tính năng downstream.

**`Canon Safety Guard`**
Layer kiểm tra trước generation: timeline lock (không retcon sự kiện đã xảy ra), POV lock, no-contradiction với indexed facts. Không có OSS nào làm điều này đủ nghiêm túc cho novel context.

**`StoryContinuationAgent`**
Agent sáng tác được grounding bởi context pack từ wiki + retriever. Khác với ChatGPT thuần túy ở chỗ nó *biết* canon của cuốn sách cụ thể và không hallucinate chi tiết đã được establish.

### 4.4 Phân bổ effort ước tính

```
Reuse (pipeline cũ)      ████░░░░░░░░░░░░░░░░  ~15%
Borrow / integrate OSS   ████████░░░░░░░░░░░░  ~25%
Build unique             ████████████████████  ~60%
```

---

## 5. Kiến Trúc Hybrid Đề Xuất

```
┌─────────────────────────────────────────────────────┐
│                   INGESTION LAYER                   │
│  translate_pipeline.py  │  Reflect loop  │  Normalizer│
│       [REUSE]           │   [BORROW]     │  [BUILD thin]│
└──────────────────────────────┬──────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────┐
│                  KNOWLEDGE LAYER                    │
│  LightRAG          │  ChromaDB     │  StoryWikiBuilder│
│  [BORROW]          │  [BORROW]     │  [BUILD ★]      │
└──────────────────────────────┬──────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────┐
│                  RETRIEVAL LAYER                    │
│  Canon Safety Guard  │  HybridRetriever │ ContextPacker│
│  [BUILD ★]           │  [BORROW]        │ [BUILD thin] │
└──────────────────────────────┬──────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────┐
│                 GENERATION LAYER                    │
│  LangGraph          │  Ollama+LiteLLM  │  StoryContinuation│
│  [BORROW]           │  [BORROW]        │  Agent [BUILD ★]  │
└─────────────────────────────────────────────────────┘
```

★ = unique value, không có OSS thay thế

---

## 6. Roadmap Triển Khai

Với constraint **self-host + cost thấp** và priority **creative continuation**:

### Giai đoạn 1 — Foundation (Tuần 1–2)
- Setup Ollama + LiteLLM + ChromaDB local
- Index novel đầu tiên từ JSONL artifacts có sẵn
- Validate retrieval cơ bản hoạt động

### Giai đoạn 2 — Knowledge Core (Tuần 3–4)
- Build `StoryWikiBuilderAgent` — chuyển JSONL → structured wiki
- Đây là prerequisite cho toàn bộ hệ thống

### Giai đoạn 3 — Safety & Retrieval (Tuần 5–6)
- Build `Canon Safety Guard` — timeline lock, no-retcon rules
- Build `ContextPacker` — assemble grounded context với citations
- Test với retrieval queries thực tế

### Giai đoạn 4 — Creative Agent (Tuần 7–8)
- Build `StoryContinuationAgent` trên LangGraph
- Kết nối với context pack từ Giai đoạn 3
- Test end-to-end: novel input → wiki → continuation output

### Giai đoạn 5 — Sau v1 (Tương lai)
- UI (dashboard, book studio, knowledge hub)
- Multi-user, ownership, sharing
- Translation pipeline integration
- Public platform features

> **Lưu ý:** UI và platform features **không cần thiết cho v1** của creative continuation. Ưu tiên core pipeline chạy đúng trước.

---

## 7. Rủi Ro & Quyết Định Còn Mở

| Rủi ro | Mức độ | Mitigation |
|---|:---:|---|
| LightRAG chưa mature cho production | Trung bình | Có thể fallback về ChromaDB + BM25 thuần |
| Quality variance giữa local models (Ollama) và API models | Cao | LiteLLM routing — dùng API cho tasks quan trọng, local cho tasks phụ |
| StoryWikiBuilder output quality thấp với novel phức tạp | Cao | Bắt đầu với novel đơn giản, iterate schema trước khi mở rộng |
| Canon Safety Guard quá strict → block creative generation | Trung bình | Design theo severity level, không binary block |

**Quyết định cần finalize trước khi code:**
1. Local model nào dùng qua Ollama cho translation vs creative tasks? (Qwen2.5, Llama 3.1, hay Mistral?)
2. LightRAG hay ChromaDB + BM25 thuần cho v1? (LightRAG powerful hơn nhưng phức tạp hơn)
3. Schema của StoryWikiPage — cần define trước khi build builder

---

## 8. Kết Luận

LoreWeave có lý do rõ ràng để tồn tại vì không có sản phẩm OSS nào hiện tại giải quyết được giao điểm của translation consistency + story knowledge graph + canon-safe creative continuation.

Chiến lược đúng đắn là **không reinvent những gì đã tốt** — reuse pipeline cũ, borrow OSS ecosystem (LightRAG, ChromaDB, LangGraph, Ollama), và dành toàn bộ engineering effort cho ba thứ thực sự unique: `StoryWikiBuilderAgent`, `Canon Safety Guard`, và `StoryContinuationAgent`.

Với constraint self-host và cost thấp, stack Ollama + LiteLLM + ChromaDB là lựa chọn phù hợp nhất để bắt đầu — và có thể scale lên sau khi v1 validate được core value proposition.

---

*Tài liệu này được tổng hợp dựa trên phân tích cạnh tranh OSS tháng 3/2026 và 01_PROJECT_OVERVIEW.md của LoreWeave.*






