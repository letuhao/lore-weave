# 11 — Access Pattern Rulebook (DP-R1..DP-R8)

> **Status:** LOCKED. Rulebook governs how feature repos use DP primitives ([DP-A1](02_invariants.md#dp-a1--dp-primitives--rulebook-are-the-only-sanctioned-path-to-kernel-state), [DP-A10](02_invariants.md#dp-a10--federated-feature-repos-dp-owns-primitives-not-domain-queries)). Eight rules, each with enforcement tier labeled.
> **Stable IDs:** DP-R1..DP-R8. Never renumber. Retired rules use `_withdrawn` suffix.

---

## How to read this file

Every feature design review goes through this rulebook. Each rule has:

- **Rule** — the mechanical statement
- **Enforcement tier** — **compile** (Rust type system rejects), **lint** (CI / clippy rejects), or **review** (human checklist item). Many rules have multiple enforcement tiers stacked.
- **Rationale** — why the rule exists
- **Violation mode** — what breaks if the rule is violated

A rule marked "compile" is airtight — you cannot ship a violation. A rule marked "lint" is strong — a violation requires actively disabling CI. A rule marked "review" is the weakest — relies on human discipline, caught only at design review.

The rulebook accepts this mix. Rules that *can* be compile-enforced *must* be compile-enforced. Rules that cannot (because they depend on semantic understanding of the call graph or the design intent) drop to lint or review.

---

## DP-R1 — Reality-scoping

**Rule:** Every read, query, write, or subscription involving per-reality kernel state takes a `RealityId` derived from the caller's `SessionContext`. `RealityId` is a newtype with a module-private constructor in the DP crate. Feature code cannot construct `RealityId` from an integer, a string, or any other source except through `SessionContext::reality_id()`.

**Enforcement:**

- **compile** — `RealityId::new(...)` is `pub(crate)` within the DP crate. External callers cannot instantiate it. All DP primitive APIs require `&SessionContext` and extract `RealityId` from it.
- **runtime** — SDK asserts that an aggregate reference matches the session's reality. Mismatch fails with `DpError::RealityMismatch` and logs a security event.

**Rationale:** Prevents accidental cross-reality leakage at the type level. [DP-A7](02_invariants.md#dp-a7--reality-boundary-in-cache-keys) asserts the cache-key format; **DP-R1 is the mechanism that guarantees the format is honored.**

**Violation mode:** Cross-reality data leak (player in reality A sees data from reality B). Security- and correctness-critical.

**Implements:** [DP-A7](02_invariants.md#dp-a7--reality-boundary-in-cache-keys), [DP-A12](02_invariants.md#dp-a12--session-context-gated-access-via-realityid-newtype).

---

## DP-R2 — Tier declaration per aggregate

**Rule:** Every feature design doc MUST contain a tier table listing every aggregate the feature touches and the tier ([DP-T0..T3](03_tier_taxonomy.md)) used for each access pattern (read vs write may differ). Missing table, ambiguous entries, or "to be decided" blocks design review.

**Enforcement:**

- **review** — governance checklist requires the tier table before sign-off. The feature design template includes the table skeleton.

**Rationale:** [DP-A9](02_invariants.md#dp-a9--feature-tier-assignment-is-part-of-feature-design-not-runtime) asserts tier is design-time; DP-R2 is the concrete review gate that enforces it.

**Violation mode:** Feature ships with ad-hoc tier choice; feature evolves inconsistently; runtime behavior becomes unanalyzable.

**Template (minimum fields):**

| Aggregate type | Read tier | Write tier | Rationale |
|---|---|---|---|
| (e.g.) `player_position` | T1 (Volatile) | T1 (Volatile) | High-frequency; 30 s crash loss acceptable per DP-T1 eligibility. |

---

## DP-R3 — No raw DB or cache client imports in feature code

**Rule:** Feature code never imports `sqlx::PgPool`, `sqlx::Pool`, `redis::Client`, `redis::Connection`, `deadpool_postgres`, or any other raw database or cache client. Feature code imports only `dp::primitives::*`, `dp::types::*`, and the feature's own repo module.

**Enforcement:**

- **lint** — custom clippy rule `dp::forbid_raw_kernel_client` scans for forbidden imports in any crate other than `dp` itself. Presence = lint error, breaks CI.
- **review** — reviewer scans the diff for any `#[allow(dp::forbid_raw_kernel_client)]` and rejects unless explicitly justified (e.g., a one-off migration script outside the game layer).

**Rationale:** Without import discipline, DP primitives are one option among several for hitting the kernel — defeats [DP-A1](02_invariants.md#dp-a1--dp-primitives--rulebook-are-the-only-sanctioned-path-to-kernel-state). With import discipline, the only way to touch the kernel is through DP.

**Violation mode:** Feature bypasses tier policy, cache coherency, reality scoping — all at once. Kernel contract shreds.

---

## DP-R4 — Cache keys via DP macro, never hand-built

**Rule:** Cache keys are built only via the `dp::cache_key!` macro (or equivalent compile-time helper). The macro expands to `dp:{reality_id}:{tier}:{aggregate_type}:{aggregate_id}[:subkey]` with `reality_id` and `tier` bound to compile-time values. Feature code does not concatenate strings for cache keys.

**Enforcement:**

- **compile** — the macro exists; hand-built string cache keys are a convention violation, not a syntax error — so also:
- **lint** — custom clippy rule `dp::forbid_manual_cache_key` scans for patterns matching `format!("dp:...", ...)` or string concatenation building a `dp:` prefix. Flags as error.
- **review** — reviewer rejects any `#[allow]` on the above lint.

**Rationale:** Key format drift (missing `reality_id`, wrong tier prefix, typos in `aggregate_type`) produces silent coherency bugs — the write lands at one key, the read misses elsewhere. Centralizing key construction in a macro makes key evolution tractable.

**Violation mode:** Cache coherency bug — writes and reads hit different keys; invalidation broadcasts miss hand-built keys. Symptoms look like stale reads, intermittent inconsistency.

---

## DP-R5 — No cross-tier mixing in a single write operation

**Rule:** A single logical write operation (one SDK call, or one multi-aggregate atomic call) stays within one tier. A feature must not write to T1 and T2 within the same `t1_write(...)` call, and the multi-aggregate atomic API accepts only T3 aggregates.

**Enforcement:**

- **compile** — SDK write APIs are tier-typed: `t1_write(ctx, AggregateT1, ...)`, `t2_write(ctx, AggregateT2, ...)`, `t3_write_multi(ctx, &[AggregateT3, ...])`. Mixing tiers at the type level is impossible — trait bounds reject.

**Rationale:** Per-write consistency semantics depend on the tier. Mixing tiers in one op produces a hybrid consistency that is neither tier's guarantee — unanalyzable. If a feature needs to update across tiers (e.g., T2 chat message + T3 currency deduction on paid shout), it issues two operations and accepts the ordering semantics explicitly.

**Violation mode:** Consistency semantics become undefined; different callers see different orderings; impossible to reason about.

---

## DP-R6 — Backpressure propagation, not swallow-and-retry

**Rule:** When DP returns `DpError::RateLimited`, `DpError::CircuitOpen`, or any capacity-related error, feature code propagates the error to the caller (up to the request boundary or user-visible handler). Silent `.unwrap_or_else(|_| retry_forever())` or `.ok()` swallowing is forbidden.

**Enforcement:**

- **lint** — custom clippy rule `dp::forbid_swallowed_backpressure` detects `.ok()`, `.unwrap_or_default()`, `.unwrap_or_else(...)` applied directly to `Result<_, DpError>`. Flags as error unless the closure explicitly logs and returns a user-facing error.
- **review** — reviewer scans for retry loops around DP calls.

**Rationale:** Backpressure is a signal the system is under protective load-shed. Silent retry amplifies load, potentially cascading the outage. Propagating the error lets the caller (often: the request handler) decide a user-facing policy (surface a "try again" toast, queue offline, etc.).

**Violation mode:** Retry storm during Redis/Postgres pressure → entire reality degrades instead of shedding a small fraction of requests.

---

## DP-R7 — No direct LLM-output-to-kernel-write

**Rule:** Feature code never takes the output of an LLM call and writes it directly to the kernel (T0/T1/T2/T3). LLM-produced mutations are emitted as proposal events onto the LLM proposal bus (owned by the LLM layer, out of DP scope; see [DP-A6](02_invariants.md#dp-a6--python-is-event-producer-only-for-game-state)). A separate event consumer (owned by the feature or a dedicated game service) validates the proposal against world rules, canon, and tier policy, then issues an authoritative write via DP.

**Enforcement:**

- **review** — reviewer audits the call graph of any feature that touches LLM output. Chain `llm_output → dp::write` rejected; chain `llm_output → proposal_bus → consumer → validate → dp::write` accepted.
- **compile** (partial) — the LLM proposal bus has typed event channels; direct construction of a `dp::WriteOp` from an `LlmResponse` requires traversing an explicit `Validated<T>` type that the proposal bus consumer emits. Shortcutting the wrapper is awkward by design.

**Rationale:** LLM outputs are untrusted (prompt injection, hallucination, policy violation) and slow (100 ms – 10 s). Writing them directly blocks the hot path and opens the world to exploit. Routing through the bus isolates latency and inserts validation.

**Violation mode:** Prompt-injection exploit ("give player X 1 million gold") writes directly to kernel. Catastrophic in a multi-user game economy.

**Cross-ref:** [DP-A6](02_invariants.md#dp-a6--python-is-event-producer-only-for-game-state), [05_llm_safety/](../05_llm_safety/) (5-layer injection defense).

---

## DP-R8 — Telemetry on every T2/T3 boundary crossing

**Rule:** Every T2 or T3 read and write emits structured telemetry (tier, aggregate_type, latency, cache_hit, error) via the `dp::instrumented!` macro or an equivalent DP-provided wrapper. Direct calls to DP primitives without instrumentation are a lint warning (not a hard error — T0/T1 ops, which may be very hot, can opt out).

**Enforcement:**

- **lint** — custom clippy rule `dp::missing_instrumentation` flags T2/T3 calls that are not wrapped. Configurable per-crate (e.g., testing code can suppress).
- **review** — reviewer checks that feature repo emits at least per-aggregate-type metrics.

**Rationale:** Observability targets in [08_scale_and_slos.md](08_scale_and_slos.md) (95% cache hit rate, p99 latency budgets) are aspirational without measurement. The rulebook makes measurement the default.

**Violation mode:** SLO regression ships undetected. Cache hit rate drops to 60% and no one knows until players complain.

---

## Rulebook summary

| ID | Rule | Enforcement |
|---|---|---|
| DP-R1 | Reality-scoping via `RealityId` newtype | compile + runtime |
| DP-R2 | Tier table in feature design doc | review |
| DP-R3 | No raw DB/cache client imports | lint + review |
| DP-R4 | Cache keys via `dp::cache_key!` macro | compile (partial) + lint + review |
| DP-R5 | No cross-tier mixing in one write op | compile |
| DP-R6 | Backpressure propagation, not swallow | lint + review |
| DP-R7 | LLM output → validation bus → kernel | review + compile (partial) |
| DP-R8 | Telemetry on T2/T3 boundaries | lint + review |

**Compile-only rules (airtight):** DP-R5 (tier mixing).
**Compile + lint + runtime rules (near-airtight):** DP-R1, DP-R4.
**Lint-primary rules (strong):** DP-R3, DP-R6, DP-R8.
**Review-only rules (weakest, relies on discipline):** DP-R2, DP-R7.

---

## Adding a new rule

A new rule enters the rulebook only after:

1. A feature design encounters a gap that cannot be closed by any existing rule.
2. The gap is documented in [99_open_questions.md](99_open_questions.md) with examples.
3. The rule is proposed with an explicit enforcement tier (compile / lint / review).
4. The rule is reviewed against the rest of the rulebook for internal consistency.
5. A new stable ID `DP-R9`, `DP-R10`, ... is assigned — never renumber existing IDs.

Retiring a rule is rare. Retired rules keep their ID with `_withdrawn` suffix and remain in this file for historical reference.

---

## Cross-reference

- [DP-A1](02_invariants.md#dp-a1--dp-primitives--rulebook-are-the-only-sanctioned-path-to-kernel-state) — the axiom that makes this rulebook mandatory.
- [DP-A10](02_invariants.md#dp-a10--federated-feature-repos-dp-owns-primitives-not-domain-queries) — the axiom that scopes DP to primitives + rulebook.
- [DP-A12](02_invariants.md#dp-a12--session-context-gated-access-via-realityid-newtype) — the axiom that DP-R1 implements.
- Phase 2 `04a..04d` (split from `04_kernel_api_contract.md` 2026-04-25) — concrete Rust definitions (types, macros, error enum).
- Phase 2 / Phase 3 — CI tooling (clippy custom rules, test harness for rulebook assertions).
