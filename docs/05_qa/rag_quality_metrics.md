# RAG Quality Metrics Reference

A comprehensive reference for evaluating Retrieval-Augmented Generation (RAG) pipelines, organized by evaluation layer.

---

## Retrieval Metrics

Measure whether the right documents were retrieved.

### Hit Rate @ K (HR@K)

```
HR@K = (queries with ≥1 relevant doc in top-K) / total queries
```

Binary metric — did **any** relevant document appear in the top-K results? The most lenient retrieval metric.

**Example:** K=5, 80/100 queries returned at least one relevant doc → `HR@5 = 0.80`

---

### Mean Reciprocal Rank @ K (MRR@K)

```
MRR@K = (1/|Q|) · Σ (1 / rank of first relevant doc)
```

Cares about *where* the first relevant doc ranks. If it's rank 1 → 1.0, rank 2 → 0.5, rank 3 → 0.33…

**Example:**
- Q1: first hit at rank 1 → `1.0`
- Q2: first hit at rank 3 → `0.33`
- MRR = `(1.0 + 0.33) / 2 = 0.67`

---

### Precision @ K (P@K)

```
P@K = (# relevant docs in top-K) / K
```

How many of the K retrieved docs are actually relevant? Penalizes noise in results.

**Example:** K=5, 3 relevant found → `P@5 = 0.60`

---

### Recall @ K (R@K)

```
R@K = (# relevant docs in top-K) / total relevant docs
```

How many of **all** relevant docs were captured in the top-K results? Penalizes missing coverage.

**Example:** 5 total relevant docs exist, K=10 retrieved 4 → `R@10 = 0.80`

> Precision and Recall are in tension — tuning retrieval chunk count involves a tradeoff between the two.

---

### Mean Average Precision @ K (MAP@K)

```
AP@K  = (1/R) · Σ P@k · rel(k)
MAP@K = mean of AP@K across all queries
```

Average Precision rewards finding relevant docs **early** AND finding many of them. MAP is the mean across all queries.

- `R` = total number of relevant docs
- `rel(k)` = 1 if the document at rank k is relevant, 0 otherwise

---

### Normalized Discounted Cumulative Gain @ K (NDCG@K)

```
DCG@K  = Σ rel(k) / log₂(k+1)   for k = 1..K
NDCG@K = DCG@K / IDCG@K
```

Supports graded relevance scores (0, 1, 2…). Normalizes against the ideal ranking (IDCG). The most informative retrieval metric when relevance is not binary.

- `IDCG` = DCG of the perfect ranking

---

### Context Precision *(Ragas)*

```
CtxPrec = relevant chunks in context / total chunks in context
```

RAG-specific: of the chunks fed to the LLM, what fraction were actually needed to answer the question?

---

### Context Recall *(Ragas)*

```
CtxRecall = ground-truth claims covered by context / total ground-truth claims
```

Did the retrieved context contain enough information to construct the ground-truth answer?

---

## Generation Metrics

Measure whether the generated answer was good.

### Faithfulness

```
Faithfulness = faithful claims in answer / total claims in answer
```

Are all claims in the generated answer actually supported by the retrieved context? Primary metric for catching hallucinations. Graded by an LLM judge or NLI model.

---

### Answer Relevance

```
AnswerRel = avg cosine_sim(questions regenerated from answer, original question)
```

Does the answer actually address the question? Technique: generate N questions from the answer, then measure embedding similarity back to the original question.

---

### Answer Correctness

```
AnswerCorr = F1(answer ∩ ground_truth)
             (optionally + weighted semantic similarity)
```

Factual overlap between the generated answer and a reference answer. Requires ground-truth labels.

---

### ROUGE (1 / 2 / L)

```
ROUGE-N = n-gram F1(answer, reference)
        = 2·P·R / (P + R)
```

Token overlap with a reference string. ROUGE-1 = unigrams, ROUGE-2 = bigrams, ROUGE-L = longest common subsequence. Fast and cheap, but misses paraphrases.

---

### BLEU

```
BLEU = BP · exp( Σ wₙ · log Pₙ )
Pₙ   = clipped n-gram precision
BP   = brevity penalty
```

Precision-focused n-gram metric. Originally designed for machine translation. Weak for open-ended QA — prefer semantic metrics when possible.

---

### BERTScore

```
BERTScore = F1 of token-level cosine similarities
            between contextual embeddings (BERT / RoBERTa)
```

Semantic token matching via pretrained embeddings. Captures paraphrases that ROUGE and BLEU miss.

---

## End-to-End & Composite Metrics

### Ragas Score

```
Ragas = harmonic_mean(
  Faithfulness,
  Answer Relevance,
  Context Precision,
  Context Recall
)
```

Aggregate score from the [Ragas](https://github.com/explodinggradients/ragas) framework. Harmonic mean penalizes any weak sub-score heavily, making it good for CI/CD regression checks.

---

### LLM-as-Judge

```
Score = LLM( question, context, answer, [reference] )
      → 1–5 Likert scale or binary pass/fail
```

Use a strong LLM (GPT-4, Claude) to rate answers on custom criteria: correctness, completeness, tone, safety. Flexible but requires prompt calibration. Correlates well with human evaluation when done carefully.

---

### Groundedness

```
Groundedness = # answer sentences attributable to a specific chunk
               / total answer sentences
```

Variant of Faithfulness focused on attribution: can each sentence of the answer be pointed to a source chunk? Particularly useful for citation UIs.

---

### Latency @ Percentile

```
Track: P50 / P95 / P99 of end-to-end request time
       (retrieval + rerank + generation)
```

Operational quality metric. Tail latency (P99) matters most for user-facing systems.

---

## Quick Decision Guide

| Goal | Primary metrics |
|---|---|
| Validate retrieval coverage | `HR@K`, `R@K` |
| Validate retrieval ranking quality | `MRR@K`, `NDCG@K` |
| Balance precision vs. coverage | `MAP@K`, `P@K` vs `R@K` |
| Detect hallucinations | `Faithfulness`, `Groundedness` |
| Check answer quality | `Answer Relevance`, `BERTScore` |
| Full pipeline regression in CI/CD | `Ragas Score` |
| Nuanced / custom eval criteria | `LLM-as-Judge` |
| Production health | `Latency P95/P99` |

---

## Practical Starting Point

For most RAG systems, start with this minimal eval suite:

1. **HR@5** — does retrieval find anything relevant?
2. **MRR@5** — does the best doc rank near the top?
3. **Faithfulness** — is the answer grounded in context?
4. **Answer Relevance** — does the answer address the question?
5. **Ragas Score** — single composite for quick regression checks

Add **NDCG@K** once you have graded relevance labels from human annotators, and **LLM-as-Judge** when you need to evaluate nuanced quality criteria that token-overlap metrics cannot capture.
