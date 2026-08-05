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
import re
from pathlib import Path
from typing import Iterable

from . import ambient, canon
from .admission import Admitted
from .contract import CONTRACT_VERSION, Declaration, check_contract, identity_of

MANIFEST_VERSION = 1

_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
_MANIFEST_REL = Path("contracts") / "agent-runtime-manifest.json"
# CP-1.8c — the env var name now lives behind the purity boundary (`ambient.py`).
_ENV_VAR = ambient.MANIFEST_PATH_ENV


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
    override = ambient.manifest_path_override()
    if override:
        return Path(override)
    here = ambient.module_anchor()
    for parent in here.parents:
        candidate = parent / _MANIFEST_REL
        if ambient.exists(candidate):
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


def _row(admitted: Admitted[Declaration], *, origin: dict[str, str] | None = None) -> dict:
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
        # 🔴 P4, AND IT HAD A SUBJECT AT THIS CHECKPOINT AFTER ALL.
        #
        # This wrote `ident.contract_version`, and `identity_of` hardcodes the module constant — so
        # every row claimed the contract version **current at write time**, while the version the
        # declaration was actually checked against was captured on `Admitted` and thrown away. A
        # column bound to a constant at the INSERT with the real signal sitting one attribute away:
        # the exact shape P4 names, at this package's own persistence boundary.
        #
        # The consequence is §6.4's mechanism, defeated silently. That clause says a **breaking**
        # amendment puts prior declarations into a re-admission queue. Computing that queue means
        # comparing what a row was admitted against with what the contract now says — and if the row
        # re-states the current constant, every historical row claims conformance to a contract it
        # was never checked against, and the queue is permanently empty — a migration that can
        # never find work.
        #
        # I had reported P4 as having "no subject at CP-1" because the new runtime reaches no DB
        # INSERT. That was reasoning from where I expected the property to live rather than from
        # what it says: the manifest IS this checkpoint's write boundary.
        #
        # 🔴 **AND THE FIRST FIX INVERTED THE RULE, WHICH BROKE §6.4 THE OTHER WAY.** It read
        # `carried.get(d.id, admitted.contract_version)` — the file's old stamp shadowing the live
        # one **for any id already present**. A verifier executed a re-admission under an amended
        # contract, including one whose `owning_service` materially changed: the owner column
        # updated, and the stamp did not. So a declaration that HAD been re-admitted still reported
        # the old contract, and §6.4's queue named work already done, forever. The queue went from
        # permanently EMPTY (the original defect) to permanently NON-EMPTY. **A field that cannot
        # move and a field that restates a constant fail identically: the reader cannot act on
        # either.**
        #
        # §6.4 requires TWO fields, and this is why. They answer different questions and only one of
        # them moves:
        #   `contract_version`  — the generation this declaration ORIGINATED in. Carried forward
        #                         untouched, so "two contract generations on one runtime" is visible.
        #   `admitted_against`  — what THIS admission was checked against. Always the live value,
        #                         because being in `admitted` means the current contract just passed
        #                         on this row. This is what drains the queue.
        # Queue = rows whose `admitted_against` is not the document's contract version. It empties
        # exactly when the migration is done, which is the only behaviour that makes it a work list.
        "contract_version": (origin or {}).get(ident.id, admitted.contract_version),
        "admitted_against": admitted.contract_version,
        "members": list(d.members),
    }


def build(
    admitted: Iterable[Admitted[Declaration]], *, previous: dict | None = None,
) -> dict:
    """The manifest document for a set of admitted declarations. Pure; writes nothing.

    Takes `Admitted`, not `Declaration`, and that is the membrane in one signature: an unadmitted
    declaration cannot reach this function, because the only way to hold the argument type is to
    have passed the contract check.

    🔴 `previous` CARRIES THE ORIGIN. IT MUST NOT CARRY THE ADMISSION.

    Two attempts at P4 failed here, in opposite directions, and the pair is the whole lesson.

    **First:** the constant read moved one call earlier and that was called a fix — `admit()` took
    the version from `check_contract()`, whose only success return is `CONTRACT_VERSION`. Same
    constant, same value on every row; a verifier printed `{'1.0.0'}` across all of them. **A field
    that cannot differ between two rows records nothing about either.**

    **Second:** `previous` was then allowed to shadow the live value for **any** id already in the
    file. That does make two rows differ — and it froze them. A row genuinely re-admitted under the
    amended contract kept its old stamp, so §6.4's queue reported work that had already been done,
    permanently. Empty forever, then non-empty forever; neither is a work list.

    **What `previous` is actually for:** `contract_version`, the generation a declaration
    ORIGINATED in, which by definition cannot be recomputed from a live admission because the
    admission happening now is not the first one. `admitted_against` is never carried — being in
    `admitted` *means* the current contract passed on this row, and that is precisely the fact the
    queue reads.

    Validation happens here rather than only on the read side because `previous` is caller-supplied:
    the exported `build()` was reachable with `previous={"declarations": [{"id": ..., "admitted_
    against": 7}]}` and emitted an integer as a stamp, producing a document its own `load()` refuses.
    A writer that trusts its argument is the write-end of the boundary `UntrustedRow` describes.
    """
    origin: dict[str, str] = {}
    for i, r in enumerate((previous or {}).get("declarations", []) or []):
        if not isinstance(r, dict) or not r.get("id"):
            raise UntrustedRow(f"previous.declarations[{i}] has no id; it cannot carry an origin")
        stamp = r.get("contract_version")
        if not isinstance(stamp, str) or not _VERSION.match(stamp):
            raise UntrustedRow(
                f"previous.declarations[{i}].contract_version is {stamp!r}; the origin generation "
                f"must be MAJOR.MINOR.PATCH. `previous` is caller-supplied, so it is checked here "
                f"and not only on the way back in."
            )
        origin[r["id"]] = stamp
    rows = [_row(a, origin=origin) for a in admitted]
    # 🔴 A DECLARATION PRESENT IN `previous` AND ABSENT FROM `admitted` WAS SILENTLY DROPPED, and
    # that is how the "origin" stamp turned out not to be an origin at all: a verifier regenerated
    # without one declaration, regenerated again with it, and the row came back **claiming the new
    # generation**. Four routes reset it, three of them ungated.
    #
    # §1 says the plan deletes nothing and retirements are structurally zero, so a row disappearing
    # is never intended — it is either a caller that forgot one or a declaration that **failed a
    # breaking amendment**, which §6.4 says must enter a re-admission queue *without leaving the
    # runtime*. That mechanism does not exist (see §6.4.1), and the honest response to a missing
    # mechanism is to make its absence LOUD rather than to let the row fall out in silence.
    lost = sorted(set(origin) - {r["id"] for r in rows})
    if lost:
        raise UntrustedRow(
            f"{lost} are in the previous manifest and not in this build. A declaration does not "
            f"leave the runtime (§1), and §6.4's re-admission queue — the mechanism that would let "
            f"one stay while it is re-admitted — IS NOT BUILT (§6.4.1). Dropping the row silently "
            f"erases the generation it originated in."
        )
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


def generate(
    admitted: Iterable[Admitted[Declaration]], *, path: Path | None = None,
    bootstrap: bool = False,
) -> dict:
    """Build and write. **The generator is the only writer** — a hand-edited manifest is a row that
    passed no contract check, which is the whole mechanism defeated by a text editor.

    The M1 gate (*manifest row count == admitted count*) is the drift check on exactly that.

    🔴 **`bootstrap` EXISTS BECAUSE THE ABSENCE OF A FILE WAS SILENTLY TREATED AS PERMISSION TO
    REWRITE HISTORY.** `previous` used to default to `None` whenever the target did not exist, so
    writing to a fresh path — or deleting the manifest, which is the ordinary reaction to a drift
    gate going red — restamped every row's origin with the current constant and emptied §6.4's queue.
    No test and no gate noticed. A missing manifest cannot be distinguished from *"the origins are
    genuinely unknown"* by looking at it, so the caller has to say which one it means: writing the
    **first** manifest is a real operation, and it is the only one this flag is for.
    """
    target = path or manifest_path()
    if target is None:
        raise UntrustedRow(
            "no manifest location: pass `path=`, or set "
            f"{_ENV_VAR}. Guessing one would write the catalog somewhere nobody reads."
        )
    if ambient.exists(target):
        previous = load(path=target)
    elif bootstrap:
        previous = None
    else:
        raise UntrustedRow(
            f"no manifest at {target}: every row would be stamped with the CURRENT contract "
            f"version, erasing which generation each declaration originated in and silently "
            f"emptying §6.4's re-admission queue. Pass `bootstrap=True` if this really is the "
            f"first manifest."
        )
    doc = build(admitted, previous=previous)
    ambient.write_text(target, json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
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
    if target is None or not ambient.exists(target):
        return _empty()
    doc = json.loads(ambient.read_text(target))
    return validate_document(doc, source=str(target))


def validate_document(doc: dict, *, source: str = "<memory>") -> dict:
    """Re-run the contract over a manifest document. Returns it unchanged, or raises.

    Separate from `load` so the same check covers a document that arrived any other way, and so the
    M1 drift gate can call it without reading through this module's path resolution.
    """
    if not isinstance(doc, dict):
        raise UntrustedRow(f"{source}: manifest is not an object")
    # The document-level stamps were written from constants and read from nowhere: a verifier fed
    # `contract_version: "banana"` and a missing `manifest_version` and both passed. The only thing
    # catching it today is the drift gate's byte-equality with `build([])`, which does not survive
    # the first non-empty manifest. `contract_version` is also the queue's COMPARAND — an unreadable
    # one silently empties the queue, which is the same failure §6.4.1 records one level down.
    if doc.get("manifest_version") != MANIFEST_VERSION:
        raise UntrustedRow(
            f"{source}: manifest_version is {doc.get('manifest_version')!r}, expected "
            f"{MANIFEST_VERSION}. One format is supported and an unknown one is not a newer file, "
            f"it is a file this reader cannot make claims about."
        )
    doc_version = doc.get("contract_version")
    if not isinstance(doc_version, str) or not _VERSION.match(doc_version):
        raise UntrustedRow(
            f"{source}: contract_version is {doc_version!r}; §6.4's re-admission queue is derived "
            f"by comparing every row against it, so an unreadable value empties the queue in silence"
        )
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
                # §0.14.2 door (a). Every other row string is ASCII-constrained by the contract;
                # `owning_service` is not, and an NFD spelling loaded, validated and stored
                # un-normalised — two `canon.digest` values for one visibly identical document,
                # which is the "drift check reports a change nobody made" failure this door exists
                # to prevent.
                source_path=f"services/{canon.nfc(r.get('owning_service', ''))}/",
                # 🔴 NO DEFAULT. This read `r.get("lifecycle", "draft")`, so a row with **no**
                # lifecycle key passed validation — and was returned still missing it, because the
                # default lived only inside this check. C-0 names lifecycle state as part of
                # identity, so a row omitting it was admitted on read with an identity the file does
                # not contain. It is the P4 shape at the READ half of the same boundary: a column
                # value fixed by the code rather than by the thing being validated.
                lifecycle=r["lifecycle"] if "lifecycle" in r else "",
                members=tuple(r.get("members", ()) or ()),
            ))
        except Exception as exc:
            raise UntrustedRow(f"{source}: declarations[{i}] failed the contract — {exc}") from exc
        # 🔴 Both stamps are validated, because a field nothing checks is a field anything can say.
        # A verifier fed `admitted_against` `null`, `"banana"`, `"99.0.0"` and the OLD field name;
        # all four were accepted, and four hand-built fixtures still carried the removed name and
        # passed — which was itself the proof that neither name was being validated.
        #
        # **This is a SYNTAX check and not a validity one, deliberately and with a residual.**
        # `"99.0.0"` and `"0.0.0"` still pass: they are well-formed versions that never existed. A
        # shape check cannot tell a real generation from a plausible one, and the safe direction is
        # this one — a bogus stamp lands a row *in* the queue rather than out of it. An earlier
        # version of this comment implied all four of the verifier's inputs were now rejected. Three
        # are.
        # 🔴 **A BACKFILL STOOD HERE AND IT WAS A LAUNDERING PATH FOR A MIGRATION THAT DOES NOT
        # EXIST.** It adopted `admitted_against` as the origin whenever `contract_version` was
        # absent, reasoning that for a pre-two-field row the one stamp IS the origin. True for a
        # genuine old row — and a verifier showed the cost: a **hand-edited** row carrying
        # `admitted_against: "99.0.0"` and no `contract_version` was rejected before and accepted
        # after, and the carry then made `"99.0.0"` its **permanent** origin across a real
        # `generate()`. The `"99.0.0"` residual is defensible for a queue *comparand*, where a bogus
        # value lands the row IN the queue; an origin is not a comparand and nothing re-checks it.
        #
        # And the migration it was written for has **no subject**: the committed manifest is
        # `declarations: []`. The old shapes — three of them, not the two I claimed — exist only in
        # git history. **Nothing deployed is bricked, so nothing needs laundering to un-brick it.**
        # It also mutated its argument, so the M1 drift gate compared a document it had silently
        # repaired. Both gone: `load()` is strict, and a real migration, if one is ever needed, is
        # an explicit operation somebody runs and reviews.
        for field in ("contract_version", "admitted_against"):
            stamp = r.get(field)
            if not isinstance(stamp, str) or not _VERSION.match(stamp):
                raise UntrustedRow(
                    f"{source}: declarations[{i}].{field} is {stamp!r}; §6.4 requires BOTH the "
                    f"origin generation (`contract_version`) and what this admission was checked "
                    f"against (`admitted_against`), as MAJOR.MINOR.PATCH. The re-admission queue is "
                    f"the difference between them, so an unreadable stamp empties it silently."
                )
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
    """The rows, through the one reader.

    🔴 THIS WAS THE THIRD COPY of `.get("declarations", [])`, and the worst-placed one: `rows_of`
    was written to be "ONE PLACE" while this function — **the only row-reader in `__all__`** — kept
    the silent form. So the package's public API returned `[]` for a malformed document while its
    internal one raised. The docstring claiming one place was written over a count of two, and a
    verifier found the third by executing `declarations({})`.

    The rule that keeps failing here is not about `.get`. It is that **a consolidation is a count,
    not a sentence** — the claim "one place" is checkable in seconds and was not checked.
    """
    from .surface import rows_of
    return rows_of(doc if doc is not None else load(path=path))
