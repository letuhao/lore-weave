# glossary_corpus_20k.tsv.gz — attribution

Derived from Wikipedia database dumps (`dumps.wikimedia.org`):

- `viwiki-latest-all-titles-in-ns0.gz` — Vietnamese article titles
- `zhwiki-latest-all-titles-in-ns0.gz` — Chinese article titles
- `viwiki-latest-page.sql.gz` + `viwiki-latest-redirect.sql.gz` — redirects, used as real human-authored aliases

Wikipedia text and titles are licensed **CC BY-SA 4.0**. This file is a filtered, deterministic sample of article *titles* only — no article prose is included.

## Why this corpus

It is test data for a **string matcher**, not for extraction quality, so it carries no gold labels. What it must supply is real morphology: nesting (`Lâm` ⊂ `Lâm Uyên`), Vietnamese diacritics and their unaccented alias forms, and CJK names with no whitespace — the case where an ASCII word boundary is meaningless.

Regenerate with `scripts/build-glossary-test-corpus.py --cache-dir <dumps>`. The committed file is the fixture of record; regenerating against a newer dump legitimately produces different titles.
