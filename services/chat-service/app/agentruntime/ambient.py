"""CP-1.8c · the purity boundary — the ONE module in this package that may read ambient state.

`ARCHITECTURE.md` §0.14.4. Environment, filesystem, clock and randomness are read **here**, and
every other module in `app/agentruntime/` receives those values as parameters.

**Why a boundary rather than a rule.** The rest of this package is a pure function of its arguments,
and that is what makes a surface reproducible from a record. An ambient read anywhere else is not a
style problem — it is an input that no record captures, so the same recorded inputs stop producing
the same surface. `take_while_budget`'s budget is the live example: it is read from `os.environ` **at
import** in the legacy path, which makes it a property of the container that nothing can replay.

**What the gate can and cannot see, written here rather than discovered later.**
`scripts/agentruntime-membrane-gate.py` checks by **direct name**: an `os.environ` or `open()` in a
module that is not this one fails. It **cannot** see an ambient read reached through an intermediate
helper, or through a callable passed in as an argument. **It raises the cost of crossing the
boundary; it does not make crossing impossible**, and no sentence in this package may claim it does.

🔴 **And "by direct name" was not the whole residual — the NAME LIST itself was short.** A verifier
executed twelve probe shapes against it instead of trusting it and found seven it did not know:
`.resolve()`, `Path.cwd()`, `Path.home()`, `.touch()`, `.is_file()`, `time.perf_counter()` and
**`secrets.*`** — which §0.14.4's own word *"randomness"* covers even though its explicit list named
only `random` and `uuid`. One of the seven was **live in this package**: `manifest.py` computed
`Path(__file__).resolve()` with the gate green, which is why `module_anchor` now exists. All seven
are covered and each has a selftest probe, because a capability list that nobody proves is a list
that quietly shrinks. **A disclosure of one blind spot is not a disclosure of the others.**

*(The gate could not see any of this until CP-1.8: it permits the whole standard library, and every
ambient capability in Python is in the standard library — it was green on `os`, `time`, `random`,
`uuid` and `open()`.)*
"""
from __future__ import annotations

import os
from pathlib import Path

#: Where the manifest lives, when the deployment says so explicitly.
MANIFEST_PATH_ENV = "LOREWEAVE_AGENT_RUNTIME_MANIFEST"


def manifest_path_override() -> str | None:
    """The explicit manifest location, or `None`. **Deployment resolves the path; code does not
    guess it** — a guess writes the catalog somewhere nobody reads."""
    return os.environ.get(MANIFEST_PATH_ENV) or None


def module_anchor() -> Path:
    """The absolute location of this package on disk, for the marker search that finds the manifest.

    🔴 **`Path(__file__).resolve()` lived in `manifest.py` and the gate was green on it** — a
    filesystem call *and* a read of the checkout's layout, in a non-boundary module, missed because
    `.resolve()` was not in the gate's method list. A verifier found it by executing twelve probe
    shapes rather than by trusting the list, and six more were missing beside it.

    It belongs here for the reason the boundary exists: **the deployed layout differs from the
    checkout**, which is exactly how `parents[4]` once made this package unimportable in production.
    A module that computes where it is is not a function of its arguments.
    """
    return Path(__file__).resolve()


def exists(path: Path) -> bool:
    """A filesystem probe, behind the boundary so `manifest.py` stays a function of its arguments."""
    return path.exists()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
