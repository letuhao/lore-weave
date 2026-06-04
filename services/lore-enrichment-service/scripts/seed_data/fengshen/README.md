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

**Coverage:** chapters 卷001–卷020 — the founding arc (紂王/妲己/女媧, 蘇護, 姬昌/西伯侯,
雲中子, 哪吒/李靖/太乙真人/乾元山, 姜子牙下山/磻溪, 伯邑考). ~115k chars total.

**How fetched (LE-PROD-2 P1):** `scripts/_fetch_fengshen.ps1` pulls each chapter's
VERBATIM wikitext via a **direct raw HTTP GET** to zh.wikisource (`?action=raw`, with a
descriptive User-Agent — Wikimedia's bot policy requires one) and strips the wiki
markup. **No LLM in the path** (the earlier WebFetch route summarized/refused — a small
model mediated it; a plain HTTP fetch is verbatim + reliable). The platform itself does
NOT web-crawl (Mode E was dropped for copyright reasons); this is a one-off, license-safe
PD data-seeding step. ADDITIVE — re-run the fetcher for more chapters + re-seed to widen.
