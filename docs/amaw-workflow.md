# AMAW — Autonomous Multi-Agent Workflow (opt-in extension to v2.2)

**Version:** 3.0 (revised 2026-05-15 post-first-real-run calibration)
**Status:** OPT-IN extension to the default v2.2 workflow in `WORKFLOW.md`
**Trigger:** user types `/amaw` (slash command) OR includes "use AMAW workflow" / "spawn Adversary" / "AMAW mode" in the task description.
**Without trigger:** default v2.2 (human-in-loop) is used. AMAW is never auto-activated.

---

## What AMAW adds to v2.2

Default v2.2 uses **main-session self-review** at REVIEW phases and **human checkpoint** at POST-REVIEW. This works for everyday tasks. It misses subtle issues — cache coherence, semantic edge cases, scope drift — because the author self-reviews their own work.

AMAW replaces those self-review/human points with **cold-start AI sub-agents** that read only files, never chat history:

- **Adversary** — at design REVIEW (phase 3) and code REVIEW (phase 7). Finds exactly 3 problems, never says what's good. Re-spawned per round until APPROVED.
- **Scope Guard** — at QC (phase 8) and POST-REVIEW (phase 9). Compares spec fingerprint to implementation, checks AC coverage, conservative final gate.
- **Scribe** *(optional)* — at CLARIFY, PLAN, mid-BUILD, SESSION. Detects deferred items, validates plans, writes session summaries.

**Key principle: files are truth, chat is ephemeral.** Sub-agents cannot inherit the main session's biases because they read only the spec, plan, and audit log — never the conversation history.

---

## When to use AMAW

Phase 14 case study (the first real AMAW run — global model swap touching all projects) found AMAW worth its cost (~$1-5 / ~30 min extra wall-clock per task) for:

| Use case | Why AMAW pays off |
|---|---|
| **Data migrations** | Vector dim changes, schema migrations — cache coherence issues are easy to miss |
| **New service boundaries** | Multi-system contracts where edge cases compound |
| **Security-critical paths** | Auth, tenant isolation, destructive ops, injection defense |
| **Bulk operations affecting >1 project** | Side effects across project boundaries are hard to enumerate |

**Don't use AMAW for:**
- Single-file bug fixes (XS/S tasks)
- Documentation updates
- Small refactors (S/M without side effects)
- Anywhere the human-in-loop default catches the same issues at lower cost

---

## What it costs

Phase 14 measured cost:
- **Tokens:** ~420K across 6 sub-agent calls (~$1-5 at typical pricing)
- **Wall-clock:** ~30 min extra per task in review loops
- **Findings caught:** 8 distinct issues — 5 BLOCKs that would have been production bugs (silent data corruption, cache coherence, runtime crashes)

ROI is good for **critical paths**, overkill for **everyday work**.

---

## Files-as-truth: AUDIT_LOG.jsonl

AMAW uses an append-only `docs/audit/AUDIT_LOG.jsonl` as the single source of truth for phase transitions and agent verdicts. **This replaces earlier per-phase `.phase-gates/*.gate` files** (which polluted the repo with ephemeral state).

**Schema:** one JSON object per line. Append-only — never modify existing lines.

```jsonl
{"ts":"2026-05-15T10:00:00Z","task":"phase-14-model-swap","phase":"design","agent":"main","action":"design_complete","artifact":"docs/specs/DESIGN.md","spec_hash":"abc123def456"}
{"ts":"2026-05-15T10:05:00Z","task":"phase-14-model-swap","phase":"review-design","agent":"adversary","action":"review","round":1,"status":"REJECTED","findings_count":3,"block_count":2,"warn_count":1,"note":"..."}
{"ts":"2026-05-15T10:30:00Z","task":"phase-14-model-swap","phase":"qc","agent":"scope-guard","action":"qc","status":"CLEAR","spec_drift":false,"ac_covered":12,"ac_not_covered":0}
{"ts":"2026-05-15T11:00:00Z","task":"phase-14-model-swap","phase":"retro","agent":"main","action":"sprint_complete","lessons_added":2}
```

**Common actions:** `phase_enter`, `phase_complete`, `review`, `qc`, `deferred_detected`, `size_change`, `commit`, `sprint_complete`.

**AUDIT_LOG.jsonl IS committed** (durable history). `.workflow-state.json` is NOT (per-session state, gitignored).

---

## Phase × Agent spawn map (AMAW mode)

| Phase | Default v2.2 role | AMAW role | Note |
|---|---|---|---|
| 1. CLARIFY | Main + human | Main + Scribe | Scribe scans DEFERRED.md for triggered items |
| 2. DESIGN | Main | Main | Spec fingerprint (sha256) recorded in AUDIT_LOG |
| 3. REVIEW (design) | Main self-review | **Adversary cold-start** | Finds exactly 3 problems. Re-spawn on REJECTED. |
| 4. PLAN | Main | Main + Scribe | Scribe validates no placeholders, size classification correct |
| 5. BUILD | Main | Main | TDD; mid-build Scribe checkpoint if 3+ tasks without review |
| 6. VERIFY | Main | Main | Evidence gate; raw test output in AUDIT_LOG event |
| 7. REVIEW (code) | Main self-review | **Adversary cold-start** | Finds exactly 3 problems comparing code to spec |
| 8. QC | Main | **Scope Guard** | Spec fingerprint vs implementation, AC coverage |
| 9. POST-REVIEW | Human checkpoint | **Scope Guard** | Final conservative gate; CLEAR or BLOCKED |
| 10. SESSION | Main | Scribe | SESSION_PATCH + DEFERRED.md updates |
| 11. COMMIT | Main | Main | Git commit; commit event in AUDIT_LOG |
| 12. RETRO | Main | Audit Logger | Write the lesson into the repo (standard/spec/handoff); `sprint_complete` event in AUDIT_LOG |

---

## Sub-agent prompt templates

### Adversary — Design Review

Use when: phase 3 (REVIEW after DESIGN), phase 7 (REVIEW after BUILD).

```
You are the Adversary reviewer in AMAW. Cold-start, no chat context — read only the files below.

Read ONLY:
- docs/specs/<your-design-file>.md
- docs/audit/AUDIT_LOG.jsonl (for prior context if review round > 1)
- The relevant code files for code-review variants

Step 0 — Captured rules (PRE-LOADED — read them BEFORE finding 3 problems):
- The orchestrator (main session) has already gathered the relevant rules FROM THE
  REPO — `docs/standards/*`, the open `docs/deferred/DEFERRED.md` rows touching this
  area, prior `docs/audit/findings-*.md` for this task — and embedded them into the
  **`## Captured rules`** section near the end of this prompt. **Do NOT go looking
  yourself.** Deterministic injection by the orchestrator beats agent-driven lookup,
  which was measured to be inert (it returned nothing across a full task).
- Read that section. Your "3 problems" MUST be informed by it. If an invariant or
  standard is being violated by the proposed change, that's a BLOCK finding. If a
  prior adversary REJECTED a similar pattern, frame your finding as "this regressed
  prior fix X" or "this resembles the pattern that produced REJECTED finding Y".
- Background context (a design note, a recorded decision, a preference) is CONTEXT —
  do NOT auto-promote it to a finding.
- If the `## Captured rules` section is absent or says "(none pre-loaded)", proceed
  on the files alone — do not block on it.

Instructions:
- Find EXACTLY 3 things that could go wrong. Use BLOCK or WARN severity.
- Never say what is good. Never propose fixes unless they reveal a flaw.
- For each finding, frame it as a question for the designer to answer.

Adversarial lens (vary by review type):
- Design review: contract holes, side effects not enumerated, idempotency claims that are false, transaction scope issues
- Code review: typeerror/null cases, resource leaks, race conditions, error handling that silently swallows, off-by-one in pagination/iteration

## Captured rules
<orchestrator: replace this block with the verbatim text of the repo rules you
gathered before spawning this agent — the applicable docs/standards/* rules, the
open DEFERRED.md rows touching this area, and any prior findings-*.md for this
task. If nothing relevant applies, write exactly: (none pre-loaded)>

Output: append ONE JSON line to docs/audit/AUDIT_LOG.jsonl:
{"ts":"<iso>","task":"<slug>","phase":"review-design","agent":"adversary","action":"review","round":<N>,"status":"APPROVED|APPROVED_WITH_WARNINGS|REJECTED","findings_count":3,"block_count":<n>,"warn_count":<n>,"note":"<one-liner summarizing the 3 findings>"}

Write a separate findings document to docs/audit/findings-<task>-r<N>.md with the detailed findings.
  IMPORTANT — the Write tool blocks sub-agents from writing report files ("Subagents should
  return findings as text, not write report files"). This is expected. Write the findings doc
  with a Bash heredoc instead: `cat > docs/audit/findings-<task>-r<N>.md <<'EOF' ... EOF`.
  Include footer:
  Captured rules: read pre-loaded `## Captured rules` block | (none pre-loaded)
  Guardrails relevant: <list of guardrail titles from the pre-loaded block>, or "(none)"
  Prior REJECTED patterns: <list of titles>, or "(none)"

Status rules:
- APPROVED if all 3 are nitpick WARN
- APPROVED_WITH_WARNINGS if 3 WARNs worth fixing
- REJECTED if any finding is BLOCK

Constraints:
- Total findings doc under 600 words
- Be specific: file paths, line numbers
- Do NOT manufacture issues to hit count of 3
```

### Scope Guard — POST-REVIEW

Use when: phase 9 (POST-REVIEW). Conservative final gate.

```
You are Scope Guard in AMAW. Cold-start. Final conservative gate before SESSION.

Read ONLY:
- docs/specs/<task-spec>.md (acceptance criteria, locked assumptions)
- docs/specs/<task-design>.md (design fingerprint)
- docs/audit/AUDIT_LOG.jsonl (all prior phase events)
- Latest diff or relevant code files

Step 0 — Captured-rules check (MUST run BEFORE rendering verdict):
- The orchestrator pre-loaded the applicable repo rules into the `## Captured rules`
  block of this prompt — read it. Do NOT go looking yourself.
- Name the SINGLE riskiest concrete action this change enables — a real action
  string ("push to main", "run migration 0042 against loreweave_book", "delete the
  legacy glossary rows"), NOT a phrase like "ready-to-commit", which describes no
  action and therefore cannot be evaluated against anything.
- Check that action against the repo's hard invariants — the Gateway, Provider-gateway,
  MCP-first, tenancy, and destructive-DB-ops rules in `AGENTS.md`, plus the applicable
  `docs/standards/*`. If the action would violate one, your verdict MUST be BLOCKED,
  quoting the violated rule verbatim.

Your authority: conservative wins. If ANY prior agent finding is unresolved, OR any acceptance criterion uncovered, OR spec fingerprint shows unexplained drift, OR the Step-0 action violates an invariant → BLOCKED. Otherwise → CLEAR.

Checklist:
1. Compute current spec_hash and compare to design event's spec_hash in AUDIT_LOG — unexplained drift = BLOCKED
2. For each REVIEW event (design + code rounds) — verify resolution (fix event must exist or "documented residual risk" note)
3. AC coverage: walk through spec's acceptance criteria, mark COVERED / UNCOVERED / PARTIAL with evidence
4. Open deferred items with met trigger conditions: must be acknowledged (not silently ignored)

Output: append ONE JSON line to AUDIT_LOG.jsonl:
{"ts":"<iso>","task":"<slug>","phase":"post-review","agent":"scope-guard","action":"qc","status":"CLEAR|BLOCKED","spec_drift":<bool>,"ac_covered":<n>,"ac_uncovered":<n>,"prior_findings_resolved":"<n>/<total>","note":"<one-line verdict>"}

Detailed AC table goes to docs/audit/post-review-<task>.md.
  IMPORTANT — the Write tool blocks sub-agents from writing report files. Write this doc
  with a Bash heredoc instead: `cat > docs/audit/post-review-<task>.md <<'EOF' ... EOF`.

If BLOCKED: name SPECIFIC ACs uncovered or findings unresolved. Don't be vague.
```

### Scribe — Deferred-Item Detection + Session Closeout

Use when: CLARIFY (session start), PLAN (validation), BUILD (mid-task checkpoint), SESSION.

```
You are the Scribe in AMAW. Cold-start. Files-as-truth recorder.

Read ONLY:
- Files relevant to your task (see "Task type" below)
- docs/deferred/DEFERRED.md (current state)
- docs/audit/AUDIT_LOG.jsonl

Task type — depends on when you were spawned:

(a) CLARIFY session-start scan: read DEFERRED.md, list any items whose trigger
    condition is now met. Report each as a candidate "should we handle this now?"
    line for the main session.
    Also grep docs/audit/AUDIT_LOG.jsonl for prior runs in this task area (by `task`
    slug or by `action`), and skim docs/standards/ for rules this task will touch.
    Print the 3 most-relevant prior findings or rules for the main session to consider.

(b) PLAN validation: read the plan file. Check for: placeholders ("TBD",
    "TODO", "add error handling here"), tasks without exact file paths,
    missing verification commands, size classification mismatch with
    task count.

(c) Mid-BUILD checkpoint: read recent AUDIT_LOG events + current file changes.
    Report: context-budget status (how many tasks done without review), drift
    from PLAN scope, any "later" mentions that should go into DEFERRED.md.

(d) SESSION closeout: write SESSION_PATCH.md entry summarizing the task,
    update DEFERRED.md (resolve completed items, add new deferred items),
    append session_complete event to AUDIT_LOG.

Output: depends on task type. Always at minimum: one event appended to
AUDIT_LOG.jsonl describing what you did.

Deferred-item invariant: any time main session output contained "later",
"deferred", "future sprint", "out of scope" — there MUST be a corresponding
entry in DEFERRED.md by SESSION phase. An item mentioned only in chat does
not exist.
```

---

## Anti-skip rules (AMAW-strict)

AMAW mode enforces stricter anti-skip than default v2.2 because the sub-agent review IS the verification:

- **No combining phases** — each phase boundary triggers a different sub-agent prompt
- **No self-authorizing skips** — Conservative wins, any REJECTED requires fix + respawn
- **No "pragmatic close"** without documented residual risk — if you stop sub-agent reviews early, write that decision into AUDIT_LOG as a `pragmatic_stop` event with reason

Skip conditions (same as v2.2):
- XS tasks: may skip CLARIFY + PLAN. AMAW still applies to REVIEW/QC/POST-REVIEW phases that do run.
- S tasks: may skip PLAN only. CLARIFY required.
- M+: no skips.

---

## Calibration table

When opting into AMAW, calibrate intensity by task criticality:

| Task type | AMAW intensity |
|---|---|
| **XS (typo, version bump)** | Skip AMAW entirely. tsc + 1 smoke. |
| **S (small change, 0 side effects)** | 1 Adversary code review only (skip design review). Default for everything else. |
| **M (3-5 files, side effects)** | 1 design + 1 code review + Scope Guard. Stop at first APPROVED_WITH_WARNINGS. |
| **L (data migration, schema, security)** | Full AMAW: up to 3 design rounds + 2 code rounds + Scope Guard. |
| **XL (new system, multi-module)** | Full AMAW + subagent dispatch for parallel sub-tasks. |

**Diminishing returns:** Phase 14 case study found round 3 of design review caught only a typo-level BLOCK that `tsc --noEmit` would have caught for free. Run static analysis before invoking the next Adversary round — don't burn tokens on issues automation catches.

**Stop condition:** APPROVED_WITH_WARNINGS after round 2 is acceptable. Don't chase APPROVED at the cost of doubling token spend.

---

## Files an AMAW user needs

Beyond default v2.2:
1. `docs/audit/AUDIT_LOG.jsonl` — created on first AMAW run
2. `docs/deferred/DEFERRED.md` — created when first deferred item appears
3. `.claude/commands/amaw.md` — `/amaw` slash command (in this bundle)
4. AMAW prompt templates — in this file (AMAW.md)

Nothing else changes structurally from v2.2.

## Where AMAW's memory lives

**`docs/audit/AUDIT_LOG.jsonl` — and nothing else.** Append-only, one JSON line per event,
committed. Grep it by `task` slug or by `action` to recover what happened in a prior run.

`AMAW L3` originally paired that log with an external **ContextHub MCP** server
(`http://localhost:3000/mcp`) holding lessons and guardrails, reached through
`scripts/mcp-query.py` and three harness hooks. **On 2026-08-03 all of it was removed** —
the server registration, `mcp-query.py`, `amaw-guardrail-gate.py`, `amaw-context-inject.py`,
`seed-amaw-guardrails.py`, the `workflow-gate.py` bridge, and the `amaw-pre-commit` verb.

**Why, and the lesson worth keeping:** no agent ever actually called it. It was *configuration
that looked like a capability* — a listed server, a permission allow-list, an "optional" section in
the guide — and its own design notes recorded the tell: agent-driven `search_lessons` was
"empirically inert", returning `(none)` across a full task, which is why step 3 had already moved to
orchestrator-side pre-loading. Meanwhile every hook was fail-open, so a server that was never up
gated nothing while costing a subprocess on every Bash call and a 75-second commit timeout.

**A memory backend that is listed but unread is worse than none**, because it invites an agent to
assume a lookup happened. If a persistent-memory layer is ever reintroduced, it needs a consumer
that demonstrably reads it and a check that fails when it stops being read — see
[`docs/standards/non-vacuity.md`](standards/non-vacuity.md).

**What survived, because it was carrying its weight:**
- `AUDIT_LOG.jsonl` events, gated on `amaw_enabled` — `phase_complete` for every phase, plus a
  second distinctly-actioned row for high-signal events: `sprint_complete` (on retro),
  `adversary_rejection` (a REVIEW completed with "REJECTED" in its evidence), `pragmatic_stop`.
- **Orchestrator-side pre-loading** of the `## Captured rules` block — now sourced from the repo
  (`docs/standards/*`, open `DEFERRED.md` rows, prior `findings-*.md`) instead of a lesson store.
  This was always the part that worked; only its source changed.
- **Activation:** `/amaw` runs `bash scripts/workflow-gate.sh amaw-enable [task-slug]`, setting
  `state['amaw_enabled']=True`. All L3 behaviors gate on this flag; default v2.2 stays silent.

**Historical record:** `docs/specs/2026-05-15-amaw-l3-deepen.md` and
`docs/plans/2026-05-15-amaw-l3-deepen.md` describe the integration as built. They are kept as
history — **do not treat them as current**.

---

## Related

- **Default workflow:** `WORKFLOW.md` (always-on)
- **On-demand review (default mode):** `.claude/commands/review-impl.md`
- **AMAW invocation:** `.claude/commands/amaw.md` (this bundle)
