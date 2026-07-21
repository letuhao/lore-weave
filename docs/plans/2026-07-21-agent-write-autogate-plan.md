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
| **M0c** | frontend | render the book confirm card's `changes[]` as the old→new diff. **Evidence:** `4ec37f04c` — ConfirmActionCard 22 passed (new M0c diff+book-confirm test), autoConfirm 7, RecordDiffCard 4; tsc clean. | ✅ DONE |

**M0c wiring (PRECISE — resume here):** dispatch is by TOOL NAME in [`AssistantMessage.tsx`](../../frontend/src/features/chat/components/AssistantMessage.tsx) around **lines 356–373**:
- `:360` `if (tc.tool === 'glossary_propose_entity_edit') return <GlossaryDiffCard .../>`
- `:368-370` descriptor-based: `descriptorDomain(desc)` truthy (dotted, e.g. `book.meta`) → `<ConfirmActionCard/>` (plain yes/no, commits `/v1/<domain>/actions/*`), else `<ConfirmCard/>`.
- `:373` `if (tc.tool === 'propose_record_edit') return <RecordDiffCard record={tc} .../>`

**Problem:** `book_update_meta`'s result descriptor is `book.meta` (dotted) → today it falls to `:369` → `ConfirmActionCard` (plain confirm, NO diff).

**Key data-source difference to handle:** `propose_record_edit` is a frontend tool where the AGENT put `changes[]` in **tc.args**; `book_update_meta` is a backend tool where the SERVER put `changes[]` + `confirm_token` in the **tool RESULT** (`tc.result`/envelope). So `RecordDiffCard` (read [it](../../frontend/src/features/chat/components/RecordDiffCard.tsx) first — likely reads `tc.args`) must also accept changes+token from the RESULT. Plan: add a dispatch branch `if (tc.tool === 'book_update_meta') return <RecordDiffCard record={tc} source="result" .../>` (or an adapter that lifts `{changes, confirm_token, descriptor:'book.meta'}` from the result into the shape RecordDiffCard expects), and make Apply POST `/v1/book/actions/confirm {confirm_token}` (book path — [`actionsApi.ts`](../../frontend/src/features/chat/actionsApi.ts) `descriptorDomain('book.meta')` should already map to book). Verify Go `recordEditChange` (`field_label/old_value/new_value/target`) == FE `RecordEditChange`. Add a vitest mirroring `RecordDiffCard.test.tsx` for the book/result path.

**Prerequisite RESOLVED (no server change needed):** the card surfaces via the FE **auto-confirm token detection** — `AssistantMessage.tsx` `:286–324` builds `autoConfirms` by scanning tool RESULTS for a LIVE `confirm_token` (`actionTokenLive`), and `:382–388` renders each via `descriptorDomain(p.descriptor)` → `ConfirmActionCard`/`ConfirmCard`. So `book_update_meta`'s minted card auto-renders TODAY as a plain confirm (no `stream_service.py` suspend dependency, no `confirm_action` call required). **⇒ M0c is purely FE:** in the auto-confirm render (`:382-388`) AND the explicit dispatch (`:356-373`), when the card/result carries `changes[]` (descriptor `book.meta`), render `RecordDiffCard` (fed from the RESULT) instead of the plain confirm. Confirm the `autoConfirms` builder also carries `changes[]` through from the result (extend the `ProposeConfirm` parse at `:83`/`:106-115` to include `changes`). That parse extension + the two render branches + a vitest = M0c.
| **M0d** | live | **request → diff card, no loop.** Mechanism PROVEN deterministically: `edc419491` PASS TestMCP_BookUpdateMeta_ThroughMCPHandler_ReturnsDiffCard_DB (drives the "rewrite the description" request through the REAL /mcp handler → diff card, writes nothing) + M0c vitest (FE renders + confirms). **Browser NL smoke: BLOCKED by local-model reliability** (see drift) — deployed stack rebuilt + live; local Gemma-4 26B mis-selects (book_chapter_delete/save_draft) or loops; gpt-4o (probe) returns nothing. Mechanism is model-independent and proven; NL tool-*selection* is the model's job. | ⚠️ MECHANISM PROVEN; browser-NL model-limited |
| **M1** | composition | audit write tool(s) → adopt facade. Evidence: pasted composition unit + live | ⬜ TODO |
| **M2** | glossary | reconcile `glossary_propose_entity_edit` with the shared factory. Evidence: pasted glossary tests + live | ⬜ TODO |
| **M3** | settings | adopt facade. Evidence: pasted tests | ⬜ TODO |
| **M4** | translation | adopt facade. Evidence: pasted tests | ⬜ TODO |
| **M5** | cleanup | delete `propose_record_edit` (tool + FE resolver + `contracts/frontend-tools.contract.json`). Evidence: contract drift-test pasted green | ⬜ TODO |

## M0d LIVE DIAGNOSIS (2026-07-21) — three red herrings cleared, real root cause found

The live NL smoke ("update the book's description" → diff card) went through THREE
false blockers before the real one surfaced:
1. **Auth expiry** (`6b426c04c` era) — a long-lived browser JWT expired → silent 401s that looked like a model hang. Fixed by re-login.
2. **Reasoning-loop steer bug** — FIXED `6b426c04c` (use `no_thinking_fields()`, not hand-rolled). After this the model stopped LOOPING.
3. **Wrong-tool pick** — the model chose `book_chapter_save_draft` for a metadata edit. FIXED `7d3659e60` (save_draft disclaims book metadata). After this the model stopped picking save_draft.

**REAL ROOT CAUSE (still open):** even loop-free and save_draft-disclaimed, the model
never reaches `book_update_meta`. It says "this is a **metadata** change, I'll prepare a
proposal" (correct intent!) but calls `tool_list → book_list → book_get` and stops — the
tool is not selected. Two compounding reasons:
- **Engineer-jargon name.** `book_update_meta` — "meta" is a dev word; users/models say
  "book description / details / blurb". The name doesn't match the intent language, hurting
  both find-retrieval and selection. **User's call: rename it.**
- **Discoverability.** In a GLOBAL chat the book domain is lazy; the model must `tool_list(book)`.
  It did — yet didn't reach the tool. (ai-gateway was re-federated after the tier A→W change;
  verify the tool actually appears in `tool_list(book)` now.)

### NEXT TASK (do NOT rush under low context — touches advertisement-gating files): rename `book_update_meta` → `book_update_details`

A natural name covering title/description/summary/genre. Careful cross-cutting rename
(the Go handler func `toolBookUpdateMeta` and the confirm descriptor `book.meta` can STAY —
only the advertised TOOL-NAME string changes). Files:
- **book-service** `mcp_server.go` — the `addTool("book_update_meta", …)` name + strengthen synonyms with natural phrasings ("book details", "book blurb", "book description"); update the `book_chapter_create` + `book_chapter_save_draft` disclaimers that say "use book_update_meta".
- **⚠️ ADVERTISEMENT-GATING (get these right or the renamed tool is blocked/invisible):**
  - `services/mcp-public-gateway/src/scope/tool-policy.ts` — the tool scope/tier policy.
  - `contracts/tool-liveness.json` + `services/chat-service/app/services/tool-liveness.json` + `services/agent-registry-service/internal/api/tool-liveness.json` — the tool-liveness manifest (3 copies must move together).
- **chat-service** `frontend_tools.py` (propose_record_edit disclaimer), `stream_service.py` (steer directive), `book_skill.py` (if it names the tool).
- **FE** `ConfirmActionCard.tsx` + `AssistantMessage.tsx` — comments only (the descriptor `book.meta` is unchanged, so functional dispatch is unaffected).
- **Tests** — `mcp_book_meta_autogate_db_test.go` (CallTool Name), `test_stream_service.py` / `test_reasoning_loop_detector.py` fixtures.
- Rebuild book-service + chat-service, **restart ai-gateway to re-federate**, re-smoke.
- Historical docs/eval `*.json`/`*.md` under `docs/eval/tool-liveness/` are RECORDS — do NOT rewrite.

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
- 2026-07-21 (M0d) — **FINDING → FIXED `6b426c04c`:** the reasoning-loop steer hand-rolled `reasoning_effort="none"` and **popped `chat_template_kwargs`**, stripping the field that actually suppresses `<think>` on local Qwen3/Gemma (`chat_template_kwargs.{enable_thinking:false}`). Per model docs, `reasoning_effort` alone is ignored by these models (and on Gemma-4 setting it ENABLES thinking) — so the steered retry kept reasoning and re-looped. Fix: use the codebase's standardized `loreweave_llm.no_thinking_fields()` (both fields), the same primitive canon_check/llm_judge/entity_recovery use. **Lesson: the repo already standardized reasoning control — USE the primitive, never hand-roll the wire fields.**
- 2026-07-21 (M0d) — **model-reliability:** local Gemma-4 26B is unreliable at this tool selection (variously loops, or picks book_chapter_save_draft / book_chapter_delete for a "update the description" ask). It DID follow the M0b guidance (reaches for book_update_meta, not propose_record_edit). gpt-4o "(probe)" returned no response (looks misconfigured for full chat). A capable, correctly-configured model is needed for the live NL smoke; the mechanism itself is proven model-independently.
- 2026-07-21 (M0d) — **gotcha:** a long-lived browser session's JWT expired mid-run → silent 401s on chat POST (no assistant response, easily mistaken for a model hang). Re-login (clear storage → /login) fixes it. Check console for 401s before blaming the model.

## RESUME PROTOCOL (after compaction)
1. Re-read THIS file (commitment + invariants + slice board), not memory.
2. `git log --oneline -8` to see what actually landed.
3. Continue at the first ⬜ slice; fill its evidence string only from pasted output.
