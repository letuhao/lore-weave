# Interview-Practice Roleplay — contracts (MOVED)

> **The working-memory/charter contract moved to [`contracts/agent-control/`](../agent-control/README.md)**
> at the Agent Control Plane extraction (2026-07-16). It was never interview-specific — it is the control
> plane's core anchor, shared by every agent-runtime. See
> [docs/specs/2026-07-16-agent-control-plane-sdk.md](../../docs/specs/2026-07-16-agent-control-plane-sdk.md).

Interview-roleplay background: [docs/specs/2026-06-23-interview-roleplay.md](../../docs/specs/2026-06-23-interview-roleplay.md).

## `build_context` contract (unchanged, still owned by knowledge-service)

`POST /internal/context/build` response (`ContextBuildResponse`) carries **`working_memory: string`** (default
`""`) — the rendered anchor text chat-service pins into the system block AND tail-injects (depth-0). `""` when
the session has no working-memory block (non-interview session, or a knowledge-service build predating the
field — backward compatible).
