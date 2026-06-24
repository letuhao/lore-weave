# Deep Analytics

Home for **deep, multi-source audits and analyses** of the LoreWeave platform — the detailed work behind the summary findings in [`docs/specs/2026-06-20-platform-ai-architecture-gap-analysis.md`](../specs/2026-06-20-platform-ai-architecture-gap-analysis.md).

Each analysis gets its own dated subfolder: `YYYY-MM-DD-<topic>/` with a `FINDINGS.md` (+ a charter `README.md` for larger ones).

> These are **audits, not designs.** They report state-of-the-system, never propose implementation. Acting on a finding is a separate, sized task per the workflow. First-sweep findings are `file:line`-grounded but should each be confirmed-and-fixed under the normal failing-test→fix→verify flow.

## Index

| Date | Analysis | Status / headline | Source task |
|---|---|---|---|
| 2026-06-20 | [Tenant-isolation / IDOR sweep](2026-06-20-tenant-isolation-idor-sweep/) | ✅ **2 Critical + ~10 High** (book-service media/audio; auth + statistics ungated endpoints) | §11 T1 (XL) |
| 2026-06-20 | [contracts/ adoption + turn-latency](2026-06-20-contracts-adoption-and-latency/) | ✅ **13/23 service SDKs at 0 adoption** (resilience, logging, tracing…); turn path unbuilt | §11 T3+T4 |
| 2026-06-20 | [Data-architecture / SSOT](2026-06-20-data-architecture-ssot/) | ✅ distributed core solid; **glossary delete/rename desync knowledge graph (2 High)** | §11 T7 |
| 2026-06-20 | [Identity / auth-lifecycle](2026-06-20-identity-auth-lifecycle/) | ✅ **4 High** (legacy /ws JWT-in-URL · no revocation propagation · SVID/ACL unenforced · shared JWT secret) | §11 T10a |
| 2026-06-20 | [Test-coverage](2026-06-20-test-coverage/) | ✅ auth-flow untested · 3 services miss tenant deny-tests · app-tier smoke non-enforcing | §11 T8 |
| 2026-06-20 | [Frontend / game-client](2026-06-20-frontend-architecture/) | ✅ **auth token in localStorage** · 28 MVC violations · game client scaffold | §11 T10b |

**Blocked / not yet runnable:** A6-L5 per-PC retrieval-isolation audit (read-side consumer unbuilt — see IDOR sweep §5).
**Not audits (sequential build/ops):** §11 T5 logging adoption (refactor), T6 security CI gates (refactor), T9 DR restore drill (ops).
