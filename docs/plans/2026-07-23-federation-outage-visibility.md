# Plan — make an MCP provider outage VISIBLE (ai-gateway federation)

**Task size:** L (files≈8, logic≈7, side-effects=2 — a tool-result `_meta` contract + a healthcheck).
**Origin:** the 2026-07-23 glossary de-federation. One malformed schema dropped all 54 glossary
tools; the platform ran that way, undetected, until a live E2E happened to trip over it.
**Investigation:** the availability signal EXISTS and is plumbed — it is wired to the wrong places.
See `docs/sessions/SESSION_HANDOFF.md` and the findings below.

---

## The defect, precisely

`ai-gateway` tracks `partial` + per-provider `available` (`catalog.ts`), exposes them on
`/health/catalog`, and stamps `_meta.unavailable_providers` on `tools/list`. chat-service has a
correct consumer, `provider_availability()`, whose note says exactly the right thing:

> *"tell the user the capability exists but to try again shortly; do NOT say you can't do it."*

It has **one call site** — `stream_service.py:2479`, inside `find_tools_result_async`. F17 retired
`find_tools` from the LLM's view ("never hot-seeded, never discoverable"). **The outage-awareness
message lives on a path the model can no longer reach.** The mechanism was built correctly and
attached to the 2026-07 discovery surface; when F17 replaced that surface, the guarantee didn't
come with it — the same shape as the skill-drift and hot-set gaps.

| # | Sev | Finding |
|---|---|---|
| 1 | HIGH | `tool_list`/`tool_load` **structurally cannot** report unavailability — neither twin takes an availability param (`tool_discovery.py:887`, `find-tools.ts:467`). Measured: `tool_list("glossary")` returned `count: 5` and read as a complete, healthy answer while 54 tools were missing. |
| 2 | HIGH | `tool_load` answers `not_found` — documented as "no such tool" — when the truth is "provider down". The system lied; gemma reasoned correctly from a false premise and gave up. |
| 3 | MED | Even on the wired path the note is gated behind `matches.length === 0`. A *partial* outage that still returns some matches (our exact case) says nothing. |
| 4 | MED | Docker healthcheck hits `/health` → hardcoded `{status:'ok'}`. `/health/catalog` has the truth; **nothing polls it** (0 references repo-wide). No metric, no alert, container stays healthy. |
| 5 | LOW | The WARN re-prints identically every refresh (~30s) with no transition logging, so it can't be alerted on and can't date the outage. `provider_availability()` still carries `TODO(S-GATEWAY): freeze the key`. |

---

## Measurement protocol (decide by data, not by argument)

A reproducible outage: `docker stop infra-glossary-service-1`, wait one refresh cycle
(`catalogRefreshMs`), confirm `PARTIAL` in the gateway log. Reversible; dev stack only.

Captured at each checkpoint — **M0 (outage, pre-fix)**, **M1 (outage, post-fix)**,
**M2 (healthy, post-fix — the no-false-alarm control)**:

| Metric | How | Why it matters |
|---|---|---|
| `tool_list(glossary)` names the outage | raw payload | the model's only view of a domain |
| `tool_load(glossary_propose_entities)` verdict | raw payload | `not_found` vs `unavailable` is the lie |
| container health during outage | `docker inspect` | ops visibility |
| `/health/catalog` `partial` | HTTP | already true today; the control |
| **agent's words to the user** | live gemma E2E, final assistant text | **the money metric** — "try again shortly" vs "I can't / doesn't exist" |

The last row is the acceptance criterion. Everything else is instrumentation; the user-visible
outcome is whether the assistant hedges correctly instead of denying a capability that exists.

---

## Fixes, in dependency order

### F1 — availability reaches the LIVE discovery pair *(HIGH — findings 1+2)*
Thread the gateway's per-provider availability into `tool_list_result` / `tool_load_result` in
**both twins** (they are a lockstep pair — changing one alone is the drift this repo keeps hitting).
- `tool_list`: when any provider is unavailable, stamp `unavailable_providers` on the payload and
  say the listing may be incomplete. A category whose provider is down must not read as complete.
- `tool_load`: split the verdict. `not_found` keeps meaning "no such tool"; a name that cannot be
  resolved **while a provider is down** returns `unavailable` + a retry steer, never `not_found`.

**Open design question, resolved by measurement (F1a vs F1b):**
With the provider down, its tools are absent from the catalog, so the gateway cannot attribute a
requested name to it by lookup.
- **F1a (cheap, ship first):** no per-name attribution — "some providers are down, this name may
  belong to one; retry rather than concluding it doesn't exist."
- **F1b (stronger, only if F1a under-performs on the money metric):** retain a **last-known-good**
  tool-name set per provider, so a down provider's tools are attributable by name and `tool_list`
  can show them flagged `unavailable`. Must be disclosure-only (never callable, never hot-seeded)
  and staleness-bounded.

Ship F1a, measure, and let the E2E decide whether F1b is warranted.

### F2 — report unavailability on a NON-empty result *(MED — finding 3)*
Drop the `matches.length === 0` gate in both twins; a partial catalog is worth saying even when
some matches came back. This is the case that actually occurs.

### F3 — the container must not read healthy through a provider loss *(MED — finding 4)*
Add a federation-aware readiness signal that fails on **sustained** PARTIAL (a threshold of N
consecutive partial refreshes, not the first blip — a hard-fail on one transient would flap the
container, which is worse than the bug). Leave `/health` as the liveness probe; the outage signal
belongs on readiness.

### F4 — make the log alertable + freeze the key *(LOW — finding 5)*
Log provider availability **transitions** (up→down, down→up) instead of re-printing identical
WARN lines every refresh, so the event has a timestamp and can be alerted on. Freeze the
`unavailable_providers` `_meta` key and drop the defensive multi-shape parsing
(`TODO(S-GATEWAY)`), with a contract test pinning it across the two languages.

---

## Risks

- **False alarms.** A guard that cries outage during normal operation is worse than none — this is
  the same trap as the boolean-`default` false positive caught in the federation-schema gate.
  Mitigated by checkpoint **M2** (healthy, post-fix) as an explicit no-false-alarm control.
- **Twin drift.** `tool_discovery.py` and `find-tools.ts` are a hand-maintained pair. Every F1/F2
  change lands in both, in the same commit, with a test on each side.
- **Healthcheck flap.** Addressed by the N-consecutive threshold in F3.

## Out of scope
- Fixing the composition `_meta.tier` gap (pre-existing, different track).
- Any alerting/metrics infrastructure beyond making the signal correct and pollable.
