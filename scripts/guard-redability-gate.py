#!/usr/bin/env python
"""Every guard must go RED against a REAL violation sitting in REAL source.

Why this exists
---------------
An audit of the generation-SSOT run found one of its twelve guards completely inert. The
guard's own control was green, its logic read correctly, and it reported PASS with the
violation it forbids on the line above it. The cause was not logic: the file had been written
by a generator script and `\\b` had become a literal 0x08 backspace, so the pattern required a
control character no source file contains.

Nothing in the repo could have caught that, because every check available was a check on the
author's *intent*: reading the code, reasoning about the regex, running a control that
restated the pattern by hand. The only thing that catches it is putting the real violation on
disk and asking the real guard.

That is a general lesson and this is the general mechanism. The two failure shapes it exists
to catch, both of which it DID catch on its first run:

  · **Scope** — a guard that scans an enumerated list of files is default-uncovered (NV-2).
    The critic guard scanned `routers/engine.py`; the eighth copy lived in `engine/canon_reflect.py`.
  · **Corruption / self-defeat** — a guard whose detector cannot fire, whatever the input.

…and two defects in `llm-budget-ssot-gate.py` that no unit test had reached:

  · Deleting `"max_tokens": max_tokens,` from a real call site left the gate GREEN, because a
    payload with a `**spread` and no budget key was excused as `opaque`. The site was
    identified as a call site BY the key the rule is about.
  · Marking a VERDICT row `signal_inert=True` left the gate GREEN, while the service's own
    unit test went red — and `signal_inert` is also an EXEMPTION from the gate's ratchet.

What a case proves
------------------
Each case asserts THREE things, in order, and all three are load-bearing:

  1. the guard is GREEN on the clean tree (or "it went red" proves nothing — it was already red);
  2. it is RED with the violation injected;
  3. the file is restored BYTE-IDENTICALLY afterwards, verified by sha256.

Restore is from saved bytes, never `git checkout <file>` — a checkout would discard unrelated
real edits living in the same file.

Usage
-----
    python scripts/guard-redability-gate.py               # every case
    python scripts/guard-redability-gate.py --gates-only  # only cases needing no service deps
    python scripts/guard-redability-gate.py --list        # what would run, and where
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "services" / "composition-service"
TRANS = ROOT / "services" / "translation-service"
KNOW = ROOT / "services" / "knowledge-service"
CHAT = ROOT / "services" / "chat-service"

#: A case whose guard is a plain script under `scripts/` needs nothing installed, so CI's
#: `lints` job can run it. A SUITE case needs something that job does not have — a service's
#: Python dependencies, or the Go toolchain — so it runs locally and in any job that provides
#: them. The distinction is printed, never silently applied: a sweep that quietly ran 4 of 13
#: and said "all guards red-able" would be the exact defect this file is about.
GATE = "gate"
SUITE = "suite"   # needs a service's deps or another language's toolchain


def append(text):
    return ("append", text)


def create(text):
    return ("create", text)


def replace(old, new, count=1):
    return ("replace", (old, new, count))


#: (name, tier, target(s), mutation, guard argv, guard cwd)
CASES = [
    ("S6 critic — an EIGHTH hand-rolled copy of the distinct rule", SUITE,
     COMP / "app" / "engine" / "select.py",
     append("\n\ndef _redability_probe(critic_ref, drafter_ref):\n"
            "    return str(critic_ref) != str(drafter_ref)\n"),
     [sys.executable, "-m", "pytest", "tests/unit/test_critic_policy.py", "-q",
      "-p", "no:cacheprovider", "-k", "re_inlines"], COMP),

    ("S3 findings — a raw skip_reason string outside the enum", SUITE,
     COMP / "app" / "engine" / "plan_heal.py",
     append('\n\ndef _redability_probe(f):\n    f.skip_reason = "not_locatd"\n'),
     [sys.executable, "-m", "pytest", "tests/unit/test_finding_vocabulary.py", "-q",
      "-p", "no:cacheprovider"], COMP),

    ("S5 heal — a module quietly RUNS a stage it declared SKIPPED", SUITE,
     COMP / "app" / "engine" / "plan_heal.py",
     append("\n\ndef _redability_probe(t):\n    return _snap_to_sentence(t)\n"),
     [sys.executable, "-m", "pytest", "tests/unit/test_heal_protocol.py", "-q",
      "-p", "no:cacheprovider"], COMP),

    ("S7 budget — a caller re-introduces an int max_tokens literal", SUITE,
     COMP / "app" / "engine" / "select.py",
     append("\n\ndef _redability_probe(c):\n    return c.chat(max_tokens=4242)\n"),
     [sys.executable, "-m", "pytest", "tests/unit/test_llm_budget_registry.py", "-q",
      "-p", "no:cacheprovider", "-k", "re_introduces"], COMP),

    ("S7 budget — signal_inert=True on a row that DOES move", SUITE,
     COMP / "app" / "llm_budget.py",
     replace('"judge_prose": CallProfile(OutputKind.VERDICT, 1536, 1536,',
             '"judge_prose": CallProfile(OutputKind.VERDICT, 1536, 1536, signal_inert=True,'),
     [sys.executable, "-m", "pytest", "tests/unit/test_llm_budget_registry.py", "-q",
      "-p", "no:cacheprovider", "-k", "signal_inert or no_inert_row"], COMP),

    ("S7 gate — the same inert claim, seen by the REPO gate", GATE,
     COMP / "app" / "llm_budget.py",
     replace('"judge_prose": CallProfile(OutputKind.VERDICT, 1536, 1536,',
             '"judge_prose": CallProfile(OutputKind.VERDICT, 1536, 1536, signal_inert=True,'),
     [sys.executable, "scripts/llm-budget-ssot-gate.py"], ROOT),

    ("S7 gate — an LLM call site with its budget stripped", GATE,
     COMP / "app" / "engine" / "cast_plan.py",
     replace('"max_tokens": max_tokens, **no_thinking_fields(),', "**no_thinking_fields(),"),
     [sys.executable, "scripts/llm-budget-ssot-gate.py"], ROOT),

    ("S4 injection — a translation worker stops scanning imported book text", GATE,
     TRANS / "app" / "workers" / "session_translator.py",
     replace("""    injection = scan_untrusted_source(
        chapter_text, where=f"chapter_translation:{chapter_translation_id}",
    )""", "    injection = None"),
     [sys.executable, "scripts/injection-coverage-lint.py"], ROOT),

    ("S4 injection — a real subject module loses its sanitizer", GATE,
     COMP / "app" / "engine" / "cowrite.py",
     replace("sanitize_", "xanitize_", count=-1),
     [sys.executable, "scripts/injection-coverage-lint.py"], ROOT),

    ("DoD-1 Go — the mirror invents a status the contract does not carry", SUITE,
     ROOT / "services" / "glossary-service" / "internal" / "guardstatus" / "guardstatus.go",
     replace('\tDegraded Status = "degraded"',
             '\tDegraded Status = "degraded"\n\tPartial Status = "partial"'),
     ["go", "test", "./internal/guardstatus/", "-count=1"],
     ROOT / "services" / "glossary-service"),

    ("S9 guard-SDK — a THIRD service adopts GuardReport", GATE,
     [TRANS / "app" / "_redability_probe.py", KNOW / "app" / "_redability_probe.py"],
     create('"""probe."""\nfrom typing import Any\n\n'
            "GuardReport: Any = None\nCheckStatus: Any = None\n"),
     [sys.executable, "scripts/guard-sdk-entry-gate.py"], ROOT),

    ("S11 context-trace — a closed-set value added on ONE side", SUITE,
     ROOT / "sdks" / "python" / "loreweave_context" / "trace.py",
     replace('"T5", "T6")', '"T5", "T6", "T7")'),
     [sys.executable, "-m", "pytest", "tests/test_context_trace_contract.py", "-q",
      "-p", "no:cacheprovider"], CHAT),

    ("S1 composition — an SSE stream stops declaring that no guard ran", SUITE,
     COMP / "app" / "routers" / "engine.py",
     replace('''                      "selection_edit": True,
                      # S1/DoD-1 — see the co-write stream: declared, not silent.
                      "canon": unguarded_envelope(
                          "the selection-edit stream does not run the canon guard: it rewrites a span the author picked, in-place and interactively. Approve the scene to have the whole passage checked.")}''',
             '                      "selection_edit": True}'),
     [sys.executable, "-m", "pytest", "tests/unit/test_unguarded_declaration.py", "-q",
      "-p", "no:cacheprovider"], COMP),

    ("S6 critic — two rows for ONE model stop being caught", SUITE,
     COMP / "app" / "engine" / "critic_policy.py",
     replace("    if critic_identity == drafter_identity:",
             "    if False and critic_identity == drafter_identity:"),
     [sys.executable, "-m", "pytest", "tests/unit/test_critic_policy.py", "-q",
      "-p", "no:cacheprovider"], COMP),

    ("S1 tilemap — the engine's own default claims a model wrote it", SUITE,
     ROOT / "services" / "tilemap-service" / "src" / "harness" / "l4_validate.rs",
     replace("        source: Provenance::CanonicalDefault,",
             "        source: Provenance::Llm,"),
     ["cargo", "test", "--test", "l4_mock"], ROOT / "services" / "tilemap-service"),

    ("AUDIT — a SIXTH guard signal is emitted with nothing acting on it", GATE,
     ROOT / "contracts" / "guard-signals.yaml",
     replace("  - id: eval.exclusion_unverified",
             "  - id: probe.sixth_unconsumed\n    field: exclusion_unverified\n    emitter:\n      file: sdks/python/loreweave_eval/calibration.py\n    unconsumed: a sixth, injected by the red-ability gate\n\n  - id: eval.exclusion_unverified"),
     [sys.executable, "scripts/guard-signal-consumption-gate.py"], ROOT),

    # The widening that made this necessary: `_helper_params_by_call` binds a private helper's
    # budget param from its callers. The gate's own source names the hazard — widening the
    # detector is how a ratchet stops meaning anything — so the case is the exact shape the
    # earlier tightening protected: ONE caller of an otherwise-attributed helper passing a flat
    # number. If the binding ever swallows that, this reds.
    ("DoD-3 budget — one literal caller no longer defeats an attributed helper", GATE,
     ROOT / "services" / "composition-service" / "app" / "engine" / "promise_audit.py",
     replace("system=system, user=user, max_tokens=max_tokens, trace_id=trace_id,\n"
             "                          tag=\"promise_extract\", cancel_check=cancel_check)",
             "system=system, user=user, max_tokens=400, trace_id=trace_id,\n"
             "                          tag=\"promise_extract\", cancel_check=cancel_check)"),
     [sys.executable, "scripts/llm-budget-ssot-gate.py"], ROOT),

    ("S1 generation-paths — a row claims `guarded` with a coverage field the file lacks", GATE,
     ROOT / "contracts" / "generation-paths.yaml",
     replace("coverage_field: kg_status", "coverage_field: kg_status_that_does_not_exist"),
     [sys.executable, "scripts/generation-guard-gate.py"], ROOT),

    ("S1 glossary — an outage and a clean sweep collapse back into one answer", SUITE,
     ROOT / "services" / "glossary-service" / "internal" / "api" / "wiki_staleness.go",
     replace("\t\tif !ok {\n\t\t\tunchecked++\n\t\t\tcontinue\n\t\t}\n\t\tif cur == a.storedHash {",
             "\t\tif !ok || cur == a.storedHash {"),
     ["go", "test", "./internal/api/", "-run", "TestSweepKgDrift", "-count=1"],
     ROOT / "services" / "glossary-service"),

    ("S7 translation — an inert MIRROR row that stops being inert", SUITE,
     TRANS / "app" / "llm_budget.py",
     replace('"translate_chunk": CallProfile(OutputKind.MIRROR, signal_inert=True)',
             '"translate_chunk": CallProfile(OutputKind.VERDICT, 512, 256, '
             'signal_inert=True, why="probe")'),
     [sys.executable, "-m", "pytest", "tests/test_llm_budget_registry.py", "-q",
      "-p", "no:cacheprovider"], TRANS),
]


#: Cases whose guard is itself gated on a live dependency. Without the variable the suite
#: SKIPS, so the guard is green before AND after the injection — which this file would
#: otherwise report as an inert guard. That is a false accusation, and a false accusation
#: from a gate is how the gate gets switched off. Named here so an absent dependency is
#: reported as NOT RUN, which is the honest answer and is never a pass.
#:
#: Keyed by the case NAME, and that coupling is checked below: a renamed case would silently
#: shed its requirement and go straight back to being falsely accused.
REQUIRES_ENV = {
    "S1 glossary — an outage and a clean sweep collapse back into one answer":
        "GLOSSARY_TEST_DB_URL",
}

#: The floor on cases that must actually RUN, per mode. MEASURED (full 18, gates-only 7) with
#: headroom, so adding or retiering a case does not red while a COLLAPSE does.
#:
#: This exists because of a defect found by auditing this file: with every case skipped it
#: printed
#:
#:     guard-redability-gate: PASS — 0/0 guard(s) proved RED-ABLE
#:
#: and exited 0. A gate that passes having verified nothing, inside the gate written to catch
#: exactly that — the same shape as the 0x08 bug it was built for. `--gates-only` runs in CI,
#: so a future edit that retiers those cases to SUITE would have left CI green forever.
MIN_PROVED = {"full": 12, "gates-only": 5}


def _run(argv, cwd):
    r = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def _mutate(target: Path, op: str, payload) -> str | None:
    """Apply the injection. Returns an error string when the anchor is gone."""
    if op == "append":
        target.write_text(target.read_text(encoding="utf-8") + payload, encoding="utf-8")
    elif op == "create":
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload, encoding="utf-8")
    elif op == "replace":
        old, new, count = payload
        # `newline=""` + an explicit unwrap, because this repo's working tree is CRLF and a
        # multi-line anchor written with `\n` silently matches NOTHING there. That failure
        # mode is indistinguishable from an anchor that genuinely moved, so it would surface
        # as ANCHOR-GONE — a case reporting that it tested nothing, for a reason that has
        # nothing to do with the guard. Measured the first time a case used a multi-line
        # anchor. Restore is still from the SAVED BYTES, so the round trip is lossless.
        src = target.read_text(encoding="utf-8").replace("\r\n", "\n")
        if old not in src:
            # NOT a pass. An anchor that has moved means this case is no longer injecting the
            # violation it names, and a sweep that skipped it would report full coverage while
            # testing nothing — the failure mode the whole file exists to refuse.
            return f"anchor gone from {target.name}: {old[:60]!r}"
        target.write_text(src.replace(old, new) if count == -1
                          else src.replace(old, new, count), encoding="utf-8")
    return None


def run_case(case) -> tuple[str, str, str]:
    name, _tier, targets, (op, payload), argv, cwd = case
    need = REQUIRES_ENV.get(name)
    if need and not os.environ.get(need):
        return name, "NO-ENV", f"needs {need} — the suite would SKIP, proving nothing"
    if isinstance(targets, Path):
        targets = [targets]
    saved = [(t, t.read_bytes() if t.exists() else None) for t in targets]

    base_rc, base_out = _run(argv, cwd)
    if base_rc != 0:
        tail = (base_out.strip().splitlines() or [""])[-1]
        return name, "BASELINE-RED", f"already failing before injection: {tail[:90]}"

    err = None
    try:
        for target in targets:
            err = _mutate(target, op, payload)
            if err:
                break
        rc, out = (0, "") if err else _run(argv, cwd)
    finally:
        for target, original in saved:
            if original is not None:
                target.write_bytes(original)
                assert hashlib.sha256(target.read_bytes()).hexdigest() == \
                    hashlib.sha256(original).hexdigest(), f"RESTORE FAILED for {target}"
            elif target.exists():
                target.unlink()

    if err:
        return name, "ANCHOR-GONE", err
    tail = ([ln for ln in out.strip().splitlines() if ln.strip()] or [""])[-1]
    return name, ("RED" if rc != 0 else "STILL-GREEN"), tail[:90]


def self_test() -> int:
    """Prove this gate can tell a guard that FIRES from one that does not.

    Every case here asserts `verdict == "RED"`, which is satisfied just as loudly by a
    `run_case` hardwired to return "RED" — the check-that-cannot-fail shape this whole file
    exists to refuse, and it would be indefensible to ship it inside this file of all files.

    So both directions are driven against throwaway guards whose behaviour is known by
    construction, plus the third outcome that must never be silently treated as a pass: a case
    whose anchor has moved is testing nothing, and must say so rather than count as covered.

    Deliberately free of service dependencies, so it runs in the same CI job as `--gates-only`.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        target = tmp / "subject.py"
        target.write_text("CLEAN = 1\n", encoding="utf-8")

        reacting = tmp / "reacting_guard.py"
        reacting.write_text(
            "import sys, pathlib\n"
            "src = pathlib.Path(sys.argv[1]).read_text(encoding='utf-8')\n"
            "sys.exit(1 if 'VIOLATION' in src else 0)\n", encoding="utf-8")
        blind = tmp / "blind_guard.py"
        blind.write_text("import sys\nsys.exit(0)\n", encoding="utf-8")

        checks = [
            ("a guard that FIRES on the injected violation",
             [sys.executable, str(reacting), str(target)], replace("CLEAN", "VIOLATION"), "RED"),
            ("a guard that is BLIND to it (the 0x08 defect's shape)",
             [sys.executable, str(blind)], replace("CLEAN", "VIOLATION"), "STILL-GREEN"),
            ("a case whose anchor has MOVED (tests nothing, must not pass)",
             [sys.executable, str(reacting), str(target)],
             replace("A_STRING_THAT_IS_NOT_THERE", "X"), "ANCHOR-GONE"),
        ]
        for label, argv, mutation, expected in checks:
            _, verdict, detail = run_case((label, GATE, target, mutation, argv, tmp))
            if verdict != expected:
                print(f"[redability] SELFTEST FAIL — {label}: expected {expected}, "
                      f"got {verdict} ({detail})")
                return 1
            if target.read_text(encoding="utf-8") != "CLEAN = 1\n":
                print(f"[redability] SELFTEST FAIL — {label} did not restore the subject")
                return 1

    print("[redability] SELFTEST PASS — reports RED on a guard that fires, STILL-GREEN on a "
          "blind one, ANCHOR-GONE on a case that tests nothing; subject restored each time.")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    gates_only = "--gates-only" in sys.argv
    selected = [c for c in CASES if not gates_only or c[1] == GATE]
    skipped = len(CASES) - len(selected)

    # A stale REQUIRES_ENV key is a silent detach: the case it named runs unguarded, its suite
    # SKIPS for want of the dependency, and it is reported STILL-GREEN — the false accusation
    # the mapping exists to prevent, reintroduced by a rename. Checked, not trusted.
    names = {c[0] for c in CASES}
    orphans = sorted(set(REQUIRES_ENV) - names)
    if orphans:
        print("guard-redability-gate: FAIL — REQUIRES_ENV names case(s) that do not exist:\n")
        for o in orphans:
            print(f"   {o!r}")
        print("\n   A renamed case sheds its dependency requirement silently and is then")
        print("   falsely accused of being inert. Re-key the entry.")
        return 1

    if "--list" in sys.argv:
        for name, tier, targets, _, argv, cwd in CASES:
            t = targets if isinstance(targets, list) else [targets]
            print(f"[{tier:6}] {name}")
            print(f"          inject into: {', '.join(p.name for p in t)}")
            print(f"          then run   : {' '.join(argv[1:])}  (cwd={cwd.name})")
        return 0

    results = [run_case(c) for c in selected]
    width = max((len(n) for n, _, _ in results), default=1)
    no_env = [r for r in results if r[1] == "NO-ENV"]
    bad = [r for r in results if r[1] not in ("RED", "NO-ENV")]
    skipped += len(no_env)

    for name, verdict, detail in results:
        print(f"{name:<{width}}  {verdict}{'' if verdict == 'RED' else '   <<<'}")
        print(f"{'':<{width}}    {detail}")

    print()
    if bad:
        print(f"FAIL — {len(bad)} of {len(results)} guard(s) did not go red against a real "
              f"on-disk violation.")
        print("   A guard that cannot fail is worse than no guard: it reports coverage and")
        print("   silences review. Fix the guard, or fix the case if the anchor moved.")
        return 1

    proved = len(results) - len(no_env)
    mode = "gates-only" if gates_only else "full"
    floor = MIN_PROVED[mode]
    if proved < floor:
        # The defect this file exists to catch, found in this file: with every case skipped it
        # printed PASS 0/0 and exited 0 — a gate verifying nothing while reporting coverage.
        print(f"guard-redability-gate: FAIL — only {proved} case(s) actually ran in {mode} "
              f"mode; the floor is {floor}.")
        print("   Cases were skipped or dropped, so this run proved almost nothing — and a")
        print("   PASS here is read as 'every guard is red-able'. Restore the cases, or")
        print("   provide the dependencies the NOT-RUN ones name.")
        return 1
    print(f"guard-redability-gate: PASS — {proved}/{proved} guard(s) proved "
          f"RED-ABLE against a real on-disk violation.")
    if skipped:
        # Named, because an unrun case that goes unmentioned is how a partial sweep starts
        # reading as a complete one — the same lie `llm-budget-ssot-gate` told about its own
        # unscanned surface until it was made to name it.
        print(f"  NOT RUN in this mode: {skipped} case(s) whose guard is a service/toolchain "
              f"suite (needs service deps or another toolchain).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
