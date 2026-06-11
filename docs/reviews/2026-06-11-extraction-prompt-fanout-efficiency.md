# Extraction prompt fan-out — efficiency observation & improvement plan

**Date:** 2026-06-11
**Origin:** live 万古神帝 5-chapter campaign run (campaign `019eb684`, project `019eb683`, model qwen2.5-7b-instruct via LM Studio).
**Status:** observation only — improvement deferred (no code change in this note). Tracked as `D-EXTRACTION-PROMPT-FANOUT`.

---

## Observation (real numbers from the live run)

User flagged during the run: *"2 chương hết 150 prompts, mỗi prompt tầm 1k token."* Confirmed against `provider_registry.llm_jobs` for the run window (after 11:50 UTC), at the point ~3 chapters had been processed:

| operation | jobs | chunks (= prompts) |
|---|---|---|
| event_extraction | 11 | 47 |
| relation_extraction | 8 | 47 |
| fact_extraction | 8 | 40 |
| entity_extraction | 6 | 40 |
| **total** | **33** | **174** |

- **~58 LLM prompt calls per chapter** (174 chunks / 3 chapters), consistent with the user's eyeballed ~75/chapter.
- Each chunk prompt ≈ 1k input tokens (chapter text slice + extraction instruction).
- `tokens_used = 0` in `llm_jobs` for every row — **local LM Studio does not report usage back**, so the provider-registry usage/billing path records nothing for local models. (Separate gap — see "Secondary findings".)
- Job count > chapter×op count (e.g. 11 event jobs for ~3 chapters) → **retries are inflating the call count** on top of the structural fan-out.

## Root cause — structural 4× fan-out

The extraction pipeline runs **four independent single-purpose passes** over the **same chunked chapter text**:

```
chapter → semantic chunking → N chunks
  ├─ entity_extraction   : N prompts
  ├─ event_extraction    : N prompts
  ├─ relation_extraction : N prompts
  └─ fact_extraction     : N prompts
                          = 4 × N prompts / chapter   (before retries)
```

Each chunk is re-sent to the LLM 4 times (once per extraction type), each with a full instruction prompt. For a chapter that chunks into ~15 slices that is ~60 prompts; retries push it higher. The chapter text is paid for 4× in input tokens.

## Improvement directions (future)

Ranked by expected leverage:

1. **Unified extraction prompt (biggest win, ~4× fewer prompts).** One prompt per chunk that returns a single structured object `{entities[], events[], relations[], facts[]}` instead of four separate passes. The chunk text is sent once, not four times. Risk: a combined prompt is longer/more complex and a weaker local model may degrade per-type recall — gate behind the existing K17.9 benchmark and an eval-judge comparison before defaulting it on. Could be a per-model capability flag ("supports_unified_extraction").
2. **Fewer, larger chunks.** Tune the semantic chunker so a chapter produces fewer chunks (larger context window utilisation on models that support it). Halving chunk count halves every operation's prompts. Risk: extraction recall on very long chunks; needs the benchmark to confirm.
3. **Retry discipline.** The job count shows retries are a real multiplier. Tighten transient-retry classification + add a per-chunk "empty result is valid, don't retry" path so a legitimately entity-free chunk isn't retried. Ties into `JOB_MAX_RETRIES`.
4. **Skip-empty / cheap pre-filter.** A cheap heuristic (or a tiny first pass) to skip chunks that are pure dialogue/filler with no extractable entities, avoiding 4 prompts on a barren chunk.
5. **Batch API path (cost, not latency).** For non-interactive campaign extraction, route to a provider Batch API where available (OpenAI/Anthropic batch = ~50% cost). Local models don't have this, but cloud campaigns would benefit. Ties into the event-driven re-arch (`docs/specs/2026-06-11-llm-execution-event-driven-rearchitecture.md`) — batch is inherently fire-and-forget.

## Secondary findings (separate from fan-out)

- **Local usage = 0 tokens.** LM Studio (and likely Ollama) don't return usage, so `tokens_used`/cost is unrecorded for local extraction. Cost/budget tracking is blind on local models. Either (a) estimate tokens locally (tokenizer count) at the provider-registry seam, or (b) accept local = untracked and document it. Worth a dedicated row if budget enforcement on local matters.
- **Long-tail chapter latency.** One chapter took ~6 min vs ~2 min for others — consistent with LM Studio model thrashing (swapping bge-m3 embedding ↔ qwen2.5-7b chat between extraction and embedding steps). A single-GPU local backend serialised by the governor amplifies this. Mitigation: pin/keep-alive both models, or order operations to batch all embeddings together.

## Live-run outcome (2026-06-11, campaign `019eb684`)

The 5-chapter run **completed end-to-end** (import → extract → knowledge → translate VI → eval), but with a split verdict:

**Infra/orchestration — PASS:**
- The saga flowed all 5 chapters through knowledge → translation → eval to `completed`.
- The `governor: acquire timeout` cascade (which killed the first attempt at chapter 3/5) was fixed by raising `GOVERNOR_ACQUIRE_TIMEOUT_MS` 30s → 600s so the 4 concurrent extraction ops serialise behind the single local GPU instead of dying. Second attempt reached 5/5 with no cascade. This validates the event-driven re-arch thesis: the acquire-or-die default is the brittleness; a generous wait (≈ a bounded queue) is the interim mitigation, Phase 1 is the real fix.
- The translation **verifier/QA works**: it flagged **632 `omission`/`untranslated` issues** and scored `quality_score=0` on every chapter — the quality gate correctly caught bad output.

**Content quality — FAIL, but the root cause is the PROMPT FORMAT, not raw model inability (revised 2026-06-11 after a direct test):**
- The campaign's translation output was ~mostly the untranslated Chinese source (the structured `translated_body_json` had `content[].text` ≈ the `_text` source, only occasional token swaps), and the verifier correctly flagged **632 `untranslated`/`omission` issues** + `quality_score=0`.
- **BUT a direct LM Studio test refutes "7B is too weak to translate":** given a simple prompt — *"Translate this Chinese web-novel text to natural Vietnamese, output ONLY the translation"* — on the exact same xianxia sentence, **both** models produce real Vietnamese: qwen2.5-7b → *"Nguyễn Nhạc Chú hiện tại đang ở trong một quốc gia có tên là…"*; qwen2.5-32b → *"Quốc gia mà Zhang Ruochen đang ở hiện tại tên là…"* (32B better — keeps the name as pinyin). So 7B **can** translate zh→vi.
- **Therefore the dominant cause is the V3 translation pipeline's structured-JSON prompt** — it sends paragraphs as `{_text: <source>, content:[…]}` and asks the model to fill `content`; a weaker model's instruction-following degrades and it **echoes the source into `content`** instead of translating. A stronger model (32B/cloud) follows the structured instruction better, but the prompt format itself is the lever. → **`D-V3-TRANSLATION-PROMPT-ECHO`** (review the V3 translator prompt: does the structured/source-preserving format induce source-echoing on weaker models? consider a translate-then-restructure split, or a stricter "DO NOT copy source" instruction + an echo check in the verifier).
- **Knowledge extraction:** `extraction_leaves` = 0, `stat_entity_count/fact/event` = 0 — 174 chunks ($0.032) persisted **zero** entities. Same hypothesis class (the multi-field structured extraction prompt vs a weak model's JSON discipline) — verify against the extraction prompt too, not assumed model-weakness.
- `eval_status=done` does NOT mean "passed" — the campaign completes regardless of `quality_score`; a `quality_score=0` batch still reaches `completed`. Consider a quality-gate that surfaces/blocks a 0-score batch (`D-CAMPAIGN-QUALITY-GATE`).

**Recommendation (revised):** for a clean content demo, run with **qwen2.5-32b-instruct (`019e7874`)** or a cloud model (gpt-4o / claude) — better structured-prompt adherence — AND open `D-V3-TRANSLATION-PROMPT-ECHO` to fix the prompt so even mid models don't echo the source. Orchestration + governor + queue are proven; the remaining content gap is prompt-format × model-adherence, not the architecture. The full-pipeline re-run with a capable model is the definitive validation (deferred — long live run).

**Local usage = 0 (re-confirmed):** extraction `tokens_used=0` for every llm_job (LM Studio doesn't report usage), yet the **translation** path *did* record input/output tokens (9285/3659 etc. on `chapter_translations`) — so token capture is inconsistent across the two paths, not uniformly absent on local. Worth reconciling.

## Cross-links

- Execution-seam re-arch: [`docs/specs/2026-06-11-llm-execution-event-driven-rearchitecture.md`](../specs/2026-06-11-llm-execution-event-driven-rearchitecture.md) — Phase 0 (cancel) shipped; batch path is Phase 2.
- Audit: [`docs/reviews/2026-06-11-llm-execution-architecture-audit.md`](2026-06-11-llm-execution-architecture-audit.md).
- The fan-out is orthogonal to the seam re-arch: even a perfect event-driven queue still sends 4×N prompts. This note is about **reducing the work**, the re-arch is about **how the work is dispatched/awaited**.
