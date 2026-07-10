# Spec — Chat &amp; AI settings consolidation (unified surface · two-tier model resolution · de-silencing)

**Status:** **SHIPPED** (M1a–M5) + `/review-impl` + all defers cleared 2026-07-05. Edge-case-hardened (adversarial review, §12). Size **XL** (multi-service). Codified the [Settings & Configuration Boundary Standard](../standards/settings-and-config.md) (SET-1..8) from this work.
**Date:** 2026-07-05 · **Branch of origin:** feat/context-budget-law

**Session half of G1 shipped, 2026-07-10.** G1 promised "a single Chat & AI settings surface
(account-level) **+ a session-scoped subset reachable from chat**". Only the account half had been
built. Three things were wrong, and the first made the other two impossible:

1. **The Session tier was read-only and permanently NULL.** `chat_sessions.grounding_enabled` /
   `voice_overrides` / `context_overrides` existed, the effective-settings resolver read them, and the
   turn consumed `grounding_enabled` — but nothing could WRITE them. `PatchSessionRequest` never declared
   the fields, so Pydantic's `extra="ignore"` accepted the keys, dropped them and returned 200. Fixed in
   `d524e1e60` with the 3-state contract (`omit` / explicit `null` = clear-to-inherit / value), one shared
   deep-merge (`apply_patch`), and the enum registry moved out of the account router — the session row is
   a **second write door** onto settings the turn consumes.
2. **The chat panel predated the cascade.** `SessionSettingsPanel` never called the resolver; it seeded
   itself from client-side literals (`temperature ?? 0.7`, `top_p ?? 0.9`) that were **not** the system
   defaults — the request went out with the field unset and the provider chose. It now reads
   `Session ▸ Book ▸ Account ▸ System`, shows a `TierChip` per row, and offers "clear · inherit *X*"
   keyed on **which tier supplied the value, never on value-equality** (finding UX-5). An unset sampling
   param renders "Not set — the provider's own default applies", not a fabricated number.
3. **Voice had two account stores that never spoke.** Settings → Chat & AI → Voice wrote
   `user_chat_ai_prefs.voice`; the chat `VoiceSettingsPanel` wrote `lw_voice_prefs`/`voice_prefs`, and the
   voice **runtime reads the second one** — so picking a TTS voice in the unified panel changed nothing you
   could hear. `voiceBridge.ts` reconciles them (§7.1 MIG-4 dual-write) and normalizes the vocabulary split
   where the account panel wrote `tts_source: 'user_model'` for what the voice store calls `'ai_model'`.

Also delivered: `VoiceSettingsPanel` folded into the session panel as its Voice **section** (the mic button
deep-links there instead of opening a rival slide-over), and the "6-vs-4 preset lists" unified into one
`PROMPT_PRESETS` — they had diverged in keys, capitalisation *and* prompt text, so the prompt a new chat was
seeded with was not the prompt the settings panel showed under that name.

**Reachability fix, 2026-07-10.** G1 ("one place") held only on `/settings`. The tab list was declared
**twice** — `pages/SettingsPage.tsx` and `features/studio/panels/SettingsPanel.tsx` — and the new
`chat-ai` tab was added to the page but **missed on the Studio dock**, whose header comment still read
*"reuses the six settings tab components"*. A user working inside the Writing Studio could not reach
Chat & AI settings at all: built, mounted, unreachable. Root-caused rather than patched — both surfaces
now derive from one registry (`features/settings/tabs.tsx`); `SettingsTabContent` is an exhaustive
`switch`, so the compiler rejects a listed-but-bodiless tab; and `__tests__/settingsTabParity.test.tsx`
renders **both** surfaces and asserts each offers exactly what the registry yields (proved red by
deleting `chat-ai` from the registry — 6 tests fail). Live-verified in a browser: the Studio dock's
Chat & AI tab renders all six sections with 0 console errors. The command palette's stale panel
description ("Account, providers & translation") was corrected too.

**Resolution log (2026-07-05):** M1a–M5 shipped; `/review-impl` fixed the write-only-behavior HIGH + enum MED; **M1b** (Book tier, grant-gated cross-service) shipped `9d1575cc8`; **M5** (voice unified home, kills `af_heart`) shipped `ccae0ce68`; **M4-TIER-CONSUMPTION** resolved as a **conscious won't-fix** (defer gate #5) — the T5/T4/D13a tiers are eval-proven inert (blind-judge baseline≡candidate; compaction architecturally rare), the shipped `mode` Off switch is the meaningful control, and no per-tier write-only toggles were built (SET-5 clean); revisit only if a future eval shows the tiers add quality.
**Mockups:** [`design-drafts/settings/2026-07-05-chat-ai-settings-redesign-mockup.html`](../../design-drafts/settings/2026-07-05-chat-ai-settings-redesign-mockup.html) (this spec) · [`design-drafts/settings/2026-07-05-advanced-context-management-mockup.html`](../../design-drafts/settings/2026-07-05-advanced-context-management-mockup.html) (context-mgmt sub-panel, folded in).
**Supersedes:** the standalone **D-LONG-WORK-CONTEXT-MODE** proposal (context management becomes one section of this surface).

---

## 1. Problem

Chat/AI settings are **fragmented, silently-defaulting, and non-shared**. Verified by a full FE+BE audit (2026-07-05):

**Fragmentation — settings live in 7 surfaces:**
| Surface | Scope | Store |
|---|---|---|
| `SessionSettingsPanel` | per chat session | `PATCH /v1/chat/sessions/{id}` |
| `VoiceSettingsPanel` | global (per user) | localStorage `lw_voice_prefs` + server `voice_prefs` |
| `NewChatDialog` | new-session seed | session API |
| `ChatInputBar` | per-send + session | mixed (ephemeral + PATCH) |
| Settings → `ProvidersTab`/`DefaultModelsCard` | global | `user_default_models` |
| Settings → `ReadingTab` | global | localStorage `media_prefs` + server `media_prefs` (**second, disconnected TTS store**) |
| Studio `SettingsPanel` (dock) | global | duplicate of the settings page |

**Model choice split 3 ways, no shared source of truth:** session `model_ref` · per-user `user_default_models` · per-book `work.settings.default_model_ref`. **8 model pickers** in the studio; per code, **`PlannerView` + `ReferencesPanel` are still bespoke `<select>`s and `list[0]`-defaulting** while `SelectionToolbar`/`SceneGraphCanvas`/motif already use the shared `ModelPicker` but default to `modelList[0]` (favorites-first), **not** a cascade (verified — see §12 finding UX-9; the "5 tools" framing was partly stale). Co-writer chat pulls from a *4th* source (chat session). A hidden `work.settings.critic_model_ref` has **no UI at all**.

**Silent fallbacks the user cannot see or control** (file:line from audit):
1. **Grounding is ALWAYS ON, no toggle** — `stream_service.py:1812` forces `EntityPresence(True, "gate_disabled")` when the T5 gate is off (the default). Only a process-global env flag governs it.
2. **Reasoning silently `off`** — `stream_service.py:229`.
3. **`permission_mode` silently `write`** (tool write authority) — `models.py:457`.
4. **TTS voice silently `af_heart`, never persisted to the session** — `voice_stream_service.py:219`; resets every request.
5. **`temperature`/`top_p`/`max_tokens` unset → opaque provider SDK default** — `stream_service.py:303-318`; shown nowhere.
6. **planner/composer/subagent model slots silently inherit the turn model** when blank — `stream_service.py:1606,1758-1765`; the one place the empty-`user_default_models` caveat surfaces.
7. **All context-budget knobs are process-global env flags** — `config.py:70-178`; `compact_persist_enabled=True` + `compact_breadcrumb_enabled=True` are ON by default, reshaping every turn invisibly. Not per-user/session.

**Voice split 2 ways:** chat `voice_prefs` (`lw_voice_prefs`) vs reading `media_prefs` (`loreweave:media-prefs`) — different model lists, different voice vocabularies (chat = provider voices like `af_heart`/Kokoro; reading = a hardcoded OpenAI list `alloy/echo/…`), different keys. **Both server stores live in auth-service** `user_preferences.prefs`, not chat-service (a cross-service boundary the migration must respect).

**System-prompt presets duplicated** (6 in `SessionSettingsPanel:12`, 4 in `NewChatDialog`) — both are **client-side constants**, not a DB row. **Effort** appears in 3 places.

## 2. Goals / non-goals

**Goals**
- **G1 — One place.** A single **Chat &amp; AI** settings surface (account-level) + a session-scoped subset reachable from chat, replacing the 7 fragmented surfaces. Casual controls up front; advanced buried &amp; collapsed.
- **G2 — Explicit, nothing silent.** Every fallback in §1 becomes a **visible, controllable** setting whose *effective* value + *originating tier* is always shown (never a blank that hides a provider/engine default; never a silent no-op or mid-turn substitution).
- **G3 — Set once, inherit everywhere.** A **two-tier** model source (book overrides account) that a chat session and every Studio tool inherit from, with an **optional** local override — never a required re-pick.
- **G4 — Unify voice** into one store (without collapsing distinct configs); **unify** system-prompt presets and effort into one definition.
- **G5 — Context management** becomes a per-session setting **derived from the account default**, replacing the process-global env flags for user-facing behavior. Env flags remain the *deploy-time ceiling/kill-switch*, not the per-user knob.

**Non-goals**
- No change to the **provider-gateway invariant** — models still resolve through `provider-registry-service` (BYOK). We change *which model_ref* is chosen, never *how* it's called.
- No new agentic MCP logic; this is settings plumbing + UI.
- No removal of the env flags as a **deployment kill-switch** (see §5 precedence).
- Not building new model *capabilities*; only surfacing/sharing existing ones.
- **No user-authorable preset store** (see §3.3 — presets stay client-seed constants for now).

## 3. The resolution model (core abstraction)

Every Chat &amp; AI setting resolves through a fixed **tier cascade, most-specific wins**:

```
Tool/turn override  ▸  Session override  ▸  Book override  ▸  Account default  ▸  System default
   (per studio tool     (chat session       (book-OWNER's      (user_default_*     (deploy env /
    or per chat turn,     row)                work.settings,     per user)           client seed;
    session-ephemeral)                        grant-gated read)                      admin/deploy-owned)
```

### 3.1 Resolution rules (the fixes)

- **Field-by-field deep-merge, per leaf.** Resolution is **per leaf field**, not per category-blob (finding RES-3/TEN-4). A book that overrides only `behavior.temperature` does **not** shadow the account's `top_p`/`max_tokens`. Inheritance predicate = **key-absence** at a tier ⇒ inherit down; an explicit value (incl. explicit `null` meaning "clear to the next tier down") is an override. Applies uniformly to models (per role) and behavior/grounding/voice/context (per field).
- **Liveness-validate at EVERY tier from one authoritative source** (finding RES-1). The **BE resolver** (`GET /v1/chat/effective-settings`) checks each candidate `model_ref` against provider-registry via an `/internal/*` resolve/liveness route and **skips dead/deactivated refs at any tier**, not just the topmost. FE preview and server submit share this one source of truth — they cannot disagree. If a tier's ref is dead, the response names *which* tiers were skipped; if **all** tiers resolve dead/unset → an explicit `no_model_configured` state, never a mid-turn 404.
- **Studio-tool context skips the Session tier** — but only by a **canonical predicate** (finding RES-5): *a surface uses the Session tier **iff it is driven by a chat session it owns*** (co-writer chat ⇒ 5 tiers, its own `session_id`). A studio tool with no owning session (e.g. `SelectionToolbar` what-if) ⇒ 4 tiers even when a chat panel is open elsewhere. Not a bare "did the caller pass `session_id`" check.
- **Per-tool overrides are session-ephemeral** (finding UX-4). "Change the model in this tool" is React-local state for that mount (mirrors today's `PlannerView.localModel`), **not** a persisted tier. There is **no persisted "ask each time" mode** — dropped to avoid a store with no home. Default = inherit; an in-tool pick overrides for that session only.
- **Effective-value contract.** Every settings **read** returns, per field: `{effective_value, source_tier, tier_stack}` — the winning value, which tier supplied it, **and the full raw per-tier stack** (finding UX-5) so the UI can render "overriding book's X · revert to inherited (would be Y)" and distinguish *explicitly-set-equal-to-parent* (keys on tier) from *inherited*.

### 3.2 Shared-book tenancy (the structural fix — finding TEN-1/TEN-2)

`work.settings` is **per-`(user_id, book_id)`** (verified: `composition-service works.py` filters `user_id` on every statement; a cross-user read returns `[]`). Therefore:
- **Book tier = the book-OWNER's `work.settings`.** For a book shared via an **E0 grant**, grantees inherit the **owner's** book-tier model/behavior through a **new grant-checked, read-only** composition-service route (`GET /internal/works/{book_id}/settings?as_grantee={uid}` — verifies the grant, then deliberately reads the owner's row). A grantee's fallback **below** Book is their **own** Account default.
- **The book-tier WRITE path stays `user_id`-scoped.** Only the owner mutates `work.settings`. A grantee never writes it; grantee-local intent lives at their Session/Tool tier. **Widening the write query's scope to "fix" sharing is a tenancy defect** (the `entity_kinds`-class bug) — this invariant is LOCKED.
- **Book-settings unreachable ≠ no override** (finding TEN-6): if composition-service is down/slow, affected fields resolve to `source_tier: "unavailable"` (mirroring `resolve_work`'s existing `unavailable` status), and the caller surfaces it / blocks — it does **not** silently fall to Account (that would be a brand-new silent fallback). A short TTL cache avoids a per-turn hard dependency.

### 3.3 System tier &amp; presets (finding TEN-3)

The System tier holds only **deploy/admin-owned** defaults (env ceilings, seed values) — **read-only to users**. **System-prompt presets are a client-side seed constant** (`PRESETS`), *not* a resolvable DB tier and *not* user-authorable in this spec. A "Custom" prompt persists as the resolved `system_prompt` string in the user's `behavior` blob; there is no shared preset row (so no `UNIQUE(code)` smell). A future per-user preset store, if built, must be `UNIQUE(owner_user_id, code)` with System rows admin-only — explicitly out of scope here.

### 3.4 Model roles (finding TEN-5)

One canonical **closed `ModelRole` enum** — `chat · composer · planner · embedding · rerank · critic` — shared and enum-validated by all three stores (`user_default_models.capability`, `work.settings.model_roles{}`, session columns) so no tier is read under a mis-spelled key. `embedding`/`rerank` are provider capabilities; `composer`/`planner`/`critic` are **app-roles that call the `chat` capability** — their **Account** default resolves from `user_default_models` under their own key **if present, else falls back to the `chat` capability default** (verified `user_default_models` already admits `planner`; `composer`/`critic` keys to be added to the capability domain).

### 3.5 Setting categories &amp; their tiers

| Category | Fields | Account store | Book store | Session store |
|---|---|---|---|---|
| **Models** | chat, composer, planner, embedding, rerank, critic | `user_default_models` (per role, §3.4) | `work.settings.model_roles{}` (**new** per-role map; **dual-written** with legacy `default_model_ref`+`critic_model_ref` during compat) | session `model_ref`/`composer_model_ref`/`planner_model_ref` (existing) |
| **Behavior** | system_prompt(+preset), temperature, top_p, max_tokens, reasoning_effort, permission_mode | **new** `user_chat_ai_prefs.behavior` (per user) | `work.settings.behavior{}` (**new**, optional subset) | session `generation_params` + per-turn `permission_mode` (existing) |
| **Grounding &amp; memory** | grounding_enabled, linked project_ids, recent_message_window | **new** `user_chat_ai_prefs.grounding` | `work.settings.grounding{}` (optional) | session `project_ids`/`project_id` (existing) + **new** session `grounding_enabled` |
| **Voice** | stt_*, tts (per-surface), vad_*, speed | **new unified** `user_chat_ai_prefs.voice` (replaces `voice_prefs` **and** the voice half of `media_prefs`) | — (not book-scoped) | **new** session `voice_overrides` (persists a saved voice — fixes silent `af_heart`) |
| **Context mgmt** | mode(auto/on/off), t5, t4, d13a, trigger_ratio, tool_result_cap | **new** `user_chat_ai_prefs.context` (default `mode=auto`) | `work.settings.context{}` (optional) | **new** session `context_overrides` |

## 4. Data model

### 4.1 New: `user_chat_ai_prefs` (per-user, **Per-user tenancy tier**) — chat-service
```
user_chat_ai_prefs(
  owner_user_id  uuid PK,                            -- scope key (tenancy)
  behavior       jsonb not null default '{}',
  grounding      jsonb not null default '{}',
  voice          jsonb not null default '{}',        -- see §4.4 (per-surface sub-objects)
  context        jsonb not null default '{"mode":"auto"}',
  version        bigint not null default 0,          -- optimistic-concurrency guard (§4.5)
  updated_at     timestamptz not null default now()
)
```
- Model **account** defaults stay in `user_default_models` (one SoT per fact — do not duplicate).
- `GET /v1/chat/ai-prefs` · `PATCH /v1/chat/ai-prefs`, fronted through `api-gateway-bff`.

### 4.2 Extend `work.settings` (per-book, owner-scoped) — composition-service
Add optional nested override maps; **dual-write** the legacy scalars during compat (finding MIG-3):
```
work.settings.model_roles = { chat?, composer?, planner?, embedding?, rerank?, critic? }  -- each {model_ref, model_source}
work.settings.behavior/grounding/context = { ...optional subsets }
```
- **Dual-WRITE** (not dual-read): new code writes **both** `model_roles.chat` and legacy `default_model_ref` (and `.critic`) on every save; resolver prefers `model_roles.*` when present, else the scalar. Legacy scalars dropped only in a **later** milestone after all writers are on new code (kills concurrent-old-code divergence + rollback loss).

### 4.3 Extend chat `sessions` (per-session) — chat-service
Add nullable columns (null = inherit): `grounding_enabled bool`, `voice_overrides jsonb`, `context_overrides jsonb`. Pre-migration rows are null ⇒ inherit — safe by design.

### 4.4 Voice blob shape — unify the STORE, not the VALUE (finding MIG-1/MIG-2, UX-3)
A single `voice` blob, but **TTS playback stays per-surface** because a voice ID is only valid for its model:
```
voice = {
  stt: { source, model_ref, model_name, language, ... },   -- shared
  vad: { silence_frames, min_duration_ms, ... },           -- shared
  speed, auto_play, pause_mic_during_tts,                   -- shared
  chat:    { tts_source, tts_model_ref, tts_voice_id },     -- e.g. Kokoro/af_heart
  reading: { tts_source, tts_model_ref, tts_voice_id }      -- e.g. OpenAI/alloy
}
```
- Migration is **lossless**: chat fields ← `voice_prefs`, reading fields ← `media_prefs` — no winner rule, no reading-voice regression.
- **`tts_voice_id` always travels coupled to its `tts_model_ref`.** Voice options are **derived from the selected TTS model** (resolved via provider-registry / `useUserModels`), never a hardcoded list (kills the `alloy/…` hardcoded-list + the model↔voice mismatch that would revive the `af_heart` silent fallback). On TTS-model change, the persisted voice is **re-validated** against that model's voice list; invalid ⇒ "voice X unavailable for model Y — pick one", never a silent fallback.
- `media_prefs` residual = image/video/theme only; M-Voice shrinks the `MediaPrefs` type and deletes the ReadingTab TTS UI in the **same** milestone (no resurrected writer).

### 4.5 Concurrency — field-merge, not blob-LWW (finding TEN-4/MIG-9/UX-2)
`PATCH /v1/chat/ai-prefs` is a **deep field-merge**: apply only the keys present in the body into the target jsonb (`col = col || $patch` per sub-key / `jsonb_set` per leaf), matching auth-service's existing `||` semantics — device A editing `voice.speed` and device B editing `stt.source` **both** survive. An explicit `null` leaf = "clear to inherit" (distinct from absent = untouched). A `version` **If-Match** guard 412s on a genuine concurrent conflict rather than silently clobbering.

**Tenancy check (LOCKED):** every new table/column carries a scope key (`owner_user_id`; book via owner-scoped `work`; session user-scoped). No shared/global user-writable row. System tier admin/deploy-owned, read-only.

## 5. Precedence vs the env flags (finding TEN-9, RES-2)

Context-budget env flags split into two roles:
- **Deploy ceiling / kill-switch (System tier, unchanged):** an operator can force a tier **off** platform-wide. The env flag is a **max**; a user can only turn a tier **on** if the ceiling permits, always **off**.
- **Per-user/session knob (new):** within the allowed envelope, `context.mode` + per-tier toggles decide.

**Effective = AND(deploy_allows, cascade_resolved(user_enables), all_dependencies_effective).** Two clarifications the review forced:
- The AND is applied **after** the tier cascade resolves the user value (Session ▸ Book ▸ Account) — not per-tier.
- **Inter-tier dependencies are part of the AND** (finding RES-2): T4 (story-state net) requires T5 (intent gate). If a user enables T4 but the deploy ceiling forces T5 off, T4 resolves **off** with UI state **"unavailable — requires T5, disabled by deployment"** — never silently on-without-prerequisite (which would produce the empty-context injection the `story-state-trigger-keys-on-full-context` lesson warns about). The context-tier dependency graph (T4⇒T5) is declared explicitly.

The UI shows a tier as **"disabled by deployment"** (distinct from user-off) when the ceiling or a dependency blocks it — no silent no-op.

## 6. API contracts (new/changed)

- `GET /v1/chat/ai-prefs` → `{behavior, grounding, voice, context}` (account view).
- `PATCH /v1/chat/ai-prefs` → partial **deep field-merge** (§4.5), `If-Match: version`; validates the closed-set enums (§8.1).
- `GET /v1/chat/effective-settings?book_id=&session_id=` → the resolved cascade for a context: per model role + per behavior/grounding/voice/context field, `{effective_value, source_tier, tier_stack}` (§3.1) with `source_tier ∈ {tool,session,book,account,system,unavailable,no_model_configured}`. `session_id` omitted ⇒ Session tier skipped per the §3.1 predicate. **This is the single endpoint chat and every studio tool call** — it replaces the ~8 independent resolutions. Liveness-validated against provider-registry (§3.1).
- Book overrides: composition-service `PATCH work.settings` accepts the nested maps + a grant-checked `GET /internal/works/{book_id}/settings?as_grantee=` (§3.2).
- Session overrides: existing `PATCH /v1/chat/sessions/{id}` + the 3 new nullable fields.
- Model lists come from provider-registry via `useUserModels` **for pickers**; the **effective resolver** does its own BE liveness check (the FE `useUserModels` is not authoritative for submit).

## 7. Migration (dual-write everywhere; drop legacy last)

1. **Voice unify (cross-service, lazy read-through — finding MIG-5):** source = auth-service `user_preferences.prefs` (`voice_prefs`+`media_prefs`); target = chat-service `user_chat_ai_prefs.voice`. On first `GET /v1/chat/ai-prefs` with empty `voice`, chat-service seeds it by reading the user's prefs via an auth-service internal route. **No bulk cross-DB sweep.** Migration is lossless (§4.4). During compat, the unified panel **dual-writes** back to `voice_prefs`/`media_prefs` so a rollback loses nothing (finding MIG-4).
2. **Book model roles (dual-write — §4.2):** new code writes both shapes; resolver prefers the map. Backfill lazily on next `work.settings` write.
3. **Account model defaults:** unchanged (`user_default_models` is already the account tier).
4. **localStorage reconciliation (finding MIG-8):** localStorage (`lw_voice_prefs`/`media_prefs`) is demoted to cache-only, but the **first** post-migration client load **reconciles** newer-than-server local edits **up** to the server before "server wins" takes over — never an unconditional clobber of unsynced offline edits.
5. **Drop legacy keys** (`voice_prefs`, `media_prefs.tts*`, `work.settings.default_model_ref`/`critic_model_ref`) in a **separate later milestone** (M-Drop) gated on the rollback window closing and all branches merged — never in the same migration that introduces the new store.
6. **Shared dev DB safety:** all backfills are **idempotent, additive-only, lazy-on-read**; any one-time bulk run is scoped to the **test account** only. No `DROP` interleaved with additive DDL (finding TEN-7/MIG-7).

## 8. Frontend architecture (MVC-compliant)

- **Provider hoist (finding UX-1 — the load-bearing FE fix):** mount `ChatAiSettingsProvider` in `WorkspaceShell` **as a sibling *outside* `LiveStateProvider`**, keyed by `bookId`, **unconditionally** (never behind a `bookId != null` ternary — that would remount in-flight `ComposeView`, the exact hazard `StudioFrame`/`CompositionPanel` are engineered against). The context `value` is **memoized with structural sharing** (explicitly *not* the un-memoized `{stream}` pattern in `LiveStateContext:39` that re-renders consumers per streamed token).
- **Split stable vs session context (Split-context rule):** the hoisted provider carries only the **Account+Book** resolved cascade (stable). The **Session tier is layered in at the consuming chat panel**, so a session-override edit doesn't re-render account-tier consumers. `useEffectiveModel(role)` is a **per-role selector** (memo boundary / `useContextSelector`-style), not `const {models}=useContext()`.
- **Writes flow through the context (finding UX-2):** settings panels call the context's mutation methods (not `aiPrefsApi` directly) → one PATCH optimistically updates the cascade, every consumer re-derives immediately; on success `invalidateUserModelsCache()` + refetch `effective-settings`. Kills the same-device stale-cascade "silent no-op" (a Frontend-Tool-Contract violation).
- **Tool refactor (scoped per finding UX-9):** the change is *"switch the default-value source from `list[0]`/local → `useEffectiveModel(role)`"*, **not** "add a picker." Only **`PlannerView` + `ReferencesPanel`** remain bespoke `<select>`s to replace with `ModelPicker`; `SelectionToolbar`/`SceneGraphCanvas`/motif already use it and just need the default source redirected. Keep the `DockSlot` mount list **byte-identical** (no remount). Note: existing users' toolbar model shifts from favorite→cascade — intended, call out in release notes.
- **Consolidated panel:** `features/settings/chat-ai/` (Models / Behavior / Grounding / Voice + buried Advanced: Context, Developer). The session subset is a slimmed `SessionSettingsPanel` reading the same context, showing tier chips.
- **Chip semantics (finding UX-5):** chips key on **`source_tier`**, never value-equality — "set here · matches book" ≠ "inherited"; always offer "clear override → inherit (would be Z)" using `tier_stack`.
- **Scope switcher (finding UX-6):** Account edits show an impact hint ("Applies to N books that don't override this"); **save-per-scope** with a dirty-buffer guard on scope switch; the "This book" option **disables** (not silent no-op) when no book is in scope.
- **Dock reuse (finding UX-8):** the consolidated panel uses **container-relative** sizing (no `100vw/100vh/fixed/inset-0` — the `dockview-panel-fixed-positioning-window-scoped-bug`) and a **container-query / `dockMode` prop** for responsive layout, not `@media` window width. Dock-embedded live smoke at a narrow panel width.
- **Delete/redirect** duplicates: `VoiceSettingsPanel`→Voice sub-panel; `ReadingTab` TTS (incl. its bespoke `aiModelsApi` fetch → shared source)→Voice; unify the 6-vs-4 preset lists into one `PRESETS`.

### 8.1 Closed-set enums (finding UX-3) — shared FE/BE module + parity test
These are REST (outside `contracts/frontend-tools.contract.json`), so add a **dedicated shared enum module + a parity test** — "PATCH validates enums" alone gives no cross-side guarantee: `permission_mode∈{ask,plan,write}` · `reasoning_effort∈{off,low,medium,high}` · `context.mode∈{auto,on,off}` · `stt_source`/`tts_source∈{browser,ai_model}` · `model_source`. **`tts_voice_id` is NOT a static enum** — dynamically validated against the resolved TTS model's voice list (§4.4).

## 9. Milestones (each independently shippable; runs the full /loom cycle)

| M | Goal | Services | Risk |
|---|---|---|---|
| **M1 — Resolver + storage spine** (merged; finding MIG-7 — the M1/M2 split was fake) | `user_chat_ai_prefs` + book `model_roles` (dual-write) + session cols; the §3 cascade + `GET /v1/chat/effective-settings` with per-tier liveness; grant-gated book read; `useEffectiveSettings`/`useEffectiveModel`; wire `PlannerView`+`ReferencesPanel`+the `list[0]` tools to inherit. | chat-service, composition-service, provider-registry (read), FE | **High** — the core seam; live-smoke studio inherit + shared-book grant |
| **M2 — Models + Behavior panel** | two-tier UI, scope switcher, `{effective,source,stack}` display, tier chips; de-silence behavior defaults (reasoning/permission/sampling shown). | FE | Low |
| **M3 — Grounding &amp; Memory** | explicit grounding toggle: `grounding_enabled=false` **short-circuits** the `gate_disabled` force-on branch (`stream_service:1812`); reconcile OFF with T4 story-state + anti-confab (§11 GR-4). | chat-service, FE | Med |
| **M4 — Voice unify** | per-surface voice blob (§4.4), lazy cross-service seed, dual-write back, persist session voice, one Voice panel, ReadingTab TTS removed same-milestone. | chat-service, auth-service (read), FE | Med |
| **M5 — Context management** | mode=auto/on/off + per-tier, `AND(deploy, cascade, deps)` (§5), per-session override; folds in the context-mgmt mockup. | chat-service, FE | Med |
| **M-Drop** | remove legacy keys after rollback window (§7.5). | all | Low |

## 10. Verification (per milestone; live-smoke token required, ≥2 services)

- **M1:** studio tool with no override runs the book (else account) model; a book override cascades to session+tools (live-smoke, test account, chat+composition). `effective-settings` returns correct `source_tier` for every tier permutation incl. a **dead ref at a middle tier** (skips it, names it) and **all-dead** (`no_model_configured`, no 404). **Shared-book:** a grantee inherits the **owner's** book model via the grant-gated read; a grantee **cannot** write `work.settings`. Multi-model turn pins one snapshot at turn start (RES-7).
- **M3:** grounding OFF at the **T5-gate-off default** ⇒ turn issues **no** `build_context` retrieval (verify by trace/telemetry effect, not raw stream); ON ⇒ retrieval present. OFF also suppresses/annotates anti-confab per GR-4 (no silent new confabulation).
- **M4:** set a TTS voice → reload/new session → same voice (persisted, not `af_heart`); reading voice unchanged by migration (lossless); voice options derived from the model; rollback reads old keys intact (dual-write).
- **M5:** user enables a tier the deploy ceiling forbids ⇒ "disabled by deployment", effective off; T4-without-T5 ⇒ unavailable, not silently on.

## 11. Edge cases — resolved (was §11 seed; hardened by §12 review)

| # | Edge case | Resolution | Where |
|---|---|---|---|
| **EC-1** | Model deleted/deactivated at a middle tier (book dead, session copied same dead ref) | Liveness-validate **every** tier from provider-registry (one source for FE+BE); skip dead at any tier; name skipped tiers; all-dead ⇒ `no_model_configured`, never mid-turn 404 | §3.1, §6, M1 verify |
| **EC-2** | Empty `user_default_models` (test-account reality) | Account tier null ⇒ fall to System; System model may be unset ⇒ explicit "pick one", no silent 404 | §3.1, UX-10 |
| **EC-3** | Shared book — whose model applies; collaborator mutating owner's row | Book tier = **owner's** `work.settings` via grant-gated read; writes owner-only; grantee overrides at own Session/Tool; widening write scope = tenancy defect (LOCKED) | §3.2 |
| **EC-4** | Two-device concurrent prefs edit | Deep **field-merge** + `version` If-Match (not blob-LWW) | §4.5 |
| **EC-5** | In-flight generation while model changes; multi-model turn (planner→composer→subagent) | Resolve the **whole settings snapshot once at turn start**, thread through all sub-steps, never re-resolve mid-turn | §3.1, M1 verify |
| **EC-6** | Book override changes mid-session; FE cache stale vs server submit | Writes go through the context (invalidate-on-write); `effective-settings` carries `resolved_at`/etag; **server resolve at submit is authoritative** | §8, RES-6 |
| **EC-7** | Deploy ceiling flips a context tier off while user has it on; T4 without T5 | `AND(deploy, cascade, deps)`; "disabled by deployment"/"requires T5"; never silently on | §5 |
| **EC-8** | grounding OFF + T4 story-state net + anti-confab | Define matrix: OFF short-circuits gate-off force-on; T4 gated by `grounding_enabled`; anti-confab suppressed **or** UI warns "grounding off — may invent lore" (no silent confab) | §5, M3, **GR-4** |
| **EC-9** | Voice merge collapsing chat+reading TTS | Per-surface `voice.chat`/`voice.reading` coupled (model,voice); lossless; voice options model-derived, re-validated on model change | §4.4 |
| **EC-10** | Session-skip ambiguity for embedded co-writer chat | Session tier iff surface **owns** the session (co-writer ⇒ 5 tiers); studio tool w/o owning session ⇒ 4 | §3.1 |
| **EC-11** | Provider remount / re-render bomb | Hoist outside `LiveStateProvider`, unconditional, memoized; split stable/session; per-role selector | §8 |
| **EC-12** | "Ask each time" has no store; inherit chip lies when inherited model dead | Drop persisted "ask" mode (session-ephemeral override); chip shows resolved name + "(inheriting X — unavailable, using Y)" via `includeInactive` | §3.1, UX-4 |
| **EC-13** | Migration on shared dev DB; rollback data loss; cross-service boundary | Idempotent lazy-on-read; dual-write both shapes; drop legacy in separate M-Drop; test-account-scoped bulk; auth→chat via internal read | §7 |
| **EC-14** | Dock reuse fixed-positioning/viewport bug | Container-relative sizing, container-query responsive, narrow-panel dock smoke | §8, UX-8 |

## 12. Review provenance

Hardened by a 4-lens adversarial edge-case pass (2026-07-05): **tenancy/data-model**, **resolution correctness**, **migration/compat**, **FE-state/UX**. Findings folded in above; tags (TEN-/RES-/MIG-/UX-/GR-/EC-) cross-reference. Load-bearing structural corrections vs the first draft: (1) Book tier is owner-scoped + grant-gated, not a shared per-book row; (2) unify the store, not the value (voice); (3) dual-write, not dual-read; (4) one liveness-validating BE resolver; (5) AND-post-cascade with inter-tier deps; (6) provider hoisted outside the streaming context. Two items **decided** (were open): shared-book Book tier = owner's (grant-gated); presets = client-seed constant, no user preset store this pass.
