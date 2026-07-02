# Decision Log — Agent Extensibility Registry (autonomous run)

Mid-run design forks discovered during implementation. Per the execution model
(`00_EVALUATION_AND_TASKS.md` §7): the agent picks the safest default consistent
with the sealed Decision Register (§3) + CLAUDE.md invariants, records it here,
and **continues** — no pause. The PO reviews this log at the FINAL RELEASE GATE
and may order rework.

Format per entry:

```
## DL-<n> · <date> · <task-id>
- Context: <what surfaced the fork>
- Options: <A / B / …>
- Chosen: <option> 
- Rationale: <why this is the safest default; which sealed decision/invariant it follows>
- Rework cost if overturned: <low/med/high + one line>
```

---

## DL-1 · 2026-07-03 · REG-X-01 (audit)
- Context: Spec/plan called for the audit trail via an AFTER-UPDATE trigger → projection table (the `projection-trigger-activity-log` pattern). At P0 the mutation surface is small and all writes flow through a handful of handlers.
- Options: (A) explicit `s.audit(...)` insert from each mutation handler; (B) AFTER-UPDATE/INSERT triggers per table.
- Chosen: **A — explicit insert helper**, for P0.
- Rationale: simpler + directly unit-testable, and it captures actor identity (user vs agent vs admin) + intent (create/enable/accept-risk) that a row-diff trigger can't see without extra plumbing. Triggers shine for out-of-band writes; here every write already goes through our handlers. Consistent with "fix-now, keep it simple".
- Rework cost if overturned: low — swap the helper for triggers; the `registry_audit` table shape is unchanged either way.

## DL-2 · 2026-07-03 · REG-P0-03 / REG-P0-04 (book tier)
- Context: Creating a `book`-tier plugin, or writing a `book`-scope enablement override, requires verifying the caller holds an E0 grant on the target `book_id`. The book-grant client is not wired into agent-registry yet.
- Options: (A) allow book writes now, trusting the caller-supplied book_id; (B) reject book-tier creation + book-scope enablement writes until the grant client is wired; (C) build the grant client now.
- Chosen: **B — reject with 501 NOT_IMPLEMENTED** (`D-REG-BOOK-GRANT`), while the resolver still fully honors book overrides (so no behavior is lost once writes land, and the D1 matrix is implemented + unit-tested).
- Rationale: an unguarded book write is a tenancy hole (CLAUDE.md LOCKED — the exact class the entity-kinds rule forbids; `worker-loaded-id-needs-parent-scoping`). (C) is real scope (a cross-service grant contract) that belongs to the book-tier track, not P0 foundation. Safest default that ships P0 without a security regression.
- Rework cost if overturned: low-med — add the grant client + flip the two 501 branches to real inserts; no schema change.

## DL-3 · 2026-07-03 · P0 test strategy
- Context: Handler happy-paths (full RETURNING-row scans) are painful to mock precisely with pgxmock, and the sealed E2E-1 decision + repo lessons (`prefer-e2e-and-evaluation-over-live-smoke-poc`, `new-cross-service-contract-needs-consumer-live-smoke`) say the real gate is a real-stack E2E.
- Options: (A) exhaustively mock every handler row; (B) unit-test the pure logic + validation/tenancy rejection branches, prove happy-path CRUD through the real-stack E2E (E2E-P0-A/B).
- Chosen: **B**.
- Rationale: mock-only row scans are brittle and have repeatedly hidden real cross-service bugs in this repo; the pure resolver matrix, name/vault/clamp, and the reject branches (401/400/403/501/internal-token) ARE unit-tested, and the create/list/delete happy path is covered by the real-stack E2E where it actually matters.
- Rework cost if overturned: low — add pgxmock row fixtures later if a unit-level happy-path guard is wanted.
