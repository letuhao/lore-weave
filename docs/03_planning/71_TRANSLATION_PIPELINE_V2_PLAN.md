# Translation Pipeline V2 — Chunking, Session Context & Compact Logic
<!-- STATUS: APPROVED — implementation in progress -->

## Context

The current translation pipeline sends an entire chapter as a single prompt to the AI model. This breaks in two ways:
- **Context overflow**: A chapter with 10,000 characters may exceed the model's context window, causing the model to silently truncate or refuse.
- **Timeout cascade**: One giant prompt takes too long, hits the 502 timeout, and the whole chapter fails.

This plan introduces chunk-based translation with a persistent in-session conversation history (for style consistency across chunks) and an AI-driven compaction mechanism to prevent history from overflowing the context window.

---

## 1. Compact Model Suggestions

The compact step summarises already-translated conversation history into a brief "translation memo" so the session stays within the model's context window. It does NOT need to be the same model as the translation model — a lighter, cheaper model is ideal.

| Tier | Model | Notes |
|------|-------|-------|
| **Cloud — recommended** | `gpt-4o-mini` | Fastest, cheapest OpenAI option; excellent at structured summarisation |
| **Cloud — alternative** | `claude-3-haiku-20240307` | Anthropic equivalent; very fast, follows instructions precisely |
| **Local (Ollama/LM Studio)** | `llama3.2:3b` | 3 B params, fast on CPU/GPU; good for summarisation |
| **Local — minimal footprint** | `qwen2.5:1.5b` | Tiny but surprisingly capable at summarisation tasks |
| **Same model (default)** | *(translation model)* | Simplest UX; fine if the translation model is cheap/fast |

**Default**: Leave `compact_model_ref = NULL` = use the translation model. Power users can switch to a lighter model to cut costs.

---

## 2. Architecture Overview

```
Chapter text
    │
    ▼
chunk_splitter.py
  • Split on: \n  。！？…  . ! ?  (sentence/paragraph boundaries)
  • Max chunk size: min(chunk_size_tokens, context_length/4) tokens
  • Token estimate: len(text) / 3.5  (conservative mixed CJK/Latin ratio)
    │
    ▼ chunks[0..N]
session_translator.py  (new module, runs inside chapter_worker)
  ┌─────────────────────────────────────────────────┐
  │ session_history: list[{role, content}]           │
  │ compact_memo: str                                │
  │                                                  │
  │ for chunk in chunks:                             │
  │   messages = build_messages(chunk)               │
  │   translated = invoke(messages, timeout)         │
  │   session_history.append(user + assistant)       │
  │   if token_estimate(history) > context/2:        │
  │     compact_memo = compact(history, memo)        │
  │     session_history = []                         │
  └─────────────────────────────────────────────────┘
    │
    ▼
Concatenated translated chunks → chapter_translations.translated_body
```

---

## 3. Database Schema Changes

### `migrate.py` — additive ALTER statements (idempotent)

```sql
-- New columns on user_translation_preferences
ALTER TABLE user_translation_preferences
  ADD COLUMN IF NOT EXISTS compact_model_source TEXT,
  ADD COLUMN IF NOT EXISTS compact_model_ref     UUID,
  ADD COLUMN IF NOT EXISTS chunk_size_tokens     INT  NOT NULL DEFAULT 2000,
  ADD COLUMN IF NOT EXISTS invoke_timeout_secs   INT  NOT NULL DEFAULT 300;

-- New columns on book_translation_settings (mirror)
ALTER TABLE book_translation_settings
  ADD COLUMN IF NOT EXISTS compact_model_source TEXT,
  ADD COLUMN IF NOT EXISTS compact_model_ref     UUID,
  ADD COLUMN IF NOT EXISTS chunk_size_tokens     INT  NOT NULL DEFAULT 2000,
  ADD COLUMN IF NOT EXISTS invoke_timeout_secs   INT  NOT NULL DEFAULT 300;

-- Snapshot in job row so history is self-contained
ALTER TABLE translation_jobs
  ADD COLUMN IF NOT EXISTS compact_model_source TEXT,
  ADD COLUMN IF NOT EXISTS compact_model_ref     UUID,
  ADD COLUMN IF NOT EXISTS chunk_size_tokens     INT  NOT NULL DEFAULT 2000,
  ADD COLUMN IF NOT EXISTS invoke_timeout_secs   INT  NOT NULL DEFAULT 300;

-- Per-chapter chunk detail (observability; recovery re-starts from scratch)
CREATE TABLE IF NOT EXISTS chapter_translation_chunks (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  chapter_translation_id  UUID NOT NULL REFERENCES chapter_translations(id) ON DELETE CASCADE,
  chunk_index             INT  NOT NULL,
  chunk_text              TEXT NOT NULL,
  translated_text         TEXT,
  compact_memo_applied    TEXT,          -- memo that was in effect for this chunk
  status                  TEXT NOT NULL DEFAULT 'pending',
  input_tokens            INT,
  output_tokens           INT,
  created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (chapter_translation_id, chunk_index)
);
CREATE INDEX IF NOT EXISTS idx_ctc_ct ON chapter_translation_chunks(chapter_translation_id);
```

---

## 4. Backend Changes

### 4.1 `app/workers/chunk_splitter.py` — new file

```python
"""
Split chapter text into token-bounded chunks.
Splitting preference: paragraph break > sentence end > any whitespace.
"""

SENTENCE_ENDS = frozenset('.!?。！？…\n')
TOKEN_CHAR_RATIO = 3.5  # chars per token (conservative for mixed CJK/Latin)

def estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / TOKEN_CHAR_RATIO))

def split_chapter(text: str, max_tokens: int) -> list[str]:
    """Return list of chunks each ≤ max_tokens estimated tokens."""
    max_chars = int(max_tokens * TOKEN_CHAR_RATIO)
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break
        # Find best split point within max_chars
        window = remaining[:max_chars]
        # Prefer splitting at paragraph break (\n\n)
        split = window.rfind('\n\n')
        if split == -1:
            # Fall back: last sentence-ending char
            for i in range(len(window) - 1, -1, -1):
                if window[i] in SENTENCE_ENDS:
                    split = i + 1
                    break
        if split <= 0:
            # Hard split at max_chars
            split = max_chars
        chunks.append(remaining[:split].strip())
        remaining = remaining[split:].strip()
    return [c for c in chunks if c]
```

### 4.2 `app/workers/session_translator.py` — new file

Core logic for one chapter: translate all chunks with a rolling conversation history and compact when needed.

```python
"""
Session-based translation of a single chapter.
Maintains conversation history across chunks for style consistency.
Compacts history when it exceeds half the model context window.
"""
import json
import httpx
from .chunk_splitter import estimate_tokens, split_chapter
from ..auth import mint_user_jwt
from ..config import settings
from .content_extractor import extract_content

_JWT_TTL = 4 * 3600

DEFAULT_COMPACT_SYSTEM = (
    "You are a translation assistant. Summarise the following translation session history "
    "into a concise Translation Memo (200 words max). Include: key character names and their "
    "translations, recurring terminology, tone/style notes. Output ONLY the memo."
)

async def translate_chapter(
    chapter_text: str,
    msg: dict,        # full job message (model_source, model_ref, prompts, etc.)
    pool,
    chapter_translation_id,  # UUID for chunk rows
    *,
    context_window: int = 8192,
) -> tuple[str, int, int]:
    """
    Returns (translated_body, total_input_tokens, total_output_tokens).
    Raises _TransientError / _PermanentError (imported from chapter_worker).
    """
    chunk_size = msg.get("chunk_size_tokens", 2000)
    # Clamp: never exceed 1/4 of the model's context window
    chunk_size = min(chunk_size, context_window // 4)
    timeout_secs = msg.get("invoke_timeout_secs", 300) or None  # 0 → None (unlimited)

    chunks = split_chapter(chapter_text, chunk_size)
    session_history: list[dict] = []
    compact_memo: str = ""
    translated_parts: list[str] = []
    total_input = 0
    total_output = 0

    token = mint_user_jwt(msg["user_id"], settings.jwt_secret, ttl_seconds=_JWT_TTL)
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(connect=10.0, write=30.0, read=timeout_secs, pool=5.0)
    ) as client:
        for idx, chunk in enumerate(chunks):
            translated, in_tok, out_tok = await _translate_chunk(
                client, chunk, idx, len(chunks),
                msg, token, session_history, compact_memo, pool,
                chapter_translation_id,
            )
            translated_parts.append(translated)
            total_input  += in_tok
            total_output += out_tok

            # Append to session history
            user_content = _build_user_content(chunk, msg, idx)
            session_history.append({"role": "user",      "content": user_content})
            session_history.append({"role": "assistant", "content": translated})

            # Compact if history is consuming > 50% of context
            history_tokens = sum(estimate_tokens(m["content"]) for m in session_history)
            if history_tokens > context_window // 2:
                compact_memo = await _compact_history(
                    client, session_history, compact_memo, msg, token
                )
                session_history = []

    return "\n\n".join(translated_parts), total_input, total_output
```

Key helpers inside `session_translator.py`:

- **`_build_messages(chunk, msg, history, memo)`** — constructs the messages array: system prompt + (compact memo as assistant preamble if present) + session_history + new user chunk
- **`_translate_chunk(client, chunk, ...) → (str, int, int)`** — calls `/v1/model-registry/invoke`, writes chunk row to `chapter_translation_chunks`, returns translated text + token counts
- **`_compact_history(client, history, old_memo, msg, token) → str`** — invokes the compact model (`compact_model_source` / `compact_model_ref` from msg, falls back to translation model) with `DEFAULT_COMPACT_SYSTEM` and returns the new memo string

### 4.3 `app/workers/chapter_worker.py` — modify `_process_chapter`

Replace the single-invoke AI call block (lines 63–134) with:
```python
from .session_translator import translate_chapter

# After marking chapter running...
context_window = await _get_model_context_window(msg)  # see §4.4
translated_body, input_tokens, output_tokens = await translate_chapter(
    chapter_text=chapter.get("body") or "",
    msg=msg,
    pool=pool,
    chapter_translation_id=ct_id,   # UUID from chapter_translations row
    context_window=context_window,
)
```

Remove the inline `httpx.AsyncClient` block and the `extract_content` call (moved to `session_translator`).

### 4.4 `app/workers/chapter_worker.py` — add `_get_model_context_window`

```python
async def _get_model_context_window(msg: dict) -> int:
    """
    Query provider-registry-service for model context length.
    Falls back to 8192 if the model doesn't publish it (local models).
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(
                f"{settings.provider_registry_service_url}"
                f"/v1/model-registry/models/{msg['model_ref']}/context-window",
                params={"model_source": msg["model_source"]},
            )
            if r.status_code == 200:
                return r.json().get("context_window", 8192)
    except Exception:
        pass
    return 8192  # safe default for unknown models
```

### 4.5 `app/routers/settings.py` — propagate new fields

The `PreferencesPayload`, `BookSettingsPayload`, `UserTranslationPreferences`, `BookTranslationSettings` models in `models.py` must include:
```python
compact_model_source: Optional[str] = None
compact_model_ref: Optional[UUID] = None
chunk_size_tokens: int = 2000
invoke_timeout_secs: int = 300
```

The upsert SQL in `settings.py` must include the 4 new columns.

### 4.6 `app/routers/jobs.py` — snapshot new fields

When creating a job, snapshot `chunk_size_tokens`, `invoke_timeout_secs`, `compact_model_source`, `compact_model_ref` from effective settings into `translation_jobs`. Pass them in the coordinator message so `worker.py` / `chapter_worker.py` receive them in `msg`.

### 4.7 `app/workers/coordinator.py` — forward new fields

Add to the chapter message published by `handle_job_message`:
```python
"chunk_size_tokens":   msg["chunk_size_tokens"],
"invoke_timeout_secs": msg["invoke_timeout_secs"],
"compact_model_source": msg.get("compact_model_source"),
"compact_model_ref":   msg.get("compact_model_ref"),
```

### 4.8 Provider-Registry-Service — new endpoint

Add `GET /v1/model-registry/models/{model_ref}/context-window` to `server.go`:
```go
// Returns {"context_window": N} for the given model.
// For platform models: reads from static inventory.
// For user models: reads context_length from the user_models table (synced by syncInventory).
// Returns 200 with {"context_window": 8192} as a safe fallback if not found.
```

This endpoint is called internally (no auth header needed for the worker), so guard with an internal-only IP check or a simple shared secret header if desired.

---

## 5. Frontend Changes

### 5.1 `frontend/src/features/translation/api.ts`

Add new fields to `UserTranslationPreferences`, `BookTranslationSettings`, and `PreferencesPayload`:
```typescript
compact_model_source: ModelSource | null;
compact_model_ref: string | null;
chunk_size_tokens: number;       // default 2000
invoke_timeout_secs: number;     // default 300
```

### 5.2 `frontend/src/components/translation/AdvancedTranslationSettings.tsx` — new component

Collapsible `<details>` accordion labelled "Advanced settings":

**Section A — Compact model:**
```
[ ] Use same model for compaction (default checked)
    When unchecked: ModelSelector for compact model appears
    Info text: "Compaction summarises translation history when context is full.
                A lighter/cheaper model works well (e.g. gpt-4o-mini, llama3.2:3b)"
```

**Section B — Performance:**
```
Chunk size (tokens): [number input, default 2000]
  ↳ hint: "Each chunk ≈ chunk_size × 3.5 characters. Smaller = more API calls; larger = risk of context overflow."

AI timeout per chunk (seconds): [number input, default 300]
  ↳ hint: "Max wait for one AI response. Set 0 for unlimited (not recommended)."
```

### 5.3 `frontend/src/pages/BookTranslationPage.tsx` + Translation Settings page

Mount `<AdvancedTranslationSettings>` in the settings form below the `<PromptEditor>` in both pages. Wire its values into `form` state and save/load via the updated preferences API.

---

## 6. Files to Create

| File | Purpose |
|------|---------|
| `services/translation-service/app/workers/chunk_splitter.py` | Text chunking with sentence-boundary awareness |
| `services/translation-service/app/workers/session_translator.py` | Session loop: per-chunk invoke + compact trigger |
| `frontend/src/components/translation/AdvancedTranslationSettings.tsx` | UI: compact model + chunk size + timeout |

## 7. Files to Modify

| File | Change |
|------|--------|
| `services/translation-service/app/migrate.py` | ADD COLUMN x4 on 3 tables + new `chapter_translation_chunks` table |
| `services/translation-service/app/models.py` | Add 4 new fields to settings models + `ChapterTranslationChunk` model |
| `services/translation-service/app/config.py` | No change (new fields are per-user, not env-vars) |
| `services/translation-service/app/routers/settings.py` | Include new fields in upsert SQL and response |
| `services/translation-service/app/routers/jobs.py` | Snapshot new fields; include in coordinator message |
| `services/translation-service/app/workers/coordinator.py` | Forward new fields in chapter message |
| `services/translation-service/app/workers/chapter_worker.py` | Replace inline AI call with `translate_chapter()` |
| `services/provider-registry-service/internal/api/server.go` | Add `GET /v1/model-registry/models/{id}/context-window` |
| `frontend/src/features/translation/api.ts` | Add 4 new fields to types + payload |
| `frontend/src/pages/BookTranslationPage.tsx` | Mount `AdvancedTranslationSettings` |
| `frontend/src/pages/TranslationSettingsPage.tsx` (if exists) | Mount `AdvancedTranslationSettings` (only `BookTranslationPage` exists currently — build the global settings page too if missing) |

---

## 8. Implementation Sequence

1. DB migrations (`migrate.py`) — additive, safe to run immediately
2. `chunk_splitter.py` — pure function, easy to unit-test first
3. Provider-registry-service `context-window` endpoint
4. `session_translator.py` — core logic (depends on `chunk_splitter` + invoke endpoint)
5. Modify `chapter_worker.py` to call `translate_chapter()`
6. Modify `coordinator.py` + `jobs.py` to forward new fields
7. Update `models.py` + `settings.py` for new config fields
8. `AdvancedTranslationSettings.tsx` frontend component
9. Wire into `BookTranslationPage.tsx` and settings page

---

## 9. Verification

1. **Unit tests** — `test_chunk_splitter.py`: test empty, short-chapter (1 chunk), long chapter with CJK sentence ends, hard-split fallback
2. **Unit tests** — `test_session_translator.py`: mock invoke calls, verify compaction triggers at 50% context, verify compact model fallback
3. **Integration smoke test**:
   - Set `chunk_size_tokens = 50` (very small) on a short chapter → verify multiple rows in `chapter_translation_chunks`
   - Set `invoke_timeout_secs = 1` on a slow model → verify `_TransientError` fires and retries
4. **Full pipeline test**: translate a real 3000-character chapter with a local Ollama model → `translated_body` is complete (not truncated)
5. **Frontend**: Open BookTranslationPage → expand "Advanced settings" → change chunk size → save → reload → verify value persisted
