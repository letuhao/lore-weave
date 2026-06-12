# Cycle 17: Writer flow polish (FE) — ▶ M3

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** Polish the unblocked writer (C15) + resilient setup (C16) into a *guided* first-run, and make **"Continue from cursor"** a first-class action. On a fresh book: **auto-create the first scene**, **auto-pick the sole chat model** when exactly one exists, and show a **cue** that tells the writer what to do next — so a writer reaches a first draft in ≤2 clicks. "Continue from cursor" becomes a prominent, explicit action that streams continuation from the caret. **Milestone M3: write-from-scratch / continue-writing works.** FE-only.
- **Acceptance gate:** `scripts/raid/verify-cycle-17.sh` exits 0
- **Top 3 LOCKED decisions consumed:** WG-4, WG-5, writer-not-hard-blocked
- **DPS count:** 2
- **Estimated wall time:** 4h

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C15, C16
- Files expected to exist (grep-able paths): C15's Compose unblock (`AddModelCta` wiring + ready-to-draft + plain-editor→AI bridge); C16's resilient `POST /work` (setup succeeds without knowledge). Both must be DONE.

## Scope (IN)
- **Guided first-run:** fresh book → auto-create the first scene; auto-pick the chat model when exactly one is registered (no picker friction); render a contextual **cue** ("write your opening, then Generate / Continue").
- **"Continue from cursor" first-class:** a prominent explicit action that streams AI continuation from the caret position; visible without digging through menus.
- ≤2-click path from a fresh book to a first AI draft.
- `scripts/raid/verify-cycle-17.sh` (acceptance gate — the runner creates it) + Playwright screenshots (guided-to-first-draft ≤2 clicks; continue-from-cursor streaming).

## Scope (OUT — explicitly)
- **No BE changes.** Setup resilience (C16) and Generate endpoints already exist; this is FE flow only.
- No new model-registration UI — reuse C0 `AddModelCta` / C15 wiring. Auto-pick only chooses among already-registered models.
- No multi-model selection UX beyond auto-pick-the-sole-model; full model-switcher polish is out.
- No knowledge/grounding pipeline edits, no graph (C18/C19), no world container (C20+).

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: `scripts/raid/verify-cycle-17.sh` exits 0 — asserts (1) fresh-book path auto-creates a first scene, (2) sole-chat-model is auto-picked (hook/unit), (3) the first-run cue renders, (4) "Continue from cursor" action is present and wired to the streaming Generate handler.
- Lints pass: frontend `eslint` + `tsc` on touched files.
- Integration smoke: **Playwright MCP** (`claude-test@loreweave.dev`) — fresh book → guided to a first draft in ≤2 clicks; place cursor mid-text → "Continue from cursor" streams continuation. Screenshots filed with this brief. **M3 milestone screenshot.**

## DPS parallelism plan
- DPS 1: guided first-run — auto-first-scene + auto-pick-sole-model (in a hook, not a component) + first-run cue rendering (return budget: 1500 tokens summary).
- DPS 2: "Continue from cursor" — caret-anchored continuation action wired to the existing streaming Generate; explicit handler (no useEffect-for-events).

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **Auto-pick misfire:** auto-selecting a model when there are 0 or ≥2 chat models (must only auto-pick when exactly one) — wrong model or a silent block.
- **Hardcoded model name:** any literal chat-model string in the auto-pick logic instead of reading the user's registered model list.
- **useEffect-for-events:** guided-run side effects fired from `useEffect` reacting to state instead of an explicit handler at the action origin — CLAUDE.md FE rule.
- **Stateful unmount:** ternary-rendering the editor/stream panel during guided transitions, destroying the streaming connection / hook state.
- **Cursor edge cases:** "Continue from cursor" with an empty doc, caret at start, or caret in the middle — must not corrupt or duplicate text.
- **Click-count regression:** the ≤2-click promise broken by an interstitial dialog.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
- All scope items present (guided first-run: auto-scene + auto-pick-sole-model + cue; continue-from-cursor)
- No OUT items touched (no BE, no registration UI, no graph/world)
- All acceptance criteria met; `verify-cycle-17.sh` exits 0 + M3 Playwright screenshots filed
- Cross-cycle invariants not violated (provider invariant on auto-picked model; writer-not-hard-blocked)

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- Cycle row: `docs/plans/2026-06-13-creation-unblock/CYCLE_DECOMPOSITION.md` — C17 (Writer flow polish, WG-4/5, ▶ M3).
- LOCKED: `docs/plans/2026-06-13-creation-unblock/OPEN_QUESTIONS_LOCKED.md` — writer-not-hard-blocked.
- Spec: `docs/specs/2026-06-13-writer-core-flow-P0.md` (WG-4/5), `docs/specs/2026-06-13-writer-persona-use-cases-scenarios.md`.

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **Top LOCKED 1:** WG-4 → guided first-run: auto first scene + auto-pick the **sole** chat model + a next-step cue; ≤2 clicks to a first draft.
- 🔴 **Top LOCKED 2:** WG-5 → "Continue from cursor" is a first-class, explicit, streaming action — not buried.
- 🔴 **Top LOCKED 3:** Provider invariant → auto-pick reads the registered model list; NO hardcoded chat-model name.
- 🔴 **Acceptance MUST include:** `verify-cycle-17.sh` exit 0 AND M3 Playwright screenshots (guided ≤2 clicks + continue-from-cursor streaming).
- 🔴 **Do NOT touch:** any BE (C16 owns setup resilience), model-registration UI, graph/world cycles.
- 🔴 **Fresh session reminder:** this is a new `/raid 17` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + LOCKED file ONLY.
