# Divergence MCP Tools (D-DIVERGENCE-MCP-TOOLS) — spec

> Origin: close-21-28 (pre-S5) recorded ZERO divergence MCP tools + S5's §2-bar #5
> (agent-parity). The divergence panel is human-reachable + Lane-B-refreshable, but an AI
> agent cannot LIST/switch/archive/create a dị bản — it has no tools. Per the MCP-first
> invariant, this agentic surface should be MCP tools on composition-service, federated by
> ai-gateway. This spec designs them, with the derive path's Tier-W confirm as the crux.

## 1 · Why a spec (not just "clear it")

Three of the four verbs are safe reads/soft-writes and could ship as plain tools. The fourth —
CREATE (derive) — **forks a whole knowledge partition** (works.py mints a fresh knowledge
project + a divergence_spec + entity_overrides; expensive + not silently undoable, only
archivable). That is an **AN-8 Tier-W action** and MUST go through the confirm spine, not a
bolt-on. Designing that confirm is why this needs a spec.

## 2 · The tools (composition-service MCP; ai-gateway federates)

All gated by the E0 grant on the Work's book (VIEW for reads, EDIT for writes) — the SAME gate
the REST routes already use; the tools call the same repo methods, no new backend logic.

- **`composition_list_derivatives`** (R, VIEW) — the canonical Work + every derivative for a
  book (name, taxonomy, branch_point, overrides count), off the existing resolve_by_book /
  candidates[] the panel already reads. Safe.
- **`composition_get_derivative_context`** (R, VIEW) — one derivative's durable spec (reuses
  GET /derivative-context). Safe. (Register it in the Lane-B READ_TOOLS ledger as a read — no
  effect handler, no cache thrash.)
- **`composition_switch_active_work`** (W, EDIT) — set the per-user active-work pref
  (useSetActiveWork's server side: /v1/me/preferences lw_active_work.<book>). Per-user, per-book;
  reversible; cheap. Emits a Lane-B effect so the studio re-resolves (the panel already fans out
  via the pref query). Safe write.
- **`composition_archive_derivative`** (W, EDIT) — PATCH status=archived + If-Match (the panel's
  archive). Soft-delete, reversible (restore = status active). Emits the work-resolution effect.
  Class-C-ish but reversible → a lightweight confirm (or none, given reversibility) — decide with
  the AN-8 tiering.
- **`composition_create_derivative`** (W, EDIT, **Tier-W**) — the derive. §3.

## 3 · The derive confirm (the Tier-W crux)

Deriving is expensive + hard-to-undo (mints a knowledge project + forks the grounding
partition). It MUST use the generic confirm spine (the SAME `confirm_action` frontend-tool +
token-gated commit the glossary/book Tier-W actions use — see the Frontend-Tool Contract):

1. The agent calls `composition_create_derivative` with the DeriveBody (name, branch_point,
   taxonomy, overrides, canon_rules).
2. The tool does NOT derive immediately — it returns a **confirm descriptor** (Tier-W): "Spawn a
   dị bản 'X' from chapter N — this mints a new knowledge partition and cannot be undone, only
   archived." The FE renders the confirm card (the existing DOCK-9 ConfirmDialog / confirm_action
   path), the human Confirms, and the token-gated commit runs the real POST /works/{id}/derive.
3. The outcome enum (`created` / `create_unavailable` (503 PROJECT_CREATE_UNAVAILABLE, verbatim)
   / `conflict` / `dismissed`) is what lets the agent report the REAL result (never assume
   success) — the H6 discipline.
4. Idempotency: the derive already gates on a pre-existing source; the confirm token is
   single-use so a double-confirm can't mint two.

## 4 · Registration + enforcement (don't ship a silent no-op)

- Each tool on composition-service's MCP server (domain owns its tools; ai-gateway federates —
  the glossary-assistant architecture). Keep the X-Project-Id envelope intact (the known
  ai-gateway drop bug — see the KG-MCP lessons).
- Add the write tools to the **Lane-B coverage ledger** (effectCoverage.contract.test) with their
  §8.0b handler (switch/archive → the work-resolution effect) — a missing handler REDS the ledger.
- Closed-set args (taxonomy) as `enum`; the confirm descriptor machine-checked both sides.
- Live-smoke: an agent list→switch→(confirm)derive→archive on a stack-up (the cross-service
  contract; a mock-only pass hides the ai-gateway federation + confirm-token bugs).

## 5 · Status + size

✅ **BUILT + LIVE-PROVEN 2026-07-17.** All 5 verbs shipped: list_derivatives + get_derivative_context
(R), switch_active_work + archive_derivative (A), create_derivative (W, confirm-gated). The derive
routes the `mint_confirm_token → /actions/confirm` spine (§3) executing the SHARED `perform_derive`;
switch writes the `lw_active_work.<book>` pref to auth-service via a minted user-bearer (the store the
FE reads), with a Lane-B handler firing `notifyActiveWorkChanged` so the studio re-resolves live. A
live MCP-protocol smoke (composition /mcp → knowledge → book → auth) proved propose→confirm mints a
real derivative + switch sets/clears the auth pref (verified via GET /me/preferences). Agent-parity is
COMPLETE. Cross-service live-smoke: DONE (not deferred).
