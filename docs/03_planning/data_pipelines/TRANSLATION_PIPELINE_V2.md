# Translation Pipeline V2 — Context-Engineered Design

> **Status:** Design proposal
> **Author:** Session 28 (2026-04-09)
> **Problem:** Current pipeline has zero context awareness, wrong token math, no output validation, and no glossary integration. LLM hallucinations go undetected.
>
> **Scope:** This pipeline is TRANSLATION ONLY. It reads glossary context but does NOT extract glossary, timeline, facts, relations, or scenes. Those are separate pipelines (see MVTN comparison doc). The old MVTN pipeline mixed all concerns into one monolith — we separate them cleanly:
>
> | Pipeline | Responsibility | Reads from | Writes to |
> |----------|---------------|------------|-----------|
> | **Translation V2** (this doc) | Translate chapter blocks | glossary-service (context) | chapter_translations |
> | **Glossary Extraction** (future) | Discover entities from chapter text | chapter content | glossary-service |
> | **Metadata Extraction** (future) | Timeline, facts, relations, scenes | chapter content + glossary | metadata tables |
> | **Quality Validation** (future) | Post-hoc translation QA | chapter_translations + glossary | quality_logs |

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

### Context Window Allocation (single LLM call)

For a 32K token model translating CJK → Vietnamese:

```
┌─────────────────────────────────────────┐
│          CONTEXT WINDOW (32000)          │
├─────────────────────────────────────────┤
│  System prompt          ~500 tokens     │ ← fixed
│  Glossary context       ~1500 tokens    │ ← tiered, capped (see §4)
│  Rolling summary        ~300 tokens     │ ← grows, compacted
│  ─────────────────────────────────      │
│  Fixed overhead         ~2300 tokens    │
│                                         │
│  Available for I/O      ~29700 tokens   │
│    ├── Input (source)   ~12000 tokens   │ ← 40% of available
│    └── Output (target)  ~17700 tokens   │ ← 60% (CJK→Latin expands)
│                                         │
│  Safety margin          included in 60% │
└─────────────────────────────────────────┘
```

**Output expansion ratios by language pair:**

| Source → Target | Output/Input ratio | Output allocation |
|----------------|-------------------|-------------------|
| CJK → Vietnamese | ~1.8-2.5x | 60% of available |
| CJK → English | ~1.5-2.0x | 55% of available |
| CJK → Japanese | ~1.0-1.2x | 50% of available |
| CJK → Korean | ~1.0-1.3x | 50% of available |
| Latin → Latin | ~1.0-1.3x | 50% of available |

The split is: `input_budget = available * (1 / (1 + expansion_ratio))`

### Degradation Strategy

| Dependency | If unavailable | Behavior |
|-----------|---------------|----------|
| glossary-service | Translate without glossary | Warning logged, names may be inconsistent |
| chapter_entity_links empty | Fall back to Tier 2 (name-scan only) | Slower but functional |
| No translations for target language | Inject names_zh only (no names_vi) | LLM transliterates from context |
| provider-registry slow | Retry with backoff, then fail chapter | Transient error, safe to retry |
| Previous chapter memo missing | Skip rolling context | First chapter or re-translation |

**Rule: Missing context = degraded quality, NOT a failure.** The pipeline always produces output; quality varies with available context.

### Architecture Overview

```
┌──────────────────────────────────────────────────────┐
│                  1. PREPARATION                       │
│                                                      │
│  Chapter Tiptap JSON                                 │
│       │                                              │
│       ├──→ Classify blocks (translate/pass/caption)  │
│       ├──→ Extract translatable text                 │
│       ├──→ Count REAL tokens (CJK-aware, see §5)     │
│       │                                              │
│       ├──→ Load glossary (tiered, see §4)            │
│       │    ↳ If glossary-service down: skip (warn)   │
│       ├──→ Load previous chapter memo (from DB)      │
│       │    ↳ If missing: skip (first chapter)        │
│       └──→ Compute output expansion ratio            │
│            ↳ From source_language + target_language   │
│                                                      │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────┼───────────────────────────────┐
│                      ▼                                │
│              2. CONTEXT BUDGET                        │
│                                                      │
│  context_window    = from model registry             │
│  fixed_overhead    = system + glossary + memo         │
│  expansion_ratio   = from language pair table         │
│  input_budget      = (ctx - overhead) / (1 + ratio)  │
│                                                      │
│  → Split blocks into chunks fitting input_budget     │
│  → Keep semantic groups together (dialogue, scene)   │
│  → Max blocks per chunk: 40 (prevents hallucination) │
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

### The Scale Problem

A book can have 2000 chapters and 5000+ glossary entities (10MB+). That's ~2.5M tokens — impossible to inject into a 32K-128K context window. Even 1% would consume the entire window.

**Rule: NEVER inject the full glossary. Always scope to what's relevant.**

### Source Data (already exists)

| Table | Service | What |
|-------|---------|------|
| `glossary_entities` | glossary-service | Characters, places, items, concepts |
| `entity_attribute_values` | glossary-service | Names, aliases, titles |
| `attribute_translations` | glossary-service | Known translations per language |
| `chapter_entity_links` | glossary-service | **Which entities appear in which chapters** (the index) |

The `chapter_entity_links` table is the key — it maps entities to chapters with relevance (major/appears/mentioned). This is our **relevance index** that avoids scanning the full glossary.

### Tiered Glossary Injection Strategy

```
Tier 0: PINNED (always included, ~200 tokens)
  ┌─────────────────────────────────────────────────────┐
  │ 5-10 protagonist/antagonist entities                 │
  │ Identified by: linked to most chapters (top N by     │
  │ chapter_entity_links count) or manually flagged       │
  │                                                       │
  │ Example: 伊斯坦莎, 提拉米, 魔王 — always injected    │
  └─────────────────────────────────────────────────────┘

Tier 1: CHAPTER-LINKED (primary source, ~400-1500 tokens)
  ┌─────────────────────────────────────────────────────┐
  │ Entities linked to THIS chapter via chapter_entity_links │
  │ Filter: relevance = major OR appears                     │
  │ Typically 10-50 entities per chapter                     │
  │                                                          │
  │ SQL: SELECT entity_id FROM chapter_entity_links          │
  │      WHERE chapter_id = $1 AND relevance IN ('major','appears') │
  └─────────────────────────────────────────────────────┘

Tier 2: NAME-MATCHED (fallback for unlinked mentions, ~200-500 tokens)
  ┌─────────────────────────────────────────────────────┐
  │ Scan chapter text for known entity names NOT already │
  │ in Tier 0/1. Catches cross-references.               │
  │                                                       │
  │ Build name→entity_id index once per book.             │
  │ For each name found in text, include that entity.     │
  │ Cap: remaining token budget after Tier 0+1            │
  └─────────────────────────────────────────────────────┘
```

**Total budget: 1200-2000 tokens** (fits in any context window with room for translation).

### Scoring Within Tiers

Within Tier 1+2, rank by relevance to the chapter:

```python
score = occurrences_in_chapter_text * max(1, len(name_zh))
```

- More occurrences = more important for this chapter
- Longer names = more important to get right (伊斯坦莎 vs 王)
- Sort by score descending, take top N within token budget

This is the same approach MVTN used in `build_chapter_glossary_block()`.

### Glossary Context Builder

```python
def build_glossary_context(
    book_id: str, 
    chapter_id: str,
    chapter_text: str,
    target_language: str,
    max_tokens: int = 1500,
) -> str:
    """
    Build scoped glossary for one chapter's translation.
    Uses chapter_entity_links as primary index, text scanning as fallback.
    Returns formatted string for LLM system prompt injection.
    """
    
    # Tier 0: Pinned (most-linked entities across the book)
    pinned = glossary_api.get_most_linked_entities(book_id, limit=10)
    
    # Tier 1: Chapter-linked
    linked = glossary_api.get_chapter_entities(
        book_id, chapter_id, relevance=['major', 'appears']
    )
    
    # Tier 2: Name-scan for unlinked mentions
    name_index = glossary_api.get_entity_name_index(book_id)  # cached
    text_mentioned = [
        eid for name, eid in name_index.items() 
        if name in chapter_text
    ]
    
    # Merge, dedupe, score by chapter_text occurrence
    candidates = dedupe_entities(pinned + linked + text_mentioned)
    scored = score_by_occurrence(candidates, chapter_text)
    
    # Project to minimal form + cap tokens
    return format_glossary_block(scored, target_language, max_tokens)
```

### Minimal Projection (what gets injected)

```json
{"id":"aldric","zh":["提拉米","提拉米·蘇蘭特"],"vi":["Tirami","Tirami Sulant"],"kind":"character"}
{"id":"demon-lord","zh":["伊斯坦莎"],"vi":["Isutansha"],"kind":"character"}
{"id":"dark-palace","zh":["暗黑魔殿"],"vi":["Dark Demon Palace"],"kind":"location"}
```

Only `names_zh → names_vi + kind`. NOT full entity with descriptions, evidences, attributes. ~30-50 tokens per entity.

### Stability Rule

**Build glossary block ONCE per chapter, inject into EVERY chunk/batch.** Don't rebuild per-chunk — that causes inconsistency if different chunks match different entities.

### Future: Glossary Extraction Pipeline (separate concern)

The extraction pipeline discovers NEW entities from chapter text. It also needs existing glossary context to avoid re-discovering known entities:

```
Chapter text + EXISTING glossary (scoped) → NEW entities → glossary-service
```

Same tiered scoping applies: only inject existing entities whose names appear in the current text. Tell the LLM: "These entities are already known. Only extract NEW ones."

This is a separate pipeline doc — not part of Translation V2.

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

## 11. Edge Cases

### Very large chapters (500+ blocks)

- Token estimation creates many chunks (e.g., 500 blocks → 10-15 chunks of ~40 blocks)
- Each chunk gets the SAME glossary context (stable per chapter)
- Rolling summary grows across chunks — if it exceeds budget, compact it (same as text pipeline's memo system)
- Max 40 blocks per chunk as a hard cap to prevent LLM block-count confusion

### New book (no glossary yet)

- Tier 0: empty (no pinned entities)
- Tier 1: empty (no chapter_entity_links)
- Tier 2: empty (no entities to name-scan)
- Result: translates without glossary context — names will be inconsistent
- **This is expected.** Run Glossary Extraction pipeline first, then re-translate.

### First translation for a target language

- Glossary entities exist but `attribute_translations` has no rows for this language
- Inject `names_zh` only: `{"zh":["伊斯坦莎"],"vi":[],"kind":"character"}`
- LLM will transliterate from context — better than nothing
- After translation, Glossary Extraction pipeline can harvest the names LLM used

### Chapter with only media blocks

- All blocks classified as `passthrough` or `caption_only`
- Only captions get translated (few tokens)
- Single chunk, tiny — fast, no chunking needed

### Concurrent translations of same chapter

- Each worker builds its own glossary block and chunks independently
- Revision versioning in `chapter_translations` handles concurrent writes
- Last one wins (by version_num) — acceptable for concurrent jobs

---

## 12. Comparison: Current vs Proposed

| Aspect | Current Pipeline | Proposed V2 |
|--------|-----------------|-------------|
| Token counting | `len(text)/3.5` | CJK-aware: `cjk/1.5 + latin/4.0` |
| Context budget | 25% of ctx, no reserves | Dynamic: ctx - system - glossary - memo - output (language-pair-aware) |
| Glossary | None | Tiered injection: pinned + chapter-linked + name-scan (see §4) |
| Cross-chunk | None (each batch isolated) | Rolling summary between chunks |
| Cross-chapter | None | Chapter memo stored in DB |
| Output validation | Silent fallback | Strict check + retry with feedback |
| Name consistency | Random per-batch | Glossary lock + auto-correct post-process |
| Error handling | Silent | Fail loud, log details, mark partial |
| Token tracking | Always 0 | Multi-provider format extraction |
| Retry | None | 2 retries with error feedback |
| Quality metrics | None | Per-chunk: blocks ok/failed/corrected, glossary fixes |
| Media blocks | Caption only | Caption + alt text |
| Batch sizing | Token budget only | Semantic grouping + 40-block hard cap |
| Degradation | Crash on missing deps | Graceful: skip glossary/memo if unavailable, warn |

---

## Appendix A: Current Pipeline Bugs (reference)

> Moved from main body. These are the bugs that motivated V2. See §1 for current pipeline description.

(Bug details in sections 2.1-2.6 above remain as historical reference.)
