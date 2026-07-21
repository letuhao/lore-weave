# RUN-STATE — Agent write auto-gate (server-built diff card)

**Spec:** [docs/specs/2026-07-21-agent-write-autogate.md](../specs/2026-07-21-agent-write-autogate.md)
**Branch:** feat/frontend-tools-mcp-migration
**Origin:** live co-writer dogfood 2026-07-21 (book *The Tidewright*, chat 019f82b3) — Finding #3 (HIGH reasoning loop from a two-tools-one-job overlap).

## THE COMMITMENT (re-read this first after every compaction)

Deliver the FULL auto-gate: the agent calls only the natural domain write; the SERVER builds the old→new diff card and gates it through the existing `GateOrConfirm` seam. Convert **all 5** `propose_record_edit` domains, uniform MCP-tool gating (REST stays a direct write), then **delete `propose_record_edit`**. Done = every slice below carries a **pasted evidence string** (test output or live-smoke), not a claim.

## INVARIANTS (must hold at every slice — a violation blocks done)

- **I1** — Agent-facing surface gains NO new free-string mechanic; the diff is server-built, model supplies only the new field values it already has.
- **I2** — Reuse `loreweave_mcp.GateOrConfirm` + `MintConfirmToken` (Go) / `gate_or_confirm` (Py). No new kit primitive unless proven necessary.
- **I3** — Tenancy: read-current + write stay owner/grant-scoped; confirm token HMAC-bound to {user,resource,descriptor,payload} (confused-deputy guard).
- **I4** — No silent no-op: dismissed → `dismissed`; agent states "changed" ONLY on `applied_saved`.
- **I5** — Single-use: the `*_consumed_tokens` replay ledger guards the confirm.
- **I6** — REST `PATCH` stays a direct write (confirm route + automation use it); only the MCP tool surface is gated.
- **I7** — OCC on confirm: a stale diff → `applied_conflict`, never a clobber.

## SLICE BOARD  (done = the evidence string is filled in)

| Slice | Scope | Done-criteria (evidence) | State |
|---|---|---|---|
| **R1** ride-along | reasoning-loop breaker | `35024ec05`; 9 unit + 2 integ green; serial suite exit 0 | ✅ DONE |
| **R2** ride-along | auto-title sanitizer | `35024ec05`; 10 tests incl. the "4." bug | ✅ DONE |
| **M0a** | book-service Go | `book.meta` descriptor + `update_meta` op + `changes[]` diff card; `book_update_meta` Tier-A→W, mints diff card; confirm route `effectUpdateMeta` applies (OCC on updated_at). **Evidence:** `7b861223c` — PASS TestMCP_BookUpdateMeta_ProposesDiff_NoWrite_ThenConfirmApplies_DB + _StaleVersion_Conflicts_DB; vet clean; api suite green | ✅ DONE |
| **M0b** | chat-service | dropped `book` from `propose_record_edit` domain enum + redirect in description; contract mirror regen'd. **Evidence:** `5e9cff19c` — test_frontend_tools_contract 13 passed (drift red→green); validation green; test_agent_surface 8 fails proven pre-existing (identical at HEAD). | ✅ DONE |
| **M0c** | frontend | render the book confirm card's `changes[]` as the old→new diff card. **Evidence:** pasted vitest | ⬜ TODO |

**M0c wiring (found — resume here):** FE already has [`RecordDiffCard.tsx`](../../frontend/src/features/chat/components/RecordDiffCard.tsx) (renders `propose_record_edit`'s `changes[]`) + [`actionsApi.ts`](../../frontend/src/features/chat/actionsApi.ts) (`RecordEditChange` type + confirm POST). Card dispatch is in [`AssistantMessage.tsx`](../../frontend/src/features/chat/components/AssistantMessage.tsx). The book `book_update_meta` result is a confirm card with `domain:"book"`, `descriptor:"book.meta"`, `confirm_token`, `changes[]` — TODAY it would dispatch to the plain yes/no `ConfirmCard`. **Task:** in AssistantMessage dispatch, when a confirm card carries `changes[]` (or descriptor `book.meta`), render `RecordDiffCard` instead of `ConfirmCard`, wired to Apply via the **book** confirm endpoint (`POST /v1/book/actions/confirm` with `{confirm_token}`), NOT the glossary path. Verify the `changes[]` shape from Go `recordEditChange` (`field_label/old_value/new_value/target`) matches FE `RecordEditChange`. Add a vitest mirroring `RecordDiffCard.test.tsx` for the book path. Watch RUN-STATE debt: chat-service must SUSPEND on this card (Tier-W confirm) — verify the confirm-card suspend path fires for `book_update_meta` (it returns the card as the tool result, same shape as delete/publish).
| **M0d** | live | **live re-smoke: "rewrite the description" → diff card, no loop** (book *The Tidewright* `019f82b6-c31b-72e9-bf2a-3f37f4c8a847`, chat via :5174). **Evidence:** pasted browser observation | ⬜ TODO |
| **M1** | composition | audit write tool(s) → adopt facade. Evidence: pasted composition unit + live | ⬜ TODO |
| **M2** | glossary | reconcile `glossary_propose_entity_edit` with the shared factory. Evidence: pasted glossary tests + live | ⬜ TODO |
| **M3** | settings | adopt facade. Evidence: pasted tests | ⬜ TODO |
| **M4** | translation | adopt facade. Evidence: pasted tests | ⬜ TODO |
| **M5** | cleanup | delete `propose_record_edit` (tool + FE resolver + `contracts/frontend-tools.contract.json`). Evidence: contract drift-test pasted green | ⬜ TODO |

## PER-DOMAIN AUDIT (fill before starting each of M1–M4)

For each domain: (1) which direct-write MCP tool edits its records? (2) Tier-A auto-commit or already Tier-W? (3) read-current source for `old_value`? (4) does the FE diff card already handle its `target` keys? A domain with no direct-write tool → build one (buildable, not blocked).

## REGISTERS (append as you go — an empty drift log at the end is dishonest)

### Decisions
- 2026-07-21 — Scope = all 5 domains, uniform MCP gating (user chose "all five" + "always gate"). REST stays direct (I6) resolves the "breaks automation" risk.
- 2026-07-21 — Reuse GateOrConfirm card factory; no new kit primitive (seam already supports an arbitrary card).

### Parked / blocked
- (none)

### Debt
- M0a — `book_update_meta` returns the plain confirm_token diff card (not the GateOrConfirm *tasks* branch), because chat-service is non-tasks (the durable-gate path is dormant). Behaviorally identical for the live chat flow (GateOrConfirm's non-tasks branch returns the same card). If chat-service later declares tasks capability, register `descBookMeta` in the `actionTasks` resolver registry + add an `update_meta` case to `resolveBookAction` (calls the shared `applyBookMetaUpdate`). Not needed for M0's live smoke.
- M0a — OCC key is `updated_at` (no dedicated version column on `books`); precision relies on timestamptz round-trip. Tested green, but a dedicated monotonic version column would be sturdier (future).

### Drift / near-misses
- 2026-07-21 — nearly mis-filed Finding #2 as a misroute; the runtime trace showed `book_create` DID run first (correct). Lesson: read the full agent-runtime step trace, not just the pending confirm chip.
- 2026-07-21 — `-n auto` parallel run showed 3 false failures (skill-router embedding ConnectError under parallel load); the SERIAL run is the authoritative gate. Do not trust `-n auto` for these skill/embedding integration tests without `--dist loadgroup`.

## RESUME PROTOCOL (after compaction)
1. Re-read THIS file (commitment + invariants + slice board), not memory.
2. `git log --oneline -8` to see what actually landed.
3. Continue at the first ⬜ slice; fill its evidence string only from pasted output.
