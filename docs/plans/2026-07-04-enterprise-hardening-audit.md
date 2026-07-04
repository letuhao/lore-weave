# Enterprise Hardening Audit + Improvement Plan — 2026-07-04

> **▶ NEXT (this track's handoff — SESSION_HANDOFF's NEXT block is owned by a concurrent studio/KG track, so this doc is the enterprise-hardening system-of-record).** **P0 fully clear** (8/8). **P1 fully clear.** **P2 spec** authored + adversarially verified: [`docs/specs/2026-07-04-enterprise-p2-structural.md`](../specs/2026-07-04-enterprise-p2-structural.md). **P2·B1 (KEK sha256-derivation) ✅ SHIPPED** — clears `D-REVIEW-AESKEY-DERIVE`. **P2·A2a (Python shared logging) ✅ SHIPPED** (`687fd4949`, `aba652a86`, `e7dbef061`, `178858d51`, `7500db04e`): `loreweave_obs.setup_logging` + dual-emit `otel_trace_id` (closes the Python half of A1); 3 copied `logging_config.py` retired; all runtime `basicConfig` migrated + lint-enforced. **NEXT P2 items (recommended order):** A1 (Go slog span-injection + call-site sweep — the Go half of correlation-id) → B2 (route-parity test + retention row-delete sweeper) → C (notification dedup/outbox/FE-i18n) → D (latency SLO) → F (tenant-boundary audit, first-access-per-session) → E (salience↔learning, decision-first). **Open forks:** A2b (Go `contracts/logging` adopt-vs-retire — CLARIFY needed); chat-service partial-tier logging adoption (tail).

**Status:** AUDIT RECORDED — execution in progress. **Done 2026-07-04 (parallel fan-out):** P0-1/P0-3/P0-4/P0-5/P0-7/P0-8 fixed (`a7ebdb9d4`); P0-6 gitleaks-all-branch + dep-vuln CI + dependabot wired; **P1 enforcement lints built + advisory-wired** (timeout→Python, pagination-cap, blocking-in-async, raw-sql, injection-coverage, language-bias-gate, sdk-duplication-gate — each baseline-seeded so it passes on current code + flags NEW violations). **Remaining (sequenced serially):** ~~P0-2 streaming/embed logging rework~~ (✅ audit-ledger closed `ebff3448f`+`09f1d989e`; structural residual → P2); the big SDK creations + 14-service JWT/logging migrations; notification/correction envelope contracts; edge rate-limit; flip advisory lints → blocking after backlog burndown. **P0 is now fully clear** — all 8 live defects resolved (2026-07-04).
**Scope:** LLM-call logging · general logging · security · performance · notification · analytics/learning
**Method:** 6 parallel investigation sub-agents, code-grounded. This doc is the **record of findings + the prioritized backlog**; the governing rules extracted from it live as enforceable standards under [`docs/standards/`](../standards/README.md).

> **How to use:** the P0 rows are live defects (No-Defer-Drift = fix-now when scheduled). P1 = build the enforcement gates that give the standards teeth. P2 = structural improvements. Each standard doc (`docs/standards/<area>.md`) states the *rule*; this doc states the *current gap + the work to close it*.

---

## The cross-cutting thesis (why everything looks the same)

Across all six areas the pattern is identical:

> **The apparatus almost always EXISTS — often at enterprise grade — but is not governed by a standard, so the good implementation isn't adopted fleet-wide; cross-service contracts aren't frozen, so they drift and silently drop; and enforcement is narrow — Go/Rust-only, warn-mode, unwired from pre-commit, MMO-scoped, or presence-only.**

Evidence: `contracts/logging` (PII-aware, typed) has **0 adopters** (the fleet uses bare `slog`); the SSRF-safe client exists only in `agent-registry-service`; the hardened `adminjwt` verifier is admin-only (platform user JWT is copy-pasted per service); `learning-service`/`statistics-service`/`notification-service` **all exist and run** yet the CLAUDE.md service table lists only **12 of 46** services (the root of the "these don't exist" confusion).

**Doc defect to fix first:** the CLAUDE.md "Services" table is a stale curated subset. Either complete it to all 46 or mark it explicitly as a subset and point to the authoritative map (`contracts/language-rule.yaml` + `docs/ARCHITECTURE.md`).

---

## Area 1 — LLM / provider call logging  → standard: [`llm-call-logging.md`](../standards/llm-call-logging.md)

**Current state:** three disjoint paths. Async jobs (~80% instrumented: `llm_jobs.input/.result` plaintext JSONB + truncated 16KB encrypted copy in `usage_logs`). Streaming chat + sync embed/rerank/web-search: essentially unlogged.

**P0 fix-now bugs (live defects):**
- **B3 read-back returns empty `{}`** — `usage-billing` stores the payload as a JSON *string* (`truncatePayload`→string) but `getUsageLogDetail` (`services/usage-billing-service/internal/api/server.go:584-607`) `json.Unmarshal`s into a `map[string]any` → fails → returns `{}`. *Every encrypted async-job payload reads back empty.* A round-trip test would have caught it.
- **B1 streaming chat stores no readable I/O** — `services/provider-registry-service/internal/api/stream_handler.go:324-330` writes stub `Input:{"stream":true}`; `stream_billing.go` `RecordUsage` payload carries only tokens/cost. Prompt + completion (and the assembled system+RAG prompt) persist **nowhere** in the gateway/billing plane.
- **B2 streaming records nothing on the unhappy path** — `stream_billing.go:203` gates the `/record` write on `op=="chat" && !aborted && finalUsage!=nil`; aborted/disconnected/no-final-chunk streams produce zero rows.
- **B4 sync embed/rerank/web-search unlogged** — `internalEmbed`/`internalRerank`/`internalWebSearch` in `provider-registry server.go` call no record path (`recordInvocation:2740` is dead code). No cost, no tokens, no I/O.
- **🔴 Key-management defect** — payload-encryption "master key" = `JWTSecret` truncated/padded to 32 bytes (`usage-billing server.go:36-44`); `payload_encryption_key_ref` is a UUID referencing nothing. Rotating `JWT_SECRET` → all payloads permanently undecryptable; leaking it compromises auth **and** all logged prompts. No rotation.
- **B5 short retention** — full-fidelity plaintext lives on `llm_jobs.input/.result` with `expires_at = now()+7d` (`provider-registry migrate.go:145`); after the sweep only the (B3-broken) encrypted copy remains → unrecoverable after 7 days.
- **Encryption inconsistency** — `usage_logs` AES-256-GCM encrypted; `llm_jobs` plaintext JSONB **and** payloads plaintext on the Redis wire (`usage_relay.go:149-152` acknowledges this). **No redaction anywhere** (BYOK secrets + PII stored verbatim).
- **Correlation gap** — no single `trace_id` tying a chat turn → the N LLM calls → the usage rows; `trace_id` is caller-optional; the SDK (`sdks/python/loreweave_llm/client.py`) is transport-only.

**P1 enforcement:** route ALL provider calls (streaming + sync) through the *same* finalize→outbox→usage→`writeUsageLog` chokepoint; extend `scripts/ai-provider-gate.py` with a rule "a provider-invoking handler not routing through the logging chokepoint = defect"; a **round-trip decrypt test** (write payload → `getUsageLogDetail` → assert equality); a dedicated `LLM_PAYLOAD_ENCRYPTION_KEY` env (fail-to-start, distinct from `JWT_SECRET`).

---

## Area 2 — General logging  → standard: [`logging.md`](../standards/logging.md)

**Current state:** three competing idioms, not "no standard." **Go:** `contracts/logging` (typed PII/Sensitive + Redactor + prod-guard, **0 adopters**) vs `slog` JSON (the whole 17-service fleet) vs raw `log.Printf` (glossary panic recoverer). **Python:** 3-tier spectrum — Full (`logging_config.py` copy-pasted ×3: knowledge/composition/lore-enrichment) / Partial (chat, learning: OTel but unstructured root) / None (`basicConfig` plain text: translation, worker-ai, campaign, jobs, video-gen — the hot-path LLM workers are in the worst tier). **TS:** NestJS Logger ∪ `console.*` (6 raw). **Frontend:** 26 `console.*`.

**Structural gaps:**
- Two unreconciled correlation-id namespaces: OTel W3C `traceparent` (spans) vs bespoke `X-Trace-Id` uuid-hex (`glossary-service/internal/api/trace_id.go`). **Go logs carry no trace_id** → Loki logs and Tempo traces don't join.
- Source-side redaction essentially absent (3 Python services, 2 regexes; Go: 0). Only broad redaction is the Vector *ingest* scrubber (`infra/vector/scrubber_patterns.yaml`) — a single point whose prod deployment is unconfirmed and which is "strictly weaker than typed-source redaction."
- `logging_config.py` is copy-pasted, not a shared SDK → guaranteed drift.
- **Bright spot:** audit logging is the most mature area — append-only scrubbed `*_audit` meta tables (`migrations/meta/{013,015,016,018}`) with `error_detail_raw_hash` + `error_detail_scrubbed` + CHECK constraints + `contracts/meta/scrubber.go` (no raw-string accessor). Gap: no audit contract covers **domain tenant-boundary crossings** (book/glossary cross-tenant reads emit nothing).

**P1 enforcement:** pick ONE idiom per language (recommend: fleet's `slog`/`pythonjsonlogger` + a shared helper that injects span-context trace_id + a Redactor); promote `logging_config.py` → `sdks/python/loreweave_obs.setup_logging()`; **revive+fix+flip+wire `scripts/logging-discipline-lint.sh`** (currently warn-mode, unwired, premise contradicts the fleet) to error-mode in pre-commit + CI, extended to catch `console.*`, `basicConfig`-plain, missing-`setup_logging`, missing-trace-id.

---

## Area 3 — Security  → standard: [`security.md`](../standards/security.md)

**Current state:** two inverted regimes — the MMO/foundation meta layer is heavily governed (15 CI lints, RS256 `adminjwt` adversarially tested, PII/KMS crypto-shred) but much has no running code; the **main platform is convention + per-service tests**. The one platform-wide enforced control is **gitleaks** secret scanning.

**P0 — genuinely UNPROTECTED:**
- **No HTTP edge rate limiting** at `api-gateway-bff` (no throttler/helmet/security-headers). Only auth-service's in-process limiter guards login; chat/knowledge/LLM/MCP endpoints have none. DDoS/abuse exposure.
- **chat-service splices book/graph content into LLM prompts without `neutralize_injection`** — the detector (`sdks/python/loreweave_grounding/sanitize.py`) is used in knowledge + lore-enrichment but **chat-service is the hole**; it relies on a prompt-convention string + human gate only.
- **No dependency vulnerability scanning anywhere** — no dependabot/trivy/snyk/govulncheck/pip-audit/npm-audit/cargo-audit. Supply-chain CVEs invisible. (`dep-pinning-lint.sh` pins lockfiles — integrity, not vuln.)
- **gitleaks branch-coverage hole** — runs only on `main`/`mmo-rpg/**` PRs, not `feat/*`, not pre-commit; a secret lives uncaught on a feature branch until its merge PR.
- **No auth-failure / tenant-boundary security audit log** on the main platform.

**Under-protected (correct by convention, no gate):** SQL parameterization is uniformly correct (audit found no injectable query) but nothing stops the next `Sprintf("...WHERE x='%s'", userInput)`; PII classification + crypto-shred are MMO-meta-only (platform user PII has no tags/erasure/retention); platform user JWT validation is duplicated per service (not a shared hardened path like `adminjwt`); two disjoint key schemes with no rotation for the provider-registry AES-GCM key.

**Enforced + good (keep):** BYOK creds AES-GCM at rest (`provider-registry server.go:999`), SSRF resolve-then-connect (`agent-registry probe.go`), 404-anti-oracle (book-service, tested), auth rate-limit (in-process), admin RS256 (adversarially tested), prompt-injection detector.

**P1 enforcement:** gitleaks on `**` + pre-commit; dependency vuln scanning (govulncheck/pip-audit/npm-audit/cargo-audit + `.github/dependabot.yml`); semgrep; new lints — raw-SQL/unparameterized, missing-authz/anti-oracle, injection-coverage (every LLM-prompt feed routes through `neutralize_injection`), pii-classify extended to `services/*/migrations/`, secret-required-config; shared JWT-verifier adversarial test suite (template: `contracts/adminjwt/adminjwt_test.go`); edge rate-limit at the gateway.

---

## Area 4 — Performance  → standard: [`performance.md`](../standards/performance.md)

**Current state:** strong apparatus but MMO/foundation-scoped + Go/Rust-only + mostly advisory for the platform. Enforced-and-real: `timeout-discipline-lint.sh` (Go/Rust, CI-blocking) + `capacity-budget-lint.sh` (presence-only). Everything richer (breaker/cache/latency/load) is MMO-scoped or advisory.

**Gaps:**
- **Language asymmetry** — the one enforced runtime rule (timeout) is Go/Rust-only, yet the latency-heavy services (chat, knowledge, translation, composition) are **Python**, and the highest-risk calls (LLM/embed/rerank) are entirely unlinted.
- Resilience contract (`contracts/dependencies/matrix.yaml`) + cache registry (`contracts/cache/keys.yaml`) are real but **exclusively MMO** — no main-platform dep or cache key registered; `dependency-registry-lint` is warn-only.
- **No DB-perf guardrail** — no N+1 detection, no "list endpoints must paginate+cap" lint (the `parseLimitOffset` clamp + `limit le=100` were reactive bug-patches), no index review.
- **No platform latency SLO** (DP-T tier latency contracts stop at the MMO boundary).
- Load/regression testing is hot-path micro-bench only + advisory; no e2e latency gate on any user HTTP surface.
- **No blocking-in-async lint** despite the documented bug class (the kg_unify `asyncio.to_thread` fix).

**P1 enforcement (most machinery exists to copy):** extend `timeout-discipline-lint.sh` → Python (httpx/aiohttp/asyncpg without timeout); `pagination-cap-lint`; `blocking-in-async-lint`; register main-platform deps in `matrix.yaml` + flip `dependency-registry-lint` → error; a `contracts/slo/latency.yaml` SoT + presence/shape check + wire p95 assertion into perf-nightly; k6 smoke against real platform HTTP endpoints (advisory → blocking on the non-noisy top-level latency check).

---

## Area 5 — Notification  → standard: [`notification.md`](../standards/notification.md)

**Current state:** `notification-service` (Go/Chi, `loreweave_notification`) EXISTS but has **no shared envelope contract** — wire shapes are copy-pasted/divergent across 4 producers (translation, composition, auth, provider-registry).

**P0 fix-now bugs:**
- **`mcp_approval` silently dropped** — `auth-service/internal/api/mcp_approvals.go:401` posts `category:"mcp_approval"` but `notification-service server.go` `validCategory` allows only `{translation, social, wiki, system}` → 400 → fire-and-forget goroutine swallows it → the approval-pending notification is **never persisted**.
- **Consumer bypasses validation** — the AMQP consumer inserts `category:"llm_job"` via raw SQL, bypassing `validCategory` (a category the API would reject exists in the table).
- **i18n payload discarded** — translation sends `i18n_key`+`params` but the table has no such columns and `createNotification` ignores them (localization Phase 2 half-built).

**Delivery defects:** HTTP-ingest producers are fire-and-forget-swallow (lost forever if the service is down; no outbox); the AMQP consumer is at-least-once but the `notifications` table has **no dedup key** → requeue creates duplicate rows; `NoopNotifier` silently drops when `RABBITMQ_URL` unset; two live transports (SSE + `/ws`) for one concept; only `llm_job` events reach live-push (translation/composition/approval are persist-only). No user opt-out; no PII discipline on notification bodies.

**P1 enforcement:** `contracts/notifications/envelope.{go,yaml}` (one versioned schema + Go+Python mirrors, killing the copy-pasted `TerminalEvent` struct) — model on `contracts/alerts/envelope.go`; category = single-source enum enforced on **every** ingress; producer-side transactional outbox + `(user_id, dedup_key)` unique; consumer contract test + a handler-coverage test (every emitted event type has a registered handler).

---

## Area 6 — Analytics & Learning  → standard: [`analytics-and-learning.md`](../standards/analytics-and-learning.md)

**Current state:** both `statistics-service` (Go, `loreweave_statistics`) and `learning-service` (Python, `loreweave_learning`) EXIST and run.
- **Statistics: LOW fragmentation** — one owner, event-sourced; book-service already migrated off local stats (`analytics.go:206` "Deprecated: book stats now served by statistics-service"). Only real ambiguity: "usage metrics" appears in both statistics-service and usage-billing-service descriptions (engagement vs USD spend — distinct axes, no shared tables).
- **Learning: MODERATE-HIGH fragmentation** — TWO independent loops that don't know about each other: (a) `learning-service` = cross-service eval/quality flywheel fed by ~14 correction event types from 5 producers; (b) `knowledge-service` salience (`app/context/selectors/salience.py`) = in-service adaptive ranking with its own `feedback_weight` **not** sourced from learning-service's quality signal. Plus the correction "capture" logic is re-implemented per producer (chat/composition/translation/glossary/knowledge) with **no single correction-event contract** → a producer drift fails silently at the consumer (`learning-service` `build_dispatcher()` registers a handler per event name; an unregistered/renamed event is silently ignored).

**P1 enforcement:** freeze the producer→statistics event payload contract (`book.viewed`, `reading.progress`, `chapter.translated`, `voice.turn`, …) + a consumer field-assertion test; a single correction/feedback event contract (required fields + redact-by-default hash-not-raw + idempotency key) every producer conforms to; a **no-silent-drop wiring test** asserting every emitted correction event type has a registered `build_dispatcher` handler (the Agent-Extensibility "no-silent-no-op" rule applies verbatim). Codify "statistics has one owner; other services emit outbox events, never store their own aggregates" so book-service's migration can't regress. Document the two-loop boundary + decide whether salience `feedback_weight` should eventually source from learning-service.

---

## Area 7 — Multilingual / language-bias  → standard: [`multilingual.md`](../standards/multilingual.md)

**Current state:** substantially multilingual-aware (a shared NFKC+casefold+CJK-fold spine, mirrored Go+Python parity-tested; a per-language pattern registry; a genuinely multi-language injection sanitizer en+zh+ja+ko+vi; CJK-aware chunkers) — but English-first rule logic recurs and the good patterns are applied inconsistently.

**Bias sites (backlog):** 🔴 **A1** intent classifier 100% English keywords (`knowledge-service/app/context/intent/classifier.py`, live L3 retrieval path → zh/ja/ko/vi get no intent routing) · 🔴 **A6** `ensure_ascii=True` in `translation-service/app/broker.py:91,103` (trivial fix; wire bloat) · **A2** proper-noun `[A-Z][a-z]+` (`selectors/glossary.py:72` — fails vi diacritics/ja kana/ko hangul) · **A5** honorific-strip list English+romanized only, no native 大人/님/様 (`canonical.py:41` — load-bearing for the dedup id) · A3 English-only stopwords · A4 English negation object-slot · FE i18n 4-locale hardcoded (~93 manual imports; `fallbackLng:'en'`; extensions feature has English literals bypassing `t()`) · notification titles English-concat + no i18n columns · `SUPPORTED_LANGUAGES=5` → English fallback; translation target defaults `"en"`. Moderation: no in-repo wordlist (provider-delegated). **P1 enforcement:** `scripts/language-bias-gate.py` + a multi-language golden-fixture set (corpus has 0 ja / 0 ko despite both first-class) + normalization parity tests.

## Area 8 — SDK-first / reuse-violations  → standard: [`sdk-first.md`](../standards/sdk-first.md)

**Current state:** a strong SDK layer exists (`loreweave_{llm,extraction,grounding,grants,obs,mcp,jobs}` + Go mirrors) with target-shape examples (`loreweave_grants` "extracted from 3 byte-identical copies"; `loreweave_obs`). But major copy-paste remains, and 3 shared modules are **orphans** (0 importers: `contracts/logging`, `contracts/errors`, `client_factory.go`).

**Reuse-violations (backlog):** `logging_config.py` byte-identical ×3 · `trace_id` middleware ×5 · **platform JWT verifier re-implemented 6× Python + 8× Go** (no shared user-JWT verifier; only admin `contracts/adminjwt`) · notification `TerminalEvent` struct duplicated · drifted HTTP client wrappers (book/embedding/glossary) · config `Settings` boilerplate ×10. **P1 enforcement:** near-duplicate CI detector + symbol-level grep-gate (`jwt.ParseWithClaims`/`RedactFilter`/`TerminalEvent` outside `sdks/`/`contracts/`) + adoption check (orphan module = red). **SDKs to create:** `loreweave_logging`, `loreweave_authn`, `contracts/platformjwt`, shared `TerminalEvent`, `BaseInternalClient`.

## Areas 9–10 — scope-separation + user-data-scope
Design standards (no investigation defects): [`scope-separation.md`](../standards/scope-separation.md) (one data/logic owner per concept; cross-service via contract; SSOT-vs-derived) + [`user-data-scope.md`](../standards/user-data-scope.md) (classify user data C1–C6 → scope key + protection profile). Both compose existing rules (tenancy, PII, encryption, DB-per-service) into explicit design-time gates.

## Consolidated prioritized backlog

### P0 — live defects (fix-now when scheduled; each is a bug, not a standard)
| ID | Defect | File |
|---|---|---|
| P0-1 | LLM payload read-back returns empty `{}` (string-vs-map type mismatch) | `usage-billing server.go:584-607` |
| P0-2 | ✅ Streaming chat + embed/rerank/web-search log no I/O | `provider-registry stream_handler.go`, `server.go internalEmbed/Rerank` |
| P0-3 | Payload encryption key = `JWT_SECRET` (rotation/leak catastrophe) | `usage-billing server.go:36-44` |
| P0-4 | Notification `mcp_approval` silently 400-dropped | `auth mcp_approvals.go:401` × `notification-service validCategory` |
| P0-5 | chat-service feeds book/graph into prompts without `neutralize_injection` | `chat-service knowledge_skill.py` |
| P0-6 | gitleaks not on `feat/*` / not in pre-commit; **pre-commit hooks not active** (`core.hooksPath=.git/hooks`) | `.githooks/pre-commit`, `foundation-ci.yml` |
| P0-7 | intent classifier 100% English keywords (zh/ja/ko/vi get no retrieval routing) | `knowledge-service/app/context/intent/classifier.py` |
| P0-8 | `ensure_ascii=True` inflates CJK on the event wire (trivial one-line fix) | `translation-service/app/broker.py:91,103` |

### P1 — enforcement gates (give the standards teeth; "full enforcement")
Extend `timeout-lint`→Python · `pagination-cap-lint` · `blocking-in-async-lint` · flip `dependency-registry-lint`→error (after registering platform deps) · revive+flip+wire `logging-discipline-lint` · gitleaks all-branch + `.github/dependabot.yml` + govulncheck/pip-audit/npm-audit/cargo-audit · raw-SQL lint · injection-coverage lint · pii-classify→`services/*/migrations/` · LLM-logging chokepoint gate (extend `ai-provider-gate.py`) + round-trip decrypt test · `contracts/notifications/envelope` + consumer contract test · correction-event contract + no-silent-drop wiring test · shared JWT-verifier adversarial suite · edge rate-limit · **`language-bias-gate.py` + multi-language golden fixtures (ja/ko)** · **SDK near-duplicate detector + symbol-level grep-gate + orphan-adoption check** · create `loreweave_logging`/`loreweave_authn`/`contracts/platformjwt`/shared-`TerminalEvent`/`BaseInternalClient`.

### P2 — structural improvements
Unify the two correlation-id namespaces (OTel-only) · shared logging SDK per language · dedicated `LLM_PAYLOAD_ENCRYPTION_KEY` + rotation · **LLM-logging route-parity test (Route A inline-HTTP + Route B outbox both → `writeUsageLog`; outbox-unification out of scope — HTTP paths have no tx) + `llm_jobs` retention row-delete sweeper (P0-2 structural residual)** · notification outbox + dedup + opt-out + i18n columns + SSE/WS unification · latency-SLO SoT · salience↔learning-service feedback integration · platform-tenant-boundary audit log · fix CLAUDE.md service table (12→46).

**Full P2 spec:** [`docs/specs/2026-07-04-enterprise-p2-structural.md`](../specs/2026-07-04-enterprise-p2-structural.md).

---

## Notes
- The MMO/foundation track already contains best-in-class implementations of most of these (typed logger, KMS crypto-shred, resilience matrix, SSRF client, adversarial JWT tests). Much of P1/P2 is **"point the existing enterprise machinery at the product services"**, not build-from-scratch.
- Ordering suggestion: P0-6 (activate pre-commit + gitleaks all-branch) is a one-liner with outsized value; P0-1..P0-5 are cheap root-cause-clear bugs; then P1 gates top-down by leverage (timeout→Python + logging-lint + dep-scanning first — most machinery to copy).

---

## `/review-impl` pass over the P0/P1/JWT commits (2026-07-04)

A 3-reviewer cold-start adversarial review of `a7ebdb9d4`+`ebff3448f`+`6a60e3b0c`+`6edfdae7d`. **8 findings fixed-now** (JWT Go↔Python `aud` parity drift + the same flaky last-char tamper test in BOTH suites; usage-billing KEK-rotation keyring `LLM_PAYLOAD_ENCRYPTION_KEYS_RETIRED` + dead `encryptPayload` removed; provider-registry sync embed/rerank/web_search now record failures too via a `status` param + the streaming completion is `boundedPayload`-capped; chat evaluate.py — the THIRD `build_context` consumer — now deep-neutralizes the judge prompt; injection_defense docstring made accurate). Verified: platformjwt `go test` + 27 authn pytest, usage-billing + provider-registry full Go suites, chat 14 injection + 28 eval tests.

## JWT-verifier migration → `contracts/platformjwt` / `loreweave_authn` (2026-07-04)

Fan-out of 13 per-service agents (disjoint files, self-verify, no-commit) + serial QC integration. **10 MIGRATED, 3 FLAGGED** (flag-don't-force caught a real authz issue rather than force-fitting).

**Migrated (10):** Go → `platformjwt.Verify` — book, glossary, notification, sharing. Python → `loreweave_authn.build_get_current_user` — chat, composition, knowledge, learning, campaign, jobs. Each preserved the outer verifier's signature/return-type (str vs UUID via `return_subject`), 401 path, and public symbol names; dead `accessClaims`/`import jwt` removed. The SDK's two hardenings (exp-required, sub-must-be-UUID) required fixing a handful of test fixtures that minted bare/non-UUID-sub tokens (composition `_bearer()` lacked exp → optional dep silently dropped identity — caught by the agent).

**QC caught two things unit tests alone would miss:**
- **Dockerfile build-break:** the Go `replace => ../../contracts/platformjwt` only resolves at image build if the Dockerfile COPYs it into the repo-root build context. glossary's agent added the `COPY`; book/notification/sharing did NOT (local `go build` passed regardless) → I added `COPY contracts/platformjwt` to all three. **Rule for the next Go SDK adoption: a new `replace` needs a matching Dockerfile COPY, or the image build fails while local tests stay green.**
- **Uniform-401 behavior change:** the SDK collapses expired/invalid/malformed → a single terse `"invalid token"` 401 (anti-oracle). Verified NO frontend branches on the `"expired"` detail string (the client-side `tokenExpired()` decodes `exp` locally; the `token_expired` FE outcomes are the 422 confirm-token flow; `useJobsStream` treats expired==invalid==terminal). Safe.

Verify at QC: Go book/glossary/notification/sharing full `go test ./...` green; Python chat 920 · composition 1491 · knowledge 3505 · learning 186 · campaign 182 · jobs 97. `sdk-duplication-gate` baseline shrunk 27→19; provider-gate clean.

**`/review-impl` (3 cold-start adversarial reviewers, Python-drift / Go-drift / knowledge-dual-mode+fixtures): no HIGH/MED — migration sound.** Verified: return-type (str/UUID) matches every caller per service; `optional`/None-semantics preserved (only composition had one); exp-required breaks nothing (all 3 auth-service mint sites set `exp`); knowledge `kg_actions` dual-mode is a mutually-exclusive `if x_internal_token:`-first branch so `verify_access_token`'s `InvalidAccessToken` can't escape the fallback; no test-fixture weakened (rejection tests kept, detail-string asserts *tightened* to the anti-oracle `"invalid token"`); real verifier still exercised (not `dependency_overrides`-bypassed). Findings: **F1 (LOW, accepted)** — chat/campaign/jobs/learning missing-header status normalizes 403→401 (SDK `HTTPBearer(auto_error=False)`); the FE keys refresh/logout on `401 && init.token`, and a tokenless request has no `init.token`, so nothing branches on the change — it's strictly more correct + aligns with composition/knowledge. **F2 (INFO)** — chat/campaign/learning also lost a latent 500 (`data["sub"]` KeyError → clean 401). **Fixed:** added `notification-service` `TestRequireUserID` (accept + 7 reject modes) — it was the one migrated verifier with zero direct coverage (pre-existing gap).

### `D-JWT-ROLE-GATE` — ✅ RESOLVED 2026-07-04 (adminjwt RS256, user chose option a)
The 3 flagged services now gate their admin endpoints with the RS256 admin token (`contracts/adminjwt`, glossary's `requireAdminScope` pattern) and verify the user JWT via `contracts/platformjwt` (dead `role` claim dropped). Per-service: **provider-registry** (reference impl) — 3 platform-model write endpoints → `requireAdminScope(admin:write)`; **usage-billing** — `adminListUsage` + `createReconciliation` → same; **agent-registry** — `authorizeRowWrite` System branch + `requireAdmin` (ingest) + `canWritePlugin` → `requireAdminScope`; the ingest routes (the one path with a real FE caller) are admin-reachable E2E. Each: `ADMIN_JWT_PUBLIC_KEY_PEM` config (fail-closed 503 when unset), go.mod + Dockerfile wired for adminjwt+platformjwt, `newAdminTestServer` (RS256 mint) + admin-guard tests asserting 503/401/403/gate-pass. compose passes `ADMIN_JWT_PUBLIC_KEY_PEM` to all 3. `sdk-duplication-gate` baseline 19→13 (6 JWT verifier copies retired; only auth-service the minter remains). Verify: all 3 full `go test ./...` green; provider-gate + sdk-dup clean.

**Follow-up `D-AGENTREG-SYSTEM-WRITE-ADMIN` (gate #2 — structural, no current caller):** agent-registry's MULTI-tier create/patch/delete handlers authenticate the user with `requireUser` (HS256) *before* the tier is known, so an admin's RS256 token can't reach the System-tier branch (one request carries one Bearer token) — System-tier create/patch/delete via those endpoints is fail-closed-and-unreachable. No regression (System skills are SQL-seeded via migrate.go; the FE never POSTs `tier:system`; the pre-fix state was also locked, just with a misleading 403). Fixing = branch the multi-tier handlers to authenticate by *target* tier (RS256-only for System, HS256 for user/book) — a per-handler restructure with no consumer today. Admin System writes that DO have a caller (ingest) already work. **When fixed, also update `proposals.go` `approveProposal`'s System-target update audit (currently hardcodes `actor_kind="user"` — correct for the only reachable, user-tier case today, but would mis-record once a System-tier proposal-approve becomes reachable).**

<details><summary>Original finding (pre-resolution)</summary>
`agent-registry`, `provider-registry`, `usage-billing` were NOT migrated: each reads a custom `role` claim off the **user** token (`accessClaims{ RegisteredClaims; Role }`) to gate admin-only endpoints (`role != "admin" → 403`). `platformjwt.AccessClaims` is deliberately minimal (no role — that's the admin token's job). **Root-cause dug in QC:** `auth-service.SignAccess` mints the user access token with only `sid`+`sub`+`iat`+`exp` — **it never sets `role`.** So in production `claims.Role` is always `""` and these admin gates 403 EVERY caller (reachable only by hand-crafted test tokens). This is a pre-existing authz gap the migration surfaced. **Decision needed (gate #2 — structural, needs a design call):** either (a) route these admin endpoints through the RS256 admin token (`contracts/adminjwt`, which DOES carry role/scope), or (b) if they were never meant to be admin-gated this way, remove the dead role check; then migrate the user-JWT half to `platformjwt`. Do NOT mechanically swap while the role gate stands.
</details>

### Deferred findings (each earns its gate row)
| ID | Finding | Gate | Trigger |
|---|---|---|---|
| `D-REVIEW-EMBED-AUDIT-COST` | Sync **embed** audit `usage_logs` row omits `TotalCostUSD` → flat-rate fallback over-counts free-local embeds / under-counts cloud. Audit-only (spend is enforced by the guardrail reserve, not this row). | #2 — needs embed-pricing resolution plumbing (the embed handler doesn't fetch pricing JSONB today) | when the sync paths get pricing resolution, or a billing-report accuracy pass |
| ~~`D-REVIEW-AESKEY-DERIVE`~~ ✅ **RESOLVED 2026-07-04** (P2·B1) | `usage-billing` now `sha256`-derives the KEK when the value carries a `sha256:` marker, keeping the legacy pad/truncate for unmarked keys — **version-gated per key, no re-encrypt migration** (the audit doc's "orphans every row" concern was mooted: decrypt is try-all, no key-id routing). Rotation runbook documented on the config field; money-test proves differing >32-byte tails no longer collide. | — | resolved |
| `D-REVIEW-DECRYPT-STATUS` | `getUsageLogDetail` returns 200 + `null` payloads on a decrypt FAILURE, indistinguishable from a genuinely-empty payload, on an audited endpoint. | #2 — adds a response field; must check the FE usage-log-detail consumer first | next usage-log-detail contract change |
| `D-REVIEW-VOICE-INJECT-TEST` | Voice injection-defense splice (`voice_stream_service.py:339,348-349`) has no regression test (code is correct + symmetric with the fully-tested text path). | #2 — needs a voice STT/TTS test harness that doesn't exist yet | when a voice test harness is built |
| `D-REVIEW-SANITIZER-ROLE-COLON` | Shared `loreweave_grounding.sanitize` `role_colon_prefix` over-tags legit transcript memory (`User:`/`System:` lines) with `[FICTIONAL]`. | #2 — a shared-SDK regex change; a stronger anchor (line-start) risks weakening injection detection → needs its own review | a sanitizer-precision pass |
| `D-REVIEW-SANITIZER-SPAN-PRECISE` | On a hit, the WHOLE block is NFKC-folded (from the prenormalized text), not just the flagged spans — legit content in a flagged block is normalized. (Docstring now states this accurately.) | #2 — span-precise splice-into-raw is a structural SDK enhancement | same sanitizer-precision pass |
| `D-REVIEW-NOTIF-POISON-TEST` | No delivery-level test for the notification consumer's poison-category `Nack(false,false)` no-wedge branch. | low value — the branch is currently unreachable-by-construction (`transformTerminalEvent` hardcodes `llm_job`); the guard itself is correct | if the consumer's category becomes dynamic |
| `D-LANGBIAS-COMPACTION-LOWER` | `chat-service/compaction.py:145` `k = term.lower()` (proper-noun dedup key) is baselined in `language-bias-gate` so the gate could flip to BLOCKING. Symmetric dedup key (low-risk: CJK is a lower() no-op, Latin folds symmetrically), owned by the context-budget track. | low — a `.casefold()`/`name_normalize` swap; not corrupting today | context-budget track, or a language-bias cleanup pass |

### `P0-2` — ✅ RESOLVED 2026-07-04 (audit-ledger closed; structural residual → P2)
The **live defect** (streaming chat + sync embed/rerank/web-search persisting no readable I/O; the unhappy path recording nothing) is closed and committed (`ebff3448f` P0-2 + `09f1d989e` review-impl), verified green (provider-registry + usage-billing `go build`/`go test` 2026-07-04). Code-grounded state map:
- **B1 (readable I/O) — DONE.** Streaming assembled prompt captured post-injection (`stream_handler.go:427` `guard.captureRequest(boundedPayload(input))`) + completion accumulated from deltas (`stream_billing.go:152`), shipped with cost+tokens via `RecordUsage` → `/record` → `writeUsageLog` (encrypted `usage_logs`/`usage_log_details`, idempotent on `request_id`).
- **B2 (unhappy path) — DONE.** `settle` fires via `defer` on every terminal exit (completion/abort/upstream-error/disconnect, `stream_handler.go:299`); the record gate is now only `op=="chat"` (`stream_billing.go:250`) with `finalizeOutcome` classifying success/aborted/cancelled/provider_error + a delta-estimated tally fallback when no final usage chunk arrives.
- **B4 (sync embed/rerank/web-search) — DONE.** Shared `recordSyncUsage` (`server.go:2785`) records **success + failure** with bounded real I/O for all three ops.
- **B5 (7-day plaintext retention) — catastrophe MOOT, residual → P2.** The original "unrecoverable after 7 days" depended on B3 (encrypted read-back broken); **B3 = P0-1 is fixed**, so the durable encrypted `usage_logs` copy is now recoverable after the plaintext `llm_jobs` row expires. What remains is a **retention-policy + PII decision** (there is no implemented sweeper today — plaintext currently accumulates un-purged; `migrate.go:145` default `now()+7d`), not a data-loss bug — see `P2` below.

**Accepted residuals (no live defect):**
- **B1 observability stub** — the cancellation-registry `llm_jobs` row still writes `Input:{"stream":true}` (`stream_handler.go:330`). **Accept-and-document:** that row is billing-neutral (`reservation_id` NULL); the audit I/O lives (encrypted) in `usage_logs`. Keeping the real prompt OUT of this plaintext row is *desirable* (less plaintext-PII sprawl), so this is intentional, not a hole.
- **Sync ops flat-cost** — `recordSyncUsage` leaves `TotalCostUSD` unset → usage-billing's flat fallback. Already tracked as `D-REVIEW-EMBED-AUDIT-COST` (needs embed-pricing resolution plumbing).
- **Chokepoint not literally unified** — streaming + the 3 sync ops reach the shared `writeUsageLog` SQL writer via inline `RecordUsage` HTTP (Route A), while async jobs use `finalize→outbox` (Route B). Both converge on the same writer so the ledger-integrity goal is met; collapsing the two routes into one is a **structural refactor → P2** (LLM-logging-chokepoint item), not a defect.

**P1 envelope contracts (2026-07-04):** `contracts/notifyevent` shared `TerminalEvent` (killed the notification↔provider-registry cross-service struct dup; sdk-dup baseline 13→11) + learning-service `correction_contract.py` (`CORRECTION_EVENT_TYPES` SoT + `build_dispatcher` startup fail-fast + no-silent-drop wiring test — a correction type can no longer ship unwired and silently drop).

### Deferred P1 — ✅ ALL CLEARED 2026-07-04
- **`D-EDGE-RATELIMIT`** ✅ `840367871` — Redis fixed-window edge limiter, hardened after an adversarial /review-impl caught 3 HIGH + 3 MED bypasses (client-controlled key/exemption): value-matched+stripped internal-token, removed the spoofable Accept/`/stream` exemptions, `commandTimeout` for the wedged-Redis hang, dual IP+user keying (forged-sub is IP-bounded), `trust proxy` for a non-spoofable IP, Lua TTL self-heal. Fail-open. 20 limiter tests incl. the adversarial cases.
- **`D-NOTIF-I18N`** ✅ `a2b9054cf` (BE core) — i18n columns + populate + expose. Remaining: FE per-locale rendering (locale catalog for `notif.*` keys + UI render from key) — a FE follow-up.
- **`D-LEARN-ENTITY-MERGED`** ✅ `82da77d59` — learning handler for `glossary.entity_merged` + the glossary producer now emits `actor_id` (empty for system/auto merges) so user merges persist instead of DLQ'ing. Fully closed.

### Deferred P1 (original scoping — now resolved above)
| ID | Item | Gate | Plan |
|---|---|---|---|
| `D-EDGE-RATELIMIT` | No HTTP-edge rate-limit at `api-gateway-bff` (only a per-connection WS token bucket exists; `ioredis` is available, `@nestjs/throttler` is not). | #2 — **critical-path** (every request); a fail-mode/limits/keying decision is load-bearing (Redis-down must fail-OPEN or the whole edge outages) | A Redis sliding-window/token-bucket middleware keyed per-user (JWT `sub`) with an IP fallback for unauthenticated; env-configured limit+window; **fail-OPEN** on any Redis error; exempt `/health` + internal-token traffic + SSE/stream routes; 429 + `Retry-After`; unit tests (allow/deny/expiry/fail-open) + a cross-instance Redis test. Deserves a focused effort, not a session-tail rush. |
| `D-NOTIF-I18N` | Notification titles/bodies are English-concatenated with no i18n columns (NOTIF-1); no per-locale key+params model. | #2 — schema migration + FE i18n (the FE has ~93 manual imports, `fallbackLng:'en'`) | Add `notifications` i18n columns (message_key + params JSONB, keep the rendered text as a fallback), have producers emit a key+params, resolve per user locale on read; FE renders via the key. Feature-scale; own effort. |
| `D-LEARN-ENTITY-MERGED` | `glossary.entity_merged` (a user merging duplicate entities — glossary `outbox.go`) lands on the learning-consumed glossary stream but has no handler; it's a correction-class user action currently unhandled. Now VISIBLE (the dispatcher WARNs on unhandled correction-class events) but not captured. | product call — its payload is winner/loser ids, not the before/after diff shape learning's corrections use; may be deliberately out of scope | decide whether learning should mine merges; if so add a handler + a contract row |

**P1 lints flipped to BLOCKING (2026-07-04):** the 6 `p1-lints` (pagination-cap, blocking-in-async, raw-sql, injection-coverage, language-bias-gate, sdk-duplication-gate) dropped `continue-on-error` in `lint-foundation.yml` — all pass clean (baseline-seeded), so they now fail CI on a NEW violation. `timeout-discipline-lint`'s Go/Rust legs stay blocking; its Python asyncpg-`command_timeout` extension stays advisory-internal (WARN) pending the 4-pool timeout debt.
