# RT-0.13 · COST AND FEASIBILITY

**Artifact under review:** `ARCHITECTURE.md` §0.13 (lines 70–208) · `2026-08-04-agent-runtime-RUNSTATE.md`
items **1.8** (line 1165) and **2.9** (line 1192).
**Angle:** not *is it right* — *what does it cost, and what breaks if adopted as written*.
**HEAD:** `4ec3f2a83318d0343c14c31bdd5645619fd9e16d`, verified. No tracked file edited but this one.

---

## VERDICT IN ONE PARAGRAPH

§0.13's *diagnosis* survives. Its *costing* does not. Three of the four things CP-1.8 bundles are
genuinely cheaper now; the fourth is a same-cost bug fix riding the argument. CP-2.9 is costed as if
it were a chat-service change and it is a **three-component change** — and one of its two supporting
factual claims (*"`seed` appears nowhere on the provider path — checked, not assumed"*) is **false at
`services/provider-registry-service/internal/provider/adapters.go:678`**, where `seed` is already in
the forwarding allowlist. The `code_revision` "nearly free" claim is **false as written**: `GIT_SHA`
reaches an image **label**, which is the one place a Python process cannot read it, and
`os.environ.get("GIT_SHA")` returns `None` in **every** current scenario including the
`build-stack.sh` happy path. And the largest problem is structural: **`NarrowingRule`-as-data cannot
express the narrowing stage that motivated the entire clause.** `budget_names_by_tokens` — the arm-E
killer §0.13.4 quotes — is a running accumulator over a sort order. It is not a `keep(row)` predicate
in closure form and it will not be one in data form.

---

## 1 · `NarrowingRule` must become data, not a closure

### 1a · What exists today

`services/chat-service/app/agentruntime/surface.py:51-62`:

```python
@dataclass(frozen=True, slots=True)
class NarrowingRule:
    stage: str
    reason: str
    keep: Callable[[dict], bool]
```

Applied at exactly one site, `surface.py:185-201` (`_narrow`), one row at a time:
`if rule.keep(row): kept.append(row) else: self._log.record(...)`.

**Production construction sites of `NarrowingRule`: 0.** All 9 are in
`services/chat-service/tests/test_cp1_membrane.py` (lines 507, 519, 528, 535, 553, 613, 695, 717,
802). The refactor is therefore free in production code — that part of the cheap-moment argument is
correct and I am not disputing it.

**But look at what the 9 test rules are named.** Six of the nine use `stage="token_budget"` (507,
553, 613, 695, 717, 802). `token_budget` is the one legacy stage that provably **cannot** be a
`keep(row)` predicate. The fixtures already encode the wrong shape, and converting `keep` from
`Callable` to data does not fix that — it removes the escape hatch that currently disguises it.

### 1b · The expressiveness that is actually lost — and it is not what the clause says

A closure loses **nothing** a data enum loses, in one direction: any per-row predicate expressible as
`{op, params}` is expressible as a lambda. The loss runs the other way, and it is **exactly one
capability**: a closure can close over a **pre-computed keep-set** —
`lambda r: r["id"] in precomputed_keep` — where `precomputed_keep` was decided by an accumulator, a
global ranking, or an HTTP call somewhere else.

That is the whole game, and it cuts both ways:

- it is the **only** way today's `NarrowingRule` can model a token budget or a top-K at all;
- and it is precisely the thing that makes the record useless, because **the decision was made
  outside the rule**, so `{stage, reason}` describes a mechanism that did not run here.

So the data refactor's real effect is: *it converts a silent modelling lie into a compile-time
refusal*. That is a genuine win — but it is a win only if the data language grows a **pipeline stage
kind**, not if it is a keep-predicate enum. A keep-predicate enum makes the budget **inexpressible**,
and inexpressible means it will be implemented one call-site away, which is the eight-frame defect
this package's own docstrings (`surface.py:188-192`) were written to prevent.

### 1c · The legacy stages, counted

I enumerated the reduction points in `tool_surface.py` (772 lines), `tool_discovery.py` (1697 lines)
and `stream_service.py` (8315 lines). Roughly **60–79 distinct narrowing sites** depending on whether
you count a shared helper once or per call site. The precise total is not the finding; the
**partition** is, and I verified the load-bearing half myself.

**Expressible as declarative per-row policy with parameters — ~9 distinct rule *kinds*, covering the
clear majority of sites:**

| kind | example site | data form |
|---|---|---|
| domain/prefix membership | `tool_discovery.py:521-523` `hot_tool_names` | `{op: domain_in, domains: [...]}` |
| group equality | `tool_discovery.py:758, 891, 930, 1360` | `{op: domain_eq, group}` |
| name-set exclusion | `tool_discovery.py:756, 889, 919`; `stream_service.py:3030, 3325` | `{op: not_in, names: [...]}` |
| visibility / legacy | `tool_discovery.py:932-934` `is_legacy_tool` | `{op: visibility_ne, value: legacy}` |
| permission tier | `stream_service.py:1406-1417, 1432-1447` | `{op: tier_in, tiers: [R], plus_prefix: plan_}` |
| intent gate | `tool_discovery.py:481-504` | `{op: not_in, names: [...], exempt: [...]}` |
| kind filter | `surface.py:233-242` `discover(kind=)` | `{op: field_eq, field: kind}` |
| liveness / broken | `tool_discovery.py:928, 1051-1053` | `{op: not_in, names: <resolved>}` |
| depth / const gate | `stream_service.py:2161-2173` | `{op: const, value: bool}` |

**NOT expressible as any `keep(row)` predicate — verified individually:**

| # | site | why not |
|---|---|---|
| 1 | `tool_surface.py:196-201` `_budget_names_impl` — `if used + t > token_budget and used > 0: break` | **running accumulator**. Row N's fate depends on rows 1..N−1 |
| 2 | `tool_surface.py:192-195` sort key `(0 if _is_read_tool else 1, _tool_tokens, name)` | **the total order IS the policy**; not a row property |
| 3 | `tool_surface.py:280-290` `budget_rail_tools` | accumulator over author-declared step order |
| 4 | `tool_surface.py:538-544` rail candidate 3-tier reorder | exists solely to change *who* #3 drops |
| 5 | `tool_surface.py:726` `activated_tools[-AUTO_ACTIVATED_TAIL:]` | positional recency tail |
| 6 | `tool_surface.py:762-769` reverse-iteration eviction + `:771` `ACTIVATED_TOOLS_CAP` | LRU-order accumulator, then a count cap |
| 7 | `tool_discovery.py:763-764` `scored.sort(...); scored[:max(1,limit)]` | **global top-K ranking** |
| 8 | `tool_discovery.py:1400-1401` semantic top-K | global ranking **+ an embedding HTTP call** |
| 9 | `stream_service.py:2091` `offered_tools = tools_supported and not last_iter` | pass index + a flag flipped by a prior pass |
| 10 | `stream_service.py:2121-2126` rail gate over `turn_succeeded` (a `Counter` consumed in step order, `rail.py:675-681`) | multiplicity-dependent, not membership |
| 11 | `stream_service.py:2130-2131` / `2111-2114` `failure_suppress` / `oneshot_suppress` | filled by *earlier tool results in the same turn* |
| 12 | `stream_service.py:1330-1337` `_add` first-source-wins dedup | insertion-order-dependent |
| 13 | `stream_service.py:2161-2167` gate requiring `advertised` non-empty | depends on the **result** of all prior stages |
| 14 | `stream_service.py:2943, 2976-2977` per-category / per-turn `tool_list` counters | per-turn counters |

**Verified counts:** the token budget is invoked at **9 call sites** — `tool_surface.py:375, 459,
501, 552, 632` and `stream_service.py:2954, 3070, 3172, 3351`. Top-K appears at **2**
(`tool_discovery.py:764, 1401`).

**And one that is not a narrowing at all in either form:** `stream_service.py:1274-1296` **mutates
the row's schema** — it strips `book_id` from an `ambient_book` tool's advertised parameters.
`NarrowingRule` is keep-only. Neither the closure form nor the data form can express it, so it will
live outside the rule pipeline in both worlds. That is a pre-existing hole in the design, and §0.13
does not name it.

### 1d · The finding that actually matters here

> **§0.13.4's own headline example is in the inexpressible column.**
> *"`budget_names_by_tokens` was query-dependent — 87 candidate tools for one message and 101 for
> another — so the control varied per input."*

That is `tool_surface.py:196-201`. It is *not* query-dependent because a predicate read the query; it
is query-dependent because the **candidate list handed to the accumulator** differed, and the
accumulator's cut point moves with it. Making `NarrowingRule` data does not touch that. Recording
`policy_revision` does not touch it either — the policy was identical in both runs. **The thing that
would have caught 87-vs-101 is recording the accumulator's INPUT LIST and its budget, which is layer
A (input closure), not the closure-to-data refactor.**

CP-1.8 leads with the closure argument and files input-closure second. The priority is inverted
relative to the evidence.

### 1e · And the premise is overstated

> *"a `Callable` has no content identity, so no `policy_revision` can exist"* (RUNSTATE:1165)

A closure has **transitive** content identity: `module:qualname` pinned by `code_revision`. Under
`code_revision`, a policy expressed as closures is content-addressed — coarsely. What data buys is
**attribution granularity** (which rule changed) and **cross-`code_revision` comparability**, not the
existence of a revision id.

More sharply: **the DRIFT gate, which CP-2.9 names as the CI gate and the main value, does not need
policy-as-data at all.** §0.13.2 D says drift *"needs the record alone"* — i.e. recorded inputs plus
**today's** code. Today's code contains today's closures; replay calls them. Only **fidelity** replay
(reconstruct that day's policy without that day's code) needs data — and §0.13.2 D itself says
fidelity is *"for incidents, not CI"*. So CP-1.8's stated justification supports the deliverable that
the clause explicitly deprioritises.

---

## 2 · Content-addressed revisions

### 2a · Is there a precedent that predicts trouble? Yes. Several, and they are the same defect.

There is **no shared canonical-JSON helper anywhere in this repository.** Counted at HEAD:

- **18 distinct Python JSON-canonical hash implementations**, in **5 serialization-flag variants** —
  `{sort_keys}` · `{sort_keys, ensure_ascii=False}` · `{sort_keys, separators}` ·
  `{sort_keys, ensure_ascii=False, separators}` · `{sort_keys, ensure_ascii=True, separators}`.
  **Two sites hashing the same dict produce different digests.**
- **4 demonstrable copy-paste clone pairs**, including
  `services/learning-service/app/events/snapshot.py:66` ↔
  `services/knowledge-service/app/wiki/fingerprint.py:32` (the latter's docstring says "ported
  from"), and `scripts/freeze-tool-catalog.py:46` ↔ `eval/arms/run_arms.py:63` — **the tool-catalog
  producer and its verifier are two independent implementations of the same hash.**
- **5 hash algorithms** in content-addressing use: sha256, sha1, md5, blake2b, blake3.
- **0 sites normalize floats.** No `-0.0`/`1.0`-vs-`1` handling anywhere; `json.dumps` emits
  non-standard `NaN`/`Infinity`.

### 2b · The defect history is a *series*, not an incident

- **The ETag bug** (`docs/sessions/SESSION_ARCHIVE.md:4901`, commit `eb26e8323`, `/review-impl` M1,
  critical): `_etag(job)` hashed `updated_at` only, so a chapter rename in *another service* served
  stale data via 304. Two failure modes in one — a response field outside the hash, and the naive fix
  (`hash()`) would have been PYTHONHASHSEED-randomised per uvicorn worker. Live code:
  `services/knowledge-service/app/routers/public/extraction.py:1704-1732`.
- **`schema_fingerprint` outside the hash**
  (`services/lore-enrichment-service/app/gamegen/fold.py:526-535`): re-folding after a schema move
  produced the **same** `content_hash`, `ON CONFLICT` returned the OLD row, and the new fingerprint
  was silently discarded. Its own comment: *"Found by probe, not by reading."*
- **The ruleset digest series — four separate commits, all the same shape**: `442f0bac8`
  ("the digest is real, and it hashes something that governs"), `c6a46afe4` ("the digest now covers
  the LAW"), `1df3e151d` ("the progression pin enters the hashed bytes, schema 4 → 5"), `5c484849b`
  ("an author's own identity enters the hashed bytes"). Four rounds of *"field X was not in the
  hashed bytes."*
- **`ensure_ascii` sweep** (`e84214cc5`): 16 sites fixed, **3 baselined and permanently unfixable** —
  `scripts/language-bias-gate.py:280-300, 355` records the reason: flipping `ensure_ascii` *"would
  invalidate every stored `outline_fingerprint`/`bindings_fingerprint` — a re-run for every arc — in
  exchange for nothing."* Two of the three are documented as **"migrations, not edits"**.

**That last one is the precedent that predicts trouble here, and it is exact.** Once a digest is
persisted, the serializer is frozen by the data, not by the code. `docs/standards/multilingual.md:29`
already carries this scar. §0.13 proposes persisting four new digests
(`manifest_revision`, `policy_revision`, `budget_revision`, `code_revision`) with **no** named
canonical form, **no** shared helper to reuse, and **no** stated algorithm.

### 2c · Cost, honestly

Getting canonicalization right is **not expensive** — it is one small module. The repo even has
better-than-adequate prior art to copy:
`services/lore-enrichment-service/app/gamegen/answer_hash.py:267` and `fold.py:523` (blake2b,
domain-separated, length-prefixed, presence-tagged), and the gold standard
`crates/ruleset-core/src/ruleset.rs:220` / `ruleset_codec.rs:142` (versioned binary canon +
`digest_at()`), which is Rust-only.

**Getting it wrong is expensive and irreversible-in-practice.** So the cheap-moment argument is
**valid here specifically** — but what is cheap now is **deciding and gating the canonical form**,
not **emitting revisions**. Those are separable and CP-1.8 fuses them.

**Requirement:** a single `agentruntime/canon.py` with a **version prefix in the hashed bytes** (the
ruleset-core pattern), `sort_keys=True, ensure_ascii=False, separators=(",",":")`, explicit float and
`None` policy, a domain tag per revision kind, and a test that an independent re-implementation
agrees. Without the version prefix the repo repeats `1df3e151d` — *"schema 4 → 5"* — with persisted
rows already in the ground.

### 2d · And a P4 problem with emitting `manifest_revision` at CP-1

`contracts/agent-runtime-manifest.json` holds **0 declarations** (verified). A `manifest_revision`
emitted at CP-1 is therefore `hash(<empty catalog>)` — **the same value on every INSERT**.

RUNSTATE:1169 states P4's rule: *"No CP-0 column bound to a constant at any INSERT"* — which *"failed
retrofitted at eight asserted values."* An emitted-at-CP-1 `manifest_revision` **is** a constant-valued
column at every INSERT, and any test over it cannot distinguish *"the hasher works"* from *"the hasher
returns a constant"*. The earliest point at which `manifest_revision` is **testable** is the first
admitted declaration — CP-4 brick 2 (`book_list`).

`manifest_revision` is also *already* accepted and *already* unsupplied: it is a keyword-only
parameter at `services/chat-service/app/services/instrument.py:319, 339-340` with **zero callers**
repo-wide. §0.13.4 names this as a CP-0 artefact. Emitting a constant into it at CP-1 does not close
that hole; it closes the *shape* of the hole with an untestable value.

---

## 3 · `code_revision` from `GIT_SHA` — the "nearly free" claim is FALSE

§0.13.2 A, line 117-119: *"The last is nearly free — `scripts/build-stack.sh` already computes
`GIT_SHA` and labels images with it."*

`scripts/build-stack.sh` is **22 lines**. Verified in full:

- `:14` `GIT_SHA="$(git rev-parse HEAD)"` — full SHA
- `:16` `export GIT_SHA BUILD_TIME`
- `:21` `exec docker compose build "$@"`

It goes **one place**: `infra/docker-compose.yml:11-13`, the `x-build-labels` anchor
(`org.loreweave.git_sha: "${GIT_SHA:-unknown}"`), applied as `build.labels` at **36** build blocks
including chat-service at `:965-975`.

**A `build.labels` entry is OCI image metadata. It is not a build-arg and not an ENV. The process
cannot read it.** The proof is the only consumer: `scripts/check_stack_freshness.py:199-205` reads it
from the **host** via `docker image inspect --format '{{ index .Config.Labels ... }}'`.

**No Dockerfile in this repository contains the string `LABEL`, and zero Dockerfiles declare an
`ARG`/`ENV` for `GIT_SHA`/`VCS_REF`/`COMMIT`/`VERSION`.** `services/chat-service/Dockerfile` sets
exactly one ENV (`PORT=8090`). chat-service's `environment:` block
(`infra/docker-compose.yml:976-1041`) has no build-identity variable of any kind.

### `os.environ.get("GIT_SHA")` today

| scenario | value |
|---|---|
| `docker compose up` after `build-stack.sh` | **`None`** |
| `docker compose up` without the wrapper | **`None`** |
| local `uvicorn` | **`None`** |
| `pytest` in CI | **`None`** — no workflow sets it; CI builds **no** first-party images at all |
| dirty working tree | **`None`** in-process, and the *label* silently carries clean HEAD |

**`None` in 100% of current scenarios, including the happy path.** No Python file in `services/**`
reads `GIT_SHA`/`VCS_REF`/`BUILD_SHA`/`COMMIT_SHA`/`code_revision`/`app_version` —
zero matches. `services/chat-service/app/config.py` has no version field.

### Dirty builds

`build-stack.sh:14` has no `git status --porcelain`, no `--dirty`, no `git describe`. A build from a
dirty tree stamps clean HEAD and is **indistinguishable from a clean build**. For a `code_revision`
used in *fidelity* replay (§0.13.2 D: *"did the record match what the code at that time would
produce?"*), that is not a degraded field — it is a field that **confidently attests a commit whose
code never ran**. An absent `code_revision` fails loudly; a dirty-but-clean-looking one fails
silently, which is the failure mode this whole spec exists to eliminate. This is the
*degrade-safe-guard-must-surface-unverified* class.

### Real cost

**~4 files plus a semantic decision**, not "nearly free":

1. `ARG GIT_SHA` + `ENV GIT_SHA` in the Dockerfile **and** `args:` under each `build:` block (labels
   do not imply args) — *or* add `GIT_SHA: "${GIT_SHA:-unknown}"` to `environment:`, which is cheaper
   but then describes the **container start**, not the image's code, which for an audit field is a
   different fact;
2. a settings field in `services/chat-service/app/config.py`;
3. dirty-tree handling in `build-stack.sh:14` (a `-dirty` suffix, or refuse);
4. CI wiring via `GITHUB_SHA`, since CI builds nothing.

**Note for the record:** `verification/RT-0.13-falsifiability.md:415` marks this claim
*"✅ true; 'nearly free' is fair"*. That review verified that `build-stack.sh` computes and labels —
which is true — and did not verify the step that matters, that a process can read it. A peer
verification already passed this.

---

## 4 · `seed`, prompt hashes, per-block hashes — CP-2.9 is a cross-service change

### 4a · The factual claim is false

§0.13.3, line 141-142: *"this repository passes **no seed at all** — checked, not assumed: `seed`
appears nowhere on the provider path."*

Verified with `grep -n seed services/provider-registry-service/internal/provider/adapters.go`:

```
663://   - top_p, top_k, presence_penalty, frequency_penalty, seed —
678:		"seed",
```

`seed` **is on the provider path**, in the `forwardOptionalChatFields` passthrough allowlist at
`adapters.go:669-679`. The **last hop is already done.** What is missing is the first three.

A clause that says *"checked, not assumed"* and is wrong at the checked point is worse than one that
says "assumed", because it suppresses the next reader's check.

### 4b · The hops

| # | component | file:line | body type |
|---|---|---|---|
| 1 | chat-service | `stream_service.py:390` `StreamRequest(**request_kwargs)` | dict → typed |
| 2 | `sdks/python/loreweave_llm` | `models.py:134` `class StreamRequest(BaseModel)` | **typed; drops unknown fields silently** |
| 3 | provider-registry `POST /internal/llm/stream` | `internal/api/stream_handler.go:58` `type streamRequest struct` | **typed Go struct; drops unknown JSON** |
| 4 | `buildChatStreamInput` | `stream_handler.go:392` | **explicit per-field if-nil ladder** |
| 5 | adapter | `adapters.go:1048` (openai) / `:1386` (ollama) / `:1598` (lm_studio) | allowlist — **`seed` present** |

**Three typed chokepoints, each of which silently drops an unknown field.** `ai-gateway` is *not* on
this path — it is MCP/tool federation; `grep temperature services/ai-gateway/src/` returns zero.

### 4c · The precedent is live in the code right now, and it is `top_p`

chat-service sets `top_p` at `stream_service.py:381-382` and `:2085-2086`. It is a validated
(`app/models.py:217`, `0.0–1.0`), user-facing, DB-persisted session setting. And:

- `sdks/python/loreweave_llm/models.py` has **zero** occurrences of `top_p`; `StreamRequest` has no
  such field and pydantic v2 defaults to `extra='ignore'` — **silently discarded at construction**;
- `stream_handler.go:58` `streamRequest` has no `TopP`; `buildChatStreamInput` never sets it.

**`top_p` is a dead parameter today**, and the only non-test occurrences downstream are the allowlist
entry and its comment. This is precisely what `seed` becomes if CP-2.9 is scoped as a chat-service
change. It is also the *unconditional-success-that-discards-its-own-signal* class from this repo's own
bug lore.

### 4d · Real cost of `seed`

**4 files, 3 components, minimum:** `chat-service/app/models.py` (GenerationParams) ·
`chat-service/app/services/stream_service.py` (**3** `StreamRequest` construction sites: `:390`,
`:2372` via `:2083`, `:8272`) · `sdks/python/loreweave_llm/models.py` · `stream_handler.go` (struct
`:58` + `buildChatStreamInput` `:392`). Grows to ~7 if `seed` becomes a persisted session setting
(`routers/sessions.py`, `routers/ai_settings.py`, `services/settings_resolution.py`).

**Provider reality:** `ResolveAdapter` (`adapters.go:1616-1639`) has 4 kinds. **Anthropic does not
call `forwardOptionalChatFields` at all** (body built at `adapters.go:1224-1257`, `temperature` +
`max_tokens` only) — correct, since the Anthropic API rejects `seed`. So `seed` buys **nothing on a
cloud-Anthropic run** and everything on ollama/lm_studio/openai. Given this repo's *local-LLM-first*
stance that is the right trade — but §0.13.3's *"a local model becomes genuinely replayable; a cloud
model becomes at least diffable"* should say plainly that for one of the four adapters the field is
structurally inert. Also: the stateful `/v1/responses` path (`responses_adapter.go:106`) forwards
`temperature` only and would drop `seed` when `stateful=True`.

### 4e · `prompt_hash` — chat-service-only, and honest

Prompt assembly is fully in chat-service: `stream_service.py:5791` `build_system_message(...)`,
`:5804` system insert, `:5278` compaction summary. Downstream only *reshapes*. `hashlib` is already
imported at `stream_service.py:15`. **This one is genuinely cheap and genuinely chat-service-local.**
It is the highest value-per-line item in all of §0.13 — *"today a prompt can change with nobody
noticing"* is a real, currently-undetectable failure, and one hash closes it.

### 4f · Per-cache-block hashes — the boundary is in the WRONG SERVICE

§0.13.3 makes `block_hashes` load-bearing (*"show which cache block broke, and `tools` is the first
one"*). But the cache breakpoints are split across two services **by design**:

- chat-service owns the **system** breakpoints — 2 of Anthropic's max 4, documented at
  `stream_service.py:5295-5308` with the `D-ANTHROPIC-CACHE-4BP` scar (an old renderer emitted ~11
  breakpoints and Anthropic 400'd);
- **provider-registry owns the `tools` breakpoint** —
  `services/provider-registry-service/internal/provider/prompt_cache.go:79-92`
  `applyAnthropicPromptCache` marks the **last tool**, gated by `anthropicCacheMinChars = 4096`
  (`:57`), called from `adapters.go:1189, :1257`. Rationale at `prompt_cache.go:65-73`: it cannot
  reach the tools until it has converted them.

So a `tools` block hash computed **in chat-service** hashes the **pre-translation** tool array. The
bytes Anthropic actually caches are produced after an adapter-side schema translation. **An
adapter-side change alters the cached bytes while leaving the chat-service hash green.** That is
`fold.py:526-535` again — a fingerprint outside the hashed bytes — and the ETag bug again, in a new
place. Computing this hash on the wrong side of a translating hop produces a check that **can be
green while the thing it protects changed**, which is strictly worse than not having it.

There is a second, unrelated hazard already latent: nothing enforces that chat-service's 2 + 
provider-registry's 1 stays ≤ Anthropic's 4. That coupling is held by prose comments in two
languages. §0.13's `block_hashes` would be the first mechanism that *could* enforce it — a real
argument in its favour, and one the clause does not make.

**Verdict:** `prompt_hash` — cheap, local, high value. `block_hashes` — cross-service, and if scoped
to chat-service it is a false-negative generator. Do not ship the second one at CP-2 as written.

---

## 5 · The "cheap moment" argument, taken apart

The argument: *the manifest is empty and nothing is admitted, so now is cheap.* That is a real
argument and it applies to **exactly two** of the seven proposed items. Cost is *not* uniform across
the bundle, and bundling same-cost items under a cheap-moment header inflates the header's weight.

| item | cheaper NOW than at CP-4? | why |
|---|---|---|
| **`NarrowingRule` → data** | ✅ **YES, strongly** | **0 production construction sites** (all 9 are in `test_cp1_membrane.py`). At CP-4 every admitted declaration's policy is written in the old shape and the migration is a rewrite. But see §1: only if the data language includes pipeline kinds |
| **purity boundary named + gate-enforced** | ✅ **YES** | Ambient reads are already confined to **one** module (`manifest.py:23-25, 54-57` — `os`, `pathlib`). `scripts/agentruntime-membrane-gate.py` (416 lines) is already an AST walker with `ALLOWED_EXTERNAL = {}` (`:60`); adding an ambient-stdlib check scoped to one module is ~30 lines + a selftest. This cost grows monotonically with module count |
| **canonical serialization DECIDED + gated** | ✅ **YES** | Not because the code is cheaper, but because **persisted digests freeze the serializer**. `language-bias-gate.py:280-300` documents 3 permanently-baselined sites for exactly this reason. Zero digests are persisted today |
| **`manifest_revision` EMITTED** | ❌ **NO — and arguably worse now** | Over 0 declarations it is `hash(∅)`: a **constant-valued column at every INSERT**, which P4 (RUNSTATE:1169) forbids and which no test can distinguish from a broken hasher. Same code cost whenever; only testable from CP-4 |
| **narrowing-log idempotency** | ❌ **NO** | `NarrowingLog.record` (`narrowing.py:81-82`) is a pure `list.append` with no dedup key. The fix is ~5 lines on `(declaration_id, stage, pass_number)`. Zero coupling to admission, zero stored data. **This is a bug fix riding the cheap-moment argument.** Its cost is identical at CP-1, CP-2 and CP-4 |
| **`code_revision` plumbing** | ❌ **NO** | 4 files of Dockerfile/compose/config wiring plus a dirty-tree decision. Touches no admitted row. Identical cost whenever |
| **`seed` threading** | ❌ **NO** | 4 files across 3 components. Touches no admitted row. Identical cost whenever. If anything **cheaper later**, bundled with the `top_p` fix it duplicates |
| **`prompt_hash`** | ❌ **NO (same cost)** | chat-service-local, ~10 lines, whenever |
| **`block_hashes`** | ❌ **cheaper LATER** | The block boundary contract is currently split by prose across two services. CP-2.1 replaces the assembly layer; hashing a boundary you are about to move is rework |

**Score: 3 of 9 are genuinely time-sensitive. 6 are same-cost-whenever or later-is-better.**

The cheap-moment framing is therefore **correct but over-applied**. Its correct scope is: *shapes
that later code will be written against* (the rule form, the purity boundary, the canonical form).
Its incorrect scope is: *values, plumbing and bug fixes* (revisions emitted, `code_revision`, `seed`,
hashes, log dedup) — none of which get more expensive from an admitted row, because none of them are
shapes that admitted rows conform to.

---

## 6 · The smallest subset that captures most of the value

**Ship at CP-1 — three items, all shape, all irreversible-if-deferred:**

1. **`NarrowingRule` becomes data — with a stage-kind enum that includes `order_by`,
   `take_while_budget` and `top_k`, not only keep-predicates.** Without those three kinds the
   refactor makes the 9 verified budget call sites and 2 top-K sites *inexpressible*, and they will
   be implemented one call-site away — reproducing the exact split-decision defect
   `surface.py:188-192` documents. A keep-predicate-only enum is **worse than the closure it
   replaces**.
2. **`agentruntime/canon.py` — one canonical-bytes function with a version prefix in the hashed
   bytes**, `sort_keys=True, ensure_ascii=False, separators=(",",":")`, explicit float/`None`
   policy, a domain tag per revision kind, and a gate forbidding any second implementation inside
   `agentruntime`. Copy `crates/ruleset-core/src/ruleset_codec.rs:142` (`digest_at(version)`), which
   is the one place in this repo that got it right on the first try. Reason it is now: **18
   implementations, 5 flag variants, 0 shared helpers, and three separate multi-commit repair series
   in this repo's history.**
3. **Layer B — the purity boundary named, with the existing membrane gate extended to enforce
   ambient-stdlib confinement to `manifest.py`.** Cheap today (one module), monotonically more
   expensive per module added.

**That subset costs roughly one working day and captures the clause's irreversible value.**

**What the rest buys, and when to buy it:**

| deferred item | buys | buy at |
|---|---|---|
| narrowing-log idempotency | a correctness fix, unrelated to §0.13's thesis | **now, but bill it as a bug, not as this clause** — it is measured broken at `narrowing.py:81-82` |
| `prompt_hash` | detection of silent prompt drift — **currently undetectable**, chat-service-local, ~10 lines | **CP-2, and this is the single best value-per-line item in §0.13** |
| `manifest_revision` emitted | a field that is `hash(∅)` until CP-4 | **CP-4**, with the first admitted declaration, where a test can distinguish a hash from a constant |
| `code_revision` | fidelity replay — which §0.13.2 D itself says is *for incidents, not CI* | **CP-2 at the earliest**, and only with dirty-tree handling. A silently-wrong `code_revision` is worse than none |
| `seed` | replayability on 3 of 4 adapters, structurally inert on Anthropic | **CP-2, bundled with the `top_p` fix and a test that the SDK does not swallow the field** — the two edits are identical and in the same two files |
| `block_hashes` | cache-break attribution, and the only mechanism that could enforce the ≤4-breakpoint budget | **after CP-2.1**, computed **provider-registry-side** or on both sides with an equality assertion. Chat-service-only is a false-negative generator |

---

## 7 · Corrections the clause needs before adoption

1. **`ARCHITECTURE.md:141-142`** — *"`seed` appears nowhere on the provider path — checked, not
   assumed"* is **false**. `services/provider-registry-service/internal/provider/adapters.go:678`.
   Correct reading: *the final hop already accepts `seed`; the three typed hops above it drop it,
   exactly as they silently drop `top_p` today.*
2. **`ARCHITECTURE.md:117-119`** — *"nearly free"* is **false**. `GIT_SHA` reaches an image **label**
   only (`infra/docker-compose.yml:11-13`), read from the host by
   `scripts/check_stack_freshness.py:199-205`. `os.environ.get("GIT_SHA")` is `None` in every
   scenario. Say **~4 files plus a dirty-tree decision**.
3. **`RUNSTATE:1165`** — *"a `Callable` has no content identity, so no `policy_revision` can exist"*
   is too strong (`module:qualname` + `code_revision` gives coarse identity) and, more importantly,
   **argues for the wrong deliverable**: the DRIFT gate CP-2.9 names as *the* CI gate does not need
   policy-as-data. State the real reason — *a keep-predicate over a pre-computed set records a
   `{stage, reason}` for a decision made elsewhere.*
4. **`RUNSTATE:1165`** — `manifest_revision` emitted over a 0-declaration manifest is a
   constant-valued column at every INSERT, which is the P4 violation this same RUNSTATE quotes at
   `:1169`. Move the emission to CP-4; keep the canonical form at CP-1.
5. **`ARCHITECTURE.md:144-145`** — `block_hashes` cannot be computed correctly in chat-service. Name
   `prompt_cache.go:79-92` as the owner of the `tools` breakpoint, or drop `block_hashes` from CP-2.
6. **§0.13.4's own example is in the inexpressible column.** 87-vs-101 is a *running accumulator over
   a varying input list* (`tool_surface.py:196-201`), not a policy-identity problem. Layer A (input
   closure) is what catches it; the clause files layer A second and leads with the closure refactor.

---

*Reviewer note: `verification/RT-0.13-falsifiability.md:415` already passed the `code_revision`
claim. It verified the true half (build-stack computes and labels) and not the load-bearing half (a
process can read it). Two verifications agreeing is not two checks when they check the same half.*
