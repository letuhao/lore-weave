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

## v1 fixture set

| Fixture                    | Source                              | Notes                     |
|----------------------------|-------------------------------------|---------------------------|
| `alice_ch01`               | Alice in Wonderland ch. 1 opening   | Classic rabbit-hole scene |
| `alice_ch02`               | Alice in Wonderland ch. 2 opening   | "Curiouser and curiouser" |
| `sherlock_scandal_ch01`    | "A Scandal in Bohemia" ch. 1 opening | Watson framing            |

Two more English fixtures and the xianxia / Vietnamese pairs are
deferred to v2. See `docs/sessions/SESSION_PATCH.md` for status.
