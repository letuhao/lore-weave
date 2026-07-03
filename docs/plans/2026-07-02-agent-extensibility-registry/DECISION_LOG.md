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

## DL-4 · 2026-07-03 · REG-P1-03 / REG-P1-05 (System skill bodies)
- Context: The 5 System skills' full bodies live in chat-service `*_skill.py` constants and are already injected there. REG-P1-03 said "seed System rows, body == python constants (checksum)".
- Options: (A) copy the 5 Python skill bodies verbatim into the agent-registry seed (satisfies the checksum AC); (B) seed System rows with slug + description + a marker body, keep the real bodies authored in chat-service (single source), and have chat-service inject its own System bodies while honoring per-user disable via `/internal/skills.system_overrides`.
- Chosen: **B — chat-service stays the System-skill-body source of truth.**
- Rationale: copying the bodies duplicates content across two services in two languages → guaranteed drift (the exact anti-pattern the Frontend-Tool-Contract section warns about). The seed rows exist for the catalog/enable-disable UX + shadow resolution; `/internal/skills` returns `system_overrides` (disabled System slugs) + `shadowed_system` (user slugs that override) so chat-service injects correctly. The checksum-equality AC is relaxed to slug-equality (byte-identical slugs — E2E-verified).
- Rework cost if overturned: low — if a future consumer needs the bodies in agent-registry, add a one-time sync from chat-service; no schema change.

## DL-5 · 2026-07-03 · REG-P1-06 (proposal approve auth)
- Context: Spec §12b described the confirm route as "internal-token + X-User-Id gated (no JWT mint)" — that shape is the PUBLIC-MCP approval spine for EXTERNAL agents. For our in-app chat, the human approves in the browser with their own JWT.
- Options: (A) internal-token + X-User-Id confirm route (FE would need an internal token — it doesn't have one); (B) JWT-owner-gated `PUT /proposals/{id}/approve` where the browser's own token authorizes the write to the user's own tier.
- Chosen: **B — JWT-owner-gated approve/reject** (no JWT mint; owner from the token).
- Rationale: the human is in-app with a JWT; a JWT-gated approve to one's own tier is the correct, simplest authorization and needs no token minting. The public-MCP internal-token spine is for the P3+ external-agent path, not this in-app loop. The `confirm_token` remains on the proposal for chat tool-call correlation.
- Rework cost if overturned: low — add an internal-token confirm alias later for an external-agent approval path if needed.

## DL-6 · 2026-07-03 · REG-P1-08 (SkillProposalCard) — deferred on concurrent-work collision
- Context: `registry_propose_skill` is a SERVER MCP tool, so its result renders as a normal tool result inside the chat assistant message — i.e. in `frontend/src/features/chat/components/AssistantMessage.tsx`. That file (and the whole `features/chat/**` tree) is currently MID-FLIGHT with the chat-quality-ux-wave track's UNCOMMITTED changes.
- Options: (A) edit AssistantMessage.tsx now (collides with the other track's uncommitted diff — can't cleanly stage just our part, high conflict risk); (B) defer SkillProposalCard until the chat-quality track's changes land, then add the card render on a clean base.
- Chosen: **B — defer (`D-REG-SKILLPROPOSAL-CARD`)**, gate #1 (out-of-scope collision with a concurrent track's uncommitted work).
- Rationale: editing another track's actively-modified files mid-flight is the exact "shared file hazard" the repo warns about; the proposal loop is already fully functional headless (MCP propose → DB row → Proposals inbox → approve), so the card is a chat-surface convenience, not a blocker. The ProposalsPanel/ProposalsView already give the human an approve/reject surface outside chat.
- Rework cost if overturned: low — the card is one component reading a tool-result shape we already emit; add it once `features/chat` is quiescent.

---

## CLEARED — 2026-07-03 (all deferrals resolved on user request)
- **DL-2 / D-REG-BOOK-GRANT** → CLEARED: grantclient wired (`RequireGrant ≥edit`, fail-closed 404/501/503); book-tier plugins/skills + book-scope enablement now work. Live: book-tier for an ungranted book → 404 (`p1_governance_smoke.ps1`).
- **REG-X-02** → CLEARED: 50-skill per-user cap enforced at every write path (createSkill/import/proposal-approve) → 429. Live-verified.
- **DL-6 / D-REG-SKILLPROPOSAL-CARD** → CLEARED: `AssistantMessage.tsx` is clean again (the chat-quality track landed), so the collision that forced the defer is gone; the in-chat approve/reject `SkillProposalCard` is wired. 159 FE tests green (no regression).
- **D-REG-P1G-BROWSER** → FULLY CLEARED (deterministic + LIVE): `registryPanels.test.tsx` mounts the real panels + panelCatalogContract holds, AND the live browser smoke `p1g_browser_smoke.mjs` PASSED — a standalone Playwright script launching its OWN isolated chromium (bypassing the MCP-held shared browser): real login → studio → Ctrl+Shift+P → "Open Extensions" → the dock actually mounted the Extensions panel + rendered the Skills view from the live backend.
- **FE tails** (standalone /extensions route, save-as-skill affordance) → shipped.
