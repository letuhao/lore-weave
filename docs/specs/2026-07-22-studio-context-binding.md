# Spec — Studio Context Binding (ambient book/project scope for in-system agents)

- **Date:** 2026-07-22
- **Status:** **BUILT (book-first pilot) + MEASURED** (2026-07-22) — SEALED design realized in commits `263fcd483` (SDK + book_*) + `e3af56d9b` (gateway forward + chat-service + A/B). Live-proven through ai-gateway; ambient vs baseline −25%/−46% tokens, book_id 0/5 emitted ([AMBIENT_RESULTS.md](../eval/tool-liveness/manuscript-structure/AMBIENT_RESULTS.md)). Fan-out to other domains (glossary/composition/kg) is the remaining work. One deviation from §2.4: book_id was made optional in the tool's OWN schema (auto-propagates through federation) rather than dropped only on the bound surface — simpler, and external callers fail-closed in the handler; re-requiring book_id on external surfaces is a follow-on if wanted.
- **Size:** L (cross-cutting: chat-service envelope + `loreweave_mcp` SDK identity + every domain tool's id-resolution; no DB migration)
- **Governs:** MCP-tool-io (IN-*), User Boundaries & Tenancy (the scoping cascade), SEC-1 (identity from envelope, never a tool arg), settings-and-config (SET resolution cascade — same shape).

---

## 1. Problem

When an in-system agent runs **inside the writing studio**, it is already bound to one book — yet every MCP tool takes `book_id` (and often `project_id`/`chapter_id`) as an **explicit arg the model must produce**. For a weak model this is a real error + cost surface, and it doesn't match the user's mental model ("I'm working on THIS book").

### 1.1 What exists today (as-built — honest baseline)

A **prose-note + arg-repair patchwork**, not an architecture:

1. The session resolves `{book_id, chapter_id, project_id}` from the studio context (`stream_service.py` ~3802/4115/4257).
2. The model is told the id **in prose**: `"You are working inside book_id=…"` (~4260) — and must **transcribe** it into each call.
3. `_inject_context_ids` (~1188) repairs at dispatch, **conservatively**:
   - fills the id when the model **omits** it (only if the tool's schema declares the key),
   - overrides a **non-UUID mistranscription** with the known id,
   - **honors a valid but different UUID** — treated as a deliberate cross-book call, never silently redirected.

Measured failures this was built for (gemma-4-26b): `{}` → `VALIDATION: missing book_id` retry loop; `book_id="019f5239…e6"` (one char added) → `400 book_id must be a UUID`; scalar id wrapped as `[uuid]`. Real, recurring, weak-model-specific.

### 1.2 Why it's a patch, not the design

- The scope lives in the **client** (chat-service) as **per-arg** injection for **3 ids only** (`book_id`/`chapter_id`/`project_id` — not `world_id`/`arc_id`/`work_id`), tool-by-tool, only when the schema declares the key.
- The **tool schema still requires `book_id`**, so the model is still prompted to produce it — the repair catches *some* failures but the model still spends reasoning/tokens on a UUID it should never touch.
- `project_id`/`work_id` are passed **alongside** `book_id` (the model juggles up to 3 ids) instead of being **derived** from the one thing that matters (the book).
- The envelope carries identity (`X-User-Id`, `X-Session-Id`, `X-Trace-Id`, `X-Mcp-Key-Id` — `sdks/go/loreweave_mcp/identity.go`) but **no book scope** — so each domain service is blind to the ambient book; only the chat-service client knows it.

### 1.3 The framing that unlocks it

"Ép" (force) conflates two very different things:
- **(a) ambient default** — inject the scope so the agent needn't pass it, can't get it wrong;
- **(b) hard sandbox** — forbid the agent from touching any other book.

The **Cursor/Claude-Code lesson is about (b)**: they dropped the *restriction* (ineffective + inconvenient) but **kept the workspace/CWD as an ambient default (a)**. This spec does **(a), never (b).**

**Security is already handled elsewhere** — identity is enveloped (SEC-1) and every tool `grant`-checks the user against the book. A user can only touch books they hold a grant on, regardless of what `book_id` is passed. ⇒ Binding is **not** a safety mechanism; its whole value is **correctness/ergonomics + matching the user's "I'm in this book" model.** That removes any temptation to build a wall.

---

## 2. Design — promote the ambient scope into the envelope (like identity)

### 2.1 Envelope scope

Add `X-Book-Id` (and only that — see §2.3) to the MCP envelope, lifted into the tool ctx exactly like `X-User-Id`:
- `sdks/go/loreweave_mcp/identity.go` — new `HeaderBookID = "X-Book-Id"`; `IdentityMiddleware` lifts it into ctx; add `BookIDFromCtx(ctx)` mirroring `UserIDFromCtx`. (Python SDK mirror.)
- chat-service, on a **book-bound surface**, sets `X-Book-Id` on the tool-call envelope from the session's resolved book — the same place it already sets `X-User-Id`. Computed **per-turn from the live session binding** (not cached), so a mid-session book switch (the embedded-chat re-scope path) is reflected on the next turn.
- **External/global agents** simply don't send the header (they have no bound surface).

> **INVARIANT (critical) — `X-Book-Id` is a SCOPE HINT, never authorization.** The ambient book is `grant`-checked **exactly like an explicit arg** — a spoofed, stale, or foreign `X-Book-Id` grants **zero** access (resolves → grant check → uniform 404, no owner oracle). This mirrors SEC-1 (`X-User-Id` isn't authz either) and the internal-route rule "the token authenticates the SERVICE, the grant still gates." The envelope only chooses a *default id*; it can never widen access.

### 2.2 Server-side resolution cascade (per tool, replaces the client-side patch)

Each tool resolves its effective book as a cascade (mirrors the User-Boundaries tier cascade + SET-* resolution):

```
effective_book_id =
   explicit arg, if present AND a valid UUID          # deliberate call (incl. cross-book) wins
   else envelope X-Book-Id, if present                # ambient default (the studio binding)
   else → required-arg error                          # external agent that passed nothing: fail-closed
```

- **Omitted arg on a bound surface** → resolves from the envelope. The model **need not emit `book_id` at all** — this *eliminates* the transcription burden rather than repairing it.
- **Non-UUID arg + envelope present** → envelope wins (**silent repair**; same as today's S02 override — a malformed value is a mistranscription, never a deliberate cross-book call, so no confirm).
- **Valid different UUID (cross-book), grant-ok** → honored, but **the timing of the confirm depends on read vs write** (the correctness fix below).
- **Neither arg nor envelope** → fail-closed with a clear required-arg error. **Never** act on a null/guessed book (no silent seam).
- **Effective id is exposed** in the result (`effective_book_id` + `scope_source: "arg" | "envelope"`) so a human/trace can always see which book a call actually hit (SET "expose effective value + source" discipline).

**Cross-book confirm — READ is advisory, WRITE is pre-confirm (correctness fix to Q1).** A post-hoc `scope_note` is fine for a read, but a *write* that executes first and notes second has **already mutated the wrong book** before the user can react. So the soft-confirm splits by tier:
- **Read (Tier R) on a different book** → execute + return an advisory `scope_note` ("showing «B», not the studio's «A»"). No blocking.
- **Write (Tier A/W) on a different book** → **do NOT execute.** Return a typed `cross_book_confirm_required` result carrying the target book (id + title); the client raises the soft confirm; on approval it re-issues with an explicit `allow_cross_book: true` (or rides the existing confirm-token spine). This still *allows* cross-book (not a wall) while never silently mutating the wrong manuscript. `allow_cross_book` is the studio-surface opt-out of the ambient default — absent on external surfaces (they have no ambient to differ from).

### 2.3 Derive project_id / work_id — don't pass them

A studio agent should deal with **one** concept: "this book." `project_id`/`work_id` are **derived server-side** from `effective_book_id` via the canonical-Work resolver (`work_resolution.ensure_work` / `canonical_work`), reusing the pending-vs-absent semantics already there. So:
- **Studio agents never pass `project_id`/`work_id`** — 3 ids the model juggled → **0**.
- **External agents** still pass them explicitly (no envelope, no derivation context).
- This is why only `X-Book-Id` goes in the envelope: book is the root; the rest derive.
- **Derivation is off `effective_book_id`** (the resolved book, including a cross-book explicit arg) — never the raw envelope — so project/work always match the book actually being acted on.
- **Derivation can legitimately yield None** (a book with **no Work**, or a **pending** Work whose project isn't minted). A tool that needs a project MUST then **fail closed** with the honest reason ("this book has no composition project yet — create/plan it first"), distinguishing *pending* (retry) from *absent* (create) exactly as `work_resolution` already does. **Never** derive a null project and write against it (the no-silent-seam rule). A tool keyed by `project_id` but not `book_id` gets the symmetric helper `ResolveProjectScope(arg, ctx)` that derives from the envelope book.

### 2.4 Tool-schema shape (bound vs global)

Two options (§ open Q2):
- **(A) Keep `book_id` in the schema as `required`, resolve server-side.** Lowest churn; the model *may* still emit it; the cascade covers omission. External contract unchanged.
- **(B) Advertise `book_id` as optional on a bound surface** (the chat-service surface builder drops it from `required` / annotates "resolved from studio context"), so the model is never even asked for it. Strongest ergonomics; the surface already rewrites advertised tools per-surface (hot-set), so this is a natural extension. External surface keeps it required.

Lean **(B)** for the bound surface (kills the burden at the source), **(A)** as the safe fallback everywhere else.

**Migration atomicity (critical) — schema-drop and envelope-resolve ship TOGETHER, per tool.** Dropping `book_id` from the advertised `required` while the tool still 400s on a missing `book_id` = a silent break (the two-schemas-joined-by-the-LLM drift, the Frontend-Tool-Contract bug class). So a tool is **opted in** explicitly — a `_meta` flag `scope: {book: "ambient"}` marks it "resolves `book_id` from the envelope." Only opted-in tools get the `required`-drop on the bound surface; every un-migrated tool keeps `book_id` required and behaves exactly as today. This makes the rollout **per-tool atomic** (mirrors the `visibility:legacy` opt-in) and is the mechanism the surface builder reads to decide the drop. `_inject_context_ids` composes cleanly through the transition: it only fills a key the advertised schema declares, so once a tool's `book_id` is dropped-from-advertised it simply skips (no double-fill).

### 2.5 What the S02 patch becomes

`_inject_context_ids` stays as **belt-and-suspenders** during migration (it still repairs a mistranscription on any surface), but the *primary* mechanism moves to the envelope + server cascade. Once tools resolve from the envelope, the prose `book_context_note` can shrink to a plain "you are in book «Title»" (human-readable, not a UUID to transcribe).

---

## 3. What changes where

| Layer | Change |
|---|---|
| `loreweave_mcp` (Go + Py SDK) | `HeaderBookID` + lift into ctx + `BookIDFromCtx`; shared `ResolveBookScope(argBookID, ctx)` (cascade + `scope_source` + the read-advisory / write-`cross_book_confirm_required` split) and `ResolveProjectScope(argProjectID, ctx)` (derive-from-book, None-aware) |
| chat-service | set `X-Book-Id` per-turn on the bound-surface envelope (where `X-User-Id` is set); drop `book_id` from `required` **only** for tools flagged `_meta.scope.book="ambient"`; shrink the prose UUID note; render the cross-book soft-confirm |
| domain tools (book/glossary/composition/kg) | opt in via `_meta.scope.book="ambient"`; replace `book_id`-from-arg with `ResolveBookScope(...)`; derive `project_id`/`work_id` (None-aware fail-closed) instead of taking them on the studio path |
| ai-gateway | forward `X-Book-Id` alongside the identity headers (same threading as `X-User-Id`) |

No DB migration. No new table. Grants unchanged (still the security boundary).

---

## 4. Edge cases (adversarial seal pass — resolved)

1. **Envelope book, no grant (stale/spoofed/revoked mid-session)** → resolves → grant check → uniform **404**. The envelope grants nothing (the §2.1 invariant). No cross-book confirm is raised for a book the caller can't access — **grant check precedes the confirm**, so a book the user lacks access to returns 404 and never leaks its existence (no owner oracle).
2. **Binding applies ONLY to tools that DECLARE `book_id`.** Inherently cross-book / library tools (`book_list` = "my books", search-across-books) take no `book_id` and are **unaffected** — the ambient never narrows a deliberately-global read.
3. **"Bound surface" is precise** = a studio/editor session with a *resolved* book. The **universal `/chat`** surface is NOT bound → `book_id` stays `required` there (a `/chat` turn that happens to mention a book is an external-style call; the model passes the id, as today).
4. **Cross-book explicit arg → all derivation keys off the EFFECTIVE book** (arg B), not the envelope (A): a write to B (post-confirm) derives B's project, never A's.
5. **Non-UUID arg vs valid-different-UUID are different paths**: malformed → **silent repair** from the envelope (a mistranscription is never a deliberate cross-book intent); valid-but-different → the read/write confirm split. This preserves today's S02 repair while adding the intent path.
6. **`chapter_id` is the NEXT ambient (editor open-chapter), same mechanism, deferred** past the book pilot — more volatile (the user switches chapters), so recomputed per-turn like `book_id`. Sub-book ids (`arc_id`, `node_id`, `entity_id`) are **never** ambient (many per book) — always explicit.
7. **`allow_cross_book:true` is a bound-surface-only field**; on an external surface there is no ambient to differ from, so it's absent/ignored (a global agent's `book_id` is simply its target).
8. **Undo/idempotency after a confirmed cross-book write** target the effective (confirmed) book — the undo hint carries B, consistent with §2.2.

---

## 5. Decisions (PO 2026-07-22)

- **Q1 — cross-book on a bound surface → RESOLVED: allow + soft confirm, split by tier (correctness refinement in §2.2).** Still allowed (grant-gated), never a wall — but a **read** returns an advisory `scope_note` while a **write** must **pre-confirm** (`cross_book_confirm_required` → re-issue with `allow_cross_book:true`), because a post-hoc note on a write has already mutated the wrong book. This is the faithful realization of "soft confirm," not a change of intent.
- **Q2 — schema shape → RESOLVED: drop `book_id` from `required` on the bound surface (option B).** The chat-service surface builder omits `book_id` from `required` (annotated "resolved from studio context") when advertising to a book-bound surface, so the model is never asked for it. The external/global surface keeps it `required`. (§2.4.)
- **Q3 — first cut → book-first pilot** (`book_*`, where we just measured), then fan out to glossary/composition/kg — mirrors the visibility:legacy rollout.
- **Q4 — measurement → re-run the gemma-4 harness** with the bound surface (`book_id` omitted entirely) vs today (model transcribes it) → expect fewer tokens + zero mistranscription retries. Same method as the manuscript-structure eval.

---

## 6. Non-goals

- **No hard sandbox** (the Cursor/CC anti-pattern). Cross-book stays possible, grant-gated.
- **No change to the security model** — grants remain the boundary; this is ergonomics only.
- **No change for external/global agents** — they pass ids explicitly, exactly as today.

*SEALED. Verified against `stream_service.py` (_inject_context_ids / prose note / session resolution) + `identity.go` (envelope headers). The adversarial seal pass changed the mechanism in three places — the §2.1 authz invariant (envelope is scope, not access), the §2.2 read-advisory / write-pre-confirm split, and the §2.4 per-tool opt-in migration atomicity — none of which change the sealed intent. Build order: SDK helper → ai-gateway forward → book_* opt-in + chat-service surface drop → re-measure (§5 Q4).*
