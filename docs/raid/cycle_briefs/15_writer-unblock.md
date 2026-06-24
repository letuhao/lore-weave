# Cycle 15: Writer unblock (FE)

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** Remove the writer's "I'm stuck" cliff in the Compose surface. When no chat model is registered, show an inline **`AddModelCta`** (reuse C0's deep-link-and-return component) instead of a dead Generate button. Reframe knowledge as **OPTIONAL** — surface **"Ready to draft"** messaging once a chat model exists, with empty grounding shown as an *advisory* not a blocker. Add the **plain-editor → AI bridge** so a writer drafting plain prose can hand off to AI Generate without re-setup. Writer is NOT hard-blocked (LOCKED): write/continue needs only a chat model; embedding/rerank/knowledge degrade gracefully. FE-only.
- **Acceptance gate:** `scripts/raid/verify-cycle-15.sh` exits 0
- **Top 3 LOCKED decisions consumed:** WG-1, WG-2, WG-6
- **DPS count:** 2
- **Estimated wall time:** 3h

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C0
- Files expected to exist (grep-able paths): `frontend/src/**/AddModelCta.tsx` (C0 reusable CTA), the Compose feature dir (`frontend/src/features/compose/**` or equivalent writer/co-writer surface).

## Scope (IN)
- Empty chat-model state in Compose → render `AddModelCta` (deep-link to model registration, return to Compose). No raw "no model" error.
- **"Ready to draft"** affordance: once a chat model is resolvable, Compose signals the writer can draft now; knowledge/grounding presented as **optional enrichment**, not a precondition.
- Empty-grounding **advisory** copy (non-blocking) when no knowledge project / no graph exists — Generate still works.
- **plain-editor → AI bridge:** an explicit action from the plain prose editor to invoke AI Generate on the current draft without a separate co-writer setup wall.
- `scripts/raid/verify-cycle-15.sh` (acceptance gate — the runner creates it) + Playwright screenshot evidence (greenfield book + one chat model → write + Generate with empty grounding).

## Scope (OUT — explicitly)
- **No BE changes.** `POST /work` resilience is C16; do not touch composition endpoints here.
- No knowledge-service / grounding pipeline edits — grounding degradation already exists; this cycle only *signposts* it.
- No model-registration form changes (that is C0/C1 rerank scope) — only consume `AddModelCta`.
- No "Continue from cursor" / guided first-run — that is C17 (M3). This cycle unblocks; C17 polishes.
- No graph canvas / subgraph (C18/C19).

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: `scripts/raid/verify-cycle-15.sh` exits 0 — asserts (1) Compose renders `AddModelCta` when chat-model list is empty (component test), (2) "Ready to draft" / optional-knowledge messaging present when a chat model exists, (3) plain-editor→AI bridge handler wired (not a dead button).
- Lints pass: frontend `eslint` + `tsc` on the touched Compose files.
- Integration smoke: **Playwright MCP** (test account `claude-test@loreweave.dev`) — greenfield book, one chat model registered → reach the editor, Generate with empty grounding returns prose; screenshot filed with this brief.

## DPS parallelism plan
- DPS 1: empty-state + "Ready to draft" messaging — `AddModelCta` wiring in Compose, optional-knowledge advisory copy, chat-model-present branch (return budget: 1500 tokens summary).
- DPS 2: plain-editor → AI bridge — handler from the plain editor to AI Generate on current draft text; no useEffect-for-events (call handler directly).

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **Hard-block regression:** any branch that still disables Generate / blocks the writer when knowledge is empty — LOCKED writer-not-blocked violation.
- **Hardcoded model name:** any literal chat-model string in Compose instead of resolving the user's chat model via the registry/provider-registry path.
- **MVC drift:** API calls or business logic placed inside a component instead of a hook; useEffect used to react to a user action (must be an explicit handler).
- **Stateful unmount:** ternary-rendering a stateful editor/Generate panel that destroys hook/stream state on the empty↔ready transition — use CSS hidden or internal branching.
- **CTA round-trip:** `AddModelCta` that navigates away but doesn't return the writer to Compose.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
- All scope items present (empty-state CTA, ready-to-draft messaging, plain-editor→AI bridge)
- No OUT items touched (no BE, no knowledge pipeline, no C17 guided-run, no graph)
- All acceptance criteria met; `verify-cycle-15.sh` exits 0 + Playwright screenshot filed
- Cross-cycle invariants not violated (provider invariant on the chat model; writer-not-hard-blocked)

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- Cycle row: `docs/plans/2026-06-13-creation-unblock/CYCLE_DECOMPOSITION.md` — C15 (Writer unblock, WG-1/2/6).
- LOCKED: `docs/plans/2026-06-13-creation-unblock/OPEN_QUESTIONS_LOCKED.md` — "Writer path is not hard-blocked" + writer-locks.
- Spec: `docs/specs/2026-06-13-writer-core-flow-P0.md` (WG-1/2/6), `docs/specs/2026-06-13-writer-persona-use-cases-scenarios.md`.

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **Top LOCKED 1:** WG-1/WG-2 → writer needs ONLY a chat model; knowledge is OPTIONAL — never re-introduce a knowledge precondition wall.
- 🔴 **Top LOCKED 2:** WG-6 → empty grounding is an *advisory*, Generate must still run (FTS fallback / grounding degrades gracefully).
- 🔴 **Top LOCKED 3:** Provider invariant → resolve the chat model via the registry; NO hardcoded model name in Compose.
- 🔴 **Acceptance MUST include:** `verify-cycle-15.sh` exit 0 AND a Playwright screenshot of Generate succeeding with empty grounding.
- 🔴 **Do NOT touch:** `POST /work` BE (C16), C17 guided-first-run / continue-from-cursor, any graph/subgraph code.
- 🔴 **Fresh session reminder:** this is a new `/raid 15` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + LOCKED file ONLY.
