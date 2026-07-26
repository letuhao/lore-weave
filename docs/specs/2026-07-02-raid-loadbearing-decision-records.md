# RAID load-bearing items — Decision Records (autonomous run)

**Purpose:** the user-mandated autonomous run builds the load-bearing RAID items
(C1 steering, C2 HITL, C6 checkpoints, Wave D dial) without a human POST-REVIEW in
the loop. Each gets a Decision Record here — schema, scope keys, who-writes-what,
reversibility — so the human can veto/redirect *after the fact* without archaeology.
Everything is additive + flag-safe; nothing rewrites an existing contract.

---

## DR-C1 — Steering store (07S §1a) · 2026-07-02

**What:** per-book author-written rules (story-bible-as-steering; the Cursor-rules /
Kiro-steering analog) rendered into every matching chat turn as the `steering` bucket.

**Owner service: book-service.** Steering is *authored book content* whose write
authority is exactly the book grant model — and book-service IS the E0 grant
authority (`getBookAccess` is the single resolver every service calls). Placing the
table next to the authority avoids a second tenancy implementation. (Considered:
chat-service — wrong owner, it consumes; knowledge-service — steering is authored
SSOT, not derived knowledge; glossary — lore entities, not authoring rules.)

**Schema (tenancy per CLAUDE.md checklist):**
```sql
CREATE TABLE book_steering (
  id              UUID PK DEFAULT uuidv7(),
  book_id         UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,  -- scope key
  name            TEXT NOT NULL,            -- slug-ish, #name manual trigger
  body            TEXT NOT NULL,            -- CHECK char cap 8000 (taxed every turn)
  inclusion_mode  TEXT NOT NULL DEFAULT 'always'
      CHECK (inclusion_mode IN ('always','scene_match','manual','auto')),
  match_pattern   TEXT,                     -- scene_match: case-insensitive substring/regex vs active chapter/scene title
  enabled         BOOLEAN NOT NULL DEFAULT true,
  author_user_id  UUID NOT NULL,            -- who wrote it (audit)
  created_at/updated_at TIMESTAMPTZ,
  UNIQUE (book_id, name)                    -- scoped unique — NEVER UNIQUE(name)
);
```
- **Write tier:** book owner + E0 EDIT grantees (edge #13: an edit-collaborator CAN
  author steering — same tier as editing chapters; a VIEW grantee cannot).
- **Read tier:** VIEW grant (steering renders into any collaborator's chat on that book).
- **Row caps:** ≤ 20 entries/book (soft, 422 over), body ≤ 8000 chars — steering is
  taxed every turn; keep tight (07S §1).

**Render path (chat-service):** on a book-scoped turn, fetch via internal
`GET /internal/books/{book_id}/steering` (book-service; internal token), select:
`always` ∪ (`manual` whose `#name` appears in the user message) ∪ (`scene_match`
whose pattern matches the active chapter/scene title from editor_context). Rendered
as a `<steering>` system part right after the system prompt (pinned — never compacted,
per compaction's pinned rule). Soft cap: if the selected set estimates > 2000 tokens,
log + truncate lowest-priority (manual < scene_match < always keeps).
**v1 honesty:** `auto` mode (model pulls by name) is NOT yet model-driven — v1 treats
`auto` as `manual` (trigger by #name only); the pull-tool is a follow-up. Documented
in the API description so authors aren't misled.

**Reversibility:** additive table + one fetch/render block in chat-service guarded by
"book-scoped session AND fetch succeeded" (failure → skip, turn unaffected). Dropping
the feature = dropping the render block; no data migration risk.

**FE:** deferred ONE step (a steering editor panel touches the dock catalog, which the
concurrent dockable-migration track owns right now — collision risk). The REST API is
the contract the panel will consume; tracked as `D-RAID-C1-FE-PANEL`.

---

## DR-C2 — HITL permission modes + per-tool approval (07S §5 + §4) · 2026-07-02

**Governing rule (07S):** *reversibility determines autonomy.* Today: Tier-R reads +
Tier-A (undoable writes) execute silently; Tier-S/W go through propose/confirm; FE
tools suspend for the human. The gap: (a) no **Ask** mode (read-only research surface),
(b) Tier-A server tools run with NO prompt ever (silent-write gap, 07R MED #6).

**Modes (BE contract):** a per-request `permission_mode: 'ask' | 'write'` (default
`write` = today's behavior, byte-identical for existing clients; Compose remains the
existing `disable_tools` path — NOT a third enum value, no migration of that seam).
- **Ask:** the advertised/executable server-tool surface filters to tier R only
  (+ `find_tools`; discovery still works — discovered non-R tools are NOT advertised).
  Frontend tools stay available (they are human-executed by construction — a
  `propose_edit` card's Apply IS the human gate). A tier A/W/S server tool that
  somehow gets called in Ask returns a tool-result error ("read-only mode"), never
  executes — defense in depth behind the surface filter.
- **Write:** today's surface, PLUS the §4 gate: a **Tier-A server tool not on the
  user's allowlist prompts once** (below). Tier-S/W stay on their existing
  propose/confirm — unchanged.

**Per-tool approval (the prompt-once):**
- Store: chat DB `user_tool_approvals(user_id, tool_name, created_at,
  PK(user_id, tool_name))` — per-USER tier (CLAUDE.md), no book scope (a tool's
  trustworthiness is not book-specific), no global rows.
- Flow: in Write mode, tool loop hits Tier-A server tool ∉ allowlist → **reuse the
  existing frontend-tool suspend/resume machinery** (ARCH-1 C6): suspend the run with
  a pending approval card `{tool, args, tier}`; FE renders approve-once / always-allow
  / deny; resume with the outcome → execute (+"always" writes the allowlist row) or
  feed a "denied by user" tool result so the model self-corrects. NO new transport.
- **Tier-A tools keep their undo** — approval is additive, undo unchanged.
- **Availability regression guard (the flagged risk):** mode filtering happens at
  ADVERTISE time in ONE chokepoint; a contract test pins that `write` mode advertises
  the identical surface as before the change (snapshot), so the filter cannot silently
  shrink the default surface.

**Reversibility:** `permission_mode` defaults to write; allowlist misses in ask/write
paths degrade to today's behavior on any store failure (fail-open on READS of the
allowlist — a DB blip must not brick tool calling; the suspend gate itself fails
closed only for the specific un-allowlisted call).

---

## DR-C6 — Turn checkpoints + hunk review (07S §5c) · 2026-07-02 — DESIGN DONE, BUILD DEFERRED (collision)

**Verified-first result:** the entire restore spine ALREADY EXISTS — `chapter_revisions`
snapshots every draft PATCH, `POST /v1/books/{b}/chapters/{c}/revisions/{r}/restore`
is live (server.go:279), and the FE already calls `booksApi.restoreRevision`
(RevisionHistory). **No backend work is needed** (the old classification "needs a
book-service restore endpoint" was stale).

**What C6 actually is (pure FE wiring):**
- *Turn checkpoint:* at the editor Apply seam (`tiptapEditorRef` accept/applyPolish —
  the load-bearing seam per project memory), BEFORE mutating, pin the chapter's current
  revision id and stash `{assistant_message_id → (chapter_id, revision_id)}`; render
  "Restore checkpoint" on that assistant message → confirm → existing restoreRevision.
- *Hunk review:* the `propose_edit` diff card gains per-hunk accept checkboxes; Apply
  builds the merged text from accepted hunks only (client-side; no schema change).

**Why deferred THIS run (gate #1 — collision, not effort):** the concurrent
human-in-loop dockable track is actively editing the exact seam (dirty:
`ManuscriptUnitProvider.tsx`, `EditorPanel.tsx`) — parallel edits on the load-bearing
apply seam violate the disjoint-files rule. Build lands right after their wave.
Tracked: `D-RAID-C6-FE-WIRING` (design above is the plan; ~a day of FE work).

---

## DR-D — Wave D autonomy dial (07S §10, plan D1–D5) · 2026-07-02 — DESIGN; BUILD = NEXT RUN

**Why the build stops here (the honest boundary, not a punt):** D2 stacks directly on
B2 (Plan mode) and C2 (tool allowlist), which landed THIS run **without their live
browser smokes** — the smoke substrate (FE image rebuild + browser loop) is owned by
the concurrent dockable track mid-flight. Building the L-sized autonomy FSM on two
unproven layers is exactly the stacked-risk this project's lessons forbid
(agent-gui-loop-needs-live-browser-smoke). Order of operations for the next run:
**live-smoke B2+C2 (D-B2-LIVE-SMOKE, D-RAID-C2-LIVE-SMOKE) → build D2 → D3/D4/D5.**

**D2 — the dial (L). Decisions fixed now:**
- **Run entity lives in composition-service** (`authoring_runs`): it dispatches
  composition drafting and already hosts PlanForge plan_runs (the plan the run
  executes) + the campaign-saga reference implementation lives one service over —
  reuse its driver pattern (guarded claim, per-unit fan-out, DRIVER_MAX_INFLIGHT,
  probe-reconcile breaker), do NOT invent a second saga.
- Schema: `authoring_runs(run_id, owner_user_id, book_id, plan_run_id FK, level
  CHECK (3|4), scope jsonb (chapter list — the per-unit lock fence), budget_usd cap,
  tool_allowlist jsonb (from C2's store snapshot at start), breaker_state, status FSM
  (draft→gated→running→paused→report_ready→closed), created/updated)`. Tenancy: owner
  + E0 EDIT (same tier as steering writes).
- **Start-gate** (all-or-nothing, server-enforced): approved plan (plan_runs row
  status), scope fence (reject overlap with an active run — unique partial index on
  (book_id) WHERE active, per edge #11), budget cap set, breaker armed, tool allowlist
  DECLARED (edge #5: an autonomous run may only call allowlisted side-effecting tools;
  hitting a non-allowlisted one trips the breaker, never prompts — there is no human).
- **During:** headless compaction already proven (A4); per-unit terminal events reuse
  the llm_job_terminal stream; breaker on compaction_failed / budget / critic-severe.
- **End-gate (D3):** Run Report artifact = Quality Report + per-chapter draft diffs +
  dependency-ordered accept/reject (edge #3: rejecting an upstream chapter cascade-warns
  its threaded downstream) + Revert-All via the C6 checkpoint spine.
- **D1 memory-for-canon (M):** the AGNOSTIC slice only (route pre-eviction facts through
  the existing `memory_remember_confirm` pending-facts path) — the A5 Anthropic overlay
  half stays deferred with A5 itself.
- **D4 durable/background (L):** reuse notification-service completion
  (`operation="autonomous_authoring"`) + the multi-device runs list (server-side rows,
  never localStorage). **D5 critic (L):** parallel continuity critic feeding the breaker
  (severe) or the Run Report (else) — reuse the composition verify-voting judges.
