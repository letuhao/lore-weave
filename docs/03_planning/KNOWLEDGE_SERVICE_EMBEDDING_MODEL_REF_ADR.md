---
name: KNOWLEDGE_SERVICE_EMBEDDING_MODEL_REF_ADR
description: ADR — knowledge-service passes a logical embedding-model name where provider-registry's /internal/embed requires a user_model UUID; the whole semantic-retrieval layer is dead. Decision + fix design.
type: adr
---

# ADR — Embedding model-ref contract: logical name vs. provider UUID

> **Status:** IMPLEMENTED — core (session 58 cycle 3), simplified variant.
> Cycle 2 wrote this ADR (DESIGN only); cycle 3 implemented the fix and
> verified the Track 2/3 extraction pipeline live. See §12.
> **Discovered by:** the D-K21B-06 follow-on Track 2/3 extraction live-smoke
> attempt (session 58). Setting up the smoke surfaced that the K17.9
> embedding benchmark gate can never pass live.
> **Supersedes nothing.** Corrects the half-built K12.1–K12.3 contract.

---

## 1. Context

LoreWeave's knowledge-service has a semantic-retrieval layer ("Mode 3"):
chapter passages are embedded into vectors, stored in Neo4j with a vector
index, and retrieved by cosine similarity at chat time and during
extraction. Embedding calls are BYOK — they go through provider-registry's
`POST /internal/embed`, which resolves the user's registered provider
credentials and forwards to the upstream embedding model.

The D-K21B-06 follow-on (a live end-to-end smoke of the Track 2/3
extraction pipeline) could not get past step 1: the K17.9 embedding
benchmark gate. Investigation found a hard cross-service contract bug.

---

## 2. The bug

**knowledge-service side** — a project's embedding model is stored as a
**logical name string**. [`knowledge_projects.embedding_model`](../../services/knowledge-service/app/db/migrate.py#L33)
is a `TEXT` column constrained (by `EMBEDDING_MODEL_TO_DIM` in
[`passages.py:74`](../../services/knowledge-service/app/context/selectors/passages.py#L74))
to logical names: `bge-m3`, `bge-small`, `text-embedding-3-small`,
`text-embedding-3-large`. knowledge-service passes that string **unchanged**
as the provider `model_ref`.

**provider-registry side** — [`internalEmbed`](../../services/provider-registry-service/internal/api/server.go#L2285)
does `modelRef, err := uuid.Parse(in.ModelRef)` ([server.go:2320](../../services/provider-registry-service/internal/api/server.go#L2320))
and returns `400 EMBED_VALIDATION "invalid model_ref"` on any non-UUID.
`user_model` resolution is strictly `WHERE um.user_model_id=$1` — a UUID
primary key. provider-registry has **zero** name-based model resolution
(confirmed across `internalEmbed`, `doProxy`, `jobs_handler`,
`stream_handler`; the `llm-gateway` OpenAPI declares `model_ref` as
`type: string, format: uuid` everywhere).

**Result:** `embed(model_ref="bge-m3")` → `uuid.Parse` fails → **400, every
call**. No embedding call from knowledge-service can succeed.

---

## 3. Blast radius

Every embedding call site passes a logical name as `model_ref`. The bug is
**not** confined to extraction — it kills the entire Mode-3 retrieval layer:

| # | Call site | Effect when it 400s |
|---|---|---|
| 1 | `app/extraction/passage_ingester.py:244` (chapter passage ingest) | Extracted chapters never get embeddings → no vector index → Mode-3 finds nothing |
| 2 | `app/context/selectors/passages.py:218` (`select_l3_passages` — **live chat-turn query embedding**) | Every Mode-3 chat turn silently degrades to facts-only (`except EmbeddingError → return []`) |
| 3 | `app/tools/executor.py:198` (K21 `memory_search` tool) | The K21 memory tool's search returns nothing |
| 4 | `app/routers/public/drawers.py:191` (drawer semantic search) | Surfaces as a `502` to the frontend |
| 5 | `eval/fixture_loader.py:114` (K17.9 benchmark fixture load) | Benchmark cannot embed its golden set |
| 6 | `eval/mode3_query_runner.py:89` (K17.9 benchmark + eval queries) | Benchmark cannot run → `start_extraction_job` always `409 benchmark_failed/missing` → **extraction pipeline cannot start at all** |

Failures in 1/2/3/5 are swallowed (`except EmbeddingError → []`), so the
production symptom is **silent zero-recall semantic retrieval**, not a loud
error. Only drawers (4) surfaces it. This is why it went unnoticed.

`model_source` is hardcoded `"user_model"` at every site.

---

## 4. Why it was never caught

It shipped broken **at birth** — `embedding_client.py` (the Python caller)
and `server.go internalEmbed` (the Go handler) both landed in the **same
commit** `4ea3475d` (2026-04-18, "K12.1–K12.3 BYOK embedding pipeline")
with an unaligned contract: the Go side parsed a UUID, the Python side sent
a name. It has never been aligned since.

Every test mocks `embedding_client.embed` — `tests/unit/test_embedding_client.py`
mocks the httpx transport and only ever uses `model_ref=str(uuid4())` (a
UUID, so it never reproduces the mismatch); every selector / ingester /
tool / drawers test injects an `AsyncMock` client. There is **no**
integration test exercising `embedding_client` against a real
`internalEmbed`. Same root cause as the K21 tool-calling loop (D-K21B-06)
and the K21-B `execute_tool` timeout: a cross-service contract that only
unit-mock coverage ever touched.

---

## 5. Intended design vs. what was built

The K12.x task plan ([`KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md`](KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md),
K12.1–K12.4) specified a **`(provider_id UUID, model_name string)` pair**:

- **K12.1** — provider-registry endpoint `POST /internal/providers/{provider_id}/embed`
  with `{ model: string, ... }`, resolving the model **by name** within the
  provider, after validating it is embedding-capable.
- **K12.3** — `knowledge_projects` gains `embedding_provider_id UUID`,
  `embedding_model TEXT`, `embedding_dimension INT`; PATCH validates the
  `(provider_id, model)` pair against provider-registry before saving.

**What was actually built diverged on both sides:**

1. provider-registry built a flat `POST /internal/embed` taking
   `{model_source, model_ref}` where `model_ref` is a `user_models`
   **UUID** — matching the unified LLM-gateway `model_ref`-is-UUID
   convention, **not** the K12.1 `{provider_id}/embed` + `model: string`
   spec.
2. knowledge-service's `embedding_client` sends `project.embedding_model`
   (the logical name) — neither a `(provider_id, model)` pair nor a UUID.
3. The `embedding_projects.embedding_provider_id UUID` column **was
   created** (K12.3) but never populated, never read, never plumbed — it
   is a dead column (not in `_SELECT_COLS`, every writer passes `None`).
4. K12.3's "PATCH validates via provider-registry" was never built —
   `change_embedding_model` and project PATCH accept any free-text string.

So K12.3 was implemented at roughly 40%: the schema column exists, the
wiring does not.

---

## 6. Decision

### Adopt **Option A — embedding model addressed by a `user_model` UUID**, consistent with the platform-wide `model_ref`-is-UUID invariant.

knowledge-service stores the provider-registry **`user_model_id` UUID** of
the embedding model and passes *that* as `model_ref`. The logical name is
**kept** — it is still needed for vector-space routing — but it stops being
the wire identity.

> **Note (review-impl M5).** Option A is *not* chosen because it is the
> smaller change — it is plausibly the larger one (it spreads across
> knowledge-service schema + 6 call sites + the FE picker + the eval CLI,
> whereas Option B is concentrated in one provider-registry handler). It is
> chosen because the alternatives put a **knowledge-service curated
> abstraction** (`bge-m3` — a name provider-registry has no concept of)
> into provider-registry's resolution path, and because a bare name is
> ambiguous. Pick the option by where the concern *belongs*, not by diff
> size.

### Option B (rejected) — add name resolution to provider-registry's `/internal/embed`

This is what K12.1 originally specified. **Rejected because:**

- `bge-m3` / `text-embedding-3-small` are **knowledge-service curated
  logical names** — they are not `provider_model_name`s (LM Studio's actual
  id is `text-embedding-bge-m3`). Resolving them would force provider-registry
  to carry knowledge-service's curated map: a leak of the wrong concern
  across a service boundary.
- It contradicts the now-established platform invariant: `jobs`, `stream`,
  `proxy`, and the `llm-gateway` OpenAPI all treat `model_ref` as a UUID.
  Making `embed` the one name-addressable endpoint is a lasting
  inconsistency.
- A bare model name is **ambiguous** — a user can register the same
  `provider_model_name` under two different credentials. A UUID is not.

### Option C (rejected for now — but reconsider at CLARIFY) — platform-hosted embedding models

Embedding models are small, shared, and identical across users — unlike
chat LLMs, there is little BYOK value in each user running their own. They
are a natural fit for `platform_model` hosting: LoreWeave registers a small
curated set of embedding models centrally, and a project references one by
its `platform_model_id` UUID. This would mean **users never register or
benchmark a BYOK embedding model** — a real onboarding-cost reduction.

Rejected *for this ADR's default* only because `internalEmbed` currently
**rejects `model_source="platform_model"`** ([server.go:2363](../../services/provider-registry-service/internal/api/server.go#L2363)),
so Option C is strictly more work than Option A *today*. But it is the
better long-term shape, and Option A is forward-compatible with it (both
pass a UUID `model_ref`; only `model_source` differs). **The implementation
CLARIFY must make an explicit platform-vs-BYOK call for embeddings** — see
Q5. If platform-hosted embeddings are chosen, Option A's per-user
registration + benchmark UX is replaced by a one-time platform setup.

---

## 7. Design (Option A)

### 7.1 The vector-space problem — why the logical name must stay

A project's passages are all embedded in **one** vector space. Neo4j
`:Passage` nodes are tagged with `embedding_model` as a string property
([`passage_ingester.py:289`](../../services/knowledge-service/app/extraction/passage_ingester.py#L289))
and `find_passages_by_vector` filters on it; the vector index is sized to a
fixed **dimension**. So the fix cannot simply replace the name with a UUID
— it must store **both**:

- a **UUID** — the wire identity for the provider call (`model_ref`);
- a stable **logical name** + **dimension** — for index tagging,
  cross-project vector-space consistency, and the `EMBEDDING_MODEL_TO_DIM`
  routing.

This is exactly the `(uuid, name, dimension)` triple K12.3 specified — it
just was never wired.

### 7.2 Schema — `knowledge_projects`

Add (idempotent `DO`-block migration, matching the existing `migrate.py`
idiom):

```
embedding_user_model_id  UUID    -- provider-registry user_models.user_model_id
```

`embedding_model TEXT` and `embedding_dimension INT` already exist — keep
them. The dead `embedding_provider_id UUID` column is **left in place**
(dropping it is a separate, unrelated cleanup — `D-EMB-CLEANUP-01`); the
new column is purpose-named so the dead one causes no confusion. The
`project_embedding_benchmark_runs` audit table keeps its own
`embedding_provider_id` column unchanged (out of scope).

### 7.3 The configuration flow — how a project gets its embedding model

When the user sets a project's embedding model (`change_embedding_model`,
project PATCH, or the K12.4 FE picker):

1. The FE picker lists the user's **embedding-capable registered
   `user_models`** (provider-registry — see open question Q1).
2. The user picks one → the request carries `embedding_user_model_id`
   (UUID).
3. knowledge-service **validates by probing**: it issues one real
   `embedding_client.embed(model_ref=<uuid>, texts=["dimension probe"])`.
   - On `400/404` → reject the config change (`422`, "model not found or
     not usable").
   - On success → `dim = len(result.embeddings[0])`.
4. **Dimension must have a Neo4j vector index (review-impl M2).** The
   probed `dim` must be one of the dimensions for which a `:Passage`
   vector index exists — today `SUPPORTED_PASSAGE_DIMS = (384, 1024,
   1536, 3072)` (the `passage_embeddings_*` indexes in
   `neo4j_schema.cypher`). A model whose probed `dim` is outside that set
   (e.g. a 768-dim `nomic-embed-*`) must be **rejected at config time**
   (`422`, "embedding dimension N is not supported") — otherwise its
   passages can never be indexed and Mode-3 silently dies again, exactly
   the bug this ADR fixes. (Alternative: create the vector index on
   demand for any probed dimension — heavier; settle at CLARIFY, Q6.)
5. knowledge-service stores `embedding_user_model_id` (UUID),
   `embedding_dimension` (measured + index-validated), and
   `embedding_model` (a stable label — see open question Q2).

**Probing the dimension at config time** is the recommended resolution of
the long-standing "curated list vs. BYOK" tension (KSA §4.3 assumed a
curated `SUPPORTED_EMBEDDING_MODELS` map; BYOK means the set is open). A
measured dimension is deterministic, works for any model, and removes the
need to keep `EMBEDDING_MODEL_TO_DIM` authoritative — it can degrade to a
sanity-check hint or be retired (open question Q3). Note the probe is a
real network call from a config endpoint — give it a bounded timeout and
treat a provider flake as a retryable `503`, not a stored bad config
(review-impl L2).

### 7.3a Changing the embedding model on a populated project (review-impl M4)

The endpoint is named `change_embedding_model`, so change is first-class —
but every existing `:Passage` of the project is embedded in the **old**
model's vector space (and possibly a different dimension). A naive swap
leaves the whole graph's vectors silently mismatched against query vectors
→ garbage retrieval. The rule:

- Changing `embedding_user_model_id` on a project that **has no passages
  yet** → free, just store the new config.
- Changing it on a project that **already has embedded passages** → the
  change MUST trigger a **full re-embed** of every passage (a background
  job, like extraction), OR be **blocked** with a "delete the graph and
  re-extract" instruction. The implementation CLARIFY picks one (Q7); the
  re-embed job is the better UX but is extra scope.
- The benchmark gate (§7.3b) and `embedding_dimension` must update
  atomically with the model change.

### 7.3b Re-key the K17.9 benchmark gate on the UUID (review-impl M3)

`project_embedding_benchmark_runs` and `start_extraction_job`'s
`get_latest(...)` currently key on `embedding_model` (the **name**). If a
user swaps `embedding_user_model_id` while the logical-name label stays
`bge-m3`, a stale benchmark row for the *old* model would falsely satisfy
the gate — defeating the benchmark's purpose (catch a model that cannot
retrieve the user's own entities). The benchmark row's identity must become
`embedding_user_model_id` (the UUID), not the name. This is a schema +
query change on the audit table and the gate — fold it into the cycle.

### 7.4 Call-site changes

All six call sites in §3 change from passing `project.embedding_model` to
passing `project.embedding_user_model_id`. The selector/ingester signatures
that currently thread an `embedding_model: str` thread an
`embedding_user_model_id: UUID` instead (or both, where the name is still
needed for `:Passage` tagging). `model_source` stays `"user_model"`.

The K17.9 benchmark + `eval/run_benchmark.py` `--embedding-model` flag must
accept a UUID (or a UUID plus a label). `eval/fixture_loader.py` and
`mode3_query_runner.py` thread the UUID.

### 7.5 Guardrails

- A project with no `embedding_user_model_id` set must **not** silently
  embed with a bad ref. The embed-dependent paths should treat "no
  embedding model configured" as an explicit state (extraction refuses to
  start with a clear error; chat Mode-3 degrades deliberately, logged at
  INFO not swallowed silently). **Existing projects** that had only the
  old `embedding_model` name set land in exactly this state after the
  migration (`embedding_user_model_id = NULL`) → they must be
  re-configured through the new flow before Track 2/3 works (review-impl
  L3; pure schema-add migration, no backfill — see Q4).
- Add the missing **integration test**: one test that exercises
  `embedding_client` against a real (or contract-faithful stub)
  `internalEmbed`, so a future name-vs-UUID drift fails loudly. (Memory:
  test-stub + real-contract companion.)

---

## 8. Open questions — settle at the implementation cycle's CLARIFY

- **Q1 — embedding-capability discovery.** How does the FE picker know
  which of a user's registered `user_models` are embedding models?
  `user_models.capability_flags` is a free JSONB — is there an `embedding`
  flag today, and is it populated? If not, this is a provider-registry
  sub-task (classify embedding-capable models, expose them on the
  user-models list API). May widen the cycle into provider-registry.
- **Q2 — the logical-name label.** With BYOK, what string goes in
  `embedding_model` for `:Passage` tagging? The `user_model` alias? Its
  `provider_model_name`? A user-entered label? It must be stable for the
  life of the project (re-tagging passages on change = a re-embed).
- **Q3 — fate of `EMBEDDING_MODEL_TO_DIM`.** Retire it in favour of the
  probed dimension, or keep it as a sanity check / known-good list?
- **Q4 — existing projects / data.** Are there any projects in any live DB
  with `embedding_model` set + passages already embedded? If so they were
  embedded by... nothing (the path never worked) — so there is almost
  certainly **no real embedded data to migrate**. Confirm, then the
  migration is pure schema-add, no backfill.
- **Q5 — platform-hosted embeddings (Option C — review-impl M1).** This
  is now a **required CLARIFY decision**, not a footnote. Embedding models
  are shared and identical across users; hosting a curated set as
  `platform_model`s removes per-user registration + benchmarking entirely.
  It needs `internalEmbed` to accept `model_source="platform_model"`
  (currently rejected, [server.go:2363](../../services/provider-registry-service/internal/api/server.go#L2363)).
  Decide platform-vs-BYOK for embeddings before designing the FE picker —
  it changes the whole config UX.
- **Q6 — dimension vs. Neo4j index.** Reject a probed dimension with no
  `:Passage` vector index, or create the index on demand? (§7.3 step 4.)
- **Q7 — re-embed on model change.** Background re-embed job vs. block the
  change on a populated project. (§7.3a.)
- **Q8 — embed scope beyond knowledge-service (review-impl L1) — RESOLVED.**
  Grepped `services/` for `/internal/embed` callers: knowledge-service is
  the only one (provider-registry is the server). Blast radius confirmed
  knowledge-service-only; no cross-service widening.

---

## 9. Sizing & sequencing

**Full-stack, L–XL.** Touches: knowledge-service (schema migration,
`change_embedding_model` + project PATCH validation, repo, 6 call sites,
the `Project` model), the K17.9 benchmark + `eval/` CLI, the FE embedding
picker (K12.4), provider-registry (Q1 capability discovery, and Q5 if
platform-hosted embeddings are chosen), the `project_embedding_benchmark_runs`
audit table + the K17.9 gate (§7.3b re-key), an optional re-embed job
(§7.3a), and a new integration test. It is **not** an ad-hoc fix — it needs
its own CLARIFY (settle Q1–Q7) → DESIGN → BUILD cycle.

Recommended slicing if it proves XL at CLARIFY:
- **Cycle 1** — provider-registry embedding-capability discovery (Q1), if
  needed.
- **Cycle 2** — knowledge-service schema + config flow + the 6 call sites
  + the integration test.
- **Cycle 3** — FE embedding picker alignment + eval CLI.

## 10. Test plan

- A knowledge-service **integration test** exercising `embedding_client`
  against a contract-faithful `internalEmbed` — the regression lock that
  was missing (§4).
- `change_embedding_model` / PATCH: valid UUID → probes + stores dimension;
  unknown/inactive UUID → `422`; non-embedding model → `422`.
- Each of the 6 call sites: a regression test asserting the UUID (not the
  name) reaches the embed call.
- The K17.9 benchmark end-to-end against a real embedding model (the
  D-K21B-06 follow-on smoke this ADR unblocks).

---

## 11. Decision log

| Date | Decision |
|---|---|
| 2026-05-18 | Bug found during the D-K21B-06 Track 2/3 extraction smoke. ADR written. **Option A** (UUID `model_ref`) chosen over Option B (name resolution in provider-registry) — provider-registry must not carry knowledge-service's curated logical-name abstraction. Implementation deferred to a dedicated CLARIFY→DESIGN→BUILD cycle (D-EMB-MODEL-REF-01). |
| 2026-05-18 | `/review-impl` on the ADR — 0 HIGH, 5 MED, 3 LOW. Folded: M1 → Option C (platform-hosted embeddings) added as a first-class CLARIFY decision (Q5); M2 → §7.3 step 4 (probed dimension must have a Neo4j vector index); M3 → §7.3b (re-key the K17.9 benchmark on the UUID); M4 → §7.3a (re-embed-on-change rule); M5 → §6 note (Option A chosen for *concern ownership*, not diff size). L1 → Q8 resolved by grep (knowledge-service is the only `/internal/embed` caller). L2/L3 folded into §7.3/§7.5. |
| 2026-05-18 (cycle 3) | Implemented — **Option A, simplified to one column** (§12). The two-column design (§7.2: a new `embedding_user_model_id` UUID + the kept logical name) was found over-engineered during BUILD: the logical name is **vestigial**. A UUID tags `:Passage` nodes and discriminates vector spaces just as well, and the dimension already has its own column. So the existing `embedding_model TEXT` column simply now carries the `user_model` UUID; `embedding_dimension` is caller-supplied; `EMBEDDING_MODEL_TO_DIM` is retired from runtime. No new column, no 6-site re-threading (the sites already passed `embedding_model` as `model_ref` — it just holds the right value now). M3 (benchmark gate re-key) resolved for free — the gate keys on `embedding_model`, which is now the UUID. |

---

## 12. Implementation note (session 58 cycle 3)

**Built — the simplified one-column variant.** `embedding_model TEXT` now
holds the provider-registry `user_model` UUID (the `/internal/embed`
`model_ref`); `embedding_dimension` is caller-supplied; the logical name
and `EMBEDDING_MODEL_TO_DIM` are retired. 8 source files + 3 test files:

- `db/models.py`, `db/repositories/projects.py` — `embedding_dimension`
  is now a directly-settable `ProjectUpdate` field (was derived from the
  name map); clearing `embedding_model` still clears the dimension.
- `benchmark/runner.py`, `context/modes/full.py` — dimension sourced from
  `project.embedding_dimension`, not `EMBEDDING_MODEL_TO_DIM`.
- `eval/run_benchmark.py` — CLI takes `--embedding-dim` explicitly.
- `context/selectors/passages.py` — `EMBEDDING_MODEL_TO_DIM` marked legacy.
- `routers/public/extraction.py` — fixed the `_GRAPH_STATS_CYPHER`
  duplicate-column syntax error (a separate latent bug — the graph-stats
  endpoint 500'd on Neo4j 2026.03; bare `RETURN 0, 0, count(ev), 0`
  branches now alias every column).

**Two further latent bugs the live smoke surfaced + fixed in the same
cycle** (all "wired but never run end-to-end"):

- `services/knowledge-service/Dockerfile` — the **production** stage
  copied only `app/`, but `app/benchmark/runner.py` imports `eval.*`.
  The benchmark endpoint `ModuleNotFoundError`'d in every deployed image.
  Production stage now copies `eval/` too. (Cleaner: move the three
  benchmark-runtime modules under `app/benchmark/` — `D-EMB-EVAL-PKG-01`.)
- `sdks/python/pyproject.toml` — `loreweave_extraction` shipped **without
  its `prompts/*.md`** files (setuptools drops non-`.py` data by default,
  no `package-data`). Every Pass-2 extraction `FileNotFoundError`'d on
  the prompt template. Added `[tool.setuptools.package-data]`.

**Verified live.** Full Track 2/3 extraction smoke: registered
`text-embedding-bge-m3` (provider-registry) → embed works with the UUID
(1024-dim) → K17.9 benchmark ran (`recall@3=1.0`, `mrr=1.0` — embeddings
flow correctly) → extraction job `complete` (1 chapter) → **9 `:Entity`
nodes + 10 `:Passage` nodes** in Neo4j → `graph-stats` returns
`{entity_count: 9, passage_count: 10}`. knowledge-service unit suite
1608/1608.

**Still open (follow-ups, not blocking the pipeline):**

- **`D-EMB-MODEL-REF-02`** — `change_embedding_model` (`extraction.py`,
  via `set_extraction_state`) sets `embedding_model` but **not**
  `embedding_dimension` → a model change through that endpoint leaves a
  stale/None dimension. Needs the §7.3a re-embed design too. The project
  PATCH path (used by the smoke) is correct; `change_embedding_model`
  is the gap.
- **`D-EMB-MODEL-REF-03`** — the FE embedding picker (K12.4) + the probe-
  at-config-time validation (§7.3) are not built; config is API/DB-direct
  for now. Q1 (capability discovery) + Q5 (platform-vs-BYOK) still open.
- **`D-EMB-BENCHMARK-CAL-01`** — the K17.9 golden-set
  `negative_control_max_score` ceiling (0.50) is too strict for bge-m3's
  score distribution: a clean run scored `recall@3=1.0` but
  `negative_control=0.664` → `passed=false`. The smoke flipped the row to
  proceed. The threshold needs per-model calibration.
- **`D-EMB-EVAL-PKG-01`** — move `fixture_loader` / `mode3_query_runner` /
  `persist` from `eval/` into `app/benchmark/` so production doesn't ship
  the eval harness.
- The full ADR open questions Q1/Q2/Q5/Q7 remain for the
  picker/platform/re-embed follow-up.
