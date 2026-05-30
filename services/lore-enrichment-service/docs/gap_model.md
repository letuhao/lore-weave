# Gap MODEL spec (RAID C6 — M1a)

> Pure-data spec the gap-detection **engine** (C7) consumes. Defines WHAT a gap
> is and HOW gaps are ranked — **not** how they are detected from a live
> knowledge graph (that traversal is C7 and is OUT of scope here).
>
> Code: [`app/gaps/model.py`](../app/gaps/model.py) · Fixtures:
> [`tests/fixtures/gaps_fengshen.json`](../tests/fixtures/gaps_fengshen.json) ·
> Tests: [`tests/test_gap_model.py`](../tests/test_gap_model.py)

## 1. Entity kinds

`EntityKind` is **extensible** but only `LOCATION` is modeled this cycle (demo
scope). String values mirror the C2 schema's lowercase `entity_kind`
vocabulary (`enrichment_proposal.entity_kind = 'location'`) so the model and the
persistence layer agree without translation. `CHARACTER` / `ITEM` / `FACTION`
are reserved enum members with **no dimension set** — calling `dimensions_for`
on them raises `KeyError` (no silent empty set).

| EntityKind | value | dimension set defined? |
|---|---|---|
| `LOCATION` | `location` | ✅ yes (this cycle) |
| `CHARACTER` | `character` | ⛔ reserved, not modeled |
| `ITEM` | `item` | ⛔ reserved, not modeled |
| `FACTION` | `faction` | ⛔ reserved, not modeled |

## 2. LOCATION dimension set (locked)

Exactly five dimensions, in this canonical order (the `Dimension` enum
declaration order — used everywhere for deterministic iteration):

| id | label | required? | weight (when missing) | expected payload shape |
|---|---|---|---|---|
| `history` | `历史` | **required** | 3.0 | prose: founding, key events, era, lineage of the place |
| `geography` | `地理` | **required** | 3.0 | prose: location, terrain, climate, layout/architecture |
| `culture` | `文化` | **required** | 3.0 | prose: customs, beliefs, daily life, governance, faction |
| `features` | `features` | optional | 2.0 | list: notable landmarks, relics, natural wonders |
| `inhabitants` | `inhabitants` | optional | 2.0 | list: residents, factions, notable figures tied to place |

- `历史 / 地理 / 文化` are **source-faithful Chinese** labels (output language
  is locked Chinese). `features / inhabitants` are intentionally **English**
  per the locked dimension set — do not romanize or translate either way.
- The three **core descriptive axes** of a place are *required*; the two
  *enhancing* dimensions are *optional* and carry lighter weight.
- The weight table is **frozen** (changing a weight changes every score and
  every pinned test) — treat it as part of the public contract.

## 3. Gap definition

> A **gap** is a **canon-mentioned entity** that is **missing one or more of
> its entity-kind's dimensions**.

For the demo: a LOCATION that appears in 封神演义 canon but lacks 历史 / 地理 /
文化 / features / inhabitants detail. A `Gap` partitions the full dimension set
into `present_dimensions` and `missing_dimensions`; **at least one missing
dimension is required** (a fully-described entity has no gap and is rejected by
validation).

### H0 boundary — describes ABSENCE only

A `Gap` is **pure data describing what is missing**. It deliberately carries:

- **no** generated content,
- **no** `source_type` / `origin` / `enriched` tagging,
- **no** `confidence`,
- **no** proposal id.

A gap is *"this place lacks X"*, never *"here is invented X"*. Emitting
proposals and applying `source_type='enriched'` (H0) belongs to C8–C11/C13, not
to this model. (Enforced by `test_gap_carries_no_enriched_content_or_source_type`.)

### Engine boundary (C7) — NOT here

`model.py` imports only the stdlib + pydantic. **No** graph reads, DB I/O, LLM
calls, embeddings, or model names appear in this cycle. Building the live ranked
list from a real KG is the C7 engine. (Enforced by
`test_model_module_has_no_io_or_llm_imports` and
`test_no_hardcoded_model_names_in_module`.)

## 4. Ranking model (deterministic)

Order gaps so the **biggest gaps are filled first**. The score combines three
signals, all order-independent and pure:

```
required_term   = REQUIRED_BONUS * (# missing REQUIRED dimensions)   # bonus = 1.0
weighted_missing = Σ weight(d)  for d in missing_dimensions          # frozen table
salience_factor = 1 + log1p(mention_count) / log1p(SALIENCE_REF)     # SALIENCE_REF = 55

raw   = (required_term + weighted_missing) * salience_factor
score = round(raw, 6)
```

- **`required_term`** rewards places missing their core descriptive axes.
- **`weighted_missing`** sums the frozen per-dimension weights of the missing
  dimensions — iterated in enum-declaration order, never set/dict order, so the
  (non-associative) float sum is stable.
- **`salience_factor`** is a **log-damped** canon-mention multiplier: a place
  with 55 mentions does not dwarf one with 7, but more-referenced places still
  rank higher all else equal. It is `≥ 1.0` (never down-weights below baseline)
  and monotonic.
- **`score`** is rounded to **6 decimals** so float equality is exact across
  calls and in tests — **never** compare raw floats with `==`.

**Determinism guarantees** (pinned by tests): no `random`, no wall-clock, no
set/dict-iteration dependence, fixed precision. `rank_gaps` sorts by
`(-score, canonical_name)` — a total order whose tie-break is a content-derived
key (never list position or object identity), so input order never affects the
result.

## 5. Pinned 封神演义 fixtures (golden output for C7)

The 4 locked under-described LOCATIONs, classified from canon. Most dimensions
read as **missing** — these are deliberately sparse places, which is the whole
point of the demo (a place where everything is "present" yields an empty,
hollow gap set).

| place | mentions | present | missing | missing-required | score | rank |
|---|---|---|---|---|---|---|
| **蓬萊** | 28 | — | 历史·地理·文化·features·inhabitants (all 5) | 3 | **29.384354** | 1 |
| **玉虛宮** | 55 | inhabitants | 历史·地理·文化·features | 3 | **28.0** | 2 |
| **碧遊宮／金鰲島** | 45 | inhabitants | 历史·地理·文化·features | 3 | **27.31585** | 3 |
| **陳塘關** | 32 | inhabitants·历史 | 地理·文化·features | 2 | **18.686216** | 4 |

**Why 蓬萊 ranks #1 despite the lowest mention count:** it is missing **all
five** dimensions (the two optional dims add `2.0` each), so its
`weighted_missing` (13.0) beats 玉虛宮's (11.0) by enough that even 玉虛宮's
higher salience cannot overtake it. A place missing *everything* is a larger gap
than one missing 4-of-5. This is the documented, intended behaviour — the
ordering and exact scores are pinned in
`test_pinned_ranking_order_and_scores`. The C7 engine must reproduce this output
from real KG data.

## 6. Out of scope (this cycle)

- The gap-detection **ENGINE** (graph-stats traversal, template matching,
  building the live ranked list) — **C7**.
- Any enrichment **strategy / generation** (template / retrieval / fabrication /
  recook) — **C8–C11**.
- Write-back to glossary SSOT / Neo4j / knowledge-service, `source_type` /
  `origin='enriched'` tagging & quarantine (H0) — **C11/C13**.
- Embeddings / retrieval — **C10**.
- Other entity-kinds (CHARACTER / ITEM / FACTION).
