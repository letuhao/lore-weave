# ADR — Event wall-clock date (in-story)

> **Status:** Accepted (2026-04-25, session 51 cycle 49 / C18 🏗 DESIGN+BUILD bundle).
> **Decision:** Add nullable `event_date_iso` (TEXT, ISO with optional truncation) to `:Event` nodes; populate via LLM prompt update + best-effort Python parse of existing `time_cue` strings as one-shot backfill; expose `event_date_from`/`event_date_to` Query params on the timeline endpoint.
> **Closes-on-BUILD:** D-K19e-α-02.
> **BUILD cycle:** **same cycle** (C18 — DESIGN+BUILD bundle per user approval, matching C17's pattern).
> **Related plan row:** [Track 2/3 Gap Closure §4 C18](./KNOWLEDGE_SERVICE_TRACK2_3_GAP_CLOSURE_PLAN.md#c18--event-wall-clock-date-p5-xl-design-first).
> **KSA amendments:** §3.4 (Neo4j schema — `:Event` gains `event_date_iso`), §5.1 (extraction prompt — event LLM emits ISO date when present).

---

## 1. Context — what D-K19e-α-02 represents

K19e Cycle α shipped the timeline endpoint with `after_order`/`before_order` (narrative position) + `after_chrono`/`before_chrono` (in-story sequence). But fiction often has explicit calendar dates ("June 1880", "the third year of the war", "TA 3019") and users want to filter the timeline by **wall-clock dates** — "show me everything between 1880 and 1882" or "what happened in spring 1881?".

The current `:Event` schema has no date property. The K17.6 LLM event extractor already captures a free-text `time_cue` ("at dawn", "next spring", "summer 1880") for narrative display, but this is unstructured — Cypher can't `WHERE` on it, and a string range query on `"summer 1880"` vs `"the next morning"` is meaningless.

**What "wall-clock date" means in this codebase**: the in-story calendar date the event takes place, NOT the chapter publication date. For Lord of the Rings ch.1 (published 1954), the in-story event is in TA 3001, so chapter `published_date` is useless as a fallback signal.

**Concrete failure trace** (today, on hobby data):

1. User has a project with a multi-decade family saga.
2. Timeline tab shows 200 events sorted by `event_order` (the order they appear in the text).
3. User wants "events in the 1880s only" — currently impossible. They'd have to scroll the entire list and read every `time_cue` to mentally filter.
4. The narrative `event_order` axis is also unhelpful when the saga has flashbacks: chapter 1 is in 1920 (frame story), chapter 2 is a flashback to 1880. Events sorted by `event_order` interleave the eras.

---

## 2. Existing surface (audited 2026-04-25)

### 2.1 :Event schema (Neo4j, K11.7)

[`app/db/neo4j_repos/events.py:98-123`](../../services/knowledge-service/app/db/neo4j_repos/events.py#L98-L123). Fields: `id, user_id, project_id, title, canonical_title, summary, chapter_id, chapter_title, event_order, chronological_order, participants, confidence, source_types, evidence_count, mention_count, archived_at, created_at, updated_at`. **No date field.**

### 2.2 LLM event extractor (K17.6)

[`llm_event_extractor.py:58-67`](../../services/knowledge-service/app/extraction/llm_event_extractor.py#L58-L67). The `_LLMEvent` Pydantic model already has `time_cue: str | None` capturing the free-text temporal hint. The K17.6 prompt at [`event_extraction.md`](../../services/knowledge-service/app/extraction/llm_prompts/event_extraction.md) instructs the LLM to extract `time_cue` from TEXT but explicitly **does not invent dates** (rule §4: "do not invent a date").

`LLMEventCandidate` (the post-resolution output passed to the writer) includes `time_cue` but no structured date.

### 2.3 Event writer + Cypher upsert

[`merge_event` at events.py:182](../../services/knowledge-service/app/db/neo4j_repos/events.py#L182) — does not accept a date param. `_MERGE_EVENT_CYPHER` does not set any date prop.

`pass2_writer.py:write_pass2_extraction` calls `merge_event(...)` for each `LLMEventCandidate`; no date is threaded through.

### 2.4 Timeline router (K19e Cycle α)

[`app/routers/public/timeline.py:56-86`](../../services/knowledge-service/app/routers/public/timeline.py#L56-L86) — Query params: `after_order`, `before_order`, `after_chrono`, `before_chrono`. Reversed-range → 422.

The Cypher predicates filter on `e.event_order` and `e.chronological_order`. Adding `event_date_iso` filters means adding parallel Cypher predicates and Query params.

### 2.5 What the audit confirms

- LLM already captures temporal hints — the path of least resistance is one extra optional JSON field in the prompt schema.
- No DDL change needed. Neo4j schema is implicit (`MERGE` adds props on first write); no Postgres DDL touched.
- Backfill can re-use existing `:Event.time_cue` values without an LLM round-trip if a Python parser handles common ISO-y patterns.
- Timeline filter is a 1:1 mirror of the existing `(after, before)` shape.
- 1 prompt file + 4 code files + 1 router file + 2 test files for the plumbing; 1 NEW parser util + 1 NEW backfill helper.

---

## 3. Decision — `event_date_iso` TEXT (ISO with optional truncation), LLM-extracted, best-effort backfill from `time_cue`

### 3.1 Storage shape: `event_date_iso` TEXT (Neo4j string property)

Format: ISO 8601 with optional truncation:
- `"YYYY"` — year-only ("1880")
- `"YYYY-MM"` — year-month ("1880-06" for "summer 1880" → June)
- `"YYYY-MM-DD"` — full date ("1880-06-15")

ISO format makes string-comparison range queries sort-stable: `"1880" < "1880-06" < "1880-06-15" < "1881"`. Range filters in Cypher use `e.event_date_iso >= $from AND e.event_date_iso <= $to`. The FE compares as strings (no parsing required for sort).

**Why TEXT instead of Neo4j `date` type**: Neo4j's `date()` builtin requires complete `YYYY-MM-DD`. Partial dates ("summer 1880" → "1880-06") would force us to invent a representative day, losing the precision signal. TEXT preserves the LLM's actual confidence ("1880" vs "1880-06-15" tells the FE how precise the extraction was).

**Why not three int fields `(year, month, day)`**: filter Cypher would need three predicates per range, the comparison logic is more error-prone, and the FE would have to reconstruct the display string. TEXT is one column, one predicate per bound, and the wire format is the display format.

**Negative dates / fictional eras**: prefixing with a non-digit (e.g. `"TA-3019"` for Tolkien's Third Age) breaks string sort. **Out of scope for v1** — fictional eras stay as `time_cue` free text only. ADR §6 documents this limit.

### 3.2 Source: LLM prompt update

The event extraction prompt gains a new optional output field `event_date` (ISO with truncation). Prompt rule:

> **`event_date` is optional.** Extract ONLY when TEXT contains an explicit date or year that maps cleanly to ISO. Acceptable: "summer 1880" → `"1880-06"`, "June 15, 1880" → `"1880-06-15"`, "the year was 1880" → `"1880"`. **Reject** vague references ("long ago", "the next morning", "in his youth") — leave null. Reject fictional-era prefixes ("TA 3019", "Year of the Dragon"). The FE displays `time_cue` for those.

Existing `time_cue` field stays in `_LLMEvent` / `LLMEventCandidate` for transient extraction-time use. `event_date` is the structured filter axis that DOES reach the persisted `:Event` node.

**Pre-C18 limitation surfaced during REVIEW-CODE**: `time_cue` is currently NOT persisted on the `:Event` node (`merge_event` doesn't accept it; `pass2_writer` drops it with comment "tracked for K18+"). So vague hints like "the next morning" or "in his youth" are lost at write time today. C18 doesn't fix that — it adds the *structured* date axis. Persisting `time_cue` for narrative display would be a separate cycle (logged as **C18-DEF-01**).

**Why LLM, not Python parse only**: LLM already reads the chapter for event extraction; one additional schema field is free at zero marginal cost. Python parsing of `time_cue` post-extraction is the **backfill** path (cheaper than LLM round-trip for old data) but a weaker signal than LLM-with-context.

### 3.3 Backfill: best-effort Python parser over existing `time_cue` strings

A pure function `parse_time_cue_to_iso(text: str) -> str | None` handles:

| Pattern | Output |
|---|---|
| `r"\b(\d{4})\b"` (year alone, in range 1000-2999) | `"YYYY"` |
| `r"\b(January|February|...|December)\s+(\d{4})\b"` | `"YYYY-MM"` |
| `r"\b(\d{4})-(\d{2})-(\d{2})\b"` (already ISO) | `"YYYY-MM-DD"` if valid |
| `r"\b(spring|summer|autumn|fall|winter)\s+(\d{4})\b"` (season → month) | `"YYYY-03"`/`"YYYY-06"`/`"YYYY-09"`/`"YYYY-12"` |
| Anything else | `None` |

One-shot CLI walks every `:Event` with `time_cue IS NOT NULL AND event_date_iso IS NULL`, parses, writes via UPDATE Cypher. Idempotent (skips rows with non-null `event_date_iso`). Documented as "approximate — LLM re-extraction is the gold standard but $$$".

### 3.4 Timeline filter exposure

Add to [`timeline.py`](../../services/knowledge-service/app/routers/public/timeline.py):

```python
event_date_from: str | None = Query(
    None,
    description="ISO date (YYYY, YYYY-MM, or YYYY-MM-DD); inclusive lower bound on e.event_date_iso. C18 D-K19e-α-02.",
    pattern=r"^\d{4}(-\d{2}(-\d{2})?)?$",
)
event_date_to: str | None = Query(...)  # same shape, inclusive upper bound
```

Reversed range (`from > to`) → 422 (mirrors `after_order >= before_order` validation).

Cypher predicate: `($event_date_from IS NULL OR e.event_date_iso >= $event_date_from) AND ($event_date_to IS NULL OR e.event_date_iso <= $event_date_to)`. Events with `event_date_iso = NULL` are EXCLUDED when either filter is active (no-date events have no business answering "what happened in 1880?"). Documented in router docstring.

### 3.5 Why this combination

| Decision | Why this | Why not alternatives |
|---|---|---|
| TEXT with truncation | One column, sort-stable range, preserves precision, FE-display-equivalent | `date` strict (lossy on partials); `(year, month, day)` ints (3 predicates per range); `time_cue`-only (unsortable) |
| LLM prompt (with backfill) | Already in-loop for events; one extra optional JSON field | Compute from chapter `published_date` (wrong axis for fiction); Python parse only (weaker than LLM-with-context) |
| Best-effort backfill from time_cue | Cheap; idempotent; recovers most cases | LLM re-extraction (expensive); skip-entirely (permanent null for pre-deploy data) |
| `event_date_from`/`event_date_to` parallel to `after_order`/`before_order` | Consistent shape across timeline filters | Single `event_date_range: str` (parsing burden split BE/FE); reuse `after_order` (semantic confusion) |

---

## 4. Rejected alternatives

### 4.1 Storage: Neo4j `date` (strict ISO `YYYY-MM-DD`)

**Pro**: Cypher operators (`+`, `-`, comparison) work natively; type-safe.

**Con**: Forces full date for partials. "Summer 1880" becomes `"1880-06-15"` losing the "I don't actually know the day" signal. The FE can't distinguish year-only knowledge from precise-date knowledge. For fiction this matters — most events have year-only or year-month at best.

### 4.2 Storage: Three integer fields (`event_year`, `event_month`, `event_day`)

**Pro**: Exact precision tracking via nullability per field.

**Con**: Range queries need 3+ predicates. Display format reconstruction in the FE adds complexity. For sort, you'd need a Python-side comparator key like `(year or 9999, month or 13, day or 32)`. TEXT with truncation gets the same precision tracking with one column.

### 4.3 Storage: `event_date` Neo4j `date` + `event_date_precision: 'year'|'month'|'day'`

**Pro**: type-safe + precision flag.

**Con**: Two columns instead of one; range query has to UNION across precision values OR pick a sentinel day for ranged comparison. Adds complexity for marginal type-safety benefit.

### 4.4 Source: compute from chapter `published_date`

**Pro**: zero LLM cost; works for events in non-fiction or strictly contemporary fiction.

**Con**: Wrong signal for the dominant use case (fantasy/sci-fi/historical fiction where in-story year ≠ publication year). Lord of the Rings ch.1 published 1954, story is in TA 3001. Even contemporary fiction may have flashback chapters set decades earlier.

### 4.5 Source: Python parse of `time_cue` only (no LLM prompt change)

**Pro**: No prompt change → no $ cost → no need to re-extract existing chapters.

**Con**: Python parser sees only the LLM's free-text hint, not the surrounding context. "The next morning" needs the prior event's date; "in his youth" needs the character's birth year. LLM has the context; Python doesn't. Use LLM as primary, Python parser as backfill-only.

### 4.6 Backfill: LLM re-extraction over every existing chapter

**Pro**: highest accuracy; LLM with full context.

**Con**: Cost is per-chapter × per-user × per-model. At hobby scale a single user might have ~500 chapters across 5 books = $5–$50 in LLM cost for a backfill of historical data. Compared to the time_cue parser path which costs ~0¢ and recovers most explicit-date cases. LLM re-extraction is the user's option (manual re-extract per-chapter is already exposed); we don't need to force it cycle-wide.

### 4.7 Backfill: skip entirely (lazy population only)

**Pro**: zero migration risk.

**Con**: Pre-C18 events stay date-less forever. The user's existing project (the most likely first user of the new filter) sees an empty result for every date query. Best-effort parse from `time_cue` is cheap insurance.

---

## 5. Implementation sketch (BUILD-ready)

### 5.1 No DDL — Neo4j schema is implicit

`MERGE (e:Event {id: $id}) ON CREATE SET ..., e.event_date_iso = $event_date_iso` adds the property on first write. Existing nodes don't have it; reads return NULL. No migration step needed for the schema add itself; backfill is the data-population step (§5.5).

### 5.2 `Event` Pydantic model + Cypher upsert

[`events.py`](../../services/knowledge-service/app/db/neo4j_repos/events.py):

```python
class Event(BaseModel):
    ...
    event_date_iso: str | None = None  # NEW

# _MERGE_EVENT_CYPHER ON CREATE SET adds:
#   e.event_date_iso = $event_date_iso
# ON MATCH SET adds:
#   e.event_date_iso = coalesce($event_date_iso, e.event_date_iso)
```

`merge_event()` signature gains `event_date_iso: str | None = None`. Default None preserves all existing test sites (~14 callers across pass2_writer + pattern_writer + tests).

### 5.3 LLM prompt update + extractor schema

[`event_extraction.md`](../../services/knowledge-service/app/extraction/llm_prompts/event_extraction.md): add `event_date` to the JSON schema + add Rule §4 about ISO format + reject fictional/vague.

[`llm_event_extractor.py`](../../services/knowledge-service/app/extraction/llm_event_extractor.py):

```python
class _LLMEvent(BaseModel):
    ...
    event_date: str | None = None  # NEW; validated against pattern

class LLMEventCandidate(BaseModel):
    ...
    event_date: str | None  # threaded from _LLMEvent
```

Validator on `_LLMEvent.event_date` enforces the truncated-ISO regex `^\d{4}(-\d{2}(-\d{2})?)?$`; LLM output not matching → coerce to `None` (don't reject the whole event).

### 5.4 NEW `event_date_parser.py`

Pure function module at `app/utils/event_date_parser.py`:

```python
def parse_time_cue_to_iso(text: str) -> str | None:
    """Best-effort backfill: parse a free-text time_cue into a
    truncated ISO date string. Returns None for unparseable input.

    Patterns recognized (in order):
      1. r"^\\s*(\\d{4})-(\\d{2})-(\\d{2})\\s*$" — already-ISO YYYY-MM-DD
      2. r"\\b(January|...|December)\\s+(\\d{1,2}),?\\s+(\\d{4})\\b" → YYYY-MM-DD
      3. r"\\b(January|...|December)\\s+(\\d{4})\\b" → YYYY-MM
      4. r"\\b(spring|summer|autumn|fall|winter)\\s+(?:of\\s+)?(\\d{4})\\b" → YYYY-MM (season-to-month)
      5. r"\\b(\\d{4})\\b" — bare year in [1000, 2999]
    Order matters: more specific patterns win (longer match first).
    """
```

Pure function — no I/O, fully unit-testable. ~80 LOC + comprehensive test suite.

### 5.5 Backfill helper

NEW `app/db/migrations/backfill_event_date.py` (mirrors C17 backfill structure):

```python
async def run_backfill(session: CypherSession) -> BackfillResult:
    """Walk every :Event with time_cue NOT NULL AND event_date_iso IS NULL,
    parse via parse_time_cue_to_iso, write event_date_iso when parser
    returns a value. Idempotent — second run skips rows already populated.
    """
```

CLI entry point: `python -m app.db.migrations.backfill_event_date`. Logs `total_scanned, parsed, skipped_unparseable`.

### 5.6 pass2_writer wire-through

[`pass2_writer.py`](../../services/knowledge-service/app/extraction/pass2_writer.py): the existing event-write loop does:

```python
await merge_event(
    session,
    user_id=user_id, project_id=project_id,
    title=ev.name,
    summary=ev.summary,
    chapter_id=...,
    event_order=...,
    participants=...,
    source_type=source_type,
    confidence=ev.confidence,
)
```

Add `event_date_iso=ev.event_date,` to that call.

### 5.7 Timeline router filter

[`timeline.py`](../../services/knowledge-service/app/routers/public/timeline.py):

```python
event_date_from: str | None = Query(
    None,
    description="C18 D-K19e-α-02. Inclusive lower bound on e.event_date_iso. ISO YYYY / YYYY-MM / YYYY-MM-DD.",
    pattern=r"^\d{4}(-\d{2}(-\d{2})?)?$",
)
event_date_to: str | None = Query(
    None,
    description="C18 D-K19e-α-02. Inclusive upper bound on e.event_date_iso. ISO YYYY / YYYY-MM / YYYY-MM-DD.",
    pattern=r"^\d{4}(-\d{2}(-\d{2})?)?$",
)

# Reversed-range validation mirrors after_order/before_order:
if event_date_from and event_date_to and event_date_from > event_date_to:
    raise HTTPException(422, ...)

# Cypher predicate added to list_events_filtered:
#   AND ($event_date_from IS NULL OR e.event_date_iso >= $event_date_from)
#   AND ($event_date_to IS NULL OR e.event_date_iso <= $event_date_to)
# When EITHER filter is active, events with NULL event_date_iso are
# EXCLUDED — see docstring + test_timeline_excludes_dateless_events_when_filtered.
```

The `_LIST_EVENTS_FILTERED_CYPHER` constant in `events.py` gains the two new predicates. `list_events_filtered()` signature extends with the new params (default None → existing tests unaffected).

### 5.8 Wire-through table

| File | Change |
|---|---|
| `app/db/neo4j_repos/events.py` | `Event.event_date_iso` field; `_MERGE_EVENT_CYPHER` ON CREATE+ON MATCH; `merge_event()` param; `_LIST_EVENTS_FILTERED_CYPHER` predicates; `list_events_filtered()` params |
| `app/extraction/llm_prompts/event_extraction.md` | Schema add + Rule §4 reword |
| `app/extraction/llm_event_extractor.py` | `_LLMEvent.event_date` validator; `LLMEventCandidate.event_date` |
| `app/extraction/pass2_writer.py` | Pass `event_date_iso=ev.event_date` to `merge_event()` |
| `app/routers/public/timeline.py` | Two new Query params + reversed-range 422 + plumbing to `list_events_filtered` |
| NEW `app/utils/event_date_parser.py` | Pure parser function |
| NEW `app/db/migrations/backfill_event_date.py` | CLI shim + `run_backfill` helper |
| `tests/unit/test_event_date_parser.py` | NEW — ~12 tests for the parser (year, month-year, season, ISO passthrough, garbage, edge cases) |
| `tests/unit/test_event_date_backfill.py` | NEW — ~5 tests for the backfill helper (happy + idempotent + null-time_cue skip + unparseable skip) |
| `tests/unit/test_events_repo.py` | +2 tests — Event model field + merge_event roundtrip |
| `tests/unit/test_timeline_api.py` | +5 tests — date-from filter, date-to filter, reversed 422, NULL-excluded when filter active, both filters compose |
| `tests/unit/test_pass2_writer.py` | +1 test — event_date_iso threaded to merge_event |
| `tests/unit/test_llm_event_extractor.py` | +2 tests — _LLMEvent accepts valid event_date; rejects malformed (coerces to None) |

### 5.9 Test plan summary

~27 new tests covering: parser (12) + backfill (5) + repo (2) + router (5) + writer plumbing (1) + LLM extractor (2). Target: all 1557 existing tests still green; +27 ≈ 1584 total.

---

## 6. Open questions for BUILD cycle (CLARIFY pre-checks)

These get re-confirmed at BUILD time (or in this same cycle since C18 is bundled).

1. **Fictional-era prefixes** ("TA 3019", "Y3 of the Crown War"): explicitly OUT of scope per §3.1. Will surface in `time_cue` only. **Recommend deferring** to a future ADR if user requests fictional-calendar support — that's a meatier design question (need per-project calendar systems).

2. **Date precision flag**: should `event_date_iso = "1880"` be rendered to the user as `"1880"` (truncated) or `"1880-?"` (with explicit unknown marker)? **Recommend** wire-format = display-format ("1880"); the truncation IS the precision flag. FE can detect length.

3. **Timezone**: in-story dates are calendar-only, no timezone. ISO format is calendar dates without timezone. **No question to defer.**

4. **Event with `event_date` but no `time_cue`**: theoretical (LLM sees explicit ISO date in chapter) but possible. Both fields are independently optional. **No issue.**

5. **Reversed range semantics** at season-boundary: e.g. `from="1880-06"`, `to="1880"` — string compare says `"1880-06" > "1880"` so this is reversed. The 422 fires. But `from="1880"`, `to="1880-06"` says `"1880" < "1880-06"` — accepted, range is "year 1880 events with date precision year-only OR earlier in 1880". Hmm. Actually `e.event_date_iso >= "1880" AND e.event_date_iso <= "1880-06"` includes "1880" (year-only), "1880-01" through "1880-06" but EXCLUDES "1880-07"..."1880-12". That's the user's stated range. **Acceptable** — semantic matches the literal string sort.

6. **Backfill running concurrently with extraction writes**: backfill uses `WHERE event_date_iso IS NULL` so a concurrent write of `event_date_iso` (post-C18 LLM extraction) means backfill will skip that row on next pass. Idempotent. **No race issue.**

7. **REVIEW-DESIGN catch — tighten Query regex pattern**. ADR §5.7 has `^\d{4}(-\d{2}(-\d{2})?)?$` which accepts "1880-13" (invalid month) and "1880-02-30" (invalid day for February). The router would happily run a Cypher comparison against the malformed string — Cypher returns nothing (no event has month 13) but the user got no error. **BUILD-time fix**: tighten to `^\d{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01]))?)?$` which validates month [01-12] + day [01-31]. Won't catch Feb-30 (would need calendar awareness) but the cheap structural validation catches the dominant typo class.

8. **REVIEW-DESIGN catch — inclusive vs exclusive bound semantic differs from existing `after_order`**. Existing `after_order` is EXCLUSIVE (`e.event_order > $after_order`); my proposed `event_date_from` is INCLUSIVE (`e.event_date_iso >= $event_date_from`). This is intentional because dates often have natural inclusive bounds ("events in 1880" = `from="1880" to="1880"` inclusive both ends), whereas narrative-order ranges are typically exclusive (the "from" event is the anchor, not part of the range). **BUILD-time**: docstring on the router explicitly notes the inclusive semantic + reversed-range check uses `>` strictly (not `>=`).

9. **REVIEW-IMPL HIGH-1 — precision downgrade on ON MATCH**. (Caught + fixed during /review-impl.) `coalesce($event_date_iso, e.event_date_iso)` allowed a re-mention with less precision (e.g. "1880") to overwrite a previously-stored more precise value (e.g. "1880-06-15"). Mirroring confidence's max-wins pattern, the ON MATCH branch now uses a CASE that prefers the longer (more precise) ISO string when both are non-null. Source-scan regression test in `test_event_date_cypher.py` locks the invariant.

10. **REVIEW-IMPL MEDIUM-1 — year-range filter UX**. `from="1880" to="1880"` only matches events with EXACTLY `event_date_iso="1880"` (year-only precision); it does NOT include events with `"1880-06"` or `"1880-06-15"` because lexicographically `"1880-01" > "1880"`. To capture "all events in 1880" the user must pass `from="1880" to="1880-12-31"`. Acceptable BE semantic (literal string-range), but the FE should provide a year-only quick-pick that expands to the inclusive day-end pair. **Defer FE polish** — BE contract is correct, just non-obvious without the helper.

11. **REVIEW-IMPL MEDIUM-2 — parser BC/AD ambiguity**. `parse_time_cue_to_iso("1880 BC")` returns `"1880"` (the bare-year regex doesn't see the "BC" suffix), silently converting BC to AD. Fictional fiction set in antiquity is rare and recoverable via LLM re-extraction or manual edit. **Document in parser docstring as a known limitation**; don't fix in v1 since the alternative (rejecting any year with "BC"/"AD" context) creates more false negatives than the current false positives.

---

## 7. Closing checklist for C18 (DESIGN+BUILD bundle)

D-K19e-α-02 is fully cleared **only** when ALL of the following ship in this cycle:

- [ ] `Event` model gains `event_date_iso: str | None`
- [ ] `_MERGE_EVENT_CYPHER` ON CREATE + ON MATCH set the prop (coalesce on match — preserves existing if param is None)
- [ ] `merge_event()` signature gains `event_date_iso: str | None = None`
- [ ] `event_extraction.md` prompt updated: schema field + Rule §4 (ISO with truncation, reject vague/fictional)
- [ ] `_LLMEvent.event_date` field with validator coercing malformed → None
- [ ] `LLMEventCandidate.event_date` threaded from `_LLMEvent`
- [ ] `pass2_writer.py` passes `event_date_iso=ev.event_date` to `merge_event()`
- [ ] NEW `app/utils/event_date_parser.py` with `parse_time_cue_to_iso` + ~12 unit tests covering 5 patterns + garbage
- [ ] NEW `app/db/migrations/backfill_event_date.py` CLI + 5 unit tests (happy + idempotent + null-time_cue skip + unparseable skip + cross-tenant scan)
- [ ] Timeline router gains `event_date_from` / `event_date_to` Query (with regex pattern) + reversed-range 422 + Cypher predicates in `_LIST_EVENTS_FILTERED_CYPHER`
- [ ] `list_events_filtered()` signature accepts the two new params
- [ ] Test: dateless events EXCLUDED when either filter is active (regression lock — no silent inclusion)
- [ ] Test: full filter compose (from + to together)
- [ ] FE timeline filter UI — out-of-scope for pure-BE C18 cycle. Defer as C18-DEF-01 (next FE timeline touch)
- [ ] `/review-impl` 0 unresolved HIGH/MED on the BE surface
- [ ] KSA §3.4 (`:Event` schema) + §5.1 (event extraction prompt) amended
- [ ] Plan row C18 flipped `[ ]` → `[x]` with cycle detail
- [ ] SESSION_PATCH cycle 49 entry; D-K19e-α-02 marked cleared

When all rows above are checked, this ADR's status changes to "Accepted + shipped (commit hash)".
