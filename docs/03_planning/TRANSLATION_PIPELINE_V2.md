# Translation Pipeline V2 — Context-Engineered Design

> **Status:** Design proposal
> **Author:** Session 28 (2026-04-09)
> **Problem:** Current pipeline has zero context awareness, wrong token math, no output validation, and no glossary integration. LLM hallucinations go undetected.

---

## 1. Current Pipeline — What Exists

### Two pipelines in translation-service:

**Text pipeline** (legacy, for raw text chapters):
```
chapter text → chunk by token budget → for each chunk:
  → build messages [system, ...session_history, user:chunk]
  → LLM call
  → append to session_history (rolling context)
  → if history > 50% context window: compact to memo
→ concatenate all chunks
```
- Has session history + compaction (good)
- No glossary awareness (bad)
- Token estimation wrong (bad)

**Block pipeline** (current, for Tiptap JSON chapters):
```
chapter blocks → classify (translate/pass/caption) → estimate tokens (len/3.5)
  → batch blocks into groups within token budget
  → for each batch: one LLM call with [BLOCK N] markers
  → regex-parse response → reassemble Tiptap JSON
```
- No session history between batches (bad)
- No glossary (bad)
- No output validation (bad)
- Token estimation wrong (bad)

### Data flow:

```
chapter_worker.py
  → _process_chapter()
    → fetch chapter body from book-service
    → if Tiptap JSON: translate_chapter_blocks()     ← block pipeline
    → if raw text:    translate_chapter()             ← text pipeline
    → persist to chapter_translations table
```

### Files involved:

| File | Purpose |
|------|---------|
| `workers/chapter_worker.py` | Entry point, fetches chapter, selects pipeline, persists |
| `workers/block_classifier.py` | Classifies blocks, serializes inline marks to markdown |
| `workers/block_batcher.py` | Groups blocks into batches, parses LLM response |
| `workers/session_translator.py` | Both pipelines live here. LLM invoke, history, compaction |
| `workers/chunk_splitter.py` | Text chunking by paragraph/sentence boundaries |

---

## 2. Bugs in Current Pipeline

### Bug 1: Token estimation is character-based, wrong for CJK

```python
# chunk_splitter.py
TOKEN_CHAR_RATIO = 3.5
def estimate_tokens(text): return max(1, int(len(text) / 3.5))
```

| Language | Actual ratio | Estimate ratio | Error |
|----------|-------------|----------------|-------|
| English  | ~4.0        | 3.5            | ~14% over |
| Chinese  | ~1.5        | 3.5            | ~133% UNDER |
| Japanese | ~1.5        | 3.5            | ~133% UNDER |
| Korean   | ~2.0        | 3.5            | ~75% UNDER |
| Vietnamese | ~3.0      | 3.5            | ~17% over |

**Impact:** For CJK text, batcher thinks a batch is 985 tokens but it's actually 4,676. The entire batch fits in one LLM call on paper, but in reality it overflows the context window. The model starts looping and hallucinating.

### Bug 2: Block pipeline has ZERO context between batches

Unlike the text pipeline which has session_history + compaction, the block pipeline translates each batch independently:

```python
# session_translator.py translate_chapter_blocks()
for batch in plan.batches:
    combined = batch.combined_text()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Translate...:\n\n{combined}"},
    ]
    # No history, no previous batch context, no glossary
```

**Impact:** Character names translated differently across batches. Style shifts. No consistency.

### Bug 3: No output validation

```python
# block_batcher.py parse_translated_blocks()
def parse_translated_blocks(response_text, expected_indices):
    # Only accepts blocks in expected_indices
    # But: no count validation, no duplicate detection
    # Missing blocks → caller silently uses original text
    # Extra blocks → silently discarded
    # Duplicate blocks → last one wins
```

**Impact:** Corrupted translations persisted to DB. User sees mix of translated and original text with no indication. Hallucinated duplicate blocks silently accepted.

### Bug 4: Token tracking always 0

```python
# session_translator.py
usage = full_response.get("usage") or {}
in_tok = int(usage.get("input_tokens") or 0)   # Ollama uses "prompt_eval_count"
out_tok = int(usage.get("output_tokens") or 0)  # Ollama uses "eval_count"
```

Ollama response format:
```json
{"prompt_eval_count": 4676, "eval_count": 7000}
```

Code expects:
```json
{"usage": {"input_tokens": 4676, "output_tokens": 7000}}
```

**Impact:** No cost tracking, no usage metrics, no way to detect expensive runaway translations.

### Bug 5: Media blocks are second-class

```python
_CAPTION_ONLY_TYPES = {"imageBlock", "videoBlock", "audioBlock"}
# Only translates attrs.caption, ignores alt text
```

### Bug 6: Silent fallback to originals

```python
# session_translator.py
for entry in plan.all_entries:
    if entry.index in translated_texts:
        result_blocks.append(rebuild_block(...))
    else:
        result_blocks.append(entry.block)  # ← original, NOT translated
```

No log, no warning, no user notification.

---

## 3. Proposed Pipeline V2

### Core Principle

**Translation quality = context quality.**

The LLM needs to know:
1. **WHO** — character/entity names with fixed translations (from glossary)
2. **WHAT** — what happened earlier in this chapter (rolling summary)
3. **HOW** — translation style/tone (from previous chapter memo)
4. **LIMITS** — how much it can output (proper token budget)

### Architecture Overview

```
┌──────────────────────────────────────────────────────┐
│                  1. PREPARATION                       │
│                                                      │
│  Chapter Tiptap JSON                                 │
│       │                                              │
│       ├──→ Classify blocks (translate/pass/caption)  │
│       ├──→ Extract translatable text                 │
│       ├──→ Count REAL tokens (tiktoken)              │
│       │                                              │
│       ├──→ Load glossary term map (from DB)          │
│       ├──→ Load previous chapter memo (from DB)      │
│       └──→ Load book style reference                 │
│                                                      │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────┼───────────────────────────────┐
│                      ▼                                │
│              2. CONTEXT BUDGET                        │
│                                                      │
│  context_window    = 32000 (from model registry)     │
│  system_prompt     =   ~500 tokens                   │
│  glossary_context  =   ~800 tokens (scales w/ count) │
│  style_memo        =   ~300 tokens                   │
│  output_reserve    = chunk_input * 1.3               │
│  ─────────────────────────────────                   │
│  available_input   = context_window                  │
│                    - system_prompt                    │
│                    - glossary_context                 │
│                    - style_memo                       │
│                    - output_reserve                   │
│                                                      │
│  → Split blocks into chunks fitting available_input  │
│  → Keep semantic groups together (dialogue, scene)   │
│                                                      │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────┼───────────────────────────────┐
│                      ▼                                │
│         3. TRANSLATE (per chunk, sequential)          │
│                                                      │
│  ┌─────────────────────────────────────────┐         │
│  │  BUILD PROMPT                            │         │
│  │                                          │         │
│  │  [SYSTEM]                                │         │
│  │  You are a {src}→{tgt} translator.       │         │
│  │  ...formatting rules...                  │         │
│  │                                          │         │
│  │  GLOSSARY (use exact translations):      │         │
│  │  伊斯坦莎 → Isutansha (Demon Lord)       │         │
│  │  提拉米 → Tirami (Hero)                  │         │
│  │  暗黑魔殿 → Dark Demon Palace            │         │
│  │  ...                                     │         │
│  │                                          │         │
│  │  [ASSISTANT] (if chunk > 1)              │         │
│  │  [Summary of previous section: ...]      │         │
│  │                                          │         │
│  │  [USER]                                  │         │
│  │  [BLOCK 0] text...                       │         │
│  │  [BLOCK 5] text...                       │         │
│  │  ...                                     │         │
│  └───────────────┬─────────────────────────┘         │
│                  │                                    │
│                  ▼                                    │
│  ┌─────────────────────────────────────────┐         │
│  │  LLM INVOKE                              │         │
│  │  → provider-registry/invoke              │         │
│  │  → extract tokens from response          │         │
│  │    (handle Ollama + OpenAI formats)       │         │
│  └───────────────┬─────────────────────────┘         │
│                  │                                    │
│                  ▼                                    │
│  ┌─────────────────────────────────────────┐         │
│  │  4. VALIDATE OUTPUT                      │         │
│  │                                          │         │
│  │  ✓ Block count matches input?            │         │
│  │  ✓ All expected indices present?         │         │
│  │  ✓ No duplicate indices?                 │         │
│  │  ✓ Output length sane? (0.5x-3x input)  │         │
│  │  ✓ Known glossary names correct?         │         │
│  │                                          │         │
│  │  IF FAIL + retry_count < 2:              │         │
│  │    → retry with correction prompt:       │         │
│  │    "You output N blocks but input had M. │         │
│  │     Output exactly M blocks."            │         │
│  │                                          │         │
│  │  IF FAIL + retry exhausted:              │         │
│  │    → mark chunk FAILED                   │         │
│  │    → log detailed diagnostics            │         │
│  │    → continue with next chunk            │         │
│  └───────────────┬─────────────────────────┘         │
│                  │                                    │
│                  ▼                                    │
│  ┌─────────────────────────────────────────┐         │
│  │  5. POST-PROCESS                         │         │
│  │                                          │         │
│  │  a. Auto-correct glossary names          │         │
│  │     - Scan output for source terms that  │         │
│  │       should have been translated        │         │
│  │     - Replace with glossary translation  │         │
│  │     - Flag corrections in metrics        │         │
│  │                                          │         │
│  │  b. Update rolling summary               │         │
│  │     - Brief summary of this chunk        │         │
│  │     - Passed to next chunk as context    │         │
│  │                                          │         │
│  │  c. Record metrics                       │         │
│  │     - Real token counts                  │         │
│  │     - Blocks: translated/failed/corrected│         │
│  │     - Glossary corrections count         │         │
│  │     - Retry count                        │         │
│  └───────────────┬─────────────────────────┘         │
│                  │                                    │
│         (loop back to next chunk)                    │
│                                                      │
└──────────────────┬───────────────────────────────────┘
                   │
┌──────────────────┼───────────────────────────────────┐
│                  ▼                                    │
│              6. ASSEMBLY                              │
│                                                      │
│  a. Rebuild Tiptap JSON                              │
│     - Translated blocks replace originals            │
│     - Failed blocks marked (not silent fallback)     │
│     - Passthrough blocks kept as-is                  │
│                                                      │
│  b. Validate final JSON structure                    │
│                                                      │
│  c. Persist to DB                                    │
│     - chapter_translations: body + token counts      │
│     - translation_quality_log: per-chunk metrics     │
│                                                      │
│  d. Store chapter memo for next chapter              │
│     - Compact summary of translation decisions       │
│     - Glossary terms seen + how they were handled    │
│                                                      │
│  e. Emit events                                      │
│     - chapter.translated (success)                   │
│     - chapter.translation_partial (some blocks fail) │
│     - chapter.translation_failed (all blocks fail)   │
│                                                      │
└──────────────────────────────────────────────────────┘
```

---

## 4. Glossary Integration Design

### Source Data

Already exists in glossary-service DB:
- `glossary_entities` — characters, places, items, concepts
- `entity_attribute_values` — names, aliases, titles
- `attribute_translations` — known translations per language

### Glossary Context Builder

```python
def build_glossary_context(book_id: str, target_language: str) -> str:
    """
    Fetch glossary entities and build a term map for the LLM.
    
    Returns a formatted string like:
    
    GLOSSARY — Use these exact translations:
    伊斯坦莎 → Isutansha (Demon Lord, female, character)
    提拉米·蘇蘭特 → Tirami Sulant (Hero, male, character)
    提拉米 → Tirami (short name for Tirami Sulant)
    暗黑魔殿 → Dark Demon Palace (location)
    煉獄之炎 → Inferno Flame (ability)
    
    Do NOT translate these names differently.
    """
    # 1. Fetch entities: GET /v1/glossary/books/{book_id}/export
    # 2. For each entity with status='active':
    #    - Get original name (from 'name' or 'term' attribute)
    #    - Get known translation for target_language
    #    - Get aliases
    #    - Get kind (character, location, item, concept)
    # 3. Format as term map
    # 4. Estimate tokens, truncate if over budget
```

### Token Budget for Glossary

| Entities | Estimated tokens | Strategy |
|----------|-----------------|----------|
| < 50     | ~400            | Include all |
| 50-200   | ~1600           | Include all, may need larger model |
| 200-500  | ~4000           | Include only entities appearing in this chapter |
| 500+     | ~8000+          | Filter by chapter_entity_links relevance |

For large glossaries, use `chapter_entity_links` to only include entities that appear in the current chapter + major recurring characters.

---

## 5. Token Counting Strategy

### Option A: tiktoken (recommended for OpenAI-compatible models)

```python
import tiktoken

def count_tokens(text: str, model: str = "gpt-4") -> int:
    enc = tiktoken.encoding_for_model(model)
    return len(enc.encode(text))
```

Pros: Accurate for OpenAI models. Fast. Well-maintained.
Cons: Not accurate for non-OpenAI models (Ollama/local).

### Option B: Provider-specific estimation

```python
def count_tokens(text: str, provider: str, model: str) -> int:
    if provider in ("openai", "anthropic"):
        return tiktoken_count(text, model)
    elif provider in ("ollama", "lm_studio"):
        # CJK-aware heuristic: count CJK chars separately
        cjk_count = sum(1 for c in text if is_cjk(c))
        latin_count = len(text) - cjk_count
        return int(cjk_count / 1.5 + latin_count / 4.0)
    else:
        return tiktoken_count(text, "gpt-4")  # conservative fallback
```

### Option C: Ask the provider (most accurate, slower)

Some providers have a tokenize endpoint. Could be used for budget calculation before batching.

### Recommendation

Start with Option B (CJK-aware heuristic). It's simple, no dependencies, and fixes the 2-3x error for CJK. Upgrade to Option A/C later if needed.

```python
def is_cjk(char: str) -> bool:
    cp = ord(char)
    return (
        0x4E00 <= cp <= 0x9FFF or    # CJK Unified
        0x3400 <= cp <= 0x4DBF or    # CJK Extension A
        0x3000 <= cp <= 0x303F or    # CJK Punctuation
        0x3040 <= cp <= 0x309F or    # Hiragana
        0x30A0 <= cp <= 0x30FF or    # Katakana
        0xAC00 <= cp <= 0xD7AF       # Hangul
    )

def estimate_tokens_v2(text: str) -> int:
    cjk = sum(1 for c in text if is_cjk(c))
    other = len(text) - cjk
    return max(1, int(cjk / 1.5 + other / 4.0))
```

---

## 6. Output Validation Rules

```python
@dataclass
class ValidationResult:
    valid: bool
    errors: list[str]
    warnings: list[str]
    
def validate_translation_output(
    response_text: str,
    expected_indices: list[int],
    input_texts: dict[int, str],
    glossary_terms: dict[str, str],  # source → target
) -> ValidationResult:
    errors = []
    warnings = []
    
    parsed = parse_block_markers(response_text)
    
    # Rule 1: Block count
    if len(parsed) != len(expected_indices):
        errors.append(
            f"block_count_mismatch: expected {len(expected_indices)}, "
            f"got {len(parsed)}"
        )
    
    # Rule 2: All indices present
    missing = set(expected_indices) - set(parsed.keys())
    if missing:
        errors.append(f"missing_blocks: {sorted(missing)}")
    
    # Rule 3: No unexpected indices
    extra = set(parsed.keys()) - set(expected_indices)
    if extra:
        errors.append(f"extra_blocks: {sorted(extra)}")
    
    # Rule 4: Length sanity (output should be 0.5x-3x of input)
    for idx in parsed:
        if idx in input_texts:
            ratio = len(parsed[idx]) / max(1, len(input_texts[idx]))
            if ratio > 3.0:
                warnings.append(f"block_{idx}_too_long: {ratio:.1f}x input")
            if ratio < 0.3:
                warnings.append(f"block_{idx}_too_short: {ratio:.1f}x input")
    
    # Rule 5: Glossary names (source terms should NOT appear in output)
    for source_term, target_term in glossary_terms.items():
        for idx, text in parsed.items():
            if source_term in text:
                warnings.append(
                    f"block_{idx}_untranslated_term: '{source_term}' "
                    f"should be '{target_term}'"
                )
    
    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )
```

---

## 7. Retry Strategy

```python
async def translate_chunk_with_retry(
    chunk_blocks, context, glossary, max_retries=2
):
    for attempt in range(max_retries + 1):
        response = await invoke_llm(chunk_blocks, context, glossary)
        validation = validate_translation_output(response, ...)
        
        if validation.valid:
            # Apply glossary auto-corrections even on valid output
            corrected = auto_correct_glossary(response, glossary)
            return corrected, validation
        
        if attempt < max_retries:
            # Retry with error feedback
            context.add_correction(
                f"Your previous output had errors: {validation.errors}. "
                f"Please fix and output exactly {len(chunk_blocks)} blocks."
            )
            log.warning(
                "chunk retry %d: %s", attempt + 1, validation.errors
            )
        else:
            log.error(
                "chunk failed after %d retries: %s", 
                max_retries, validation.errors
            )
            return None, validation  # caller marks as failed
```

---

## 8. Rolling Context Between Chunks

### Within a chapter (chunk-to-chunk):

```python
class ChunkContext:
    """Maintains context between chunks within a single chapter."""
    
    glossary_terms: dict[str, str]     # source → target name map
    previous_summary: str              # summary of translated content so far
    style_notes: str                   # tone/style observations
    
    def build_context_message(self) -> str:
        parts = []
        if self.previous_summary:
            parts.append(f"[Previous content summary]\n{self.previous_summary}")
        if self.style_notes:
            parts.append(f"[Style notes]\n{self.style_notes}")
        return "\n\n".join(parts) if parts else ""
    
    def update_after_chunk(self, translated_text: str):
        """Called after each chunk. Updates rolling summary."""
        # Option A: Simple last-N-sentences
        sentences = translated_text.split(".")[-5:]
        self.previous_summary = ".".join(sentences)
        
        # Option B: LLM compaction (like text pipeline)
        # self.previous_summary = await compact_summary(translated_text)
```

### Across chapters (chapter-to-chapter):

```python
class ChapterMemo:
    """Stored in DB after each chapter translation. 
    Loaded by next chapter for consistency."""
    
    chapter_id: str
    book_id: str
    target_language: str
    
    # Glossary terms encountered and how they were translated
    terms_used: dict[str, str]  # {source: target_used}
    
    # Brief story summary up to this point
    story_summary: str
    
    # Style/tone notes
    style_notes: str
    
    created_at: datetime
```

Table:
```sql
CREATE TABLE IF NOT EXISTS translation_chapter_memos (
    book_id          UUID NOT NULL,
    chapter_index    INT NOT NULL,
    target_language  TEXT NOT NULL,
    terms_used       JSONB NOT NULL DEFAULT '{}',
    story_summary    TEXT NOT NULL DEFAULT '',
    style_notes      TEXT NOT NULL DEFAULT '',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (book_id, chapter_index, target_language)
);
```

---

## 9. Token Response Format Handling

```python
def extract_token_counts(response: dict, provider: str) -> tuple[int, int]:
    """Extract input/output token counts from provider response.
    
    Different providers return different formats:
    - OpenAI: {"usage": {"prompt_tokens": N, "completion_tokens": N}}
    - Anthropic: {"usage": {"input_tokens": N, "output_tokens": N}}
    - Ollama: {"prompt_eval_count": N, "eval_count": N}
    - LM Studio: {"usage": {"prompt_tokens": N, "completion_tokens": N}}
    """
    # Try standard format first (OpenAI/Anthropic)
    usage = response.get("usage") or {}
    input_tok = (
        usage.get("input_tokens")
        or usage.get("prompt_tokens")
        or response.get("prompt_eval_count")
        or 0
    )
    output_tok = (
        usage.get("output_tokens")
        or usage.get("completion_tokens")
        or response.get("eval_count")
        or 0
    )
    
    input_tok = int(input_tok)
    output_tok = int(output_tok)
    
    if input_tok == 0 and output_tok == 0:
        log.warning(
            "token_counts_missing: provider=%s, response_keys=%s",
            provider, list(response.keys())
        )
    
    return input_tok, output_tok
```

---

## 10. Implementation Priority

| Phase | What | Effort | Impact |
|-------|------|--------|--------|
| **P1** | CJK-aware token estimation | Small | Fixes hallucination from context overflow |
| **P2** | Output validation + retry | Medium | Catches corrupted translations |
| **P3** | Token count extraction (multi-provider) | Small | Enables cost tracking |
| **P4** | Glossary context injection | Medium | Name consistency — #1 quality issue |
| **P5** | Rolling chunk context | Medium | Style/tone consistency within chapter |
| **P6** | Auto-correct post-processing | Small | Belt-and-suspenders for names |
| **P7** | Cross-chapter memo | Medium | Book-wide consistency |
| **P8** | Quality metrics logging | Small | Observability |

### P1+P2+P3 are critical fixes (can implement in existing pipeline structure).
### P4-P8 are the new pipeline features (require architectural changes).

---

## 11. Comparison: Current vs Proposed

| Aspect | Current Pipeline | Proposed V2 |
|--------|-----------------|-------------|
| Token counting | `len(text)/3.5` | CJK-aware: `cjk/1.5 + latin/4.0` |
| Context budget | 25% of ctx, no reserves | Dynamic: ctx - system - glossary - memo - output |
| Glossary | None | Injected in system prompt from glossary DB |
| Cross-chunk | None (each batch isolated) | Rolling summary between chunks |
| Cross-chapter | None | Chapter memo stored in DB |
| Output validation | Silent fallback | Strict check + retry with feedback |
| Name consistency | Random per-batch | Glossary lock + auto-correct post-process |
| Error handling | Silent | Fail loud, log details, mark partial |
| Token tracking | Always 0 | Multi-provider format extraction |
| Retry | None | 2 retries with error feedback |
| Quality metrics | None | Per-chunk: blocks ok/failed/corrected, glossary fixes |
| Media blocks | Caption only | Caption + alt text |
| Batch sizing | Token budget only | Semantic grouping (dialogue, scene) |
