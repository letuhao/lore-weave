# Spec/Plan: WS-4C Half A — auto-capture chat-established canon into the glossary inbox

**Date:** 2026-07-10 · **Branch:** `feat/context-budget-law` · **Size:** L (new cross-service route +
DB column + chat post-turn side-effect) · **Track:** B (`D-WS4C-HALFA`, the last Track-B item).
**Half B** (admit `llm_tool_call` facts to L2 auto-recall) shipped in `0742d8373`.

---

## 1. The gap this closes (F4 write-side)

From [the persistent-memory investigation](2026-07-09-agent-discoverability-and-workflow/investigations/2026-07-09-persistent-memory-and-longsession-continuity.md#3):

> **Write side — MISSING.** No auto-extraction/auto-persist of conversation facts. The only chat→store
> write is the explicit `memory_remember` tool […] Extraction pipelines run over **book chapters, not chat**.
> […] **The durable path that actually auto-recalls is: persist canon as GLOSSARY entities.**

So a name the user coins in turn 3 is gone by turn 40 unless the model *chose* to persist it. Half A makes
the platform do it: every Nth assistant turn, the turn's text is extracted for newly-named entities and they
land as **`draft` + `ai-suggested` glossary entities** — the existing, already-shipped **review inbox**
(`AiSuggestionsPanel` → promote / reject-with-`ai-rejected`-tombstone).

**Human-gated by construction (the user's explicit choice).** Capture never writes canon. A draft is invisible
to L1/L2 auto-recall until a human promotes it to `active`; a rejected name is tombstoned and never re-proposed.

## 2. What already exists (build on, do not rebuild)

| Piece | Where | Reused how |
|---|---|---|
| The review inbox (draft + `ai-suggested`, promote/reject) | `frontend/src/features/glossary/hooks/useAiSuggestions.ts` | unchanged — capture writes into it |
| Create-only, dedup-safe, tombstone-aware entity write | `proposeNewEntity` (`mcp_server.go`) — advisory-locked, tags `[ai-suggested, assistant]`, returns `created` / `skipped_exists` / `skipped_tombstoned` | called per candidate |
| Ontology-grounded LLM entity extractor | `runDocExtractor` / `parseDocExtraction` (`entity_doc_extract_tools.go`, WS-4A) | factored out + a capture-flavored prompt |
| Per-project chat behaviour toggles reaching chat via `kctx` | `knowledge_projects.tool_calling_enabled` → `KnowledgeContext` | mirrored for `canon_capture_enabled` |
| Post-turn best-effort background spawn | `stream_service.py` `_fire_executive_tick` / `_auto_generate_title` | one more `asyncio.create_task` |

Net new code is therefore small: one glossary internal route, one DB column, one chat module + client.

## 3. Tenancy — the load-bearing decision

Chat has **two** book ids in scope, and only one of them is trustworthy:

- `_ctx_book_id` — from the FE's `editor_context` / `book_context` / `studio_context`. **Client-supplied.**
  Today it is only used to render a prompt note, so nothing depends on it being real.
- `_gate_book_id` — `knowledge_client.resolve_book_id(user_id, project_id)`, resolved server-side from the
  session's knowledge project.

Neither is a *grant proof* (a project's `book_id` is itself user-supplied at project-create). So:

> **The capture route grant-checks `owner_user_id` against `book_id` with `GrantEdit`, server-side, on every
> call**, via the same `s.checkGrant` + `uniformOwnershipError` (anti-oracle) path every MCP write tool uses.
> Chat passes `_gate_book_id` (the server-resolved one), never `_ctx_book_id`.

An internal-token caller is *not* implicitly authorized to write into an arbitrary book. This is the one place
where copying the existing `/internal/books/{id}/extract-entities` posture (no grant check — it is called by
the worker on a job it already owns) would have been a tenancy defect.

## 4. Contract — `POST /internal/books/{book_id}/capture-canon`

Internal-token gated (`requireInternalToken`), like its siblings.

```jsonc
// request
{ "owner_user_id": "<uuid>",       // REQUIRED — grant-checked (Edit) against book_id
  "source_text":   "<the turn>",   // REQUIRED — treated as DATA, never instructions
  "model_ref":     "<uuid>",       // optional; omit → provider-registry resolves the user's planner/chat model
  "max_candidates": 12 }           // optional; server-clamped to [1, 24]

// 200
{ "created":  [{"name": "Ilyana", "kind": "character", "entity_id": "<uuid>"}],
  "skipped":  2,      // already exists, or previously rejected (ai-rejected tombstone)
  "failed":   0,
  "notes":    ["…anything the model could not map to a kind…"] }
```

- `403`/`404` collapse into the uniform ownership error (no existence oracle).
- `409 GLOSS_NO_KINDS` when the book has no ontology yet — honest, non-thrashing (mirrors WS-4A).
- The route performs **no** attribute writes on entities that already exist. `proposeNewEntity` short-circuits
  on `skipped_exists` before touching attributes, so capture can never mutate authored canon.

### Prompt flavour (why not reuse the doc prompt verbatim)

WS-4A's prompt says *"Extract EVERY distinct entity the notes describe."* — correct for a seed doc, wrong for
conversational prose, where it would harvest every common noun and flood the inbox (cf. the measured
`extraction-over-extracts-4x` lesson). The capture prompt instead demands:

- only **named** entities that the conversation **introduces or defines** — skip passing mentions, pronouns,
  generic nouns, and anything merely *referenced*;
- if nothing new is established, return `{"candidates": []}` — an empty capture is the expected common case.

Shared machinery (`parseDocExtraction`, ontology grounding, `safePromptField` neutralization, the one repair
round, the candidate cap) is factored into `extractEntityCandidates` and used by both callers.

## 5. The toggle — `knowledge_projects.canon_capture_enabled`

Per the **Settings & Configuration Boundary**: two users absolutely want different values here (it spends
their BYOK tokens), so it is a **user setting**, not an env flag.

| Tier | Value | Home |
|---|---|---|
| Deploy ceiling / kill-switch | `CHAT_CANON_CAPTURE_ENABLED` (default `true`) | chat `config.py` |
| Per-project user setting | `knowledge_projects.canon_capture_enabled` (default `true`) | knowledge DB, `PATCH /projects/{id}` |

`effective = AND(deploy_allows, project_enables)` — the ceiling narrows, it is never a per-user knob. Default
`true` mirrors the `tool_calling_enabled` precedent (a behaviour the user turns *off*), and capture is inert
anyway unless the project has a book. The effective value + the reason it did or didn't fire is **logged every
turn** (no silent hidden default — the "grounding always-on / reasoning silently-off" bug class).

Reaches chat on the already-existing `kctx` wire (`ContextResponse.canon_capture_enabled`), the same path
`tool_calling_enabled` takes. **Consumed, proven by effect:** a test asserts capture does not fire when the
project's flag is off, and does not fire when the env ceiling is off.

## 6. Firing conditions (all must hold)

1. the turn succeeded and produced assistant text;
2. `settings.canon_capture_enabled` (deploy ceiling) **and** `kctx.canon_capture_enabled` (project);
3. a **server-resolved** `book_id` exists for the session's project;
4. `assistant_message_count % CANON_CAPTURE_EVERY_N_TURNS == 0` (default 4 — the `_fire_executive_tick` cadence);
5. `len(user_text) + len(assistant_text) >= CANON_CAPTURE_MIN_CHARS` (default 200) — a "yes"/"ok" turn establishes nothing.

Then: `asyncio.create_task(_fire_canon_capture(...))`, best-effort, swallowing every exception — identical to
the sibling post-turn tasks. A capture failure must never surface after `RUN_FINISHED`.

**Cost.** One small LLM call every 4th turn, on the user's own model through provider-registry (so it is
metered and billed to them like any other call — glossary holds no key). Timeout `CANON_CAPTURE_TIMEOUT_S`
(90s); no retry (the next cadence tick is the retry).

**Dedup is glossary's job, not chat's.** Chat does *not* pre-filter against its known-entity token cache: that
cache is TTL-stale and name-only, whereas `proposeNewEntity` dedups by `(kind, name-or-alias, scope_label)`
inside the advisory-locked transaction. A chat-side filter would be a second, weaker, drifting dedup key.

## 7. Plan

1. **glossary (Go)** — factor `extractEntityCandidates` out of `toolExtractEntitiesFromDoc`; add the
   capture prompt flavour; add `capture_canon_handler.go` + the `/internal` route; tests (grant denial,
   no-kinds 409, create/skip/tombstone accounting, clamp, prompt-flavour selection).
2. **knowledge (Py)** — migration `canon_capture_enabled BOOLEAN NOT NULL DEFAULT true`; `Project` /
   `ProjectUpdate` / repo column list; serve it on `ContextResponse` from `full` / `static` / `multi_project`
   (multi-project = `any(...)`, matching `tool_calling_enabled`); tests.
3. **chat (Py)** — `KnowledgeContext.canon_capture_enabled`; `client/glossary_capture_client.py`;
   `services/canon_capture.py` (the gate + the call, unit-testable pure gate function); `config.py` settings;
   hoist `_gate_book_id` and spawn from the post-turn block; tests.
4. **VERIFY** — Go suite, chat + knowledge suites, `ai-provider-gate`, and a **live cross-service smoke**
   (real chat turn → real glossary → real BYOK model → a real draft row in the inbox). This spans 3 services;
   per the cross-service live-smoke rule, unit green alone is not evidence.

## 8. Acceptance — **ALL MET (2026-07-10)**

- [x] A turn that names new characters creates `draft` + `ai-suggested` entities in the existing inbox;
      re-running the same exchange creates nothing (`skipped=2`, zero duplicate names). *(live)*
- [x] A name the user **rejected** (tombstoned `ai-rejected`) is never re-proposed. *(live)*
- [x] Capture never mutates an entity that already exists — `proposeNewEntity` returns `skipped_exists`
      before it loads attribute defs, let alone writes one.
- [x] A caller without `Edit` on the book gets the uniform 403 — and gets it **before** the extractor runs, so
      naming someone else's book cannot spend their tokens.
      *(`TestCaptureCanon_NonGranteeDeniedBeforeAnyModelCall`, plus live: 0 rows written.)*
- [x] Capture does not fire when the project toggle is off, nor when the deploy ceiling is off, nor without a
      capture context; each blocks the **spawn** (not merely the return value) and names itself in the log.
- [x] A capture failure (glossary down, model down, timeout, bad body) returns `None` and never raises.
- [x] The in-flight task is strongly referenced until it completes (asyncio keeps only a weak ref).
- [x] Live cross-service smoke — chat's **real** `CanonCaptureClient` → glossary `:8211` → provider-registry
      `:8208` → LM Studio `gemma-4-26b`.

### Live verification (3 services, real BYOK model, $0)

Book `019dc729-…` (test account, ontology = one visible kind `character`, 0 entities):

| step | result |
|---|---|
| stranger (`019d4966-…`) captures | denied, **0 rows written**, no model call |
| owner captures a 2-name exchange | `created=[Ilyana Vosk, Marek Tallow]`, both `draft` + `ai-suggested` |
| re-capture the same exchange | `created=[] skipped=2`, **0 duplicate names** |
| reject `Ilyana Vosk`, re-capture | not re-proposed; still exactly 1 (inactive) row |

The model also declined to invent a `place` kind for "Grendlehaven", reporting it in `notes` — the ontology
grounding and the capture-flavour selection rule both worked on a real 26B local model.

## 9. Known limitations (conscious, not oversights)

1. **The tool-confirm RESUME path does not capture.** `resume_stream_response` rebuilds no knowledge context,
   so it has no resolved book id and passes `ctx=None` → `no_capture_context` (fail closed). Capture is
   cadence-based, so a resumed turn simply defers to the next tick. Resolving a book id there would add a
   knowledge round-trip to the resume path for no continuity gain.
2. **The deploy ceiling is invisible to the user (SET-4 gap).** If an operator sets
   `CHAT_CANON_CAPTURE_ENABLED=false`, a user's project toggle still reads `true` while nothing happens. Today
   the only observable is the per-turn log line (`fire=… reason=deploy_ceiling_off`). When the FE toggle lands
   it must show the **effective** value, not the stored one. Tracked as `D-WS4C-FE-TOGGLE`.
3. **No FE toggle yet** — `canon_capture_enabled` is PATCHable on `/projects/{id}` (it rides `response_model=Project`
   and the `_UPDATABLE_COLUMNS` allowlist) but has no settings UI, exactly like `save_raw_extraction`
   (`D-P2-FE-SAVE-RAW`). Same tracked row as above.
