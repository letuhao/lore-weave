#!/usr/bin/env python3
"""`rsa` must not be in the Rust BUILD graph — the fact that licenses the audit ignore.

    python scripts/rsa-out-of-build-gate.py
    python scripts/rsa-out-of-build-gate.py --self-test

WHY THIS EXISTS
---------------
`rsa` carries RUSTSEC-2023-0071 (Marvin Attack — key recovery through a timing sidechannel) and
**there is no fixed version**: `cargo audit` says *"No fixed upgrade is available!"*. On
2026-09-13 the workspace switched `jsonwebtoken` from the `rust_crypto` backend to `aws_lc_rs`,
which removes `rsa` from the compiled binary — `rust_crypto` is one bundled feature that pulls
`rsa` in with it, and there is no way to take the feature set without it.

**That fixed the binary and did NOT fix the audit.** `cargo audit` scans `Cargo.lock`, not the
build graph, and `rsa` is still in the lock because `sqlx`'s lock entry unconditionally lists
`sqlx-mysql` — an OPTIONAL dependency this workspace never enables (sqlx is `default-features =
false` with `postgres` only, and no `.rs` file mentions mysql). Cargo records optional
dependencies in the lockfile regardless, so the residue cannot be removed without patching sqlx.

So `.cargo/audit.toml` ignores RUSTSEC-2023-0071. **An ignore is a claim, and this gate is what
makes it a checked one.** Without it, someone restoring `features = ["rust_crypto"]` would put
the vulnerable code back into two request-path services and the audit would stay green, because
the ignore was written for a condition that had silently stopped being true.

WHAT IT CHECKS
--------------
`cargo tree -e normal -i rsa` — the *normal* (non-dev, non-build) dependency graph, resolved with
this workspace's actual features. `rsa` absent means no shipped binary contains it. That is a
different and stronger question than "is it in the lockfile", and it is the one the ignore rests
on.

Exit 0 = rsa is out of the build; 1 = it is back; 2 = misuse / self-test failure / cargo missing.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CRATE = "rsa"
ADVISORY = "RUSTSEC-2023-0071"

#: `cargo tree -i` prints this, on stderr, when the crate is not in the graph. It exits 0 either
#: way — which is the trap this gate would otherwise fall into, and did once during development:
#: a check written against the exit code passes whether the crate is there or not.
ABSENT_MARKER = "nothing to print"


def tree_output(crate: str = CRATE, timeout: int = 600) -> tuple[bool, str]:
    """(present_in_build_graph, combined_output). Raises RuntimeError if cargo cannot answer."""
    if shutil.which("cargo") is None:
        raise RuntimeError("cargo is not on PATH, so the build graph cannot be read")
    r = subprocess.run(["cargo", "tree", "-e", "normal", "-i", crate],
                       cwd=REPO, capture_output=True, text=True, timeout=timeout,
                       stdin=subprocess.DEVNULL)
    out = (r.stdout or "") + (r.stderr or "")
    if ABSENT_MARKER in out:
        return False, out
    # A real tree starts with the crate's own line. Anything else -- a resolver error, a network
    # failure -- is NOT evidence of absence, and must not be spelled as one.
    if f"{crate} v" not in out:
        raise RuntimeError(
            f"cargo tree answered neither a tree nor {ABSENT_MARKER!r} (exit {r.returncode}). "
            f"This is a READ failure, not a finding:\n{out.strip()[:400]}")
    return True, out


def self_test() -> int:
    """The parse, both ways, without needing the graph to actually change."""
    fails: list[str] = []
    # The absent marker must be recognised even though cargo exits 0 for it.
    if ABSENT_MARKER not in "warning: nothing to print.":
        fails.append("the absent marker no longer matches cargo's wording")
    # A crate that IS present must be readable as present.
    try:
        present, out = tree_output("serde")
        if not present:
            fails.append("`serde` read as ABSENT from the build graph, which cannot be right — "
                         "the presence arm is broken, so this gate would pass over a restored rsa")
    except RuntimeError as e:
        fails.append(f"could not read the build graph at all: {e}")
    if fails:
        print("rsa-out-of-build-gate SELF-TEST FAILED:")
        for f in fails:
            print(f"  - {f}")
        return 2
    print("rsa-out-of-build-gate: self-test OK — recognises cargo's absent marker AND reads a "
          "present crate as present (so the check can go red at all)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()

    try:
        present, out = tree_output()
    except RuntimeError as e:
        print(f"rsa-out-of-build-gate: CANNOT DETERMINE — {e}")
        return 2

    if present:
        print(f"rsa-out-of-build-gate: FAIL — `{CRATE}` is back in the Rust build graph.\n")
        for line in out.splitlines()[:12]:
            if line.strip():
                print(f"  {line}")
        print(f"\n  {ADVISORY} has NO fixed version, and `.cargo/audit.toml` ignores it on the "
              f"strength of `{CRATE}` not being built.")
        print("  That ignore is now false: the vulnerable code ships again. Either restore the "
              "`aws_lc_rs`\n  backend for jsonwebtoken, or delete the ignore and carry the "
              "advisory openly.")
        return 1

    print(f"rsa-out-of-build-gate: OK — `{CRATE}` is not in the normal build graph, so no shipped "
          f"binary contains it.")
    print(f"  It REMAINS in Cargo.lock via sqlx-mysql, an optional dependency this workspace "
          f"never enables;\n  that is why {ADVISORY} is ignored in .cargo/audit.toml rather than "
          f"absent from the report.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
