# Spec — Agent write auto-gate (server-built diff card)

**Status:** DESIGN (checkpoint approved 2026-07-21 — scope: all 5 propose_record_edit domains; uniform MCP-tool gating)
**Origin:** live co-writer dogfood 2026-07-21 (book *The Tidewright*, chat `019f82b3`). Finding #3 (HIGH): asking the agent to "rewrite the description" sent a mid-tier local model (Gemma-4 26B) into an **infinite reasoning-channel loop**, oscillating between `book_update_meta` (direct write) and `propose_record_edit` (generic diff tool that demands a `base_version` it can't source). Zero tool calls emitted; the run hung until stopped.
**Root cause:** the MCP write surface exposes **two ways to do one thing**. We already auto-gate the *destructive* path (Tier-W → `GateOrConfirm` mints a confirm card, agent never calls a separate "propose" tool). The *edit-diff* path was never migrated onto that seam — `propose_record_edit` stayed an **agent-invoked** tool (born in glossary-assistant P3, merely *relocated* by the frontend-tools→MCP migration, never questioned). So the agent must know it exists, read current values, supply `base_version`, and hand-build the diff — and it overlaps the direct-write tools.

## Principle

An agent proposes **intent**, never mechanics. It calls the natural domain write (`book_update_meta{book_id, description}`). The **server** turns that into a gated diff card: it reads the current values, builds the `old→new` diff, mints the confirm token, and returns it through the **existing `GateOrConfirm` seam**. `propose_record_edit`, `base_version`, and read-first vanish from the agent's world.

## Non-negotiables it must satisfy (standards)

- **No new agent-facing free string** — the diff card is server-built; the model supplies only the new field values it already has.
- **Tenancy** — the read-current + write are owner/grant-scoped exactly as the existing tools are; the confirm token is HMAC-bound to `{user, resource, descriptor, payload}` (confused-deputy guard, already in the kit).
- **No silent no-op** — a gated write that the human dismisses returns `dismissed`; the agent states the change was made ONLY on `applied_saved`.
- **Single-use** — the `*_consumed_tokens` replay ledger already guards confirm; reused for the diff card.

## The seam (reused, not rebuilt)

`GateOrConfirm(ctx, meta, store, descriptor, ownerUserID, payload, inputRequests, cardFactory, ttlMs)`
([`sdks/go/loreweave_mcp/tasks_wire.go`](../../sdks/go/loreweave_mcp/tasks_wire.go)) already returns **either** a durable task gate (tasks-capable client) **or** `cardFactory()` (today a `{confirm_token, descriptor}` card). The *only* change: a **diff-card factory** that also carries `changes[]` (`field_label, old_value, new_value, target`). Python mirror: `gate_or_confirm`.

## Behavior change (flagged)

Diff-able metadata writes move **Tier-A (quick permission prompt → commit)** → **gated propose-diff (Apply a shown old→new diff)**. Better UX, and matches what `propose_record_edit` already did. Applies to the **MCP tool surface only** — the underlying REST `PATCH` stays a direct write (the confirm route calls it), so REST-based automation/import/migrations are unaffected. "Uniform gating" = every *agent/MCP* caller gets the diff card; there is no caller-type branch inside the tool.

## Scope — all 5 `propose_record_edit` domains

`propose_record_edit.domain ∈ {book, composition, glossary, translation, settings}`. Each domain's direct-write metadata tool adopts the facade; `propose_record_edit` is deleted once every domain has its auto-gate. **Glossary already has `glossary_propose_entity_edit`** (a diff card) — audit whether it's already conformant or needs to fold into the shared factory.

### Milestones (risk-bounded; "all five" is the scope, not one commit)

| M | Domain | Deliverable | Gate |
|---|---|---|---|
| **M0** | kit + **book** (proving ground) | diff-card factory in `loreweave_mcp` (Go + Py mirror); `book_update_meta` reads-current + `GateOrConfirm`; confirm route commits; chat-service suspends on it; FE renders `changes[]` via the existing `RecordEditChange` card; **de-advertise `propose_record_edit` for book** | `/review-impl` + **live re-smoke the exact description-rewrite** |
| **M1** | composition | audit write tools → adopt facade | unit + live |
| **M2** | glossary | reconcile `glossary_propose_entity_edit` with the shared factory | unit + live |
| **M3** | settings | adopt facade | unit + live |
| **M4** | translation | adopt facade | unit + live |
| **M5** | cleanup | delete `propose_record_edit` (tool + FE resolver + contract SoT); update `contracts/frontend-tools.contract.json` | contract drift-test green |

### Ride-along (independent, chat-service only — ship with M0)

- **Streaming reasoning loop-detector** (defense-in-depth — even a perfect tool surface can loop): rolling line-hash window + period-cycle detection over the reasoning stream in `stream_service.py`; on trip → abort pass, inject a steer message ("stop deliberating; call the single best tool now"), cap ≤2 interventions/turn, then honest stop. Fills the gap the tool-call-only breakers (`blank_tool_args_streak`, `REPEAT_READ_CAP`, `TOOL_LIST_CATEGORY_CAP`) leave open.
- **Auto-title sanitizer** ([`stream_service.py:6512`](../../services/chat-service/app/services/stream_service.py#L6512)): strip leading list/number/markdown markers; reject degenerate titles (<2 words, pure punctuation, prompt-echo) → keep `New Chat` rather than saving `"4."`.

## Per-domain audit (M1–M4 input — must run before planning each)

For each domain answer: (1) what direct-write MCP tool(s) edit its records? (2) do they currently auto-commit (Tier-A) or already gate (Tier-W)? (3) what is the read-current source for `old_value`? (4) does the FE diff card already handle this domain's `target` keys? A domain with **no** direct-write tool needs one built (buildable, not blocked).

## Open risks

- **R1** — a diff over a large field (full book summary) must render sanely; cap `old_value`/`new_value` display length in the card, keep the full value in the token payload.
- **R2** — chat-service's Tier-A auto-commit path must NOT fire for a now-gated tool; verify the suspend path is taken (the `envelope.get("task")` / confirm-card seam), else the diff card is bypassed.
- **R3** — resume/confirm must re-verify the version (OCC) so a stale diff `applied_conflict`s instead of clobbering a concurrent edit.
