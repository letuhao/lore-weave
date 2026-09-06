# Spec — Retire architecture v1 (the chat-service frontend-tool construct)

Reconciles: Frontend-Tool Contract · Agent GUI Reconciliation (09) · Chat-agent ↔ MCP wiring — the spec for the retirement; it relocates the enforcement point those three rows describe and renames the contract file one of them cites, and defines nothing new.

> **FINAL REPORT (2026-09-03):** [`docs/plans/2026-09-03-retire-v1-FINAL-REPORT.md`](../plans/2026-09-03-retire-v1-FINAL-REPORT.md) — verdict `v1 IS DEAD`, every DQ-V6 decision, and what is deliberately not done.

- **Date:** 2026-09-03
- **Status:** 🔒 **SEALED 2026-09-03** — all five decisions ratified by the owner (§7). No code yet.

  | id | ruling |
  |---|---|
  | DQ-V1 | **Retain** all three names in `frontend-tools.contract.json`; rename the contract to reflect FE card-rendering ownership (owner default, not overruled) |
  | DQ-V2 | **Adopt** the tasks gate in translation-service — no exemption |
  | DQ-V3 | `tool_load` **refuses** a legacy tool and names its successor; **`pinned_legacy` is KEPT** as an explicit user escape hatch. D5 therefore reads *unreachable by the model **unaided*** |
  | DQ-V4 | The synthesised batch-cap card is **re-homed as `batch_confirm`** in the same slice that moves the tool |
  | DQ-V5 | **Split:** `confirm_action` + `glossary_confirm_action` → glossary-service MCP tools; `glossary_propose_entity_edit` → ai-gateway directive tool mirroring `propose_edit` |
- **Predecessor:** [`2026-07-19-frontend-tools-mcp-migration.md`](2026-07-19-frontend-tools-mcp-migration.md)
  (SEALED). Its S1/S3/S4 landed 2026-07-20; **S2 and S5 did not**. This spec completes them and adds
  the two things that spec did not cover: the *deprecated-tool* cohort and the *documentation* rot.
- **Trigger:** the 2026-09-03 runstate audit. Not a symptom this time — a deliberate sweep.
- **Size:** L — cross-service (chat-service · 4 domain services · 2 frontends · docs), phased.

---

## 0. Why this spec exists at all, given the predecessor

The 2026-07-19 spec was correct and its build board is *honest*: it still marks S2 and S5 `pending`,
and they are. What it could not anticipate is that the intervening six weeks would ship a **second**
gate mechanism (ext-tasks) **beside** v1 rather than over it, leaving two live confirm paths and no
document saying which is current. The audit found the resulting confusion in the load-bearing code
itself — see §6.

So this is not a re-plan of the migration. It is the retirement of what the migration left behind,
plus the de-rot needed so the next agent cannot re-inherit the confusion.

---

## 1. What "architecture v1" IS — the exact footprint

v1 is **three agent-facing tools and the chat-service-local machinery that serves them**. That is the
whole of it. Stated precisely because the audit began from an assumption that v1 covered ~199 tools;
it covers three.

### 1.1 The three tools

`services/chat-service/app/services/frontend_tools.py:47-51` — `FRONTEND_TOOL_NAMES`:

| Tool | Spec KIND | Why it is v1 |
|---|---|---|
| `glossary_propose_entity_edit` | C1 · version PATCH | chat-service-local OpenAI function dict; intercepted, never federated |
| `glossary_confirm_action` | C2 · mint→confirm | ditto |
| `confirm_action` | C2 · mint→confirm | ditto, **and advertised on every turn on every surface** |

`confirm_action` reaches the model because it sits in `ALWAYS_ON_CORE_NAMES`
(`tool_discovery.py:310`) and the advertise loop resolves it as
`catalog_index.get(name) or generic_frontend_tool_def(name)` (`stream_service.py:1905`). It is absent
from the federated catalogue, so the **fallback always fires** and the v1 schema is what the model
sees. Verified against the live federation: 316 tools, `confirm_action` not among them.

### 1.2 The machinery

- `frontend_tools.py` (834 lines) — 22 module symbols; `is_frontend_tool`, `validate_frontend_tool_args`,
  `frontend_tool_defs`, `generic_frontend_tool_def`, `is_browser_executed`, and 6 schema dicts.
- The unguarded intercept at `stream_service.py:7146` (`if is_frontend_tool(c["name"]):`) — no feature
  flag, no context guard.
- The advertisement paths at `stream_service.py:1905`, `:10705`, `:10896`, `:13381`, `:13877`.
- The FE mirror `frontend/src/features/chat/utils/serverKey.ts:31-39` and the admin render gate
  `cms-frontend/src/features/admin-chat/components/MessageList.tsx:28`.
- `contracts/frontend-tools.contract.json` — 11 entries, of which 3 are v1.

### 1.3 The residue of already-migrated tools

`propose_edit` and the 7 `ui_*` tools moved to ai-gateway in 2026-07-20, but their **schema dicts
remain** in `frontend_tools.py` as "an ai-gateway-down advertisement fallback + the P0
validation-seam map", tracked as `D-P3-RETIRE-UI-FRONTEND-DEFS`. `propose_edit`'s copy is still what
is advertised on the editor surface, and the file records that the two copies **had already drifted**
before `TestResidualAdvertisedDescriptionsMatchAiGateway` pinned them. The guard is real — it reads
ai-gateway's TypeScript and parses the literal — but a pinned duplicate is still a duplicate.

---

## 2. What v1 is NOT — four things that must survive

**This section is the most important in the spec.** Each is named because its name or shape invites
deletion, and deleting any of them breaks something that has nothing to do with v1.

### 2.1 KEEP — the `confirm_token` spine and the domain confirm routes

`mint_confirm_token` / `MintConfirmToken` and `POST /v1/<domain>/actions/confirm` are **not v1**. The
gate helper's own docstring names the clients that depend on the fallback
(`sdks/python/loreweave_mcp/tasks_wire.py:160-165`):

> *"Otherwise → return `confirm_fallback()` … so a non-tasks client (chat-service pre-driver, **the
> public edge, external agents**) is NEVER stranded with a task it can't drive."*

chat-service is no longer "pre-driver". The public edge and external agents are permanent. **The
fallback is permanent.** What ends is chat-service's *agent-facing wrapper* around it.

### 2.2 KEEP — the public gateway's `confirm_action`

`services/mcp-public-gateway/src/mcp/public-mcp.controller.ts:171` implements a **different tool with
the same name**: a synthetic edge tool for headless self-confirm, gated on an API key holding both
`write_confirm` and `allow_self_confirm`, not federated and not in `TOOL_POLICY`. It shares no code
with `frontend_tools.py`.

> **A consumer-local tool's NAME can lie about its owner.** A sweep that greps `confirm_action` and
> deletes what it finds will break the public edge. Every removal step in the build plan must name
> its file, never its tool name.

### 2.3 KEEP — `chat_suspended_runs` and `POST /tool-results`

The audit's single most plan-shaping finding. There are **seven** `suspended_call` producers in
`stream_service.py` and **one** writer (`:12457`). Only one producer is v1:

| Line | Producer | v1? |
|---|---|---|
| 7321 | `is_frontend_tool` intercept | **YES** |
| 7807 | Tier-A auto-apply batch cap → synthesises a call named `confirm_action` | no |
| 7863 | `require_approval` hook (`kind="tool_approval"`) | no |
| 8166 | DQ-T76 disambiguation picker | no |
| 8426 | DR-C2 write-mode approval gate | no |
| 8820 | ext-tasks durable gate | no |
| 8840 | `propose_edit` ai-gateway directive, detected in the **result** | no |

The table, `db/suspended_runs.py`, the TTL sweep, and the `/tool-results` endpoint are **shared
infrastructure**. Six of seven survive v1. Deleting the table with v1 removes the durable gate that
*replaces* v1.

### 2.4 KEEP (conditionally) — the synthesised `confirm_action` card

`stream_service.py:7809` builds a pending call literally named `confirm_action` with **no model tool
call involved** — the enforceable injection-damage bound on Tier-A auto-apply. The FE renders it via
the `FRONTEND_TOOLS` array at `AssistantMessage.tsx:256-259`. Dropping `'confirm_action'` from that
array kills the batch-cap card silently. See DQ-V4.

---

## 2.5 KEEP — the three tools THEMSELVES. Only their implementation dies.

**This supersedes the framing the audit started from, and it is the single most important
correction in this spec.** `docs/standards/mcp-tool-io.md:120` (GATE-2) is a sealed rule:

> *"**The `confirm_token` fallback is permanent (spec OQ3).** So `confirm_action` /
> `glossary_confirm_action` are **not retired** — they still render (a) the fallback for non-tasks
> clients, and (b) the tools that legitimately can't be task-shaped: a confirm whose execute path
> needs the token itself (a replay-ledger / usage-billing key), a dual-mode tool whose non-confirm
> branch has a typed output, System-tier admin confirms, and the client-side C1 record-edit
> (`propose_record_edit`, `glossary_propose_entity_edit`) which PATCH from the browser with no
> server executor to gate."*

That names **all three** v1 tools as deliberately non-retirable, with four stated reasons. A plan to
delete them contradicts a sealed standard.

**It does not contradict this spec, because the defect was never that the tools exist.** The defect
is that their schemas are chat-service-local OpenAI function dicts that bypass MCP's validation,
discovery and advertisement. GATE-2 protects the *tools*; it says nothing about *where their schemas
live*. The predecessor spec's S2 said so outright: **"KIND C → native MCP + task-shaped gate."**

> **THE TARGET, restated:** the three tools survive as **real federated MCP tools owned by their
> domain service**. `frontend_tools.py` and the interception path die. "v1 is dead" means *the
> construct* is dead, not *the capability*.

For `confirm_action` and `glossary_confirm_action` this is a straight relocation: glossary-service
already owns the confirm route (`internal/api/action_confirm.go`) and already registers 25 MCP tools.
For `glossary_propose_entity_edit` GATE-2's reason (b) is real — it PATCHes from the browser with no
server executor — which makes it the same shape as `propose_edit`: a **validated directive tool**,
the pattern ai-gateway already implements. See DQ-V5.

---

## 3. The precondition — the tasks gate should be total where it CAN be

`confirm_action` will always exist (§2.5). But it should be reached only where a task genuinely
cannot be, and today it is reached far more widely than that: **14 minting sites never open a task**,
regardless of client capability.

Measured 2026-09-03 by pairing every `mint_confirm_token` / `MintConfirmToken` call site against a
`gate_or_confirm` / `GateOrConfirm` within ±30 lines (8 of composition's 15 mints are the fallback
closure *passed into* the gate and are therefore already gated):

| Service | Ungated | Tools / sites |
|---|---|---|
| composition | 7 | `composition_decompile_arcs`, `composition_motif_adopt`, `composition_motif_mine`, `composition_library_translate`, `composition_arc_import_analyze`, `composition_conformance_run`, `plan_bootstrap_apply` |
| translation | 4 | `translation_start_job`, `translation_retranslate_dirty`, `translation_start_extraction`, `translation_job_control` — **the service has no tasks gate at all** |
| book | 2 | `mcp_actions.go:105`, `:886` |
| provider-registry | 1 | `mcp_server.go:878` |

**Already gated:** composition ×8 (`gate_or_confirm`), book ×2 (`GateOrConfirm` at `mcp_actions.go:345`,
`:387`), glossary via the shared `action_task_gate.go:84`.

> **The bar:** a KIND-C write reachable by chat-service must return a durable task to a tasks-capable
> client. Not "translation-service imports the gate" — the *rate of bare `confirm_token`s reaching
> chat-service must be zero*, measured on the wire, before `confirm_action` is withdrawn.

---

## 4. Definition of done — what "v1 is dead" means, testably

Each clause is a machine-checkable postcondition, not a description. §5 assigns each a gate.

- **D1 — the construct is gone.** `FRONTEND_TOOL_NAMES` is empty or absent; `is_frontend_tool` and
  `validate_frontend_tool_args` do not exist; no module imports `frontend_tools`.
- **D2 — nothing chat-service-local reaches the model.** Every tool in a turn's advertised set
  resolves from the federated catalogue or from a named consumer-local allowlist
  (`tool_list`, `tool_load`, `compose_prose`, `workflow_list`, `workflow_load`).
  `generic_frontend_tool_def` is not a source of advertised schemas.
- **D3 — the declaration's OWNER moves; the declaration survives.**
  `glossary_propose_entity_edit`'s manifest row (`contracts/agent-runtime-manifest.json:90`) reads
  `owning_service: "chat-service"` today. On completion it reads a domain owner
  (glossary-service, or ai-gateway if DQ-V5 chooses the directive shape).
  **This is NOT a `retired` transition.** Retirement was the plan before §2.5; GATE-2 forbids it.
  Because `LIFECYCLE_MOVES` (`app/agentruntime/contract.py:98-103`) has no `admitted → admitted`
  edge and no resurrection, a change of owner is a **new admission against the current contract** —
  the old row goes `admitted → retired` *and* a new row is admitted for the new owner, in that
  order, in one slice. Doing only the first half deletes the capability.
- **D4 — the gate is total where a task is possible, and exempt where it is not.** Every one of the
  14 sites in §3 either opens a durable task, or sits on a named exemption list citing which of
  GATE-2's four classes it falls under. An unexplained bare `confirm_token` is a failure; an
  explained one is the design.
- **D5 — deprecated means dead, to the model UNAIDED.** The 117 `visibility: legacy` tools are not
  advertised, not searchable, and **not loadable by name**: `tool_load` refuses and names the
  successor (today it merely *labels*, `tool_discovery.py:1270`). **`pinned_legacy`
  (`tool_surface.py:957-961`) is KEPT** — an explicit, user-initiated pin is not the model reaching a
  dead tool, and closing it would remove a capability from users to satisfy a slogan (DQ-V3 ruling).
- **D6 — no document describes v1 as current.** No guidance file names `frontend_tools.py` as the
  schema home for a live tool, asserts a hardcoded tool count that disagrees with the SSOT, or points
  a resume marker at finished work.
- **D7 — regression is impossible, not merely unlikely.** A gate fails the build if D1, D2, D3, D5 or
  D6 regresses. A new tool that is chat-service-local and agent-facing cannot merge.

---

## 5. Enforcement — the gates that make D7 true

Without these, this is a cleanup that rots again in six weeks. The audit found three separate
mechanisms that already exist and are not enforced, so each gate below states what it would have
caught.

| Gate | Checks | Would have caught |
|---|---|---|
| **G1 · no-local-agent-tool** | every advertised tool resolves from the federated catalogue or the named allowlist | `confirm_action` advertised from `generic_frontend_tool_def` on every turn since 2026-07 |
| **G2 · manifest-lifecycle** | no `SERVED_LIFECYCLES` row whose `owning_service` is chat-service and whose `kind` is `tool`, outside the allowlist | `glossary_propose_entity_edit` sitting `admitted` |
| **G3 · gate-totality** | every `mint_confirm_token` call site is paired with a `gate_or_confirm`, or is on a named exemption list with a stated reason | all 14 sites in §3 |
| **G4 · doc-count-drift** | every hardcoded "N tools" figure in `docs/` and `AGENTS.md` matches the SSOT, or is marked a dated snapshot | `mcp-tool-io.md`'s 315/198 vs the true 316/199 |
| **G5 · status-contradiction** | a doc whose header says `open`/`pending` while its body contains a completion marker fails | `toolv2-loop-RUNBOOK.md:3` "open" vs `:1531` "THE LOOP IS CLOSED" |
| **G6 · stale-docstring** | a docstring asserting a capability is "dormant"/"not wired" while the symbol has a live caller fails | `task_detect.py`'s two dormancy claims |

G4 and G5 are the de-rot half. They are cheap, and they are what stops §6 recurring.

---

## 6. The rot this creates, and why it is in scope

The audit found the confusion this spec exists to end **inside the code that implements the
replacement gate**. `services/chat-service/app/services/task_detect.py:11-16` states:

> *"It is NOT wired into `mcp_execute_tool` yet and chat-service does **NOT yet declare tasks
> capability**, so on the current stack a task never comes back and this never fires (dormant-safe)."*

and `tasks_capability_meta` at `:76`: *"Until then this is defined but unused (dormant)."*

Both are false. `knowledge_client.py:962` calls `tasks_capability_meta()` under
`tasks_gate_enabled: bool = True` (`config.py:166`). An agent reading `task_detect.py` concludes v2's
gate is off and v1 is the only live path — the exact belief this work exists to remove.

The documentation half of this spec is therefore **not** cosmetic and is not deferrable to the end.
It is scheduled as Slice 0, before any code moves, so that an agent picking the work up mid-way reads
a true description of where it is.

Full de-rot worklist: see the build plan's Slice 0.

---

## 7. Decisions required before sealing (DQ-V1 … DQ-V4)

Each changes the work materially. None can be settled from the code.

### DQ-V1 — Do the three names stay in `contracts/frontend-tools.contract.json`?

Precedent cuts both ways: `propose_edit` and the 7 `ui_*` migrated to ai-gateway and **stayed** in the
contract (11 entries today). If v1's three also stay, the contract stops meaning "chat-service serves
these" and becomes "the FE renders cards for these" — a rename, not a deletion.

**Recommendation:** retain them, and rename the contract to reflect FE card-rendering ownership. The
FE genuinely still needs the names (`AssistantMessage.tsx`, `MessageList.tsx`); deleting them to make
a number smaller is how `serverKey.ts` and the contract drift apart.

### DQ-V2 — Does `translation-service` adopt the tasks gate, or are its 4 tools exempted?

It has no gate at all. Adopting it is real work in a service otherwise untouched by this programme.

**Recommendation:** adopt. An exemption re-creates exactly the dual-path condition being retired, and
`translation_start_job` is one of the few tools with a proven end-to-end store-moving live run.

### DQ-V3 — Does "deprecated is dead" mean *unloadable*?

D5 as written closes `tool_load`'s labelling path and `pinned_legacy`. Both were deliberate: pinning
was built so a user could keep a legacy tool for a session.

**Recommendation:** make `tool_load` refuse a legacy tool and name its successor, but **keep**
`pinned_legacy` as an explicit, user-initiated escape hatch. Closing it removes a capability from
users to satisfy a slogan; a user who pins knows what they pinned. If accepted, D5 becomes
"unreachable by the model *unaided*" and must be reworded to say so.

### DQ-V5 — Where do the three tools land? (NEW — raised by §2.5, and it is the biggest one)

GATE-2 keeps all three tools. They must stop being chat-service-local dicts. Three shapes exist,
and the right answer may differ per tool:

| Shape | Precedent | Fits |
|---|---|---|
| **Domain MCP tool** on glossary-service | its 25 existing tools; it already owns `action_confirm.go` | `confirm_action`, `glossary_confirm_action` — the confirm route is already there |
| **ai-gateway validated directive tool** | `propose_edit` (`propose-edit-tool.ts`), the 7 `ui_*` | `glossary_propose_entity_edit` — GATE-2 reason (b) says it PATCHes from the browser with *no server executor to gate*, which is exactly `propose_edit`'s shape |
| **Stay chat-service-local, but federated properly** | `tool_list`/`tool_load` | fallback only if the other two fail; it does not remove the construct |

**Recommendation:** `confirm_action` + `glossary_confirm_action` → glossary-service MCP tools;
`glossary_propose_entity_edit` → ai-gateway directive tool, mirroring `propose_edit`. That retires
`frontend_tools.py` entirely and leaves one well-trodden pattern per tool, rather than inventing a
third.

**Consequence if deferred:** V6/V7 cannot start. This is the gating decision of the whole plan.

### DQ-V4 — Is the synthesised batch-cap `confirm_action` card re-homed or retired?

`stream_service.py:7807` names a server-generated card `confirm_action`. If the name goes, the card
needs a new one and the FE array plus `cms-frontend`'s render gate move with it.

**Recommendation:** re-home it under a distinct name (e.g. `batch_confirm`) in the same slice that
removes the tool, so the two never share a name again. Leaving it named `confirm_action` after the
tool is gone guarantees a future sweep deletes it.

---

## 8. Explicitly out of scope

- The 117 legacy tools' **implementations**. D5 is about reachability, not deletion. They are a
  record, and deleting them is a separate, larger decision.
- `SP-0c` (the ai-gateway TS SDK 2.0 migration). Tracked in the predecessor plan; independent.
- The 13 unwritten invariants in `contracts/tool-resolution-problems.json`. Separate track; noted
  here only because its runbook's COMPLETE banner is one of the documents Slice 0 corrects.
- `propose_edit`'s duplicate schema is **in** scope (it is `frontend_tools.py` residue), but its
  *execution* already moved and does not change.

---

## 9. Sources

- 2026-09-03 runstate audit (this session): live federation check (316/316, 0 added, 0 removed, 42
  drifted `inputSchema`), the 14-site gate census, the 7-producer suspend census, the manifest
  lifecycle read.
- `docs/specs/2026-07-19-frontend-tools-mcp-migration.md` §2.3 (the KIND taxonomy).
- `sdks/python/loreweave_mcp/tasks_wire.py:155-172` (`gate_or_confirm`).
- `services/chat-service/app/agentruntime/contract.py:80-103` (`SERVED_LIFECYCLES`, `LIFECYCLE_MOVES`).
