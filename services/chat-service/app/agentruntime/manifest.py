"""CP-1.1 · M1 — the registry that starts empty. CP-1.5 · M5 — references that must resolve.

`ARCHITECTURE.md` §3. The manifest is **generated only from admitted declarations**. It is the new
surface's sole catalog: not the preferred one, not the first of two.

> **Old declarations are not hidden. They are absent.** There is no branch here that can read the
> legacy catalog — not one that is disabled, not one behind a flag.

**Why "starts empty" is a property and not a starting condition.** An empty manifest is the only
state in which the membrane is *provably* not leaking: with 315 legacy declarations one directory
away, any non-empty result on day one would be indistinguishable from a leak. The emptiness is the
measurement. CP-4 admits the first row, one at a time, and each one is then attributable.

**M5, and why it is at generation rather than at call time.** 12 rails in this repository point at
30 dead tools behind a gate that **fails open** — the reference is checked when it is used, and the
check's failure mode is to allow. Resolving at generation inverts both: an unresolvable member
means **no manifest is written at all**, so the failure cannot be reached at runtime because the
artifact does not exist.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from .admission import Admitted
from .contract import CONTRACT_VERSION, Declaration, identity_of

MANIFEST_VERSION = 1

# Resolved from this file: app/agentruntime/manifest.py -> chat-service -> services -> repo root.
_REPO_ROOT = Path(__file__).resolve().parents[4]
MANIFEST_PATH = _REPO_ROOT / "contracts" / "agent-runtime-manifest.json"


class UnresolvedReference(Exception):
    """M5 — a member naming a declaration that is not admitted. Generation fails; nothing ships."""

    def __init__(self, declaration_id: str, member: str) -> None:
        self.declaration_id = declaration_id
        self.member = member
        super().__init__(
            f"{declaration_id} references {member!r}, which is not admitted. A reference is a "
            f"foreign key into the manifest (C-11 / M5) — resolve it or do not declare it."
        )


def _row(admitted: Admitted[Declaration]) -> dict:
    d = admitted.declaration
    ident = identity_of(d)
    return {
        "id": ident.id,
        "kind": d.kind,
        # C-0: derived from where the code lives, never read from the declaration.
        "owning_service": ident.owning_service,
        "lifecycle": ident.lifecycle,
        "contract_version": ident.contract_version,
        "members": list(d.members),
    }


def build(admitted: Iterable[Admitted[Declaration]]) -> dict:
    """The manifest document for a set of admitted declarations. Pure; writes nothing.

    Takes `Admitted`, not `Declaration`, and that is the membrane in one signature: an unadmitted
    declaration cannot reach this function, because the only way to hold the argument type is to
    have passed the contract check.
    """
    rows = [_row(a) for a in admitted]
    ids = {r["id"] for r in rows}
    for r in rows:
        for m in r["members"]:
            if m not in ids:
                raise UnresolvedReference(r["id"], m)
    dupes = sorted({r["id"] for r in rows if sum(1 for x in rows if x["id"] == r["id"]) > 1})
    if dupes:
        raise UnresolvedReference(dupes[0], dupes[0])
    return {
        "manifest_version": MANIFEST_VERSION,
        "contract_version": CONTRACT_VERSION,
        "declarations": sorted(rows, key=lambda r: r["id"]),
    }


def generate(admitted: Iterable[Admitted[Declaration]], *, path: Path | None = None) -> dict:
    """Build and write. **The generator is the only writer** — a hand-edited manifest is a row that
    passed no contract check, which is the whole mechanism defeated by a text editor.

    The M1 gate (*manifest row count == admitted count*) is the drift check on exactly that.
    """
    doc = build(admitted)
    target = path or MANIFEST_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return doc


def load(*, path: Path | None = None) -> dict:
    """Read the manifest. **Returns an empty manifest when the file is absent** — the fail-safe
    direction, and the one that matters: a missing catalog must mean *no declarations*, never
    *fall back to the one with 315 in it*.
    """
    target = path or MANIFEST_PATH
    if not target.exists():
        return {"manifest_version": MANIFEST_VERSION,
                "contract_version": CONTRACT_VERSION,
                "declarations": []}
    return json.loads(target.read_text(encoding="utf-8"))


def declarations(doc: dict | None = None, *, path: Path | None = None) -> list[dict]:
    return list((doc if doc is not None else load(path=path)).get("declarations", []))
