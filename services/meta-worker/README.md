# services/meta-worker — L2.L sole xreality consumer

Per **I7 invariant** (`docs/plans/.../OPEN_QUESTIONS_LOCKED.md` §3) this is
the **only** service that consumes the `xreality.*` Redis Streams.

## Why a dedicated service?

xreality fanout has the cross-tenant blast-radius — a bug here can leak
canon from reality A into reality B's projections. Putting every consumer
behind one service makes the contract enforceable: the ACL allows only
`meta-worker` SVID to `XREADGROUP` on `xreality.*`, and the codepath here
is the narrowest possible (`dispatch.Dispatch(event_type)`).

## Internal layout

| Package | Purpose |
|---|---|
| `pkg/consumer` | Redis Streams XREADGROUP loop (per-topic consumer group) |
| `pkg/dispatch` | (event_type) → handler routing; **ALLOWLIST-only** |
| `cmd/meta-worker` | Entry point + graceful shutdown |

## V1 handler skeletons

V1 ships SKELETON handlers (`xreality.canon.promoted` → `noopCanonHandler`,
`xreality.user.erased` → `noopUserHandler`). Real projection writes land in
cycle 12+ when the per-reality `canon_projection` tables exist.

The skeleton handlers DO assert + log the dispatch event so the cycle-10
integration test can verify the wiring end-to-end without a real
projection sink.

## Q-L2-4 topic naming

`xreality.<entity>.<verb>` — verified by both publisher fanout and meta-
worker consumer. Mismatch = test failure.
