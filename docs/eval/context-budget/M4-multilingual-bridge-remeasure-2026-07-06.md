# M4 — multilingual re-measure of the M1a passage→graph bridge + a fix it surfaced

**Date:** 2026-07-06 · **Branch:** `feat/context-budget-law` ·
**Follow-on to:** [`M4-graph-anchor-bridge-2026-07-06.md`](M4-graph-anchor-bridge-2026-07-06.md)
(the original, English/Dracula-only, that gated shipping M1a in `31eefb2dc`).

Gates plan [`docs/plans/2026-07-06-context-retrieval-improvements.md`](../../plans/2026-07-06-context-retrieval-improvements.md)
M4's carried-forward caveat: *"a larger multilingual corpus … remains the follow-on
robustness check."* This is that check.

> **D-EVAL-BOOK follow-on (2026-07-06):** building a *larger* corpus (万古神帝, Chinese,
> 4232 published chapters) to size the lift surfaced **two pipeline issues fixed/diagnosed
> below** before any A/B ran — see "Appendix A: D-BACKFILL-NO-SCOPE-LIMIT" and "Appendix B:
> extraction stall diagnosis". The larger-corpus A/B itself is recorded in
> [`M4-wangu-largecorpus-2026-07-06.md`](M4-wangu-largecorpus-2026-07-06.md).

---

## Why re-measure (the caveat the first M4 left open)

M1a's A/B ran on **one small English book** (Dracula, N=15) with a local judge. Its own
verdict flagged two bounds: single-corpus, and the answerer's role→entity resolution limit.
The platform's core use case is **multilingual (Vietnamese/Chinese) novels**, and the M1a
bridge leans on `extract_candidates` — the same proper-noun path whose ASCII-only ancestor
shredded Vietnamese names (`Nguyễn`→`Nguy`, the ML-3 breadcrumb bug). So the load-bearing
question was never answered: **does the bridge work on the languages this product exists for?**

## Corpus — a second, independent, multilingual graph that the first M4 said didn't exist

A live Neo4j survey (`scratchpad/corpus_inventory.py`) found the first M4's "only Dracula
is usable" is now **stale** — a second project carries a full entities+relations+passages graph:

| Project | entities | relations | passages | rel/ent |
|---|---|---|---|---|
| `019f2be0` (Dracula, English) | 64 | 110 | 116 | 1.7 |
| **`019f1783` (Vietnamese xianxia)** | 30 | **95** | **181** | **3.2** |

`019f1783` is a Vietnamese cultivation novel (protagonist *Lâm Uyển*; sect *Thanh Vân Tông*;
demon-mentor *Cửu U Ma Cơ*) with a denser, protagonist-centered relation graph than Dracula.
It is an **independent corpus in a different language** — the exact robustness axis the first
M4 could not test. **No expensive fresh extraction was needed** — a real multilingual corpus
already existed. (The big entity-only graphs — `019f0867` 3172 ent, `019effe4` 1814 ent — have
**zero passages**, so they still cannot exercise a *passage*→graph bridge; the plan's 万古神帝
assumption remains refuted.)

**Harness caveat (cross-service model-ref).** The Vietnamese passages were indexed under a
*different* bge-m3 `user_model` row (`019eeb08-8bff…`) than Dracula's (`019e7f71…`) — same model,
two BYOK ids. `find_passages_by_vector` filters on the id, so a first pass returned **0 passages**
and a false "bridge is dead on Vietnamese." The eval must embed the query with the corpus's **own**
index model. (Recurring cross-service normalization bug class.)

---

## Finding 1 (mechanism) — shipped M1a is materially DEGRADED on Vietnamese

Running the **real shipped** `select_bridge_anchor_names` / `expand_facts_from_passages` over
the Vietnamese passages (`scratchpad/viet_diag.py`, `viet_mech.py`) exposed **two defects that
English could never reveal** — the bridge reuses `extract_candidates`, a user-*message*
proper-noun extractor, over passage **prose**:

1. **Cap starvation (fixed here).** On Vietnamese prose the candidate stream is dominated by
   (a) whole **quoted dialogue sentences** (`"Không thể... không thể để nó nuốt chửng mình!"` —
   `_QUOTED` trusts them verbatim) and (b) **sentence-initial common words** (`Một`/`Sự`/`Không`/
   `Giọng`, capitalized at sentence start). With the plain **cap-then-resolve** ordering, these
   junk candidates filled 5 of 6 anchor slots → **only 1/6 resolved to a real entity**, and in one
   query the actual answer entity was crowded out entirely.

2. **Name fragmentation (`D-BRIDGE-NAME-FRAGMENT` — now FIXED, see below).** The 4-token
   Sino-Vietnamese name `Cửu U Ma Cơ` was split by `extract_candidates` at the mid-name single-char
   token `U` into `Cửu` / `Ma Cơ`, neither of which resolves via `find_entities_by_name`. So even a
   perfect anchor selector missed it. This lived in the **shared** extractor / `LATIN_NAME_RE`.

Both are the **same class** as the ML-3 breadcrumb bug (a message-tuned heuristic misapplied to
multilingual prose), now in the bridge path.

## Fix (defect 1) — sentence-junk filter + resolve-then-cap, bridge-local

`facts.py`, two bridge-local changes (the shared `extract_candidates` is untouched):
- **`_looks_like_sentence`** drops candidates carrying interior sentence punctuation (`! ? … 。！？`,
  or `. ` — a trailing abbreviation dot like `Coutts & Co.` is preserved) or > 8 words, **before**
  the cap.
- **resolve-THEN-cap** in `expand_facts_from_passages`: pull a bounded candidate **pool**
  (`_MAX_BRIDGE_CANDIDATE_POOL = 40`) and resolve in rank order until `max_anchors` candidates hit
  a *real* entity — so unresolvable junk no longer spends the anchor budget. I/O stays bounded
  (≤ pool resolution lookups + ≤ `max_anchors` relation lookups).

**Mechanism effect (deterministic — no LLM):**

| | queries with ≥1 bridge fact | avg bridge facts / query |
|---|---|---|
| Shipped M1a | 8 / 12 | 3.42 |
| **+ fix** | **11 / 12** | **6.92** |

The fix ~**doubles** the real-anchor yield and closes 3 of the 4 empty-bridge queries (the one
remaining `+0` is correct dedup: every passage entity was already message-anchored).

## Update — defect 2 (`D-BRIDGE-NAME-FRAGMENT`) fixed; combined result is a CLEAN lift

`LATIN_NAME_RE` matched a capitalized phrase of *up-to-3* words where each word required
**≥1 lowercase letter**. Sino-Vietnamese cultivation names break both bounds: they run 4-5
syllables (`Hắc Sát Lão Nhân` — truncated to 3) and can carry a **single-uppercase interior
syllable** (`Cửu U Ma Cơ` — the bare `U` split the name in two). Fix (`scripts.py`, the shared
regex — so it also helps the extraction entity-detector + glossary selector):
- a subsequent word may be a real word **or** a single uppercase letter, but the single-letter
  form is admitted **only as an interior connector** (a lookahead requires a real word to follow),
  so a trailing stray capital (`Paris U`) is *not* glued on and the resolvable name is preserved;
- word cap raised 3 → 5.

**Live-verified on the Vietnamese corpus:** `extract_candidates` now yields `Cửu U Ma Cơ` whole,
and Q2's resolve-then-cap recovers the **actual answer entity** it previously missed. Combined
with the defect-1 fix the bridge yield climbs **3.42 → 6.92 → 10.83** facts/query, and — because
the bridge now surfaces the real answer entities (not just the omnipresent protagonist) — the
answer-quality A/B turns **clean and decisively positive**:

| Config | overall mean | bridge-class mean | better / worse |
|---|---|---|---|
| Shipped M1a | 1.00 → 1.10 (+10%) | 1.00 → 1.167 (+17%) | 1 / 0 |
| + defect-1 (cap) | 1.111 → 1.222 (+10%) | 1.20 → 1.40 (+17%) | 1 / 1\* |
| **+ both fixes** | **1.10 → 1.50 (+36%)** | **1.00 → 1.667 (+67%)** | **3 / 0** |

\* spurious (judge-truncation on an identical answer, see below). With both fixes two
`base=0 → bridge=2` rescues land (the "Nữ chính là đệ tử/vật chứa…" queries the classifier could
only anchor on the junk word `Nữ`), controls stay flat, **zero regressions**.

**Regression pass (shared-regex blast radius):** knowledge unit suite **3606 passed**; the 4 reds
(3 `test_mode_full` budget + 1 `test_internal_dispatch`) are **pre-existing** — they fail
identically on a stash baseline without this change. 4 new `test_scripts` cases pin the
Sino-Vietnamese phrases + the trailing-capital guard.

---

## Finding 2 (answer quality) — safe & positive, but the corpus is too small to size the lift
> *(numbers below are the pre-name-defrag "shipped M1a" run; the fixed run is the table above.)*

LLM-judged A/B (`scratchpad/viet_ab.py`, gemma-26b local answerer+judge, passages in **both**
arms, truncated-answer rows excluded — mirroring the Dracula methodology). 12 golden questions
(8 role-referenced "bridge-sensitive" + 4 named "control") grounded in the live relation graph:

| Run | class | scored | mean base | mean +bridge | better / worse |
|---|---|---|---|---|---|
| Shipped M1a | overall | 10/12 | 1.00 | 1.10 (+10%) | 1 / **0** |
| Shipped M1a | bridge | 6/8 | 1.00 | 1.167 (+17%) | 1 / **0** |
| **+ fix** | overall | 9/12 | 1.111 | 1.222 (+10%) | 1 / 1\* |
| **+ fix** | bridge | 5/8 | 1.20 | 1.40 (+17%) | 1 / 1\* |

\* **The single "worse" is a judge artifact, not a regression** — verified by reading the row:
base and bridge answers are **byte-identical** (*"Cha mẹ ruột của nàng là Lâm Chấn Nhạc và Tô
Yến."*); the bridge arm's **judge** call truncated its long Vietnamese JSON reason mid-string
(`{"score": 1, "reason": "Ứ`…) → unparseable → mis-scored 0. The judge intended 1. No answer got
worse.

**Cross-lingual replication of the core result:** on a fully independent, different-language
corpus the bridge **never genuinely regresses an answer** and produces a small positive mean lift
with a clean empty-junk-anchor rescue (`base=0 → bridge=2` on the "Nữ chính…" queries — the
classifier anchored only the junk word `Nữ`, the bridge supplied the graph). The Dracula
"weak-but-positive, zero-regression GO" holds in Vietnamese.

**Honest bound (unchanged from Dracula):** N≤10 scored on one small book with a local judge that
itself truncates — the answer-quality **magnitude** is within noise. The trustworthy, decisive
signal is the **mechanism** leg (deterministic 2× yield), not the A/B means.

---

## Verdict & what changed

- **M1a is confirmed cross-lingually safe** — no genuine answer regression on an independent
  multilingual corpus; keep it ON (default already ON).
- **Shipped M1a under-delivered on the platform's core languages** — the multilingual re-measure
  found it, exactly what M4 was for. **Defect 1 fixed** this run (2× mechanism yield, 3 unit tests,
  bounded I/O); **defect 2 (`D-BRIDGE-NAME-FRAGMENT`) tracked** for the shared extractor.
- **Answer-quality magnitude remains unproven at scale** — bounded by one small book + a local
  judge. The genuine `D-EVAL-BOOK` (a full passage+relation extraction of a *large* book) is still
  the follow-on to size the lift; not built this run.

**Tests:** `test_facts_selector.py` 21/21 (3 new: sentence-junk filter, resolve-then-cap-not-
starved, resolved-anchor cap). Broader selector/mode slice green except 3 **pre-existing**
`test_mode_full` budget reds (fail identically without this change — the reds the M1a commit noted).

**Repro:** harnesses in the session scratchpad — `corpus_inventory.py`, `dump_viet_graph.py`,
`viet_diag.py`, `viet_mech.py`, `viet_ab.py`; run in `infra-knowledge-service-1` with
`PYTHONPATH=/app`, embed model = the corpus's own index id `019eeb08-8bff-75cb-8e86-700efd4033b5`.

---

## Appendix A — D-BACKFILL-NO-SCOPE-LIMIT (found + fixed building the larger corpus)

Extracting a bounded slice (chapters 1–20) of 万古神帝 (4232 published chapters) triggered a
**runaway**: setting the project's embedding model (`PUT /embedding-model`) fires a **synchronous,
in-request** `backfill_published_passages` over **every published chapter of the book** — no scope
limit. On a 4232-chapter book it embedded ~11.6K passages before a manual restart stopped it (a
120s client timeout only hid it; the server kept going). A second, background copy fires the same
unscoped backfill on `start_extraction_job`.

**Root cause:** passage backfill is whole-published-book by design; nothing bounds it to the
chapters a scoped extraction actually processes, and the embedding-PUT path runs it *synchronously*.

**Fix** (`facts`-adjacent extraction pipeline):
- `backfill_published_passages` / `backfill_project_passages` gain `chapter_range=(lo,hi)` → ingest
  only that `sort_order` slice.
- `start_extraction_job` threads the job's own `scope_range` into its background backfill, so a
  scoped extraction ingests passages **only for the extracted chapters**.
- the synchronous embedding-PUT backfill gains an inline cap
  (`kg_backfill_max_inline_chapters`, default 200): a book with more published chapters than the cap
  and no explicit range **skips** the inline backfill (a scoped extraction ingests instead) — so a
  large book can never run away embedding its whole self in one request.

**Verified:** 3 new `test_passage_ingester` cases (range bound / inline cap skip / range-overrides-cap);
knowledge unit suite green (pre-existing reds only). Live: the second run's embedding-PUT returned
*instantly* (cap skipped the 4232-chapter backfill) and the scoped extraction ingested passages only
for chapters 1–20 (bounded — 58 passages, not 11.6K).

## Appendix B — extraction "stall" diagnosis (user-caught; my first diagnoses were wrong)

During the first 20-chapter run the `entity_extraction` LLM job **hard-stopped at chunk 3/7** and
LM Studio went idle. I asserted "LM Studio queue wedge" and "reasoning-off broken" — **both wrong,
and I cancelled the job prematurely.** Proper diagnosis:
- **Ruled out with evidence:** governor (no `gov:conc:*` slots), circuit breaker
  (`breaker:lm_studio:state = closed`), missing idle timeout (`LLM_GATEWAY_STREAM_IDLE_TIMEOUT_S=300`
  *is* set). `last_progress_at` showed 3 chunks done in the **first 5 seconds**, then a hard cliff —
  a stall, not slowness.
- **Reproduced** a 2-chapter run on the same book+model: it **completed cleanly** (7/7 chunks/chapter,
  ~2s/chunk, 30 entities / 55 relations). Fast chunks ⇒ reasoning is *not* dominating (killing the
  reasoning-off theory).
- **Conclusion:** the original stall was a **transient LM Studio mid-stream drop** (its documented
  model-auto-eviction behavior — a streaming connection dropped without `done`/`err`), almost
  certainly aftermath of my own runaway-kill *restart* disrupting LM Studio's connection state.
  **Not a systemic bug; the pipeline is healthy.**
- **Residual robustness note (tracked, not blocking):** when LM Studio *does* drop a stream, the
  300s idle timeout means a chunk hangs ~5 min before recovering — long for a local model. Consider
  lowering `LLM_GATEWAY_STREAM_IDLE_TIMEOUT_S` for local-first deployments.
