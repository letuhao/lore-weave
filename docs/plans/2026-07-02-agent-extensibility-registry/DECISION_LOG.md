# Decision Log — Agent Extensibility Registry (autonomous run)

Mid-run design forks discovered during implementation. Per the execution model
(`00_EVALUATION_AND_TASKS.md` §7): the agent picks the safest default consistent
with the sealed Decision Register (§3) + CLAUDE.md invariants, records it here,
and **continues** — no pause. The PO reviews this log at the FINAL RELEASE GATE
and may order rework.

Format per entry:

```
## DL-<n> · <date> · <task-id>
- Context: <what surfaced the fork>
- Options: <A / B / …>
- Chosen: <option> 
- Rationale: <why this is the safest default; which sealed decision/invariant it follows>
- Rework cost if overturned: <low/med/high + one line>
```

---

## DL-1 · 2026-07-03 · REG-X-01 (audit)
- Context: Spec/plan called for the audit trail via an AFTER-UPDATE trigger → projection table (the `projection-trigger-activity-log` pattern). At P0 the mutation surface is small and all writes flow through a handful of handlers.
- Options: (A) explicit `s.audit(...)` insert from each mutation handler; (B) AFTER-UPDATE/INSERT triggers per table.
- Chosen: **A — explicit insert helper**, for P0.
- Rationale: simpler + directly unit-testable, and it captures actor identity (user vs agent vs admin) + intent (create/enable/accept-risk) that a row-diff trigger can't see without extra plumbing. Triggers shine for out-of-band writes; here every write already goes through our handlers. Consistent with "fix-now, keep it simple".
- Rework cost if overturned: low — swap the helper for triggers; the `registry_audit` table shape is unchanged either way.

## DL-2 · 2026-07-03 · REG-P0-03 / REG-P0-04 (book tier)
- Context: Creating a `book`-tier plugin, or writing a `book`-scope enablement override, requires verifying the caller holds an E0 grant on the target `book_id`. The book-grant client is not wired into agent-registry yet.
- Options: (A) allow book writes now, trusting the caller-supplied book_id; (B) reject book-tier creation + book-scope enablement writes until the grant client is wired; (C) build the grant client now.
- Chosen: **B — reject with 501 NOT_IMPLEMENTED** (`D-REG-BOOK-GRANT`), while the resolver still fully honors book overrides (so no behavior is lost once writes land, and the D1 matrix is implemented + unit-tested).
- Rationale: an unguarded book write is a tenancy hole (CLAUDE.md LOCKED — the exact class the entity-kinds rule forbids; `worker-loaded-id-needs-parent-scoping`). (C) is real scope (a cross-service grant contract) that belongs to the book-tier track, not P0 foundation. Safest default that ships P0 without a security regression.
- Rework cost if overturned: low-med — add the grant client + flip the two 501 branches to real inserts; no schema change.

## DL-3 · 2026-07-03 · P0 test strategy
- Context: Handler happy-paths (full RETURNING-row scans) are painful to mock precisely with pgxmock, and the sealed E2E-1 decision + repo lessons (`prefer-e2e-and-evaluation-over-live-smoke-poc`, `new-cross-service-contract-needs-consumer-live-smoke`) say the real gate is a real-stack E2E.
- Options: (A) exhaustively mock every handler row; (B) unit-test the pure logic + validation/tenancy rejection branches, prove happy-path CRUD through the real-stack E2E (E2E-P0-A/B).
- Chosen: **B**.
- Rationale: mock-only row scans are brittle and have repeatedly hidden real cross-service bugs in this repo; the pure resolver matrix, name/vault/clamp, and the reject branches (401/400/403/501/internal-token) ARE unit-tested, and the create/list/delete happy path is covered by the real-stack E2E where it actually matters.
- Rework cost if overturned: low — add pgxmock row fixtures later if a unit-level happy-path guard is wanted.

## DL-4 · 2026-07-03 · REG-P1-03 / REG-P1-05 (System skill bodies)
- Context: The 5 System skills' full bodies live in chat-service `*_skill.py` constants and are already injected there. REG-P1-03 said "seed System rows, body == python constants (checksum)".
- Options: (A) copy the 5 Python skill bodies verbatim into the agent-registry seed (satisfies the checksum AC); (B) seed System rows with slug + description + a marker body, keep the real bodies authored in chat-service (single source), and have chat-service inject its own System bodies while honoring per-user disable via `/internal/skills.system_overrides`.
- Chosen: **B — chat-service stays the System-skill-body source of truth.**
- Rationale: copying the bodies duplicates content across two services in two languages → guaranteed drift (the exact anti-pattern the Frontend-Tool-Contract section warns about). The seed rows exist for the catalog/enable-disable UX + shadow resolution; `/internal/skills` returns `system_overrides` (disabled System slugs) + `shadowed_system` (user slugs that override) so chat-service injects correctly. The checksum-equality AC is relaxed to slug-equality (byte-identical slugs — E2E-verified).
- Rework cost if overturned: low — if a future consumer needs the bodies in agent-registry, add a one-time sync from chat-service; no schema change.

## DL-5 · 2026-07-03 · REG-P1-06 (proposal approve auth)
- Context: Spec §12b described the confirm route as "internal-token + X-User-Id gated (no JWT mint)" — that shape is the PUBLIC-MCP approval spine for EXTERNAL agents. For our in-app chat, the human approves in the browser with their own JWT.
- Options: (A) internal-token + X-User-Id confirm route (FE would need an internal token — it doesn't have one); (B) JWT-owner-gated `PUT /proposals/{id}/approve` where the browser's own token authorizes the write to the user's own tier.
- Chosen: **B — JWT-owner-gated approve/reject** (no JWT mint; owner from the token).
- Rationale: the human is in-app with a JWT; a JWT-gated approve to one's own tier is the correct, simplest authorization and needs no token minting. The public-MCP internal-token spine is for the P3+ external-agent path, not this in-app loop. The `confirm_token` remains on the proposal for chat tool-call correlation.
- Rework cost if overturned: low — add an internal-token confirm alias later for an external-agent approval path if needed.

## DL-6 · 2026-07-03 · REG-P1-08 (SkillProposalCard) — deferred on concurrent-work collision
- Context: `registry_propose_skill` is a SERVER MCP tool, so its result renders as a normal tool result inside the chat assistant message — i.e. in `frontend/src/features/chat/components/AssistantMessage.tsx`. That file (and the whole `features/chat/**` tree) is currently MID-FLIGHT with the chat-quality-ux-wave track's UNCOMMITTED changes.
- Options: (A) edit AssistantMessage.tsx now (collides with the other track's uncommitted diff — can't cleanly stage just our part, high conflict risk); (B) defer SkillProposalCard until the chat-quality track's changes land, then add the card render on a clean base.
- Chosen: **B — defer (`D-REG-SKILLPROPOSAL-CARD`)**, gate #1 (out-of-scope collision with a concurrent track's uncommitted work).
- Rationale: editing another track's actively-modified files mid-flight is the exact "shared file hazard" the repo warns about; the proposal loop is already fully functional headless (MCP propose → DB row → Proposals inbox → approve), so the card is a chat-surface convenience, not a blocker. The ProposalsPanel/ProposalsView already give the human an approve/reject surface outside chat.
- Rework cost if overturned: low — the card is one component reading a tool-result shape we already emit; add it once `features/chat` is quiescent.

---

## CLEARED — 2026-07-03 (all deferrals resolved on user request)
- **DL-2 / D-REG-BOOK-GRANT** → CLEARED: grantclient wired (`RequireGrant ≥edit`, fail-closed 404/501/503); book-tier plugins/skills + book-scope enablement now work. Live: book-tier for an ungranted book → 404 (`p1_governance_smoke.ps1`).
- **REG-X-02** → CLEARED: 50-skill per-user cap enforced at every write path (createSkill/import/proposal-approve) → 429. Live-verified.
- **DL-6 / D-REG-SKILLPROPOSAL-CARD** → CLEARED: `AssistantMessage.tsx` is clean again (the chat-quality track landed), so the collision that forced the defer is gone; the in-chat approve/reject `SkillProposalCard` is wired. 159 FE tests green (no regression).
- **D-REG-P1G-BROWSER** → FULLY CLEARED (deterministic + LIVE): `registryPanels.test.tsx` mounts the real panels + panelCatalogContract holds, AND the live browser smoke `p1g_browser_smoke.mjs` PASSED — a standalone Playwright script launching its OWN isolated chromium (bypassing the MCP-held shared browser): real login → studio → Ctrl+Shift+P → "Open Extensions" → the dock actually mounted the Extensions panel + rendered the Skills view from the live backend.
- **FE tails** (standalone /extensions route, save-as-skill affordance) → shipped.

## /review-impl round 2 — 2026-07-03 (adversarial pass on the deferral-clearing work)
Three findings, all resolved + live-regressed (`p1_booktier_smoke.ps1` 5/5, `p1_governance_smoke.ps1` regression clean):
- **MED (FIXED) — book lifecycle gate:** `requireBookGrant` checked grant LEVEL only, not lifecycle. Per the grantclient SDK ("edit/manage should gate on `Active()`"), a user with edit on a TRASHED/purge_pending book could create book-tier resources on a book being deleted. → now `ResolveAccess` + `≥edit` + `Active()`; trashed → 409 BOOK_NOT_ACTIVE.
- **MED (FIXED) — book-tier was half-wired (orphaned rows):** enabling book-tier CREATION exposed that the READ side never handled book tier — `internalSkills` only queried `tier='user'` (book skills never injected → inert) and get/patch/delete used `canWritePlugin` (book rows → 404, i.e. create-can't-delete). → `internalSkills` now resolves book skills for the `book_id` context (book-scoped, no cross-book leak — proven); `authorizeRowWrite` grant-gates book-tier get/patch/delete on skills AND plugins. Live: create→inject→isolate→get→delete on an owned book all pass.
- **LOW (accept + document) — quota TOCTOU:** `skillQuotaExceeded` is check-then-insert; a rare concurrent double-create could reach 51. Accepted — a soft guardrail, not a security boundary (documented in-code).
- **Verified NOT bugs:** registry tool tiers flow via `_meta.tier` (TierA/TierR) read by chat-service `tool_tier()` — propose/update/enable correctly Tier-A (excluded in ask-mode); resume path carries the pass-1 system message (injected skills) via `list(susp.working)`.
- **Deferred (gate #2, genuinely larger, NOT a regression):** `D-REG-BOOK-TIER-FE` — surfacing a book context in the FE Extensions panel so book skills are managed from the UI (the backend is now complete + grant-gated; this is additive FE work).

## /review-impl round 3 — 2026-07-03 (adversarial pass on P2 — the ai-gateway overlay)
Three findings, all fixed + live-verified (`p2_overlay_smoke.ps1` still 6/6, live SSRF-reject 400, ai-gateway jest 35/35, `TestIsInternalHost`):
- **HIGH (FIXED) — no timeout on the overlay's upstream calls:** `fetchEffective` used bare `fetch()` (no signal) and the per-server list/dispatch relied on SDK defaults — a HUNG (not down) agent-registry or user MCP server would stall EVERY turn's tools/list indefinitely (fail-open catches errors, not hangs). → `AbortSignal.timeout` on all three (2s probe / 15s list+dispatch), combined with the turn-stop signal via `AbortSignal.any`.
- **MED (FIXED) — hot-path HTTP on every tools/list:** `resolve()` fetched agent-registry on EVERY call before the TTL check, so the cache only saved re-federation, not the round-trip — an added synchronous dependency + latency per turn (even for zero-registration users). → TTL-gate: within the 30s TTL, serve from cache with NO upstream call; fetch only on expiry; version compared on refresh to skip re-federation; fail-open now serves last-known (stale) over dropping tools mid-session.
- **MED (FIXED) — link-local SSRF in the P2 guard:** `isInternalHost` allowed `IsLinkLocalUnicast`, which includes `169.254.169.254` (the cloud-metadata SSRF target). → removed; loopback + RFC1918 only. `TestIsInternalHost` guards it; live: link-local + public → 400.
- **LOW (accept + document):** global `catalog_version` → a bump invalidates all users' overlay caches on their next TTL refresh (bounded by TTL now, so minor perf, not incorrect); `OVERLAY_NAME_RE` (`^[ub]_…`) couples to the fact that no System provider uses a `u_`/`b_` prefix (true today; a new such provider would mis-route — documented).
- **Deferred to P3 (by design):** redirect-based SSRF (the overlay's fetch/MCP-client follows redirects — a user server could 302 to a metadata endpoint) + full egress allowlist are the P3 security layer; the P2 guard is scoping only. **→ CLOSED in M3 (`ad5bce682`): the egress fetch uses `redirect:'manual'` + re-validates each hop's host against the SSRF+allowlist policy.**

---

## DL-7 · 2026-07-03 · REG-P3-05 (scan probe location)
- Context: the supply-chain scan must fetch a server's `tools/list`, which requires an MCP client. ai-gateway already has the MCP SDK + will own the runtime egress path (M3), so the probe could live there and agent-registry could call it.
- Options: (A) probe in ai-gateway, agent-registry calls an `/internal/probe` on it; (B) implement a minimal streamable-http MCP client in Go inside agent-registry.
- Chosen: **B — Go probe in agent-registry (`probe.go`).**
- Rationale: (A) creates an agent-registry→ai-gateway dependency CYCLE (ai-gateway already depends on agent-registry for the overlay resolve). The scan is a register-time concern the registry owns; keeping it in-process avoids the cycle. SSRF is re-applied at DIAL time (`safeDialContext` resolve-then-connect pinning) so the Go probe is independently hardened. The runtime tool-CALL egress stays in ai-gateway (M3) — different moment, both SSRF-safe. Two egress implementations is acceptable because they guard two distinct seams.
- Rework cost if overturned: med — move the probe to ai-gateway + add the internal route + break the cycle with a queue; not worth it unless a shared egress worker emerges.

## DL-8 · 2026-07-03 · REG-P3-01 (SSRF dev escape hatch)
- Context: the P3 SSRF guard rejects user URLs resolving to internal/loopback/metadata (prod posture). But the whole dev stack live-smokes the overlay/scan/egress against IN-CLUSTER MCP servers (agent-registry's own `/mcp`), which are internal by definition.
- Options: (A) always reject internal (can't live-smoke in-cluster — would need a real public MCP server on every dev box); (B) a dev-only flag `AGENT_REGISTRY_ALLOW_INTERNAL_MCP` that re-permits internal targets, classifying them `is_external=false`.
- Chosen: **B — dev flag, DEFAULT OFF (prod-safe); compose sets it =1 for the dev stack.**
- Rationale: the SSRF *rejection* (prod) is fully unit-proven (`TestClassifyRegistrationURL_SSRF`, 10+ payloads incl. DNS-rebind); the flag only affects live-smoke reachability, never the prod code path (flag off ⇒ every user URL is guarded). `is_external=false` also correctly makes internal targets skip the egress internal-block (they ARE the trusted platform) while still honoring the allowlist. The scan probe mirrors the overlay's federation envelope (X-Internal-Token/X-User-Id) for internal targets so an internal-token-gated `/mcp` is probeable exactly as runtime federates it.
- Rework cost if overturned: low — drop the flag; provide a real external test MCP server for smokes instead.

---

## /review-impl round 4 — 2026-07-03 (adversarial pass on P3 — the whole external-MCP + security milestone)
Two cold-start reviewers (egress/overlay/OAuth + SSRF/vault/probe). **Verified correct (not bugs):** the internal-token→
external-server leak boundary (`chooseOutboundHeaders` — external never gets X-Internal-Token), OAuth state single-use
(atomic DELETE…RETURNING, state=PK, 10-min TTL) + PKCE binding + RFC 8707 `resource` on both legs, token-endpoint SSRF
(dialed via the pinned probe client), `secret_ciphertext` non-serialization (unexported field), the quarantine filter
(`internalEffectiveMcpServers WHERE status='active'` excludes pending/suspended), anti-oracle 404s on every mcp-server
route, and the Go probe's IP-pinned dial (rebind-safe). **Findings fixed (`ba576e410`):**
- **HIGH — DNS-rebind TOCTOU in the ai-gateway TS egress:** `makeEgressFetch` resolved+validated the host but global
  `fetch` (undici) RE-RESOLVED at connect → a rebind slipped an internal IP past the check (the Go side was already
  pinned; the TS side was not — the asymmetry the reviewer caught). → `makePinnedDispatcher`: an undici `Agent` whose
  connect-time lookup filters internal addresses and PINS the socket to a validated IP (added `undici` dep). This IS the
  resolution undici connects with → no second lookup → TOCTOU closed, mirroring the Go `safeDialContext`.
- **MED — CircuitBreaker never re-opened on a failed half-open trial:** after open→cooldown→half-open, a failed trial
  left `openUntil` in the past so `canRequest` returned true forever (breaker defeated). → re-open immediately on a
  half-open failure.
- **LOWs (all fixed):** strip `Authorization` on a cross-origin redirect (an empty allowlist was allow-all for redirect
  hops → the user's bearer could reach an arbitrary host); the internal-envelope probe refuses any cross-host redirect
  (Go strips only standard auth headers, NOT our custom `X-Internal-Token`); `accept-risk` restricted to scanned+flagged
  `suspended` only (a `pending`/unscanned server could otherwise be forced active into the federation set); `/internal`
  token check fails CLOSED on an empty configured token + `crypto/subtle.ConstantTimeCompare`; refresh-worker store
  failure is logged (a rotated refresh token could otherwise be lost silently).
- **Accepted + documented (not fixed):** the model-capability rejection is a best-effort POLICY heuristic (a model proxy
  on a custom domain/path passes) — the provider-gateway invariant is enforced structurally by `ai-provider-gate`, not
  this substring check; and the `/internal` routes trust the caller-supplied `user_id`/`book_id` by design (the shared-
  secret internal trust boundary; ai-gateway resolves the grant upstream). Neither is exploitable.
- **~~Deferred~~ CLEARED (`p3_external_live_smoke.ps1`):** `D-REG-P3-EXTERNAL-LIVE` — the real external-MCP E2E was run
  against a GENUINE public third-party server (**DeepWiki** `https://mcp.deepwiki.com/mcp`, no-auth streamable-http):
  register → `is_external=true` + quarantined → probe scanned its 3 real tools → clean → active → federated → **tool
  CALLED through the gateway's pinned egress dispatcher, real content returned** (external+no-auth ⇒ no internal token
  sent) → cross-tenant isolation. Only OAuth-against-a-real-server is untaken (DeepWiki is no-auth; the OAuth loop is
  live-proven vs a conformant fake AS in M4). P3 defers: all clear.

---

## DL-9 · 2026-07-03 · REG-P4-01 (command expansion seam)
- Context: a `/name args` command must expand so BOTH the model and the transcript see the template. I first wired it inside `stream_service.stream_response` (before parse_inline_effort) — but the model still saw the raw `/echotest` and complained about an unknown tool.
- Root cause: the messages ROUTER persists the user message (`body.content`) BEFORE calling `stream_response`, and the prompt is built from that history row. Mutating `user_message_content` inside `stream_response` never reached the model.
- Chosen: **expand in the router (`messages.py`) BEFORE the INSERT + before `stream_response`** — expand-in-place (persist + send the same expanded text). Also passes the session's `project_id` so book-tier commands resolve.
- Rationale: the only seam where the expansion reaches both the persisted history AND the model. Caught by a live turn (the persisted user row + the model complaint), not by units — the exact `new-cross-service-contract-needs-consumer-live-smoke` value.
- Rework cost if overturned: low — the client + pure `expand_command` are seam-agnostic; move the 3-line call.

## /review-impl round 5 — 2026-07-03 (adversarial pass on P4 — commands + hooks)
One reviewer. **Verified correct:** tenancy on every command/hook route + resolver (anti-oracle 404), reserved-name shadowing blocked at create+patch+the Python guard, hook action validation at create AND patch, higher-tier shadow-by-name resolution, `_substitute` mapping (guarded indices, no ReDoS), expansion placement (before persist+stream), pre_turn injection placement (guarded, before the last user msg), and the deny short-circuit's loop accounting (well-formed tool-exchange atom, untouched usage/write-budget). **Fixed:**
- **HIGH — `require_approval` pre_tool_call hook was a SILENT NO-OP:** the loop only handled `deny`; `require_approval` fell through and the tool executed with no gate (exactly the silent-no-op-of-a-guardrail class). → WIRED to the same `tool_approval` suspend machinery as the C2 write-mode gate.
- **MED — `annotate` / `post_tool_call` / `post_turn` were advertised but unwired** (the engine never invoked `collect_annotations`/post_turn). → agent-registry now accepts ONLY the WIRED (event, action) matrix (pre_tool_call→deny|require_approval, pre_turn→inject_text) at create AND patch; the FE builder offers only those. Storage CHECK stays forward-compatible; the API is the gate. No advertised no-ops.
- **LOW — no hook creation quota:** added `quotaHooks` (20/user), mirroring commands.
- **Accepted+documented:** book-tier creates bypass the per-user quota (grant-gated; matches the skills/mcp pattern); a denied tool can spin the loop with an adversarial model (pre-existing class shared by `find_tools`/planner-cap — an absolute iteration cap is a separate cross-cutting change).
- **Deferred (gate #1):** `D-REG-P4-SLASH-AUTOCOMPLETE` — the in-chat `/` autocomplete touches the chat-input component under a concurrent track's edits; the builder is the primary authoring surface.

## DL-10 · 2026-07-03 · REG-P5 (bundle scope + two runtime/ingest defers)
- Context: P5 = subagents (REG-P5-01) + bundles (REG-P5-02) + official-registry ingest (REG-P5-03) + FE (REG-P5-04).
- Bundle scope: a bundle carries **skills + commands + hooks only** — MCP servers are DELIBERATELY excluded because they hold a vault secret + connection/scan state that isn't portable (the target must re-register + re-auth). Documented in-code.
- Chosen defers (both gate #2 — large/structural, need their own plan):
  - **`D-REG-P5-SUBAGENT-RUNTIME`** — the CRUD/resolver ship; the scoped-execution runtime (`registry_run_subagent` running an ISOLATED nested turn with ONLY the tool_scope subset + the persona system_prompt) is a nested agent tool-loop that must route through the provider gateway + isolate context — a serious feature, not a quick edit. The AC's negative test (subagent runs with only its scoped tools) belongs to the runtime.
  - **`D-REG-P5-REGISTRY-INGEST`** — pulling the official MCP Registry API into an admin curation queue → approve → System rows is an admin-only feature + an external-API integration; large + lower-priority than the shipped user-facing system.
- Rationale: both clear defer gate #2 (verified against the anti-laziness rule — they're not "missing infra" but genuinely large tracks needing a plan). The buildable foundations (subagent CRUD/resolver; the full user-facing bundle + extension system) are shipped + live-proven.

## /review-impl round 6 — 2026-07-03 (adversarial pass on P5 — subagents + bundles)
One reviewer. **Verified correct:** importBundle transaction (no partial-commit path — deferred Rollback fires on any member-insert error before Commit), no double-write, export excludes MCP-server secrets entirely, export/import tenancy (System∪own read; forced user-tier write), quota-before-Begin, validation-before-txn, subagent tool_scope validation (create+patch), subagent authz (anti-oracle 404), resolver book▷user▷system shadowing, and the FK ON DELETE CASCADE on every member table. **Fixed:**
- **MED — bundle import bypassed the skill validators:** importBundle checked only the slug, so a bundle could smuggle a skill with executable `scripts/` content (defeating the prompt-only guard), a >64 KB body, or an empty description. → `validateBundle` now runs the SAME `validateSkill` on every skill (live-proven: a `scripts/` skill → 400 on import).
- **MED — unvalidated plugin `version` → Content-Disposition filename injection:** only import validated semver; `createPlugin` stored any version verbatim and `exportBundle` interpolated it into the (quoted) filename — a `"` broke out. → `createPlugin` + `patchPlugin` require semver; `bundleFileName` strips every non-`[A-Za-z0-9._-]` char.
- **LOW — `createSubagent` had no quota** → `quotaSubagents` (20/user). **LOW — `subagent_defs` was missing `uq_subagents_system`** → added.
- **Accepted:** book-tier subagents creatable-but-not-listable — a SYSTEMIC gap shared by listSkills/listCommands (system+user base clause), not a P5 regression.
