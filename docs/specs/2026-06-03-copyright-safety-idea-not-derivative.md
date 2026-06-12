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
| ① Input license default-deny | never *ingest* a non-PD/licensed source (the server-side ingestion COPY is a platform act the approval gate ④ cannot cure → this layer is irreplaceable) | ✅ exists (recook `_admit_sources`, FIX-2 skips per-source) |
| ② **Abstraction** — facts→fresh expression | the generator sees the uncopyrightable FACT skeleton, NOT the source prose → it cannot copy expression it never saw | ✅ built (`recook.build_abstract_prompt`) |
| ③ **Output regurgitation guard** | PROVE the output does not reproduce protected source expression (catches LLM memorization + mislabeled licenses) — the OUTPUT-side complement courts actually test (substantial similarity). Calibrated by ④: AUTO-REJECT only a WHOLESALE copy; softer overlap is ADVISORY for the human gate | ✅ built (`app/verify/regurgitation.py`) |
| ④ **Human approval gate** (H0) | enrichment is a PRIVATE DRAFT (`review_status=proposed`, conf<1.0, never auto-published); only the author's explicit promote makes it canon → the **user** is the volitional actor (liability shift) | ✅ exists (H0); documented as a legal layer here |

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
  - **EGREGIOUS (→ auto-reject, HIGH) — calibrated by ④:** a WHOLESALE copy only —
    `max_lcs >= LCS_REJECT` (default 24) AND that run covers `>= LCS_FRACTION` of the
    output (default 0.75, i.e. the output is "almost entirely a copy"). Length-
    independent (a short-but-complete copy still trips it). A single copied sentence
    inside an otherwise-original output (high LCS, small fraction) does NOT auto-reject.
  - **ADVISORY (→ NEEDS_REVIEW, MED):** `max_lcs >= LCS_FLAG` (default 12) OR
    `overlap >= OVERLAP_FLAG` (default 0.40, only on content `>= MIN_OVERLAP_LEN`).
    Surfaced to the human gate (④), NOT auto-rejected — a re-cook legitimately
    re-uses facts; the author decides borderline overlap (and may keep a short
    attributed quotation = fair use).

**Why auto-reject only the WHOLESALE case (④-calibration):** the human approval gate
④ is the real decision point, so the machine auto-rejects only the egregious copy a
human should never have to triage; everything softer is advisory. This reduces
false-blocks of good drafts without losing the insurance against bulk copy-paste.
Conservative on both ends: shared proper nouns / short idioms (玉虛宮/元始天尊, 2–4
chars) never reach even the advisory threshold.

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

## ② Abstraction recook (defence-in-depth) — BUILT

Make the generator's input the FACT skeleton, not the source prose:
- `build_abstract_prompt(canonical_name, grounding)` + `_abstract_facts` (reuses the
  existing complete seam — no new injection): the recook strategy first turns the
  grounding excerpts into NEUTRAL factual bullets (entities / events / relations /
  dates) that deliberately DISCARD the source's phrasing.
- `build_recook_prompt(proposal, source_block)` then frames the FACTS (not raw
  excerpts) as the re-contextualisation basis. The model never sees the source prose
  → it cannot reproduce expression it never received.
- Cost: one extra LLM call per re-cook (P3 is already the highest tier; acceptable).
- **Best-effort + fail-safe:** on any abstraction failure it falls back to the raw
  excerpts — ③ still runs on the output as the backstop (② reduces, ③ proves).
- Live-proven: the 玉虛宮 re-cook now uses the historical facts (邊關戍守/耕牧/祭祀)
  but RE-EXPRESSES + re-contextualises them ("…皆轉化爲仙庭規矩"), and ③ found no
  regurgitation (`verified_clean`).

## ④ Human approval gate (H0) — the liability-shifting layer

Enrichment is a PRIVATE DRAFT, never auto-published: `review_status=proposed`,
`confidence<1.0`, `origin=enrichment`; it becomes canon ONLY when the **author**
(book-owner, gated by book-service) explicitly *promotes* it on the UI. So the
**user is the volitional actor** who chooses the source, generates, reviews, and
adopts the output — the platform provides the tool. Legal grounding:
- **Volitional-conduct** (Cartoon Network v. Cablevision) — the user makes the
  adopting act; **substantial non-infringing uses** (Sony/Betamax); **DMCA §512**-
  style user-responsibility for user-directed/held content.
- **Limits (honest):** this does NOT cure the server-side INGESTION copy (→ ① stays
  load-bearing), and an *inducement* design/marketing (MGM v. Grokster) would forfeit
  the defense — so the feature must be framed as create-from-your-own-licensed-sources,
  never "launder copyrighted material". A small platform cannot rely on the big-LLM
  "training is fair use / we'll litigate" posture (actively litigated, unsettled) —
  hence defence-in-depth, not reliance on any single theory.
- **ToS (to add at productionize):** the registering user warrants they hold the
  rights/license to corpora they ingest, and is responsible for any enriched content
  they promote/use. The platform stores proposals private to the owner.

## Platform posture (summary)
BYOK + ToS shift source-license responsibility to the registering user · ① input
default-deny (ingestion copy) · ② idea-abstraction · ③ output regurgitation guard
(auto-reject only WHOLESALE copies; softer = advisory for ④) · transformation into
the 商周/封神 frame · ④ human-promote gate (H0 — private draft, volitional user act) ·
provenance/audit. Each layer is independently defensible — the platform never relies
on "no one will sue".
