# Convergence rubric

Score only the strongest 3–7 candidates, after clustering. Every score needs a one-line reason —
a number without a reason cannot be argued with, and so cannot be trusted.

## Criteria (1–5 each)

| Criterion | 1 | 3 | 5 | Weight |
|---|---|---|---|---|
| **User value** | nice to have for a few | clear gain for a real group | removes a pain users already work around | 3 |
| **Strategic fit** | off to the side of the product | fits, no special leverage | strengthens what makes LoreWeave distinct | 2 |
| **Effort** (inverted) | months, many services | weeks, a few services | days, one place | 2 |
| **Risk** (inverted) | data, security, migration or cost risk | manageable, known risks | low risk, easily reversible | 2 |
| **Evidence** | pure intuition | one source or one user story | several independent sources, or measured | 1 |
| **Novelty** | everyone does it | a better version of a known idea | nobody we found does it | 1 |

**Weighted score** = Σ(score × weight) / Σ(weights), rounded to one decimal (range 1.0–5.0).

Effort and Risk are *inverted*: a 5 means easy or safe.

## Table format

```markdown
| # | Candidate | Value | Fit | Effort | Risk | Evidence | Novelty | Score |
|---|---|---|---|---|---|---|---|---|
| A | Series bible project | 5 — authors keep hand-copying (3 forum threads) | 4 — uses the KG we already have | 3 — new project type + UI | 4 — additive, no migration | 4 — 3 sources | 3 — Campfire has a lite version | 4.1 |
```

## Invariant check

For each finalist, note any conflict with AGENTS.md's invariants — for example:

- agentic logic must be an MCP tool through `ai-gateway` (MCP-first);
- the service language rule;
- user-data scope and privacy rules;
- self-hostable, works on a local model.

A conflict does not disqualify an idea. It adds effort or risk, and it must be visible to the PO.

## Recommendation

- Name one winner (two at most), and say in one or two sentences why it beats the runner-up.
- Say why the others lost. That paragraph is what stops the same debate next quarter.
- A score is an aid, not a verdict. If you recommend against the top score, say why.

## Smallest test

The cheapest action that would tell us whether the winner is right, before anyone builds it:

- a paper or Figma mock-up shown to users;
- a manual "wizard of Oz" run of the feature;
- a spike limited to one day;
- a measurement on existing data;
- one question asked of five real users.

State what result would make us drop the idea. A test with no failure condition cannot fail, so it proves nothing.
