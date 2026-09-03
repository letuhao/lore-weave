# RT4 — A9 (deprecate everything, rebuild) and A12 (codegen does not grow the prompt)

**Mandate:** falsify, not grade. Assigned assumptions **A9** and **A12** of
[`../DESIGN-HYPOTHESIS.md`](../DESIGN-HYPOTHESIS.md) §1.

**Headline.**

> **A9 — WOUNDS hard, and it trips its own stated falsifier.** A wholesale retirement breaks
> **33 enumerated consumer categories across the frontend + 6 services**, including a **public MCP
> edge with a 170-entry external allowlist, 9 published OAuth scopes and issued third-party keys**
> — the *"dependency that cannot be dark"* A9 names as its own falsifier. Two classes are worse
> than the ones that go red: the **16 studio effect-handler RegExps fail SILENTLY** by construction
> (`effectRegistry.ts:69-71` *filters*; an unmatched pattern raises nothing), and the CD4 ship gate
> built for exactly this case **fails open** — `toolBlocked()` only rejects an explicit
> `executes:false`, and an absent tool is "unknown, not broken"
> (`liveness.go:76-82`). And the control group does not survive: the POC's own root-cause experiment (P14 arms
> C/D/E) is built from the **live** `tools/list`, **no catalog snapshot exists in `contracts/`
> today**, and the P14 arms are **not scripted anywhere in the repo**. After A9, the only arms that
> remain reconstructible (A: one tool; B: schema in the conversation) are precisely the two that
> *agree with the new design*. That is the repo's own recorded lesson
> `a-check-whose-control-and-seed-agree-is-theatre`.
>
> **A12 — SURVIVES the literal claim, but the gate it rests on is aimed at the wrong artifact.**
> Measured here: the group-directory block that R13.6.1 cites at *"~188 tokens live"* is
> **1,570 characters ≈ 392 tokens today** — the spec's own budget figure is stale by ~2×, which is
> itself the evidence that an ungated prompt artifact drifts. And **20,500 tokens** of prompt-
> resident skill prose is *explicitly exempted from generation* by R13.6, so R13.6.1 — which only
> binds *generated* artifacts — cannot see the largest prompt-resident surface in the system.

**New measurements made for this report** (originals, not restatements of the POC):

| measurement | value | how |
|---|---|---|
| distinct tools **ever called by the chat model** | **123** of 315 live catalog → **192 never called** | `loreweave_chat.chat_messages.tool_calls`, 7,447 calls |
| distinct tools that **ever succeeded once** | **90** of 315 → **225 never succeeded** | same |
| tools called ≥5× with **zero** successes | **14** (worst `glossary_propose_entity_edit` 0/101) | same |
| `GROUP_DIRECTORY` prompt block | 14 entries, **1,570 chars ≈ 392 tokens**; 161 of them (41%) in **one** entry (`plan`) | `tool_discovery.py:65-111`, rendered at `:508-511` |
| hand-written skill prose in the prompt path | **~20,500 tokens** across 11 skills | `services/chat-service/app/services/*_skill.py` triple-quoted bodies |
| tools with `executes: false` in the repo's generated ship gate | **0** (203 `true`, 13 `null`) | `contracts/tool-liveness.json` |

---

## 1 · Blast radius — who calls MCP tools besides the chat model

### 1.1 The frontend: 41 distinct tool names in production code, 124 across `frontend/src`

| # | consumer | evidence | failure mode on wholesale retirement |
|---|---|---|---|
| 1 | **Direct MCP invocation from the browser** — the FE has its own MCP client | `frontend/src/mcpBridge.ts:15-26` (`mcpExecute` → `POST /v1/ai/tools/execute`) | runtime 404/`NOT_DISCOVERED` |
| 2 | 6 call sites naming 5 tools | `frontend/src/features/composition/motif/api.ts:224,261,361,454,494`; `.../arcImport/api.ts:56` | Motif mine/adopt, library translate, arc conformance, arc import — **all dead** |
| 3 | **BFF bridge allowlist, a THIRD hardcoded copy** | `services/api-gateway-bff/src/tools/tools.controller.ts:24-31` — 6 names, `:73` rejects anything else | every FE bridge call 403s |
| 4 | Chat confirm-card dispatch keyed on tool name | `frontend/src/features/chat/components/AssistantMessage.tsx:254-259` (`FRONTEND_TOOLS`), `:296`, `:316`, `:364-383`, `:389-398` (hardcodes `tool:'glossary_confirm_action'`) | confirm/diff/propose cards stop rendering — the human approval path |
| 5 | Translation + skill proposal cards | `TranslationReviewCard.tsx:43,63`; `SkillProposalCard.tsx:22,35` | 4 more card types dead |
| 6 | i18n labels namespaced **by tool name** | `ToolCallIndicator.tsx:26-28` → `tools.label.<tool>`; 5 keys × 18 locales = 90 strings | every activity row shows a raw key |
| 7 | UI-tool resolvers (the `ui_*` family) | `features/chat/nav/uiNav.ts:45-51,122-169`; `features/studio/agent/studioUiNav.ts:11,26-41,53-83` | agent-driven navigation dead |
| 8 | Prefix→server routing + FE tool mirror | `features/chat/utils/serverKey.ts:13-23,30-42,50` | activity attribution wrong |
| 9 | Undo strip emits raw tool names into a new agent turn | `features/chat/hooks/useActivityUndo.ts:29-39,50-56,60+` | undo silently unavailable |
| 10 | Agent-mode default tool allowlist | `features/studio/panels/agentMode/useNewRunForm.ts:21` (must subset BE `ALLOWLISTABLE_TOOLS`) | agent runs start with an invalid allowlist |
| 11 | 🔴 **Studio effect registry — 16 tool-name RegExps → GUI refresh** | `features/studio/agent/effectRegistry.ts:36-70`; handlers `arcEffects.ts:28`, `authoringRunEffects.ts:44`, `bookEffects.ts:69,73,75`, `compositionEffects.ts:81,87,90,95`, `flywheelEffects.ts:22`, `glossaryEffects.ts:18,59`, `knowledgeEffects.ts:16,76`, `planEffects.ts:27`, `translationEffects.ts:28`, `worldEffects.ts:19,36` | **SILENT.** `matchEffectHandlers` (`effectRegistry.ts:69-71`) *filters* — an unmatched pattern raises nothing. The GUI simply stops refreshing after agent writes, with no error anywhere |
| 12 | **31 studio panels** declare `mcpTools`/`mcpToolPrefixes` | `features/studio/host/types.ts:27-30`, consumed `panels/useStudioPanel.ts:14`; e.g. `StructureTemplatesPanel.tsx:35-39`, `WorldSetupPanel.tsx:17`, `PassRailPanel.tsx:55` | each panel's agent rack goes empty |
| 13 | Contract + coverage suites that pin the surface | `nav/__tests__/frontendToolContract.test.ts:23-52`; `motif/__tests__/feBridgeAllowlist.test.ts:58-79`; `studio/agent/__tests__/effectCoverage.contract.test.ts:25+` (**75 tool names hardcoded**); `chat/utils/__tests__/serverKey.test.ts` | 4 suites red immediately |
| 14 | Cross-language contract file | `contracts/frontend-tools.contract.json` — 11 tools (`confirm_action`, `glossary_confirm_action`, `glossary_propose_entity_edit`, `propose_edit`, 7 × `ui_*`) | the FE↔BE SoT is void |

Dynamic (would *not* break — they fetch the catalog): `features/extensions/hooks/useToolCatalog.ts`,
`features/chat/hooks/useToolSkillCatalog.ts:20-39`, `useContextRack.ts:53,128-152`.

### 1.2 🔴 The public MCP edge — third-party clients, and this is the "cannot be dark" dependency

A9's own falsifier is *"a dependency that cannot be dark."* Here it is, and it is external:

| # | consumer | evidence |
|---|---|---|
| 15 | **`mcp-public-gateway`** — a full JSON-RPC MCP relay where external agents connect | `services/mcp-public-gateway/src/mcp/public-mcp.controller.ts:38-51`, relay at `:290-291`, `:394`, `:495` |
| 16 | Publicly routed at the BFF, incl. RFC 9728 Protected Resource Metadata | `services/api-gateway-bff/src/gateway-setup.ts:280-291`, `:42` |
| 17 | 🔴 **`TOOL_POLICY` — a hardcoded 170-entry external allowlist** with tier + domain scope per tool. *Verified: 170 entries.* An unlisted federated tool is **denied and logged as drift** (`tool-policy.ts:84-86`) | `services/mcp-public-gateway/src/scope/tool-policy.ts:87+`; Domain union `:30-55`; always-allowed meta `:72-76` |
| 18 | **9 published OAuth scopes** in the third-party vocabulary (`domain:book|glossary|knowledge|translation|composition|lore_enrichment|jobs|settings|catalog`) | `services/auth-service/internal/api/oauth_meta.go:144-146` |
| 19 | **Issued third-party keys with a per-`tools/call` audit row** carrying `tool_name` | `services/auth-service/internal/migrate/migrate.go:221-230`; `internal/api/server.go:117`; approvals `mcp-public-gateway/src/approval/approval-client.ts:32,80` |
| 20 | Public-MCP spend attribution survives into the worker (`mcp_key_id`, `spend_cap_usd`) | `services/worker-ai/app/runner.py:600-612` |

**Scenario.** A third party holds an issued key scoped `domain:book`. A9 lands. Every tool it
calls is now absent from the federated catalog, so `TOOL_POLICY` denies and logs drift on all 170
entries at once. There is no version negotiation and no deprecation window in this path — the
external contract simply stops. This is not "schedule risk"; it is an external API break, and it is
the falsifier A9 wrote for itself.

### 1.3 Server-to-server, federation, seeded workflows, skills

| # | consumer | evidence | note |
|---|---|---|---|
| 21 | ai-gateway federates **10 providers** (+2 admin upstreams) | `infra/docker-compose.yml:1082`; `federation.service.ts:310`, `:355-367` | the fan-out itself |
| 22 | Hardcoded **prefix maps** gating what survives `computeCatalog` | `services/ai-gateway/src/config/config.ts:90-100` (`DEFAULT_PREFIX_MAP`), `:116-135` (`EXTRA_PREFIX_MAP`), `:264-290` (admin upstreams) | §7's *"Phase 1 breaks federation"* risk row |
| 23 | Catalog cache + refresh timer; degradation gating; `/health/federation` 503 | `federation/catalog.ts:23-50`; `federation.service.ts:118-127,172,196-217`; `health/health.controller.ts:19,26,38-40` | a cached federated list means a retirement is not observable until restart |
| 24 | **`GROUP_DIRECTORY` byte-lockstep pair**, hand-synced across 2 languages | `ai-gateway/src/federation/find-tools.ts:27-61` ↔ `chat-service/.../tool_discovery.py:65-111` | prose here *names specific tools* (`plan_compile`, `story_search`, `book_get_chapter`, …) |
| 25 | **12 seeded System workflows, 45 `steps[].tool` refs, 30 distinct tools** *(independently re-counted: 47 `"tool"` keys, 30 distinct)* | `services/agent-registry-service/internal/migrate/migrate.go:497,526,548,569,595,628,648,669,692,721,740,766`; contract comment `:405` | re-seed is `DO UPDATE` — corrected on every deploy |
| 26 | Mode bindings pin workflow `vision-to-book` into `write` mode | `migrate.go:818-825` | the flagship rail |
| 27 | **12 chat-service `SkillDef`s** with `hot_domains` prefix pins (9 domains) + **~99 tool names in skill prose** | `services/chat-service/app/services/skill_registry.py:105-285`; contract `:31-40` enforced by `test_skill_registry.py` | prose naming a tool must have that domain hot |
| 28 | 4 more hardcoded tool-name sets in chat-service (17 names) | `tool_discovery.py:282-318` (`ALWAYS_ON_CORE_NAMES`), `:426-428`, `:442-448`; `tool_surface.py:79-106` (`ALWAYS_HOT_WRITES`) | |
| 29 | `agent-registry` probes **arbitrary user-registered MCP servers** (`tools/list` + prompt-injection scan) | `internal/api/probe.go:112,141,157-162`; `scan.go:86-100` | user-supplied servers are a second catalog A9 does not own |
| 30 | Manifest byte-duplicated into **3 places** | `contracts/tool-liveness.json` + `agent-registry-service/internal/api/tool-liveness.json` + `chat-service/app/services/tool-liveness.json` | |
| 31 | **233 test files / 3,764 tool-name occurrences**; **341 non-test source files** name a manifest tool | densest: `chat-service/tests/test_tool_discovery.py` (245/21), `scripts/eval/tool_liveness/tests/test_pure.py` (202/75), `composition-service/tests/unit/test_mcp_server.py` (167/70), `test_skill_registry.py` (80/52) | |
| 32 | **~15 closed-set / contract suites** assert the exact inventory and fail as a block | `book-service/internal/api/mcp_closed_set_contract_test.go`, `mcp_legacy_visibility_test.go`, `mcp_meta_contract_test.go`; `composition-service/tests/unit/test_mcp_closed_set_contract.py`; `test_mcp_schema_federation_safe.py` ×5 services; `ai-gateway/test/{discovery-covers-everything,catalog,tool-meta-contract}.spec.ts`; `sdks/go/loreweave_mcp/closed_set.go` | |
| 33 | Eval corpora pin names outside the test tree | 16 files under `docs/eval/tool-liveness/`, **1,834** refs | this is the baseline of §3 |

**Negative result, and it is real:** **no** worker, cron, scheduler, outbox relay or job runner
invokes an MCP tool. Sweeps of `worker-ai`, `worker-infra`, `scheduler-service`, `meta-worker`,
`meta-outbox-relay`, `publisher`, `archive-worker`, `retention-worker`, `backup-scheduler`,
`canary-controller`, `game-server`, `roleplay-service`, `campaign-service`, `learning-service`
found zero call sites (only two incidental string mentions: `worker-ai/app/distiller.py:88`,
`runner.py:606`). **The queued/scheduled lane is genuinely safe under A9** — that is a point in
A9's favour and it should be recorded as one.

### 1.4 🔴 The guard built for exactly this scenario FAILS OPEN

`liveness.go` is the CD4 ship gate: *"A curated workflow MUST NOT reference a tool that has not
passed G1–G4."* It is the one mechanism that ought to catch a workflow pointing at a retired tool.

**Read the predicate** (`services/agent-registry-service/internal/api/liveness.go:76-82`):

```go
// toolBlocked reports whether the tool is PROVEN BROKEN (executes == false). Only an
// explicit false blocks; an absent tool or a null `executes` is unknown, not broken.
func toolBlocked(tool string) bool {
	t, ok := liveness.Tools[tool]
	return ok && t.Executes != nil && !*t.Executes
}
```

**A deleted tool is ABSENT, and absent is not blocked.** `toolUnchecked` (`:87-90`) catches it and
emits a *warning string* (`livenessWarnings`, `:99-127`) — never a rejection. And
`contracts/tool-liveness.json` today carries **zero** tools with `executes: false` (measured: 203
`true`, 13 `null`, **0 `false`**), so `toolBlocked` has never returned `true` for anything.

**Consequence for A9.** Retire the catalog and all 12 seeded workflows keep seeding, still naming
30 tools that no longer exist, emitting `unproven_tool: …` warnings into a log. The gate designed
to notice exactly this cannot notice it. *(This corrects a plausible-sounding reading that the gate
would hard-fail the migration — it would not, and the fail-open is the worse outcome: A9 would
appear to land cleanly.)*

**Cheapest observation.** Delete one tool name from `contracts/tool-liveness.json`, re-run the
agent-registry workflow validation, and confirm it returns a warning rather than an error. One
command; settles whether the retirement has any mechanical guard at all.

---

## 2 · In-flight work on this branch

`feat/frontend-tools-mcp-migration`, **352 commits ahead of `main`**, 2,730 files changed.

- The frontend-tools MCP migration itself **already merged** as `298bd72a9` / PR #166. The branch's
  own recent 19 commits are the docs for *this* spec.
- **`docs/sessions/SESSION_HANDOFF.md:5941-6055`** records the migration's phase board.
  P2.1/P2.2/P2.3, P3.1–P3.4 are DONE and **live-proven end-to-end in a browser**
  (`fdc4c160f`: a real turn → `ui_navigate` → chat-service → ai-gateway → the browser navigated).
  **`P2.4` is explicitly REMAINING** — the propose-edit editor E2E ("verify by effect").
- Two coexistence windows are open by design and are keyed to tool names:
  - `D-P3-RETIRE-UI-SUSPEND` — the FE keeps the *legacy pending-suspend* path alongside the new
    directive path, to be retired in P4.
  - `propose_edit` P2.2 reconstructs the *byte-identical* suspend shape so the existing FE card
    works unchanged.
- Working tree is dirty in the chat/glossary/composition tool surfaces
  (`services/chat-service/app/services/tool_surface.py`, `tests/test_skill_registry.py`,
  `services/glossary-service/internal/api/*`).

**What A9 does to it.** The migration's whole value is that the *frontend* tools became *MCP*
tools. Retiring all MCP tools retires the migration's output, discards the two open coexistence
windows *before* the P4 retirement that was designed to close them safely, and voids the live E2E
evidence — the only end-to-end proof this branch has. A9 does not merely pause this work; it makes
the last three weeks' deliverable unshippable and its verification unrepeatable.

**Scenario (concrete).** A9 lands; `propose_edit` is not re-admitted in the first tranche.
`AssistantMessage.tsx:364-383` never routes to `ProposeEditCard`, the P2.4 E2E can never be run,
and `D-P3-RETIRE-UI-SUSPEND` becomes undecidable — the legacy path it was going to be measured
against no longer exists.

---

## 3 · The baseline — A9 destroys the control group

This is the strongest attack on A9, and it is the falsifier the hypothesis doc already names
(*"the loss of the baseline we need to prove the new shape is better"*). It is not hypothetical.

### 3.1 What the design will be judged against

The POC's root-cause result — the one thing in this spec that is 🟢 rather than 🔴 — is **P14**
(`poc/P1-P2-findings.md:851-905`): five arms, single variable.

| arm | tool set | source of the tool set | survives A9? |
|---|---|---|---|
| A | 1 tool (`book_list`) | hand-built | ✅ |
| B | schema delivered in the conversation | hand-built | ✅ |
| **C** | **all 35 `book_*`, 19 of them retired, 7,921 tok** | **live catalog** | ❌ |
| **D** | 16 current-only, 4,661 tok | **live catalog** | ❌ |
| **E** | **the 7 the token budget left** | **live catalog + the live budget** | ❌ |

**The two arms that survive A9 are exactly the two that look like the proposed design.** The three
that would falsify it (C proves 35 tools is *fine*; D isolates retirement; E is the whole result)
all require the catalog A9 deletes.

### 3.2 There is no snapshot, and the experiment is not scripted

- **Reproduction depends on the live stack.** `poc/P1-P2-findings.md:1060-1075` — P1 is
  `curl POST http://localhost:8218/mcp … tools/list`. That is a *live* read, not a fixture.
- **No catalog snapshot exists.** `contracts/` holds `tool-liveness.json` (223 names + booleans,
  **no schemas**) and `frontend-tools.contract.json` (11 tools). There is no full
  name+description+schema snapshot anywhere. R1's generated manifest and R13.2's
  *"CI reds on live-catalog ≠ snapshot"* are **Phase 1 / Phase 1b** — i.e. they do not exist yet.
- **P14 is not committed.** `docs/specs/2026-08-03-agent-runtime-unification/poc/` contains exactly
  one file: `P1-P2-findings.md`. No driver, no arm definitions, no seed.

**Consequence.** If A9 runs before Phase 1b, the 7,921-token arm-C payload and the 7-tool arm-E
payload can never be rebuilt. The measured root cause becomes an anecdote.

### 3.3 What *does* survive, and why it is not enough

`loreweave_chat.chat_messages.tool_calls` is a Postgres table — 7,447 calls / 549 sessions survive
any code deletion. But it is a **historical** baseline in the old vocabulary. After A9 the new
surface has no `entity_id`/`book_id` arguments *by construction* (A3), so the headline metric
("57% of errors are identifier-resolution") is **definitionally zero** on the new surface. The
comparison is won before it is run. This is the same defect the hypothesis doc flags for A3
(*"the failure becomes unobservable"*), arriving through the measurement rather than the code.

Also relevant: A10 already records context telemetry at **35% of messages and nothing before
July 2026**, and a freshly driven turn wrote none. The baseline is thin *before* anything is
deleted.

### 3.4 Cheapest observation that settles it

**Snapshot the catalog and script P14 — before any retirement.** One CI job:
`tools/list` → `contracts/tool-catalog.snapshot.json` (name + description + inputSchema + `_meta`),
plus `poc/p14_arms.py` that builds arms A–E *from the snapshot* rather than from the live gateway.
Then re-run P14 against the snapshot and confirm the 3/3 vs 0/3 split reproduces. If it does, A9's
schedule risk is bought off for a day's work. If it does not, the root-cause finding was never
reproducible and **A1 is in trouble independently of A9**.

---

## 4 · The dogfood book

**A9's counter-evidence is one day old.** `docs/sessions/SESSION_HANDOFF.md:5-27` — on
**2026-08-03**, the day the spec was written, a novel (*Mị Đế*) was **planned and drafted through
the real frontend**: propose(llm) → compile → validate → bootstrap → Pass Rail 6/7 with two human
checkpoints → **35 linked scenes → three level-4 chapters drafted**, $0.15 on a local model. The
prose is in the book. `SESSION_HANDOFF.md:599` records the book state: **15 chapters / 4 published
/ a knowledge project that shares the composition project id**; `:636` notes the 15 written
chapters are still unextracted.

The repo has a standing constraint that makes the risk explicit — `SESSION_HANDOFF.md:902-904`:

> **A content-CREATING live smoke uses a THROWAWAY book (`[eval-throwaway] …`), never the dogfood
> book. Smoke debris in a real book reads as a product bug later.**

**Scenario.** A9 re-admits tools "one at a time under the stricter definition." Re-admission has to
be *verified*, and the repo's own verification standard is G4 EFFECT — an independent DB read-back
(`scripts/eval/tool_liveness/README.md`). For ~200 tools that means ~200 effect-verifications. The
throwaway-book rule says none of them may touch the dogfood book — so the dogfood book is frozen
for the duration of the rebuild, or the rule is broken. Meanwhile the book's *own* half-finished
state (11 compiled chapters, 15 unextracted) sits behind tools that no longer exist. There is no
"dark" mode for a book someone is writing.

**Cheapest observation.** Ask for the re-admission order and check whether the tools the dogfood
book's current state depends on (`plan_compile`, `composition_write_prose`, the Pass Rail's tools,
`composition_glossary_build`) are in tranche 1. If they are, "clean floor" is not clean — it is the
current floor re-laid in the same order, which is migration-in-place with extra steps.

---

## 5 · Steel-manning A9 — the evidence FOR a clean floor, measured

A9 deserves better than the counter-evidence, and the numbers are genuinely strong.

| claim | measured | source |
|---|---|---|
| the catalog is mostly retired | **114 of 316 retired (36%)**; **61 of those name no replacement** | `python scripts/deprecated-tool-scan.py --list` |
| retired tools are served forever | **114 legacy tools served**, `visibility:"legacy"` read at **7 filter sites** with no policy layer, `pinned_legacy_tools` as a per-session escape hatch | `SESSION_HANDOFF.md:48-52` |
| 60% of the catalog is unusable by construction | **189 of 315** require an id-shaped arg that names no producer (R17/G3) | `poc/P1-P2-findings.md:438-452` |
| 🔴 **the chat model has never called 61% of it** | **123 distinct tools ever called** of 315 → **192 never called** | measured here (§0) |
| 🔴 **71% has never once succeeded** | **90 distinct tools ever succeeded** → **225 never succeeded** | measured here |
| tools that fail 100% of the time | **14 with ≥5 attempts and 0 successes**, worst `glossary_propose_entity_edit` **0/101** | measured here |
| the existing ship gate cannot see any of it | `contracts/tool-liveness.json`: **0 tools marked `executes:false`**, 203 `true` | measured here |

That last row is A9's real argument and it lands: **the repo's own generated liveness manifest
reports a healthy catalog while 71% of it has never worked in production.** A synthetic probe that
supplies correct arguments cannot detect a tool whose only failure mode is that a model cannot
obtain those arguments. The confound A9 names is real and it is measured.

### 5.1 …and this is also the cheapest refutation of A9

**The same measurement identifies the noise without deleting the signal.** 192 tools have never
been called by the chat model; 114 are already retired. A *data-driven* retirement — retire the
never-called set, keep the 123 that are live — removes essentially the same noise, is reversible,
and keeps every consumer in §1 working and every arm of P14 reconstructible.

**One honest caveat, and it cuts A9's way too.** `chat_messages.tool_calls` sees **only the chat
lane**. The FE bridge (§1.1 #1–3), server-to-server calls, and job runners never write there — so
"never called" means "never called *by the chat model*". Two of the six BFF-allowlisted FE tools
(`composition_conformance_run` 0/31, `composition_get_mine_job` 0/21) appear in the chat history
with zero successes yet are load-bearing for a shipped FE feature.

**That is itself a finding against A9's method.** A "clean floor, re-admit one at a time" policy
needs a *deadness predicate*, and the only usage telemetry the repo has covers one of at least
three call paths. Re-admitting by chat-lane evidence alone would silently drop the FE-bridge and
job-driven tools. **R9.6's usage counters (Phase 4) are the prerequisite for A9, and A9 is
scheduled before them.**

**One more point genuinely in A9's favour** (§1.3 negative result): the entire scheduled/queued
lane — 14 workers, cron and outbox services — invokes **zero** MCP tools. A9's blast radius is
narrower than the phrase "deprecate everything" suggests: it is the chat lane, the FE, and the
public edge, not the async spine.

### 5.2 The verdict on A9

**WOUNDS as a mechanism; KILLS as a big bang.** The hypothesis doc classifies A9 as "schedule and
product risk, not design correctness" — that classification is too generous by one item. The public
MCP edge (§1.2) is an **external contract with issued credentials**, and the doc's own falsifier is
*"a dependency that cannot be dark."* That falsifier is met, on the evidence, today.

Beyond it, A9 is wounded in a way that changes the *order of the plan*:

1. A9 cannot precede R1's manifest + a catalog snapshot, or the control group dies (§3).
2. A9 cannot precede R9.6's usage counters, or the deadness predicate is one-lane-blind (§5.1).
3. A9 cannot precede P2.4, or this branch's deliverable is stranded (§2).
4. A9's only mechanical guard (`liveness.go`) fails open on deletion (§1.4), so a wholesale
   retirement would *look* clean while 12 rails point at nothing.

Since (1) is Phase 1/1b, (2) is Phase 4 and (3) is now, **A9 is not a first move under any reading
of its own spec's phase order** — and once it is sequenced after Phases 1–4, the accumulated
manifest + counters + snapshot make a *surgical* retirement strictly cheaper than a wholesale one.
A9's mechanism survives; A9 as a **big bang** does not.

---

## 6 · A12 — codegen does not grow the prompt

**Claim.** *"An EF-style generated manifest and migration chain add build-time cost only."*
**Falsifier.** *"Any generated artifact that reaches a prompt and is more verbose than the
hand-written prose it replaced."*

### 6.1 Every place a generated artifact could enter a prompt

| # | prompt-resident artifact | where | size today | generated under this spec? |
|---|---|---|---|---|
| 1 | **group directory block** | authored `tool_discovery.py:65-111`; **rendered into the prompt** at `:508-511` (`"Tool domains (call tool_list with category=…)"`) | **1,570 chars ≈ 392 tok** | ✅ R13.6 lists "the group tree" as generated; R14.2 makes `group` a **path** |
| 2 | tool descriptions + schemas | the 315 live tools | **413 tok/tool**, ~130k total (`poc:41`) | partly — R17/G3 mandates new text per argument |
| 3 | skill bodies | 11 files, triple-quoted prose | **~20,500 tok** | ❌ **explicitly not generated** (R13.6: *"Prompt prose: not generated at all"*) |
| 4 | rail / workflow step text | agent-registry seeds | — | ❌ per R13.6 |
| 5 | `tool_list`/`tool_load` result payloads | `find-tools.ts:744` returns `{...GROUP_DIRECTORY}` | rides #1 | ✅ |
| 6 | R10 error-contract text (`terminal_permanent` "what to do instead") | to be written at every raise site | new | ambiguous — see §6.3 |

### 6.2 The measurement that matters — and it contradicts the spec's own figure

R13.6.1 justifies itself with *"the repo already measures (the group directory at ~188 tokens
live…)"*. **Measured today: 392 tokens** — 14 entries, 1,570 characters. The block is ~2× the
figure the spec quotes.

More telling: **161 of those 392 tokens (41%) are in a single entry, `plan`**, and that entry is
not a description at all — it is a hand-written sequencing instruction:

> `"Novel planning workflow — PlanForge. THE SEQUENCE MATTERS: plan_propose_spec drafts a spec, but
> a proposal ALONE creates NOTHING the book can use… you MUST finish by calling plan_compile…"`
> — `tool_discovery.py:100-110`

**This is the concrete A12 falsification scenario.** R14.2 makes `group` a path and `tool_list`
return *children, not leaves*. A generated group tree therefore has more nodes than 14 (315 tools
over a 2-level tree is plausibly ~50–60 selectable nodes), and every node needs a description to be
selectable at all. At the current mean of **~28 tokens per non-`plan` entry**, a 55-node generated
tree is **≈1,540 tokens — ~4× today's block** — and that is *before* C1's projected thousands of
tools. Meanwhile the `plan` entry's sequencing prose is exactly the thing a generator cannot emit,
so it must either be dropped (losing guidance that was added deliberately) or relocated into skill
prose (net-zero at best, and now duplicated).

**Cheapest observation that settles A12.** Generate the group tree from the live catalog **today**,
render it through `format_group_directory()` (`tool_discovery.py:508-511`), and count the tokens
against 392. One afternoon, no refactor. If the generated tree is larger — and the arithmetic says
it will be by ~4× — A12 is falsified at its own falsifier, in the exact artifact R13.6 names as
generated.

### 6.3 The gate is real and enforceable — but it is pointed away from the risk

**Enforceability: YES, and there is precedent.** These already run in CI on every PR:

| gate | wired at |
|---|---|
| `scripts/context-budget-l3-lint.py` | `.github/workflows/foundation-ci.yml:174` |
| `scripts/context-budget-defaults-lint.py` | `foundation-ci.yml:184` |
| `scripts/tier-tag-gate.py` | `foundation-ci.yml:191`, `lint-foundation.yml:95` |
| `scripts/deprecated-tool-scan.py` | `foundation-ci.yml:222` |

`context-budget-defaults-lint.py` is the right template — it has a `LIMIT_CEIL`, an `ALLOW` map with
per-row reasons, a documented FLIP-PENDING drain, and it is currently at `ALLOW = {}` (the K37 drain
completed). R13.6.1 can be built exactly like it. **So A12's *mechanism* is not the weak point.**

**Scoping: NO.** R13.6.1 binds *"every generated artifact that enters a prompt"*. But R13.6 draws
the line precisely so that the biggest prompt-resident artifacts are **not generated**:

- **20,500 tokens of skill prose** — hand-written by rule. The gate never sees it.
- **R17/G3's mandated new text** — *"the remedy is one sentence per argument"*
  (`poc/P1-P2-findings.md:459-463`), applied to **189 tools**. That sentence is hand-written prose
  on a tool description, so it is out of R13.6.1's scope, and it is paid on every turn for every
  advertised tool. At ~15 tokens/sentence over the tools actually on the wire this is a real,
  permanent per-turn addition that **no gate in this spec watches**.
- **R10's `terminal_permanent` "what to do instead" strings** — same shape, same blind spot.

### 6.4 The verdict on A12

**SURVIVES as literally stated; the risk it was written to control ESCAPES it.**

The claim *"codegen does not grow the prompt"* can be kept true by fiat (R13.6 forbids generating
prose) while the spec still produces a permanent per-turn cost regression through hand-written prose
that R13.6.1 does not bind. And the one prompt artifact R13.6 *does* commit to generating — the
group tree — is the one the arithmetic says grows ~4×.

**The fix is a one-line scope change, and it should be made before the phase plan is signed:**
R13.6.1 must bind **every artifact that enters a prompt**, generated or not, with a recorded
baseline per artifact (group block 392 tok, skill prose 20,500 tok, per-tool description budget) and
a ratchet that may only shrink. Written as *"generated artifacts only"* it is a gate that cannot
fail, which is the vacuity shape §9 of the spec already enumerates ("the scope never reaches it").

---

## 7 · Findings summary

| id | assumption | verdict | scenario in one sentence | cheapest observation |
|---|---|---|---|---|
| RT4-0 | **A9** | 🔴 **KILLS as a big bang** | The public MCP edge has a 170-entry `TOOL_POLICY`, 9 published OAuth scopes and issued third-party keys with per-call audit — retiring the catalog denies all 170 at once with no deprecation window; this is A9's own named falsifier ("a dependency that cannot be dark") | count `TOOL_POLICY` entries (`tool-policy.ts:87+` — verified 170) and list issued keys in `auth-service` |
| RT4-1 | **A9** | **WOUNDS** | 33 consumer categories across FE + 6 services break, and the 16 studio effect RegExps break *silently* — the GUI stops refreshing with no error | rename one tool and watch `matchEffectHandlers` (`effectRegistry.ts:69-71`) return `[]` with no throw |
| RT4-1b | **A9** | **WOUNDS** | The CD4 ship gate fails open: `toolBlocked()` rejects only an explicit `executes:false` (of which there are **zero**), so 12 seeded workflows keep seeding against 30 non-existent tools and only warn | delete one name from `contracts/tool-liveness.json`, re-run workflow validation, observe a warning not an error |
| RT4-2 | **A9** | **WOUNDS (control group)** | P14 arms C/D/E are built from the live `tools/list`, no catalog snapshot exists in `contracts/`, and P14 is not scripted — only the two arms that agree with the design survive | snapshot `tools/list` to `contracts/` and script P14 arms A–E *before* any retirement |
| RT4-3 | **A9** | **WOUNDS (in-flight)** | P2.4 (propose-edit E2E) is open and two coexistence windows are keyed to tool names; A9 voids the only end-to-end evidence this branch has | run P2.4 now, or record it as knowingly abandoned |
| RT4-4 | **A9** | **WOUNDS (dogfood)** | The Mị Đế book was planned + drafted through the real FE on 2026-08-03; the throwaway-book rule means ~200 re-admission effect-checks cannot touch it, so it freezes | ask for the tranche-1 list; if it contains `plan_compile`/`composition_write_prose`, the clean floor is migration-in-place |
| RT4-5 | **A9 (steel-man)** | **REAL** | 192/315 never called, 225/315 never succeeded, 14 tools at 0%, while `tool-liveness.json` marks **zero** tools broken — the confound A9 names is measured | already measured; re-run the SQL in §0 |
| RT4-6 | **A9 (method)** | **WOUNDS** | The only usage telemetry covers the chat lane; the FE bridge and job runners never write to it, so a "never called ⇒ dead" predicate silently drops shipped FE tools | check `composition_conformance_run` (0/31 in chat) against `tools.controller.ts:24-31` |
| RT4-7 | **A12** | **SURVIVES (literally)** | The claim is kept true by forbidding prose generation — and 20,500 tok of skill prose plus R17/G3's 189 mandated sentences are therefore outside the gate | re-scope R13.6.1 to *all* prompt artifacts with a per-artifact ratchet |
| RT4-8 | **A12** | **WOUNDS** | The one prompt artifact R13.6 does generate — the group tree — goes from 14 nodes to ~55 under R14.2, ≈392 → ≈1,540 tokens | generate the tree today, render via `tool_discovery.py:508-511`, count against 392 |
| RT4-9 | **A12 (calibration)** | **WOUNDS** | R13.6.1 cites the group block at "~188 tokens live"; it is **392** — the budget figure is already stale by 2×, which is the evidence that an ungated prompt artifact drifts | `python -c` over `GROUP_DIRECTORY` — done in §0 |

### The rival shape (mandate §3, explicitly in scope)

A far cheaper package captures most of A9's value with none of its risk:

1. **Retire by data, not by decree** — drop the 192 never-called tools *after* R9.6 counters cover
   all three call lanes. Reversible; every consumer in §1 keeps working.
2. **Fix the silent budget** (P14's actual root cause) — `excluded_by` + R5's "guards register what
   they withhold". One mechanism, backed by the only 🟢 experiment in the spec.
3. **Ship R17/G3** — one sentence naming the producer for each required id arg. `poc:465` already
   calls it *"the cheapest"* and it sits at the head of the six-symptom chain.

None of these three needs a clean floor, and all three are measurable against a baseline that still
exists.

---

*RT4 · red team 4 of the agent-runtime-unification review · measurements taken 2026-08-04 against
the running stack (`infra-postgres-1`) and HEAD `3f7acb6a9`.*
