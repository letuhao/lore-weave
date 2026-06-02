# Copyright-safety: create from the IDEA, not an infringing derivative

> **Status:** DESIGN (2026-06-03). Branch `lore-enrichment/foundation`.
> **Not legal advice** — engineering design; a real release needs IP counsel sign-off.
> **Motivation:** protect the platform's reputation before release. Re-cook ingests
> real reference material; we must guarantee the OUTPUT uses the uncopyrightable
> idea/fact layer and generates FRESH expression — never reproducing protected
> source expression (a derivative-work / reproduction-right liability).

## Legal model (the foundation)

Copyright protects EXPRESSION, not:
- **Facts** (historical events, who/what/when) — uncopyrightable (Feist v. Rural;
  no "sweat of the brow").
- **Ideas / concepts / systems / methods** — 17 USC §102(b).
- **Public-domain works** (封神演义 = Ming dynasty; Shang–Zhou history).

It DOES protect: specific phrasing/prose, original detailed characters, distinctive
worldbuilding — and a modern **translation** of a public-domain work has its OWN
copyright (the translator's expression).

Re-cook is NOT parody (it doesn't comment on the source), so it cannot rely on the
parody/fair-use defense. Its defensible path is the **idea/fact doctrine**: use the
free fact/idea layer + generate fresh expression + prove no copying.

## Residual risks even with input license default-deny (why we need more)

Input default-deny (only `public_domain`/`licensed` corpora) is necessary but not
sufficient:
1. **Mislabeled license** — a user tags a copyrighted source `public-domain`. The
   store trusts the label; the output could copy protected expression.
2. **Licensed-but-no-verbatim** — a license may permit facts/inspiration but not
   verbatim reproduction.
3. **Copyrighted translation of a PD work** — the prose is the translator's.
4. **Good-faith posture** — actively preventing verbatim copying is itself strong
   evidence of non-infringing intent.

## Defense-in-depth — three layers

| Layer | Purpose | Status |
|---|---|---|
| ① Input license default-deny | never *ingest* a non-PD/licensed source | ✅ exists (recook `_admit_sources`, FIX-2 skips per-source) |
| ② **Abstraction** — facts→fresh expression | the generator sees the uncopyrightable FACT skeleton, NOT the source prose → it cannot copy expression it never saw | ❌ build |
| ③ **Output regurgitation guard** | PROVE the output does not reproduce protected source expression (catches LLM memorization + mislabeled licenses) — the OUTPUT-side complement courts actually test (substantial similarity) | ❌ build (priority) |

## ③ Output regurgitation guard (build first — load-bearing)

A pure, deterministic detector comparing generated content vs the grounding
source excerpts. CJK has no word boundaries → operate on CHARACTER units.

`app/verify/regurgitation.py`:
- `longest_common_substring_len(a, b) -> int` — the longest CONTIGUOUS shared run
  (the strongest verbatim-copy signal). DP, O(len·window) with a rolling row.
- `char_ngram_containment(output, source, n) -> float` — fraction of the output's
  distinct n-char shingles that also appear in the source (near-verbatim paraphrase
  signal). n default 8.
- `detect_regurgitation(content, excerpts) -> RegurgitationResult`
  - `max_lcs` (chars), `overlap` (containment ratio), `flagged: bool`, `severity`.
  - **EGREGIOUS (→ auto-reject, HIGH):** `max_lcs >= LCS_REJECT` (a whole sentence
    copied verbatim). Default `LCS_REJECT = 24` chars.
  - **ADVISORY (→ NEEDS_REVIEW, MED):** `max_lcs >= LCS_FLAG` (default 12) OR
    `overlap >= OVERLAP_FLAG` (default 0.40). Surfaced to the human gate, NOT
    auto-rejected (a re-cook legitimately re-uses facts; some phrase overlap is
    normal, esp. from PD sources — the human + ② reduce it).

**Thresholds are conservative on the AUTO-REJECT side** (only egregious verbatim
runs auto-reject) so legitimate fact-reuse + shared proper nouns (玉虛宮/元始天尊,
2–4 chars) never trip it; the advisory tier surfaces softer overlap for review.

**PD nuance (documented, v1 keeps it simple):** copying PUBLIC-DOMAIN text is not
infringement, so an egregious-overlap auto-reject is strictly necessary only for
non-PD sources. v1 flags regurgitation license-AGNOSTICALLY because (a) labels can
be wrong (risk #1) and (b) verbatim copy-paste is also a QUALITY failure (we want
fresh re-contextualisation). A later refinement may downgrade EGREGIOUS→ADVISORY
when ALL overlapping sources are confirmed `public_domain`.

**Wiring:**
- `canon_verify.py`: new `FlagKind.REGURGITATION`; `verify()` runs
  `detect_regurgitation(fact.content, [g.excerpt for g in proposal.grounding])`
  per fact and appends a flag (severity per tier). Annotation only (H0 — never
  writes back / canonises).
- `verify/wiring.py` `decide_auto_reject`: an EGREGIOUS regurgitation flag
  (HIGH-severity) joins injection / HIGH-contradiction / ≥2-anachronism as an
  auto-reject trigger → terminal `rejected` + reason, never surfaced to canon.
- Tests: verbatim-copy → egregious/auto-reject; light overlap → advisory not
  rejected; shared proper nouns only → not flagged; fresh paraphrase → clean.

## ② Abstraction recook (build second — defence-in-depth)

Make the generator's input the FACT skeleton, not the source prose:
- New injected `AbstractFn` seam (a second LLM call, like the complete seam): the
  recook strategy first calls it to turn grounding excerpts into NEUTRAL factual
  bullets (entities / events / relations / dates) that deliberately DISCARD the
  source's phrasing.
- `build_recook_prompt` then frames the FACTS (not raw excerpts) as the
  re-contextualisation basis. The model never sees the source prose → it cannot
  reproduce expression it never received.
- Cost: one extra LLM call per re-cook (P3 is already the highest tier; acceptable).
- ③ still runs on the output as the backstop (defence in depth — ② reduces, ③
  proves).
- Tests: the prompt carries facts not raw excerpts; the abstract step strips
  distinctive phrasing; ③ overlap drops vs the raw-excerpt path.

## Platform posture (summary)
BYOK shifts source-license responsibility to the registering user (ToS) · input
default-deny · ② idea-abstraction · ③ output regurgitation guard · transformation
into the 商周/封神 frame · human-promote gate (H0) · provenance/audit. Each layer is
independently defensible — the platform never relies on "no one will sue".
