# Extraction cost analysis + tiering plan — "are we over-extracting?"

**Date:** 2026-07-06 · **Branch:** `feat/context-budget-law` · **Status:** analysis + plan (no code
change here — extraction pipeline untouched; this scopes future work).
**Origin:** user question during a live 万古神帝 20-chapter extraction — *"are we over-extracting?
it's slow and the cost seems too high; loading a whole chapter to use might cost less."*
**Builds on:** [`docs/reviews/2026-06-11-extraction-prompt-fanout-efficiency.md`](../reviews/2026-06-11-extraction-prompt-fanout-efficiency.md)
(`D-EXTRACTION-PROMPT-FANOUT` — identified the 4× fan-out, improvement deferred). This doc **replicates
that finding on a second book** and adds the **extract-vs-load economics** the prior note didn't cover.

---

## 1. The measured cost (2026-07-06, 万古神帝, gemma-4-26b local)

Per `provider_registry.llm_jobs` for the 20-chapter run — the pipeline runs **four independent
single-purpose LLM passes over the SAME chunked chapter text**, plus summarization:

| Operation | jobs (chapters) | chunks (= prompts) |
|---|---|---|
| entity_extraction | 13 | 88 |
| event_extraction | 13 | 88 |
| fact_extraction | 13 | 88 |
| relation_extraction | 13 | 88 |
| summarize_level | 10 | 10 |

- **~7 chunks/chapter × 4 passes ≈ 28 extraction LLM calls/chapter** (+ summary). Identical structure
  to the 2026-06-11 run (~58/chapter there — more chunks on a different chunker setting).
- **Per-call fixed overhead is large**: the four system prompts are entity **1582**, event **1657**,
  fact **1148**, relation **1549** tokens (measured). So each chunk call is
  ~1500 (system) + ~1000 (chunk text) + ~200 (known-entity injection) ≈ **~2700 input tok + ~300 out**.
- **Per chapter ≈ 28 × 3000 ≈ 84K tokens** of LLM work (+ a ~5K summary). The chapter's text is paid
  for **4×** in input tokens, and the 4 fixed system prompts (~5.9K tok) are re-sent on **every** chunk.
- **`tokens_used = 0`** on every local job — LM Studio doesn't report usage, so cost tracking is blind
  on local models (a real measurement gap; the numbers above are tokenizer estimates, not billed).

## 2. The economics the user raised — extract vs. just load the chapter

| | tokens | when paid |
|---|---|---|
| **Extract a chapter into the KG** | **~84K** | ONCE, upfront (eager, on publish) |
| **Load the raw chapter into context** | **~4.5K** (≈3000 words) | per query that needs it |

**Break-even ≈ 84K / 4.5K ≈ ~19 uses.** A chapter must be pulled into context **~19+ times over the
book's entire writing life** for its extraction to pay for itself against simply loading it.

**Implication for a real book:** eagerly extracting **all** chapters of a 4232-chapter novel is
~4232 × 84K ≈ **355M tokens** upfront. The protagonist's chapters clear the 19-use bar easily; but the
overwhelming majority (a minor scene in chapter 2837) will be referenced **far fewer than 19 times, if
ever** — for those, extraction is a **net loss** vs. lazy loading. **So yes: eager whole-book
extraction over-spends.** The user's intuition is correct for the long tail.

**But extraction is not redundant** — it buys things raw loading cannot:
- **Cross-chapter multi-hop** — "the feud between house X (ch 5) and kingdom Y (ch 3000)". You cannot
  fit both spans + everything between into context; the KG answers it in a few hundred tokens.
- **Hot entities** — the protagonist / main factions are queried thousands of times; extracted once,
  the compact graph amortizes immediately.
- **Books longer than the window** — a 4232-chapter book never fits; the KG is the only way to have
  whole-book memory at all.

**Conclusion:** the KG is right for *cross-book, long-lived, frequently-queried* memory and wrong as an
*eager, uniform, whole-book* tax. The current pipeline applies it uniformly → over-extraction.

## 3. Improvement plan (ranked by leverage-per-risk)

### P1 — Unified extraction prompt (4× → 1×; ~75% fewer calls)   *[from D-EXTRACTION-PROMPT-FANOUT]*
One prompt per chunk returning `{entities[], events[], relations[], facts[]}` instead of four passes.
The chunk text + system overhead is sent **once**, not four times: ~84K → **~21K tok/chapter**.
**Risk:** a combined prompt is longer/harder; a weak local model may lose per-type recall. Gate behind
the K17.9 benchmark + an eval-judge A/B; expose as a per-model `supports_unified_extraction` capability
so strong models get it and weak ones keep the split. **Biggest single win.**

### P2 — Fewer, larger chunks (7 → 2-3; ~2-3× fewer calls)
A 3000-word chapter chunked into ~7 slices over-chunks a model with an 8K-200K window. Larger chunks
cut every pass's prompt count and stop re-sending the 5.9K of system prompts so many times.
~21K → **~8-10K tok/chapter** stacked on P1. **Risk:** recall on long chunks — benchmark-gated.

### P3 — Lazy / selective extraction (extract 10-20% of chapters, not 100%)
Stop eagerly extracting the whole book on publish. Extract a chapter into the KG only when it **earns
it**: it's referenced by the author, its entities are promoted to canon, or it's in the "settled" back-
catalog the author explicitly bibles. This directly fixes the long-tail over-spend **and** the
"Knowledge extraction is never-gated, writes straight to Neo4j" defect the Narrative Forge audit flagged
as the worst gate-philosophy offender. **Risk:** a query about an unextracted chapter falls back to raw
passage retrieval (already exists) — acceptable degrade.

### P4 — Hybrid raw-in-context + KG tiering (the strategic reframe)
Two memory tiers instead of one:
- **Active window (raw text, 0 extraction):** the current + recent N chapters loaded raw into context
  for the live writing task. Cheapest, always fresh, no pipeline. This is what the user meant by "load
  the chapter to use."
- **Long-term bible (KG, selectively extracted):** cross-book, multi-hop, hot-entity memory — the only
  thing that *needs* extraction — built lazily via P3.
The per-turn Planner already decides grounding depth (Context Budget Law); this extends it to decide
**raw-load vs. KG-retrieve** by scope: active chapters → raw; distant/relational → KG.

### P5 — Supporting fixes (measurement + retries)
- **Estimate local tokens** at the provider-registry seam (tokenizer count) so local extraction cost is
  no longer invisible — you cannot manage what you cannot measure (the `tokens_used=0` gap).
- **Retry discipline / skip-empty** (from the 2026-06-11 review): job counts show retries inflate the
  call count; a barren/dialogue-only chunk shouldn't be retried or re-sent 4×.

**Stacked P1+P2+P3 ≈ 10-50× cost reduction** for a typical book (4× from unified, 2-3× from chunking,
5-10× from extracting only the chapters that earn it). P4 makes the *active* writing loop extraction-free.

## 4. Recommendation

- **Not a fire-drill** — the current pipeline is correct, just uniformly expensive; nothing is broken.
- **P1 (unified prompt) is the clear first build** — biggest win, self-contained, benchmark-gateable,
  already scoped in `D-EXTRACTION-PROMPT-FANOUT`. Promote that row from "deferred observation" to a real
  planned task.
- **P3 + P4 (lazy + tiering) are the strategic shift** the user is pointing at — they need a design
  spec (which chapters earn extraction? how does the Planner choose raw-vs-KG?) and tie into the
  Narrative Forge gate-reconciliation work. Sequence after P1 lands and its A/B proves the quality hold.
- **P5 first, cheaply** — without local token estimation every one of these wins is unmeasurable on the
  local stack; do it before/with P1 so the A/B has real numbers.

**Tracked as:** extend `D-EXTRACTION-PROMPT-FANOUT` (P1/P2/P5) + a new `D-EXTRACTION-EAGER-WHOLE-BOOK`
(P3/P4 — the lazy/tiering strategic track).
