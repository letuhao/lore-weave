#!/usr/bin/env python3
"""workflow-gate.py — Enforce workflow state transitions for AI coding agents.

Python rewrite of workflow-gate.sh. Cross-platform (no bash escaping issues
on Windows). State persisted in .workflow-state.json.

Usage:
  python scripts/workflow-gate.py size <XS|S|M|L|XL> <files> <logic> <side_effects>
  python scripts/workflow-gate.py phase <phase_name>
  python scripts/workflow-gate.py complete <name> <evidence>
  python scripts/workflow-gate.py check <phase_name>
  python scripts/workflow-gate.py status
  python scripts/workflow-gate.py pre-commit
  python scripts/workflow-gate.py reset
  python scripts/workflow-gate.py skip <phase> <reason>
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

STATE_FILE = Path(".workflow-state.json")
AUDIT_LOG = Path("docs/audit/AUDIT_LOG.jsonl")
# MCP_QUERY resolved relative to THIS script's location so the bridge works
# regardless of cwd (commit hooks may invoke from worktrees, CI runners, etc.).
# Phase 7 review-impl MED-3 fix: was Path("scripts/mcp-query.py") cwd-relative,
# silently no-op'd when invoked outside repo root.
MCP_QUERY = Path(__file__).parent / "mcp-query.py"

PHASES = [
    "clarify", "design", "review-design", "plan", "build",
    "verify", "review-code", "qc", "post-review", "session",
    "commit", "retro",
]

SKIPPABLE = {
    "XS": {"clarify", "plan"},
    "S": {"plan"},
}

INITIAL_STATE = {
    "task": "",
    "size": None,
    "size_counts": {"files": 0, "logic": 0, "side_effects": 0},
    "current_phase": None,
    "current_phase_index": -1,
    "phases_completed": [],
    "phases_skipped": [],
    "verify_evidence": None,
    "started_at": None,
    "last_transition": None,
    # AMAW v3.0 L3 deepen — flag set by `amaw-enable` verb (called by /amaw slash cmd).
    # When True, cmd_complete writes events to AUDIT_LOG.jsonl and selectively bridges
    # high-signal events (sprint_complete, pragmatic_stop, REJECTED reviews) to
    # ContextHub via mcp-query.py add_lesson. Default v2.2 mode → flag stays False,
    # no MCP autocalls, no AUDIT_LOG entries.
    "amaw_enabled": False,
    "amaw_enabled_at": None,
}


# ── AMAW L3 helpers (no-op when amaw_enabled=False) ─────────────────


def _log_audit(event: dict) -> None:
    """Append event to AUDIT_LOG.jsonl. Caller MUST gate on amaw_enabled."""
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def _parse_ts(raw) -> datetime | None:
    """Parse an ISO-8601 timestamp to a timezone-AWARE UTC datetime.

    /review-impl HIGH-1: AUDIT_LOG timestamps are heterogeneous — the main
    agent writes naive local time (`datetime.now().isoformat()`), while the
    Adversary/Scope-Guard sub-agents (separate LLM agents) emit a mix of naive,
    `+offset`, and `Z` forms. Lexical string comparison of those is wrong: a
    UTC `Z` timestamp on a UTC+7 machine sorts BEFORE the naive local string
    of the same instant. Compare parsed datetimes, never raw strings.

    Naive input is assumed local (correct for `amaw_enabled_at` and for naive
    sub-agent timestamps written against the same wall clock). Unparseable
    input returns None — the caller decides how to treat it.
    """
    if not raw:
        return None
    s = str(raw).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.astimezone()  # naive → assume local tz
    return dt.astimezone(timezone.utc)


def _had_rejected_review(task_slug: str, phase: str, since: str | None = None) -> bool:
    """True if an adversary review event for this task AND this phase logged
    status REJECTED (DEFERRED #002).

    The bridge previously inferred rejection from a substring match on the
    main agent's free-text evidence (`"REJECTED" in evidence.upper()`) — which
    false-positives on "NOT REJECTED", "non-rejected", etc. This reads the
    structured `status` field that the Adversary sub-agent writes to
    AUDIT_LOG.jsonl, the authoritative signal. A rejected round is worth a
    cross-session lesson even if a later round APPROVED — the rejection
    captured a real defect pattern future Adversaries should be able to find.

    `phase` is matched (Adversary r1 WARN-1): a REJECTED in `review-design`
    must NOT cause `complete review-code` to file a lesson mislabeled
    "...review-code". Each review phase reports its own rejections.

    `since` scopes the scan to the CURRENT run (human-review finding A1):
    AUDIT_LOG.jsonl is ONE append-only file shared by every task ever run.
    Matching on task slug alone means a slug REUSED in a later sprint would
    inherit an earlier sprint's REJECTED verdict and mis-fire an
    adversary-rejection lesson. Passing the run's `amaw_enabled_at` as `since`
    excludes events from prior runs. Timestamps are compared as PARSED
    datetimes via `_parse_ts`, never as raw strings — /review-impl HIGH-1
    found that lexical compare of mixed naive/`Z`/`+offset` forms silently
    excludes genuine in-run events on non-UTC machines. An event whose `ts`
    is missing or unparseable is excluded (consistent with A1's conservative
    anti-false-positive intent). If `since` is None the scan is unscoped
    (legacy behaviour).

    Note (Adversary r1 WARN-3): this re-parses the whole append-only
    AUDIT_LOG.jsonl per bridge call. Accepted — bridge calls happen only on
    review-phase completion (rare), and the log is per-repo small. Correctness
    relies on the Adversary's review event being flushed before cmd_complete
    runs, which the AMAW orchestration guarantees (sub-agent completes, then
    main calls `complete`).
    """
    if not AUDIT_LOG.exists():
        return False
    since_dt = _parse_ts(since) if since else None
    for line in AUDIT_LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if since_dt is not None:
            ev_dt = _parse_ts(ev.get("ts"))
            if ev_dt is None or ev_dt < since_dt:
                continue  # event predates this run (or unparseable) — A1 cross-run guard
        if (ev.get("task") == task_slug
                and ev.get("action") == "review"
                and ev.get("phase") == phase
                and str(ev.get("status", "")).strip().upper() == "REJECTED"):
            return True
    return False


def _bridge_to_contexthub(lesson_type: str, title: str, content: str, tags: list[str]) -> None:
    """Best-effort: shell out to mcp-query.py add_lesson. Never raises.

    Bridge failures are logged to stderr but do NOT block phase completion —
    the workflow state machine must remain deterministic regardless of MCP
    availability.
    """
    if not MCP_QUERY.exists():
        print(f"WARN: bridge skipped — {MCP_QUERY} not found", file=sys.stderr)
        return
    try:
        # Subprocess timeout MUST exceed mcp-query.py's internal HTTP timeout (60s)
        # so we don't kill an in-flight add_lesson whose embedding is still generating.
        # Phase 7 review fix: was 45s → 75s. 60s HTTP + 15s safety buffer.
        result = subprocess.run(
            [
                sys.executable, str(MCP_QUERY), "add_lesson",
                "--type", lesson_type,
                "--title", title,
                "--content", content,
                "--tags", ",".join(tags),
            ],
            capture_output=True, text=True, timeout=75,
        )
        if result.returncode == 0:
            print(f"OK: bridged lesson {result.stdout.strip()}", file=sys.stderr)
        else:
            stderr_tail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "(no stderr)"
            print(f"WARN: bridge exit {result.returncode}: {stderr_tail}", file=sys.stderr)
    except (subprocess.SubprocessError, OSError) as e:
        print(f"WARN: bridge exception: {e}", file=sys.stderr)


def load_state() -> dict:
    if not STATE_FILE.exists():
        save_state(dict(INITIAL_STATE))
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    # Atomic write (DEFERRED #003): serialize to a temp file, then
    # Path.replace() for an atomic rename. Protects against PROCESS-crash
    # (Ctrl+C, exception, kill): STATE_FILE always holds either the complete
    # old state or the complete new state — a half-written file can only ever
    # be the .tmp, never STATE_FILE itself.
    #
    # The tmp is derived from STATE_FILE via with_name(), so the two always
    # share a parent directory — hence the same filesystem, the precondition
    # os.replace needs (cross-device rename raises EXDEV).
    #
    # The .{pid}. infix makes the tmp unique per process: two concurrent
    # workflow-gate.py invocations get distinct tmp files and cannot interleave
    # each other's bytes (Adversary r1 finding 1).
    #
    # NOT covered: power-loss durability — write_text does not fsync, so an
    # OS-buffered tmp whose rename is durable but contents are not could
    # survive a power cut as a partial STATE_FILE. Out of scope for a local
    # dev-tool state file; process-crash safety is the design target.
    tmp = STATE_FILE.with_name(f"{STATE_FILE.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        tmp.replace(STATE_FILE)
    finally:
        # Clean our own tmp if replace() never ran (e.g. write failed, or
        # replace raised PermissionError on a Windows-locked dest).
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def phase_index(name: str) -> int:
    try:
        return PHASES.index(name)
    except ValueError:
        return -1


def completed_phases(state: dict) -> set[str]:
    return {p["phase"] for p in state.get("phases_completed", [])}


def fail(msg: str) -> None:
    print(f"BLOCKED: {msg}", file=sys.stderr)
    sys.exit(1)


# ── Commands ─────────────────────────────────────────────────────────


def cmd_size(args: list[str]) -> None:
    if len(args) < 4:
        fail("Usage: workflow-gate.py size <XS|S|M|L|XL> <files> <logic> <side_effects>")

    size = args[0].upper()
    if size not in ("XS", "S", "M", "L", "XL"):
        fail(f"Invalid size '{size}'. Must be XS, S, M, L, or XL.")

    files, logic, side_effects = int(args[1]), int(args[2]), int(args[3])

    # Determine expected size from counts
    if files <= 1 and logic <= 1 and side_effects == 0:
        expected = "XS"
    elif files <= 2 and logic <= 3 and side_effects == 0:
        expected = "S"
    elif files <= 5:
        expected = "M"
    elif files <= 9:
        expected = "L"
    else:
        expected = "XL"

    sizes = ["XS", "S", "M", "L", "XL"]
    if sizes.index(size) < sizes.index(expected):
        fail(
            f"Cannot undersize: you said {size} but counts suggest {expected} "
            f"({files} files, {logic} logic, {side_effects} side effects). "
            f"Use '{expected}' or larger."
        )

    state = load_state()
    state["size"] = size
    state["size_counts"] = {"files": files, "logic": logic, "side_effects": side_effects}
    save_state(state)

    skips = SKIPPABLE.get(size, set())
    skip_msg = f"  Allowed skips: {', '.join(sorted(skips))}" if skips else "  No phases may be skipped"
    print(f"OK: Task classified as {size} (files={files}, logic={logic}, side_effects={side_effects})")
    print(skip_msg)


def cmd_phase(args: list[str]) -> None:
    if not args:
        fail("Usage: workflow-gate.py phase <phase_name>")

    phase = args[0].lower()
    idx = phase_index(phase)
    if idx < 0:
        fail(f"Unknown phase '{phase}'. Valid: {', '.join(PHASES)}")

    state = load_state()
    task_size = state.get("size")
    if task_size is None:
        fail("Task size not classified yet! Run: workflow-gate.py size <XS|S|M|L|XL> <files> <logic> <side_effects>")

    current_idx = state.get("current_phase_index", -1)
    if current_idx is None:
        current_idx = -1

    skippable = SKIPPABLE.get(task_size, set())
    done = completed_phases(state)

    # Check all intermediate phases are completed or skippable
    for i in range(current_idx + 1, idx):
        p = PHASES[i]
        if p in done:
            continue
        if p in skippable:
            continue
        from_label = f"'{PHASES[current_idx]}'" if current_idx >= 0 else "(start)"
        fail(
            f"Phase '{p}' not completed and not auto-skippable for size '{task_size}'. "
            f"Cannot jump from {from_label} to '{phase}'."
        )

    state["current_phase"] = phase
    state["current_phase_index"] = idx
    state["last_transition"] = datetime.now().isoformat()
    if not state.get("started_at"):
        state["started_at"] = datetime.now().isoformat()
    save_state(state)

    print(f"OK: Entered phase '{phase}' ({idx}/{len(PHASES)})")


def cmd_complete(args: list[str]) -> None:
    if len(args) < 2:
        fail("Usage: workflow-gate.py complete <phase> <evidence>")

    phase = args[0].lower()
    evidence = args[1]

    state = load_state()
    completed = [p for p in state.get("phases_completed", []) if p["phase"] != phase]
    completed_at = datetime.now().isoformat()
    completed.append({
        "phase": phase,
        "completed_at": completed_at,
        "evidence": evidence,
    })
    state["phases_completed"] = completed
    if phase == "verify":
        state["verify_evidence"] = evidence
    save_state(state)

    print(f"OK: Phase '{phase}' marked complete")

    # AMAW L3 — log to AUDIT_LOG and selectively bridge to ContextHub.
    # No-op for default v2.2 (amaw_enabled=False).
    if state.get("amaw_enabled"):
        # Defensive re-normalize (DEFERRED #001, Adversary r1 WARN-2): state["task"]
        # may have been set before _normalize_slug existed, or via a path that
        # bypassed cmd_amaw_enable. _normalize_slug is idempotent so this is free
        # insurance — the slug becomes a tag below and MUST be comma-free.
        raw_task = state.get("task")
        task_slug = _normalize_slug(raw_task) if raw_task else "unnamed-task"
        _log_audit({
            "ts": completed_at,
            "task": task_slug,
            "phase": phase,
            "agent": "main",
            "action": "phase_complete",
            "evidence": evidence,
        })
        # Selective bridge — only high-signal events become lessons.
        if phase == "retro":
            _log_audit({
                "ts": completed_at,
                "task": task_slug,
                "phase": phase,
                "agent": "main",
                "action": "sprint_complete",
                "evidence": evidence,
            })
            _bridge_to_contexthub(
                lesson_type="general_note",
                title=f"Sprint complete: {task_slug}",
                content=f"Phase: retro\nCompleted: {completed_at}\nEvidence: {evidence}",
                tags=["amaw", "sprint", task_slug],
            )
        elif phase in ("review-design", "review-code") and _had_rejected_review(task_slug, phase, state.get("amaw_enabled_at")):
            _bridge_to_contexthub(
                lesson_type="general_note",
                title=f"Adversary REJECTED: {task_slug} {phase}",
                content=f"Phase: {phase}\nCompleted: {completed_at}\nEvidence: {evidence}",
                tags=["amaw", "adversary-rejection", task_slug],
            )


def _normalize_slug(raw: str) -> str:
    """Slugify a task slug (DEFERRED #001): lowercase, collapse any run of
    non-[a-z0-9] characters to a single dash, strip leading/trailing dashes.
    Idempotent — normalizing an already-normalized slug is a no-op.

    The slug flows into the downstream tag list as `["amaw", "sprint", slug]`,
    which `_bridge_to_contexthub` comma-joins and `mcp-query.py` comma-splits
    back — so an un-normalized slug containing a comma (or space, slash, etc.)
    would silently fragment into extra tags. EVERY entry point that lets a
    user supply a slug must call this: `cmd_amaw_enable` (write side) and
    `cmd_pragmatic_stop` (independent arg), plus `cmd_complete` re-normalizes
    defensively on the read side (Adversary r1 BLOCK + WARN-2).

    Empty/all-punctuation input falls back to the tag-safe string
    'unnamed-task'. NOTE: this is distinct from the '(unnamed)' DISPLAY
    sentinel used in print messages (cmd_amaw_enable / cmd_pragmatic_stop) —
    the parens make '(unnamed)' deliberately NOT a valid slug, so it can never
    be mistaken for or collide with a real normalized slug. 'unnamed-task' is
    the value layer (a usable tag); '(unnamed)' is the display layer.
    """
    # str() guard (Adversary r2 WARN-2): a hand-edited state file could carry a
    # non-string `task` (int, null); str() keeps this total instead of raising
    # AttributeError deep in the bridge path.
    slug = re.sub(r"[^a-z0-9]+", "-", str(raw).lower()).strip("-")
    # 64-char cap (human-review finding A2): the slug becomes a ContextHub tag
    # and a lesson title; a pathologically long task name should not produce an
    # unbounded tag. Re-strip in case the cut landed mid-dash.
    slug = slug[:64].strip("-")
    return slug or "unnamed-task"


def cmd_amaw_enable(args: list[str]) -> None:
    """Enable AMAW mode for the current task. Optionally accepts task slug."""
    state = load_state()
    if state.get("amaw_enabled"):
        slug = state.get("task") or "(unnamed)"
        print(f"OK: AMAW mode already enabled for task '{slug}' (no-op)")
        return
    state["amaw_enabled"] = True
    state["amaw_enabled_at"] = datetime.now().isoformat()
    if args:
        normalized = _normalize_slug(args[0])
        if normalized != args[0]:
            print(f"  NOTE: task slug normalized '{args[0]}' -> '{normalized}'")
        state["task"] = normalized
    save_state(state)
    slug = state.get("task") or "(unnamed)"
    print(f"OK: AMAW mode enabled for task '{slug}'")
    print(f"  AUDIT_LOG: {AUDIT_LOG}")
    print(f"  Bridge target: ContextHub via {MCP_QUERY}")
    print(f"  Triggers: retro→sprint_complete; REJECTED reviews; pragmatic-stop")


def cmd_amaw_pre_commit(_args: list[str]) -> None:
    """AMAW-mode addition to pre-commit hook. No-op for default v2.2.

    Calls mcp-query.py check_guardrails when amaw_enabled. If guardrails
    return BLOCKED → exit 1 (block commit). If MCP unreachable → warn + exit 0
    (don't block commits on infra failures).
    """
    # No state file = no task in flight = nothing to gate (DEFERRED #004).
    # MUST check before load_state(), which auto-creates .workflow-state.json
    # from INITIAL_STATE — an agent committing outside any tracked task would
    # otherwise leave a stale state file behind (confusing [ ] markers on the
    # next `status`).
    #
    # Exit SILENTLY here — unlike cmd_pre_commit, which prints a visible
    # "No workflow state found" warning (Adversary r1 WARN-2). In the hook
    # chain `pre-commit && amaw-pre-commit`, cmd_pre_commit runs first and
    # already surfaces that warning; a second one here would just be noise.
    #
    # Single-threaded assumption (Adversary r1 WARN-3): a concurrent `reset`
    # racing between this exists() check and load_state() is out of scope for
    # a local single-user dev tool.
    if not STATE_FILE.exists():
        sys.exit(0)
    state = load_state()
    if not state.get("amaw_enabled"):
        # Default v2.2 mode — no-op
        sys.exit(0)
    if not MCP_QUERY.exists():
        print(f"WARN: amaw-pre-commit skipped — {MCP_QUERY} not found", file=sys.stderr)
        sys.exit(0)
    # Phase 7 review-impl MED-1 fix: call helper with --format json so we parse
    # structured response instead of scraping summary-mode strings (fragile).
    # MED-2 fix: 4xx response → exit 1 (block commit) — wrong shape = something
    # broken at rule layer, safer to block than fail-open.
    try:
        # Note: --format MUST follow the subcommand. argparse subparser default
        # overrides top-level if --format is placed before the verb.
        result = subprocess.run(
            [sys.executable, str(MCP_QUERY), "check_guardrails", "git commit", "--format", "json"],
            capture_output=True, text=True, timeout=15,
        )
    except (subprocess.SubprocessError, OSError) as e:
        print(f"WARN: amaw-pre-commit guardrail check skipped (exception: {e})", file=sys.stderr)
        sys.exit(0)

    if result.returncode == 2:
        # Server down / 5xx — don't block commit on infrastructure failure
        print(f"WARN: amaw-pre-commit guardrail check skipped — ContextHub unreachable (exit 2)", file=sys.stderr)
        sys.exit(0)
    if result.returncode == 1:
        # 4xx / user-input error — BLOCK commit. Something structurally broken
        # with the rule layer or the request; safer to block until investigated.
        print(f"BLOCKED: amaw-pre-commit guardrail check returned 4xx (structural error — investigate before commit):", file=sys.stderr)
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)

    # returncode == 0 — parse JSON verdict
    try:
        verdict = json.loads(result.stdout) if result.stdout.strip() else {}
    except json.JSONDecodeError:
        print(f"WARN: amaw-pre-commit got non-JSON response from check_guardrails — passing through:\n{result.stdout}", file=sys.stderr)
        sys.exit(0)

    # Verdict source is `pass: bool`. Treat absence as CLEAR (no rule layer = no block).
    # Matched rules live in `matched_rules` (verified against live ContextHub response
    # 2026-05-15); `violated`/`rules` kept as fallback for other server versions.
    pass_field = verdict.get("pass")
    matched = verdict.get("matched_rules") or verdict.get("violated") or verdict.get("rules") or []
    if pass_field is False or (isinstance(matched, list) and len(matched) > 0 and pass_field is not True):
        prompt = verdict.get("prompt", "")
        print(f"BLOCKED by guardrails: pass={pass_field}, matched_rules={len(matched) if isinstance(matched, list) else matched}", file=sys.stderr)
        if prompt:
            print(f"  {prompt}", file=sys.stderr)
        for rule in (matched if isinstance(matched, list) else []):
            req = rule.get("requirement") if isinstance(rule, dict) else rule
            print(f"  - {req}", file=sys.stderr)
        sys.exit(1)

    rules_checked = verdict.get("rules_checked", "unknown")
    print(f"OK: amaw-pre-commit guardrails CLEAR (pass={pass_field}, rules_checked={rules_checked})")
    sys.exit(0)


def cmd_pragmatic_stop(args: list[str]) -> None:
    """Record a pragmatic stop event with reason. Only meaningful in AMAW mode."""
    if len(args) < 2:
        fail("Usage: workflow-gate.py pragmatic-stop <task-slug> <reason>")
    # Normalize the slug (DEFERRED #001, Adversary r1 BLOCK): this is a SECOND
    # entry point — independent of cmd_amaw_enable — that feeds task_slug into a
    # comma-joined tag list below. An un-normalized slug here re-introduces the
    # exact comma-fragmentation defect #001 set out to close.
    task_slug, reason = _normalize_slug(args[0]), args[1]
    state = load_state()
    if not state.get("amaw_enabled"):
        print("WARN: pragmatic-stop has no effect in default v2.2 mode (amaw_enabled=False).", file=sys.stderr)
        print("      Run `workflow-gate.py amaw-enable` first to enable AMAW logging.", file=sys.stderr)
        sys.exit(1)

    ts = datetime.now().isoformat()
    _log_audit({
        "ts": ts,
        "task": task_slug,
        "phase": state.get("current_phase") or "unknown",
        "agent": "main",
        "action": "pragmatic_stop",
        "reason": reason,
    })
    _bridge_to_contexthub(
        lesson_type="workaround",
        title=f"Pragmatic stop: {task_slug}",
        content=f"Phase: {state.get('current_phase')}\nTimestamp: {ts}\nReason: {reason}",
        tags=["amaw", "pragmatic-stop", task_slug],
    )
    print(f"OK: pragmatic stop recorded for task '{task_slug}'")


def cmd_check(args: list[str]) -> None:
    if not args:
        fail("Usage: workflow-gate.py check <phase>")

    phase = args[0].lower()
    state = load_state()
    if phase in completed_phases(state):
        print(f"OK: Phase '{phase}' is completed")
    else:
        print(f"NOT COMPLETED: Phase '{phase}' has not been completed yet")
        sys.exit(1)


def cmd_skip(args: list[str]) -> None:
    if len(args) < 2:
        fail("Usage: workflow-gate.py skip <phase> <reason>")

    phase = args[0].lower()
    reason = args[1]

    state = load_state()
    skipped = state.get("phases_skipped", [])
    skipped.append({
        "phase": phase,
        "reason": reason,
        "skipped_at": datetime.now().isoformat(),
    })
    state["phases_skipped"] = skipped

    # Also count as completed so the gate doesn't block
    completed = [p for p in state.get("phases_completed", []) if p["phase"] != phase]
    completed.append({
        "phase": phase,
        "completed_at": datetime.now().isoformat(),
        "evidence": f"SKIPPED: {reason}",
    })
    state["phases_completed"] = completed
    save_state(state)

    print(f"OK: Phase '{phase}' skipped (reason: {reason})")


def cmd_pre_commit(_args: list[str]) -> None:
    if not STATE_FILE.exists():
        print("WARNING: No workflow state found. Proceeding without enforcement.")
        sys.exit(0)

    state = load_state()
    done = completed_phases(state)

    gates = [
        ("verify", "Phase 6 VERIFY not done — run tests and record evidence"),
        ("post-review", "Phase 9 POST-REVIEW not done — present changes to user"),
        ("session", "Phase 10 SESSION not done — update session notes"),
    ]

    for phase, msg in gates:
        if phase not in done:
            print(f"\n{'=' * 50}")
            print(f"  COMMIT BLOCKED: {msg}")
            print(f"{'=' * 50}")
            print(f"\n  Fix: python scripts/workflow-gate.py complete {phase} \"<evidence>\"")
            print(f"  Or:  python scripts/workflow-gate.py skip {phase} \"<reason>\"\n")
            sys.exit(1)

    print("OK: Pre-commit checks passed (verify + post-review + session completed)")
    sys.exit(0)


def cmd_status(_args: list[str]) -> None:
    state = load_state()
    done = completed_phases(state)
    skipped = {p["phase"] for p in state.get("phases_skipped", [])}
    current = state.get("current_phase")
    size = state.get("size", "NOT SET")
    counts = state.get("size_counts", {})

    amaw_enabled = state.get("amaw_enabled", False)
    amaw_label = "ENABLED" if amaw_enabled else "disabled (default v2.2)"

    print(f"Task: {state.get('task') or '(unnamed)'}")
    print(f"Size: {size} (files={counts.get('files', 0)}, logic={counts.get('logic', 0)}, side_effects={counts.get('side_effects', 0)})")
    print(f"AMAW: {amaw_label}")
    if amaw_enabled and state.get("amaw_enabled_at"):
        print(f"  enabled at: {state['amaw_enabled_at']}")
    print(f"Current phase: {current or 'none'}")
    print()

    for p in PHASES:
        if p in skipped:
            marker = "[S]"
        elif p in done:
            marker = "[x]"
        elif p == current:
            marker = "[>]"
        else:
            marker = "[ ]"
        print(f"  {marker} {p}")


def cmd_reset(_args: list[str]) -> None:
    if STATE_FILE.exists():
        STATE_FILE.unlink()
    # Sweep stale save_state tmp files (e.g. `.workflow-state.json.1234.tmp`)
    # left by a process killed between write and replace (Adversary r1 finding 3).
    swept = 0
    parent = STATE_FILE.parent if str(STATE_FILE.parent) else Path(".")
    for stale in parent.glob(f"{STATE_FILE.name}.*.tmp"):
        stale.unlink(missing_ok=True)
        swept += 1
    msg = "OK: Workflow state reset. Ready for new task."
    if swept:
        msg += f" (swept {swept} stale tmp file{'s' if swept != 1 else ''})"
    print(msg)


# ── Main ─────────────────────────────────────────────────────────────


COMMANDS = {
    "size": cmd_size,
    "phase": cmd_phase,
    "complete": cmd_complete,
    "check": cmd_check,
    "skip": cmd_skip,
    "pre-commit": cmd_pre_commit,
    "status": cmd_status,
    "reset": cmd_reset,
    # AMAW v3.0 L3 deepen
    "amaw-enable": cmd_amaw_enable,
    "amaw-pre-commit": cmd_amaw_pre_commit,
    "pragmatic-stop": cmd_pragmatic_stop,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("Usage: workflow-gate.py {size|phase|complete|check|skip|pre-commit|status|reset|amaw-enable|amaw-pre-commit|pragmatic-stop} [args]")
        print()
        print("Commands:")
        print("  size <XS|S|M|L|XL> <files> <logic> <effects>  Classify task size")
        print("  phase <name>                                   Enter a phase")
        print("  complete <name> <evidence>                     Mark phase done")
        print("  check <name>                                   Check if phase done")
        print("  skip <name> <reason>                           Skip with reason")
        print("  pre-commit                                     Gate check for commits")
        print("  status                                         Show current state")
        print("  reset                                          Reset for new task")
        print()
        print("AMAW v3.0 L3 (opt-in, fired by /amaw slash command):")
        print("  amaw-enable [task-slug]                        Enable AMAW mode + AUDIT_LOG + bridge")
        print("  amaw-pre-commit                                Hook: check_guardrails (no-op default v2.2)")
        print("  pragmatic-stop <task-slug> <reason>            Record pragmatic stop + bridge to lesson")
        sys.exit(1)

    cmd = sys.argv[1]
    COMMANDS[cmd](sys.argv[2:])


if __name__ == "__main__":
    main()
