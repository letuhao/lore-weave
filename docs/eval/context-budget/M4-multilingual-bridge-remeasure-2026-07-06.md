# M4 — multilingual re-measure of the M1a passage→graph bridge + a fix it surfaced

**Date:** 2026-07-06 · **Branch:** `feat/context-budget-law` ·
**Follow-on to:** [`M4-graph-anchor-bridge-2026-07-06.md`](M4-graph-anchor-bridge-2026-07-06.md)
(the original, English/Dracula-only, that gated shipping M1a in `31eefb2dc`).

Gates plan [`docs/plans/2026-07-06-context-retrieval-improvements.md`](../../plans/2026-07-06-context-retrieval-improvements.md)
M4's carried-forward caveat: *"a larger multilingual corpus … remains the follow-on
robustness check."* This is that check.

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

2. **Name fragmentation (deferred — `D-BRIDGE-NAME-FRAGMENT`).** The 4-token Sino-Vietnamese name
   `Cửu U Ma Cơ` is split by `extract_candidates` at the mid-name single-char token `U` into
   `Cửu` / `Ma Cơ`, neither of which resolves via `find_entities_by_name`. So even a perfect
   anchor selector misses it. This lives in the **shared** extractor / `LATIN_NAME_RE` and needs a
   glossary-path regression pass — tracked, not fixed here.

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

## Finding 2 (answer quality) — safe & positive, but the corpus is too small to size the lift

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
