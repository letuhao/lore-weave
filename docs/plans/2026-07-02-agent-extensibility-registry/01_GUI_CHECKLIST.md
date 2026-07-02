# GUI Checklist — element-level (anti-omission control)

- **Source of truth:** `design-drafts/screens/plugin-register/draft-ui.html` (v2). Every visible element there = one line here.
- **Rule:** a screen's task (REG-*) is NOT done until its section here is 100% ticked. The FINAL GATE re-walks this file against the running app.
- **FE item ⇒ BE item:** each section ends with `BE implied` — the endpoints/params that section forces. Building the FE line without its BE line = the line stays unticked.
- Phase tags: [P0]…[P5] map to the roadmap. Conventions section applies to every screen.

---

## 0. Global chrome [P1]

- [ ] Header quota strip: Skills n/50
- [ ] Header quota strip: MCP servers n/10
- [ ] Header quota strip: Commands n/20
- [ ] Quota strip updates after create/delete (no reload)
- [ ] Nav: Plugins / MCP Servers / Skills / Commands & Hooks / Proposals / Activity log
- [ ] Nav: Proposals pending-count badge
- [ ] Nav badge live-updates on new proposal
- [ ] Active nav item highlight
- [ ] Route per screen (deep-linkable URLs)

**BE implied:** `GET /v1/agent-registry/usage` (quota counters) · proposals pending count (piggyback or same endpoint).

---

## 1. Plugins list [P0 CRUD · P1 full UI]

### Toolbar
- [ ] Search input (debounced, server-side `q`)
- [ ] Search placeholder: name + description
- [ ] Filter Tier: All / System / User / Book
- [ ] Filter Status: All / active / draft / suspended
- [ ] Filter Has-capability: mcp / skills / commands / hooks / subagents
- [ ] Sort: Recently updated / Name A→Z / Tier / Status
- [ ] Filters combine (AND) and survive paging
- [ ] Button: Import bundle [P5]
- [ ] Button: + New plugin

### Bulk actions
- [ ] Select-all checkbox (header)
- [ ] Per-row checkbox
- [ ] Bulk bar appears on ≥1 selected, shows count
- [ ] Bulk: Enable
- [ ] Bulk: Disable
- [ ] Bulk: Delete… (confirm dialog)
- [ ] System rows excluded from bulk delete (note shown)
- [ ] Bulk bar clears after action

### Table
- [ ] Col: name (bold) + description hint line
- [ ] Col: tier badge — SYSTEM style
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

### Pager (standard — reuse `Pager`/`useServerPagedList`)
- [ ] "X–Y of N" total
- [ ] Page-size select: 20 / 50
- [ ] Page buttons + current highlight + ellipsis
- [ ] ‹ › disabled at bounds

### New-plugin dialog
- [ ] Name input, reverse-DNS validated inline (`io.github.user/pack`)
- [ ] Invalid name → field error message
- [ ] Tier select: User (default) / Book
- [ ] Book picker appears when tier=Book
- [ ] Description input
- [ ] Create → row appears without reload

### Delete dialog
- [ ] Typed-confirm (plugin name)
- [ ] Cascade list: N skills, M servers, K commands, hooks, subagents
- [ ] Warning: "X sessions pin its skills"
- [ ] Cancel / Delete states

### States
- [ ] Empty: icon + headline + "+ Create first plugin" + "Import bundle"
- [ ] Loading: skeleton rows
- [ ] Error: "Registry unreachable — cached from HH:MM" + Retry
- [ ] Mutation toasts (success / fail with reason)

**BE implied:** `GET /plugins?q&tier&status&capability&sort&limit&offset` (server-paged, filtered) · `POST /plugins` (name validation) · `PATCH/DELETE /plugins/{id}` (delete returns cascade counts for the dialog — or a `GET /plugins/{id}/cascade-preview`) · `PUT /plugins/{id}/enablement` · bulk = client loop or `POST /plugins/bulk` · pinned-sessions count query.

---

## 2. MCP Servers list [P2 internal · P3 full]

### Toolbar
- [ ] Search input
- [ ] Filter Status: All / active / pending / suspended / error
- [ ] Filter Auth: All / OAuth 2.1 / Bearer / None
- [ ] Sort: Last health / Name / Tool count
- [ ] Button: + Add server → wizard

### Table
- [ ] Col: name + prefix hint (`u_3fa2c1_`) + host hint
- [ ] Col: auth kind + auth state (connected / set / **token expired**)
- [ ] Col: tools count
- [ ] Col: status chip — active
- [ ] Col: status chip — pending scan review
- [ ] Col: status chip — suspended
- [ ] Col: status chip — error
- [ ] Col: health (latency + "N min ago")
- [ ] Col: breaker (closed / open + fail count)
- [ ] Action: Detail
- [ ] Action: Rescan
- [ ] Action: Suspend (active rows)
- [ ] Action: Reconnect (expired-token rows, primary style)
- [ ] Pager (standard)
- [ ] Empty / loading / error states

**BE implied:** `GET /mcp-servers?q&status&auth&sort&limit&offset` · `POST /mcp-servers/{id}/rescan` · `PATCH {id}` (suspend) · `POST {id}/oauth/start` (reconnect) · health + breaker state readable per row (from `last_health` + gateway breaker report).

---

## 3. Server detail [P3]

### Header
- [ ] Name + tier badge + status chip
- [ ] URL (mono) + prefix + registered date

### Connection card
- [ ] Auth kind + connected-as identity
- [ ] Reconnect button
- [ ] Token expiry countdown + auto-refresh on/off state
- [ ] Egress allowlist (mono list)
- [ ] Limits: timeout 15 s · resp ≤ 1 MB · breaker 5 fails
- [ ] Breaker live state + fails-in-window

### Health card
- [ ] 24 h latency bars
- [ ] Failure bar highlighted (distinct color)
- [ ] p50 / p95 figures
- [ ] Last-failure detail (time + reason)
- [ ] Check cadence note + on-demand health check button

### Scan report card
- [ ] Rescan button
- [ ] Check lines: ssrf-guard / schema-lint / capability / inj-scan with pass–warn–fail icons
- [ ] Flagged finding banner: tool name
- [ ] Flagged finding banner: offending description quoted
- [ ] Button: Accept risk & activate (SCAN-GATE: owner self-serve)
- [ ] Button: Keep quarantined
- [ ] Accept-risk → status pending→active + audit row + toast

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

## 4. Skills [P1]

### Library column (browser-standard, compact)
- [ ] Quota "n/50" beside title
- [ ] Search input
- [ ] Filter Tier: All / System / User / Book
- [ ] Sort: Updated / Name / Last triggered
- [ ] Row: tier badge + slug
- [ ] Row hint: "editing…" (unsaved elsewhere)
- [ ] Row hint: "✨ by agent · used N× · last <date>"
- [ ] Row: enable toggle
- [ ] Selected-row highlight
- [ ] Pager (compact standard)
- [ ] Buttons: Import / Export / + New
- [ ] Import: file picker (SKILL.md or zip, scripts/ rejected with message)
- [ ] Import: validation errors listed per field
- [ ] Export: downloads SKILL.md (byte-identical body)

### Editor column
- [ ] Title = current slug + unsaved-changes chip
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
- [ ] L1 metadata line render (exactly what enters the prompt)
- [ ] L2 token estimate (~N tokens)
- [ ] Validation status (frontmatter OK / errors)
- [ ] Size n KB / 64 KB (live)
- [ ] Status: draft / published
- [ ] Used-by: "N sessions pin this skill"
- [ ] Shadow warning banner when slug == System slug (rename or intentionally override)

**BE implied:** `GET /skills?q&tier&sort&limit&offset` (with usage stats: used_count, last_triggered) · `POST/PATCH /skills` (draft/publish per D3) · `GET /skills/{id}/revisions` + `POST .../restore` · `POST /skills/import` (multipart, scripts/ reject) · `GET /skills/{id}/export` · token estimate client-side · shadow check `GET /skills/shadow-check?slug=` · pinned-sessions count.

---

## 5. Commands & Hooks [P4]

### Commands card
- [ ] Quota "n/20" in title
- [ ] Search input + Tier filter
- [ ] Button: + New
- [ ] Table col: /name (mono)
- [ ] Table col: tier badge
- [ ] Table col: args chips (enum marked)
- [ ] Action: Edit
- [ ] Built-in row (/think, /effort) shown reserved, no Edit
- [ ] Editor: name input + collision-with-builtin error
- [ ] Editor: args schema rows (name + type + enum values)
- [ ] Editor: template textarea with {{arg}} placeholders
- [ ] Editor: expand-side select (server / client)
- [ ] Template preview with sample args
- [ ] Save / Delete

### Chat surface (command consumption)
- [ ] "/" autocomplete popup in chat input
- [ ] Popup lists System ∪ user commands, tier-badged
- [ ] Arg hint inline after selecting
- [ ] Unknown /word falls through as plain text

### Hooks card
- [ ] Button: + New
- [ ] Field: on-event select (pre_tool_call / post_tool_call / pre_turn / post_turn)
- [ ] Field: match builder (tool · book · condition)
- [ ] Field: action select (require_approval / deny / inject_text / annotate)
- [ ] inject_text → text field appears
- [ ] Save hook
- [ ] Active hooks list: icon + name + event · action
- [ ] Active hooks list: fired count last 7 d
- [ ] Active hooks list: tier badge
- [ ] Hook enable/disable toggle
- [ ] Hook delete (confirm)

**BE implied:** `GET/POST/PATCH/DELETE /commands` (+ builtin-collision validation) · command expansion at chat-service (server-side default) · `GET/POST/PATCH/DELETE /hooks` · hook fired-count metric per hook (7 d window) · hook engine at loop seams.

---

## 6. Proposals inbox [P1]

### Toolbar
- [ ] Search input
- [ ] Filter Status: Pending / Approved / Rejected / Expired / All
- [ ] Sort: Newest / Expiring soon

### Table
- [ ] Col: name + description hint
- [ ] Col: action chip — create
- [ ] Col: action chip — update · diff
- [ ] Col: from-session (title + timestamp), links to the session
- [ ] Col: expires ("in N days" / status)
- [ ] History rows dimmed (approved/rejected/expired)
- [ ] Rejected row shows reject reason hint
- [ ] Action: Review & approve
- [ ] Action: Reject (reason optional)
- [ ] Action: View (history)
- [ ] Pager (standard)
- [ ] Empty state ("agent proposals appear here")

### Review modal
- [ ] Rendered frontmatter (name / description / tier note)
- [ ] Markdown body preview
- [ ] Diff view for update-proposals
- [ ] Approve → skill created + toast + row moves to history
- [ ] Edit before save → opens skill editor pre-filled, approve consumes proposal
- [ ] Reject → resolves with result.error to the model turn (if still suspended)
- [ ] Expired approve attempt → `proposal_expired` error toast

**BE implied:** `GET /proposals?q&status&sort&limit&offset` · confirm route (existing spine) · `POST /proposals/{id}/reject` (reason) · session back-link id stored on proposal · expiry sweep (D4).

---

## 7. Activity log [P0 trigger · P1 screen]

- [ ] Search input
- [ ] Filter Kind: plugin / skill / mcp_server / command / hook / enablement / proposal
- [ ] Filter Actor: me / agent (approved) / admin / system
- [ ] Filter Range: 7 d / 30 d / All
- [ ] Col: when
- [ ] Col: actor
- [ ] Col: action chip (kind.verb)
- [ ] Col: target + tier badge / status result
- [ ] Scan events appear (scan.flagged with tool name)
- [ ] Accept-risk events appear
- [ ] Pager (standard, deep history)

**BE implied:** `GET /audit?q&kind&actor&range&limit&offset` over the trigger-projection table.

---

## 8. Add-MCP wizard [P3]

### Stepper
- [ ] 4 steps with done / current states
- [ ] Back preserves entered state at every step

### Step 1 — Endpoint
- [ ] URL input
- [ ] https-only inline error
- [ ] SSRF-rejected inline error (private/internal address)
- [ ] Model-backend rejected error → pointer to BYOK Providers
- [ ] Display-name input
- [ ] Auto prefix field (disabled, `u_<hash>_`)
- [ ] Prefix explainer hint
- [ ] Continue disabled until valid

### Step 2 — Auth
- [ ] Auth select: OAuth 2.1 / Bearer / None
- [ ] OAuth: discovered issuer display
- [ ] OAuth: scopes chips
- [ ] OAuth: resource (RFC 8707) display
- [ ] OAuth: "Connect…" button → popup flow
- [ ] OAuth: connected-as state after callback
- [ ] OAuth: failure state + retry
- [ ] Bearer: token input (masked, never echoed back)
- [ ] Secret-handling hint (AES-GCM, has_secret only)

### Step 3 — Health & Scan
- [ ] Live progress while checks run
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
- [ ] Register → lands in list with correct status + toast

**BE implied:** `POST /mcp-servers` staged create (or draft row) · `POST {id}/oauth/start` + callback route · `POST {id}/validate` (steps 1 checks) · scan pipeline returns structured lines · register finalizes status machine.

---

## 9. Agent self-registration (chat surface) [P1]

- [ ] "Save as skill" affordance on a conversation
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

- [ ] `extensions` in STUDIO_PANELS (id, titleKey, descKey)
- [ ] `proposals` in STUDIO_PANELS (+ tab badge count)
- [ ] `skill-editor` in STUDIO_PANELS (hiddenFromPalette, singleton)
- [ ] Panels self-title via props.api.setTitle
- [ ] Extensions internal tabs: Plugins / MCP Servers / Commands & Hooks
- [ ] Internal tab state preserved across panel hide/show (never-unmount)
- [ ] Same components as routes (zero logic fork — hooks/context shared)
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

- [ ] All strings i18n-keyed (react-i18next, vi + en)
- [ ] Toggles: role="switch" + aria-checked
- [ ] Keyboard: table row focus, dialog focus-trap, Esc closes
- [ ] data-testid on every interactive element
- [ ] Responsive: 3-col collapses; nav → icons; tables scroll
- [ ] Per-device UI state (column widths, collapsed nav) in localStorage only
- [ ] All registry data server-side (no localStorage data)
- [ ] Skeleton loading per screen
- [ ] Error banner (cached + Retry) per screen
- [ ] Mutation toasts everywhere
- [ ] Browser lists ALL reuse EntityListBrowser-style shell + Pager (no hand-rolled)

---

## Tally

| Screen | Lines | Phase |
|---|---|---|
| 0 Global chrome | 9 | P1 |
| 1 Plugins | 44 | P0/P1 |
| 2 MCP servers list | 21 | P2/P3 |
| 3 Server detail | 28 | P3 |
| 4 Skills | 34 | P1 |
| 5 Commands & Hooks | 26 | P4 |
| 6 Proposals | 22 | P1 |
| 7 Activity log | 11 | P1 |
| 8 Wizard | 33 | P3 |
| 9 Agent flow | 13 | P1 |
| 10 Studio shell | 18 | P1/P3 |
| 11 Conventions | 11 | all |
| **Total** | **270** | |
