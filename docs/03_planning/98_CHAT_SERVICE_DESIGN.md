# 98 — Chat Service Design

## Document Metadata

- Document ID: LW-PLAN-98
- Version: 1.1.0
- Status: Draft — Pending Approval
- Owner: Tech Lead + PM
- Last Updated: 2026-03-29
- Summary: End-to-end design for the Chat Service feature — real-time AI streaming chat with session management, universal output storage, and deep integration with the existing provider-registry infrastructure.

---

## 1. Goals and Scope

### What we are building

A standalone **Chat Service** that gives users a Cursor AI / LM Studio-style chat interface backed by their own configured AI providers. Key capabilities:

| Capability | Detail |
| ---------- | ------ |
| **Real-time streaming** | Token-by-token response rendering via SSE as the model generates output |
| **Session management** | Create, rename, delete, archive chat sessions; full message history persisted |
| **Message editing** | Edit a user message and re-run from that point (like Cursor); regenerate last assistant turn |
| **Universal output storage** | Every AI response is persisted as a typed output artifact (text, code, image, audio, video, file) |
| **Output portability** | Copy artifact to clipboard, paste into other pages (Chapter Editor, Glossary), download as file, save to book/chapter |
| **Multi-provider** | Works with any provider/model already configured via M03 provider-registry: OpenAI, Anthropic, Ollama, LM Studio |

### Out of scope (for this design)

- Image/audio *generation* models (DALL-E, Stable Diffusion, TTS) — Phase 2
- Web search / tool use / function calling — Phase 3
- Sharing chat sessions publicly — deferred

---

## 2. Technology Decision

### 2.1 Library Research

#### Backend AI streaming

| Library | Language | Providers | Streaming | Decision |
| ------- | -------- | --------- | --------- | -------- |
| **LiteLLM** (`litellm`) | Python | 100+ (OpenAI, Anthropic, Ollama, LM Studio, Cohere, Gemini…) | ✅ Native async `acompletion(..., stream=True)` | ✅ **CHOSEN** |
| OpenAI Python SDK | Python | OpenAI only | ✅ `.stream()` context | ❌ Single provider |
| Anthropic Python SDK | Python | Anthropic only | ✅ `.stream()` context | ❌ Single provider |
| Go net/http + per-adapter | Go | Must implement each | ⚠️ Manual SSE per provider | ❌ Too much boilerplate |
| LangChain | Python | 50+ | ✅ | ❌ Too heavy, unstable API |

**Why LiteLLM:**
- One interface for ALL our providers — no per-provider streaming adapter code
- `await litellm.acompletion(model, messages, stream=True)` → async generator of `ModelResponse` chunks
- Custom `base_url` param → supports Ollama and LM Studio local endpoints out of the box
- Automatic token counting, cost tracking, error normalization across providers
- Actively maintained, Apache-2.0 license
- 10k+ GitHub stars

#### Frontend SSE / Streaming + Chat State

| Library | Approach | Decision |
| ------- | -------- | -------- |
| **Vercel AI SDK `useChat`** (`ai/react`) | Full hook: message state, streaming, loading, stop, edit. Works with **any backend** that implements the AI SDK data stream protocol (language-agnostic) | ✅ **CHOSEN** |
| `@microsoft/fetch-event-source` | POST + SSE + auth headers + auto-reconnect — but requires building all state management manually | ❌ Superseded |
| Native `EventSource` | GET only, no auth headers in spec | ❌ Cannot use POST |
| `fetch` + `ReadableStream` | Works but manual chunking / line-parsing + manual state | ❌ Too verbose |

**Why Vercel AI SDK `useChat`:**
- 23k+ GitHub stars, production-ready, Apache-2.0
- Manages ALL frontend chat state: `messages`, `input`, `isLoading`, `stop()`, `append()`, `setMessages()`
- Replaces ~200 lines of custom hook code with ~5 lines
- **Backend language-agnostic** — the docs explicitly state: *"You can provide compatible API endpoints implemented in a different language such as Python."* An official "AI SDK Python Streaming" template exists
- Protocol is open and documented → Python FastAPI can implement it exactly
- Supports `headers` param for passing JWT tokens
- `stop()` built-in for cancelling in-flight streams

**What `useChat` replaces that we would have had to build:**
- SSE connection lifecycle (connect, parse, reconnect)
- Streaming text accumulation into message bubbles
- Loading/error state management
- Input controlled component handling
- Optimistic message insertion

#### Frontend chat rendering

| Library | Use | Decision |
| ------- | --- | -------- |
| `react-markdown` | Render markdown in assistant messages | ✅ **CHOSEN** |
| `rehype-highlight` | Syntax highlighting in code blocks | ✅ **CHOSEN** |
| `react-textarea-autosize` | Auto-expanding chat input | ✅ **CHOSEN** |
| shadcn/ui | UI primitives (already in project) | ✅ Already present |

#### Output / File storage

| Option | Decision |
| ------ | -------- |
| MinIO (S3-compatible, self-hosted) | ✅ **CHOSEN** — already fits the self-hosted model of this project |
| AWS S3 | ❌ Requires external cloud dependency |
| Store blobs in PostgreSQL | ❌ DB not suited for large binary files |

---

### 2.2 Service Language Decision

| Service | Language | Reason |
| ------- | -------- | ------ |
| `chat-service` | **Python / FastAPI** | LiteLLM is Python-native; FastAPI `StreamingResponse` is the cleanest SSE implementation; consistent with `translation-service` |
| `provider-registry-service` | Go (unchanged) | Add one new internal endpoint for credential resolution |
| `api-gateway-bff` | NestJS (add proxy route) | Minimal change |
| Frontend | React/TypeScript | Consistent with project |

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Browser (React)                            │
│  ChatPage ──► useChat hook ──► fetchEventSource (SSE POST)          │
│                               + useSessions hook (REST CRUD)        │
└─────────────────────────┬──────────────────────────────────────────┘
                          │ JWT Bearer  /v1/chat/*
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    api-gateway-bff (NestJS)                         │
│   /v1/chat/* ──────────────────────────► proxy → chat-service:8090  │
│   /v1/model-registry/* ──────────────► proxy → provider-registry    │
└─────────────────────────┬───────────────────────────────────────────┘
                          │ internal HTTP (no external exposure)
          ┌───────────────┴───────────────────────────────┐
          ▼                                               ▼
┌─────────────────────┐                       ┌──────────────────────┐
│   chat-service      │ GET /internal/        │ provider-registry    │
│   (Python/FastAPI)  │ credentials/{id}      │ -service (Go)        │
│                     │◄─────────────────────►│                      │
│  • Session CRUD     │                       │  • Credential store  │
│  • Message persist  │                       │  • AES decrypt       │
│  • LiteLLM invoke   │                       │  • User/platform     │
│  • SSE stream       │                       │    model catalog     │
│  • Output storage   │                       └──────────────────────┘
└──────────┬──────────┘
           │                                  ┌──────────────────────┐
           │ log usage                        │ usage-billing-service│
           ├─────────────────────────────────►│  (record tokens,     │
           │                                  │   billing decision)  │
           │                                  └──────────────────────┘
           │
           │ store files                      ┌──────────────────────┐
           └─────────────────────────────────►│ MinIO (S3-compat.)   │
                                              │  bucket: lw-chat     │
                                              └──────────────────────┘

  ┌────────────────────────────────────────────────────────────────┐
  │              PostgreSQL — loreweave_chat database              │
  │  chat_sessions · chat_messages · chat_outputs                  │
  └────────────────────────────────────────────────────────────────┘
```

### Data flow — send message + stream

```
1. User types message → POST /v1/chat/sessions/{id}/messages (SSE)
2. Gateway proxies to chat-service (streams response)
3. chat-service persists user message → chat_messages
4. chat-service calls GET /internal/credentials/{model_ref} → provider-registry
5. provider-registry decrypts API key and returns {provider_kind, base_url, api_key, model_name}
6. chat-service calls litellm.acompletion(model, messages, stream=True, api_key=..., base_url=...)
7. LiteLLM calls provider (OpenAI/Anthropic/Ollama/LM Studio) and yields token chunks
8. For each chunk: chat-service writes SSE event → gateway → frontend
9. Frontend appends token to message bubble in real time
10. When stream ends:
    a. chat-service persists assistant message + output artifact → chat_messages + chat_outputs
    b. chat-service logs usage → usage-billing-service (async, does not block stream)
    c. Final SSE event carries message_id + output_id for frontend to attach
```

---

## 4. Data Model — `loreweave_chat` Database

### 4.1 Tables

```sql
-- ── Sessions ─────────────────────────────────────────────────────────────────
CREATE TABLE chat_sessions (
  session_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id     UUID NOT NULL,
  title             VARCHAR(255) NOT NULL DEFAULT 'New Chat',
  model_source      VARCHAR(20) NOT NULL,            -- 'user_model' | 'platform_model'
  model_ref         UUID NOT NULL,                   -- FK to user_models or platform_models
  system_prompt     TEXT,
  status            VARCHAR(20) NOT NULL DEFAULT 'active', -- 'active' | 'archived'
  message_count     INT NOT NULL DEFAULT 0,
  last_message_at   TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_chat_sessions_owner ON chat_sessions (owner_user_id, status, last_message_at DESC);

-- ── Messages ─────────────────────────────────────────────────────────────────
CREATE TABLE chat_messages (
  message_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id        UUID NOT NULL REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
  owner_user_id     UUID NOT NULL,
  role              VARCHAR(20) NOT NULL,  -- 'user' | 'assistant' | 'system'
  content           TEXT NOT NULL,         -- plain text (or JSON for multi-part, see content_parts)
  content_parts     JSONB,                 -- [{type:'text',text:'...'},{type:'image_url',url:'...'}]
  sequence_num      INT NOT NULL,          -- ordering within session (monotonically increasing)
  input_tokens      INT,
  output_tokens     INT,
  model_ref         UUID,                  -- model used (assistant messages only)
  usage_log_id      UUID,                  -- FK to usage-billing (populated after stream)
  is_error          BOOLEAN NOT NULL DEFAULT false,
  error_detail      TEXT,
  parent_message_id UUID REFERENCES chat_messages(message_id),  -- for edit/branch history
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (session_id, sequence_num)
);
CREATE INDEX idx_chat_messages_session ON chat_messages (session_id, sequence_num);

-- ── Output Artifacts ─────────────────────────────────────────────────────────
CREATE TABLE chat_outputs (
  output_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id        UUID NOT NULL REFERENCES chat_messages(message_id) ON DELETE CASCADE,
  session_id        UUID NOT NULL,
  owner_user_id     UUID NOT NULL,
  output_type       VARCHAR(20) NOT NULL,   -- 'text' | 'code' | 'image' | 'audio' | 'video' | 'file'
  title             VARCHAR(255),           -- user-editable label
  content_text      TEXT,                  -- for text / code outputs
  language          VARCHAR(50),           -- for code outputs (e.g. 'python', 'typescript')
  storage_key       VARCHAR(512),          -- MinIO object key (for binary outputs)
  mime_type         VARCHAR(100),
  file_name         VARCHAR(255),
  file_size_bytes   BIGINT,
  metadata          JSONB,                 -- {width, height} for images; {duration} for audio/video
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_chat_outputs_session ON chat_outputs (session_id, created_at DESC);
CREATE INDEX idx_chat_outputs_owner   ON chat_outputs (owner_user_id, output_type, created_at DESC);
```

### 4.2 Key design decisions

| Decision | Rationale |
| -------- | --------- |
| `content_parts JSONB` on messages | Supports future multi-modal user messages (image + text) without schema change |
| `parent_message_id` self-reference | Enables "edit and re-run from here" — branching history without deleting originals |
| Separate `chat_outputs` table | Outputs are independent of messages — user can save, rename, paste to other UIs regardless of session state |
| MinIO for binary outputs | DB stays small; images/audio/video stored in object store with signed URL download |
| `sequence_num` monotonic | Stable ordering even if created_at has same millisecond (concurrent inserts) |

---

## 5. Backend API — `chat-service`

### 5.1 Session Endpoints

```
POST   /v1/chat/sessions
  Body: { model_source, model_ref, system_prompt?, title? }
  → 201 ChatSession

GET    /v1/chat/sessions?status=active&limit=50&cursor=...
  → 200 { items: ChatSession[], next_cursor }

GET    /v1/chat/sessions/{session_id}
  → 200 ChatSession (includes last N messages inline for initial load)

PATCH  /v1/chat/sessions/{session_id}
  Body: { title?, system_prompt?, model_source?, model_ref?, status? }
  → 200 ChatSession

DELETE /v1/chat/sessions/{session_id}
  → 204 (cascades to messages + outputs)
```

### 5.2 Message Endpoints

```
GET    /v1/chat/sessions/{session_id}/messages?limit=50&before_seq=...
  → 200 { items: ChatMessage[] }  (paged by sequence_num, descending)

POST   /v1/chat/sessions/{session_id}/messages          ← STREAMING ENDPOINT
  Headers: Accept: text/event-stream
  Body: { content: string, edit_from_sequence?: int }
  → 200 text/event-stream (SSE)

  SSE Events:
    data: {"type":"message_start","message_id":"uuid","role":"assistant"}
    data: {"type":"content_delta","delta":"Hello"}
    data: {"type":"content_delta","delta":" world"}
    data: {"type":"message_end","message_id":"uuid","output_id":"uuid","usage":{"input_tokens":80,"output_tokens":25}}
    data: [DONE]

  On error:
    data: {"type":"error","code":"provider_unavailable","detail":"..."}

DELETE /v1/chat/sessions/{session_id}/messages/{message_id}
  → 204
```

**`edit_from_sequence` behavior:**
When set, messages after that sequence number are soft-deleted (marked `is_deleted=true` or moved to history) and the new user message + assistant response branch from that point.

### 5.3 Output Endpoints

```
GET    /v1/chat/sessions/{session_id}/outputs?type=text&limit=50
  → 200 { items: ChatOutput[] }

GET    /v1/chat/outputs/{output_id}
  → 200 ChatOutput (includes content_text or signed download URL)

PATCH  /v1/chat/outputs/{output_id}
  Body: { title? }
  → 200 ChatOutput

DELETE /v1/chat/outputs/{output_id}
  → 204

GET    /v1/chat/outputs/{output_id}/download
  → 302 redirect to signed MinIO URL (for binary outputs)
  → 200 text/plain (for text outputs, inline)

GET    /v1/chat/sessions/{session_id}/export?format=markdown|json|text
  → 200 with Content-Disposition: attachment
```

### 5.4 Internal endpoint on `provider-registry-service`

New endpoint added to provider-registry (Go), **not exposed through gateway**:

```
GET /internal/credentials/{model_source}/{model_ref}
  → 200 {
    provider_kind: "openai" | "anthropic" | "ollama" | "lm_studio",
    provider_model_name: "gpt-4o-mini",
    base_url: "https://api.openai.com/v1",
    api_key: "<decrypted>",   ← only on internal network
    context_length: 128000
  }
```

Called only by internal services; never proxied by gateway.

---

## 6. Streaming Implementation Detail

### 6.1 AI SDK Data Stream Protocol

The Vercel AI SDK `useChat` hook uses a documented, language-agnostic **data stream protocol**.
Our Python backend must emit this format — no Node.js required.

**Required response headers:**
```
Content-Type: text/event-stream
x-vercel-ai-ui-message-stream: v1
Cache-Control: no-cache
```

**SSE event format (data stream protocol v1):**
```
# Text delta — sent for every token chunk
data: {"type":"text-delta","delta":"Hello"}

# Finish — sent once at stream end
data: {"type":"finish-message","finishReason":"stop","usage":{"promptTokens":80,"completionTokens":25}}

# Stream terminator
data: [DONE]

# Error (if something goes wrong)
data: {"type":"error","errorText":"provider_unavailable: ..."}
```

We also send a **custom data annotation** in the finish event to carry our backend-specific IDs (message_id, output_id) back to the frontend:

```
data: {"type":"data","data":[{"message_id":"uuid","output_id":"uuid"}]}
data: {"type":"finish-message","finishReason":"stop","usage":{...}}
data: [DONE]
```

### 6.2 Backend (FastAPI + LiteLLM)

```python
# services/chat-service/app/routers/messages.py

import json, asyncio
from uuid import uuid4
from litellm import acompletion
from fastapi.responses import StreamingResponse

async def stream_chat(session_id, body, user_id, db, credential_client):
    # 1. Load history + append new user message
    history = await db.get_messages(session_id, limit=50)
    messages = [{"role": m.role, "content": m.content} for m in history]
    messages.append({"role": "user", "content": body.content})

    # 2. Resolve credentials from provider-registry (internal)
    creds = await credential_client.resolve(body.model_source, body.model_ref)

    # 3. LiteLLM model string: "openai/gpt-4o-mini", "anthropic/claude-3-5-sonnet-20241022",
    #    "ollama/llama3.2", "openai/local-model" (LM Studio, OpenAI-compatible)
    model = f"{creds.provider_kind}/{creds.provider_model_name}"

    # 4. Persist user message before streaming starts
    await db.insert_message(session_id, "user", body.content)

    async def event_generator():
        full_content: list[str] = []
        last_chunk = None

        try:
            response = await acompletion(
                model=model,
                messages=messages,
                stream=True,
                api_key=creds.api_key,
                base_url=creds.base_url,
                timeout=300,
            )
            async for chunk in response:
                last_chunk = chunk
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    full_content.append(delta)
                    # AI SDK data stream protocol: text-delta event
                    yield f'data: {json.dumps({"type":"text-delta","delta":delta})}\n\n'

            # 5. Persist assistant message + text output artifact
            final_text = "".join(full_content)
            msg_id = str(uuid4())
            await db.insert_message(session_id, "assistant", final_text, message_id=msg_id)
            output = await db.insert_text_output(msg_id, final_text)

            usage = last_chunk.usage if last_chunk else None

            # 6. Send our custom IDs back as a data annotation
            yield f'data: {json.dumps({"type":"data","data":[{"message_id":msg_id,"output_id":str(output.output_id)}]})}\n\n'

            # 7. Finish event (AI SDK protocol)
            finish_payload = {
                "type": "finish-message",
                "finishReason": "stop",
                "usage": {
                    "promptTokens": usage.prompt_tokens if usage else 0,
                    "completionTokens": usage.completion_tokens if usage else 0,
                },
            }
            yield f'data: {json.dumps(finish_payload)}\n\n'

            # 8. Log usage to billing async (non-blocking)
            if usage:
                asyncio.create_task(log_usage(usage, creds, user_id))

        except Exception as e:
            yield f'data: {json.dumps({"type":"error","errorText":str(e)})}\n\n'

        yield 'data: [DONE]\n\n'

    headers = {
        "x-vercel-ai-ui-message-stream": "v1",
        "Cache-Control": "no-cache",
    }
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)
```

### 6.3 LiteLLM Provider Model Strings

| Provider | Config | LiteLLM model string |
| -------- | ------ | -------------------- |
| OpenAI | api_key from creds | `openai/gpt-4o-mini` |
| Anthropic | api_key from creds | `anthropic/claude-3-5-sonnet-20241022` |
| Ollama (local) | base_url = `http://localhost:11434` | `ollama/llama3.2` |
| LM Studio | base_url = `http://localhost:1234/v1` | `openai/local-model` (OpenAI-compatible) |

### 6.4 Frontend (React + Vercel AI SDK `useChat`)

The `useChat` hook handles ALL streaming state — messages, loading, stop, error — out of the box.

```typescript
// frontend/src/features/chat/components/ChatWindow.tsx
import { useChat } from 'ai/react';

export function ChatWindow({ sessionId }: { sessionId: string }) {
  const token = useAuthToken();

  const { messages, input, handleInputChange, handleSubmit, isLoading, stop, data } =
    useChat({
      api: `/v1/chat/sessions/${sessionId}/messages`,
      headers: { Authorization: `Bearer ${token}` },
      // Custom data annotations come through in `data` array
      onFinish(message) {
        // message.id, full content available here for post-processing
      },
      onError(error) {
        toast.error(`Chat error: ${error.message}`);
      },
    });

  return (
    <div className="flex h-full flex-col">
      <MessageList messages={messages} isLoading={isLoading} chatData={data} />
      <form onSubmit={handleSubmit}>
        <ChatInputBar
          value={input}
          onChange={handleInputChange}
          isLoading={isLoading}
          onStop={stop}
        />
      </form>
    </div>
  );
}
```

**What `useChat` eliminates vs our old custom hook:**

| Was manual | Now handled by `useChat` |
| ---------- | ------------------------ |
| SSE connection + reconnect | ✅ Built-in |
| Token accumulation into message | ✅ Built-in |
| Optimistic user message insert | ✅ Built-in |
| `isLoading` state | ✅ Built-in |
| `stop()` — cancel in-flight stream | ✅ Built-in |
| Error state + display | ✅ Built-in |
| Input controlled component | ✅ `input` + `handleInputChange` |
| Message list array management | ✅ `messages` |

---

## 7. Frontend Component Design

### 7.1 Page layout (Cursor/LM Studio style)

```
┌────────────────────────────────────────────────────────────────────┐
│  [← Back]  Chat                                          [⚙ Model] │
├───────────────┬────────────────────────────────────────────────────│
│  Sessions     │  MessageList                                        │
│  ─────────── │  ─────────────────────────────────────────────────  │
│  + New Chat   │  [User bubble]  Hello, summarize this              │
│               │                                                     │
│  ▶ My Chat 1  │  [Assistant bubble]                                 │
│    My Chat 2  │    Here is a summary...  (streaming cursor ▊)       │
│    My Chat 3  │                                                     │
│    ─────────  │    [OutputCard] 📄 Text artifact  [Copy] [Save]     │
│  [Archived]   │                                                     │
│               │  ─────────────────────────────────────────────────  │
│               │  [ChatInput textarea          ] [Send ↵]            │
└───────────────┴────────────────────────────────────────────────────┘
```

### 7.2 Component tree

```
ChatPage
├── SessionSidebar
│   ├── NewSessionButton
│   ├── SessionList
│   │   └── SessionItem (title, last message preview, delete/rename actions)
│   └── ModelSelectorBar (visible when creating new session)
│
└── ChatWindow (active session)
    ├── ChatHeader (session title, model badge, edit system prompt)
    ├── MessageList (virtualized scroll)
    │   ├── MessageBubble[role=user]
    │   │   └── UserMessage (text, edit button)
    │   └── MessageBubble[role=assistant]
    │       ├── AssistantMessage (react-markdown, streaming cursor)
    │       └── OutputCard[] (one per artifact extracted from response)
    │           ├── CopyButton (to clipboard)
    │           ├── SaveButton (opens destination picker: editor/glossary/download)
    │           └── DownloadButton
    └── ChatInputBar
        ├── Textarea (react-textarea-autosize)
        ├── SendButton (disabled while streaming)
        └── StopButton (shown while streaming, cancels SSE)
```

### 7.3 OutputCard — Universal output portability

When the assistant produces a response containing a code block, image, or other structured output, it is extracted and stored as a `chat_output`. The `OutputCard` component:

```
┌────────────────────────────────────────────────────────────┐
│ 📄 Text  |  🖼 Image  |  💻 Code (python)  |  📁 File      │
├────────────────────────────────────────────────────────────┤
│ [Preview of content — truncated if long]                   │
├────────────────────────────────────────────────────────────┤
│ [Copy to clipboard]  [Paste to Editor]  [Save to Chapter]  │
│ [Save to Glossary]   [Download]                            │
└────────────────────────────────────────────────────────────┘
```

**Output extraction logic (backend):**
- Full response text → always stored as `output_type=text`
- Fenced code blocks (` ```lang `) → extracted as separate `output_type=code` artifacts
- In future: image URLs in response → `output_type=image`

**"Paste to Editor"** integration:
- Fires a custom DOM event / Zustand action
- `ChapterEditorPageV2` listens and inserts the text at cursor position
- Uses the same `onChange` pipeline as the existing Lexical / ChunkEditor

---

## 8. Service Structure — `chat-service`

```
services/chat-service/
├── Dockerfile
├── requirements.txt              # fastapi, litellm, asyncpg, aiofiles, boto3, uvicorn
├── app/
│   ├── main.py                   # FastAPI app + lifespan, CORS, auth middleware
│   ├── config.py                 # settings (DB URL, MinIO, provider-registry URL)
│   ├── db/
│   │   ├── pool.py               # asyncpg pool init
│   │   └── migrate.py            # run DDL on startup
│   ├── middleware/
│   │   └── auth.py               # validate JWT via auth-service (same pattern as translation-service)
│   ├── client/
│   │   ├── provider_client.py    # GET /internal/credentials/{source}/{ref}
│   │   └── billing_client.py     # POST to usage-billing-service
│   ├── storage/
│   │   └── minio_client.py       # upload/download/sign via boto3 S3 client
│   ├── routers/
│   │   ├── sessions.py           # CRUD sessions
│   │   ├── messages.py           # send message (SSE streaming)
│   │   └── outputs.py            # output CRUD, download, export
│   ├── services/
│   │   ├── stream_service.py     # LiteLLM invocation + SSE generator
│   │   └── output_extractor.py   # parse code blocks / structured content from response
│   └── models.py                 # Pydantic models for request/response
```

---

## 9. Integration Changes — Existing Services

### 9.1 `provider-registry-service` (Go) — minimal change

Add one new internal route (not registered on the external-facing router):

```go
// services/provider-registry-service/internal/api/internal_server.go
// Separate HTTP server on port 8082 (internal only, NOT proxied by gateway)

GET /internal/credentials/:model_source/:model_ref
```

Returns decrypted credentials for the model ref. Requires `X-Internal-Token` header (shared secret between services, set via env var `INTERNAL_SERVICE_TOKEN`).

### 9.2 `api-gateway-bff` (NestJS) — add proxy route

```typescript
// services/api-gateway-bff/src/gateway-setup.ts
// Add one line to the proxy setup:

'/v1/chat': process.env.CHAT_SERVICE_URL,   // http://chat-service:8090
```

Note: the internal port 8082 of provider-registry is **NOT** added here.

### 9.3 `docker-compose.yml`

```yaml
chat-service:
  build: ./services/chat-service
  ports:
    - "8090:8090"
  environment:
    - PORT=8090
    - DATABASE_URL=postgresql://loreweave:loreweave@postgres:5432/loreweave_chat
    - AUTH_SERVICE_URL=http://auth-service:8080
    - PROVIDER_REGISTRY_INTERNAL_URL=http://provider-registry-service:8082
    - USAGE_BILLING_SERVICE_URL=http://usage-billing-service:8084
    - MINIO_ENDPOINT=minio:9000
    - MINIO_ACCESS_KEY=${MINIO_ACCESS_KEY}
    - MINIO_SECRET_KEY=${MINIO_SECRET_KEY}
    - MINIO_BUCKET=lw-chat
    - INTERNAL_SERVICE_TOKEN=${INTERNAL_SERVICE_TOKEN}
  depends_on:
    - postgres
    - provider-registry-service
    - usage-billing-service
    - minio

minio:
  image: minio/minio:latest
  command: server /data --console-address ":9001"
  ports:
    - "9000:9000"
    - "9001:9001"
  environment:
    - MINIO_ROOT_USER=${MINIO_ACCESS_KEY}
    - MINIO_ROOT_PASSWORD=${MINIO_SECRET_KEY}
  volumes:
    - minio_data:/data

infra/postgres/init/01-databases.sql:
  → add: CREATE DATABASE loreweave_chat;
```

---

## 10. Frontend — File Structure

```
frontend/src/
├── pages/
│   └── ChatPage.tsx
├── features/chat/
│   ├── types.ts                    # ChatSession, ChatMessage, ChatOutput
│   ├── api.ts                      # REST-only API client (sessions, outputs CRUD — NOT the stream)
│   ├── hooks/
│   │   ├── useSessions.ts          # session list CRUD
│   │   └── useOutputActions.ts     # copy/paste/save/download output artifacts
│   └── components/
│       ├── SessionSidebar.tsx
│       ├── SessionItem.tsx
│       ├── ChatWindow.tsx          # uses useChat from 'ai/react' directly
│       ├── ChatHeader.tsx
│       ├── MessageList.tsx
│       ├── MessageBubble.tsx
│       ├── AssistantMessage.tsx    # react-markdown + rehype-highlight + streaming cursor dot
│       ├── UserMessage.tsx
│       ├── OutputCard.tsx          # universal output artifact display
│       ├── OutputGallery.tsx       # all outputs for a session
│       ├── ChatInputBar.tsx        # react-textarea-autosize + send/stop buttons
│       └── SystemPromptModal.tsx
```

**npm packages to add:**
```
ai            # Vercel AI SDK — useChat hook
react-markdown
rehype-highlight
react-textarea-autosize
```

**Note:** No `@microsoft/fetch-event-source` needed. The `ai` package handles all SSE internally.

**Route:** `/chat` or `/workspace/chat` (protected)

---

## 11. Implementation Phases

### Phase 1 — Core chat with streaming (P0)

**Backend:**
- `loreweave_chat` DB + DDL migration
- `chat-service` skeleton (FastAPI + asyncpg + auth middleware)
- Session CRUD endpoints
- Messages: persist + stream via LiteLLM
- Internal credential resolver in provider-registry (port 8082)
- docker-compose integration + gateway proxy route
- Unit tests: session CRUD handlers, stream event format

**Frontend:**
- `ChatPage` with sidebar + message list + input
- `useChat` hook (fetchEventSource + streaming state)
- `useSessions` hook (CRUD)
- `AssistantMessage` with react-markdown + streaming cursor
- Route registration

**AT scenarios (Phase 1):**
- Send message → stream tokens in real time → message persisted
- Create / rename / delete session
- Session persists across reload (fetch from API)
- All providers work: OpenAI, Anthropic, Ollama, LM Studio
- 401 without token; 403 for another user's session

### Phase 2 — Output storage + portability (P1)

**Backend:**
- `chat_outputs` table + output extractor (parse code blocks from response)
- Output CRUD + download endpoint
- MinIO bucket setup + signed URL generation
- Session export (markdown / JSON / text)

**Frontend:**
- `OutputCard` component
- Copy to clipboard
- "Paste to Editor" integration (custom event → ChapterEditorPageV2)
- Download button
- Session export UI

### Phase 3 — Message editing + history (P1)

**Backend:**
- `edit_from_sequence` in POST messages
- Soft-delete branched messages (add `is_deleted` column)
- Parent message ID chain for history browsing

**Frontend:**
- Edit button on user messages
- "Regenerate" button on assistant messages
- History branch indicator (optional)

### Phase 4 — Attachments + multi-modal (P2)

- User uploads image/file with message (stored in MinIO)
- Content parts sent to vision-capable models
- Audio output support (TTS API)
- Image generation output (DALL-E / SD)

---

## 12. Non-Functional Requirements

| Requirement | Target |
| ----------- | ------ |
| Streaming latency | First token delivered to frontend within 800ms of provider response start |
| SSE connection timeout | 10 min max (configurable); client auto-reconnects on drop |
| Message history load | Last 50 messages loaded on session open; older messages paginated |
| Output storage | Text artifacts stored in DB (no size limit); binary files in MinIO with max 50 MB per file |
| Session limit per user | Soft limit: 500 active sessions (oldest auto-archived) |
| DB transactions | Message insert + output insert in single transaction to ensure consistency |

---

## 13. Open Questions

| # | Question | Decision needed by |
| - | -------- | ----------------- |
| Q1 | Should MinIO be a new dependency or reuse an existing S3-compatible endpoint? | Tech Lead |
| Q2 | Should the "Paste to Editor" feature use Zustand global store or DOM custom events? | Frontend Lead |
| Q3 | Should the chat route live at `/chat` (top level) or inside a workspace/book context? | PM |
| Q4 | For "Save to Chapter": open a picker modal or auto-append? | PM / UX |
| Q5 | Should platform models (paid API) also be usable in chat, or user models only? | PM |

---

## 14. References

- `docs/03_planning/44_PHASE1_MODULE03_PROVIDER_REGISTRY_EXECUTION_PACK.md`
- `docs/03_planning/51_MODULE03_BACKEND_DETAILED_DESIGN.md`
- `services/provider-registry-service/internal/api/server.go` — invoke endpoint
- `services/translation-service/app/services/translation_runner.py` — existing provider call pattern
- `services/api-gateway-bff/src/gateway-setup.ts` — proxy routing pattern
- [LiteLLM docs](https://docs.litellm.ai/docs/) — unified LLM proxy library
- [Vercel AI SDK](https://ai-sdk.dev/) — `useChat` hook + data stream protocol spec
- [AI SDK Stream Protocol](https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol) — backend format spec for Python compatibility
- [AI SDK Python Streaming template](https://vercel.com/templates/next.js/ai-sdk-python-streaming) — official reference for Python + useChat integration
