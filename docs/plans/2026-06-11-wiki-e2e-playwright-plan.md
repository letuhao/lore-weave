# Plan — Wiki FE E2E (Playwright MCP browser pass)

**Date:** 2026-06-11 · **Branch:** `wiki/phase2-change-control` · **Goal:** a real browser pass over the wiki UI to **close the deferred wiki live-smokes** and visually confirm the 5-screen mockup↔code parity that W1–W6b shipped (all unit/code-proven, not yet browser-verified).

**Driver:** the **Playwright MCP** tools (`browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type`, `browser_fill_form`, `browser_wait_for`, `browser_take_screenshot`, `browser_console_messages`, `browser_network_requests`). This is an **agent-driven runbook**, not committed `.spec.ts` files — each scenario is a sequence of MCP calls + assertions on the accessibility snapshot.

---

## 0. Preconditions (stack + data)

1. **Stack up** — `docker compose -f infra/docker-compose*.yml up -d` (gateway :3123, FE :5174, auth, book, glossary, knowledge, provider-registry, usage-billing, postgres, redis, rabbitmq). Rebuild knowledge+glossary on the W6b code (stale-image trap — `scripts/build-stack.sh` stamps a git-SHA label). FE on :5174 (this worktree builds IPv4 `127.0.0.1`; confirm which worktree serves :5174 — see memory `frontend-serving-multi-worktree`).
2. **Flags** — `KNOWLEDGE_WIKI_GEN_ENABLED=true` on the knowledge container (LLM-gen path). Optional model: an LM Studio chat model registered in provider-registry (the prior smokes used `gemma-4-26b` / model `51ea9fd7`).
3. **Account** — `claude-test@loreweave.dev` / `Claude@Test2026`.
4. **Book** — an **indexed** book with a knowledge project + entities. The prior smokes used Dracula `019e97e4` (36 entities, 3 generated articles). Reuse it, or pick any book that has: a knowledge project (so "Knowledge graph built" shows) + ≥1 AI-generated article (for badges/results) + a way to mutate a source (entity edit → staleness).
5. **Cost guard** — prefer the **deterministic stub** path + **cancel before confirm** for dialog-only assertions; only spend on the ONE generation run (S3) with a **low `max_spend`** cap. Note: this run mutates dev data (new articles).

---

## 1. Scenarios (each maps to a slice + the live-smoke it closes)

### S1 — Login + open the wiki tab · *(smoke harness)*
- `browser_navigate` :5174 → login form → `browser_fill_form` (email/password) → submit.
- Navigate to `/books/{bookId}` → click the **Wiki** tab.
- **Assert:** the wiki sidebar renders (article list grouped by kind); no console errors (`browser_console_messages`).

### S2 — Generate dialog: W3 toggle + W6a advisory + W5 revise picker · *(no spend)*
- Click the **Sparkles** (generate) trigger → dialog opens.
- **W3:** assert the **segmented toggle** [Mẫu cố định | AI tạo sinh] (testids `wiki-gen-mode-stub/llm`), default = stub (picker hidden). Click **AI** → the model picker + spend cap appear.
- **W6a:** assert the **language** line (`wiki-gen-language`), **grounding-status** (`wiki-gen-indexed` = "knowledge graph built" on an indexed book), **budget/used** (`wiki-gen-budget`, if a monthly limit is set).
- **W5:** assert the **revise-model** picker (`wiki-gen-revise-model`, default "Same as generation").
- **Cancel** (no spend). **Closes:** the dialog-surface portions of `D-WIKI-W5-LIVE-SMOKE` (picker present).

### S3 — Generate run → job banner + W4b results + live pass (+ W5 revise model) · *(1 spend, capped)*
- Open dialog → AI mode → pick the prose model + a **different revise model** → set `max_spend` low → scope to a kind with few entities → confirm.
- **W4 (banner+detail):** assert `wiki-gen-banner` (status/progress) + `wiki-gen-detail` (per-entity rows: ✓/⊗/⏳); during the run assert `wiki-gen-detail-pass` (live "Verifying… (3/5)"); poll via `browser_wait_for` until `complete`.
- **W5:** to exercise the override, the run must produce a **canon-flagged** article (so `revise_article` fires with the revise model) — verify via the article's verify-flags / the knowledge logs. If no article flags, note `D-WIKI-W5-LIVE-SMOKE` as *partially* covered (the override path is conditional). 
- **Closes:** `D-WIKI-W4A-LIVE-SMOKE` (per-entity results + live pass on a real poll) + the run-half of `D-WIKI-W5-LIVE-SMOKE`.

### S4 — Suggestion diff (W1) · *(needs a human-edited article)*
- Precondition: edit an **AI-generated** article in the editor (human edit) → then **Regenerate** it (AI) → the clobber-guard files a `wiki_suggestion`.
- Open the article → the reader chip **"N đề xuất"** → the `WikiSuggestionReview` panel.
- **Assert:** the **AI-regen badge** + a **collapsible del/add diff** (preview + Show changes) + Accept/Reject. Accept → assert the article updates + the chip clears.
- **Closes:** the W1 reader/editor suggestion-diff flow (was unit-only).

### S5 — Knowledge-updates panel: W2 + W6b-1 jump + W6b-2b diff · *(needs a source change)*
- Precondition: **mutate a source** of a generated article — edit an entity's `short_description` (glossary) → the `entity.updated` event flips `is_knowledge_stale` + files a `wiki_staleness` row. (For a chapter source: re-publish a chapter.)
- On the wiki tab, assert the **"Cập nhật tri thức"** banner (`wiki-knowledge-updates`) → open the panel.
- **W2:** assert the **severity bar**, **cost estimate** on selection (`staleness-cost`), **dismiss-all** (`staleness-dismiss-all`), the **info banner** (ledger note), the **Rescan** button (`staleness-rescan`).
- **W6b-1:** assert the per-row **"View source"** jump (`staleness-source-jump`) → click → lands on the entity's glossary / the chapter reader.
- **W6b-2b:** assert the per-row **"View diff"** (`staleness-diff-toggle`) → click → for an article generated **after W6b-2a** (has a snapshot) assert the **red/green diff** (`staleness-diff` with del/add rows); for a pre-W6b-2 article assert the **"no snapshot"** hint. `block` rows show the **approximate** note.
- **Closes:** `D-WIKI-W6B2-LIVE-SMOKE` + `D-WIKI-W6B2B-LIVE-SMOKE` (capture→diff end-to-end) + `D-WIKI-P2-KG-SWEEP-LIVE-SMOKE` adjacent (rescan).

### S6 — Sidebar AI-count + badges (W3) · *(read-only)*
- **Assert:** the sidebar header shows **"N bài · M do AI sinh"** (AI-count split) + per-row `WikiGenBadge` (AI/needs_review/blocked) + the "Outdated" badge on a stale article.

---

## 2. Assertion style
- Prefer the **accessibility snapshot** (`browser_snapshot`) + testid/role/text matches over pixel screenshots; take a `browser_take_screenshot` per scenario for the record.
- Check `browser_console_messages` (no errors) + `browser_network_requests` (the `/v1/glossary/books/{id}/wiki/...` calls 200, the `…/staleness/{id}/diff` returns `available:true/false` as expected).

## 3. What this closes / leaves open
- **Closes (on green):** `D-WIKI-W4A-LIVE-SMOKE`, `D-WIKI-W5-LIVE-SMOKE` (if a flagged article occurs), `D-WIKI-W6B2-LIVE-SMOKE`, `D-WIKI-W6B2B-LIVE-SMOKE`; visual confirmation of W1–W6b.
- **Still open after:** `D-WIKI-W4-RESULTS-64KB` (only at >~600-entity scale — not exercised here), `D-WIKI-W6B2B-REGATHER-COST` (perf), the `.relbar` cosmetic.

## 4. Risks / notes
- **Cost** — S3 is the only token spend; cap it. S2/S4/S5 are stub/edit-driven (free).
- **Data mutation** — S3 (new articles), S4 (an edit + suggestion), S5 (an entity edit + staleness rows) mutate the dev book. Acceptable on the dev stack; note what was created so it can be cleaned.
- **Stale images** — rebuild knowledge+glossary on the W6b SHA before running (the W6b endpoints/columns won't exist on an old image → S5/W6b-2b would 404/`available:false` falsely).
- **Flake** — generation is async (LLM latency); use `browser_wait_for` with generous timeouts, not fixed sleeps.

## 5. Execution
Run as an agent-driven session with the stack up: walk S1→S6 in order (S3 before S5, since S5 needs an article to make stale). Record pass/fail + screenshots per scenario; on green, clear the corresponding live-smoke rows in `SESSION_HANDOFF.md`.
