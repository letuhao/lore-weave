# Track C — completeness audit (2026-07-11, **updated 2026-07-12, then 2026-07-15 all-tracks-clear**)

> **2026-07-15 UPDATE (all-tracks-clear run).** Track C is effectively COMPLETE. Full account:
> [`docs/plans/2026-07-13-all-tracks-clear-RUN-STATE.md`](../../../../plans/2026-07-13-all-tracks-clear-RUN-STATE.md)
> + [`docs/eval/discoverability/2026-07-15-M2-all-scenarios-clear.md`](../../../../eval/discoverability/2026-07-15-M2-all-scenarios-clear.md).
> - **P-1 (step-runner) shipped + the "model ceiling" DISPROVEN.** S03/S04/S05/S09's failures were
>   every one a fixture/harness/product-infra gap — never a capability limit. Fixes: intent→workflow
>   pinning, rail-driver DRAIN grounding, domain-aware Tier-W eval commit, cross-service translation
>   coverage, canon-check book_id resolution, translation-pass start_job. **S06 flagship 3/3 GREEN**
>   (fresh, SQL-proven); **18/18 scenarios green ≥2/3** (2026-07-15 clean run, post book-quota fix:
>   13 DB-scored + 4 judge + S00e `90e3f417e`); S09 2/3 names the planted contradiction; **S10 (maps)
>   2/3 and S11 (reader) 3/3 spoiler-safe — both BUILT + proven**, not "authored/in-flight".
> - **WS-5 catalog: now 12 System workflows** live (10 + `draw-a-map` + `lore-so-far`, added this run
>   for S10/S11; the WS-5 "13" count was aspirational — W8 is an onboarding routing change, not a rail).
> - **FE surfaces (P-5) all BUILT + browser-proven by effect:** workflow rack, binding UI, W10 maps
>   canvas, W11 lore-seeker reader (spoiler-windowed, fail-closed).


> **2026-07-12 UPDATE.** A long autonomous run advanced Track C substantially. The full
> account is [`docs/plans/2026-07-12-track-c-completion-RUN-STATE.md`](../../../../plans/2026-07-12-track-c-completion-RUN-STATE.md)
> (§10 ledger + §11 PO packet). Headlines:
> - **The consent defect (`D-C-ALLOWLIST-WRITE-ONLY`) is CLOSED** — view / revoke / deny +
>   the backend that never existed. Two adversarial reviews, all findings fixed.
> - **The flagship's real blocker was found**: a 44KB tool payload (86% unusable) the model
>   called 24× and built nothing from. Fixed, + a result-size ceiling in both MCP SDKs.
>   S06 categories went **0 (coin-flip) → reliably 13**; still 1/5 (the model adopts and
>   stops), **parked P-1** = a server-side step-runner (a genuine design).
> - **WS-5 catalog: 3 → 5** (populate-from-notes, kg-build). W5/W9's audit tool-names below
>   were **wrong** (`translation_run`/`canon_check` do not exist) — re-scope P-3.
> - The rail-driver mechanism (book-state grounding, `done_when`, grant-gated probe) is
>   complete. Still parked: 8 workflows (P-3), scenario coverage (P-4), FE surfaces (P-5).

---

# Track C — completeness audit (2026-07-11)

**Method:** every claim below was **verified against code/DB**, not read off a status doc. (A debt list
overstates real debt; this repo has been burned by both directions — a "blocked" item that already existed,
and a "done" item that was never wired.) Where a doc and the code disagreed, the code wins and the doc is
corrected.

**Bottom line: Track C is ~35% done. The mechanism half is real and live-proven. The USER-FACING half —
which is literally the track's name — is almost entirely unbuilt, and the track's Definition of Done
(S06 ❌→✅) is NOT met.**

---

## 1 · The three deliverables

| WS | Deliverable | Status | Evidence |
|---|---|---|---|
| **WS-3** | mode→capability binding (C6) | ✅ **DONE** | `mode_bindings` table + 3-tier resolve + `/internal/workflows?mode=` + `GET/PUT /v1/agent-registry/mode-bindings/{mode}`; live-proven (assent → rail) |
| **WS-3** | permission-management UI (view / revoke / deny an allowlisted tool) | ❌ **NOT BUILT — and the backend does not exist either** | `app/db/tool_approvals.py` exposes ONLY `is_tool_approved` + `approve_tool`. **No list. No revoke. No route.** |
| **WS-3** | per-user MCP-server whitelist | ✅ **DONE** (by the agent-extensibility track, but the deliverable is satisfied) | `mcp_server_enablement(mcp_server_id, owner_user_id)` + `PUT /mcp-servers/{id}/enablement` + `McpServersView.tsx` |
| **WS-5** | author the W1–W12 catalog as C3 Workflow objects | 🟡 **3 of 13** | seeded: `glossary-bootstrap` (W1), `entity-triage` (W3), `vision-to-book` (the flagship spine). **10 missing.** |
| **WS-7** | baseline + re-test S00–S12 with gemma | 🟡 **4 of 13 run** | S01 ✅ · S02 ✅ · S03 ✅ · S06 ❌ (the DoD). S04/S05 authored-not-run. S00a–e, S06b, S07–S12 never run. |

### Definition of Done: **NOT MET**
> *"a user reaches every journey by talking, no jargon required; the flagship S06 ❌→✅ with gemma."*

S06 is **❌**, at 2/5 artifacts with high run-to-run variance (kinds 5/12/0/5 · entities 0/0/0/0 ·
plan 0/1/0/0 across four identical runs). Residual jargon still reaches the user (`PlanForge`×4).

---

## 2 · The workflow catalog (WS-5) — 3 of 13

| # | Workflow | Authored? | Backing tools exist? | Verdict |
|---|---|---|---|---|
| W1 | Glossary bootstrap | ✅ `glossary-bootstrap` | ✅ | done |
| W2 | Populate glossary from a story-seed doc | ❌ | ✅ `glossary_extract_entities_from_doc` (Track B WS-4A) | **buildable now** |
| W3 | Entity population + triage | ✅ `entity-triage` | ✅ | done |
| W4 | KG build from a populated glossary | ❌ | ✅ `kg_project_create` · `kg_project_entities_to_nodes` · `kg_build_graph` | **buildable now** |
| W5 | Translation pass | ❌ | ✅ | **buildable now** |
| W6 | **Chapter compose journey** (6-phase) | ❌ | ✅ `composition_authoring_run_*` | buildable |
| W7 | End-to-end "build a book" | ❌ | ✅ (chains W1–W5) | buildable |
| W8 | Intent-branching onboarding fork | ❌ | n/a — a **FE surface**, no backend needed | needs FE |
| W9 | Canon-check / continuity pass | ❌ | ✅ | buildable |
| W10 | Worldbuilding-first world container | ❌ | ✅ (Track B shipped the backend) | needs FE + workflow |
| W11 | Reader / lore-seeker exploration | ❌ | ✅ (Track B shipped the backend) | needs FE + workflow |
| W12 | Multi-chapter autonomous drafting | ❌ | ✅ (wrap the existing FSM) | buildable |
| — | **`vision-to-book`** (the flagship spine) | ✅ | ✅ | done |

**Note — a naming error I introduced and have now corrected:** I called the flagship spine "W6". The
umbrella's **W6 is the Chapter-compose journey**; `vision-to-book` is the flagship's own rail, outside the
W1–W12 numbering. All docs/comments relabelled.

**Honest read:** 8 of the 10 missing workflows are **buildable today** — every backing tool exists (Track B
and Track D both closed their halves). Authoring them is *unbuilt work*, not blocked work.

---

## 3 · The user-facing surfaces (the track's actual name) — almost nothing

| Surface Track C owns | Exists? | Evidence |
|---|---|---|
| mode selector (ask/write/plan) | ✅ | `ChatInputBar.tsx` (+ its own test) |
| **binding UI** (edit the mode→capability profile) | ❌ | zero references to `mode-bindings` in `frontend/src` |
| **permission-management UI** (see/revoke "Always allow") | ❌ | see §4 — the **backend is write-only** |
| **workflow rack** (see/run the curated workflows) | ❌ | no consumer of `workflow_list` in the FE |
| MCP-server whitelist UI | ✅ | `McpServersView.tsx` |
| W8 onboarding fork | ❌ | no intent-branching fork |
| W10 world-container surface | ❌ | no files |
| W11 reader / lore-seeker surface | ❌ | no files |

---

## 4 · DEBT (real, verified — these are defects, not "future work")

| ID | Sev | Debt | Why it is debt, not a feature request |
|---|---|---|---|
| **D-C-ALLOWLIST-WRITE-ONLY** | **HIGH** | **A user can GRANT "Always allow" on a tool and can never see it, revoke it, or deny it.** `tool_approvals.py` has `is_tool_approved` + `approve_tool` and **nothing else** — no list, no delete, no HTTP route. | A **consent** mechanism with no withdrawal is broken by design. The user grants a standing permission to an autonomous agent, forever, with no UI to inspect or revoke it. The umbrella spec itself flags this ("the allowlist is write-only via 'Always allow'"). It is the only Track C item I would call a genuine *safety* defect. |
| **D-C-JARGON-PLANFORGE** | MED | `PlanForge` ×4 / `NovelSystemSpec` ×3 still reach the user in S06. | The rail's `notes_md` owns vocabulary *inside the rail*; these leak from the **plan_forge skill prose / tool descriptions**, which have no vocabulary owner. Same bug class, different source. |
| **D-C-S06-NOT-SHIPPING** | **HIGH** | The flagship is 2/5 with coin-flip variance; the cast never lands in any run. | **This is the track's Definition of Done.** Root cause is now known (see §6) — it is not a missing tool. |
| **D-WS3-BINDING-GUI** | MED | The mode binding is API-addressable but has no settings panel. | A user cannot turn the co-writer rail off without an API call. Settings & Config wants a user setting to be *reachable*. |

### Recently cleared (were on the defer list; **re-verified as fixed in code**)
- ~~`D-WS3-RESUME-PIN`~~ — it was never a legitimate defer: `/review-impl` showed it was a **HIGH** (the rail's
  text survived a confirm-gate suspend while its tools did not, so the rail broke at its first gate). Fixed.
- ~~`D-WS3-BOOK-TIER-PIN`~~ — also worse than logged (a private workflow could be pinned into a *shared* book,
  silently unpinning every other grantee's turns). Fixed.

---

## 5 · DEFERRED — and which rows actually EARN their deferral

The repo's gate: a finding may be deferred only if it is **out of scope · large/structural · naturally-next-phase ·
blocked on something genuinely external · or a conscious won't-fix.** *"I'd have to build it"* is **not** blocked.

| Item | Claimed reason | Audit verdict |
|---|---|---|
| S04 / S05 scenarios | "fixture blocked" | ❌ **DOES NOT CLEAR THE GATE.** 10 books already carry ≥5 active entities, and I seeded empty fixture books with a one-line INSERT four times today. A fixture is **buildable**, so this is *unbuilt work*, not a blocker. **Reclassify: do it.** |
| W2/W4/W5/W7/W9/W12 workflows | (implicitly deferred) | ❌ **DOES NOT CLEAR THE GATE.** Every backing tool exists. Authoring a C3 workflow object is a seed row. **Reclassify: unbuilt, do it.** |
| W8/W10/W11 surfaces | needs FE build | ✅ **Gate #2 (large/structural)** — these are real product surfaces (onboarding fork, world container, reader), each its own design. Legitimately deferred. |
| `D-C-ALLOWLIST-WRITE-ONLY` | — | ✅ **Gate #2**, but only just: the *backend* (list+revoke route) is ~1 hour; the UI is a panel. Given it is a consent defect, **it should not sit behind the workflow authoring.** |
| S06 step-runner | — | ✅ **Gate #2 (large/structural)** — a server-side rail driver + book-state grounding is a genuine design, not a prompt tweak. |
| `D-WS3-BINDING-GUI` | — | ✅ **Gate #2** — a settings surface. |

---

## 6 · OUT OF SCOPE for Track C (owned elsewhere — do not let it pool here)

| Item | Owner | Note |
|---|---|---|
| Discovery mechanism (`tool_list`/`tool_load`/`find_tools`), the C1–C4 contracts, the step-runner primitive | **Track A** | ✅ COMPLETE. Discovery is measurably dead as a failure mode: **0 `find_tools` calls** in the last three S06 runs. |
| Backing tools for W2/W4/W10/W11 (seed-doc→entities, glossary→KG projection, world maps, reader) | **Track B** | ✅ COMPLETE — verified present in the liveness manifest. Track C's surfaces are no longer blocked on B. |
| Tool liveness / `_meta` / selection quality | **Track D** | ✅ COMPLETE. |
| **Model quality itself** | nobody — it is the constraint | gemma-4-26b's run-to-run variance is the environment Track C must ship *into*, not a bug Track C can fix. Design for it (drive the rail server-side) rather than prompt harder. |
| `test_stream_service_story04::test_emit_chat_turn_persists_dirty_activation_state` (currently RED) | **the concurrent WS-1.6 session** | Their commit `3f3856e92` added a `persist_capture_status` write at `stream_service.py:4596`, *after* the `activated_tools` write at :4465; the test asserts on the **last** `pool.execute`. Not mine — flagged, not touched. |

---

## 7 · What I would do next, in order

1. **The step-runner + book-state grounding** (unblocks the DoD). The mechanism is done; nothing *drives* the
   rail. Give the model "you are at step N, N−1 succeeded, the next call is X" from the server, and answer
   "what is already done?" from the SSOT instead of from the model's memory.
2. **The allowlist list/revoke route + panel** (`D-C-ALLOWLIST-WRITE-ONLY`). Small, and it is a consent defect.
3. **Author W2/W4/W5/W9** — four seed rows, every backing tool present. This is the cheapest way to move
   S02/S04/S05/S09 and it is *unbuilt*, not blocked.
4. Then the big surfaces (W8/W10/W11) — genuinely large, genuinely deferred.
