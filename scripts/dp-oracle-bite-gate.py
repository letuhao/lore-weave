#!/usr/bin/env python3
"""dp-oracle-bite-gate — the `05_control_plane_spec.md` oracle, one side of
each doc/code pair broken at a time.

WHY THIS HARNESS AND NOT A GREEN TEST RUN
------------------------------------------
The four tests in `crates/dp-control-plane/tests/spec_oracle_cp.rs` passed on
their first run. `BDR-56` is precisely about that moment: **a bite mutation that
changes nothing prints exactly what a vacuous guard prints**, and three legs of
a sibling harness scored `THE GUARD IS NOT LOAD-BEARING` while being wrong about
the guard every time. A green oracle is a claim; a red one under a known
mutation is evidence.

Every leg here mutates **exactly one side** of a doc↔code pair and requires the
red to name **both** sides — because a rule that reds without saying what
disagreed with what sends the next reader hunting through twenty-six locked
files.

WHAT IS BITTEN, AND WHY EACH MUTATION WAS CHOSEN
-------------------------------------------------
* the TTL is set back to **15 minutes** — not an arbitrary wrong number, but
  the value that actually shipped (`BDR-52`), against a spec that says 5 in
  three places. If this leg does not red, the mechanism built for that incident
  would not have caught the incident.
* the doc is made to contradict **itself** — the signing-key rule states `2×`
  the lifetime as its own absolute figure, so the corpus can drift with no code
  change at all. That is the `FLOW-2` shape and it is the reason a doc↔doc arm
  exists.
* both registers get a row **added for something that is already built**. That
  arm is what stops a deferral register ageing into permanence, and it is the
  arm most likely to be quietly deleted by someone tidying a red.

MACHINERY imported from `dp-slice5b-bite-gate`, as `5c` and `5d` already do: the
read / restore / byte-identical / `O_EXCL` lock parts are solved there, and a
fourth copy would be a fourth thing to drift.

Exit 0 = every bite bit; 1 = one did not; 2 = misuse.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _load_5b():
    path = REPO / "scripts" / "dp-slice5b-bite-gate.py"
    if not path.exists():
        print(
            f"dp-oracle-bite-gate: MISUSE — {path} is missing; this harness reuses its "
            "read/restore/lock machinery",
            file=sys.stderr,
        )
        sys.exit(2)
    spec = importlib.util.spec_from_file_location("dp_slice5b_bite_gate", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


B = _load_5b()

DOC = REPO / "docs" / "03_planning" / "LLM_MMO_RPG" / "06_data_plane" / "05_control_plane_spec.md"
LIB = REPO / "crates" / "dp-control-plane" / "src" / "lib.rs"
TTL = REPO / "crates" / "meta-rs" / "src" / "control_plane.rs"
ORACLE = REPO / "crates" / "dp" / "tests" / "spec_oracle.rs"

SESSION = REPO / "crates" / "dp" / "src" / "session.rs"
MIG = REPO / "contracts" / "migrations" / "per_reality"
DOC_SDK = REPO / "docs" / "03_planning" / "LLM_MMO_RPG" / "06_data_plane" / "04d_capability_and_lifecycle.md"
DOC_CH = REPO / "docs" / "03_planning" / "LLM_MMO_RPG" / "06_data_plane" / "13_channel_ordering_and_writer.md"
DOC_LIFE = REPO / "docs" / "03_planning" / "LLM_MMO_RPG" / "06_data_plane" / "17_channel_lifecycle.md"
SDK_ORACLE = REPO / "crates" / "dp" / "tests" / "spec_oracle_sdk.rs"
CH_ORACLE = REPO / "crates" / "dp" / "tests" / "spec_oracle_channels.rs"

# (package, integration-test target) per leg; the CP oracle is the default.
CP = ("dp-control-plane", "spec_oracle_cp")
SDK = ("dp", "spec_oracle_sdk")
CH = ("dp", "spec_oracle_channels")


def cargo_outcome(test_name: str, where: tuple[str, str] = CP) -> tuple[str, str]:
    """Run ONE test of one oracle. Four-way verdict, per `BDR-56`.

    `nobuild` and `missing` are distinguished from `fail` deliberately: a red
    caused by a broken build or by a test that no longer runs is the failure
    mode that looks most like success.
    """
    pkg, target = where
    p = subprocess.run(
        [
            "cargo", "test", "-p", pkg, "--test", target,
            test_name, "--", "--exact",
        ],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    out = (p.stdout or "") + (p.stderr or "")
    if "error: could not compile" in out or "error[E" in out:
        return "nobuild", out
    if "running 0 tests" in out:
        return "missing", out
    if "test result: ok" in out:
        return "pass", out
    if "test result: FAILED" in out:
        return "fail", out
    return "nobuild", out


def gate_outcome(_ignored: str, _where: tuple[str, str] = CP) -> tuple[str, str]:
    """The coverage ratchet's verdict, in the same four-way vocabulary."""
    p = subprocess.run(
        [sys.executable, "scripts/dp-oracle-coverage-gate.py"],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    out = (p.stdout or "") + (p.stderr or "")
    if p.returncode == 0:
        return "pass", out
    if p.returncode == 2 or "SELFTEST FAIL" in out:
        # A broken self-test or a missing baseline is this harness's `nobuild`:
        # red for a reason that is not the guarded relationship.
        return "nobuild", out
    return "fail", out


def _both_sides(out: str, needles: tuple[str, ...]) -> list[str]:
    """Which required substrings the failure message did NOT contain."""
    return [n for n in needles if n not in out]


def bite(leg: dict) -> bool:
    label = leg["label"]
    path: Path = leg["path"]
    witness = leg["witness"]
    where = leg.get("where", CP)
    base = gate_outcome if leg.get("kind") == "gate" else cargo_outcome

    def runner(name: str) -> tuple[str, str]:
        return base(name, where)

    print(f"\n{'=' * 74}\nBITE {label}\n{'=' * 74}")
    print(f"  mutating : {path.relative_to(REPO)}")
    print(f"  witness  : {witness}")

    before, out = runner(witness)
    print(f"  baseline : {before}  (expected pass)")
    if before != "pass":
        print(f"  x {label}: the witness does not pass BEFORE the mutation")
        print(out[-1500:])
        return False

    original = B.read_txt(path)
    if leg["find"] not in original:
        print(f"  x {label}: MISUSE — anchor not found in {path.name}: {leg['find'][:70]!r}")
        return False
    mutated = original.replace(leg["find"], leg["replace"], 1)
    if mutated == original:
        print(f"  x {label}: MISUSE — mutation produced identical text")
        return False

    ok = False
    try:
        B.write_txt(path, mutated)
        after, out = runner(witness)
        print(f"  mutated  : one side changed -> {after}  (expected fail)")
        if after == "nobuild":
            print(f"  x {label}: the mutation broke the BUILD — the red proves nothing")
        elif after == "missing":
            print(f"  x {label}: the witness did not RUN under mutation")
        elif after == "pass":
            print(f"  x {label}: THE GUARD IS NOT LOAD-BEARING — one side changed, still green")
        else:
            missing = _both_sides(out, leg["names"])
            if missing:
                # A red that does not name what disagreed with what is a red the
                # next reader cannot act on. Scored as a failure of the LEG, not
                # of the mutation.
                print(f"  x {label}: red, but the message never names {missing}")
            else:
                line = next(
                    (l.strip() for l in out.splitlines() if "assertion" in l or "panicked" in l),
                    B._first_failure_line(out),
                )
                print(f"  red      : {line[:200]}")
                print(f"  names    : both sides present -> {list(leg['names'])}")
                ok = True
    finally:
        B.write_txt(path, original)

    if not B.restored_byte_identical(path, original, label):
        return False

    after_restore, _ = runner(witness)
    print(f"  restored : {after_restore}  (expected pass)")
    if after_restore != "pass":
        print(f"  x {label}: the witness does not pass after restore — the tree is not back")
        return False
    return ok


LEGS: list[dict] = [
    # ── DP-C8, the TTL. The exact BDR-52 regression. ─────────────────────────
    {
        "label": "[DP-C8] the TTL const set back to the 15 minutes that shipped",
        "path": TTL,
        "find": "pub const DEFAULT_CAPABILITY_TTL_MS: u64 = 5 * 60 * 1000;",
        "replace": "pub const DEFAULT_CAPABILITY_TTL_MS: u64 = 15 * 60 * 1000;",
        "witness": "the_capability_ttl_matches_dp_c8",
        "names": ("5 min", "900000"),
    },
    {
        "label": "[DP-C8] the doc's own two statements of the lifetime disagree",
        "path": DOC,
        "find": "Short expiry (5 min) bounds blast radius",
        "replace": "Short expiry (7 min) bounds blast radius",
        "witness": "the_capability_ttl_matches_dp_c8",
        "names": ("7 min", "5 min"),
    },
    {
        "label": "[DP-C8] the signing-key window stops being 2x the lifetime (doc vs doc)",
        "path": DOC,
        "find": '2× the max capability lifetime (10 minutes)',
        "replace": '2× the max capability lifetime (20 minutes)',
        "witness": "the_capability_ttl_matches_dp_c8",
        "names": ("20 min", "5 min"),
    },
    # ── DP-C3, the RPC surface. ──────────────────────────────────────────────
    {
        "label": "[DP-C3] the doc drops an RPC the contract still serves",
        "path": DOC,
        "find": "  rpc Health (Empty) returns (HealthReport);\n",
        "replace": "",
        "witness": "the_grpc_surface_matches_dp_c3_or_declares_why_not",
        "names": ("`Health`", "dp_control_plane.proto"),
    },
    {
        "label": "[DP-C3] a deferred RPC loses its register row",
        "path": LIB,
        "find": '    ("PauseChannel", "no pause state and no ack path (DP-Ch34)"),\n',
        "replace": "",
        "witness": "the_grpc_surface_matches_dp_c3_or_declares_why_not",
        "names": ("`PauseChannel`", "DEFERRED_RPCS"),
    },
    {
        "label": "[DP-C3] a register row that outlived its subject (the shrink arm)",
        "path": LIB,
        "find": '    ("GetChannelTree",',
        "replace": '    ("Health", "already served — this row is the bite"),\n    ("GetChannelTree",',
        "witness": "the_grpc_surface_matches_dp_c3_or_declares_why_not",
        "names": ("`Health`", "DEFERRED_RPCS"),
    },
    # ── DP-C2, the storage tables. ───────────────────────────────────────────
    {
        "label": "[DP-C2] a doc-declared table with no migration and no register row",
        "path": LIB,
        "find": '    ("capability_signing_keys", "explicitly NOT BUILT',
        "replace": '    ("_bitten_away", "explicitly NOT BUILT',
        "witness": "cp_storage_tables_match_dp_c2_or_declare_why_not",
        "names": ("`capability_signing_keys`", "CP_TABLES_WITHOUT_A_MIGRATION"),
    },
    {
        "label": "[DP-C2] a register row for a table that DOES have a migration (the shrink arm)",
        "path": LIB,
        "find": '    ("tier_policy",',
        "replace": '    ("reality_registry", "already built — this row is the bite"),\n    ("tier_policy",',
        "witness": "cp_storage_tables_match_dp_c2_or_declare_why_not",
        "names": ("`reality_registry`", "CP_TABLES_WITHOUT_A_MIGRATION"),
    },
    {
        "label": "[DP-C2] the doc renames a table out from under its register row",
        "path": DOC,
        "find": "- `deploy_cohort` table",
        "replace": "- `deploy_cohorts` table",
        "witness": "cp_storage_tables_match_dp_c2_or_declare_why_not",
        "names": ("`deploy_cohorts`", "`deploy_cohort`"),
    },
    # ── DP-K9 / DP-K11 (04d_capability_and_lifecycle.md). ────────────────────
    {
        "label": "[DP-K9] the doc changes the refresh lead the SDK is built to",
        "path": DOC_SDK,
        "find": "refresh proactively 60s before expiry",
        "replace": "refresh proactively 30s before expiry",
        "where": SDK,
        "witness": "the_refresh_lead_matches_dp_k9",
        "names": ("30s", "60000"),
    },
    {
        # The constant's own docstring QUOTES the spec sentence beside it, so
        # before this rule existed the two copies here agreed with each other
        # and with nothing else. This changes the constant and leaves both
        # copies of the sentence untouched — the exact drift that was invisible.
        "label": "[DP-K9] the constant moves and the two copies of the sentence do not",
        "path": SESSION,
        "find": "pub const REFRESH_LEAD_MS: Millis = 60_000;",
        "replace": "pub const REFRESH_LEAD_MS: Millis = 30_000;",
        "where": SDK,
        "witness": "the_refresh_lead_matches_dp_k9",
        "names": ("60s", "30000"),
    },
    {
        "label": "[DP-K11] a specified-but-unwritten lint loses its register row",
        "path": SDK_ORACLE,
        "find": '        "dp::forbid_manual_cache_key",',
        "replace": '        "dp::forbid_bitten_away",',
        "where": SDK,
        "witness": "the_dp_clippy_lint_set_matches_dp_k11_or_declares_why_not",
        "names": ("dp::forbid_manual_cache_key", "DEFERRED_LINTS"),
    },
    {
        "label": "[DP-K11] a register row for a lint that IS written (the shrink arm)",
        "path": SDK_ORACLE,
        "find": '        "dp::missing_instrumentation",',
        "replace": '        "dp::forbid_raw_kernel_client",',
        "where": SDK,
        "witness": "the_dp_clippy_lint_set_matches_dp_k11_or_declares_why_not",
        "names": ("dp::forbid_raw_kernel_client", "DEFERRED_LINTS"),
    },
    # ── DP-Ch11 (13_channel_ordering_and_writer.md). ─────────────────────────
    {
        "label": "[DP-Ch11] the unbuilt column loses its register row",
        "path": CH_ORACLE,
        "find": '    "turn_number",',
        "replace": '    "turn_number_bitten",',
        "where": CH,
        "witness": "the_event_log_columns_match_dp_ch11_or_declare_why_not",
        "names": ("events.turn_number", "DEFERRED_EVENT_COLUMNS"),
    },
    {
        "label": "[DP-Ch11] a register row for a column the migration DOES add (the shrink arm)",
        "path": CH_ORACLE,
        "find": 'const DEFERRED_EVENT_COLUMNS: &[(&str, &str)] = &[(',
        "replace": 'const DEFERRED_EVENT_COLUMNS: &[(&str, &str)] = &[\n    ("channel_id", "already added — this row is the bite"),\n    (',
        "where": CH,
        "witness": "the_event_log_columns_match_dp_ch11_or_declare_why_not",
        "names": ("`channel_id`", "DEFERRED_EVENT_COLUMNS"),
    },
    {
        # The key's ORDER is the contract, not just its membership: REC-99b
        # moved DP-A15's per-channel gapless order onto this key precisely
        # because `events` is partitioned and could not carry it.
        "label": "[DP-Ch11] the uniqueness triple is reordered in the migration",
        "path": MIG / "0014_channel_ordering.up.sql",
        "find": "    PRIMARY KEY (reality_id, channel_id, channel_event_id)\n);",
        "replace": "    PRIMARY KEY (channel_id, reality_id, channel_event_id)\n);",
        "where": CH,
        "witness": "the_channel_event_index_key_matches_dp_ch11",
        "names": ("0014_channel_ordering.up.sql", "13_channel_ordering_and_writer.md"),
    },
    # ── DP-Ch31 (17_channel_lifecycle.md). ───────────────────────────────────
    {
        "label": "[DP-Ch31] the CHECK admits a state the state machine does not define",
        "path": MIG / "0019_channels.up.sql",
        "find": "CHECK (lifecycle IN ('active', 'dormant', 'dissolved'))",
        "replace": "CHECK (lifecycle IN ('active', 'dormant', 'dissolved', 'frozen'))",
        "where": CH,
        "witness": "the_channel_lifecycle_states_match_dp_ch31",
        "names": ("frozen", "channels_lifecycle_known"),
    },
    {
        # Doc-to-doc. No code changes at all, so no document-to-code rule could
        # ever see this — `FLOW-2`'s shape, which the corpus is measured to
        # contain.
        "label": "[DP-Ch31] a transition names a state the state machine does not define",
        "path": DOC_LIFE,
        "find": "| Dissolved | (any) | — |",
        "replace": "| Frozen | Active | admin |\n| Dissolved | (any) | — |",
        "where": CH,
        "witness": "every_dp_ch31_transition_names_a_state_dp_ch31_defines",
        "names": ("frozen", "dormant"),
    },
    # ── the coverage ratchet itself. ─────────────────────────────────────────
    {
        # The ratchet's whole claim is that coverage cannot go backwards
        # SILENTLY. This removes the single call site of a helper that reads
        # `04b_read_write.md`, which leaves the crate compiling and the entire
        # `dp` oracle suite GREEN — measured, 15 passed — while a document stops
        # being read. Nothing but this gate sees it.
        "kind": "gate",
        "label": "[ratchet] a document silently stops being read (suite stays green)",
        "path": ORACLE,
        "find": "    check_deferred_write_forms();\n",
        "replace": "",
        "witness": "scripts/dp-oracle-coverage-gate.py",
        "names": ("COVERAGE LOST", "04b_read_write.md"),
    },
]


def main() -> int:
    print("dp-oracle-bite-gate — one side of each doc/code pair, broken\n")
    with B.HarnessLock():
        results = [bite(leg) for leg in LEGS]

    print(f"\n{'=' * 74}")
    bitten = sum(1 for r in results if r)
    for leg, ok in zip(LEGS, results):
        print(f"  {'ok' if ok else ' x'}  {leg['label']}")
    print(f"\n  bitten: {bitten}/{len(LEGS)}")

    if bitten != len(LEGS):
        print("\ndp-oracle-bite-gate: FAIL — a side was changed and nothing noticed.")
        return 1
    print(
        "\ndp-oracle-bite-gate: OK — every rule reds on a one-sided change, and every "
        "red names both sides."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
