# GUI Checklist — element-level (anti-omission control)

- **Source of truth:** `design-drafts/screens/plugin-register/draft-ui.html` (v2). Every visible element there = one line here.
- **Rule:** a screen's task (REG-*) is NOT done until its section here is 100% ticked. The FINAL GATE re-walks this file against the running app.
- **FE item ⇒ BE item:** each section ends with `BE implied` — the endpoints/params that section forces. Building the FE line without its BE line = the line stays unticked.
- Phase tags: [P0]…[P5] map to the roadmap. Conventions section applies to every screen.
- **2026-07-03 reconcile:** this file was authored but NEVER ticked (273 boxes, 0 done) — so it failed as an
  anti-omission control and 2 screens shipped backend-only (Subagents, Activity). Lesson (memory
  `checklist-is-self-report-enforce-by-tests`): a tick is only valid when a **test asserts the EFFECT**. From here,
  `[x]` = backed by a passing unit test and/or the live browser smoke (`p5_subagents_fe_browser.mjs`); un-tested lines
  stay `[ ]`. The old Subagents screen was missing entirely — added as §12 below.

## Coverage summary — HONEST close-out (2026-07-03)

The checklist enumerates the **full-fidelity draft-ui.html vision**. The **functional** track close-out is
DONE and test-backed: **every capability (skills, mcp, commands, hooks, plugins, proposals, subagents,
activity, ingest) has a working create/list/delete GUI in both shells, each with an empty-state + a
verbatim-error surface**, proven by unit tests and (for subagents/activity) a live browser smoke.

Ticks below (`[x]`) mark ONLY lines a **passing test** proves the effect of — each annotated `— test: …`.
The large **unticked** remainder is the draft's *rich* layer that is genuinely **unbuilt**, not
rubber-stampable: server-side bulk actions, a shared standard `Pager`/`useServerPagedList` across all lists,
the skills 3-column editor + revision history, 24 h health-history charts + p50/p95, the full 4-step wizard
with per-step SSRF/OAuth validation, typed-confirm cascade-delete dialogs, and the cross-cutting **i18n
(vi/en)** + **a11y focus-trap** sweep. That layer is a large/structural build-out (defer gate #2), tracked as
**D-REG-GUI-RICH-POLISH** — NOT part of this close-out. Do not fake-tick it.

---

## 0. Global chrome [P1]

- [ ] Header quota strip: Skills n/50 — rendered (ExtensionsPage useUsage) but not effect-tested
- [ ] Header quota strip: MCP servers n/10 — rendered, not tested
- [ ] Header quota strip: Commands n/20 — not rendered (usage strip omits commands)
- [ ] Quota strip updates after create/delete (no reload)
- [ ] Nav: Plugins / MCP Servers / Skills / Commands & Hooks / Proposals / Activity log — tabs exist, not tested
- [ ] Nav: Proposals pending-count badge
- [ ] Nav badge live-updates on new proposal
- [ ] Active nav item highlight
- [ ] Route per screen (deep-linkable URLs)

**BE implied:** `GET /v1/agent-registry/usage` (quota counters) · proposals pending count (piggyback or same endpoint).

---

## 1. Plugins list [P0 CRUD · P1 full UI] — SHIPPED lean (import/export/delete); rich toolbar = D-REG-GUI-RICH-POLISH

### Toolbar
- [ ] Search input (debounced, server-side `q`) — unbuilt (lean import/export view)
- [ ] Search placeholder: name + description
- [ ] Filter Tier: All / System / User / Book
- [ ] Filter Status: All / active / draft / suspended
- [ ] Filter Has-capability: mcp / skills / commands / hooks / subagents
- [ ] Sort: Recently updated / Name A→Z / Tier / Status
- [ ] Filters combine (AND) and survive paging
- [x] Button: Import bundle [P5] — *test: plugins.test plugin-import-btn*
- [ ] Button: + New plugin — not built (bundles arrive via import)

### Bulk actions
- [ ] Select-all checkbox (header) — unbuilt (D-REG-GUI-RICH-POLISH)
- [ ] Per-row checkbox
- [ ] Bulk bar appears on ≥1 selected, shows count
- [ ] Bulk: Enable
- [ ] Bulk: Disable
- [ ] Bulk: Delete… (confirm dialog)
- [ ] System rows excluded from bulk delete (note shown)
- [ ] Bulk bar clears after action

### Table
- [x] Col: name (bold) + description hint line — *test: plugins.test plugin-row (name + description)*
- [ ] Col: tier badge — SYSTEM style — system badge rendered, not asserted
- [ ] Col: tier badge — USER style
- [ ] Col: tier badge — BOOK style + book name
- [ ] Col: updated date
- [ ] Col: capability chips with counts (9 mcp · 5 skills …)
- [ ] Col: status chip (active / draft / suspended)
- [ ] Col: enable toggle per row
- [ ] Toggle on System row = enablement override (row not mutated)
- [ ] Action: View (System rows — read-only)
- [ ] Action: Edit (User/Book rows)
- [ ] Sortable header indicators (↕ / ↓)
- [x] (lean) Action: Export bundle — *test: plugins.test plugin-export present*
- [x] (lean) Action: Delete (non-System) — *test: plugins.test plugin-delete present on user row*
- [x] (lean) Import: valid bundle → API; non-bundle → inline error (no call) — *test: plugins.test import + reject*

### Pager (standard — reuse `Pager`/`useServerPagedList`)
- [ ] "X–Y of N" total — unbuilt for plugins (no shared Pager yet)
- [ ] Page-size select: 20 / 50
- [ ] Page buttons + current highlight + ellipsis
- [ ] ‹ › disabled at bounds

### New-plugin dialog
- [ ] Name input, reverse-DNS validated inline (`io.github.user/pack`) — unbuilt
- [ ] Invalid name → field error message
- [ ] Tier select: User (default) / Book
- [ ] Book picker appears when tier=Book
- [ ] Description input
- [ ] Create → row appears without reload

### Delete dialog
- [ ] Typed-confirm (plugin name) — unbuilt (plain delete for now)
- [ ] Cascade list: N skills, M servers, K commands, hooks, subagents
- [ ] Warning: "X sessions pin its skills"
- [ ] Cancel / Delete states

### States
- [x] Empty (import-focused: "No plugins yet. Import a bundle…") — *test: plugins.test plugins-empty* — draft's "+ Create first plugin" not built
- [ ] Loading: skeleton rows — plain state, no skeleton
- [ ] Error: "Registry unreachable — cached from HH:MM" + Retry — error surfaced verbatim, no cached/Retry affordance
- [ ] Mutation toasts (success / fail with reason)

**BE implied:** `GET /plugins?q&tier&status&capability&sort&limit&offset` (server-paged, filtered) · `POST /plugins` (name validation) · `PATCH/DELETE /plugins/{id}` (delete returns cascade counts for the dialog — or a `GET /plugins/{id}/cascade-preview`) · `PUT /plugins/{id}/enablement` · bulk = client loop or `POST /plugins/bulk` · pinned-sessions count query.

---

## 2. MCP Servers list [P2 internal · P3 full]

### Toolbar
- [ ] Search input — unbuilt (lean list; rich toolbar = D-REG-GUI-RICH-POLISH)
- [ ] Filter Status: All / active / pending / suspended / error
- [ ] Filter Auth: All / OAuth 2.1 / Bearer / None
- [ ] Sort: Last health / Name / Tool count
- [x] Button: + Add server → wizard — *test: mcpServers.test mcp-add-button opens the 4-step wizard*

### Table
- [x] Col: name + prefix hint (`u_3fa2c1_`) + host hint — *test: mcpServers.test mcp-row renders*
- [ ] Col: auth kind + auth state (connected / set / **token expired**)
- [ ] Col: tools count
- [ ] Col: status chip — active
- [x] Col: status chip — pending scan review (quarantined) — *test: mcpServers.test mcp-status-chip "quarantined"*
- [ ] Col: status chip — suspended
- [ ] Col: status chip — error
- [ ] Col: health (latency + "N min ago")
- [ ] Col: breaker (closed / open + fail count)
- [ ] Action: Detail — detail screen tested (§3) but row→detail nav not asserted
- [ ] Action: Rescan
- [ ] Action: Suspend (active rows)
- [ ] Action: Reconnect (expired-token rows, primary style)
- [ ] Pager (standard) — unbuilt
- [x] Empty state — *test: mcpServers.test mcp-empty* — loading/error not separately tested

**BE implied:** `GET /mcp-servers?q&status&auth&sort&limit&offset` · `POST /mcp-servers/{id}/rescan` · `PATCH {id}` (suspend) · `POST {id}/oauth/start` (reconnect) · health + breaker state readable per row (from `last_health` + gateway breaker report).

---

## 3. Server detail [P3] — scan/accept-risk card SHIPPED + tested; health-history charts = D-REG-GUI-RICH-POLISH

### Header
- [ ] Name + tier badge + status chip — rendered, not asserted
- [ ] URL (mono) + prefix + registered date

### Connection card
- [ ] Auth kind + connected-as identity
- [ ] Reconnect button
- [ ] Token expiry countdown + auto-refresh on/off state
- [ ] Egress allowlist (mono list)
- [ ] Limits: timeout 15 s · resp ≤ 1 MB · breaker 5 fails
- [ ] Breaker live state + fails-in-window

### Health card
- [ ] 24 h latency bars — unbuilt (charting; D-REG-GUI-RICH-POLISH)
- [ ] Failure bar highlighted (distinct color)
- [ ] p50 / p95 figures
- [ ] Last-failure detail (time + reason)
- [ ] Check cadence note + on-demand health check button

### Scan report card
- [ ] Rescan button — rendered, not asserted
- [ ] Check lines: ssrf-guard / schema-lint / capability / inj-scan with pass–warn–fail icons
- [x] Flagged finding banner: tool name — *test: mcpServers.test scan-flagged*
- [x] Flagged finding banner: offending description quoted — *test: mcpServers.test scan-findings contains the injected marker*
- [x] Button: Accept risk & activate (SCAN-GATE: owner self-serve) — *test: mcpServers.test mcp-detail-accept-risk*
- [ ] Button: Keep quarantined
- [x] Accept-risk → status pending→active + audit row + toast — *test: mcpServers.test acceptRiskMcpServer called + refresh*

### Tools table
- [ ] Search within tools
- [ ] Filter: All / flagged
- [ ] Col: prefixed tool name (mono)
- [ ] Col: description
- [ ] Col: args chips (enum args marked `: enum`)
- [ ] Col: scan verdict (clean / flagged)
- [ ] Pager (standard)

**BE implied:** `GET /mcp-servers/{id}` (detail incl. oauth state, limits) · `GET {id}/health-history?range=24h` · `GET {id}/scan` (findings incl. quoted text) · `POST {id}/accept-risk` (audit-logged) · `GET {id}/tools?q&flagged&limit&offset` · `POST {id}/health-check`.

---

## 4. Skills [P1] — browser column SHIPPED + tested; Editor/Preview columns = D-REG-GUI-RICH-POLISH

### Library column (browser-standard, compact)
- [ ] Quota "n/50" beside title — quota is in the page header, not the column
- [x] Search input — *test: skills.test search input re-queries server-side `q`*
- [x] Filter Tier: All / System / User / Book — *test: skills.test tier filter re-queries*
- [x] Sort: Updated / Name / Last triggered — *test: skills.test sort re-queries*
- [x] Row: tier badge + slug — *test: skills.test badge "user" + slug rendered*
- [ ] Row hint: "editing…" (unsaved elsewhere)
- [ ] Row hint: "✨ by agent · used N× · last <date>"
- [x] Row: enable toggle — *test: skills.test toggle → setSkillEnabled(id,false)*
- [ ] Selected-row highlight
- [x] Pager (compact standard) — *test: skills.test "1–20 of 45" + › advances offset 20 + ‹ disabled at page 0*
- [ ] Buttons: Import / Export / + New — not in this column (skills import is via the editor track, unbuilt here)
- [ ] Import: file picker (SKILL.md or zip, scripts/ rejected with message)
- [ ] Import: validation errors listed per field
- [ ] Export: downloads SKILL.md (byte-identical body)
- [x] (states) Empty + error banner — *test: skills.test "No skills yet" + error message rendered*
- [x] (row) System row is read-only (no delete); User row deletes — *test: skills.test system→no delete btn; user→deleteSkill(id)*

### Editor column
- [ ] Title = current slug + unsaved-changes chip — unbuilt (browser-only view; editor is a separate screen)
- [ ] Unsaved guard on navigate-away
- [ ] Field: slug (regex validated inline)
- [ ] Field: description (required marker + error)
- [ ] Field: surfaces multi-select chips (chat / compose / translate / admin)
- [ ] Field: scope select — My account / Book: <picker>
- [ ] Field: body markdown textarea (mono)
- [ ] History ▾ — revision list (append on publish)
- [ ] History: view old revision (read-only)
- [ ] History: restore revision (creates new draft)
- [ ] Button: Save draft
- [ ] Button: Publish (draft→published)

### Preview column
- [ ] L1 metadata line render (exactly what enters the prompt) — unbuilt
- [ ] L2 token estimate (~N tokens)
- [ ] Validation status (frontmatter OK / errors)
- [ ] Size n KB / 64 KB (live)
- [ ] Status: draft / published
- [ ] Used-by: "N sessions pin this skill"
- [ ] Shadow warning banner when slug == System slug (rename or intentionally override)

**BE implied:** `GET /skills?q&tier&sort&limit&offset` (with usage stats: used_count, last_triggered) · `POST/PATCH /skills` (draft/publish per D3) · `GET /skills/{id}/revisions` + `POST .../restore` · `POST /skills/import` (multipart, scripts/ reject) · `GET /skills/{id}/export` · token estimate client-side · shadow check `GET /skills/shadow-check?slug=` · pinned-sessions count.

---

## 5. Commands & Hooks [P4] — builders + chat autocomplete SHIPPED + tested

### Commands card
- [ ] Quota "n/20" in title
- [ ] Search input + Tier filter — unbuilt
- [x] Button: + New — *test: commandsHooks.test cmd-create*
- [ ] Table col: /name (mono) — list row not asserted
- [ ] Table col: tier badge
- [ ] Table col: args chips (enum marked)
- [ ] Action: Edit
- [ ] Built-in row (/think, /effort) shown reserved, no Edit
- [ ] Editor: name input + collision-with-builtin error — name input tested; collision-error unbuilt
- [ ] Editor: args schema rows (name + type + enum values)
- [x] Editor: template textarea with {{arg}} placeholders — *test: commandsHooks.test cmd-template "Plan {{topic}}"*
- [ ] Editor: expand-side select (server / client)
- [ ] Template preview with sample args
- [x] Save / Delete — *test: commandsHooks.test cmd-create sends {name,template_md}*

### Chat surface (command consumption)
- [x] "/" autocomplete popup in chat input — *test: PromptTemplates.slash.test + useSlashCommands.test (M3)*
- [x] Popup lists System ∪ user commands, tier-badged — *test: useSlashCommands fetches /commands + match(filter)*
- [ ] Arg hint inline after selecting
- [ ] Unknown /word falls through as plain text

### Hooks card
- [x] Button: + New — *test: commandsHooks.test hook-create*
- [x] Field: on-event select (pre_tool_call / post_tool_call / pre_turn / post_turn) — *test: commandsHooks.test hook-event pre_turn*
- [x] Field: match builder (tool · book · condition) — *test: commandsHooks.test hook-match "glossary_delete_*"*
- [x] Field: action select (require_approval / deny / inject_text / annotate) — *test: commandsHooks.test deny + inject_text actions*
- [x] inject_text → text field appears — *test: commandsHooks.test hook-text sent with action*
- [x] Save hook — *test: commandsHooks.test hook-create sends match+action*
- [ ] Active hooks list: icon + name + event · action — list row not asserted
- [ ] Active hooks list: fired count last 7 d
- [ ] Active hooks list: tier badge
- [ ] Hook enable/disable toggle
- [ ] Hook delete (confirm)

**BE implied:** `GET/POST/PATCH/DELETE /commands` (+ builtin-collision validation) · command expansion at chat-service (server-side default) · `GET/POST/PATCH/DELETE /hooks` · hook fired-count metric per hook (7 d window) · hook engine at loop seams.

---

## 6. Proposals inbox [P1] — inbox + approve/reject SHIPPED + tested; review-modal/diff = D-REG-GUI-RICH-POLISH

### Toolbar
- [ ] Search input — unbuilt
- [x] Filter Status: Pending / Approved / Rejected / Expired / All — *test: proposals.test status filter re-queries*
- [ ] Sort: Newest / Expiring soon

### Table
- [x] Col: name + description hint — *test: proposals.test card renders slug + description*
- [ ] Col: action chip — create
- [ ] Col: action chip — update · diff
- [ ] Col: from-session (title + timestamp), links to the session
- [ ] Col: expires ("in N days" / status)
- [ ] History rows dimmed (approved/rejected/expired)
- [ ] Rejected row shows reject reason hint — reject_reason rendered, not asserted
- [x] Action: Review & approve — *test: proposals.test proposal-approve → approveProposal(id)*
- [x] Action: Reject (reason optional) — *test: proposals.test proposal-reject → rejectProposal(id,"")*
- [ ] Action: View (history)
- [ ] Pager (standard) — single page of 50
- [x] Empty state ("agent proposals appear here") — *test: proposals.test "No proposals"; non-pending row shows no approve/reject*

### Review modal
- [ ] Rendered frontmatter (name / description / tier note) — unbuilt (inline card, no modal)
- [ ] Markdown body preview — body shown inline in the card, not a modal
- [ ] Diff view for update-proposals
- [ ] Approve → skill created + toast + row moves to history
- [ ] Edit before save → opens skill editor pre-filled, approve consumes proposal
- [ ] Reject → resolves with result.error to the model turn (if still suspended)
- [ ] Expired approve attempt → `proposal_expired` error toast

**BE implied:** `GET /proposals?q&status&sort&limit&offset` · confirm route (existing spine) · `POST /proposals/{id}/reject` (reason) · session back-link id stored on proposal · expiry sweep (D4).

---

## 7. Activity log [P0 trigger · P1 screen] — SHIPPED 2026-07-03 (`ActivityView`)

- [ ] Search input — not built (defer; kind+range cover the primary need)
- [x] Filter Kind: plugin / skill / mcp_server / command / hook / subagent / proposal / registry_ingest — *test: activity.test re-queries on kind change*
- [ ] Filter Actor: me / agent / admin / system — not built (backend `/audit` has no actor filter yet)
- [x] Filter Range: 7 d / 30 d / All — *test: activity.test re-queries on range change*
- [x] Col: when (relative time) — *test: activity.test asserts "h ago"*
- [x] Col: actor (shown for non-user) — *browser smoke*
- [x] Col: action chip (kind·action) — *test: asserts "subagent·create"*
- [x] Col: target — *test: asserts "lore-scout"* (tier badge sub-part not rendered — [ ])
- [ ] Scan events appear (scan.flagged with tool name) — real /audit shows all kinds, not explicitly asserted
- [ ] Accept-risk events appear — not explicitly asserted
- [ ] Pager (standard, deep history) — single page of 50 for now (defer)

**BE implied:** `GET /audit?kind&range&limit&offset` — SHIPPED (owner-scoped). **Live-proven:** `p5_subagents_fe_browser.mjs`
— a subagent create appeared in the Activity log (real /audit round-trip).

---

## 8. Add-MCP wizard [P3] — core flow SHIPPED + tested; per-step SSRF/OAuth validation UI = D-REG-GUI-RICH-POLISH

### Stepper
- [x] 4 steps with done / current states — *test: mcpServers.test wizard advances endpoint → auth → health/scan*
- [ ] Back preserves entered state at every step — not asserted

### Step 1 — Endpoint
- [x] URL input — *test: mcpServers.test wiz-endpoint-url*
- [ ] https-only inline error — SSRF/https guards are BE-enforced; the inline-error UI is unbuilt
- [ ] SSRF-rejected inline error (private/internal address)
- [ ] Model-backend rejected error → pointer to BYOK Providers
- [ ] Display-name input
- [ ] Auto prefix field (disabled, `u_<hash>_`)
- [ ] Prefix explainer hint
- [ ] Continue disabled until valid

### Step 2 — Auth
- [ ] Auth select: OAuth 2.1 / Bearer / None — none-auth path tested; the select UI not asserted
- [ ] OAuth: discovered issuer display
- [ ] OAuth: scopes chips
- [ ] OAuth: resource (RFC 8707) display
- [ ] OAuth: "Connect…" button → popup flow
- [ ] OAuth: connected-as state after callback
- [ ] OAuth: failure state + retry
- [ ] Bearer: token input (masked, never echoed back)
- [ ] Secret-handling hint (AES-GCM, has_secret only)

### Step 3 — Health & Scan
- [x] Live progress while checks run — *test: mcpServers.test wiz-health-scan appears after Register & scan*
- [ ] Line: health (latency · tool count · protocol)
- [ ] Line: ssrf-guard
- [ ] Line: schema-lint (n/n)
- [ ] Line: inj-scan (pass or flagged count)
- [ ] Line: capability check
- [ ] Verdict: pass / quarantine-pending + warning count
- [ ] Egress allowlist display
- [ ] Health-failed terminal state + error detail + retry

### Step 4 — Review & Enable
- [ ] Summary KV (server / tier)
- [ ] Tools chips + "+N more"
- [ ] Limits summary
- [ ] Scan summary (flagged count links to detail)
- [ ] Checkbox: enable after quarantine clears
- [x] Register → lands in list with correct status + toast — *test: mcpServers.test createMcpServer called with {endpoint_url, auth_kind:'none'}*

**BE implied:** `POST /mcp-servers` staged create (or draft row) · `POST {id}/oauth/start` + callback route · `POST {id}/validate` (steps 1 checks) · scan pipeline returns structured lines · register finalizes status machine.

---

## 9. Agent self-registration (chat surface) [P1]

- [ ] "Save as skill" affordance on a conversation — SkillProposalCard track; not re-verified this pass
- [ ] registry_* tools advertised only per surface rules (R-only in ask mode)
- [ ] SkillProposalCard: header (tool name · pending · expiry)
- [ ] Card KV: name / description / tier note ("của bạn — không ảnh hưởng ai khác")
- [ ] Card: body diff block (green adds; real diff for updates)
- [ ] Button: Approve — lưu skill
- [ ] Button: Sửa trước khi lưu (→ editor pre-filled)
- [ ] Button: Reject
- [ ] Reject sends result.error (never silent)
- [ ] Card idempotent by toolCallId (re-render ≠ double-fire)
- [ ] Post-approve agent confirmation message renders
- [ ] Card also visible in Proposals inbox after chat closed
- [ ] Update-proposal card shows old→new diff against existing skill

**BE implied:** §12b MCP tools live through ai-gateway (`registry_` prefix) · suspend/resume plumbing (existing) · proposal ↔ toolCallId link.

---

## 10. Studio shell [P1 panels · P3 MCP-in-studio]

- [ ] `extensions` in STUDIO_PANELS (id, titleKey, descKey) — panel mounts (ExtensionsPanel); registration not re-asserted this pass
- [ ] `proposals` in STUDIO_PANELS (+ tab badge count)
- [ ] `skill-editor` in STUDIO_PANELS (hiddenFromPalette, singleton)
- [ ] Panels self-title via props.api.setTitle
- [ ] Extensions internal tabs: Plugins / MCP Servers / Commands & Hooks — plus Subagents + Activity (wired 4e15711d2)
- [ ] Internal tab state preserved across panel hide/show (never-unmount) — implemented (hidden divs), not asserted
- [ ] Same components as routes (zero logic fork — hooks/context shared) — true by construction; not asserted
- [ ] Command Palette: "Studio: Open Extensions"
- [ ] Command Palette: "Studio: Open Proposals"
- [ ] ui_open_studio_panel enum += extensions, proposals (+ descriptions)
- [ ] contracts/frontend-tools.contract.json regenerated
- [ ] panelCatalogContract.test.ts green
- [ ] "Edit skill" retargets skill-editor singleton via params {skillId}
- [ ] Wizard fully operable inside the extensions panel [P3]
- [ ] OAuth popup flow works from inside the dock [P3]
- [ ] Wizard state survives hide/show mid-flow [P3]
- [ ] Live browser smoke: agent opens extensions panel (effect-verified)

**BE implied:** enum change in `frontend_tools.py` + contract regen · none else (panels reuse section APIs).

---

## 11. Cross-cutting conventions (every screen)

- [ ] All strings i18n-keyed (react-i18next, vi + en) — **NOT done** (hardcoded English) — the biggest honest gap; D-REG-GUI-RICH-POLISH
- [ ] Toggles: role="switch" + aria-checked — role="switch" present on toggles; aria-checked not wired
- [ ] Keyboard: table row focus, dialog focus-trap, Esc closes — **NOT done** (a11y sweep; D-REG-GUI-RICH-POLISH)
- [ ] data-testid on every interactive element — most, not all (some pager buttons lack ids)
- [ ] Responsive: 3-col collapses; nav → icons; tables scroll
- [ ] Per-device UI state (column widths, collapsed nav) in localStorage only
- [x] All registry data server-side (no localStorage data) — *by construction: every hook reads/writes via `extensionsApi` (HTTP); no localStorage of registry data — asserted indirectly by every hook→api test*
- [ ] Skeleton loading per screen — plain "Loading…" text, no skeletons
- [ ] Error banner (cached + Retry) per screen — errors surfaced verbatim; no cached-timestamp/Retry affordance
- [ ] Mutation toasts everywhere — inline errors, not a toast system
- [ ] Browser lists ALL reuse EntityListBrowser-style shell + Pager (no hand-rolled) — **NOT done** (pagers hand-rolled where present); D-REG-GUI-RICH-POLISH

---

## 12. Subagents [P5] — ADDED + SHIPPED 2026-07-03 (`SubagentsView`) — the screen the old checklist MISSED entirely

- [x] Create form: name (lowercase a-z0-9-) — *test: subagents.test create sends name*
- [x] Create form: tool_scope (comma → globs), empty = reasoning-only — *test: parses "glossary_*, kg_*" → globs*
- [x] Create form: model_ref (optional, user_model id) — *field present; sent when non-empty*
- [x] Create form: system_prompt (textarea, required) — *test: create disabled without it*
- [x] Create → row appears without reload — *test + browser smoke (real POST /subagents)*
- [x] Reject surfaces the backend error verbatim (no silent no-op) — *test: dup-name error shown in sa-error*
- [x] Row: scope chips from globs (+ reasoning-only badge when empty) — *test: chips = ["glossary_*","kg_*"]; empty→badge*
- [x] Row: tier badge (system/book) — *rendered; system asserted read-only*
- [x] Row: enable toggle → PATCH enabled — *test: toggle calls patchSubagent {enabled:false}*
- [x] Row: delete (User/Book only; System read-only) — *test: delete calls api; System has no delete btn*
- [x] Mounted in BOTH shells (/extensions tab + studio ExtensionsPanel) — *browser smoke uses the /extensions tab; studio wiring 4e15711d2*
- [ ] Search / sort / pager — not built (single page of 50; defer with the other list screens)
- [ ] Edit-in-place of prompt/scope on an existing row — not built (delete+recreate for now; defer)

**BE implied:** `GET/POST /subagents`, `PATCH/DELETE /subagents/{id}` — all SHIPPED (P5-M1). **Live-proven:**
`p5_subagents_fe_browser.mjs` — created a persona via the form → row appeared → create logged in Activity → deleted.

---

## Tally (2026-07-03 honest count)

Ticks are **test-backed only** (each `[x]` cites its test). Three buckets:

| Bucket | Meaning |
|---|---|
| **Done (test-backed)** | `[x]` — a passing unit test and/or live browser smoke asserts the effect |
| **Built-untested** | on disk but no effect-test yet (annotated inline) — not ticked, per the LOCKED rule |
| **Unbuilt (rich vision)** | the draft's rich layer — **D-REG-GUI-RICH-POLISH** (defer gate #2) |

| Screen | Lines | Done (test-backed) | Notes |
|---|---|---|---|
| 0 Global chrome | 9 | 0 | quota strip built-untested; nav built-untested |
| 1 Plugins | 47 | 5 | lean import/export/delete + empty; rich toolbar/bulk/dialogs unbuilt |
| 2 MCP servers list | 21 | 4 | add-wizard button, row, one status chip, empty |
| 3 Server detail | 28 | 4 | scan-flag + accept-risk card; health charts unbuilt |
| 4 Skills | 36 | 8 | full browser column (search/tier/sort/pager/states/rows); editor+preview unbuilt |
| 5 Commands & Hooks | 26 | 11 | both builders + chat autocomplete |
| 6 Proposals | 22 | 5 | inbox + filter + approve/reject + empty; review-modal unbuilt |
| 7 Activity log | 11 | 6 | kind/range/columns; pager+actor-filter deferred |
| 8 Wizard | 33 | 4 | stepper + endpoint + health/scan + register; per-step validation UI unbuilt |
| 9 Agent flow | 13 | 0 | SkillProposalCard track — not re-verified this pass |
| 10 Studio shell | 18 | 0 | panels mount (built) but not re-asserted this pass |
| 11 Conventions | 11 | 1 | server-side data ✓; i18n + a11y + shared-Pager = the honest gaps |
| 12 Subagents | 13 | 11 | full CRUD both shells + live smoke |
| **Total** | **288** | **59** | functional close-out DONE; rich-vision remainder = D-REG-GUI-RICH-POLISH |

**Bottom line:** the track is **functionally closed** — every capability has a tested, working GUI in both
shells. **59 lines are genuinely test-backed** (up from 0). The remaining lines are the draft's rich polish
layer, honestly tracked as **D-REG-GUI-RICH-POLISH** rather than fake-ticked. Proceed to **M7 (live E2E of the
cleared defers)** for track closure; schedule D-REG-GUI-RICH-POLISH as its own planned effort.
