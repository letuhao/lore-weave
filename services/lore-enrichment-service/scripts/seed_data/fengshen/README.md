# 封神演義 public-domain grounding fixtures

Curated public-domain text from *封神演義* (Investiture of the Gods, Ming dynasty,
~16th c. — public domain) sourced from [zh.wikisource.org](https://zh.wikisource.org/wiki/封神演義),
committed so the demo book's retrieval grounding is **reproducible** (no network at
seed time). Each `卷NNN_*.txt` is one verbatim chapter.

`scripts/seed_pd_corpus.py` ingests every `.txt` here as ONE curated
`source_corpus` (kind=`fengshen`, license=`public_domain`, non-ephemeral — the
reaper never GCs it) for a book, via the same `ingest_corpus` embed seam the app
uses. By default it does a **clean rebuild** (drops the existing corpus first, so
the corpus reflects the fixtures EXACTLY — re-run after adding/editing files to
widen coverage). Pass `--no-replace` to append instead.

**Why this exists:** the demo book's chapters in book-service are ~55-char UI
stubs, so P1 retrieval had nothing to ground on ("检索片段未提及" / regurgitation).
This gives it real prose to retrieve.

**Coverage:** currently a single representative entity-rich chapter (卷012 — 陳塘關
哪吒出世: 哪吒 / 李靖 / 太乙真人 / 乾元山金光洞 / 玉虛宮 / 混天綾 / 乾坤圈 / 東海敖光).
ADDITIVE — drop more verbatim `卷NNN_*.txt` files here and re-run the seed to widen
coverage. (Wikisource fetch was done by hand because automated fetch could not be
trusted to return verbatim text for every chapter.)
