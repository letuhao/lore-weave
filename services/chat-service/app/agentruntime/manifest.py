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
import os
from pathlib import Path
from typing import Iterable

from .admission import Admitted
from .contract import CONTRACT_VERSION, Declaration, check_contract, identity_of

MANIFEST_VERSION = 1

_MANIFEST_REL = Path("contracts") / "agent-runtime-manifest.json"
_ENV_VAR = "LOREWEAVE_AGENT_RUNTIME_MANIFEST"


def manifest_path() -> Path | None:
    """Where the manifest lives, resolved **at call time** and never raising.

    🔴 **This was `Path(__file__).resolve().parents[4]` at MODULE level, and it made the entire
    package unimportable in production.** The image flattens `services/chat-service/` to `/app`, so
    there are not four parents above this file and `parents[4]` raised `IndexError` **during
    import** — every submodule, in a fresh interpreter, before any code ran. Confirmed in the
    running container by a verifier.

    **Nothing in the test suite could have caught it**, and that is the transferable part: tests run
    from the source tree, where the arithmetic is correct by construction. A path expression that
    counts directory levels encodes the *layout of the checkout*, and the deployed layout is a
    different one. So this resolves by **searching for a marker** instead of counting, checks an
    explicit environment override first, and returns `None` rather than raising — a missing manifest
    is a legitimate state (it means *no declarations*), so it must never be an import-time crash.
    """
    override = os.environ.get(_ENV_VAR)
    if override:
        return Path(override)
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / _MANIFEST_REL
        if candidate.exists():
            return candidate
    return None


class UnresolvedReference(Exception):
    """M5 — a member naming a declaration that is not admitted. Generation fails; nothing ships."""

    def __init__(self, declaration_id: str, member: str) -> None:
        self.declaration_id = declaration_id
        self.member = member
        super().__init__(
            f"{declaration_id} references {member!r}, which is not admitted. A reference is a "
            f"foreign key into the manifest (C-11 / M5) — resolve it or do not declare it."
        )


class UntrustedRow(Exception):
    """A manifest row that did not come from an admission, on either side of the file.

    §6.1 layer 3. **The type was never the boundary it was believed to be**, and trusting it hid two
    separate defects: `build()` wrote a row for any object carrying a `.declaration` attribute (a
    four-line duck-typed class put `sneaky` into a generated manifest), and `load()` served whatever
    JSON was on disk — so a row **typed in by hand** reached the assembler having passed no clause.

    JSON has no types. A boundary that assumes its neighbour validated is a boundary that validates
    nothing.
    """


def _row(admitted: Admitted[Declaration]) -> dict:
    # §6.1 layer 3, the WRITE end. `isinstance` first — the type is an accident boundary, so this
    # rejects the duck type — and then the contract is re-run, because holding an `Admitted` is
    # evidence about the past and this row is a claim about now.
    if not isinstance(admitted, Admitted):
        raise UntrustedRow(
            f"{type(admitted).__name__} is not an Admitted. A manifest row is written only from an "
            f"admission; carrying a `.declaration` attribute is not the same thing (ARCHITECTURE "
            f"§6.1 layer 3)."
        )
    d = admitted.declaration
    check_contract(d)
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
    target = path or manifest_path()
    if target is None:
        raise UntrustedRow(
            "no manifest location: pass `path=`, or set "
            f"{_ENV_VAR}. Guessing one would write the catalog somewhere nobody reads."
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return doc


def _empty() -> dict:
    return {"manifest_version": MANIFEST_VERSION,
            "contract_version": CONTRACT_VERSION,
            "declarations": []}


def load(*, path: Path | None = None) -> dict:
    """Read the manifest, **re-validating every row**. §6.1 layer 3, the READ end.

    Absent file → an **empty** manifest, which is the fail-safe direction and the one that matters:
    a missing catalog must mean *no declarations*, never *fall back to the one with 315 in it*.

    **Every row is re-checked against the contract**, because the write-side guarantee does not
    survive the file. `generate()` is the only writer this code has; a text editor is a writer this
    code does not have, and before this check a row typed straight into the JSON was served to the
    assembler having passed no clause at all. Admission is a property of a *row*, not of the process
    that happened to produce the file.

    A bad row raises rather than being skipped. Skipping would make a corrupt manifest look like a
    smaller one — and *"the surface was smaller than you think and nobody said so"* is the exact
    failure class this whole runtime exists to end.
    """
    target = path or manifest_path()
    if target is None or not target.exists():
        return _empty()
    doc = json.loads(target.read_text(encoding="utf-8"))
    return validate_document(doc, source=str(target))


def validate_document(doc: dict, *, source: str = "<memory>") -> dict:
    """Re-run the contract over a manifest document. Returns it unchanged, or raises.

    Separate from `load` so the same check covers a document that arrived any other way, and so the
    M1 drift gate can call it without reading through this module's path resolution.
    """
    if not isinstance(doc, dict):
        raise UntrustedRow(f"{source}: manifest is not an object")
    rows = doc.get("declarations")
    if not isinstance(rows, list):
        raise UntrustedRow(f"{source}: `declarations` is missing or not a list")
    ids: set[str] = set()
    for i, r in enumerate(rows):
        if not isinstance(r, dict):
            raise UntrustedRow(f"{source}: declarations[{i}] is not an object")
        try:
            check_contract(Declaration(
                id=r.get("id", ""),
                kind=r.get("kind", ""),
                # The row stores the DERIVED owner; the contract derives it from a path. Feed the
                # stored owner back through the same shape so a row that names an owner nothing
                # could have derived is rejected rather than trusted.
                source_path=f"services/{r.get('owning_service', '')}/",
                lifecycle=r.get("lifecycle", "draft"),
                members=tuple(r.get("members", ()) or ()),
            ))
        except Exception as exc:
            raise UntrustedRow(f"{source}: declarations[{i}] failed the contract — {exc}") from exc
        if r["id"] in ids:
            raise UntrustedRow(f"{source}: duplicate declaration id {r['id']!r}")
        ids.add(r["id"])
    # M5 again, on the read side: a member that resolved at generation can be broken by an edit.
    for r in rows:
        for m in r.get("members", ()) or ():
            if m not in ids:
                raise UnresolvedReference(r["id"], m)
    return doc


def declarations(doc: dict | None = None, *, path: Path | None = None) -> list[dict]:
    return list((doc if doc is not None else load(path=path)).get("declarations", []))
