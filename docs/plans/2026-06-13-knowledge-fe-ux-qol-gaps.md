# Knowledge / BYOK FE — UX & QoL Gap Review + Fix Plan

**Date:** 2026-06-13
**Author:** UX review (user-reported + walkthrough as the end user)
**Branch context:** `feat/auto-draft-factory-gaps`
**Status:** PLAN — not yet built. Blocks the user from building a knowledge graph end-to-end.

---

## TL;DR

The user cannot complete the **register-a-rerank-model → create-knowledge-project → build-graph** flow
from the UI. Four distinct gaps stack up into a hard wall:

1. **Rerank model discovery is silently broken** — the local rerank backend's `/v1/models`
   returns a Cohere-shaped `{"models":[…]}` body, but provider-registry's inventory sync
   only parses the OpenAI-shaped `{"data":[…]}`. Discovery returns empty, no error shown.
2. **The model-register form has no rerank capability** — `CapabilityFlags` lists 12 flags,
   none of them rerank. There is **no way to tag a model as rerank-capable**, and **no
   cross-encoder test** to confirm the connection works. The `RerankModelPicker` filters on
   `capability=rerank`, so with no way to set that flag, the picker is **permanently empty**.
3. **"Book ID (optional)" is a raw UUID textbox** — `ProjectFormModal` asks the user to paste
   a 36-char UUID they have no way to know. There is no book search/picker.
4. **Knowledge dialogs don't constrain to viewport height** — `FormDialog` (the shared base)
   has no `max-h`/scroll, so taller dialogs (BuildGraph, ProjectForm on edit) push their
   action buttons off-screen with no way to scroll to them.

Net effect, in the user's words: *"the platform's backend is usable but the frontend is
either un-wired or missing a lot of UX."* Items #1+#2 are a **functional blocker** (cannot
build knowledge at all); #3+#4 are **friction** that compounds it.

---

## User-perspective walkthrough (role-played as the end user)

> I want to build a knowledge graph for one of my books. I open **AI Models → Credentials**,
> add my local rerank server as a provider. The setup help talks about an OpenAI-compatible
> endpoint but says nothing about a **models endpoint** or what shape it expects — unlike the
> chat/embedding guidance. I save the credential and hit **Add Model**. It syncs the
> inventory… and the rerank model never shows up. No error, no "0 found for rerank", just an
> empty group. I have no idea if my server is wrong, my key is wrong, or the app is wrong.
>
> I try to register the model by hand instead. The **capability checkboxes** are chat, vision,
> tool-calling, embedding, tts, stt, image, moderation… **there's no "reranker"**. So even if
> I force the model in, I can't mark it as a reranker, and there's **no "test" that actually
> sends a cross-encoder query** to prove it connects. Dead end.
>
> I give up on rerank (it's "optional" anyway) and go to create a **knowledge project**. The
> form has **"Book ID (optional)"** — a textbox wanting a `uuid`. I don't have a UUID. I know
> my book by its *title*. There's a perfectly good book browser elsewhere in the app, but here
> I'm asked to paste a GUID by hand. I leave it blank and hope that's fine.
>
> Finally I open **Build Graph**. The dialog has scope options, a chapter range, a model
> picker, and an estimate — and it's **taller than my screen**. The **Build / Cancel buttons
> are below the fold and the dialog doesn't scroll**. I can't submit. I'm stuck.

Every one of these is a *wired-backend / unwired-or-rough-frontend* gap, exactly as reported.

---

## Issue 1 — Rerank integration: no `/models` guidance + non-OpenAI discovery shape

### What the user sees
Setup guidance for rerank doesn't mention a models endpoint like the other integrations do,
and when added, the rerank server's model can't be discovered during provider setup.

### Root cause (confirmed in code)
- Inventory sync calls the provider adapter's `ListModels()`. For custom / OpenAI-compatible
  providers, `openaiAdapter.ListModels()` fetches `GET {base}/v1/models` and parses
  `out["data"].([]any)` — the OpenAI envelope.
  `services/provider-registry-service/internal/provider/adapters.go:665-684`
- The local rerank backend **does** implement `GET /v1/models`, but returns a Cohere/native
  envelope: `{"models":[{"id":…,"state":"loaded",…}]}` — **not** `{"data":[…]}`.
  `../local-rerank-service/app/routers/models.py:16-22`
- `ResolveAdapter()` has **no `rerank` case**; rerank falls through to the OpenAI adapter,
  whose `.data` parse misses `.models`, returns the (empty) static inventory, and the sync
  reports **zero models with no error**.
  `services/provider-registry-service/internal/provider/adapters.go` (`ResolveAdapter`)
- Rerank invocation itself works fine and bypasses adapters entirely via
  `provider.Rerank()` → `POST {base}/v1/rerank` (`internal/provider/rerank.go:22-40`,
  wired at `internal/api/server.go:2472-2552`). So **invocation is fine, discovery is the gap.**

### Fix options
- **(A) Backend, recommended) Teach inventory sync the rerank shape.** Either:
  - add a `rerank`-aware adapter (or a branch in the OpenAI adapter) that, when the
    `/v1/models` body has `.models` instead of `.data`, parses it and tags each model
    `capability_flags.rerank = true`; **or**
  - make the local-rerank-service `/v1/models` *also* emit an OpenAI-compatible
    `{"data":[{"id":…,"object":"model"}]}` envelope (cheaper, keeps provider-registry generic,
    but only helps this one backend).
  - Prefer the adapter approach — it generalizes to any Cohere-style rerank server and keeps
    the BYOK invariant (no per-service URL/token; still resolved through provider-registry).
- **(B) FE guidance parity.** Add rerank-specific setup help in the provider dialog mirroring
  the chat/embedding guidance: state that the server must expose `/v1/models` (or that the
  user can register the model name by hand), and what a working rerank endpoint looks like.
  Lives alongside the existing API-standard/endpoint hints in
  `frontend/src/features/settings/ProvidersTab.tsx:~444-456` + `i18n/locales/*/settings.json`.

### Acceptance
- Adding the local rerank credential and clicking **Refresh** surfaces the rerank model in the
  Add-Model inventory under the **Reranker** group.
- If discovery genuinely returns nothing, the UI says so per-capability (see Issue 2 fix).

---

## Issue 2 — Model register GUI has no reranker + no cross-encoder test

### What the user sees
No way to choose "reranker" when registering a model; no test to confirm a cross-encoder
connection succeeds.

### Root cause (confirmed in code)
- `CapabilityFlags` hard-codes 12 flags and **omits rerank entirely**:
  `KNOWN_FLAGS = ['chat','vision','tool_calling','extended_thinking','json_mode','reasoning','tts','stt','image_gen','video_gen','embedding','moderation']`
  `frontend/src/features/settings/CapabilityFlags.tsx:3`
- The `RerankModelPicker` (knowledge) and campaign reranker role both filter the user's models
  by **`capability=rerank`**:
  `frontend/src/features/knowledge/components/RerankModelPicker.tsx:39`,
  `frontend/src/features/campaigns/types.ts:80` (`reranker: 'rerank'`).
- **Capability-string inconsistency:** the settings layer calls it **`reranker`**
  (`frontend/src/features/settings/api.ts:87` `CapabilityType`, `AddModelModal` CAP_STYLES,
  `settings.json` `cap.reranker`), but the *filter* used to retrieve models is **`rerank`**.
  These must be reconciled or the picker will never match even once a flag exists.
- The **verify** path is generic — `POST /v1/model-registry/user-models/{id}/verify`
  (`frontend/src/features/settings/api.ts:179-182`) — and there's no evidence it performs a
  **rerank-specific** round-trip (a cross-encoder query+documents call). For chat/embedding a
  generic ping works; for rerank the user needs proof the `/v1/rerank` call actually scores.

### Fix
1. **Add a rerank capability to the register form.** Decide the canonical flag key
   (recommend **`rerank`** to match the existing filters; then fix `settings` to use `rerank`
   too — or vice-versa, but pick one and reconcile everywhere). Add it to `KNOWN_FLAGS` +
   `capability.flag.rerank` i18n. This alone lets a user hand-register a rerank model and have
   it appear in `RerankModelPicker`.
2. **Per-capability "0 found" feedback in Add-Model inventory** so discovery emptiness is
   visible instead of silent (ties back to Issue 1).
3. **Rerank-aware "Test" button.** Extend the verify endpoint (or add a typed verify) so that
   when the model is rerank-capable it issues a real cross-encoder call
   (`provider.Rerank()` with a tiny query + 2 docs) and reports score/latency, not just a
   generic 200. Surface the result in `EditModelModal` next to the existing Verify result line
   (`EditModelModal.tsx:214-222`).

### Acceptance
- The register form shows a **Reranker** capability toggle; checking it makes the model appear
  in the knowledge `RerankModelPicker` and the campaign reranker role.
- **Test** on a rerank model sends a real rerank request and shows ranked scores / latency or a
  clear failure reason.

---

## Issue 3 — "Book ID (optional)" is a raw UUID textbox, needs a picker

### What the user sees
Creating a knowledge project offers an optional Book ID field but the user has no way to know
the UUID — there should be an advanced search/picker like the book browser.

### Root cause (confirmed in code)
- `ProjectFormModal` renders Book ID as a free-text `<input>` validated against a UUID regex,
  null on empty:
  `frontend/src/features/knowledge/components/ProjectFormModal.tsx:292-308`
  (`bookIdValid = bookId === '' || /^[0-9a-f-]{36}$/i.test(bookId)`, line ~131).
- A book-listing/browsing UI already exists in
  `frontend/src/features/chat/context/ContextPicker.tsx` (books tab via `booksApi.listBooks()`),
  but it is **not extracted as a reusable picker**, so the project form can't reuse it.
- `booksApi.listBooks()` (`frontend/src/features/books/api.ts:80-86`) lists the user's books;
  `listCatalog()` supports a `q` text search (public catalog only).

### Fix
- Extract a reusable **`BookPicker`** (search-as-you-type over `booksApi.listBooks()`, showing
  title/author, returning `book_id`) from the ContextPicker book-tab logic.
- Replace the raw UUID input in `ProjectFormModal` with `BookPicker` (keep "optional"; show the
  resolved title once chosen, with a clear/"change" affordance). Retain a fallback "paste ID"
  affordance for power users, but don't make it the primary path.
- Reuse the same picker in the campaign `BookProjectStep` if it has the same raw-id smell.

### Acceptance
- The project form lets the user **search a book by title and select it**; the stored value is
  still the `book_id` UUID. Leaving it unset remains valid.

---

## Issue 4 — Knowledge wizard dialogs ignore viewport height (no scroll, content clipped)

### What the user sees
Some knowledge wizards don't account for viewport height, so the dialog overflows and items
(including action buttons) fall outside the screen with no way to interact.

### Root cause (confirmed in code)
- The shared `FormDialog` base sets a fixed centered box with **no max-height and no scroll**:
  `Dialog.Content className="fixed left-1/2 top-1/2 … w-full max-w-lg -translate-x-1/2 -translate-y-1/2 … p-6"`
  `frontend/src/components/shared/FormDialog.tsx:19`
- Every knowledge dialog built on it inherits the flaw. Tallest offenders:
  `BuildGraphDialog` (scope radios + chapter range + LLM select + embedding picker + estimate),
  `ProjectFormModal` on edit (description + instructions textareas + embedding + rerank pickers).
- `ConfirmDialog` shares the same no-max-height pattern
  (`frontend/src/components/shared/ConfirmDialog.tsx`).

### Fix (one change, broad payoff)
- In `FormDialog.Content`, constrain to viewport and make the body scroll:
  add `max-h-[90vh]` (or `max-h-[calc(100dvh-2rem)]`), `flex flex-col`, and wrap `{children}`
  in a `flex-1 overflow-y-auto` region so the title + footer stay pinned while the body
  scrolls. Keep the footer outside the scroll area so action buttons are always reachable.
- Apply the same to `ConfirmDialog`.
- Use `dvh` (not `vh`) so mobile browser chrome doesn't clip the footer.

### Acceptance
- On a short viewport (and on mobile), every knowledge dialog scrolls its body and **keeps the
  primary action button reachable**. Verified on `BuildGraphDialog` + `ProjectFormModal` edit.

---

## Additional UX gaps found during the walkthrough (not originally reported)

- **A. Silent inventory emptiness is a systemic smell.** The Add-Model sync shows counts by
  capability but doesn't distinguish "synced, 0 rerank models" from "sync failed." Add an
  explicit per-capability empty/error state (covers Issue 1 + 2 and any future capability).
- **B. Capability-string drift (`rerank` vs `reranker`)** is a latent bug beyond rerank's UI:
  any code path that sets `reranker` but reads `rerank` (or vice-versa) silently no-ops.
  Reconcile to a single constant and add a unit test asserting the picker filter matches the
  flag key (a wiring test — mirrors the project's `nil-tolerant-decorator-needs-wiring-test`
  lesson: an end-to-end assertion that the two ends agree, not just that each compiles).
- **C. `RerankModelPicker` empty-state copy already points the user to "AI Models →
  Credentials"** — good — but that path currently *can't* produce a rerank model (Issues 1+2),
  so the guidance is a dead end until those land. Sequence the fixes accordingly.

---

## Suggested sequencing (unblock first)

| Order | Item | Why first | Size (rough) |
|------:|------|-----------|------|
| 1 | **Issue 2** — add `rerank` capability flag to register form + reconcile `rerank`/`reranker` string | Smallest change that makes rerank registrable by hand → unblocks the whole knowledge build even before discovery works | S |
| 2 | **Issue 4** — `FormDialog` max-h + scroll | One-file fix, unblocks Build Graph submit, broad payoff | XS–S |
| 3 | **Issue 1** — rerank inventory discovery (adapter parses `.models`) + FE rerank setup guidance | Makes discovery work so users don't have to hand-type; backend + FE | M |
| 4 | **Issue 2 (test)** — rerank-aware cross-encoder Verify | Confidence the connection works; depends on the flag landing | S–M |
| 5 | **Issue 3** — reusable `BookPicker` in project form | Pure friction-removal, no blocker | S–M |

Items 1+2 are a coherent FE effort; 3 is BE+FE; 4 is BE+FE; 5 is FE. Per the repo's
"size by complexity, run a coherent effort as one flow" rule, 1+2+5 (the FE QoL set) can run
as one continuous FE pass, with 3+4 (rerank discovery+test) as a second BE+FE pass.

## Verification notes (for whoever builds this)
- This is a **≥2-service** change set (provider-registry + frontend, and the sibling
  local-rerank-service for #1). Per CLAUDE.md, VERIFY needs **cross-service live-smoke**:
  add the local rerank credential on a real stack-up, Refresh inventory, confirm the model
  appears, register it, Test it (real `/v1/rerank` round-trip), then select it in a knowledge
  project and run Build Graph. Mock-only green is insufficient here — discovery + envelope
  shape is exactly the kind of contract bug mocks hide.
- Rebuild touched service images before live-smoke (stale images = false greens).
