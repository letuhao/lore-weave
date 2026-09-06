#!/usr/bin/env python3
"""db-ensure-bite-gate — the SHELL guards in `infra/db-ensure.sh`, each removed.

`W7-SHELL-UNCOVERED`: four round-3 fixes shipped with no test and no bite,
because `gate-bite-harness`'s targets are Go and Rust files. The row named the
worst of them plainly — *"the injection fix is the highest-severity change in
this run and is verified only by hand."* This is the mechanism that stops it
being verified only by hand.

WHAT THE INJECTION FIX IS
-------------------------
`db-ensure.sh` creates `loreweave_provisioner` with an operator-supplied
password, as the superuser `loreweave`. It used to interpolate that password
into the DDL, so

    LOREWEAVE_PROVISIONER_PASSWORD="x'; ALTER ROLE loreweave_provisioner SUPERUSER; --"

granted SUPERUSER to the very role `W7` created to STOP provisioning running as
superuser. The one environment variable `W7` introduced was an escalation path
around the one boundary `W7` introduced. The fix binds the password with psql's
`:'pw'` instead.

WHY THE LIVE LEG RUNS THE SCRIPT'S OWN TEXT
--------------------------------------------
The obvious live test — run `db-ensure.sh` — cannot exercise this path at all:
the `CREATE ROLE` is inside `if ! role exists`, and on any cluster that has ever
booted, the role exists. Dropping it first is not available either, because
`loreweave_provisioner` OWNS the provisioned reality databases and Postgres
refuses to drop a role with dependent objects. (Discovered by reasoning about it
before trying, which is the only reason this file is not a story about a broken
dev cluster.)

So the live leg **extracts the real pipeline out of `db-ensure.sh`** and runs it
with a throwaway role name. Extracted, not retyped: a hand-written copy of the
statement under test is a second thing to drift, and it would keep passing after
the real one regressed — which is precisely the class of defect this repo keeps
finding.

THE VERDICT VOCABULARY, per `BDR-56`
-------------------------------------
A leg that goes red for an unrelated reason is the failure mode that looks most
like success. Every leg here distinguishes `pass` / `fail` / `nobuild`
(the command died for its own reasons) / `missing` (the anchor is gone), and a
live leg that cannot reach a cluster reports `SKIP` loudly rather than passing.

    python scripts/db-ensure-bite-gate.py
    python scripts/db-ensure-bite-gate.py --self-test
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "infra" / "db-ensure.sh"

# The hostile value the fix exists to defeat, verbatim from the comment in
# `db-ensure.sh` that records the finding.
PAYLOAD_TMPL = "x'; ALTER ROLE {role} SUPERUSER; --"

CONTAINER = "infra-postgres-1"


def _load_lock():
    """Reuse the `O_EXCL` harness lock — this file mutates the tree too."""
    path = REPO / "scripts" / "dp-slice5b-bite-gate.py"
    if not path.exists():
        print(f"db-ensure-bite-gate: MISUSE — {path} is missing; it owns HarnessLock",
              file=sys.stderr)
        sys.exit(2)
    spec = importlib.util.spec_from_file_location("dp_slice5b_bite_gate", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


B = _load_lock()


def read() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def write(text: str) -> None:
    SCRIPT.write_text(text, encoding="utf-8", newline="")


# ── the live cluster ─────────────────────────────────────────────────────────


def psql(db: str, sql: str) -> tuple[int, str]:
    p = subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "psql", "-U", "loreweave", "-d", db, "-tAc", sql],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def cluster_reachable() -> bool:
    rc, _ = psql("postgres", "SELECT 1")
    return rc == 0


def extract_create_role_pipeline(text: str) -> str | None:
    """The real `printf … | psql …` block, lifted out of the script.

    Anchored on `CREATE ROLE $PROVISIONER_ROLE`, so if that statement is
    rewritten or moved the extraction returns `None` and the leg reports
    `missing` — never a silent pass on a block it could not find.
    """
    lines = text.replace("\r\n", "\n").split("\n")
    start = next((i for i, l in enumerate(lines) if l.strip().startswith("printf '%s\\n'")), None)
    if start is None:
        return None
    end = next((j for j in range(start, min(start + 12, len(lines)))
                if "|| echo" in lines[j]), None)
    if end is None:
        return None
    block = "\n".join(lines[start:end])
    if "CREATE ROLE $PROVISIONER_ROLE" not in block:
        return None
    # Drop the trailing backslash continuation left by cutting off the `|| echo`.
    return block.rstrip().rstrip("\\").rstrip()


def run_create_role(block: str, role: str, password: str) -> tuple[int, str]:
    """Execute the extracted pipeline inside the container, for a throwaway role."""
    script = (
        f"set -e\n"
        f"PROVISIONER_ROLE={role}\n"
        f"PROVISIONER_PASSWORD={shell_single_quote(password)}\n"
        f"{block}\n"
    )
    # BYTES, not text=True.
    #
    # On Windows, writing a `str` to a child's stdin goes through a
    # TextIOWrapper with `newline=None`, which translates every `\n` into
    # `\r\n`. bash then reads `PROVISIONER_ROLE=lw_bite_provisioner\r` and the
    # carriage return becomes part of the value — the first run failed with
    # `CREATE ROLE lw_bite_provisioner\r ... : command not found`. §0.6 already
    # records that heredocs eat backslashes on this platform; this is the same
    # family, one layer down, and it presented as `nobuild` rather than as a
    # wrong answer, which is the safe direction.
    p = subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "bash", "-s"],
        input=script.encode("utf-8"), capture_output=True,
    )
    out = (p.stdout or b"").decode("utf-8", "replace") + (p.stderr or b"").decode("utf-8", "replace")
    return p.returncode, out


def shell_single_quote(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


def drop_role(role: str) -> None:
    psql("postgres", f"DROP OWNED BY {role}")
    psql("postgres", f"DROP ROLE IF EXISTS {role}")


def role_is_superuser(role: str) -> bool | None:
    rc, out = psql("postgres", f"SELECT rolsuper FROM pg_roles WHERE rolname='{role}'")
    if rc != 0:
        return None
    v = out.strip()
    if v == "t":
        return True
    if v == "f":
        return False
    return None


# ── static legs ──────────────────────────────────────────────────────────────
#
# (label, the anchor that must be present, what removing it means)

STATIC_LEGS = [
    (
        # ANCHORED ON THE DDL, not on `:'pw'` alone.
        #
        # The first version used the bare `:'pw'`, and the bite scored the check
        # `NOT LOAD-BEARING`. The check was fine; the MUTATION was — `:'pw'`
        # first appears in the comment that EXPLAINS the fix, twenty lines above
        # the statement, so a first-occurrence replace edited prose and left the
        # code untouched. `BDR-56` exactly: a mutation that changes nothing
        # prints what a vacuous guard prints.
        "the password is BOUND with psql's :'pw', not interpolated",
        "PASSWORD :'pw' CREATEDB",
        "-v pw=\"$PROVISIONER_PASSWORD\"",
    ),
    (
        "the table-level SELECT is REVOKED before the column list is granted",
        "REVOKE SELECT ON reality_registry FROM $PROVISIONER_ROLE",
        "GRANT SELECT (reality_id, db_host, db_name, status) ON reality_registry",
    ),
    (
        "the script ASSERTS the role is not over-privileged before reporting healthy",
        "AND rolcreatedb AND NOT rolsuper AND NOT rolbypassrls",
        "FATAL: $PROVISIONER_ROLE is missing or over-privileged",
    ),
]


def static_arm() -> list[str]:
    """Both halves of each pair must be present.

    Deliberately a PAIR rather than one string: `NV-2`, the subject must be able
    to vary. A single-anchor check on `:'pw'` would keep passing if the binding
    survived while the `-v pw=` that supplies it was deleted, which is a psql
    error at runtime and a green check here.
    """
    text = read()
    problems = []
    for label, a, b in STATIC_LEGS:
        for anchor in (a, b):
            if anchor not in text:
                problems.append(f"{label}: anchor missing from db-ensure.sh — {anchor!r}")
    return problems


def bite_static(label: str, find: str, replace: str) -> bool:
    print(f"\n{'-' * 74}\nSTATIC BITE {label}")
    original = read()
    if find not in original:
        print(f"  x MISUSE — anchor not present: {find!r}")
        return False
    if static_arm():
        print("  x baseline is already failing; the bite would prove nothing")
        return False
    print("  baseline : pass")
    try:
        write(original.replace(find, replace, 1))
        problems = static_arm()
        if not problems:
            print("  x THE CHECK IS NOT LOAD-BEARING — anchor removed, still green")
            ok = False
        else:
            print(f"  red      : {problems[0][:150]}")
            ok = True
    finally:
        write(original)
    if read() != original:
        print("  x restore FAILED — the tree is not back")
        return False
    print("  restored : pass" if not static_arm() else "  x restored but still failing")
    return ok and not static_arm()


# ── the live leg ─────────────────────────────────────────────────────────────


def live_injection_leg() -> tuple[str, str]:
    """`(verdict, detail)` — verdict in pass / fail / skip / missing."""
    if not cluster_reachable():
        return "skip", f"no reachable Postgres in container {CONTAINER}"

    original = read()
    block = extract_create_role_pipeline(original)
    if block is None:
        return "missing", (
            "could not extract the `printf … | psql …` CREATE ROLE pipeline from "
            "db-ensure.sh — the statement moved, and this leg would silently test nothing"
        )

    role = "lw_bite_provisioner"
    payload = PAYLOAD_TMPL.format(role=role)

    # ── 1. THE FIX AS IT STANDS: a hostile password must not escalate.
    drop_role(role)
    try:
        rc, out = run_create_role(block, role, payload)
        if role_is_superuser(role) is None:
            return "nobuild", f"the role was not created at all (rc={rc}): {out[-300:]}"
        if role_is_superuser(role):
            return "fail", (
                "SHIPPED CODE IS VULNERABLE — a hostile LOREWEAVE_PROVISIONER_PASSWORD "
                "granted SUPERUSER to the provisioning role"
            )
        safe = "the bound form refused the payload: role created, rolsuper = false"
    finally:
        drop_role(role)

    # ── 2. THE BITE: undo the binding and the escalation must come back.
    #
    # This is the half that makes leg 1 evidence rather than a coincidence. If
    # the interpolated form ALSO fails to escalate, then something other than
    # the binding is stopping it and the comment in db-ensure.sh is wrong about
    # its own fix.
    # THE MUTATION IS IN MEMORY. `db-ensure.sh` is NOT written here, and that is
    # a correctness requirement rather than tidiness.
    #
    # `infra/docker-compose.yml:62` bind-mounts this file into the running
    # postgres container and line 66 executes it as the **healthcheck, every 5
    # seconds**. Writing it therefore has two live consequences, neither of them
    # hypothetical: `write_text` truncates before it writes, so a healthcheck
    # landing mid-write reads a syntax error and postgres is marked UNHEALTHY —
    # which cascades to every service with `depends_on: service_healthy`; and if
    # this harness is killed before its `finally`, the **interpolated,
    # vulnerable** form is what stays on disk and runs every five seconds.
    #
    # None of it buys anything. `extract_create_role_pipeline` takes a STRING,
    # so the mutated pipeline can be derived without the file ever changing, and
    # what is executed is the extracted text either way. Found by
    # `/review-impl`. The static legs below still write, but their window is a
    # single in-process check rather than several docker round trips.
    mutated = original.replace(
        "PASSWORD :'pw'", "PASSWORD '$PROVISIONER_PASSWORD'", 1
    )
    if mutated == original:
        return "missing", "could not un-bind the password; the `:'pw'` form is gone"
    block2 = extract_create_role_pipeline(mutated)
    if block2 is None:
        return "missing", "the mutated script no longer yields an extractable pipeline"
    try:
        drop_role(role)
        run_create_role(block2, role, payload)
        escalated = role_is_superuser(role)
    finally:
        drop_role(role)

    if read() != original:
        return "nobuild", "db-ensure.sh changed on disk during the live leg — it must not"
    if escalated is not True:
        return "fail", (
            f"{safe}; BUT the interpolated form did NOT escalate either "
            f"(rolsuper={escalated}). The binding is therefore not what is stopping the "
            f"injection, and db-ensure.sh's comment claims it is — the guard is not "
            f"load-bearing, or the payload no longer reaches the statement"
        )
    return "pass", (
        f"{safe}; and with the binding removed the SAME payload granted SUPERUSER — "
        f"so the binding is what is stopping it"
    )


def self_test() -> int:
    fails = []
    if not SCRIPT.is_file():
        fails.append(f"{SCRIPT} does not exist")
    else:
        text = read()
        if extract_create_role_pipeline(text) is None:
            fails.append("the CREATE ROLE pipeline could not be extracted from db-ensure.sh")
        if extract_create_role_pipeline("nothing here") is not None:
            fails.append("extraction returned a block for a file that has none")
        if static_arm():
            fails.append(f"static anchors already missing: {static_arm()}")
    if shell_single_quote("a'b") != "'a'\"'\"'b'":
        fails.append("shell_single_quote does not escape an embedded quote")
    if fails:
        for f in fails:
            print(f"db-ensure-bite-gate: SELFTEST FAIL — {f}")
        return 1
    print("db-ensure-bite-gate: SELFTEST PASS — the pipeline extracts, extraction refuses a "
          "file without one, every static anchor is present, and quoting is exact")
    return 0


def main() -> int:
    if "--self-test" in sys.argv or "--selftest" in sys.argv:
        return self_test()
    if self_test() != 0:
        return 2

    print("db-ensure-bite-gate — the shell guards in infra/db-ensure.sh, each removed\n")
    with B.HarnessLock():
        results = [bite_static(*leg) for leg in STATIC_LEGS]
        verdict, detail = live_injection_leg()

    print(f"\n{'=' * 74}")
    for (label, _, _), ok in zip(STATIC_LEGS, results):
        print(f"  {'ok' if ok else ' x'}  [static] {label}")

    live_ok = verdict == "pass"
    mark = {"pass": "ok", "skip": " ~", "fail": " x", "missing": " x", "nobuild": " x"}[verdict]
    print(f"  {mark}  [live]   the injection fix, proven by removing it")
    print(f"          -> {verdict.upper()}: {detail}")

    bitten = sum(1 for r in results if r) + (1 if live_ok else 0)
    total = len(STATIC_LEGS) + 1
    print(f"\n  bitten: {bitten}/{total}"
          + ("  (the live leg SKIPPED — this run proves less than a full one)"
             if verdict == "skip" else ""))

    if not all(results):
        print("\ndb-ensure-bite-gate: FAIL — a static guard was removed and nothing noticed.")
        return 1
    if verdict in ("fail", "missing", "nobuild"):
        print("\ndb-ensure-bite-gate: FAIL — the live injection leg did not bite.")
        return 1
    if verdict == "skip":
        # NOT a pass dressed as one: the skip is printed on its own line above,
        # and the count says 3/4. Exit 0 because a checkout without docker must
        # not fail CI on a leg it cannot run — the same call `gate-wiring-gate`
        # makes for NEEDS_STACK, taken here per-leg instead of per-file so the
        # static arms still run everywhere.
        print("\ndb-ensure-bite-gate: OK (static only) — the live leg needs a Postgres container.")
        return 0
    print("\ndb-ensure-bite-gate: OK — every guard is load-bearing, injection proven by removal.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
