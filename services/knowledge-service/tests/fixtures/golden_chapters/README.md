# Golden Chapters — K17.10 extraction-quality fixtures

Human-annotated chapter excerpts used by the opt-in quality harness
(`tests/quality/test_extraction_eval.py`) to score the LLM extraction
pipeline against fixed ground truth.

## Layout

```
golden_chapters/
  <fixture_id>/
    chapter.txt     # raw chapter text (plain UTF-8)
    expected.yaml   # annotated ground truth
```

`<fixture_id>` is a short stable slug (`alice_ch01`, `sherlock_scandal_ch01`, …).
Do not rename existing fixtures — the id is used in the report JSON.

## expected.yaml schema

```yaml
source:
  title: "Book title"
  author: "Author"
  chapter: 1
  license: "Public domain (Project Gutenberg #N)"  # or permission note

entities:
  - name: Canonical Name
    # Kind enum mirrors the entity_extraction.md prompt schema.
    # Sync these — fixture and prompt MUST agree on vocabulary
    # (C-EVAL-FIX-FORM 2026-04-25 fixed `location`→`place` /
    # `object`→`artifact` mismatches across the v1+v2 fixture set).
    kind: person | place | organization | artifact | concept | other
    aliases: ["alias 1", "alias 2"]    # case-insensitive; normalized on load

relations:
  - subject: Entity A
    # Predicate normalized + synonym-canonicalized at score time
    # (e.g. lives_at / lives_in / dwells_in → resides_at;
    #  marries / is_married_to → married_to).
    # Vocabulary mirrors `_CANONICAL_PREDICATES` in eval_harness.py
    # which mirrors relation_extraction.md prompt's 28-predicate
    # suggested-set across 6 categories (Kinship / Mentorship /
    # Authority / Spatial / Action / Social).
    predicate: snake_case_verb_phrase
    object: Entity B
    polarity: affirm | negate           # default "affirm"

events:
  - summary: "One-sentence description of what happens in this chapter"
    participants: [Entity A, Entity B]

traps:
  # Things a naive extractor will emit but are NOT ground truth.
  # Hits against traps count as BOTH a precision-hurting FP and a
  # trap-rate hit (separately tracked).
  - kind: entity
    name: something_over_eager
    reason: "Why this isn't a real entity in this chapter"
  - kind: event
    summary: "Something only referenced, not happening here"
    reason: "Why this isn't a real event"
```

## Match logic (eval_harness.py)

- **Entity name**: case-insensitive, honorific-stripped via
  `canonicalize_entity_name`; alias-union match supported.
- **Entity kind**: strict equality after lowercase. Fixture kind
  MUST match prompt enum vocabulary.
- **Relation triple**: canonical-name match on subject/object (with
  alias hop), predicate normalized + synonym-mapped, polarity strict.
- **Relation FP classification (C-EVAL-FIX-FORM Fix #4)**: a relation
  that doesn't match any expected can be reclassified as
  `fp_annotation_gap` (excluded from FP for *lenient* precision) iff
  both endpoints canonicalize to fixture entities AND predicate is
  in the canonical 28-vocab AND polarity=affirm AND not a trap.
  Strict precision keeps gaps as FP for hard-gate compatibility.
- **Event match**: token-overlap on summary (asymmetric Jaccard over
  expected tokens, threshold 0.50) PLUS symmetric Jaccard ≥ 0.6 on
  canonicalized participant set (C-EVAL-FIX-FORM Fix #2 — replaces
  prior strict set equality so 1-off minor-participant misses don't
  break otherwise-correct events).

## Diagnostic dump (C-EVAL-DUMP)

Set `KNOWLEDGE_EVAL_DUMP_PATH=/some/dir` when running the quality
eval to write per-chapter diagnostic files:

```
{dump_path}/
  {chapter_id}/
    actual.json        # full LLM output (entities/relations/events)
    expected.json      # fixture content (side-by-side reference)
    attribution.json   # per-item TP/FP/FN/fp_trap/fp_annotation_gap
                       # with idx + content + matched-via reasons
```

The dump lets each FP/FN be analyzed semantically without re-running
the eval. Use to categorize errors into buckets:
(a) real LLM miss · (b) form mismatch · (c) edge case · (d)
annotation gap. See `services/knowledge-service/eval/QUALITY_EVAL_BASELINES.md`
for cycle history showing how the dump informed prompt and fixture
fixes.

## Adding a new fixture

1. Pick a public-domain excerpt (Project Gutenberg, Wikisource, etc.) or
   content you have explicit permission to redistribute. Record the
   license in `source.license`.
2. Keep excerpts short — 3–5 paragraphs is ideal. Longer text costs more
   per eval run and the scorer is noisier on very long inputs.
3. Annotate conservatively. Only list entities/relations/events that are
   unambiguously present in the excerpt. When in doubt, add the item as a
   `trap` instead of ground truth.
4. Re-verify annotations before committing. v1 fixtures are marked
   "illustrative — re-verify before pinning as hard gate" in their headers.
5. After adding a fixture, run the eval harness unit tests
   (`pytest tests/unit/test_eval_harness.py -v`) to make sure the YAML
   round-trips cleanly.

## Running the quality evaluation

The eval runs against any provider registered in
`provider-registry-service`. Local LLM via LM Studio is the
recommended default for iteration (cost-aware — see
`feedback_local_llm_first_cloud_is_fallback.md`); cloud LLM
calibration is one-off only.

```bash
# local LLM via LM Studio (recommended for iteration)
export PROVIDER_REGISTRY_INTERNAL_URL=http://localhost:8208
export PROVIDER_CLIENT_TIMEOUT_S=900    # bump for big fixtures
export KNOWLEDGE_DB_URL=postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_knowledge
export GLOSSARY_DB_URL=postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_glossary
export INTERNAL_SERVICE_TOKEN=dev_internal_token
export JWT_SECRET=loreweave_local_dev_jwt_secret_change_me_32chars
export KNOWLEDGE_EVAL_MODEL=<user_model_id from provider_registry>
export KNOWLEDGE_EVAL_MODEL_SOURCE=user_model
export KNOWLEDGE_EVAL_USER_ID=<owner_user_id>

# optional: write diagnostic dump per chapter
export KNOWLEDGE_EVAL_DUMP_PATH=/path/to/dump_dir

# optional threshold overrides (defaults are cloud-LLM-tier hard gate)
export KNOWLEDGE_EVAL_MIN_PRECISION=0.80
export KNOWLEDGE_EVAL_MIN_RECALL=0.70
export KNOWLEDGE_EVAL_MAX_FP_TRAP=0.15

pytest tests/quality/ --run-quality -v -s
```

See `services/knowledge-service/eval/register_lm_studio_models.sql`
for registering an LM Studio user_model. Without `--run-quality` the
quality tests are skipped so CI stays cheap.

## Content-filter gotcha (session 45)

While building v1 fixtures we hit the Anthropic output content-filter
when generating excerpts for "A Scandal in Bohemia" ch02 and
"The Red-Headed League" ch01. The filter triggered on generated text
containing certain period-typical phrases. Workarounds:

- Paste the excerpt in manually from Project Gutenberg rather than
  asking the model to reproduce it.
- Prefer excerpts that do not contain slurs or graphic descriptions
  (a hazard for 19th-century adventure fiction).
- If a specific chapter keeps hitting the filter, swap to a different
  chapter of the same work or a different public-domain work.

## v1 fixture set (English, Latin script)

| Fixture                    | Source                              | Notes                     |
|----------------------------|-------------------------------------|---------------------------|
| `alice_ch01`               | Alice in Wonderland ch. 1 opening   | Classic rabbit-hole scene |
| `alice_ch02`               | Alice in Wonderland ch. 2 opening   | "Curiouser and curiouser" |
| `sherlock_scandal_ch01`    | "A Scandal in Bohemia" ch. 1 opening | Watson framing            |
| `pride_prejudice_ch01`     | Pride and Prejudice ch. 1            | Mr. & Mrs. Bennet discuss Bingley |
| `little_women_ch01`        | Little Women ch. 1 opening           | Four March sisters by the fire |

v1 English fixture set is complete (5/5).

## v2 fixture set (multilingual — C19 / D-K17.10-02 closer)

Added in C19 to test CJK canonicalization + Vietnamese diacritic preservation
+ honorific-strip behavior across non-English scripts.

| Fixture                    | Source                              | Notes                     |
|----------------------------|-------------------------------------|---------------------------|
| `journey_west_zh_ch01`     | 西遊記 第一回 (Wu Cheng'en, c. 1592) | Stone monkey emergence; tests CJK canonicalization + multi-alias deity titles (`玉皇大天尊` / `玉帝` / `玄穹高上帝`) |
| `journey_west_zh_ch14`     | 西遊記 第十四回 (Wu Cheng'en, c. 1592) | Sun Wukong meets Tang Sanzang; **stress test for alias union** — Wukong has 7 active aliases (`那猴` / `猴王` / `孫` / `孫悟空` / `行者` / `孫行者` / `齊天大聖`); Sanzang has 5 |
| `son_tinh_thuy_tinh_vi`    | Sơn Tinh Thủy Tinh (Vietnamese folk) | Tests Vietnamese diacritic-preserving canonicalization (`Sơn Tinh` ≠ `Son Tinh`); compact 4-character entity vocabulary |
| `tam_cam_vi`               | Tấm Cám (Vietnamese folk) | Vietnamese kinship terms (`dì ghẻ`, `mẹ Cám`) not in default `HONORIFICS` tuple — tests that NON-honorific terms canonicalize intact |

**License notes:**
- 西遊記 chapters: public domain worldwide (Wu Cheng'en died 1582, well past 70-year posthumous term).
- Vietnamese folk tales (Sơn Tinh Thủy Tinh, Tấm Cám): public domain — oral tradition, no individual author. The chapter.txt retellings are original paraphrases composed for test-fixture use (standard story beats present in every published version).

## Big-fixture stress test (C-BIG-FIXTURE)

Added 2026-04-25 to expose production-scale pipeline behavior. Previous
fixtures are 1.1-1.5KB; real-world novel chapters are 5-20KB+.

| Fixture                    | Source                              | Size | Notes                     |
|----------------------------|-------------------------------------|------|---------------------------|
| `sherlock_speckled_band`   | "The Adventure of the Speckled Band" (Conan Doyle 1892, PG #1661) | ~53KB / ~13K tokens | First fixture past LLM's ~8K-token "comfort zone" |

**What this fixture revealed**: pipeline survives 13K tokens without
crash or timeout (~7-8 min/chapter with gemma-4-26b-a4b). Failure mode
at scale is **entity over-extraction** (LLM correctly extracts named
entities the prompt asks for, including backstory mentions), NOT
context-degradation. **Chunking would not directly address this** —
real lever is prompt-instruction tightening to filter scene-actors
from backstory. See `eval/QUALITY_EVAL_BASELINES.md` "Big-fixture
diagnostic" section.

## Post-C19 quality polish cycles (2026-04-25/26)

Five cycles applied iteratively after the v1+v2 fixture set was
complete, all using diagnostic-dump-driven decisions:

| Cycle | What changed | Aggregate impact |
|---|---|---|
| **C-PRED-ALIGN** | Predicate vocab (10→28) + direction rules in `relation_extraction.md` + 6 fixture rewrites | P 0.251→0.311, R 0.356→0.429 |
| **C-EVAL-DUMP** | Added per-chapter attribution dump (opt-in env var) | 0% — instrumentation |
| **C-EVAL-FIX-FORM** | Entity kind alignment (17 fixture swaps) + event participants Jaccard tolerance + predicate synonym map + annotation_gap classification + lenient_precision | P 0.311→0.407, R 0.429→0.549 |
| **C-BIG-FIXTURE** | Added Speckled Band (53KB) | aggregate P −1.3pp, but exposed real failure mode |
| **C-PROMPT-SCENE** | Rule 8 scene-relevance filter in entity_extraction.md + 3 borderline Speckled Band entities → traps | P 0.394→0.435, R 0.552→0.573, FP-trap 0.274→0.175 |

Day-compounded: **P 0.251 → 0.435 (+73% rel) · R 0.356 → 0.573 (+61%)
· FP-trap 0.275 → 0.175 (−36%)** — all measured against the same
gemma-4-26b-a4b local-LLM baseline. Hard gate (P=0.80) is calibrated
for cloud LLMs and stays unchanged.
