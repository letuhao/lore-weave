# contracts/ Adoption-Gap + Turn-Latency Budget — Findings

- **Date:** 2026-06-20 · **Status:** ✅ COMPLETE · **Type:** read-only audit (no code changed)
- **Source:** gap-analysis §11 Tasks 3 + 4.

## Part 1 — contracts/ adoption is far worse than the logging gap alone

The "strong standard, thin adoption" theme is now **quantified**: of ~23 service-facing Go SDK packages in `contracts/`, only **8 have any importer** and only **4 clear the "widely used" bar (≥4 importers)**. **13 service-facing SDKs sit at 0 adoption.**

| Adopted (the ops back-plane) | 0 importers (the request-path standards) |
|---|---|
| `lifecycle` (6), `realityreg` (6), `meta` (4), `incidents` (4), `events` (3), `adminjwt`/`admin` (2) | **`resilience`, `dependencies`, `logging`, `tracing`, `observability`, `service_acl`, `prompt`, `turn`, `ws`, `errors`, `entity_status`, `capacity`, `supply_chain`** |

**The adoption that exists clusters in the meta/lifecycle/reality ops substrate; every cross-cutting per-request standard is defined-but-dormant.** Worst three (built, complete, `_test.go`-covered, zero importers):
1. **`contracts/resilience`** — the `WithTimeout`/breaker/bulkhead wrapper **I16 mandates for every outbound call.** 0 importers → every timeout in services is raw stdlib, not the SDK. Single most consequential gap.
2. **`contracts/dependencies/client_factory.go`** — produces wrapped clients from the timeout matrix. 0 importers → the matrix is read only by a lint, never at runtime.
3. **`contracts/logging` + `contracts/tracing`** — full structured-logging/tracing libs (compile guards, redactors, samplers). 0 importers each (confirms §5 of the gap-analysis).

> **Implication:** invariants I16 (timeout chain), I19 (metric inventory), the logging standard, and SVID/ACL (I11, below) are enforced — *if at all* — only by lint scripts, never by runtime code. The libraries that would make them real exist and are unused.

## Part 2 — the real-time turn path barely exists; timeouts are undeclared on the hops that do

**Build state of the turn chain** (client → game-server → roleplay → world dispatch + knowledge retrieval → provider/LLM → output filter):
- **`roleplay-service` (the orchestrator) does not exist** — yet `contracts/dependencies/matrix.yaml` names it as `owner_service` of the `llm-*` deps (a **dangling reference to an unbuilt service**).
- **`game-server` is an echo skeleton** — grep for `roleplay`/`world-service`/`knowledge-service` in its src = **0 hits**. No downstream wiring.
- **`world-service` has no `command_dispatch` turn endpoint.**

**Timeout coverage on the designed chain:** declared for `meta-db` (3s), `per-reality-db` (10s), `redis-streams` (0.5s), `auth` (5s), `llm-*` (60s). **Missing for all 4 internal RPC hops** (roleplay→world, →knowledge, →provider-registry; roleplay itself isn't a dep) — I16 gaps.

**Budget verdict:** the project's *actual* turn SLO is **60s/120s** (`SR01`/`SR11`), not a 2–3s live-RP bar — so the LLM-dominated chain "fits" its own generous budget, but: (a) the worst-case sum (~78.5s: auth 5 + meta 3 + reality-db 10 + redis 0.5 + LLM 60) **exceeds even the 60s paid SLO**; (b) a single 60s LLM leg consumes the entire budget; (c) the docs themselves flag "a 60s timeout downstream of a 5s RPC is a bug" but **nothing enforces the inversion check at runtime** (because `resilience`/`dependencies` are unadopted).

## Combined takeaway
The single highest-leverage move bridging both parts: **adopt `contracts/resilience` + `contracts/dependencies/client_factory`** — they're built, complete, and unused, and they're the prerequisite for I16's timeout-chain guarantee to be more than documentation. The turn path can't be latency-audited for real until `roleplay-service` exists.
