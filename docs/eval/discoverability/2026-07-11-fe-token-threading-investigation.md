# FE token-threading — is the propose→confirm token a real product bug?

**Question (from the WS-5 finding):** a mid-tier model corrupts the 519-char `confirm_token` when it copies
it into the `confirm_action` arg. Does the real FE commit the **model-copied** arg token (→ real bug) or a
**server-authored** token (→ fine)? **Answer: both paths exist — and the product already ships the
mitigation. S01's real-GUI success is well past 75%; my headless harness was under-counting.**

## What the FE actually does (code-traced)

Two ways a confirm card reaches the user, in `frontend/src/features/chat/`:

1. **Explicit card** — the model calls `glossary_confirm_action` / `confirm_action`; `ConfirmCard.tsx`
   (l.48) and `ConfirmActionCard.tsx` (l.114) read `token = args.confirm_token` and BOTH *preview*
   (`previewAction(token)`) and *commit* (`confirmAction(token)`) with it. **This is the model-copied
   token.** If the model corrupted it, the preview fails and Confirm → 422 ("Expired — re-ask").

2. **Auto-rendered card** — `AssistantMessage.tsx` (l.61-70, 236-253) *also* renders an approve card
   directly from any completed **propose RESULT** carrying a live `confirm_token` (`proposeConfirm`, l.88,
   reads `tc.result.confirm_token` — the **authentic, server-authored** token). Its own comment says why:
   *"weaker local models routinely skip that [confirm] call, leaving the user with no way to approve. So we
   ALSO auto-render a confirm card directly from a completed propose result… independent of whether the
   model called the frontend tool."* (Locked by `AssistantMessage.autoConfirm.test.tsx`.)

## The verdict

- **Not a hard break.** The auto-render safety net means a GUI user gets a **working** approve card
  (authentic token) whenever a propose minted one — covering the model **skipping**, **corrupting**, OR
  **stalling after** the confirm. As long as `adopt_standards` ran, the user can approve.
- **A real but minor UX bug remains.** The auto-render is de-duplicated against the explicit card by
  **exact token value** (`explicitTokens.has(p.confirm_token)`, l.249). When the model corrupts the token,
  the corrupted value ≠ the authentic value, so the dedup **fails to match** and BOTH cards render — the
  model's (broken, 422s) *and* the auto one (works). The user sees a confusing duplicate; clicking the
  broken one gives "Expired — re-ask." (When the model copies correctly, they match → one card. When it
  skips, only the auto card → one card.)

## Why the harness said 75% (and the true number)

The headless driver has **no auto-render net** — it only completed the flow when the model itself called
`confirm_action` (and my authentic-token commit fired). So it measured *agent tool-following*, not
*product success*. Simulating the FE auto-render (`QG_SIM_AUTORENDER=1` — at end of turn, commit any
minted-but-unconfirmed live token = the user clicking the auto-card in a warm pass):

| Harness mode | S01 pass rate | measures |
|---|---|---|
| agent-only (model must call confirm) | ~3/4 | the agent's tool-following |
| + auto-render net (real GUI) | **5/5** | what a real user experiences |

So **S01 is effectively passing in the real product** once the rail gets the model to `adopt_standards`;
the 25% "failures" were the harness not modeling the FE's existing safety net.

## The fix that would push it past 75% — mostly already shipped

- **Already in production:** the auto-render card (the actual reason real users aren't blocked).
- **Remaining cleanup (optional, cheap), pick one:**
  1. **Server-side token repair** (preferred — mirrors the `book_id` injection the S02 baseline drove):
     when the agent calls a confirm tool, replace `args.confirm_token` with the authentic token from the
     most-recent live propose result in the turn. Removes the corruption failure AND the duplicate card;
     deterministic; helps any non-FE consumer too.
  2. **FE dedup by descriptor/recency** instead of exact token value, so a corrupted explicit card is
     recognized as the same confirm as its propose result and the authentic token is used (one card).

Neither is required to unblock users — the auto-render already does — so this is a polish item, not a P0.

## Harness change committed here

`run_discoverability_scenario.py` gains `QG_SIM_AUTORENDER` (default off). On, it replicates the FE
auto-render safety net so a headless run reflects real-GUI success. Off, it still measures pure agent
tool-following. Both numbers are useful; report which mode a run used.
