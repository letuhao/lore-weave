# Frontend / Game-Client Architecture — Findings

- **Date:** 2026-06-20 · **Status:** ✅ COMPLETE · **Type:** read-only audit (no code changed)
- **Source:** gap-analysis §11 Task 10 (FE half). Apps: `frontend/` (player/author, 25 features) + `frontend-game/` (realtime client).

## Scorecard vs the CLAUDE.md React-MVC rules
| Rule | Verdict |
|---|---|
| 1 MVC separation (no API/logic in components) | ❌ widespread — 28 component files use react-query directly; 1 raw `fetch()` |
| 2 Never conditionally unmount stateful components | ❌ 2 High (voice overlay + settings panel ternary-mounted) |
| 3 No useEffect for event handling | 🟢 mostly (1 instance; chat uses explicit callbacks — a positive) |
| 4 Split context by update frequency | 🟢 adheres (chat splits stable vs volatile correctly) |
| 5 Server-is-SSOT / no localStorage user data | ❌ **auth token + user profile in localStorage** |
| 6 Component/hook size limits | ❌ many (worst: 699-line component, 550-line hook) |
| 7 Game-client WS lifecycle | 🟡 scaffold + demo (reconnect/close-codes stubbed) |
| 8 REST ↔ realtime state sync | ❌ designed, not wired |

## Prioritized violations
- **P1 (security) — auth token + profile in localStorage.** `frontend/src/auth.tsx` stores `lw_auth` (access+refresh tokens, L54-57) and `lw_user` (full profile, L68/79) in plain localStorage → violates "no localStorage for user data" + "server is SSOT" (stale cross-device) **and is an XSS credential-theft surface.** Should be context + httpOnly cookies; profile fetched fresh.
- **P2 — react-query directly in 28 components.** `useQuery`/`useMutation`/`useQueryClient` in components instead of hooks across knowledge (13+, worst), composition, campaigns, enrichment, wiki — incl. **destructive ops in components** (`knowledge/PrivacyTab.tsx:41,64` exportUserData/deleteAllUserData; `JobDetailPanel.tsx` pause/resume/cancel). The hook pattern exists (`useEntityMutations.ts`) — just inconsistently applied.
- **P3 — raw `fetch()` in a component.** `chat/VoiceSettingsPanel.tsx:82,107` calls `fetch()` directly (bypasses the api layer), inside `useEffect`.
- **P4 — conditional unmount of stateful components.** `chat/ChatView.tsx:203-213` ternary-mounts a **live voice/audio overlay** (deactivation destroys the pipeline mid-session); `:195-201` ternary-mounts a settings panel with debounced flush-on-unmount (closing mid-debounce drops edits). Both should stay mounted + CSS-hidden.
- **P5 — oversized:** components up to 699 lines (`knowledge/BuildGraphDialog.tsx`), ~14 over 300; hooks up to 550 (`chat/useChatMessages.ts`), 4 over the 200 cap.
- **P6 (minor) — 1 useEffect-for-event instance** (`ChatView.tsx:67-71`).

## Game client (`frontend-game/`) — SCAFFOLD + operational demo
Architecture built + spec-compliant; gameplay stubbed (phase-labeled, not untracked hacks):
- **Ticket handshake PARTIAL** — client uses a hardcoded `devToken` baked in the bundle (`config/services.ts:28`); real gateway ticket issuance unwired. OK for V0, blocking V1.
- **Reconnection PARTIAL** — token stored, manual `reconnect()` works, but **auto-reconnect/backoff stubbed** (`net/reconnect.ts` empty; `net/http-action.ts` throws "not yet implemented").
- **Forced-disconnect close codes — client GAP** — server enforces 4001/4006-4009 (kick/rate-limit/origin/cap/fingerprint); client receives the code but **doesn't branch** → would auto-reconnect into a kick.
- **REST↔realtime sync GAP** — WS dispatch doesn't call `useGameStore.setState()`; Zustand stores are schema-only → HP/MP/inventory never update from server.
- **Security note:** `lw_reconnect_token` in localStorage, not cleared on logout → use sessionStorage/cookie.

## What's done right (capture)
- **Context split (rule 4):** chat correctly separates `ChatSessionContext` (stable) from `ChatStreamContext` (volatile streaming) so SSE chunks don't re-render session consumers — with an explicit `onStreamEndRef` callback ("not a useEffect chain", the exact prescribed pattern).
- **localStorage hygiene otherwise good:** ~20 UI-pref keys are correctly per-device; real prefs write through to `/v1/me/preferences`. Only auth/profile (P1) break it.
- The failure mode is **components reaching past their own hooks**, not missing layers — the architecture exists, it's inconsistently honored.
