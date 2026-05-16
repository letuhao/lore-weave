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
| 12. RETRO | Main | Audit Logger | `add_lesson` to ContextHub MCP (project_id=`mmo-rpg-zone-map-design-non-human-in-loop`); sprint_complete event |

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

Step 0 — Load captured rules (MUST run BEFORE finding 3 problems):
- **First, derive the actual <task topic> from the spec file's H1 title or task slug.** Do NOT pass the literal string `<task topic>` to the helper. If you can't find a topic, use the spec filename (without extension and date prefix).
- Run: `python scripts/mcp-query.py search_lessons "<actual derived topic>" --type guardrail --limit 10 --format json`
- Run: `python scripts/mcp-query.py search_lessons "<changed-file pattern>" --tags adversary-rejection --limit 5 --format json`
- Parse the JSON output. Note any guardrails or prior REJECTED findings relevant to this review.
- Your "3 problems" MUST be informed by these results. If a guardrail is being violated by the proposed change, that's a BLOCK finding. If a prior adversary REJECTED a similar pattern, frame your finding as "this regressed prior fix X" or "this resembles the pattern that produced REJECTED finding Y".
- Informational lessons (general_note, decision, preference) are CONTEXT — do NOT auto-promote them to findings.

Instructions:
- Find EXACTLY 3 things that could go wrong. Use BLOCK or WARN severity.
- Never say what is good. Never propose fixes unless they reveal a flaw.
- For each finding, frame it as a question for the designer to answer.

Adversarial lens (vary by review type):
- Design review: contract holes, side effects not enumerated, idempotency claims that are false, transaction scope issues
- Code review: typeerror/null cases, resource leaks, race conditions, error handling that silently swallows, off-by-one in pagination/iteration

Output: append ONE JSON line to docs/audit/AUDIT_LOG.jsonl:
{"ts":"<iso>","task":"<slug>","phase":"review-design","agent":"adversary","action":"review","round":<N>,"status":"APPROVED|APPROVED_WITH_WARNINGS|REJECTED","findings_count":3,"block_count":<n>,"warn_count":<n>,"note":"<one-liner summarizing the 3 findings>"}

Write a separate findings document to docs/audit/findings-<task>-r<N>.md with the detailed findings.
  IMPORTANT — the Write tool blocks sub-agents from writing report files ("Subagents should
  return findings as text, not write report files"). This is expected. Write the findings doc
  with a Bash heredoc instead: `cat > docs/audit/findings-<task>-r<N>.md <<'EOF' ... EOF`.
  Include footer:
  Lessons consulted: <N> (from search_lessons calls in Step 0)
  Step 0 query strings used: <verbatim text passed to search_lessons>  ← detect literal-placeholder failures
  Guardrails relevant: <list of guardrail titles>, or "(none)" if Step 0 returned 0 guardrails
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
- **Derive <task area> from the spec file's title or task slug — do NOT pass the literal string `<task area>`.**
- Run: `python scripts/mcp-query.py check_guardrails "ready-to-commit" --format json` and respect its verdict. If guardrails return `pass:false` or non-empty `violated` → your verdict MUST be BLOCKED with that reason quoted verbatim.
- Run: `python scripts/mcp-query.py search_lessons "<actual task area>" --type guardrail --limit 5 --format json` to verify no captured rule is being violated by the diff.
- Run: `python scripts/mcp-query.py search_lessons "<actual task area>" --limit 3 --format json` to surface prior similar verdicts. Note them in your AUDIT_LOG event with verbatim query strings used.

Your authority: conservative wins. If ANY prior agent finding is unresolved, OR any acceptance criterion uncovered, OR spec fingerprint shows unexplained drift, OR check_guardrails returned BLOCKED → BLOCKED. Otherwise → CLEAR.

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
    Also run (derive <task intent> + <task area> from the spec or current task slug
    — do NOT pass literal placeholder strings):
      python scripts/mcp-query.py search_lessons "<actual task intent>" --limit 8 --format json
      python scripts/mcp-query.py search_lessons "<actual task area>" --tags deferred --limit 10 --format json
    Print top 3 most-relevant lesson titles for the main session to consider.
    For each lesson tagged "deferred" with no matching DEFERRED.md row → flag as orphan.

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

## Repo integration (lore-weave-zone-map-design)

ContextHub MCP is already provisioned for this repo:
- Server: `http://localhost:3000/mcp` (stack at `D:/Works/source/free-context-hub`, 8 containers via docker-compose)
- Project: `mmo-rpg-zone-map-design-non-human-in-loop` (slash → dash slug normalization)
- Workspace root: `/workspaces/source/lore-weave-zone-map-design` (mounted via `D:/Works:/workspaces` bind)
- MCP tools available: `search_lessons`, `add_lesson`, `check_guardrails`, `search_code_tiered`, `index_project`, etc. (32 tools total)

**RETRO phase action:** call `add_lesson` with `lesson_payload.project_id = "mmo-rpg-zone-map-design-non-human-in-loop"`. Lessons accumulate across AMAW runs as durable cross-session memory.

**CLARIFY phase action:** call `search_lessons` with the same project_id at task start to load prior decisions/preferences before running the Scribe deferred-item scan.

---

## L3 ContextHub integration (deepened 2026-05-15)

AMAW's MCP integration was deepened from shallow (~15-20%) to ~70-80% via 4 components:

1. **`scripts/mcp-query.py`** — stdlib REST CLI wrapper for ContextHub. Sub-agents shell out to it via `python scripts/mcp-query.py <verb>` instead of relying on MCP-tool-inheritance.
2. **AUDIT_LOG → ContextHub bridge** in `workflow-gate.py`: when `amaw_enabled=True`, `cmd_complete` writes events to `docs/audit/AUDIT_LOG.jsonl` AND selectively bridges high-signal events (sprint_complete, REJECTED reviews, pragmatic_stop) to `add_lesson`. Default v2.2 mode → silent.
3. **Sub-agent prompts (Adversary / Scope Guard / Scribe)** include Step 0 calls to `mcp-query.py search_lessons` / `check_guardrails` for captured-rules awareness — see templates above.
4. **Pre-commit hook chain** — `.claude/settings.json` runs `workflow-gate.sh pre-commit && workflow-gate.sh amaw-pre-commit`. Second gate is no-op for default v2.2; calls `check_guardrails` when AMAW mode active.

**Activation:** `/amaw` slash command runs `bash scripts/workflow-gate.sh amaw-enable [task-slug]` which sets `state['amaw_enabled']=True`. All L3 behaviors gate on this flag.

**Selective bridge triggers** (low-noise design: ~3-5 lessons per task):
- `complete retro <evidence>` → bridge as `general_note` with title `Sprint complete: <task>`
- `complete review-design` or `complete review-code` with "REJECTED" in evidence → bridge as `general_note` with title `Adversary REJECTED: <task> <phase>`
- `pragmatic-stop <task> <reason>` → bridge as `workaround` with title `Pragmatic stop: <task>`

**Failure modes (best-effort):**
- ContextHub down → bridge prints warning to stderr, workflow continues. Phase still marks complete.
- `add_lesson` slow (embedding generation 15-60s) → 60s timeout in mcp-query.py; if exceeded, bridge emits warning but server may still complete the insert async (verify with `list_lessons`).

**See:** `docs/specs/2026-05-15-amaw-l3-deepen.md` (spec) and `docs/plans/2026-05-15-amaw-l3-deepen.md` (implementation plan).

---

## Related

- **Default workflow:** `WORKFLOW.md` (always-on)
- **On-demand review (default mode):** `.claude/commands/review-impl.md`
- **AMAW invocation:** `.claude/commands/amaw.md` (this bundle)
