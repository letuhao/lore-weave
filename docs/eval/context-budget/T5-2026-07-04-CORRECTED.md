# T5 grounding intent-gate — CORRECTED report (audit, 2026-07-04)

**Supersedes `T5-2026-07-04.md`, whose conclusion was WRONG.** The session self-audit
(3 cold-start reviewers) found the original A/B was confounded AND the feature had a
production no-op bug. This records the corrected findings + the honest measurement state.

## What was wrong with the original finding

The original report concluded "token-saving redundant / thesis weakened" and I raised a
"T3 optional" decision-point on it. Both were **invalid**:

1. **Production no-op bug (reviewer HIGH-1):** the gate fed `session.project_id` (a
   KNOWLEDGE project id) to glossary's `book_id`-keyed known-entities route → always
   `[]` → `grounding_needed=True` every turn → the gate was **byte-identical to disabled**.
2. **Confounded A/B:** the Dracula *book* (`019eeb09`) had **no knowledge project**, so
   `build_context` → `ProjectNotFound` → grounding degraded (`memory_knowledge.total=0`)
   in BOTH arms. The knob changed nothing because there was nothing to skip.
3. **Misattributed the 28K→120K split:** it is NOT grounding. The lore turn called MCP
   tools (`glossary_search`, `book_list`×2) — a multi-pass tool loop — and `input_tokens`
   is the SUMMED input across passes: the **~41K MCP tool-schema catalog re-sent each
   pass**. The real per-turn lever here is the tool catalog, a different tier than T5.

## Fixes applied (committed this session)

- `33a954036` — the gate now resolves project→`book_id` (new knowledge route
  `/internal/context/project-book/{id}` + cached `knowledge_client.resolve_book_id`),
  so it queries known-entities with the real book id. Multilingual bias-to-include
  (CJK/VN open; role-noun/thematic questions open; meta/capability questions stay
  gated out). Widened the entity vocab (min_freq=1, limit=500).
- `b6ef10ba6` — two live-caught false-positives: em-dash `—` no longer reads as
  non-English (require a non-ASCII *letter*); a junk 1-char entity `'i'` no longer
  `\b`-matches "I'm" (drop <3-char ASCII tokens).

## Live validation — the gate now FIRES correctly

Against a Dracula-linked knowledge project (`019f2be0`), gemma-4-26b, per-turn
`entity_presence` decisions:

| Turn | tag | gate | reason |
|---|---|---|---|
| smalltalk "what can you help me with" | no_lore | **gated OUT** | meta_question |
| status "give me a 3-step plan" | status_op | **gated OUT** | no_entity_no_anaphora |
| "who is the main character of this book" | lore_recall | open | lore_intent |
| "tell me about the core conflict" | continuity | open | lore_intent |
| "now make it darker — keep the same character" | continuity | open | anaphora |
| "how does the MC change across chapters" | cross_chapter | open | lore_intent |

✅ **The gate is no longer a no-op** — it makes correct, sensible per-turn decisions.
This is the primary audit corrective, live-proven.

## The honest measurement state (token SAVINGS still not quantified)

A meaningful savings A/B needs **full-mode grounding** (extraction-enabled project with
passages): only then does `grounding=True` (full, expensive) differ from `grounding=False`
(static, cheap). An extraction-DISABLED project uses static mode for BOTH, so the gate
saves 0 by construction.

Seeding full-mode grounding is a **multi-step pipeline** with real prerequisite gates:
create project ✅ → set embedding model ✅ → **pass the embedding golden-set benchmark
(`kg_run_benchmark`)** ⛔ (blocks extraction dispatch: `409 benchmark_missing`) → dispatch
extraction → workers ingest passages → measure. This is buildable (the tools exist) but
it is a genuine pipeline run, not a quick step.

**Evidence-backed interim conclusion:** the gate is correct + safe + now firing, but its
savings are BOUNDED by `build_context`'s share of the turn, and every run shows that share
is small next to the **41K MCP tool-schema catalog** re-sent across tool-loop passes on
lore turns. The likely bigger Context-Budget win is **tool-catalog / discovery trimming**,
not grounding gating — but that is a hypothesis to measure, not a new confident claim.

## FINAL — full-mode measurement done (2026-07-04)

Seeded the pipeline end-to-end: created Dracula KG project `019f2be0` → fixed a
`kg_run_benchmark` NameError → benchmark PASSED (recall@3=1.0) → extracted 2 chapters
(full mode now active). Then the clean gate ON vs OFF A/B on the SAME no-lore turn:

| | grounding | `memory_knowledge` (grounding block) | `used_tokens` |
|---|---|---|---:|
| gate ON (candidate) | False → static | 1084 | 29,649 |
| gate OFF (baseline) | True → **full** | 1126 | 29,697 |

**Verdict: KILL as a token optimization.** The gate saves **~48 tokens (~0.16%)**.
`build_context` grounding is ~1.1K in BOTH static and full mode — negligible next to the
**~41K `mcp_tool_schemas` catalog** re-sent across the multi-pass tool loop (the lore turn
= 120K = catalog × passes; the grounding block is a rounding error). The intent gate
correctly fires and is safe, but the lever it pulls is tiny.

**Action taken:** `t5_intent_gate_enabled` **defaulted OFF** (config + compose). The code
is KEPT (correct/safe/tested) — its residual value is retrieval COMPUTE/latency avoidance
on gated turns, the `entity_presence` telemetry, and being the D1 pull-mode substrate.
Re-enable when the strong-model JIT `pull` mode (grounding expensive per turn) lands.

**⚠ CORRECTION #2 (same day) — the "41K catalog is the real lever" claim was ITSELF a
measurement artifact.** The quality-gate driver defaulted to **legacy** stream format,
which advertises the FULL tool catalog. The real frontend uses **agui**, where tool
DISCOVERY is active. Measured both on the same no-lore turn:

| stream format | `used_tokens` | `mcp_tool_schemas` |
|---|---:|---:|
| **agui (real frontend — discovery)** | **4,915** | **368** |
| legacy (driver default — full catalog) | 29,697 | 41,358 |

Discovery already trims the catalog to **368 tok** for real users; the 41K only existed on
the legacy surface. So **"tool-catalog trimming" is NOT a real-user lever** — retracted. The
driver now defaults to agui so future measurements are representative.

**What this means for real (agui) users:** a simple no-lore turn is ~5K (already lean); a
lore turn is ~21K driven by AGENT BEHAVIOR (it spawned `run_subagent` + `kg_graph_query`),
not by the catalog (368) or grounding (~1.1K). The Context-Budget effort's real wins were
**T0 (ensure_ascii) + T1 (reference-first tool RESULTS)** — those addressed the original
146K case. T5 grounding-gating remains a minor lever; the residual per-turn cost on lore
turns is agent behavior (subagent spawns / tool results), already reference-first-trimmed
by T1.

**Net T5 verdict (unchanged): default OFF.** But the honest reason is *full≈static grounding
for a thinly-extracted book* (gate saves ~40 tok = the full−static delta) — genuinely
UNPROVEN for a richly-extracted book where full-mode grounding could be several K.

**Why a rich-book A/B couldn't be produced this session (root cause):** the Dracula KG
project was created directly (SQL) WITHOUT a graph schema/ontology, so extraction had no
entity-kinds to populate → `entities=0` on every chapter → grounding stayed thin
(`memory_knowledge` = 88–1126 tok, sections only `{project, instructions}`, never a
`passages`/`entities` section). Producing genuinely rich grounding needs the FULL KG
authoring pipeline (author a graph schema → benchmark → extraction-with-schema →
passages), several gates deep — and a second extraction wedged (likely the LM Studio
queue). So T5's savings on a truly lore-rich book remain **unmeasured, not disproven**.

**FINAL honest state:** T5 gate is correct + safe + tested + fires correctly + **default
OFF**. On all *measurable* configs it saves ≈0 (thin grounding). Its potential value on a
richly-grounded book, or under the D1 pull mode, is unproven and would need the full KG
seed. This is where the honest measurement bottoms out on the available infra.

**Bonus:** the seeded Dracula KG project (`019f2be0`, benchmark-passed, 2 chapters
extracted) partially resolves **D-EVAL-BOOK** — there is now a KG-linked book on
claude-test for future grounding/answer-correctness measurement.
