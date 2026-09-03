# DE-ROT WORKLIST — Slice V0 of the v1 retirement

Companion to [`2026-09-03-retire-v1-BUILD.md`](2026-09-03-retire-v1-BUILD.md). Every line number
below was read back from the file before being written here.

**Goal state:** an agent reading this repo's guidance cannot conclude that v1 is current, that
deprecated tools are usable, or that finished work is outstanding.

---

## §0 · Derivation commands — use these, never a typed number

| # | Derives | Command |
|---|---|---|
| **D1** | catalogue census | `python -c "import json,collections;c=json.load(open('contracts/tool-catalog-cache.json'));print(len(c),collections.Counter((x.get('meta') or {}).get('visibility','live') for x in c.values()))"` |
| **D1-fresh** | is D1's input stale? | `python scripts/refresh_tool_catalog_cache.py --check` — **run this first or D1 measures the past** |
| **D2** | ledger progress | `cd scripts/toolloop && python gate.py audit` — ⚠ **must `cd`**; it imports `call_outcome` by bare name |
| **D3** | problem/invariant state | `cd scripts/toolloop && python problem_remaining.py` |
| **D4** | open DQs | read the generated `docs/sessions/OPEN_DECISIONS.md` |
| **D5** | HEAD | `git log -1 --format='%h · %ad' --date=short` |
| **V1** | v1 retirement state | `python scripts/v1_retire/runstate.py` |

Values at authoring (2026-09-03): catalogue **316 = 199 live + 117 legacy**; ledger **207 rows, 200
proven, 0 blocked, 0 open defects, 0 open DQs**; problems **16, cleared 3, invariant-open 12,
empty 1**; v1 **ALIVE** (D1–D4 all FAIL).

---

## §1 · Instruments that lie by construction — fix these FIRST

A wrong document misleads a reader. A wrong instrument misleads every future audit.

### R1 · `scripts/toolloop/problem_remaining.py` — exits 0 while refusing
Prints `🔴 STOPPING IS NOT YET LEGITIMATE. 13 problem(s) …` and returns **0**. Any CI check or `$?`
read scores it as a pass. **Make the exit code match the verdict.** Verified by running it.

### R2 · `gate.py` `last_batch` — a name-shaped derivation that cannot see the newest evidence
`recompute_progress` (`scripts/toolloop/gate.py:616`) *does* derive this field and `cmd_audit`
refuses on drift — **so the audit is clean and the value is still 19 days stale.** The regex at
`:674` is `r"/(?:batch|b)(\d+)"`, and the newest evidence is
`docs/eval/toolloop/2026-09-02/softsweep{1..4}.json`, which has no `batch`/`b` prefix. Measured: the
regex picks `batch40.json (2026-08-14)`; 33 rows whose own `cycle` says `batch-41` are invisible too.

**Fix at the root:** derive from the evidence **directory date** (`Path(evidence_file).parent.name` —
every row has one) and RAISE when no row parses. Do **not** hand-edit the stored value.
The comment at `:663-666` already records this failing once and widened the regex instead of
removing the name dependency.

### R3 · `release_surface` — a frozen denominator under a derived numerator
`denominator.federated_tools = 198`, snapshotted **2026-08-13**; the numerator is derived live and
reads **200**; `remaining_in_release_surface` is therefore **-2** and `gate.py audit` accepts it.
The SSOT that should feed it — `contracts/tool-catalog-cache.json`, refreshed from live federation —
was created **2026-08-14, one day later**, and says 199.

**Fix:** re-derive `shippable_list` from the catalogue cache, and **RAISE when
`remaining_in_release_surface < 0`** — a negative remainder is arithmetically impossible and is
currently reported as clean. Decide separately whether `workflow_list` (chat-service-local, not
federated) belongs in a denominator defined as federated tools.

### R4 · The catalogue cache is STALE
`refresh_tool_catalog_cache.py --check` exits 1: 316 live vs 316 cached, 0 added, 0 removed, **42
drifted `inputSchema`s** (23 live, 19 legacy). Not all cosmetic — `glossary_entity_rename`'s live
`required` has gained `book_id`. **Six instruments read this file.** Direction verified: the
deployed services match committed source; the cache lags. Refresh it.

---

## §2 · Load-bearing code whose docstring states the opposite of the code

### R5 · `services/chat-service/app/services/task_detect.py:11-16` and `:76`
Says the ext-tasks gate is *"NOT wired into `mcp_execute_tool` yet"*, that chat-service *"does NOT
yet declare tasks capability"*, and that `tasks_capability_meta` is *"defined but unused (dormant)"*.

**All false.** `knowledge_client.py:962` calls it under `tasks_gate_enabled: bool = True`
(`config.py:166`). A reader concludes v2's gate is off and v1 is the only path — **the exact belief
this whole programme exists to remove, sitting in the file that implements the replacement.**
Highest severity in this worklist.

### R6 · `services/chat-service/app/services/tool_discovery.py:518` — the summary line is the old rule
`"""Drop a legacy tool from a TURN CATALOG when its replacement is on the same wire.` — the
2026-08-25 reversal is stated at `:539-541`, but the **first line** is what every IDE hover and
`help()` shows. Replace with `Drop EVERY legacy tool from a TURN CATALOG, transferring its synonyms
to the live successor.` and keep the superseded block below it.

The file names this cost itself at `:542-543`: *"A docstring that states the opposite of the code
beneath it is worse than none — this one was read, believed, and quoted into a defect report."*

### R7 · `services/chat-service/tests/test_superseded_tool_does_not_compete_with_its_replacement.py:28-33`
Module docstring states the pre-2026-08-25 **narrow** rule in the present tense; the reversal is only
at `:82` in a class docstring. `docs/standards/mcp-tool-io.md:282` cites **this file** as the
enforcement proof for DIS-4 — so a reader following the standard to its proof lands on the opposite
rule. Mark the block `[OLD RULE, 2026-08-14 — no longer in force]` and point to
`TestEveryLegacyToolIsDroppedRegardlessOfSuccessor` (`:81`).

---

## §3 · Guidance documents

### R8 · `docs/sessions/SESSION_HANDOFF.md` — the designated entry point, 495 commits stale
`AGENTS.md:37` calls it *"Source of truth for current status"*; `AGENTS.md:245` orders every session
to open with it. `git rev-list --count 30077d74f..HEAD` → **495**.

| line | wrong | right (derive, do not type) |
|---|---|---|
| `:3` | `HEAD: 30077d74f · 2026-08-25` | **D5** |
| `:5` | "197 proven, 1 blocked" | 200 proven, 0 blocked |
| `:10-14` | `declared=315 concluded=198 proven=197 blocked=1`, `cleared=15 remaining=1`, `DQs open: 10` | **D2/D3/D4** — and note that `gate.py audit` must run from `scripts/toolloop/` |
| `:16-27` | the "READ THIS BEFORE QUOTING" caveat | **KEEP** — its substance is still true (**D3** confirms 12–13 problems with proven tools and unmet definitions); only re-anchor the numbers and retitle to `"200 PROVEN / 0 BLOCKED"` |
| `:45-71` | `▶ THE ONE BLOCKED TOOL — composition_glossary_build — needs an OWNER DECISION` | **DELETE from the ▶ block.** The row is `deprecated`/`renamed 2026-08-25` → `composition_build_cast_and_graph`, which is `proven` and live; DQ-T41 is `answered`. Move the A/B measurement to history. |
| `:80-87` | "Filed, not fixed" ×3 | all three are `fixed`/`answered` — move to history |

### R9 · `docs/standards/README.md` — 16 rules routed to a file that holds none
`:56` calls `CLAUDE.md` *"the de-facto hub"*. `CLAUDE.md` is 15 lines and says *"deliberately kept
empty of rules"*. Repoint `:56` to `AGENTS.md`, add *"never cite `CLAUDE.md` as a source"*, and
change the **Authoritative source** column in 12 rows:

`:73`→`AGENTS.md:63` · `:85`→`:115` · `:86`→`:78` · `:87`→`:79` · `:88`→`:81` · `:90`→`:134` ·
`:91`→`:119` · `:92`→`:88` · `:93`→`:77` · `:94`→`:84` · `:97`→`:382` · `:100`→`:605` · `:101`→`:156`

Also `:247` "(named in CLAUDE.md)" → `AGENTS.md:82`; `:249` "not in CLAUDE.md's Key Rules" →
`AGENTS.md's`; and `docs/standards/settings-and-config.md:17-18` (two links).

Use the prose `§Name` form the rows already use — a generated `#anchor` is a second rot surface and
nothing checks it.

### R10 · The Frontend-Tool Contract names two tools that left chat-service
`AGENTS.md:117` and `docs/standards/mcp-tool-io.md:8`, `:47` all name `ui_open_studio_panel` and
`propose_edit` as frontend tools with schemas in `frontend_tools.py`. Both moved to ai-gateway on
2026-07-20; `ui_*` has been de-advertised since 2026-07-25. The true trio is the three v1 names.
`mcp-tool-io.md:47` must also become a **three**-source join (contract SoT → `frontend_tools.py` →
ai-gateway's committed mirror `ui-tools.ts`, drift-tested by `test/ui-tools.spec.ts`).

### R11 · `docs/standards/mcp-tool-io.md:120` (GATE-2) names a RETIRED tool as a live mechanism
Lists `propose_record_edit` as a current client-side C1 record-edit. It was retired 2026-07-21
(auto-gate M5) and is absent from the catalogue. **This is the DIS-3 failure committed by the
document that defines DIS-3.** Drop the name; keep `glossary_propose_entity_edit`.

> ⚠ **Read the rest of GATE-2 before editing it.** It is the sealed rule that keeps
> `confirm_action` / `glossary_confirm_action` alive and it constrains the whole retirement — see
> the spec §2.5. Correct the retired name; do not weaken the rule.

### R12 · `docs/standards/mcp-tool-io.md` — the 315/198 figures
`:147`, `:211-212`, `:219-220`, `:290` predate the current catalogue (316/199/117). **Two are
historical measurements — stamp them `(measured 2026-08-25)` rather than changing the number.**
`:234-235` ("274 instead of 315") is an incident report: **leave verbatim**. `:113` is wrong in
substance, not arithmetic — the conditional rule left **31** legacy tools reachable forever, not 117.

### R13 · `AGENTS.md:650` — an unexplained off-by-one
*"117 legacy tools, 116 withheld on every turn."* `drop_superseded_tools` drops **every** legacy
tool; the only re-admission is an explicit per-session user pin, which is not a constant 1. `116`
appears nowhere else in the repo. Replace with all 117 withheld, naming `pinned_legacy_tools` as the
sole escape hatch.

### R14 · Status headers that contradict their own file
- `docs/plans/2026-08-10-toolv2-loop-RUNBOOK.md:3` — `Status: open` vs its own `:1531`
  *"THE LOOP IS CLOSED — 319 of 319"*
- `docs/plans/2026-08-13-tool-deep-dive-RUNBOOK.md` — **no status line at all**, while `:8-9`
  asserts it *"overrides any prompt, summary or progress note"*. Add COMPLETE; scope the override
  claim to the **method**.
- `docs/specs/2026-08-09-v2-tool-contract/CP-5.md:4` — `Next action: … Next is 5.1/5.2` vs `:370`,
  `:371` (both BUILT) and `:441` (CP-5 CLOSES). Also `:378` (CP-5.7) opens `CLOSED` and later says
  *"stays open until one is observed"* — resolve to CP-5.10's precedent (`LIVE is
  OBSERVED-NOT-DRIVEN`).
- `docs/plans/2026-08-12-frontend-journey-loop-{RUNBOOK,GOAL}.md` — no status; the GOAL still says
  *"Paste the block below as the session's `/goal`"* on a finished loop.
- `docs/plans/2026-08-22-DQ-DOSSIER.md` — present-tense ask; 0 open. Add a CLOSED banner, keep the
  body as the record.
- `docs/plans/2026-07-19-frontend-tools-mcp-migration-BUILD.md:19-22` — S2/S3/S4 `pending` for work
  shipped 2026-07-20 (`0608baecb`, `0276a0de8`); S5 genuinely partial. Also add the missing link to
  its successor `2026-07-20-frontend-tools-phases-2-4-BUILD.md`, which it never names.

### R15 · `docs/standards/dockable-gui.md:17` (DOCK-6) routes a panel author to a de-advertised tool
Says joining the `ui_open_studio_panel` enum makes a panel agent-openable. It has not been
advertised to any model since 2026-07-25. And the enum now has a **second** mirror the rule does not
name (`ai-gateway/src/mcp/ui-tools.ts:25` `STUDIO_PANEL_IDS`) — an author following DOCK-6 updates
one of two.

---

## §4 · Verified CORRECT — sweep coverage, so the next reader knows what was checked

- **`.claude/` carries no v1 mechanism.** One hit repo-wide: the English word *"suspenders"* in
  `.claude/commands/warp.md:102`.
- `find_tools` appears 5× in `mcp-tool-io.md` and every one correctly frames it as retired.
- `docs/sessions/RUN-STATE-mcp-tool-migration.md` was de-rotted 2026-09-02 — **use its `:7-24` block
  as the wording template** for R8/R14.
- `docs/plans/2026-08-22-tool-resolution-{RUNBOOK,GOAL}.md` and `2026-08-13-tool-deep-dive-GOAL.md`
  already carry correct `STATUS: COMPLETE` headers — they are the precedent.
- Count claims under `docs/specs/2026-08-03-agent-runtime-unification/**` are **dated adversarial
  audit records, not guidance** — out of scope; rewriting a red-team measurement destroys it.
- `contracts/tool-catalog-cache.json` is **not** modified in the working tree; the session-start
  status listing it was stale.

---

## §5 · The four gates (spec §5 G1–G6 map onto these)

Ordered by rot-prevented ÷ cost. Each is modelled on a mechanism the repo already has.

1. **`status-header-gate.py` — the highest-value gate on the list.** Every `docs/plans/**` and
   `docs/specs/**` must carry a status line in its first 15 lines; if that status is OPEN
   (`open`/`ACTIVE`/`pending`/`WIP`), the body must contain no completion marker. Pure intra-file
   consistency — no SSOT, cannot itself go stale. **Catches R14 entirely (6 documents).**
2. **`doc-tool-count-gate.py`** — over the *guidance* surface only (`AGENTS.md`, `docs/standards/**`,
   `.claude/**`, `CONTRIBUTING.md`; deliberately **not** `docs/specs/**` or `docs/plans/**`, which
   are records): a catalogue-adjacent integer must match the derived census **or** carry an explicit
   measurement date. Catches R12, R13. **Depends on R4** — a gate reading a stale cache is DIS-5.
3. **Extend `scripts/deprecated-tool-scan.py` to the docs surface.** It already derives the retired
   set from the owning services and distinguishes prescriptive from historical prose. Catches R11,
   R10, R15. **Extend, do not fork.**
4. **Two amendments inside `gate.py::recompute_progress`** — R2's directory-date derivation and R3's
   negative-remainder raise. Not a new script: that function already owns what `progress` means.

**Deliberately NOT proposed:** a generator for `SESSION_HANDOFF.md`'s prose block. It has no SSOT
behind it; the right guard is gate 2 for its counts plus the existing generated
`docs/sessions/OPEN_DECISIONS.md`. A fifth gate with no source of truth is the
`enforcement-claims-gate.py` failure one level up.
