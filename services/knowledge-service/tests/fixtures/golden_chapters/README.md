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
    kind: person | location | object | concept
    aliases: ["alias 1", "alias 2"]    # case-insensitive; normalized on load

relations:
  - subject: Entity A
    predicate: verb_or_phrase            # normalized: [^\w]+ → _, lowercase
    object: Entity B

events:
  - summary: "One-sentence description of what happens in this chapter"
    participants: [Entity A, Entity B]

traps:
  # Things a naive extractor will emit but are NOT ground truth.
  # Hits against traps count as BOTH a precision-hurting FP and a trap-rate hit.
  - kind: entity
    name: something_over_eager
    reason: "Why this isn't a real entity in this chapter"
  - kind: event
    summary: "Something only referenced, not happening here"
    reason: "Why this isn't a real event"
```

Matching is case-insensitive and honorific-stripped via
`app.db.neo4j_repos.canonical.canonicalize_entity_name`
(same canonicalization the extractor uses, so matches align with writes).
Predicates are normalized via
`app.extraction.llm_relation_extractor._normalize_predicate`.
Event summary matching uses asymmetric Jaccard over tokens
(`|actual ∩ expected| / |expected|`), threshold 0.50.

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

```bash
export ANTHROPIC_API_KEY=...
export KNOWLEDGE_EVAL_MODEL=claude-haiku-4-5-20251001
export KNOWLEDGE_EVAL_MODEL_SOURCE=user-provided
export KNOWLEDGE_EVAL_USER_ID=<uuid>
export KNOWLEDGE_EVAL_PROJECT_ID=<uuid>

# optional threshold overrides
export KNOWLEDGE_EVAL_MIN_PRECISION=0.80
export KNOWLEDGE_EVAL_MIN_RECALL=0.70
export KNOWLEDGE_EVAL_MAX_FP_TRAP=0.15

pytest tests/quality/ --run-quality -v
```

Without `--run-quality` the quality tests are skipped so CI stays cheap.

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
