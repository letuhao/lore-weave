#!/usr/bin/env python3
"""`WorldScale` is declared twice. This is what stops the two copies drifting.

WHY A MIRROR EXISTS AT ALL
--------------------------
`crates/world-gen/src/creative_seed.rs` owns `WorldScale` — the closed size set
(`Pocket` … `Gigaplanet`). `services/world-service/src/world_seed.rs` needs it to
enforce `SDF-A19`: a `World` under a `Domain` (the 内天地 case) is bounded to
`Pocket`, because 500 holders × 1 024 cells is 512 k nodes against the 8.19 M an
unbounded `Megaplanet` would cost.

It could have been a dependency. `world-gen` pulls `image`, `clap`, `delaunator`
and boolean-polygon ops, and a provisioning service importing a renderer and a
CLI to reach one enum is the worse trade. **But a duplicated closed set with
nothing watching it is exactly the rot this repo keeps paying for** — `SPG-F4`
is one word with three meanings, `REC-97` is a table asserting an application
that never happened, and both were found late.

So the mirror gets a MECHANISM. This gate reads the variant list out of both
files and reds when they disagree, in either direction.

WHY A GATE AND NOT A TEST
-------------------------
A cross-crate parity test would need `world-service` to depend on `world-gen`,
which is the dependency the mirror exists to avoid. A gate reads source text and
needs neither crate to know the other — the same reason `entity-existence`'s Go
parity is asserted where the two shapes meet rather than inside either one.

NON-VACUITY
-----------
Two ways this check could quietly stop checking, and both are refused:

  * **either side parsing to nothing.** A rename, a move, or a syntax change
    would leave an empty set on one side and an empty comparison always passes.
    An empty parse is a FINDING, not a pass.
  * **a one-directional compare.** Checking only that the mirror's variants
    exist upstream would miss a variant ADDED upstream, which is the likelier
    direction — the source grows, the mirror does not. The compare is set
    equality.

`--selftest` proves each can fail.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

SOURCE = REPO / "crates/world-gen/src/creative_seed.rs"
MIRROR = REPO / "services/world-service/src/world_seed.rs"

_ENUM = "pub enum WorldScale {"
# A variant is a bare CamelCase identifier on its own line inside the block.
# Doc comments, attributes and blank lines are skipped rather than matched, so a
# variant carrying `#[serde(alias = "...")]` still reads as one variant.
_VARIANT = re.compile(r"^\s*([A-Z][A-Za-z0-9]*)\s*,\s*$")


def _show(path: Path) -> str:
    """Display path, tolerant of selftest fixtures outside the repo."""
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return str(path)


def variants(path: Path) -> tuple[set[str], str | None]:
    """The `WorldScale` variant names in `path`, or a reason it found none."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return set(), f"cannot read {path}: {e}"
    if _ENUM not in text:
        return set(), f"{_show(path)} no longer declares `{_ENUM}`"
    body = text.split(_ENUM, 1)[1]
    end = body.find("\n}")
    if end == -1:
        return set(), f"{_show(path)}: the enum block does not close"
    out: set[str] = set()
    for line in body[:end].splitlines():
        m = _VARIANT.match(line)
        if m:
            out.add(m.group(1))
    if not out:
        return set(), (
            f"{_show(path)}: the enum was found and parsed to ZERO "
            "variants. An empty set compares equal to anything, so this is a finding "
            "rather than a pass."
        )
    return out, None


def check() -> list[str]:
    src, why_src = variants(SOURCE)
    mir, why_mir = variants(MIRROR)
    out: list[str] = []
    if why_src:
        out.append(why_src)
    if why_mir:
        out.append(why_mir)
    if out:
        return out

    missing = src - mir
    extra = mir - src
    if missing:
        out.append(
            f"`WorldScale` variants in world-gen but NOT in the world-service mirror: "
            f"{sorted(missing)}. The source grew and the mirror did not, which is the "
            f"direction a one-way check would have missed."
        )
    if extra:
        out.append(
            f"`WorldScale` variants in the world-service mirror but NOT in world-gen: "
            f"{sorted(extra)}. The mirror is inventing a scale the generator cannot "
            f"produce."
        )
    return out


def selftest() -> int:
    import tempfile

    global SOURCE, MIRROR
    failures: list[str] = []
    real_src, real_mir = SOURCE, MIRROR

    def write(d: Path, name: str, vs: list[str]) -> Path:
        p = d / name
        body = "\n".join(f"    {v}," for v in vs)
        p.write_text(f"pub enum WorldScale {{\n{body}\n}}\n", encoding="utf-8")
        return p

    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        both = ["Pocket", "Region"]

        SOURCE, MIRROR = write(d, "a.rs", both), write(d, "b.rs", both)
        if check():
            failures.append("identical variant sets reded (false positive)")

        SOURCE = write(d, "a.rs", both + ["Megaplanet"])
        if not check():
            failures.append("a variant ADDED UPSTREAM did not red — the likelier direction")

        SOURCE, MIRROR = write(d, "a.rs", both), write(d, "b.rs", both + ["Invented"])
        if not check():
            failures.append("a variant invented by the MIRROR did not red")

        # The two vacuity shapes.
        SOURCE, MIRROR = write(d, "a.rs", both), write(d, "b.rs", [])
        if not check():
            failures.append("an EMPTY parse passed — an empty set compares equal to anything")

        gone = d / "c.rs"
        gone.write_text("pub enum SomethingElse { A }\n", encoding="utf-8")
        SOURCE, MIRROR = gone, write(d, "b.rs", both)
        if not check():
            failures.append("a RENAMED enum passed — the check would silently stop checking")

    SOURCE, MIRROR = real_src, real_mir
    if failures:
        print("SELFTEST FAILED — a check that cannot fail is not a check (NV-1):")
        for f in failures:
            print(f"  ✗ {f}")
        return 1
    print(
        "world-scale-parity-gate selftest: OK — 5 case(s): identical passes, an "
        "upstream addition reds, a mirror invention reds, an empty parse reds, and a "
        "renamed enum reds"
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true", help="prove the check can fail")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    findings = check()
    if findings:
        print(f"world-scale-parity-gate: {len(findings)} finding(s)\n")
        for f in findings:
            print(f"  ✗ {f}\n")
        return 1
    src, _ = variants(SOURCE)
    print(
        f"world-scale-parity-gate: OK — `WorldScale` agrees across "
        f"crates/world-gen and services/world-service on {len(src)} variant(s): "
        f"{', '.join(sorted(src))}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
