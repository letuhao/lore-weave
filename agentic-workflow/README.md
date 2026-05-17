# Agentic Workflow Bundle (lore-weave-zone-map-design fork)

**Bundle version 2.3** — default v2.2 workflow + opt-in AMAW v3.0 extension
**Repo-tailored:** session paths, planning paths, ContextHub MCP `project_id`, and `scripts/workflow-gate.{sh,py}` dual-impl all wired for `lore-weave-zone-map-design`.

A drop-in structured workflow for AI coding agents (Claude Code, Cursor, Codex, etc.).
Prevents agents from skipping phases, undersizing tasks, and committing without verification.

- **Default (v2.2):** human-in-loop with PO checkpoints at CLARIFY end + POST-REVIEW. Deep adversarial review is an on-demand command (`/review-impl`).
- **Opt-in (AMAW v3.0):** invoke `/amaw` for high-stakes tasks (data migrations, schema changes, security-critical paths). Cold-start sub-agents replace human review at REVIEW + POST-REVIEW. Costs ~$1-5/task in tokens, catches issues human review misses.

> **v2.2 — POST-REVIEW reshaped.** The earlier v2.1 "re-read from disk and adversarially review" rubber-stamps in practice — agents pattern-match to their own reasoning and emit "0 issues found" as ritual close-out. POST-REVIEW is now a **human-interactive checkpoint** (present summary → wait). Deep self-review moved to `/review-impl`.
>
> **AMAW v3.0 — opt-in.** First production run (Phase 14 model swap, 2026-05-15) caught 8 distinct findings across 6 sub-agent calls (~420K tokens), 5 of which were BLOCKs that would have been production bugs. Genuinely valuable for critical work; overkill for everyday tasks.

## What's inside

```
agentic-workflow/
├── README.md                    # This file — setup guide
├── WORKFLOW.md                  # Default v2.2 workflow (paste into CLAUDE.md)
├── AMAW.md                      # Opt-in AMAW v3.0 extension spec
├── CLAUDE.md.snippet            # Minimal snippet for existing CLAUDE.md
├── install.sh                   # One-line installer
├── scripts/
│   ├── workflow-gate.sh         # Bash wrapper (delegates to .py)
│   └── workflow-gate.py         # Cross-platform implementation (canonical)
└── .claude/
    ├── settings.json            # Claude Code hooks (pre-commit gate)
    └── commands/
        ├── review-impl.md       # /review-impl — on-demand adversarial review (default mode)
        └── amaw.md              # /amaw — enable AMAW for current task (opt-in)
```

## Repo customizations applied (this fork)

This bundle has been customized for the **lore-weave-zone-map-design** repo. Differences from upstream:

| Item | Customization |
|---|---|
| `scripts/workflow-gate.sh` | Now a thin bash wrapper around `workflow-gate.py` (Python is canonical impl, sidesteps Windows pyenv-win shim bug). |
| `scripts/workflow-gate.py` | Native Python implementation, ported from this repo. CLI surface identical to .sh. |
| `install.sh` | Also creates `docs/specs/` + `docs/plans/` (in addition to `docs/audit/` + `docs/deferred/`). |
| `WORKFLOW.md` Phase 10 | Names two session paths: `docs/sessions/SESSION_PATCH.md` (main) vs `docs/03_planning/<TRACK>/SESSION_HANDOFF.md` (design tracks). |
| `WORKFLOW.md` Phase 1 + 4 | Spec + plan paths can also live under `docs/03_planning/<TRACK>/` for legacy track work. |
| `CLAUDE.md.snippet` | Includes a "Repo-specific paths" block listing all canonical doc locations + ContextHub `project_id`. |
| `AMAW.md` | New "Repo integration" section: ContextHub MCP server, project_id, workspace mount path, RETRO+CLARIFY MCP call instructions. |
| `.claude/commands/amaw.md` | RETRO step explicitly names ContextHub `project_id = "mmo-rpg-zone-map-design-non-human-in-loop"`. |
| **L3 deepen (2026-05-15)** | `scripts/mcp-query.py` — stdlib REST CLI wrapper for ContextHub. `workflow-gate.py` extended with `amaw-enable` / `amaw-pre-commit` / `pragmatic-stop` verbs + `_bridge_to_contexthub` helper that selectively bridges high-signal AMAW events (sprint_complete, REJECTED reviews, pragmatic_stop) to `add_lesson` for cross-session searchable memory. Sub-agent prompts (Adversary / Scope Guard / Scribe) gain Step 0 calls to `mcp-query.py search_lessons` / `check_guardrails`. Pre-commit hook chain runs `pre-commit && amaw-pre-commit`. All L3 behaviors gate on `state['amaw_enabled']` flag (set by `/amaw` slash command); default v2.2 mode → silent. See `docs/specs/2026-05-15-amaw-l3-deepen.md`. |

## Quick Start (3 steps)

### 1. Run the installer

```bash
# From your project root:
bash /path/to/agentic-workflow/install.sh
```

The installer copies scripts, hooks, and slash commands. Existing files are NOT overwritten.

### 2. Add workflow to agent instructions

**Option A — Full default workflow:**
Copy `WORKFLOW.md` content into your `CLAUDE.md`.

**Option B — Minimal snippet:**
Copy `CLAUDE.md.snippet` content into your existing `CLAUDE.md`.

**Option C — Also enable AMAW:**
After A or B, also copy `AMAW.md` into `docs/amaw-workflow.md` (or anywhere referenced by your CLAUDE.md). The `/amaw` slash command will be active.

### 3. Verify

```bash
./scripts/workflow-gate.sh status
# Expected: prints current task state (will show defaults if no task active)
```

## How it works

### 3-Layer Enforcement (default mode)

```
Layer 1 (CLAUDE.md)      → Agent reads rules, knows skipping is forbidden
                            ↓ agent tries to skip anyway
Layer 2 (State machine)   → Script blocks the phase transition, shows error
                            ↓ agent tries to commit without verify
Layer 3 (Hook)            → Hook intercepts git commit, blocks it hard
```

### Default vs AMAW — when to use which

| Task type | Mode | Why |
|---|---|---|
| Single-file bug fix (XS/S) | Default v2.2 | Human review catches issues at lower cost |
| Doc update, small refactor | Default v2.2 | AMAW overkill |
| Multi-file feature (M) | Default v2.2 + `/review-impl` if safety-sensitive | Self-review + on-demand deep review covers most |
| Data migration, schema change (L+) | **`/amaw`** | Cold-start sub-agents catch coherence issues |
| New service boundary | **`/amaw`** | Edge cases compound; worth the token cost |
| Security-critical (auth, tenants, destructive) | **`/amaw`** + security framing | Adversary spawning with security lens |

### 12-Phase Workflow (both modes share the phases)

```
CLARIFY → DESIGN → REVIEW → PLAN → BUILD → VERIFY → REVIEW → QC → POST-REVIEW → SESSION → COMMIT → RETRO
```

Default mode: REVIEW phases use main-session self-review; POST-REVIEW is human checkpoint.
AMAW mode: REVIEW phases spawn Adversary cold-start; POST-REVIEW spawns Scope Guard.

### Task Size Classification

Agents can't self-judge "small vs large." The protocol forces objective counting:

| Size | Files | Logic | Side effects | Allowed skips |
|------|-------|-------|--------------|---------------|
| XS   | 1     | 0-1   | None         | CLARIFY + PLAN |
| S    | 1-2   | 2-3   | None         | PLAN only |
| M    | 3-5   | 4+    | Maybe        | None |
| L    | 6+    | Any   | Yes          | None |
| XL   | 10+   | Any   | Yes          | None |

The script validates counts vs claimed size — **agents cannot undersize**.

**POST-REVIEW is never skippable** — it's the only phase that requires explicit human or sub-agent review, which is exactly what makes it effective.

### Script Commands

```bash
./scripts/workflow-gate.sh reset                          # New task
./scripts/workflow-gate.sh size M 3 4 0                   # Classify (files, logic, side_effects)
./scripts/workflow-gate.sh phase clarify                  # Enter phase
./scripts/workflow-gate.sh complete clarify "user approved" # Complete with evidence
./scripts/workflow-gate.sh skip plan "user authorized"    # Skip with reason (XS/S only)
./scripts/workflow-gate.sh status                         # Show state
./scripts/workflow-gate.sh pre-commit                     # Gate check before commit
```

## Optional: AUDIT_LOG.jsonl (for AMAW users)

AMAW mode uses `docs/audit/AUDIT_LOG.jsonl` as the single source of truth for phase events + agent verdicts. This is an **append-only JSONL file** that IS committed (durable history).

Schema:
```jsonl
{"ts":"2026-05-15T10:00:00Z","task":"<slug>","phase":"design","agent":"main","action":"design_complete","spec_hash":"abc123"}
{"ts":"2026-05-15T10:05:00Z","task":"<slug>","phase":"review-design","agent":"adversary","action":"review","round":1,"status":"REJECTED","block_count":2}
```

In default v2.2 mode, AUDIT_LOG.jsonl is optional — most users won't need it. Use it if you want a machine-readable timeline across sessions.

## Requirements

- **bash** (Git Bash on Windows, native on Mac/Linux)
- **python** (3.x, for JSON state management)
- **Claude Code** (for Layer 3 hooks — optional, other layers work without it)
- **For AMAW mode:** an Agent-spawn capable environment (Claude Code Agent tool, or equivalent)

## Customization

### Change session tracking path

Search for `SESSION_PATCH.md` in WORKFLOW.md and replace with your project's session file path.

### Add/remove phases

Edit the `PHASES` array in `scripts/workflow-gate.sh`:

```bash
PHASES=("clarify" "design" "review-design" "plan" "build" "verify" "review-code" "qc" "post-review" "session" "commit" "retro")
```

### Adjust size thresholds

Edit the `cmd_size()` function in `scripts/workflow-gate.sh`.

### Disable session check in pre-commit

If your project doesn't use session tracking, remove the session check in `cmd_pre_commit()`.

### Disable AMAW entirely

Just don't copy `AMAW.md` or `.claude/commands/amaw.md`. Default v2.2 works without them.

## Credits

- **Session persistence, role perspectives, guardrails** — [free-context-hub](https://github.com/letuhao/free-context-hub) workflow
- **Brainstorming, TDD, verification gate, debugging, subagent dispatch** — [Superpowers](https://github.com/obra/superpowers) by Jesse Vincent
- **AMAW design (cold-start sub-agents, files-as-truth, conservative-wins gate)** — free-context-hub Phase 14 case study, 2026-05-15

## License

MIT
