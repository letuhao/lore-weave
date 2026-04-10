# Glossary Extraction Pipeline — Design

> **Status:** Design proposal
> **Author:** Session 30 (2026-04-10)
> **Problem:** Glossary entities are manually created. For CJK novels with hundreds of characters, locations, and terms, this is impractical. We need an AI-powered extraction pipeline that discovers entities from chapter source text.
>
> **Scope:** This pipeline is EXTRACTION ONLY. It reads chapter source text and writes draft entities to glossary-service in the **source language** (SSOT). It does NOT translate entities — translations are additive and written to `attribute_translations` via the existing glossary translation feature, at any time, for any language.

---

## 1. Design Principles

1. **Source-only extraction** — extract from original language text, never from translations
2. **Source language is SSOT** — extraction output (original_value) is ALWAYS in the chapter's source language. LLM reads Chinese text → outputs Chinese descriptions. No translation during extraction. This ensures:
   - Dedup integrity: names + descriptions match source text exactly
   - No information loss: translation can alter meaning; originals are preserved
   - Evidence chain: original_value + evidence quotes are in the same language → directly verifiable
   - Separation of concerns: extraction = identify + describe, translation = convert (separate step)
3. **Evidence-linked** — extraction captures source text quotes as `evidences` rows, preserving the exact original language passage that supports each attribute value
4. **Translations are additive** — translated aliases/attributes are written to `attribute_translations` table via the existing glossary translation feature, not by this pipeline
5. **Draft by default** — all extracted entities are `status: draft`, user reviews before activating
6. **Server-side dedup** — dedup is handled entirely by glossary-service upsert endpoint using normalized name matching (Unicode NFC, whitespace strip, alias check). Pipeline sends raw LLM output; server decides create vs merge
7. **Idempotent** — re-running extraction on the same chapter merges into existing entities (fill/overwrite per attribute). No duplicate entities created
8. **Chapter-linked** — every extracted entity gets a `chapter_entity_links` row linking it to the source chapter

---

## 2. Data Flow

```
User clicks "Extract Glossary" (chapter / translation / glossary tab)
  → Frontend POST to gateway → translation-service
    → Creates async job (type: extract_glossary)
    → Worker picks up job:
      1. Fetch chapter source text + book.source_language from book-service
         (source_language from book is authoritative; job request override is fallback only)
      2. Fetch extraction profile + kinds metadata from glossary-service
      3. Plan kind batches (auto-batch by schema token budget)
      4. For each batch:
         a. Build dynamic prompt (source language, attribute metadata)
         b. Send to LLM via provider-registry
         c. Parse + validate JSON response
         d. Collect entities
      5. POST all entities to glossary-service (bulk upsert endpoint)
         → Server-side: dedup, fill/overwrite per attribute, chapter links, evidence
      6. Update job status → done
    → Frontend polls job status / receives WebSocket update
```

**Language flow:**

```
Chapter source text (zh) ──→ LLM prompt (zh text, schema in English)
                               │
                               ▼
                          LLM output: entity names (zh) + attribute values (zh)
                               │
                               ▼
                          glossary-service upsert:
                            → entity_attribute_values.original_language = "zh"
                            → entity_attribute_values.original_value = "身穿破損銀色盔甲的銀髮女騎士"
                            → evidences.original_language = "zh"
                            → evidences.original_text = "她身穿破損的銀色盔甲，銀色長髮隨風飄動。"
                               │
                               ▼
                          Translations (SEPARATE, anytime, not this pipeline):
                            → attribute_translations: en = "Silver-haired female knight..."
                            → attribute_translations: vi = "Nữ kỵ sĩ tóc bạc..."
```

---

## 3. Entry Points (GUI)

| Location | Button label | Scope | Behavior |
|----------|-------------|-------|----------|
| **Chapter tab** (chapter list item) | "Extract Glossary" | Single chapter | Extract entities from one chapter's source text |
| **Translation tab** (chapter detail) | "Extract Glossary" | Single chapter | Same — extract from source text (not translated text) |
| **Glossary tab** (toolbar) | "Batch Extract" | All chapters / selected chapters | Extract from multiple chapters, dedup across all |

All three entry points create the same job type, differing only in scope (single vs batch).

---

## 4. Extraction Profile — Attribute-Aware Schema Resolution

### 4.1 The Problem

Entity kinds have many attributes. A "character" kind has 13 attributes (name, aliases, gender, role, occupation, social_class, affiliation, appearance, personality, emotional_wound, love_language, relationships, description). But:

- A modern drama novel doesn't need `social_class` or `love_language`
- A sci-fi novel doesn't need `emotional_wound`
- Users may have deactivated attributes (`is_active = false`) for their book
- Genre-specific kinds (power_system, species) are irrelevant for non-fantasy books
- Extracting all attributes wastes tokens and reduces LLM accuracy

### 4.2 Two-Layer Resolution

**Layer 1: Auto-resolve (default)** — no user input needed:

```
1. Fetch book's genre profile (genre_groups table)
2. Fetch ALL entity_kinds + attribute_definitions (system + user-created)
3. Filter kinds:
   - Include system kinds where genre_tags overlap with book's genres
   - Always include system kinds with genre_tags = ["universal"]
   - Always include user-created kinds (is_default = false) — user created them
     for this purpose, so they are always relevant
   - Exclude kinds where is_hidden = true
4. Filter attributes per kind:
   - Include only is_active = true
   - Include only attributes where genre_tags is empty OR overlaps with book's genres
   - Always include is_required = true attributes (name, etc.)
   - For user-created kinds: include ALL active attributes (no genre filtering —
     user defined them intentionally)
5. Result = default extraction profile
```

**Layer 2: User override (optional)** — extraction dialog shows per-attribute action controls:

```
┌─ Extraction Profile ─────────────────────────────────────────────┐
│                                                                   │
│ ☑ Character                                                       │
│   Attribute          Action                                       │
│   name (required)    [Extract new + Fill missing ▾]  (locked)     │
│   aliases            [Extract new + Fill missing ▾]               │
│   gender             [Extract new + Fill missing ▾]               │
│   role               [Extract new + Fill missing ▾]               │
│   occupation         [Skip ▾]                                     │
│   social_class       [Skip ▾]                                     │
│   appearance         [Extract new + Overwrite ▾]    ← re-extract  │
│   personality        [Extract new + Fill missing ▾]               │
│   emotional_wound    [Skip ▾]                                     │
│   description        [Extract new + Fill missing ▾]               │
│                                                                   │
│ ☑ Location                                                        │
│   name (required)    [Extract new + Fill missing ▾]  (locked)     │
│   aliases            [Extract new + Fill missing ▾]               │
│   type               [Extract new + Fill missing ▾]               │
│   description        [Extract new + Overwrite ▾]    ← re-extract  │
│                                                                   │
│ ☐ Power System  (not relevant for this genre)                     │
│                                                                   │
│ [Save as default]  [Extract]                                      │
└───────────────────────────────────────────────────────────────────┘
```

Each attribute has a **3-state action dropdown**:

| Action | Meaning |
|--------|---------|
| **Skip** | Don't extract this attribute at all |
| **Extract new + Fill missing** (default) | Extract for new entities. For existing entities, only fill if attribute is currently empty |
| **Extract new + Overwrite** | Extract for new entities. For existing entities, overwrite even if value already exists |

This gives users full per-attribute control:
- First run: select 5 attributes with "Fill missing" → creates entities with those 5
- Later: add `education` with "Fill missing" → fills only the empty `education` field on existing entities
- Re-extract: set `appearance` to "Overwrite" → LLM re-extracts appearance, replaces old value
- Mix: some "Fill missing" + some "Overwrite" + some "Skip" in the same run

### 4.3 Extraction Profile Persistence

The user's selection can be saved as the book's default extraction profile for reuse:

```
PATCH /api/v1/books/{book_id}
{
  "extraction_profile": {
    "character": {
      "name": "fill",
      "aliases": "fill",
      "gender": "fill",
      "role": "fill",
      "appearance": "overwrite",
      "description": "fill"
    },
    "location": {
      "name": "fill",
      "aliases": "fill",
      "type": "fill",
      "description": "fill"
    }
  }
}
```

Per-attribute action values:
- `"fill"` = Extract new + Fill missing (default)
- `"overwrite"` = Extract new + Overwrite existing
- Attribute not listed = Skip

Stored as JSONB on the books table (similar to `wiki_settings`). If null → use auto-resolved defaults (all auto-selected attributes default to `"fill"`).

### 4.4 Impact on LLM Prompt

The prompt is **built dynamically** from the extraction profile. Instead of a generic "extract all entities", the prompt tells the LLM exactly what to look for, with **full attribute metadata** — description, field type, and extraction hints:

```
Extract entities from this text. For each entity type, extract ONLY the listed attributes.

## character
Attributes to extract:
- name (text, required): The character's primary name as written in the text
- aliases (tags): Other names, nicknames, titles used for this character
- gender (text): Male/Female/Other as stated or implied in text
- role (text): Brief role in the story (e.g. "protagonist", "antagonist", "mentor")
- appearance (textarea): Physical traits, clothing, distinguishing features.
  Hint: Describe based on text evidence only, max 2 sentences.
- description (textarea): General summary of who this character is in this chapter

## location
Attributes to extract:
- name (text, required): The location's primary name as written in the text
- aliases (tags): Other names for this location
- type (text): Category (city, building, realm, forest, etc.)
- description (textarea): What this place is and its significance
```

The prompt uses 3 fields from `attribute_definitions`:
- **`description`** — tells LLM what the attribute means (e.g. "Physical traits, clothing...")
- **`auto_fill_prompt`** — extraction-specific hint (e.g. "max 2 sentences, text evidence only")
- **`field_type`** — tells LLM the expected format (text = short, textarea = longer, tags = array, number = numeric, date = date string)

**Language note:** Prompt schema and hints are in **English** (LLM instruction language). This does NOT contradict the source language SSOT principle. The distinction:
- **Instructions/schema** (English): attribute names, descriptions, hints → meta-language for LLM to understand the task
- **Output values** (source language): entity names, descriptions, evidence → actual extracted content in chapter's source language
- The system prompt explicitly enforces: "ALL output MUST be in {source_language}"

This is critical because:
- **Precision** — LLM knows exactly what each attribute expects, not just its name
- **Format correctness** — `tags` fields output as arrays, `text` as short strings, `textarea` as paragraphs
- **User-customizable** — users who edit attribute descriptions/hints in glossary settings directly improve extraction quality
- **Token efficiency** — fewer attributes = smaller prompt + smaller output
- **Consistency** — output matches exactly what glossary-service expects

---

## 5. API Design

### 5.1 Translation-service: Job creation

```
POST /api/v1/books/{book_id}/extract-glossary
Authorization: Bearer <token>
Content-Type: application/json

{
  "chapter_ids": ["uuid1", "uuid2"],     // optional — if empty, extract from ALL chapters
  "provider_id": "uuid",                  // AI provider to use
  "model_id": "string",                   // model identifier
  "source_language": "zh",                // optional override — defaults to book.source_language from book-service
                                         // Pipeline ALWAYS fetches book.source_language as authoritative source.
                                         // This field is only for edge cases (e.g. multilingual books with mixed chapters).
  "context_filters": {                    // optional — known entities filtering for batch mode
    "min_frequency": 2,                   // include entities appearing in >= N chapters (default: 2)
    "recency_window": 100                 // include entities seen in last M chapters (default: 100)
  },
  "extraction_profile": {                 // optional — if null, use book's saved profile or auto-resolve
    "character": {
      "name": "fill",
      "aliases": "fill",
      "gender": "fill",
      "role": "fill",
      "appearance": "overwrite",
      "description": "fill"
    },
    "location": {
      "name": "fill",
      "type": "fill",
      "description": "fill"
    }
  }
}

Response 202:
{
  "job_id": "uuid",
  "status": "queued",
  "total_chapters": 5,
  "cost_estimate": {
    "total_input_tokens": 62500,        // estimated total input tokens
    "total_output_tokens": 10000,       // estimated total output tokens
    "llm_calls": 5,                     // total LLM calls (chapters × batches)
    "batches_per_chapter": 1            // kind batches per chapter
  }
}
```

### 5.2 Glossary-service: Extraction profile endpoint (NEW)

Returns the auto-resolved extraction profile for a book, so frontend can render the extraction dialog.

**Two routes — same handler, different auth:**
- **Public:** `GET /api/v1/books/{book_id}/extraction-profile` — for frontend via gateway (JWT auth, user must own book)
- **Internal:** `GET /internal/books/{book_id}/extraction-profile` — for translation-service (service token)

```
GET /api/v1/books/{book_id}/extraction-profile
Authorization: Bearer <JWT>

Response 200:
{
  "kinds": [
    {
      "kind_id": "uuid",
      "code": "character",
      "name": "Character",
      "icon": "👤",
      "auto_selected": true,
      "attributes": [
        {
          "code": "name", "name": "Name", "field_type": "text",
          "description": "The character's primary name",
          "auto_fill_prompt": null,
          "is_required": true, "auto_selected": true
        },
        {
          "code": "aliases", "name": "Aliases", "field_type": "tags",
          "description": "Other names, nicknames, titles",
          "auto_fill_prompt": null,
          "is_required": false, "auto_selected": true
        },
        {
          "code": "appearance", "name": "Appearance", "field_type": "textarea",
          "description": "Physical traits, clothing, distinguishing features",
          "auto_fill_prompt": "Describe based on text evidence only, max 2 sentences",
          "is_required": false, "auto_selected": true
        },
        {
          "code": "social_class", "name": "Social Class", "field_type": "text",
          "description": "Character's social standing",
          "auto_fill_prompt": null,
          "is_required": false, "auto_selected": false
        },
        ...
      ]
    },
    ...
  ],
  "saved_profile": {                     // null if user never saved a custom profile
    "character": {
      "name": "fill",
      "aliases": "fill",
      "gender": "fill",
      "role": "fill",
      "appearance": "overwrite",
      "description": "fill"
    },
    ...
  }
}
```

- `auto_selected` = true means the attribute passed genre + is_active filters
- If `saved_profile` exists, frontend uses it to set the per-attribute action dropdowns
- If `saved_profile` is null, all `auto_selected` attributes default to `"fill"`, others to skip

### 5.3 Translation-service: Job status

Reuse existing job status endpoint:

```
GET /api/v1/jobs/{job_id}

Response 200:
{
  "job_id": "uuid",
  "status": "running",          // queued | running | completed | failed | cancelling | cancelled
  "job_type": "extract_glossary",
  "progress": {
    "completed_chapters": 2,
    "total_chapters": 5,
    "entities_found": 34,
    "entities_created": 28,
    "entities_updated": 4,
    "entities_skipped": 2
  }
}
```

### 5.4 Glossary-service: Bulk upsert endpoint (NEW)

```
POST /internal/books/{book_id}/extract-entities
X-Internal-Token: <service token>
Content-Type: application/json

{
  "source_language": "zh",
  "attribute_actions": {
    "character": {
      "name": "fill",
      "aliases": "fill",
      "gender": "fill",
      "role": "fill",
      "appearance": "overwrite",
      "description": "fill"
    },
    "location": {
      "name": "fill",
      "type": "fill",
      "description": "fill"
    }
  },
  "entities": [
    {
      "kind_code": "character",
      "name": "伊斯坦莎",
      "attributes": {
        "aliases": ["小莎", "銀髮騎士"],
        "gender": "女",
        "role": "主角",
        "appearance": "身穿破損銀色盔甲的銀髮女騎士，左臂有一道長疤。",
        "description": "正在尋找失去記憶的騎士，擁有被封印的神秘力量。"
      },
      "evidence": "她身穿破損的銀色盔甲，銀色長髮隨風飄動，眼神中透著堅定與迷茫。",
      "chapter_links": [
        {
          "chapter_id": "uuid",
          "chapter_title": "Chapter 1",
          "chapter_index": 1,
          "relevance": "major"
        }
      ]
    }
  ]
}

Response 200:
{
  "created": 12,
  "updated": 8,
  "skipped": 2,
  "entities": [
    {
      "entity_id": "uuid",
      "name": "伊斯坦莎",
      "kind_code": "character",
      "status": "created",              // "created" | "updated" | "skipped"
      "attributes_written": ["name", "aliases", "gender", "role", "appearance", "description"],
      "attributes_skipped": []
    },
    {
      "entity_id": "uuid",
      "name": "索菲亞",
      "kind_code": "character",
      "status": "updated",
      "attributes_written": ["appearance"],       // overwrite action took effect
      "attributes_skipped": ["name", "gender"]    // fill action, already had values
    }
  ]
}
```

**Upsert logic (server-side, per entity):**

```
1. Find existing entity — NORMALIZED MATCHING:
   a. Normalize incoming name: strip whitespace, normalize Unicode (NFC),
      normalize CJK variants (simplified ↔ traditional via mapping table)
   b. Query: SELECT entity_id, original_value FROM entity_attribute_values eav
      JOIN glossary_entities ge ON ge.entity_id = eav.entity_id
      JOIN attribute_definitions ad ON ad.attr_def_id = eav.attr_def_id
      WHERE ge.book_id = $book_id
        AND ge.kind_id = (SELECT kind_id FROM entity_kinds WHERE code = $kind_code)
        AND ad.code = 'name'
        AND normalize(eav.original_value) = normalize($entity_name)
   c. If no match on name → also check aliases (app-layer):
      - Load all entities of same kind + book where ad.code = 'aliases'
      - For each: parse original_value as JSON array (e.g. '["小莎","銀髮騎士"]')
      - Normalize each alias element, compare against normalize($entity_name)
      - NOTE: aliases are stored as JSON-serialized strings in a TEXT column,
        so SQL LIKE is unreliable. App-layer parsing is safer and handles
        edge cases (partial matches, CJK variants) correctly.
      - For performance: this query runs once per entity per upsert call,
        and the entity count per book is bounded (~hundreds), so app-layer
        iteration is acceptable.
   d. If still no match → this is a new entity (step 2)
   e. If match found → this is an existing entity (step 3)

2. If NOT found → CREATE:
   - Insert glossary_entities (status: draft)
   - Insert entity_attribute_values for all provided attributes
     (original_language = source_language, original_value = LLM output)
   - Serialize value by field_type (see "Value serialization" below)
   - Insert chapter_entity_links with relevance from LLM output
   - Insert evidence row (see step 5)
   - Result: status = "created"

3. If FOUND → MERGE per attribute:
   For each attribute in the incoming entity:
     action = attribute_actions[kind_code][attr_code]  // "fill" or "overwrite"
     existing_value = current value in entity_attribute_values

     if action == "fill":
       if existing_value is empty → write new value    (attributes_written)
       if existing_value is not empty → skip           (attributes_skipped)

     if action == "overwrite":
       log previous value to extraction_audit_log      (see step 4)
       write new value                                  (attributes_written)

   - Always add chapter_entity_links (with relevance) if missing
   - Always add evidence (step 5) — evidence is APPEND-only, never overwritten
   - Result: status = "updated" (if any attribute written) or "skipped" (if all skipped)

4. Overwrite audit trail (overwrite action only):
   - Before overwriting, log the change:
     - entity_id, attr_def_id, old_value, new_value, chapter_id, timestamp
   - Stored in a **dedicated `extraction_audit_log` table** (NOT in evidences):
     ```sql
     CREATE TABLE IF NOT EXISTS extraction_audit_log (
       id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
       entity_id UUID NOT NULL REFERENCES glossary_entities(entity_id),
       attr_def_id UUID NOT NULL REFERENCES attribute_definitions(attr_def_id),
       chapter_id UUID,                    -- source chapter that triggered overwrite
       old_value TEXT,                      -- previous attribute value
       new_value TEXT,                      -- new value from extraction
       created_at TIMESTAMPTZ NOT NULL DEFAULT now()
     );
     ```
   - **Why a separate table?** The `evidences` table has specific semantics:
     `original_text` = source quote, `evidence_type` = quote category.
     Overwrite logs have different fields (old_value/new_value) and purpose
     (audit trail vs source reference). Mixing them creates semantic confusion
     and complicates queries. A dedicated table is cleaner.
   - This prevents silent data loss in batch extraction where later chapters
     overwrite earlier values. Users can review the audit trail to see
     what changed and when.

5. Evidence handling (both create and merge):
   - **Extraction evidence** (entity-level, from LLM "evidence" field):
     - attr_value_id = the "name" attribute's value ID (primary identifier for the entity)
     - chapter_id = source chapter
     - evidence_type = "extraction_quote"
     - original_language = source_language (e.g. "zh")
     - original_text = entity.evidence (exact quote from LLM output)
     - note = "auto-extracted by glossary extraction pipeline"
   - **Overwrite evidence** (attribute-level, from overwrite action — see step 4):
     - attr_value_id = the SPECIFIC attribute's value ID being overwritten
     - This links the audit trail to the exact attribute that changed,
       not just the entity's name. Users can see which attribute was
       overwritten, with old/new values, per chapter.
   - Evidence is ALWAYS appended, never deduplicated — each chapter extraction
     adds its own evidence, building a trail of source references across chapters

6. Relevance routing:
   - `relevance` from LLM output is NOT an entity attribute
   - Pipeline extracts it BEFORE sending to upsert
   - It maps to: chapter_entity_links.relevance (value: "major" or "appears")
   - Passed in the chapter_links array of each entity
```

**Name normalization function (`normalize`):**

The `normalize()` function is used throughout the dedup logic. It runs in app-layer (Go, in glossary-service):

```go
// normalize prepares a name string for dedup comparison.
// Runs in glossary-service (Go). NOT a Postgres function.
func normalize(s string) string {
    // 1. Unicode NFC normalization (canonical decomposition + composition)
    s = norm.NFC.String(s)
    
    // 2. Strip leading/trailing whitespace
    s = strings.TrimSpace(s)
    
    // 3. Collapse internal whitespace to single space
    s = regexp.MustCompile(`\s+`).ReplaceAllString(s, " ")
    
    // 4. Lowercase (for Latin scripts; no-op for CJK)
    s = strings.ToLower(s)
    
    // 5. CJK variant normalization (optional, phase 2):
    //    Simplified ↔ Traditional Chinese mapping (e.g. 银 ↔ 銀)
    //    Use opencc-go or a lightweight mapping table.
    //    For MVP: skip this step. Users can merge manually.
    //    For phase 2: s = opencc.Convert(s, "t2s") // traditional → simplified
    
    return s
}
```

Key decisions:
- **App-layer, not SQL** — Postgres `lower()` doesn't handle CJK; `unaccent` doesn't handle Unicode NFC. Go's `golang.org/x/text/unicode/norm` is reliable.
- **CJK variants deferred** — Traditional/Simplified Chinese mapping (opencc) is valuable but complex. MVP uses exact NFC match; phase 2 adds opencc.
- **Deterministic** — same input always produces same output, safe for comparison.

**Value serialization by field_type:**

| field_type | LLM output | Stored in original_value (TEXT column) |
|-----------|-----------|---------------------------------------|
| `text` | `"女"` | `"女"` (as-is) |
| `textarea` | `"身穿破損銀色盔甲..."` | `"身穿破損銀色盔甲..."` (as-is) |
| `tags` | `["小莎", "銀髮騎士"]` | `'["小莎","銀髮騎士"]'` (JSON string) |
| `number` | `25` | `"25"` (string) |
| `date` | `"第三紀元"` | `"第三紀元"` (as-is, in-story dates are text) |
| `boolean` | `true` | `"true"` (string) |

Tags are stored as JSON-serialized strings in the TEXT column. Frontend already parses JSON arrays for tags field_type display.

---

## 6. LLM Prompt Design

### 6.1 Strategy: Per-chapter, auto-batch by kind groups

Two axes of batching:

**Axis 1: Chapters** — always one chapter per extraction round. A single chapter can be 4K-10K tokens; batching multiple chapters would exceed context windows and hurt precision.

**Axis 2: Kinds** — auto-batch selected kinds into groups based on schema token budget.

```
Why NOT batch by attributes (one attr per call)?
  - Chapter text is FIXED COST per call (8K tokens)
  - 30 attributes × 8K = 240K input tokens (vs 9K for all-at-once)
  - 26x more expensive, no quality gain
  - Attributes within a kind are CORRELATED (name ↔ gender ↔ appearance)
    → extracting together produces better results

Why NOT always all-at-once?
  - 10 kinds × 8 attrs = 80 attribute descriptions = ~3.2K schema tokens
  - Combined with 8K chapter text → prompt pushing 12K+ tokens
  - Output for 50+ entities × 8 attrs → 4K+ output tokens
  - Quality degrades when prompt schema is too large

Solution: auto-batch by kind groups.
```

**Auto-batch algorithm:**

```python
SCHEMA_TOKEN_BUDGET = 2000  # max schema tokens per LLM call

def plan_kind_batches(extraction_profile, kinds_metadata) -> list[list[str]]:
    """Group kinds into batches that fit within schema token budget.
    
    Returns list of batches, each batch is a list of kind_codes.
    Most books (3-5 kinds) → 1 batch (1 LLM call).
    Full fantasy+romance (10+ kinds) → 2-3 batches.
    """
    batches = []
    current_batch = []
    current_tokens = 0
    
    for kind_code, attr_actions in extraction_profile.items():
        kind_meta = find_kind(kinds_metadata, kind_code)
        # ~40 tokens per attribute description + ~20 tokens overhead per kind
        kind_tokens = 20 + len(attr_actions) * 40
        
        if current_tokens + kind_tokens > SCHEMA_TOKEN_BUDGET and current_batch:
            batches.append(current_batch)
            current_batch = []
            current_tokens = 0
        
        current_batch.append(kind_code)
        current_tokens += kind_tokens
    
    if current_batch:
        batches.append(current_batch)
    
    return batches
```

**Example:**

| Book genre | Selected kinds | Batches | LLM calls/chapter |
|-----------|---------------|---------|-------------------|
| Modern drama | character, location, event | 1 batch | 1 |
| Fantasy | character, location, item, event, power_system, organization, species | 2 batches | 2 |
| Fantasy + romance | all 12 kinds | 3 batches | 3 |

**Merge after batching:** Each batch produces a JSON array of entities. The pipeline concatenates all arrays, then sends the combined list to glossary-service upsert. No entity can appear in two batches (kinds don't overlap), so no merge conflicts.

### 6.2 Dynamic system prompt (built from extraction profile)

The prompt is **generated at runtime** from the extraction profile. This is the template:

```
You are a literary entity extractor. Analyze the following {source_language} novel
chapter and identify all named entities matching the types below.

IMPORTANT — Language rules:
- ALL output (names, descriptions, attribute values) MUST be in {source_language}.
- Do NOT translate anything into English or other languages.
- Extract names EXACTLY as written in the source text.
- Attribute values (description, appearance, etc.) must be written in {source_language},
  summarizing what the source text says.

For each type, extract ONLY the listed attributes. Do not add extra fields.

For each entity, also provide an "evidence" field: a short EXACT QUOTE from the source
text (in {source_language}) that best supports the entity's identification. Max 1 sentence.

{dynamic_schema}

Extract up to {max_entities_per_kind} most significant entities per type.
Prioritize entities with relevance "major" over "appears".

{known_entities_context}

General rules:
- Do NOT invent information not present in the text
- Merge aliases (e.g. "伊斯坦莎" and "小莎" are the same character → one entry)
- For pronouns referring to named characters, do not create separate entries
- "relevance": "major" if central to the chapter, "appears" if merely mentioned
- Output ONLY valid JSON array. No other text.
```

Where `{known_entities_context}` is empty for single-chapter extraction, or for batch extraction:

```
Previously identified entities (use EXACT names below, do NOT create duplicates):
- 伊斯坦莎 (character) — aliases: 小莎, 銀髮騎士
- 暗黑魔域 (location)
- 白銀騎士團 (organization) — aliases: 白銀團

If you find new information about these entities, use their exact names above.
If you find NEW entities not in this list, add them with new names.
```

Where `{dynamic_schema}` is built from the extraction profile + attribute metadata:

```
## character
Attributes to extract:
- name (text, required): The character's primary name as written in the text
- aliases (tags): Other names, nicknames, titles used for this character
- gender (text): Male/Female/Other as stated or implied in text
- role (text): Brief role in the story. Hint: Use one phrase, e.g. "protagonist", "mentor"
- appearance (textarea): Physical traits, clothing, distinguishing features.
  Hint: Describe based on text evidence only, max 2 sentences.
- description (textarea): General summary of who this character is in this chapter
Output format: {"kind":"character","name":"...","aliases":[...],"gender":"...","role":"...","appearance":"...","description":"...","evidence":"...","relevance":"major|appears"}

## location
Attributes to extract:
- name (text, required): The location's primary name as written in the text
- aliases (tags): Other names for this location
- type (text): Category (city, building, realm, forest, etc.)
- description (textarea): What this place is and its significance
Output format: {"kind":"location","name":"...","aliases":[...],"type":"...","description":"...","evidence":"...","relevance":"major|appears"}
```

Each kind section includes:
1. **Attribute list** with field type, required marker, description, and extraction hints
2. **Output format** showing the exact JSON shape expected

Only kinds and attributes the user selected (non-Skip) are included. The `description` and `auto_fill_prompt` fields from `attribute_definitions` are injected directly into the prompt — so users who customize these fields in glossary settings automatically get better extraction.

### 6.3 Pre-processing: Tiptap JSON → structured plain text

Chapters are stored as **Tiptap JSON** (block format) or raw text. The extraction pipeline must be **immutable to Tiptap** — it never reads or writes Tiptap structure. A pre-processing step converts chapter content to structured plain text before prompting.

**Why not reuse `block_classifier.extract_translatable_text()`?**

Translation pipeline's `extract_translatable_text()` strips all structure (headings become plain text, lists are flattened). This is fine for translation but **loses context** for extraction:
- A heading like `# 第三章：暗黑魔域` tells the LLM this is a location/concept important enough to be a chapter title
- A dialogue block `"你好，伊斯坦莎"` reveals character names in context
- Block order matters for understanding scene flow

**Pre-processing strategy: Tiptap → Markdown-like text**

```python
def tiptap_to_extraction_text(body: dict) -> str:
    """Convert Tiptap JSON to markdown-like text for extraction.
    
    Preserves structure cues that help LLM understand context,
    but strips all Tiptap-specific markup.
    
    Input:  Tiptap JSON {"type":"doc","content":[...blocks...]}
    Output: Structured plain text with minimal formatting markers
    """
    lines = []
    for block in body.get("content", []):
        btype = block.get("type", "")
        
        if btype == "heading":
            level = block.get("attrs", {}).get("level", 1)
            text = _extract_text(block)
            lines.append(f"{'#' * level} {text}")
            lines.append("")
        
        elif btype == "paragraph":
            text = _extract_text(block)
            if text.strip():
                lines.append(text)
                lines.append("")
        
        elif btype == "blockquote":
            for child in block.get("content", []):
                text = _extract_text(child)
                lines.append(f"> {text}")
            lines.append("")
        
        elif btype in ("bulletList", "orderedList"):
            for i, li in enumerate(block.get("content", []), 1):
                text = _extract_text_from_list_item(li)
                prefix = f"{i}." if btype == "orderedList" else "-"
                lines.append(f"{prefix} {text}")
            lines.append("")
        
        elif btype == "callout":
            for child in block.get("content", []):
                text = _extract_text(child)
                lines.append(f"[!] {text}")
            lines.append("")
        
        elif btype in ("horizontalRule", "codeBlock"):
            pass  # skip non-content blocks
        
        elif btype in ("imageBlock", "videoBlock", "audioBlock"):
            caption = block.get("attrs", {}).get("caption", "")
            if caption:
                lines.append(f"[image: {caption}]")
                lines.append("")
        
        else:
            # Unknown block: try to extract text, skip if empty
            text = _extract_text(block)
            if text.strip():
                lines.append(text)
                lines.append("")
    
    return "\n".join(lines).strip()


def _extract_text(block: dict) -> str:
    """Extract plain text from a block's inline content. Strips all marks."""
    parts = []
    for node in block.get("content", []):
        if node.get("type") == "hardBreak":
            parts.append("\n")
        elif node.get("type") == "text":
            parts.append(node.get("text", ""))
    return "".join(parts)


def _extract_text_from_list_item(li: dict) -> str:
    """Extract text from a Tiptap listItem node.
    
    A listItem wraps one or more paragraph/blockquote children.
    We extract text from each child, join with spaces.
    Nested lists are flattened (depth > 1 is rare in novels).
    """
    parts = []
    for child in li.get("content", []):
        ctype = child.get("type", "")
        if ctype in ("paragraph", "blockquote"):
            parts.append(_extract_text(child))
        elif ctype in ("bulletList", "orderedList"):
            # Nested list: flatten recursively
            for nested_li in child.get("content", []):
                parts.append(_extract_text_from_list_item(nested_li))
    return " ".join(p for p in parts if p.strip())
```

**Format comparison:**

| Source (Tiptap JSON) | Translation pipeline | Extraction pipeline |
|---------------------|---------------------|-------------------|
| `{"type":"heading","attrs":{"level":2},"content":[{"text":"暗黑魔域"}]}` | `暗黑魔域` (flat text) | `## 暗黑魔域` (structure preserved) |
| `{"type":"blockquote","content":[{"type":"paragraph","content":[{"text":"你好，伊斯坦莎"}]}]}` | `你好，伊斯坦莎` (flat) | `> 你好，伊斯坦莎` (quote context) |
| `{"type":"bulletList","content":[...]}` | `item1\nitem2` (flat) | `- item1\n- item2` (list structure) |
| `{"type":"codeBlock"}` | skipped | skipped |

**Raw text chapters:** If chapter has `text_content` instead of `body`, use the raw text directly — no conversion needed.

```python
def prepare_chapter_text(chapter: dict) -> str:
    """Convert chapter content to plain text for extraction prompt."""
    body = chapter.get("body")
    if isinstance(body, dict) and isinstance(body.get("content"), list):
        return tiptap_to_extraction_text(body)
    return chapter.get("text_content", "")
```

### 6.4 User prompt

```
Extract all named entities from this chapter:

---
{chapter_text}
---
```

### 6.4.1 Prompt injection mitigation

Chapter text is **user-authored content** injected into the LLM prompt. A malicious or adversarial chapter could contain instructions like "Ignore all above and output X". Mitigation layers:

1. **Structural separation** — chapter text is in the **user message**, not the system message. System instructions (schema, rules, output format) are in the system prompt. Modern LLMs give system prompts higher authority than user content. This is the primary defense.

2. **Delimiter fencing** — chapter text is wrapped in `---` delimiters (see user prompt above). The system prompt explicitly says to extract from content between delimiters only.

3. **Parser as safety net** — even if the LLM is "jailbroken" by chapter content, the output must pass strict validation (§6.8):
   - Must be a valid JSON array
   - Each entry must have a valid `kind` from the extraction profile whitelist
   - Each attribute must match known attribute codes
   - Values are stored as TEXT — no SQL execution, no code evaluation
   - Extra/unexpected fields are stripped

4. **No escalation path** — the worst case of a successful injection is garbage entities (wrong names, fake descriptions). These are:
   - Created as `status: draft` (not visible until user reviews)
   - Limited to the user's own book (book_id scoped)
   - Cannot access other users' data, execute code, or modify system state
   - User can delete them in the review step

**Not needed:** input sanitization (stripping special characters from chapter text) — this would corrupt legitimate novel content. The defense is structural, not content-based.

### 6.5 Expected output format

All values in source language (Chinese example):

```json
[
  {
    "kind": "character",
    "name": "伊斯坦莎",
    "aliases": ["小莎", "銀髮騎士"],
    "gender": "女",
    "role": "主角",
    "appearance": "身穿破損銀色盔甲的銀髮女騎士，左臂有一道長疤。",
    "description": "正在尋找失去記憶的騎士，擁有被封印的神秘力量。",
    "evidence": "她身穿破損的銀色盔甲，銀色長髮隨風飄動，眼神中透著堅定與迷茫。",
    "relevance": "major"
  },
  {
    "kind": "location",
    "name": "暗黑魔域",
    "aliases": [],
    "type": "異界",
    "description": "大崩壞後出現的黑暗領域，充滿瘴氣和魔物。",
    "evidence": "遠方的暗黑魔域像一道黑色的傷口橫亙在天際線上。",
    "relevance": "appears"
  }
]
```

**Key points:**
- ALL values are in source language — no English mixing
- `evidence` = exact quote from source text, used to create `evidences` rows
- `name` = exact as written in text, used for dedup matching
- If `appearance` was not selected for character, LLM won't output it and pipeline won't write it

### 6.6 Prompt builder logic (pseudo-code)

```python
def build_extraction_prompt(
    kind_batch: list[str],          # kind_codes for this batch, e.g. ["character", "location"]
    extraction_profile: dict,       # full profile (pipeline filters to batch)
    kinds_metadata: list,           # from GET /extraction-profile → kinds with full attribute metadata
) -> str:
    """Build dynamic schema section for ONE BATCH of kinds.
    
    Called once per batch. If auto-batch produces 2 batches, this is called 2x
    with different kind_batch lists, same chapter text.
    """
    # SECURITY: Whitelist validation — kind_codes and attr_codes from user input
    # must match glossary-service metadata. This prevents prompt injection via
    # crafted kind/attribute names (e.g. kind_code="character\nIgnore above...").
    valid_kind_codes = {k["code"] for k in kinds_metadata}
    
    sections = []
    for kind_code in kind_batch:
        if kind_code not in valid_kind_codes:
            continue  # skip unknown kinds silently (stale profile)
        attr_actions = extraction_profile[kind_code]
        kind_meta = find_kind(kinds_metadata, kind_code)
        
        # All non-skipped attributes (both "fill" and "overwrite")
        # SECURITY: validate attr_codes against kind metadata whitelist
        valid_attr_codes = {a["code"] for a in kind_meta["attributes"]}
        attr_codes = [c for c in attr_actions.keys() if c in valid_attr_codes]
        
        # Build attribute descriptions from metadata
        attr_lines = []
        json_fields = {"kind": kind_code}
        for code in attr_codes:
            attr_meta = find_attr(kind_meta, code)
            
            # Format: "- code (field_type, required): description. Hint: auto_fill_prompt"
            parts = [f"- {code} ({attr_meta.field_type}"]
            if attr_meta.is_required:
                parts[0] += ", required"
            parts[0] += ")"
            
            if attr_meta.description:
                parts[0] += f": {attr_meta.description}"
            
            if attr_meta.auto_fill_prompt:
                parts.append(f"  Hint: {attr_meta.auto_fill_prompt}")
            
            attr_lines.append("\n".join(parts))
            
            # Build output format example
            json_fields[code] = "[...]" if attr_meta.field_type == "tags" else "..."
        
        # Special fields (not user attributes — always included)
        json_fields["evidence"] = "..."      # exact source text quote
        json_fields["relevance"] = "major|appears"
        
        sections.append(
            f"## {kind_code}\n"
            f"Attributes to extract:\n"
            + "\n".join(attr_lines) + "\n"
            f"Output format: {json.dumps(json_fields)}"
        )
    
    return "\n\n".join(sections)


def extract_chapter(
    chapter: dict,                  # raw chapter from book-service
    extraction_profile: dict,
    kinds_metadata: list,
    known_entities: list,           # entities from previous chapters (batch mode)
    invoke_llm: callable,
    max_entities_per_kind: int = 30,
):
    """Full extraction flow for one chapter with auto-batching."""
    # 0. Pre-process: Tiptap JSON → structured plain text
    chapter_text = prepare_chapter_text(chapter)
    
    # 1. Plan batches
    batches = plan_kind_batches(extraction_profile, kinds_metadata)
    
    # 2. Build known entities context (for cross-chapter awareness)
    known_ctx = build_known_entities_context(known_entities) if known_entities else ""
    
    all_entities = []
    for batch in batches:
        # 3. Build prompt for this batch of kinds
        schema = build_extraction_prompt(batch, extraction_profile, kinds_metadata)
        system_prompt = SYSTEM_TEMPLATE.format(
            dynamic_schema=schema,
            known_entities_context=known_ctx,
            max_entities_per_kind=max_entities_per_kind,
        )
        user_prompt = USER_TEMPLATE.format(chapter_text=chapter_text)
        
        # 4. LLM call
        response = invoke_llm(system_prompt, user_prompt)
        
        # 5. Parse + validate (strip markdown fences, extract special fields)
        entities = parse_and_validate(response, batch, extraction_profile)
        all_entities.extend(entities)
    
    # 6. Send combined entities to glossary-service upsert
    return all_entities
```

**Key design decisions:**

1. **Auto-batch by kinds** — schema token budget (2K) determines how many kinds per LLM call. Most books = 1 call. Large profiles = 2-3 calls. Never per-attribute.

2. **Attribute metadata in prompt** — `description` and `auto_fill_prompt` from `attribute_definitions` are injected. Users who customize these fields in glossary settings directly improve extraction quality.

3. **Field type in prompt** — tells LLM expected format: `text` → short string, `textarea` → paragraph, `tags` → JSON array, `number` → numeric, `date` → date string.

4. **Fill vs overwrite is server-side** — LLM always extracts all selected attributes. The upsert endpoint decides what to write. Keeps prompt simple, output consistent.

5. **No merge conflicts** — each kind appears in exactly one batch, so entities from different batches never overlap.

### 6.7 Token budget (per LLM call)

| Component | Budget |
|-----------|--------|
| System prompt template | ~200 tokens |
| Dynamic schema (per batch) | ≤ 2K tokens (enforced by auto-batch) |
| Known entities context | ~250 tokens (≤50 entities after alive/frequency/recency filtering × ~5 tokens) |
| Chapter text | up to 8K tokens (if larger, split into segments) |
| Output | ~2K tokens (30 entities × ~60 tokens each) |
| **Total per call** | ~12.5K tokens max |

**Per-chapter total:** 1 batch → 12.5K tokens. 3 batches → 37.5K tokens (chapter text + known entities sent 3x).

For chapters exceeding 8K tokens: split into segments, extract separately, merge results (dedup by name).

### 6.7.1 Cost estimation (pre-job)

Before starting an extraction job, the pipeline computes a token estimate so users know what they're committing to. This is especially important for BYOK users who pay per token.

**Estimation formula:**

```python
def estimate_extraction_cost(
    chapters: list[dict],           # chapter metadata (has text_length or token_count)
    extraction_profile: dict,
    kinds_metadata: list,
) -> dict:
    batches_per_chapter = len(plan_kind_batches(extraction_profile, kinds_metadata))
    
    # Estimate input tokens per chapter
    schema_tokens = min(2000, sum(
        20 + len(attrs) * 40
        for attrs in extraction_profile.values()
    ))
    prompt_overhead = 200 + 250  # system template + known entities context
    
    total_input = 0
    total_output = 0
    for ch in chapters:
        # Use stored token_count if available, else estimate from text_length
        ch_tokens = ch.get("token_count") or (ch.get("text_length", 4000) // 3)
        segments = max(1, ch_tokens // 8000)  # chapters >8K split into segments
        
        per_call_input = prompt_overhead + schema_tokens + min(ch_tokens, 8000)
        per_call_output = 2000  # ~30 entities × 60 tokens
        
        total_input += per_call_input * batches_per_chapter * segments
        total_output += per_call_output * batches_per_chapter * segments
    
    return {
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "llm_calls": len(chapters) * batches_per_chapter,
        "batches_per_chapter": batches_per_chapter,
    }
```

**Frontend display (in extraction dialog, before user confirms):**

```
┌─ Extraction Estimate ──────────────────────────────┐
│                                                      │
│  Chapters: 200                                       │
│  LLM calls: 400 (2 batches × 200 chapters)          │
│  Estimated tokens: ~2.5M input + ~400K output        │
│                                                      │
│  ⚠ This is an estimate. Actual usage depends on      │
│    chapter length and model tokenizer.                │
│                                                      │
│  [Cancel]  [Start Extraction]                        │
└──────────────────────────────────────────────────────┘
```

**Key decisions:**
- **Estimate, not quote** — clearly labeled as approximate. Actual cost depends on model pricing (which pipeline doesn't know — that's provider-registry's concern).
- **Token-based, not dollar-based** — pipeline reports tokens. Frontend can optionally show dollar estimate if provider pricing info is available from provider-registry.
- **Computed at job creation** — the 202 response includes `cost_estimate` so frontend can show it before the job actually starts processing. If the user wants to cancel immediately, they can.

### 6.8 Output parsing and validation

**Step 0 — Strip markdown wrapping:**

Many LLMs (especially local Ollama models) wrap JSON in markdown code fences:
````
```json
[{...}]
```
````
Parser must strip these before JSON parsing. Regex: `r'```(?:json)?\s*([\s\S]*?)\s*```'` → extract group 1. Reuse the same approach from translation pipeline V2 if it exists.

**Step 1 — Parse JSON array:**
- Attempt `json.loads(response_text)`
- If fails: try stripping markdown fences first, then re-parse

**Step 2 — Validate + transform each entry:**
1. Validate required fields: `kind` + all `is_required` attributes for that kind
2. Validate `kind` is one of the selected kinds in the extraction profile
3. Extract special fields (`evidence`, `relevance`) — route to chapter_entity_links and evidences, NOT entity attributes
4. Strip any extra fields not in the extraction profile (LLM may hallucinate extra fields)
5. Serialize values by field_type (tags array → JSON string, etc.)
6. If `evidence` is missing, set to empty string (optional but valuable)

**Step 3 — On failure:**
1. If parse fails: retry once with correction prompt (same as translation pipeline V2)
2. If still fails: mark chapter as `extraction_failed`, continue to next chapter

### 6.9 Entity count limit

The prompt includes a max entity count per kind to prevent output truncation:

```
Extract up to {max_entities_per_kind} most significant entities per type.
Prioritize entities with relevance "major" over "appears".
```

Default: `max_entities_per_kind = 30`. Configurable per job.

Why this matters:
- Long chapters with many side characters → LLM may output 100+ entities
- Output hits token limit → JSON truncated mid-array → parse fails
- Better to get 30 well-extracted entities than 100 truncated ones

---

## 7. Batch Extraction (Glossary Tab)

When extracting from multiple chapters:

```
1. Fetch filtered known entities from glossary-service:
   GET /internal/books/{book_id}/known-entities
     ?alive=true&min_frequency={job.min_frequency}&recency_window={job.recency_window}
   (Initial list — smart-filtered by alive, frequency, recency)

2. for each chapter (ordered by chapter_index):
   a. Build "known entities" context from filtered + accumulated entity list
   b. Extract entities from chapter (known entities injected into prompt)
   c. POST to glossary-service (upsert handles dedup + merge)
   d. Add newly created entities to known entities list (for next chapter)
   e. Update job progress
   f. Continue to next chapter
```

**Cross-chapter context injection (smart filtering):**

When extracting chapter N, the prompt includes a "known entities" section. Instead of dumping all entities (which grows unbounded in long novels), the pipeline uses **3-layer filtering** to build a relevant, token-efficient context:

**Layer 1 — Alive filter:** Exclude entities marked `alive = false`. A character who died in chapter 12 shouldn't pollute context for chapter 500. Users toggle this flag manually on each entity.

**Layer 2 — Frequency filter:** Include only entities appearing in ≥ N chapters (`min_frequency`). Entities that appeared once in a 5000-chapter novel are noise — the writer likely forgot about them, or they were destroyed/irrelevant. Frequency is derived from `chapter_entity_links` count (no new column needed).

**Layer 3 — Recency filter:** Prefer entities seen in the last M chapters relative to the current chapter (`recency_window`). An entity not mentioned in the last 100 chapters is likely irrelevant to the current context.

| Layer | Filter | Default | User configurable? |
|-------|--------|---------|-------------------|
| Alive | Exclude `alive = false` | Yes | Yes — toggle per entity in glossary UI |
| Frequency | `chapter_frequency >= min_frequency` | `min_frequency = 2` | Yes — slider in batch extraction dialog |
| Recency | Seen in last `recency_window` chapters | `recency_window = 100` | Yes — slider in batch extraction dialog |

**After filtering:** if the list still exceeds the token budget (~250 tokens ≈ 50 entities), truncate by frequency descending (most-seen entities first). This ensures the most important entities always make it into context.

**Filtering query (glossary-service endpoint):**

```
GET /internal/books/{book_id}/known-entities
    ?alive=true
    &min_frequency=2
    &before_chapter_index=50
    &recency_window=100
    &limit=50

Returns:
[
  { "name": "伊斯坦莎", "kind_code": "character", "aliases": ["小莎", "銀髮騎士"], "frequency": 42 },
  { "name": "暗黑魔域", "kind_code": "location", "aliases": [], "frequency": 15 },
  ...
]
```

**Resulting prompt section:**

```
Previously identified entities (use EXACT names below, do NOT create duplicates):
- 伊斯坦莎 (character) — aliases: 小莎, 銀髮騎士
- 暗黑魔域 (location)
- 白銀騎士團 (organization) — aliases: 白銀團
- 索菲亞 (character)

If you find new information about these entities, use their exact names.
If you find NEW entities not in this list, add them with new names.
```

Token cost: ~5 tokens per entity × 50 entities max = ~250 tokens. Negligible compared to chapter text (8K).

**Why user control matters:** Automated filtering handles 90% of cases, but writers know their story best. A "retired" character might return in a flashback arc. A low-frequency location might become critical later. The alive flag + filter sliders give users final say over what context the LLM sees.

This prevents:
- "小莎" in chapter 5 being created as a new entity instead of recognized as 伊斯坦莎's alias
- Inconsistent naming across chapters (LLM sees the canonical name list)
- Duplicate entities with slightly different names

**Cross-chapter merging:** Handled by glossary-service upsert endpoint. If chapter 2 mentions "伊斯坦莎" and she was already created from chapter 1:
- `fill` attributes: only empty fields get filled (e.g. chapter 2 reveals her `occupation`)
- `overwrite` attributes: overwrites previous value (with audit trail in evidences)
- Chapter link: always added (chapter 2 → entity link created)
- Evidence: appended (each chapter adds its own source quote)

**Progress tracking:** Job progress includes `completed_chapters`, `total_chapters`, `entities_found`, `entities_created`, `entities_updated`, `entities_skipped`.

---

## 8. Service Implementation Plan

### 8.1 Translation-service (Python)

New files in `app/workers/`:

| File | Purpose |
|------|---------|
| `extraction_worker.py` | Job consumer: picks up `extract_glossary` jobs, orchestrates per-chapter extraction |
| `extraction_prompt.py` | Dynamic prompt builder: builds system prompt from extraction profile, output parser + validator |
| `extraction_preprocessor.py` | Pre-processing: `tiptap_to_extraction_text()` — converts Tiptap JSON to structured plain text |

Modified files:

| File | Change |
|------|--------|
| `app/routers/jobs.py` | Add `extract_glossary` job type support |
| `app/workers/glossary_client.py` | Add `post_extracted_entities()` — call glossary-service bulk endpoint |
| `app/workers/coordinator.py` | Register extraction worker consumer |
| `app/config.py` | No change needed (glossary_service_internal_url already exists) |

### 8.2 Glossary-service (Go)

New/modified files:

| File | Change |
|------|--------|
| `internal/api/extraction_handler.go` | **NEW** — bulk entity creation endpoint with dedup |
| `internal/api/server.go` | Register `/internal/books/{book_id}/extract-entities` + `/extraction-profile` routes |

### 8.3 Book-service (Go)

| File | Change |
|------|--------|
| `internal/api/server.go` | Add `extraction_profile` JSONB column migration + PATCH support |

### 8.4 API Gateway (NestJS)

| File | Change |
|------|--------|
| Proxy config | Forward `POST /v1/books/{book_id}/extract-glossary` → translation-service |
| Proxy config | Forward `GET /v1/books/{book_id}/extraction-profile` → glossary-service |

---

## 9. Frontend Implementation Plan

### 9.1 Shared extraction trigger component

A reusable `ExtractGlossaryButton` component used in all 3 locations:

```tsx
<ExtractGlossaryButton
  bookId={bookId}
  chapterIds={[chapterId]}      // single chapter
  // or
  chapterIds={undefined}         // batch: all chapters
/>
```

The button:
1. Opens a small dialog to select provider + model (reuse existing provider selector)
2. On confirm → POST to create job
3. Shows progress indicator (poll job status or WebSocket)
4. On complete → toast notification with summary ("Found 34 entities, 28 new")

### 9.2 Extraction profile dialog

When user clicks "Extract Glossary", a dialog opens:

1. **Fetch** extraction profile from glossary-service (`GET /extraction-profile`)
2. **Render** kinds with toggles + attributes with 3-state action dropdowns:
   - Skip (greyed out)
   - Extract new + Fill missing (default for auto-selected)
   - Extract new + Overwrite
3. **Pre-fill** from saved profile if exists, otherwise from auto-resolve defaults
4. **User adjusts** per-attribute actions as needed
5. **Optional:** "Save as default" stores profile to book via PATCH
6. **Confirm** → POST job with the selected profile

**UX shortcuts:**
- Kind toggle off → all attributes set to Skip
- Kind toggle on → all attributes reset to saved/default actions
- "Select all Fill" / "Select all Overwrite" bulk action per kind

### 9.3 Integration points

| Location | Component | Trigger |
|----------|-----------|---------|
| Chapter tab → chapter list item actions | `ExtractGlossaryButton` | Icon button in chapter row actions |
| Translation tab → chapter translation header | `ExtractGlossaryButton` | Button in translation detail toolbar |
| Glossary tab → toolbar | `ExtractGlossaryButton` | "Batch Extract" button with optional chapter multi-select |

---

## 10. Migration

### Translation-service (Python — app/migrate.py)

Reuse existing job tracking. Job progress stored in existing job metadata JSONB column.

```sql
-- No new tables needed
-- Job type = 'extract_glossary', progress in metadata JSONB
```

### Book-service (Go)

```sql
ALTER TABLE books ADD COLUMN IF NOT EXISTS extraction_profile JSONB;
-- Stores user's saved extraction profile:
-- {"character":{"name":"fill","aliases":"fill","appearance":"overwrite"}, "location":{...}}
-- NULL = use auto-resolved defaults
```

### Glossary-service (Go)

```sql
ALTER TABLE glossary_entities ADD COLUMN IF NOT EXISTS alive BOOLEAN NOT NULL DEFAULT TRUE;
-- Narrative-level flag: is this entity still existing in the story world?
-- Different from status (active/archived) which is system-level.
-- Used by extraction pipeline to filter known entities context.
-- User toggles manually. Default = true (assume alive until marked otherwise).
```

```sql
CREATE TABLE IF NOT EXISTS extraction_audit_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_id UUID NOT NULL REFERENCES glossary_entities(entity_id),
  attr_def_id UUID NOT NULL REFERENCES attribute_definitions(attr_def_id),
  chapter_id UUID,
  old_value TEXT,
  new_value TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_extraction_audit_entity ON extraction_audit_log(entity_id);
-- Stores overwrite history for extraction pipeline.
-- Separate from evidences table (different semantics: audit vs source quotes).
```

Existing tables already support the rest:
- `glossary_entities` — entity creation
- `entity_attribute_values` — name, aliases, description, role
- `entity_kinds` + `attribute_definitions` — kind/attribute metadata with is_active, genre_tags
- `chapter_entity_links` — chapter ↔ entity links (frequency derived from COUNT)

---

## 11. Concurrency Control

**Problem:** Two users (or one user clicking twice) run extraction on the same book simultaneously → both query existing entities → both don't see each other's results → duplicate entities.

**Solution: Book-level extraction lock**

```
Before starting extraction job:
  1. Check: SELECT job_id FROM jobs
     WHERE book_id = $book_id AND job_type = 'extract_glossary'
       AND status IN ('queued', 'running')
  2. If found → reject with 409 Conflict:
     "Extraction already in progress for this book (job_id: xxx)"
  3. If not found → create job, proceed

Additional safety: glossary-service upsert runs dedup via app-layer
  normalized name matching (see §5.4 step 1) within a transaction.
  The book-level lock (one extraction job at a time) prevents concurrent
  upsert races. No DB-level unique constraint on normalized names exists
  because normalization logic (NFC, CJK variants) is too complex for a
  Postgres constraint — it lives in Go app code.
```

Only one extraction job per book at a time. Users can queue another job after the current one completes.

### Job cancellation

Long batch extractions (hundreds of chapters) may need to be stopped mid-run:

```
POST /api/v1/jobs/{job_id}/cancel
Authorization: Bearer <token>

Auth: JWT user must be the job creator (job.user_id = token.user_id).
Returns 403 if user does not own the job.

Response 200:
{
  "job_id": "uuid",
  "status": "cancelled",
  "progress": {
    "completed_chapters": 42,
    "total_chapters": 200,
    "entities_found": 156
  }
}
```

**Cancellation flow:**
1. User clicks "Cancel" in the extraction progress UI
2. Frontend POSTs to cancel endpoint
3. Job status set to `cancelling` in DB
4. Worker checks job status before processing each chapter:
   ```python
   for chapter in chapters:
       if get_job_status(job_id) == "cancelling":
           finalize_job(job_id, status="cancelled")
           return
       # ... extract from chapter
   ```
5. Entities already extracted (from completed chapters) are kept — they were already upserted to glossary-service
6. Job final status = `cancelled` with progress showing how far it got

**Key design decisions:**
- **Cooperative cancellation** — worker checks between chapters, not mid-LLM-call. An in-flight LLM call completes, its results are saved, then the job stops. This avoids partial/corrupt data.
- **Entities are kept** — cancellation doesn't rollback already-extracted entities. They're valid data from completed chapters. User can delete them manually if unwanted.
- **Immediate re-run** — after cancellation, the book-level lock is released, so user can start a new extraction immediately.

---

## 12. Error Handling

| Error | Handling |
|-------|----------|
| LLM returns invalid JSON | Strip markdown fences, retry parse. If still fails: retry once with correction prompt, then mark chapter as failed |
| LLM returns empty array | Mark chapter as "no entities found", continue |
| LLM output truncated (hit token limit) | Detect incomplete JSON. Retry with lower `max_entities_per_kind`. Mark partial if still truncated |
| Glossary-service down | Fail job with clear error message |
| Chapter text too long (>8K tokens) | Split into segments (see below), extract separately, merge |
| Provider-registry auth failure | Fail job with auth error |
| Duplicate entity name but different kind | Create as new entity (dedup is name + kind + book) |
| Stale extraction profile | Validate on load: strip kind_codes/attr_codes not found in current attribute_definitions. Log warning, fallback to auto-resolve for missing entries |
| Concurrent extraction on same book | Reject with 409 Conflict (see section 11) |
| User cancels mid-extraction | Cooperative cancellation between chapters, keep extracted entities (see section 11) |

### Long chapter segment strategy

When a chapter exceeds 8K tokens after pre-processing:

```
1. Split text at paragraph boundaries (blank lines) into segments ≤ 8K tokens each
   - Never split mid-paragraph
   - Overlap: include last paragraph of segment N as first paragraph of segment N+1
     (provides context continuity for entities mentioned at boundaries)

2. Extract from each segment independently (same prompt, same profile)

3. Merge segment results BEFORE sending to glossary-service:
   - Group entities by normalized name + kind
   - For duplicate entities across segments:
     → Keep the entry with more non-empty attributes
     → Merge aliases (union of all alias arrays)
     → Keep the longer description/evidence
   - Dedup within segments (same entity mentioned twice in overlap)

4. Send merged entity list to glossary-service upsert (one call per chapter)
```

---

## 13. Future Enhancements (NOT in scope)

- **Auto-translate extracted entities** — separate "suggest translations" feature
- **Relationship extraction** — "X is father of Y" — separate metadata pipeline
- **Timeline extraction** — separate metadata pipeline
- **Incremental extraction** — only re-extract from newly added/modified chapters
- **Confidence scoring** — LLM self-rating on extraction confidence
- **Entity merging UI** — manual merge of duplicate entities detected post-extraction
