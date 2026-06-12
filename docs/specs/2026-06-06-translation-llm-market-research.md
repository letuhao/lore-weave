# Translation LLM — Market & Prior-Art Research

> **Status:** Research note (feeds [translation-pipeline-v3 design](./2026-06-06-translation-pipeline-v3-multi-agent.md))
> **Date:** 2026-06-06 · **Branch:** `feat/translation-pipeline-v3`
> **Question (from PO):** What LLM translators exist on the market, how good are they, and what can we learn for our pipeline?

---

## TL;DR

- **General LLMs** (Claude, GPT-4/5, DeepL, Google) are *very strong at the sentence/passage level* but **degrade across a long book** — character names and terminology drift, earlier context falls out of the window. This is the #1 unsolved pain, and it is **exactly the gap our server-side persistent glossary + cross-chapter memo targets**.
- The **multi-agent / reflection** approach (TransAgents, Andrew Ng's translation-agent, DelTA) is the validated research direction — and it maps almost 1:1 onto our planned **Translator → Verifier → Corrector** loop.
- **Automatic metrics lie for literary text.** TransAgents scored low d-BLEU (25 vs GPT-4 Turbo 47.8) yet human readers *preferred* it up to 77.8% of the time. ⇒ build an **error-detection (MQM-style)** verifier, **not** a BLEU gate.
- A battle-tested OSS tool in our exact niche — **GalTransl** (CJK web-novel/galgame) — already ships a **problem-detection checklist** that nearly equals our Verifier rule-tier. We should copy it wholesale.

---

## A. Market landscape

### A.1 General-purpose engines

| Tool | Literary strength | Weakness for novels |
|------|-------------------|---------------------|
| **Claude** | Best feel for tone, emotion, metaphor, style — top pick for literary | — |
| **ChatGPT (GPT-4/5)** | Very strong on nuance/style per passage | Loses earlier context over 200+ pages; name/term consistency needs manual effort |
| **DeepL** | Smooth, polished, reader-friendly | "Polishes away" rough edges, slang, voice |
| **Google Translate** | Best breadth (top-20 languages) | Not literary |

Source: [O.Translator showdown](https://otranslator.com/en/blog/top-3-novel-translation-sites), [translateabook](https://translateabook.com/blog/best-ai-book-translation-services).

> **Key validated pain:** *"maintaining quality across 200+ pages while keeping character names and terminology consistent requires significant manual effort, as ChatGPT's conversation window has limits and gradually loses track of earlier context."* — this is precisely what V3's glossary + memo + verify-loop is built to fix.

### A.2 Specialized novel / web-novel tools (our niche)

- **[GalTransl](https://github.com/GalTransl/GalTransl)** — automated galgame/VN translator supporting GPT-4 / Claude / Deepseek / **Sakura**. Ships a **GPT-dictionary** (glossary with character notes) + an **automated problem-detection** stage. Closest prior art to V3 — see §C.5.
- **[SakuraLLM](https://github.com/SakuraLLM/SakuraLLM) / Sakura-GalTransl-7B** — open 7B/14B models *fine-tuned* on light-novel/galgame JP↔ZH, self-hostable offline. Proof that a **cheap local model can carry the bulk translate step** (relevant to our BYOK/local story), with a stronger model reserved for verification.
- **[LLM Novel Translator](https://github.com/qw02/llm-novel-translator)** — Chrome extension with an **auto-generating glossary** that maintains name/place/rank consistency across chapters.
- **[O.Translator](https://otranslator.com/en/blog/top-3-novel-translation-sites)** — lets the user pick the engine *per novel tone* (GPT-4o for hard sci-fi precision, Claude for literary). Validates **per-book / per-genre model selection** (we already have this via provider-registry + BYOK).

### A.3 Research systems (the frontier)

- **TransAgents** (arXiv:2405.11804, EMNLP'24) — a virtual translation *company*: CEO + personnel manager + Senior/Junior Editor + Translator + Localization Specialist + Proofreader (32 LLM instances). Two stages: **preparation** (build chapter summaries, glossary, plot summary, **style guidelines**) → **execution** (translate → junior-editor accuracy review → senior-editor revise → localize → proofread → finalize → senior-editor cross-chapter QA). [paper](https://arxiv.org/abs/2405.11804) · [repo](https://github.com/minghao-wu/transagents) · [The Batch](https://www.deeplearning.ai/the-batch/transagents-a-system-that-boosts-literary-translation-with-a-multi-agent-workflow/)
- **Andrew Ng — translation-agent** — minimal **reflection** loop: *translate → reflect (constructive suggestions) → improve*. Highly steerable via prompts (names, terms, style/register). [repo](https://github.com/andrewyng/translation-agent) · [Slator](https://slator.com/ai-pioneer-says-agentic-machine-translation-has-huge-potential/)
- **DelTA** (arXiv:2410.08143, ICLR'25) — online document-level agent with **multi-level memory**: *Proper-Noun Records · Bilingual Summary · Long-Term · Short-Term*, retrieved/updated by auxiliary LLMs. Reports it **reduces content omissions** and lifts consistency (+up to 4.58 consistency, +3.16 COMET). [paper](https://arxiv.org/abs/2410.08143)
- **Translate-and-Revise** (arXiv:2407.13164) — translate, then **revise to satisfy constraints** (terminology) — the constrained-translation analogue of our verify→correct.

### A.4 Quality evaluation / error detection

- **GEMBA-MQM** (arXiv:2310.13988, WMT'23) — **reference-free**, prompt-based LLM metric that emits **error spans in the MQM framework** (error *type* + *severity*), producing severity-weighted scores; ~96.5% system accuracy on WMT'23. This is the template for our **Verifier**. [paper](https://arxiv.org/abs/2310.13988)
- **xCOMET-XL/XXL** — strong open MT metrics, but ⚠️ **untrustworthy for literary text**.
- **LiTransProQA** (arXiv:2505.05423, EMNLP'25) & ["How Good Are LLMs for Literary Translation, Really?"](https://arxiv.org/html/2410.18697v2) — find that xCOMET/GEMBA-MQM/Prometheus **may prefer machine output over professional human translators**, misaligning with experts. A QA-style, translator-insight-weighted metric does better.

---

## B. How good is it, really? (honest read)

1. **Passage-level: excellent.** Claude/GPT produce fluent, nuanced literary prose. For a single chapter, a good prompt + glossary is already close to publishable draft quality.
2. **Book-level: the wall.** Without external scaffolding, every tool drifts on names/terms and loses context past the window. Consumer tools push this work onto the user (manual glossaries, re-prompting).
3. **Multi-agent genuinely helps literary quality.** TransAgents was **preferred by human readers over both GPT-4 Turbo and human translators** for fantasy-romance (77.8%) — *despite* a low d-BLEU of 25 (vs 47.8 / 47.3). The preparation stage (style guide + glossary) and the editor/proofreader passes are what buy that.
4. **Evaluation is a trap.** BLEU/COMET/xCOMET under- or mis-rate literary translation. ⇒ We must **not** gate on reference metrics. Measure **error counts** (omission, wrong name, …) and, where possible, **human/A-B preference**.
5. **Glossary injection alone is not enough.** "Tell the LLM to use these terms" yields only *probabilistic* compliance; across thousands of lines you get inconsistency ([Lokalise](https://lokalise.com/blog/ai-translation-glossary/)). ⇒ inject **and then verify + correct** — the core thesis of V3 over V2.

---

## C. What we can learn → concrete actions for V3

| # | External finding (source) | V3 design impact | Milestone |
|---|---------------------------|------------------|-----------|
| C.1 | **Reflection loop** is the canonical pattern (Ng; Translate-and-Revise) | Confirms Translator→Verifier→Corrector. Let the Verifier also emit *suggestions*, not only hard errors (reflection mode) | M2 |
| C.2 | **MQM error-span + severity, reference-free** (GEMBA-MQM) | Align `Issue.type` to MQM **Accuracy** (omission/addition/mistranslation/untranslated) + **Terminology** (wrong/inconsistent term) + **Locale/format**; score = severity-weighted error count (major/minor), **no BLEU** | M1/M2 |
| C.3 | **Automatic metrics mislead for literary** (TransAgents d-BLEU 25 but preferred; LiTransProQA) | `quality_score` is error-count-based, never reference-based. Add optional **A/B human preference** harness instead of a metric gate | M5 |
| C.4 | **Preparation stage**: style guide + glossary + plot summary built up front (TransAgents) | Extend `context.py`: a per-book/per-chapter **"preparation" artifact** (style guidelines + plot-so-far), richer than a 5-sentence slice | M4 |
| C.5 | **GalTransl problem-detection checklist** (battle-tested) | Adopt **all** as Verifier rule-tier: residual source-script · punctuation/symbol-count · **repetition > N (looping)** · length ratio · line/block count · **glossary-term-used compliance** · non-target-language chars | M1 |
| C.6 | **Glossary carries character notes** (GalTransl GPT-dict: gender/role → pronoun/honorific) | Enrich glossary projection with aliases + role/gender notes when available (interface to extraction pipeline) for better pronoun/name handling | M2/M4 |
| C.7 | **Conditional / whole-word replacement** (GalTransl conditional dict) | Our `auto_correct_glossary` does blind `str.replace` → over-replacement risk (substring collisions). Add word-boundary + conditional logic | M1 |
| C.8 | **Multi-level memory** (DelTA: Proper-Noun Records · Bilingual Summary · Long/Short-term) | Validates our 3 memo columns (`terms_used` · `story_summary` · `style_notes`) — populate them properly; maintain a running **proper-noun record** fed forward (and back to glossary) | M4 |
| C.9 | **Finer units reduce omission** (DelTA sentence-by-sentence) | When omission persists after a redo, Corrector re-translates the flagged block at **sentence granularity** | M2/M3 |
| C.10 | **Per-step model config + cheap local bulk** (GalTransl, Sakura, O.Translator) | Confirms per-role `verifier_model` config + BYOK. Document tiers: local 7B (e.g. Sakura-class) for bulk translate, stronger model for verify | M2 |
| C.11 | **Real-time cache + auto-resume** (GalTransl) | Make the block pipeline persist per-batch rows (TD3) so a crashed chapter **resumes mid-way** instead of restarting | M1 |
| C.12 | **Market gap = our moat** | Position V3 as the thing consumer tools lack: server-side **persistent** glossary + cross-chapter memo + **automated** verify/correct, multi-user/multi-device | — |

### Net effect on the design
The research **validates the V3 direction** and sharpens four things already in the plan: (1) make the Verifier an **MQM-style error detector** (C.2) with GalTransl's concrete checks (C.5); (2) fix glossary correction to be **word-boundary/conditional** (C.7); (3) treat the cross-chapter memo as **multi-level memory** (C.8); (4) add a lightweight **preparation pass** (style guide) per book (C.4). None of this changes the milestone structure — it refines M1/M2/M4.

---

## Sources

- TransAgents — [arXiv:2405.11804](https://arxiv.org/abs/2405.11804) · [repo](https://github.com/minghao-wu/transagents) · [DeepLearning.AI The Batch](https://www.deeplearning.ai/the-batch/transagents-a-system-that-boosts-literary-translation-with-a-multi-agent-workflow/)
- Andrew Ng translation-agent — [repo](https://github.com/andrewyng/translation-agent) · [Slator](https://slator.com/ai-pioneer-says-agentic-machine-translation-has-huge-potential/)
- GEMBA-MQM — [arXiv:2310.13988](https://arxiv.org/abs/2310.13988)
- DelTA — [arXiv:2410.08143](https://arxiv.org/abs/2410.08143)
- Translate-and-Revise — [arXiv:2407.13164](https://arxiv.org/pdf/2407.13164)
- LiTransProQA — [arXiv:2505.05423](https://arxiv.org/abs/2505.05423) · "How Good Are LLMs for Literary Translation" — [arXiv:2410.18697](https://arxiv.org/html/2410.18697v2)
- GalTransl — [repo](https://github.com/GalTransl/GalTransl) · SakuraLLM — [repo](https://github.com/SakuraLLM/SakuraLLM) · [LLM Novel Translator](https://github.com/qw02/llm-novel-translator)
- Glossary/terminology — [Lokalise](https://lokalise.com/blog/ai-translation-glossary/) · [Efficient Terminology Integration arXiv:2410.15690](https://arxiv.org/abs/2410.15690)
- Market overviews — [O.Translator](https://otranslator.com/en/blog/top-3-novel-translation-sites) · [translateabook](https://translateabook.com/blog/best-ai-book-translation-services)
