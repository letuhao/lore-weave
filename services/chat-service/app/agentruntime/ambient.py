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


def exists(path: Path) -> bool:
    """A filesystem probe, behind the boundary so `manifest.py` stays a function of its arguments."""
    return path.exists()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
