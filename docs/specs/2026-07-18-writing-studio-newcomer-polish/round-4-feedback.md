# Round 4 — dogfood on the durable-gate-ACTIVATED build (2026-07-20)

**Origin:** a fresh first-run dogfood immediately after the **MCP-Tasks full activation** landed
(`tasks_gate_enabled=True`; all KIND-C confirms task-shaped; the `Out=any` gateway-federation fix).
Put on the newcomer hat again: created a brand-new book **"The Ashfall Chronicles"**, opened the
Co-writer Chat (model **Gemma-4 26B-A4B QAT**, lm_studio), and tried to (a) have the agent create a
chapter, then (b) delete a chapter — the path that exercises the newly-activated durable confirm gate.

**Headline:** the durable gate is wired correctly end-to-end — asked to delete a chapter, the agent
*itself* said *"Deleting a chapter is a high-impact action. I will first **propose** the deletion,
which will create a **confirmation card** for you to approve before any data is actually removed."* —
so the prompt + tool surface reflect the gate, and the `/mcp` path is proven. But the **local model
never actually pulled the trigger** (it kept asking for permission/info instead of calling the tool),
so the `TaskConfirmCard` browser render is still unproven — a *model-capability* gap, not a code gap.
Along the way, five concrete findings (F12–F16), grounded in root cause per this track's rule.

## Findings at a glance (investigate in ALPHABET order of the slug)

| ID | Slug (for al-order) | Severity | Finding (newcomer's words) | Root cause (grounded) |
|----|---------------------|----------|----------------------------|-----------------------|
| **F12** | `agent-registry-down` | 🔴 High | "The Usage meter and slash-commands never load — console is a wall of 504s." | `infra-agent-registry-service-1` is **Exited (255)** (crashed ~6h ago); the BFF proxies `/v1/agent-registry/*` → `agent-registry-service:8099` (down) → 504. |
| **F13** | `failing-tool-call-loop` | 🟠 Med | "The agent spun on `composition_get_mine_job` seven times, all failed, then gave up." | The model calls the job-poller `composition_get_mine_job` (needs `job_id`) with no args → `job_id Field required`; the repeated-call BREAKER counts only *successful* identical reads (by design, to allow arg-fixing retries), so an **identical FAILING call is never blocked** → it loops. |
| **F14** | `agent-refuses-tool-actions` | 🟠 Med | "I said 'create a chapter' and 'delete Chapter 1' and it just asked me questions instead of doing it." | Mix: weak local model + the agent asks permission before `book_list_chapters`/`book_chapter_delete`. Needs investigation: is the co-writer system prompt over-cautioning, or is the tool surface not steering it? (It DID correctly describe the confirm-gate, so the gate wiring is fine.) |
| **F15** | `chapter-create-steals-panel` | 🟡 Low | "I made a chapter and my chat vanished — it jumped me to the Editor." | Creating a chapter (rail empty-state "Start your first chapter") auto-activates the **Editor** dock panel, deselecting the Co-writer Chat tab the user was in. |
| **F16** | `newbook-language-not-required` | 🟡 Low | "I could hit *Create Book* with the language still on 'Select language…'." | New Book dialog enables the submit with `Select language…` selected (no required-field guard on language). Not verified downstream (I picked English), but a book with no original language is a smell. |

---

## ▶ FINAL STATUS (2026-07-20) — all F12–F18 resolved
Investigated **source-first** (bugs may be random/non-reproducible), then fixed the real ones. Since this
session fixed a lot upstream (find_tools hidden, book auto-inject, durable gate), several had already changed:
- **F12** ✅ `07e62f8bf` — restart policy (32 svcs) + FE availability breaker + "unavailable" (see below).
- **F13** ✅ **already fixed** — the **S02 missing-required-args interceptor** (`stream_service.py` ~2860) +
  `blank_tool_args_streak`/`BLANK_TOOL_ARGS_CAP` catches a repeated missing-arg call (incl. `composition_
  get_mine_job` with no `job_id`) BEFORE dispatch, and hard-stops after the cap. Proven live during the
  durable-gate e2e (it fired on `book_chapter_save_draft` missing `body`). The original claim ("breaker counts
  only successful reads") predates this interceptor.
- **F14** ✅ `977e7c71f` — book auto-inject + `LOG_LEVEL` fix + surface monitor.
- **F15** ✅ — chapter-create no longer steals focus from an ACTIVE different panel (the Co-writer Chat):
  `useChapterDoor` reads the active panel; if the editor is already active (or none is) it focuses as before,
  else it loads the chapter + opens the editor as an **inactive** tab (`openPanel focus:false` → dockview
  `inactive`). FE tests + tsc green.
- **F16** ✅ — language is now **required** on New Book (submit disabled + `handleCreate` guard), so no
  language-less book (chapters require `original_language`, inherited from the book). Tests updated + a
  no-language guard test added.
- **F17** ✅ `f30dc77e5` — hide `find_tools`; `tool_list`/`tool_load` the discovery path.
- **F18** ⏸️ **DEFERRED — root-caused, but 2 fix approaches BACKFIRED live (reverted).** The gap is real (the
  consumer-local `tool_list`/`tool_load` dispatch BEFORE the tier-R read breaker, so a repeated identical call
  loops uncaught). BUT two things make a naive fix wrong here:
  1. **F18's ORIGINAL surface — the writing studio — is already fixed by F14.** Book tools are auto-advertised
     there, so the model never tool_list-loops to discover them. The loop only reproduces on the *artificial
     GLOBAL* surface (no book context) that `f17_turn.py` drives.
  2. **Both breaker attempts regressed a weak (Gemma) model, proven live:**
     - *Per-call short-circuit* (return an error on the repeat): the error PROVOKED the weak model to
       batch-retry HARDER — 28 calls → **311** (each cheap, and the useful description still came out, but 10×
       the tool-call events).
     - *+ Budget charge* (count a spin-pass against the write budget to force finalization): forcing the
       tool-free final pass while the model still wanted a tool made it **HALLUCINATE a tool-call as text**
       (`<|tool_call>…current_book_id_placeholder…`) — garbage output. Worse.
  Both reverted. F18 is fundamentally a **weak-model quirk** (a capable model `tool_load`s + acts); the naive
  breakers provoke worse behavior. A non-regressing fix would need to **de-advertise `tool_list` after the cap**
  (so the model MUST use the list it already has) — a larger, riskier surface change — or just accept it as a
  weak-model-only edge case that **F14 already neutralizes on the real surface**. Deferred with that choice for
  the human.

---

## F12 · `agent-registry-down` — the Usage/commands 504 flood 🔴

**Symptom (observed):** on entering the Studio + starting a chat, the browser console filled with
`Failed to load resource: 504 (Gateway Timeout)` for `/v1/agent-registry/usage` and
`/v1/agent-registry/commands?limit=50` (13 errors accumulated over the short session). The Usage
button in the status bar still showed a stale `$0.50`/`$0.63`.

**Root cause (grounded):** `docker ps -a` → `infra-agent-registry-service-1  Exited (255) 6 hours ago`.
Its last log is only `"listening" addr=":8099"` — it came up, then exited 255. The BFF
(`services/api-gateway-bff/src/main.ts:34`) proxies `/v1/agent-registry/*` to
`agent-registry-service:8099`, which is down → 504. This also matches the ai-gateway federation log
`provider 'registry' list-tools failed → TypeError: fetch failed`.

**To investigate:** *why* does agent-registry exit 255 on this stack? (Startup dep, a migration, a
missing env?) Restart-and-watch the crash. Separately: the FE should degrade gracefully — a down
agent-registry should not flood the console; usage/commands should show an unobtrusive "unavailable".

**RESOLVED (2026-07-20) — the "why 255" hypothesis was WRONG; evidence corrected it.**
`docker inspect` showed **18h uptime** (StartedAt 07-19 07:05 → FinishedAt 07-20 01:32), **Exit=255,
OOM=false, no docker Error, and NO application log at exit** (only the startup "listening"). So it did
NOT crash on a startup dep/migration/env — it ran fine for 18h and was **terminated by a host/daemon
lifecycle event** (Exit 255 + no log + no OOM on Windows/Docker Desktop is the classic signature).
Restart-and-watch confirmed it: `docker compose up -d agent-registry-service` → **healthy in 6s**, same
"listening" log, no error. Not a code bug.

**Why it STAYED down:** every service in the compose had `restart: no` (16 had a policy, 32 — including
agent-registry, auth, book, chat, ai-gateway, glossary, api-gateway-bff, postgres, redis, rabbitmq —
had none). Nothing brought it back for ~9h.

**FE flood, re-measured:** the round-4 "FE doesn't degrade" read was off. `useUsage` + `useSlashCommands`
were ALREADY degrade-safe (single fetch, `catch → empty/undefined`, no retry/poll). The "wall of 504s"
is the **browser's own** network-error logging (not JS-suppressible) + re-fetches on remount/token-churn.
The stale `$0.50` is the **usage-billing** spend meter, a DIFFERENT service — not agent-registry.

**Fix shipped (user chose: restart policy + FE polish, stack-wide):**
- **F12a (infra):** `restart: unless-stopped` added to all 32 long-running services that lacked it (one-shot
  jobs — none here — deliberately excluded). agent-registry recreated so its running container carries the
  policy now (self-heals a future host/daemon kill); the rest pick it up on their next recreate. `compose
  config` validates.
- **F12b (FE):** a shared, **tenancy-safe** availability breaker (`lib/agentRegistryHealth.ts` — caches only
  "registry down until T", a down service is down for everyone, never per-user data). `useUsage` +
  `useSlashCommands` consult it: a failed read trips a 30s back-off so a remount skips the slow 504 path
  instead of re-hammering. `useUsage` now exposes `unavailable`; ExtensionsPage shows an explicit
  "Usage unavailable" (new `quota.unavailable` i18n key across all 18 locales, parity-green) instead of a
  silently-empty panel. Tests: breaker unit test (3) + useSlashCommands breaker test; 7 slash tests green.

---

## F13 · `failing-tool-call-loop` — the model loops on an identical FAILED call 🟠

**Symptom (observed):** twice, the agent's turn contained `composition_get_mine_job` called **7×**
(first turn) and **4×** (second turn), every one marked **failed**, rendered as N identical ⚙ chips
in one collapsible button.

**Root cause (grounded):**
- `composition_get_mine_job` is a real tool — the motif-mining job POLLER
  (`services/composition-service/app/mcp/server.py:4298`), whose `_MotifMineJobArgs` **requires
  `job_id`**. The model calls it with `{}` → `pydantic: job_id Field required`. (Confirmed by a direct
  `/mcp` call.)
- The repeated-tool-call breaker in `chat-service` (`stream_service.py`, the read-fingerprint ledger,
  ~L3134) **only counts SUCCESSFUL identical reads** — a deliberate choice ("a call that FAILED has not
  put its answer in the context, so retrying it with fixed args is legitimate and must not be
  blocked"). But a model that repeats the **byte-identical failing call** (same name, same empty args,
  same validation error) is never stopped → it burns N turns.

**Candidate fix (for the investigation):** add a *failed-call* breaker keyed on
`(name, args-fingerprint, error-fingerprint)` — after K (2–3) identical failures with no arg change,
short-circuit with a synthesized "you already tried this exact call and it failed the same way; change
the arguments or pick a different tool" tool-result, instead of letting it re-issue. Distinct from the
success-read breaker; must NOT block a *retry with changed args* (the legitimate case the current
design protects).

**Open question:** *why did the model reach for `composition_get_mine_job` at all* for "create/delete a
chapter"? Worth checking whether motif tools are being hot-seeded/advertised too eagerly for a
book-scoped writing turn (a catalog-hygiene angle, cf. F7c).

---

## F14 · `agent-refuses-tool-actions` — ROOT CAUSE FOUND + CORE FIXED (2026-07-20) ✅🟠

**Update (investigation + fix, `977e7c71f`):** diagnosed with a purpose-built monitor, then fixed.

**Monitoring added (this bug class had none):**
- A per-turn INFO log of the ADVERTISED tool NAMES (`stream_service.py`) — the Agent-runtime
  panel only showed COUNTS (`core N · frontend N · activated N`), which can't answer "did the
  agent even SEE the tool it needed?".
- **Fixed a broken logging infra**: `logging.getLogger("app").setLevel(INFO)` was a SILENT NO-OP
  — the "app" logger has no handler, so records fell to `logging.lastResort` (WARNING-level), so
  every `logger.info` (all 47) was dropped and `LOG_LEVEL=INFO` did nothing (`main.py` +
  `docker-compose CHAT_LOG_LEVEL=INFO`). *Every agent-behavior diagnostic depended on this.*

**Root cause (PROVEN, not guessed):** on the book writing studio the advertised surface was
100% glossary/kg/memory/composition/story tools and **not one `book_*` tool** — because the `book`
skill was *curated-pin-only*, so `book` was never a hot domain. Asked to manage chapters, the agent
saw no book tool and grabbed `composition_get_mine_job` (the seed's closest "job" tool) — this ALSO
drives F13's loop.

**Fix:** auto-inject `book` on the book-bound surfaces (studio/editor/book_scoped) —
`resolve_skills_to_inject`. **Verified live via the monitor + browser:** book tools now advertised;
the agent calls `book_list`, finds the book + "1 chapter", and accurately lists every book chapter
tool. Before: zero book tools.

**Residual (→ F13 + F17):** the 4000-tok seed budget (smallest-schema-first) still truncates
`book_list_chapters` + `book_chapter_delete`, so the agent finds the book but can't list its
chapters directly. The proper close is **F17 (remove `find_tools`, use `tool_list`/`tool_load`)** +
possibly a per-surface primary-domain seed priority.

## F17 · `remove-find-tools-semantic-discovery` 🟠 (user-directed, XL cross-service)

**User directive (2026-07-20):** *"find_tools is deprecated and should be hidden from the LLM —
it is semantic search that only returns top-K, so it can't surface the tool the agent needs; only
`tool_list` + `tool_load` solve that."* Confirmed by F14's dogfood: the weak model never reached
`book_list_chapters` (semantic find can't reliably surface it; the model also just re-called
`book_list`).

**Scope (why it's its own track, not a quick edit):** `find_tools` is wired across BOTH services —
chat-service (`ALWAYS_ON_CORE_NAMES`, the discovery loop, `agent_surface`, and the co_write/glossary/
plan_forge **skill prose** that names it) and ai-gateway (`find-tools.ts`, `catalog.ts`,
`federation.service.ts`, `handlers.ts`) — plus **34 test files**. "Hide from the LLM" (drop it from
the advertised core + the gateway's consumer-local set, keep `tool_list`/`tool_load` as the discovery
mechanism, update the skill prose + tests) is the minimal correct cut; a full deletion is larger.
XL — plan before BUILD.

**RESOLVED (2026-07-20).** Done exactly as the minimal cut above; `find_tools` is hidden from the LLM
on BOTH services, handler kept dispatchable for a legacy caller.
- **chat-service:** `FIND_TOOLS_NAME` dropped from `ALWAYS_ON_CORE_NAMES`; skill prose (co_write /
  glossary / plan_forge / universal / workflow / skill_registry) now steers to `tool_list`/`tool_load`;
  `tool_list` description no longer cross-references find_tools (they're now explicitly distinguished:
  `tool_list` = complete/deterministic discovery path, `find_tools` = legacy/optional/semantic).
- **ai-gateway:** `FIND_TOOLS_TOOL` dropped from `handleListTools`; unknown-tool hint points at
  `tool_list`→`tool_load`; `tool_list` description de-cross-referenced.
- **Tests:** chat 285 pass / ai-gateway 255 pass (handler-dispatch + `find_tools_result` unit tests kept).
- **Monitor gap closed** (the F14 monitor logged core only as a COUNT, so it could not show whether a
  *core* tool like find_tools was advertised): `stream_service` now logs core tool NAMES too.
- **Hygiene (commit `4d53ac78f`):** a stray raw NUL byte in `find-tools.ts` (the FindToolsAttemptTracker
  cache-key delimiter) made git treat the file as binary → broke grep + blocked eol=lf. Replaced with
  the `\x00` escape (runtime-identical) + renormalized CRLF→LF.

**VERIFIED LIVE (deployed stack, model-independent + effect):**
- **Gateway `/mcp` tools/list:** 274 tools, `find_tools` **ABSENT**, `tool_list`+`tool_load` present.
- **Discovery reaches the F14 residual:** `tool_list(category="book")` returns **book_list_chapters +
  book_chapter_delete** (the exact tools the semantic hot-seed truncated); `tool_load(book_list_chapters)`
  returns a callable schema.
- **chat-service monitor (real turn):** advertised `core=['tool_list','tool_load','ui_navigate',
  'ui_open_book','ui_show_panel','ui_watch_job','propose_record_edit','confirm_action','web_search']` —
  find_tools appears NOWHERE in the advertised surface. The local Gemma model **used
  `tool_list(category="book")`** to discover book tools — the F17 path in action.

**New finding surfaced during F17 verify → see F18 below.**

---

## F14 (original entry) · `agent-refuses-tool-actions` 🟠

**Symptom (observed):** "Create a first chapter titled 'The Silent Gods'…" → the agent replied *"I
cannot create a chapter for you yet because I don't have any information about your book"* and asked
for genre/conflict/protagonist. "Delete 'Chapter 1'… call the book_chapter_delete tool." → *"I cannot
delete… I don't have a list of the chapters… Shall I list the chapters now?"* — it never called
`book_list_chapters` or `book_chapter_delete` itself.

**Root cause (partial — needs investigation):** partly the weak local model (Gemma-4 26B is a poor
tool-caller — see also F13). But it may also be steered by the co-writer system prompt to
converse-first / ask-permission rather than act. **The gate itself is fine** — the agent *correctly
described* the propose→confirm-card flow, so the tool descriptions + the durable-gate wiring read
through. Investigation: (a) re-run with a stronger chat model to isolate model-vs-prompt; (b) check
whether the system prompt over-emphasizes "ask before acting" for direct tool requests.

---

## F15 · `chapter-create-steals-panel` — creating a chapter deselects the chat 🟡

**Symptom (observed):** with the Co-writer Chat tab active, clicking the Manuscript rail's *"＋ Start
your first chapter"* created Chapter 1 **and switched the active dock panel to the Editor**, hiding the
chat mid-conversation. Had to click the Co-writer Chat tab to get back.

**Root cause (to confirm):** the create-chapter action opens/activates the Editor panel
unconditionally. Reasonable to *open* the editor, but it shouldn't *steal focus* from an active chat —
open the editor in a split/adjacent tab, or only auto-focus it when no other panel is active.

---

## F16 · `newbook-language-not-required` — submit enabled with no language 🟡

**Symptom (observed):** in the New Book dialog, after typing only a **Title**, *"Create Book"* became
enabled while **Original language** still read *"Select language…"*. (I selected English, so I did not
observe the downstream effect of creating a language-less book.)

**Root cause (to confirm):** the create-book form's enable/validation guards on title but not on
language. Either make language required (it defaults the manuscript/translation language) or default it
to a sensible value + surface that default. Verify what book-service stores when language is absent.

---

## F18 · `discovery-meta-tool-success-loop` — model re-lists instead of advancing 🟠 (surfaced by F17 verify)

**Symptom (observed):** during the F17 live verify (global chat surface, local **Gemma-4 26B**), asked
to "list the chapters … then tell me which tools you have for managing chapters," the model called
**`tool_list(category="book")` ~28× in one turn, every one `ok=True`**, then finally described the book
tools. Discovery WORKED (it reached the book tools deterministically — the F17 win), but it burned ~28
identical successful calls getting there.

**Root cause (grounded):** the repeated-tool-call breaker (`stream_service.py`, the read-fingerprint
ledger) counts identical **successful reads** to suppress re-reads — but `tool_list`/`tool_load` are
consumer-local **discovery meta-tools**, and the breaker's fingerprint set does not cover them (they are
handled before the domain-tool read path). So a model that re-issues the *byte-identical successful*
`tool_list(category="book")` is never told "you already have this list" → it re-lists.

**Relation to F13:** F13 is the *failed*-call loop (identical `{}` args → validation error, never blocked
because the breaker only counts *successful* reads). F18 is its mirror on the *success* side for the
discovery meta-tools. A single fix could cover both: fingerprint `(name, args)` for `tool_list`/`tool_load`
too and, after K identical repeats (success OR failure) with no state change, inject a synthesized
"you already ran this exact discovery call — `tool_load` a specific tool or act now" tool-result.
Distinct from blocking a *legitimate* re-list after the catalog changed (rare; key on an unchanged
catalog snapshot). **Fold into F13's investigation.**

---

## Not-a-bug / confirmations
- **Durable confirm gate:** wired correctly — the agent describes propose→confirm-card accurately; the
  `book_chapter_delete` tool now routes through the gateway (post `Out=any` federation fix, catalog
  165→264). The only unproven piece is the browser `TaskConfirmCard` render, blocked purely by the
  local model not calling the tool (F14). A stronger model (or a scripted tool-call) would close it.
- **Tools DO load:** the chat context showed **37 tools · 1 skill · 7,983 tok** after the first turn
  (the initial "0 tools" is just the pre-first-message state).
