# Session Handoff — Session 42 END (K17.2 + K17.3 LLM stack COMPLETE, three R3 reviews)

> **Purpose:** orient the next agent in one read. **Source of truth for detailed state remains [SESSION_PATCH.md](SESSION_PATCH.md).** This file is the single, unversioned handoff — updated in place at the end of each session. Do NOT create `_V*.md` variants.
> **Date:** 2026-04-15 (session 42 end)
> **HEAD:** K17.3-R3 (commit `5f2cc66`)
> **Branch:** `main` (ahead of origin by sessions 38–42 commits — user pushes manually)

---

## 1. TL;DR — what shipped this session

Session 42 was **infra-capable** (live Neo4j + live Postgres + full Docker Compose stack). First action was paying the session-41 test debt, which surfaced one test-invocation fragility (pre-existing) but zero code regressions. Then built out the K17.2 BYOK LLM proxy pair (a + b) and the K17.3 JSON extraction wrapper, with a **third-pass critical review (R3)** on every shipped task plus first-review (R1) for K17.2c which was born inside a follow-up commit.

```
Session 41 test debt paid            ✅  (906 → 906 clean, then 906 → 930 through session)
K17.2a  provider-registry JSON body rewrite       ✅  + R3
K17.2b  knowledge-service ProviderClient          ✅  + R1/R2 at BUILD + R3
K17.2c  doProxy live-pool integration tests       ✅  + R1 (first review)
K17.3   LLM JSON extraction wrapper               ✅  + R3
```

**Session commit sequence (7 total):**
```
325fcfa  feat(provider-registry): K17.2a — transparent model rewrite for JSON proxy bodies
8d28e24  feat(knowledge-service): K17.2b — provider-registry BYOK LLM client
b8b8972  fix(k17.2a-r3): third-pass review follow-ups + K17.2c integration tests
decd91c  fix(k17.2bc-r3): review follow-ups for K17.2b (R3) + K17.2c (R1)
ab10efe  feat(knowledge-service): K17.3 — LLM JSON extraction wrapper with parse/validate retry
5f2cc66  fix(k17.3-r3): third-pass review follow-ups — F2/F4/F9 real bugs + 4 defensive
```

**Test execution:** full suites green against live infra throughout the session.
- **knowledge-service:** 906 → **966** (+60 net this session — K17.2b, K17.3, R3 tests)
- **provider-registry Go tests:** 0 → **15** (K17.2a helper + K17.2c integration)
- **Zero regressions, zero skips.**

Full suite was run with `KNOWLEDGE_DB_URL` + `GLOSSARY_DB_URL` pointed at compose Postgres and `TEST_NEO4J_URI=bolt://localhost:7688`. All 93 previously-skipped Postgres integration tests now execute in CI-equivalent mode.

---

## 2. Where to pick up — K17.4 is unblocked, fully ready

The K17 LLM extraction stack is now complete from prompt loader to retry wrapper:

```
K17.1 LLM prompts + loader          ✅  load_prompt(name, **substitutions)
K17.2 BYOK LLM client               ✅  ProviderClient.chat_completion(...)
K17.3 JSON parse + retry wrapper    ✅  extract_json(schema, ...)
K17.4 Entity LLM extractor          ← NEXT — fully unblocked
K17.5 Relation LLM extractor
K17.6 Event LLM extractor
K17.7 Fact LLM extractor
K17.8 Orchestrator
K17.9 Golden-set harness
```

**K17.4 is the natural next task** and can serve as the first **end-to-end integration smoke test** firing a real LLM call through the whole K17.1 → K17.3 stack. Its scope:

1. Define a `EntityExtractionResponse(BaseModel)` Pydantic schema — one outer wrapper holding `entities: list[EntityCandidate]`. Each candidate: `canonical_name`, `kind` (person/place/organization/artifact/concept), `confidence: float` (0.0–1.0), `aliases: list[str]`.
2. Write `extract_entities(text: str, known_entities: list[str], **caller_context) -> list[EntityCandidate]` that:
   - Calls `load_prompt("entity_extraction", text=text, known_entities=json.dumps(known_entities))` (K17.1)
   - Calls `extract_json(EntityExtractionResponse, system=<extractor system prompt>, user_prompt=<loaded prompt>, response_format={"type": "json_object"}, ...)` (K17.3)
   - Runs each candidate's `canonical_name` through K15.1 canonicalization to produce deterministic IDs (idempotent re-run requirement)
3. Unit tests with `FakeProviderClient` (K17.3 pattern) covering: happy path, empty input, known-entities anchoring, canonicalization determinism.

**Integration smoke test opportunity:** if a provider is configured in provider-registry (Ollama at `http://host.docker.internal:11434`, an OpenAI key, LM Studio), K17.4 can be the first task to actually hit a real LLM via the full stack. Hitting a real LLM would validate:
- K17.2a's JSON body rewrite at runtime (model-field substitution)
- K17.2b's error classification (401/429/timeout paths on a real provider)
- K17.3's fence-stripping (R3 F9 — local LMs routinely emit fenced JSON)
- K17.3's retry contract against a real parse failure

**Alternative pickups** if K17.4 isn't the right priority:
- **K15.11** — glossary sync handler (needs glossary event bus up)
- **K16.2** — job start endpoint (wires K16.1 state machine into real HTTP + Postgres)
- **K17.9** — golden-set benchmark harness (scaffold exists, real wiring pending K17.2+K18.3 — partially unblocked now)

---

## 3. Deferred items added this session

Six new rows in [SESSION_PATCH.md §Deferred Items](SESSION_PATCH.md). None block Track 2 progress; all are documented follow-ups with explicit target phases.

- **D-K17.2a-01** — provider-registry Prometheus metrics. Scope: add `client_golang` + `/metrics` route + collector. Framed as an ops cross-cutting task since the whole service has zero metrics infra today. **Target: K19/K20 ops cleanup.**
- **D-PROXY-01** — other provider-registry call sites (`verifyModelsEndpoint`, `verifySTT`, `verifyTTS`) have the same `COALESCE(pc.secret_ciphertext,'')` + silent-empty pattern that K17.2a-R3 C10 fixed for `doProxy`. Sweep needed. **Target: next provider-registry cleanup.**
- **D-K17.2a-02** — cleared in the same commit (413 classification + 4 MiB cap documentation). Row kept as a pointer.
- **D-K17.2c-01** — K17.2c tests bypass the chi router and `requireInternalToken` middleware by calling `srv.doProxy(...)` directly. Full-router coverage via `srv.Router().ServeHTTP(...)` is possible but ~20 LOC per test for coverage that's 80% already tested in `TestInvokeModelValidationAndUnauthorized`. **Target: next proxy hardening pass.**
- **D-K17.2b-01** — `ProviderClient` returns `ProviderDecodeError` for tool_calls-shaped responses (`content: null` + `tool_calls: [...]`). Fine for K17.4–K17.7 JSON-mode; future tool-based extractor will need a new `chat_completion_with_tools()` method or union return type. **Target: K17.8+ or first tool-based extractor.**

No perf deferrals opened. No Track-1-blocking deferrals.

---

## 4. Important context the next agent must know

### Process discipline (unchanged from session 41)

- **9-phase workflow is mandatory**, including Phase 8 (SESSION_PATCH update) and Phase 9 (COMMIT). Do not "batch the commit with the next task" — that is the drift the workflow exists to prevent.
- **R1 + R2 critical reviews are mandatory after every BUILD.** Session 42 added an **R3 third-pass** convention for any task that feels "done" at R2 — every R3 this session found at least one real bug or real documentation lie that R1+R2 missed.
- **Never skip review discipline by saying "this is just a follow-up".** K17.2c was born inside a K17.2a-R3 commit with zero review; K17.2b-R3 + K17.2c-R1 session ran the first-ever review on K17.2c and found 4 real gaps (T14/T18/T19/T23). Follow-ups are code; code needs review.

### K17.2 architectural subtleties

- **The BYOK proxy rewrites the request body's `model` field server-side** (K17.2a). Knowledge-service sends `{"model": "proxy-resolved", ...}` as a placeholder; provider-registry's `doProxy` resolves the real model name from the DB and overwrites it before forwarding upstream. This is the reason `ProviderClient` doesn't need to know the provider's model naming conventions.
- **The 4 MiB JSON body cap** (K17.2a) is enforced at the proxy layer. 413 `PROXY_BODY_TOO_LARGE`. Callers almost never hit it; when they do, it means the extractor is trying to feed a whole book at once or `known_entities` substitution is pathologically large. K17.2b classifies it as `ProviderUpstreamError` with an explicit greppable message.
- **`user_model` credentials must be present** (K17.2a-R3 C10). An empty `secret_ciphertext` on a `user_model` row returns `500 PROXY_MISSING_CREDENTIAL` rather than silently forwarding an anonymous request. `platform_model` legitimately has no secret — the guard is scoped to `user_model` only.
- **`ProviderClient.__init__` fails fast on a misconfigured URL** (K17.2b-R3 D12). `httpx.InvalidURL` at construction time, not silent failure on first call. The lifespan hook calls `get_provider_client()` eagerly so startup aborts cleanly.
- **`ProviderRateLimited` carries `retry_after_s`** parsed from the upstream `Retry-After` header (K17.2b-R3 D8). K17.3 honors this via its injectable `sleep_fn` parameter.
- **`ProviderClient` construction is kwarg-only** (K17.2b-R3 D14). `ProviderClient(base_url=..., internal_token=..., timeout_s=..., transport=...)`. Positional calls will `TypeError`.

### K17.3 architectural subtleties

- **Maximum LLM call count per `extract_json` invocation is 3**, not 2. The docstring lie was fixed in K17.3-R3 F11. HTTP-retry and JSON-retry budgets are independent — each capped at 1 retry, so the total is: 1 initial + 1 optional HTTP retry (on `ProviderRateLimited`/`ProviderUpstreamError`/`ProviderTimeout`) + 1 optional JSON fix-up retry.
- **Markdown code fences are stripped automatically** (K17.3-R3 F9). LLMs (especially local ones — Ollama, LM Studio) routinely wrap JSON in ```` ```json ... ``` ```` regardless of `response_format`. K17.3's `_strip_code_fences` applies on both first-attempt and retry parse paths. Fenced JSON does NOT burn a retry.
- **`ExtractionError.raw_content` carries the LAST LLM output**, including on the `provider_exhausted` fix-up path (K17.3-R3 F2/F4). K16 job failure rows should persist this for post-mortem debugging.
- **`extract_json(schema=...)` schemas must be outer wrapper Pydantic models**, e.g. `class EntityExtractionResponse(BaseModel): entities: list[Entity]`. Direct `list[...]` schemas won't work because `schema.model_validate(parsed)` requires a BaseModel subclass.
- **Bad content in retry prompts is capped at 8 KB** (K17.3-R3 F6). If the LLM echoes an entire chapter, the retry prompt truncates it rather than doubling the context size.
- **Retry fix-up prompts say "Return ONLY the corrected JSON"** (Phase 3 I10). Load-bearing for providers that silently ignore `response_format` (Ollama, some vLLM routes).

### Infra & test invocation (IMPORTANT for next session)

- **Compose stack is running at session end** with the K17.2a proxy rewrite and K17.3-R3 code deployed. If restarting from scratch:
  ```
  cd infra && docker compose up -d
  cd infra && docker compose --profile neo4j up -d neo4j
  ```
- **Neo4j host port is 7688** (not 7687). Compose exposes `bolt://localhost:7688`.
- **Postgres host port is 5555** (not 5432).
- **pytest must run from `services/knowledge-service/`**, not the repo root. The `test_config.py` subprocess test fails when pytest is launched from the repo root — pre-existing test-invocation fragility, not a K17 bug. Canonical invocation:
  ```
  cd services/knowledge-service && KNOWLEDGE_DB_URL=postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_knowledge GLOSSARY_DB_URL=postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_glossary TEST_NEO4J_URI=bolt://localhost:7688 TEST_NEO4J_USER=neo4j TEST_NEO4J_PASSWORD=loreweave_dev_neo4j python -m pytest tests/
  ```
- **Go tests for K17.2c require:** `TEST_PROVIDER_REGISTRY_DB_URL=postgres://loreweave:loreweave_dev@localhost:5555/loreweave_provider_registry?sslmode=disable` set before `go test`.
- **`python` must be the miniconda binary** (`C:\Users\NeneScarlet\miniconda3\python.exe`), not the pyenv `pytest` shim — only miniconda has `cachetools` + the other service deps installed.
- **`go test -race` cannot be used in this dev environment** (cgo unavailable on the Windows build). K17.2c's race-safety contract is documented in the test file as a Go-memory-model analysis rather than machine-verified.

### Multi-tenant safety rail (unchanged)

- **K11.4 tenant isolation** is enforced via `assert_user_id_param` in every repo-layer Cypher helper. The one exception is the quarantine cleanup admin path (K15.10), which deliberately bypasses `run_write` to allow `user_id=None` for global sweeps.
- **SESSION_PATCH.md §Deferred Items is load-bearing.** Read it at the start of every PLAN phase. Any row whose Target phase equals the current phase is a must-do.

---

## 5. Session 42 stats

| Metric | Before session 42 | After session 42 | Delta |
|---|---|---|---|
| knowledge-service tests | 906 | **966** | **+60** |
| provider-registry Go K17.2 tests | 0 | **15** | **+15** |
| Session commits | 0 | **7** | — |
| New deferred items | — | 5 | — |
| Cleared deferred items | — | 1 (D-K17.2a-02 in-commit) | — |
| Real bugs found at R3 | — | 4 (F2/F4 raw_content, F9 fence-strip, K17.2a-R3 C10 missing cred, K17.2bc-R3 D12 broken startup promise) | — |

**Test debt from session 41 is fully paid.** K15.10 / K15.12 / K16.1 / K17.1 all verified against live Postgres + live Neo4j on session 42 day 1.

---

## 6. Housekeeping note

This file is the single, unversioned handoff. The previous `SESSION_HANDOFF_V*.md` chain was removed at end of session 41; history lives in git + SESSION_PATCH's "Session History" section. **Future sessions MUST update this file in place — do NOT create a `_V18.md`** (session 42 already followed this rule by overwriting the session-41 content).
