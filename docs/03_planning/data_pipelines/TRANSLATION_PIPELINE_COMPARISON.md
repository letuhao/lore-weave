# Translation Pipeline Comparison: MVTN (Old) vs LoreWeave (Current)

> **Purpose:** Understand what the old standalone pipeline did right, what the current service-based pipeline lost, and what V2 should reclaim.

---

## Architecture Comparison

| Aspect | MVTN (Old) | LoreWeave (Current) |
|--------|-----------|-------------------|
| **Runtime** | CLI script, single-threaded, file-based | Microservice + RabbitMQ worker, async |
| **Input** | Raw `.txt` files (one per chapter) | Tiptap JSON (from book-service) |
| **Output** | Raw `.txt` translation files | `chapter_translations` table (JSON or text) |
| **Glossary** | JSONL file, built incrementally per chapter | Separate glossary-service DB (not integrated) |
| **State** | Files on disk (glossary.jsonl, timeline.jsonl) | PostgreSQL tables |

---

## Multi-Pass Pipeline (what MVTN does that LoreWeave doesn't)

### MVTN processes EACH chapter through 6 passes:

```
process_file(chapter):
  1. run_glossary_pass()     ← Extract glossary entities from chapter
  2. run_timeline_pass()     ← Extract timeline events
  3. run_facts_pass()        ← Extract entity facts/attributes
  4. run_relations_pass()    ← Extract relationship edges
  5. run_scene_pass()        ← Extract scene segments
  6. run_translate_pass()    ← Translate with glossary context
```

### LoreWeave has ONLY the translate pass:

```
_process_chapter(chapter):
  1. fetch chapter body
  2. translate_chapter_blocks() or translate_chapter()
  3. persist
```

**No glossary extraction, no timeline, no facts, no relations, no scenes.** The entire knowledge-building pipeline is missing.

---

## Glossary Integration — The Biggest Gap

### MVTN Glossary Flow:

```
1. BEFORE translating, extract glossary from chapter text:
   - LLM call with existing glossary + chapter text
   - Returns new entities: {canonical_id, names_zh, names_vi, kind, evidences}
   - Merge with existing glossary (dedup by names_zh)
   - Save to glossary.jsonl

2. Build chapter-specific glossary for translation:
   - Score entities by occurrence in chapter text
   - Pin important recurring characters
   - Cap at max_entries (40) and max_tokens (1200)
   - Project to minimal form: {canonical_id, names_zh, names_vi}

3. Inject into EVERY translation chunk:
   <start_of_glossary>
   {"canonical_id":"aldric","names_zh":["提拉米"],"names_vi":["Tirami"]}
   {"canonical_id":"demon-lord","names_zh":["伊斯坦莎"],"names_vi":["Isutansha"]}
   ...
   <end_of_glossary>

4. Inject into EVERY validation call too (same glossary block)
```

### LoreWeave Glossary:

```
(nothing — glossary exists in separate DB but translation service doesn't use it)
```

**This is why names are translated inconsistently.** MVTN's glossary is built incrementally (each chapter adds new entities) and injected into every translation call. LoreWeave's translation pipeline doesn't know the glossary exists.

---

## Translation Pass Comparison

### MVTN translate_pass:

```python
def run_translate_pass(self, source_file, header_line, chapter_text, log):
    glossary = load_glossary(self.glossary_path)
    _, max_ct, _ = self.compute_chunk_limits()
    
    chunks = build_line_chunks(translate_source, max_ct)
    
    # Build stable glossary for ENTIRE chapter (not per-chunk)
    chapter_glossary_block = build_chapter_glossary_block(
        glossary, chapter_text,
        max_tokens=1200, max_entries=40,
        pinned_names_zh=["伊斯坦莎", "勇者", "魔王"],
    )
    
    for idx, chunk in enumerate(chunks):
        # 1. TRANSLATE with glossary
        vi = client.chat([system, user_with_glossary], ...)
        
        # 2. VALIDATE (LLM checks translation quality)
        if validate_enabled:
            vi2, ok = validate(zh=chunk, vi=vi, glossary=chapter_glossary_block)
            if ok:
                vi = vi2
            elif retry:
                # Retry with hint about failure
                vi = client.chat([system, hint + user], ...)
                vi3, ok2 = validate(zh=chunk, vi=vi, glossary=...)
                if ok2: vi = vi3
        
        # 3. CJK LEAK FIX (detect untranslated Chinese in output)
        if cjk_validate_enabled:
            vi = run_cjk_line_fix_loop(zh=chunk, vi=vi, glossary=...)
        
        vi_chunks.append(vi)
    
    return "\n".join(vi_chunks)
```

### LoreWeave translate_chapter_blocks:

```python
def translate_chapter_blocks(blocks, ...):
    plan = build_batch_plan(blocks, context_window * 0.25)
    
    for batch in plan.batches:
        # 1. TRANSLATE (no glossary, no context)
        messages = [system_prompt, user_with_blocks]
        response = invoke_llm(messages)
        parsed = parse_translated_blocks(response)
        translated_texts.update(parsed)
    
    # Reassemble (no validation, no CJK check)
    return [rebuild_block(b, translated_texts.get(b.index, b.original)) for b in plan]
```

### What LoreWeave Lost:

| Feature | MVTN | LoreWeave |
|---------|------|-----------|
| Glossary injection in prompt | Yes (1200 tokens, 40 entries) | **No** |
| Glossary-aware entity scoring | Yes (by occurrence × name length) | **No** |
| Pinned important names | Yes (configurable) | **No** |
| Post-translation validation | Yes (LLM PASS/FIXED_VI check) | **No** |
| CJK leak detection | Yes (per-line regex scan) | **No** |
| CJK fix retry | Yes (up to 3 retries, JSONL line-fix) | **No** |
| Retry on validation failure | Yes (re-translate + re-validate) | **No** |
| Token budgeting for validation | Yes (ZH+VI must fit in context) | **No** |
| Logging per chunk | Yes (stage, chunk_index, vi_chars) | **Partial** |

---

## Token Estimation Comparison

### MVTN:

```python
def est_tokens(text):
    return max(1, (len(text) + 2) // 3)  # ~3 chars per token
```

CJK-aware by design: `len(text) // 3` is conservative for CJK text (~1.5-2 chars/token, estimate ~3 gives safety margin). For a 3000-char CJK chapter: estimates 1000 tokens, actual ~2000. **Safe — overestimates by ~2x, so chunks are smaller than budget allows.**

### LoreWeave:

```python
TOKEN_CHAR_RATIO = 3.5
def estimate_tokens(text):
    return max(1, int(len(text) / 3.5))
```

Same 3000-char CJK text: estimates 857 tokens, actual ~2000. **Underestimates by ~2.3x, so chunks OVERFLOW the budget.** This is the root cause of hallucination.

### Key Insight:

MVTN uses `// 3` (integer division, conservative).
LoreWeave uses `/ 3.5` (float division, optimistic).

The 3.5 was likely "optimized" for English/Latin text but breaks catastrophically for CJK.

---

## Context Budget Comparison

### MVTN:

```python
class BudgetConfig:
    context_tokens:           13000
    safety_tokens:            400
    completion_translate:     4500    # reserved for output
    completion_validate:      3200    # reserved for validation output
    glossary_inject_tokens:   1200    # reserved for glossary
    glossary_max_entries:     40
    existing_glossary_cap:    900
```

**Budget formula:**
```
available_for_input = context - safety - completion - glossary - prompt_base
```

13000 - 400 - 4500 - 1200 - ~500 = **6400 tokens for input text**

This means each chunk is ~6400 tokens max. With CJK at ~3 chars/token → ~19200 chars per chunk.

### LoreWeave:

```python
max_tokens = int(context_window * 0.25)  # budget_ratio default 0.25
```

For 32000 context: 32000 × 0.25 = **8000 tokens for ALL text in batch**.
No separate reservation for output, glossary, system prompt.

If the batch uses 8000 tokens for input, there's only 24000 left for system prompt + output. For CJK where output ≈ input length, this seems fine in theory — but the estimation is wrong so actual input could be 20000+ tokens.

---

## Validation Pipeline — What MVTN Does

### Pass 1: Full Translation Validation

```
Input:  ZH chunk + VI translation + glossary
Prompt: "Check meaning drift, name consistency, glossary compliance"
Output: PASS or FIXED_VI + corrected text
```

If PASS → keep translation.
If FIXED_VI → use corrected version.
If unparseable → retry whole chunk (re-translate + re-validate).

### Pass 2: CJK Leak Detection (rule-based, no LLM)

```python
def cjk_leak_bad_line_indices(zh_lines, vi_lines):
    """Find VI lines that still contain Chinese characters."""
    bad = []
    for i, line in enumerate(vi_lines):
        if any(0x4E00 <= ord(c) <= 0x9FFF for c in line):
            bad.append(i)
    return bad
```

### Pass 3: CJK Fix (LLM, targeted lines only)

```
Input:  Only the bad lines (line index + ZH source + current VI) as JSONL
Output: JSONL with fixed VI per line
Retry:  Up to 3 times until no CJK remains
```

This is **surgical** — only re-translates the specific bad lines, not the whole chunk. Much cheaper and more reliable than re-translating everything.

### LoreWeave has NONE of this.

---

## What V2 Should Take From MVTN

| Feature | Priority | Notes |
|---------|----------|-------|
| **Glossary injection** | P1 | MVTN's `build_chapter_glossary_block()` — score by occurrence, pin important names, cap tokens |
| **CJK-conservative token estimation** | P1 | Use `(len+2)//3` or CJK-aware estimator |
| **Post-translation validation** | P2 | MVTN's PASS/FIXED_VI pattern or block-count validation |
| **CJK leak detection + fix** | P2 | Rule-based detection + surgical LLM fix (not whole-chunk retry) |
| **Validation retry with hint** | P3 | "Your previous translation failed validation. Improve fidelity." |
| **Explicit context budget** | P3 | Separate reservations for: system, glossary, input, output, safety |
| **Chapter-level glossary (stable)** | P3 | Same glossary for ALL chunks in a chapter (not per-chunk selection) |
| **Glossary extraction pass** | P4 | Run BEFORE translation to discover new entities |
| **Timeline extraction** | P5 | After translation, extract events for knowledge graph |
| **Entity facts/relations/scenes** | P5 | Rich metadata extraction pipeline |

---

## Summary

**MVTN is a 6-pass knowledge-building pipeline** that translates as one of its passes. It builds glossary incrementally, validates translations, fixes CJK leaks, and extracts structured metadata.

**LoreWeave is a 1-pass translation-only pipeline** that lost everything except the raw translation call when it was rewritten for Tiptap JSON blocks. It doesn't use the glossary, doesn't validate, doesn't fix, and doesn't extract knowledge.

**V2 should merge the best of both:** MVTN's context engineering (glossary injection, validation, CJK fix) with LoreWeave's infrastructure (microservice, async workers, Tiptap JSON, block-level precision).
