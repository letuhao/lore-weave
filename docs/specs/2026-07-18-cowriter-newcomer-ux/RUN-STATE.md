# RUN-STATE — Co-writer Newcomer-UX track

**Goal (committed):** spec + build fixes for ALL open dogfood findings (F2–F8; F1 already shipped).
Flow: brainstorm ✅ → spec → self-evaluate → fix spec → build slice-by-slice, **QC each slice** (live-smoke
where there's a runtime surface). Stop points: after the spec self-eval (present for sign-off) and per-slice QC.

**Branch:** feat/context-budget-law (shared checkout). **Isolated smoke:** static build on a free port +
isolated playwright session (recipe proven this session). **Model for co-writer smokes:** Gemma-4 26B QAT
(`019ebb72-27a2-72f3-a42d-d2d0e0ded179`), local, $0.

## Invariants / guardrails
- **Coordination:** a concurrent session owns studio FE (onboarding doors, structure-coherence). Before editing
  ANY file, `git status`/`git log` check for collision; commit each slice via **scoped pathspec** (never sweep
  the other agent's work). If a target file is being actively edited by them, park the slice + coordinate.
- Settings-and-config: mode/hints = per-user state, server-persisted, default-safe (Ask). No new global env flag.
- Frontend-Tool-Contract: any new closed-set arg = enum both sides + contract regen.
- Verify by EFFECT: each FE slice gets an isolated-build live-smoke; BE slices get real-DB tests + a live call.

## Slice board (done = evidence string) — post-review roster, build order
| # | Slice | Finding | Collision risk | Status | Evidence |
|---|-------|---------|----------------|--------|----------|
| 1 | N5a persona scope restraint (chat-service) | F3 | LOW (BE) | **[PARKED]** | prompt fix unit-green but FAILS live QC ×2 — see debt |
| 2 | N5b de-jargon confirm (glossary-svc + FE copy) | F3 | LOW | **[x] DONE** `bf27d203f` | 3 Go sites + FE header; live binary has new copy (3), old gone (0); go build clean |
| 3 | N6 chapter-create idempotency (+migration) | F7 | LOW (BE) | [ ] | |
| 4 | N2 per-message Insert (inject onInsert) | F4 | MED (shared chat) | **[x] DONE** `9fb1960ac` | 6 unit + live /chat: Insert renders on reply, clicks clean, fires paste+toast |
| 5 | N1 mode legibility (VERIFY first-run mode FIRST) | F2 | MED (shared chat) | [ ] | |
| 6 | N3 first-run routing | F5 | LOW | **[PARKED]** | BOTH spec+review seams wrong — register doesn't auth (see debt) |
| 7 | N4 sidebar grouping (+mobile) | F6 | HIGH (shell) | [ ] | |
| 8 | N7 pop-out + SSE console | F8 | LOW | [ ] | |
| 9 | N8 99+ badge — BE INVESTIGATE-first | F8 | — | [ ] | |

## Review outcome (2026-07-18, cold-start adversary)
Verdict was **must-fix-first**; all folded into SPEC: HIGH-1 (N3→RegisterPage not login), HIGH-2 (N5a gate glossary
shaping on `enabled_skills`, not a nonexistent intent signal), HIGH-3 (N6 DB partial-unique-index+ON CONFLICT, not
racy SELECT), MED-4 (N2 inject `onInsert` — /chat has no StudioHostProvider), MED-5 (N1 verify real first-run mode),
MED-6 (N8 split — 99+ is BE tenancy, FE already caps), LOW-8 (grep all jargon sites), LOW-9 (rail Reload = tracked
follow-up).

## Decisions / parked / debt / drift (append as you go)
- (decision) BE-first order: N5/N6 are collision-safe vs the concurrent studio-FE session; build + QC those before
  the shared-FE slices (N2/N1/N4).
- (parked) **N5a — prompt-level scope control does NOT hold (2 live Gemma QCs, both fresh books, both still
  adopted glossary standards + threw the high-impact confirm).** The changes made (co_write restraint clause,
  glossary guard-line, structural core/shaping split, pin-gated shaping skill) are unit-green and are genuine
  prompt improvements, but they do NOT achieve the behavioral goal. Root cause is TOOL-SURFACE, not prompt: the
  `glossary_adopt_standards` high-impact tool is hot-advertised on the co-writing surface (_BOOK_SCOPED/_STUDIO hot
  domains) + the "materialise" persona ⇒ the agent proactively calls it. **Real fix candidate:** stop hot-seeding
  the high-impact glossary ADOPT/shaping tools on the plain co-writing surface (require find_tools to reach them),
  OR gate the tool itself on an explicit-intent flag. That's a deeper tool_surface change with real tradeoffs
  (could hide legitimate glossary tools) — needs a decision before building. Chat-service changes are LEFT in the
  working tree + the running container (they don't regress anything; unit tests pass), pending that decision.
- (parked) **N3 — live QC found BOTH the spec seam AND the review's HIGH-1 seam are wrong.** `POST /v1/auth/register`
  returns `{user_id, verification_required:true}` and **NO tokens** — registration does NOT auto-login. So
  RegisterPage's `setTokens(res.access_token…)/navigate(...)` is already stale (undefined tokens), and routing it to
  `/onboarding` just bounces to `/login` via RequireAuth (unauthenticated). The real F5 fix is a **first-run gate at
  LOGIN** — route `hasSeenOnboarding`-unseen users to `/onboarding`, gated on the existing server pref so returning
  users don't regress (the review's MED-7 concern is avoidable by checking the signal, not routing all logins
  through the gate). Needs a post-login async pref check (resolveLoginRedirect is sync). Separately: RegisterPage's
  token assumption is a stale bug (register→verify→login now). Reverted the moot RegisterPage edit.
- (parked) N3-follow: "Write card → studio not /books list" (coordinate w/ other agent).
- (debt) LOW-9 rail Reload button manual refetch.
- (drift) N5a-2 v1: review's "gate glossary shaping on enabled_skills" — I first switched to a guard-line + co_write
  restraint (prompt-level).
- (debt→FIXING) **N5a-2 v1 FAILED LIVE QC (2026-07-18):** rebuilt chat-service + ran the dogfood repro on a fresh
  book via Gemma — the co-writer STILL adopted glossary standards + threw the high-impact confirm. Guard-line +
  restraint clause did NOT hold (26B model ignores a guard-line while the surrounding prompt still carries
  imperative "book starts empty until adopted / do not skip it" language). **Pivot to the structural split:** move
  the shaping section OUT of the always-injected glossary prompt into a pin/router-gated skill; auto path keeps only
  the lean lookup/edit core (which still lets a user do glossary work when asked, minus the proactive push). This is
  the correct fix; the earlier worry that a split "breaks NL requests" was wrong — the lean core preserves ability.
