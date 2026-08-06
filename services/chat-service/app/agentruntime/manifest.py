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
from .contract import (
    CONTRACT_VERSION, ContractViolation, Declaration, UnresolvedReference, UntrustedRow, _VERSION,
    check_contract, check_document_rows, check_row, identity_of,
)

# 🔴 `UntrustedRow` and `UnresolvedReference` are DEFINED IN `contract.py` now and re-exported here
# so every existing `from .manifest import UntrustedRow` keeps working. They moved because the door
# a consumer actually stands behind is `surface.rows_of`, which could not raise either of them from
# here without an import cycle — so it raised `ContractViolation` for a bad row and a bare
# `ValueError` for a bad document, two unrelated classes at one exported door. Both are `ValueError`
# subclasses now, so no caller's `except` stops working.
__all_reexported__ = (UnresolvedReference, UntrustedRow)

MANIFEST_VERSION = 1

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
    row = {
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
    # 🔴 **THE WRITER WAS THE THIRD DOOR, AND IT WAS THE ONE NOBODY CHECKED.** `rows_of` and
    # `validate_document` both consult the one definition of a row; the only function in this
    # repository that PRODUCES a row did not. A verifier gave `_row` one plausible CP-4 field and
    # measured the result: `build()` accepted it, `generate()` **wrote it to disk**, and the failure
    # landed afterwards — at the next `load()`, or in CI at `agentruntime-membrane-gate.py`. That is
    # the "discovered late" shape, and CP-4 adding a row field is a scheduled occurrence of it.
    #
    # It also makes the closed schema self-enforcing at the only place that can violate it: adding a
    # key here without adding it to `ROW_FIELDS` now fails in the same change rather than in the next
    # one.
    check_row(row, "row")
    return row


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
    # 🔴 The OUTER `previous or {}` was left untouched while the inner one was fixed — **eight**
    # malformed shapes still accepted, the previous round's finding verbatim. Fixing the member the
    # reviewer named rather than the set is this run's most-repeated failure; this is its fifth
    # instance, and it happened inside the fix for the fourth.
    if previous is not None and type(previous) is not dict:
        raise UntrustedRow(
            f"previous is a {type(previous).__name__}, not a plain object. A malformed prior "
            f"document is not an absent one, and treating it as absent disables the loss check."
        )
    # Materialised for the same reason, and `type(...) is` for the same reason: `_prev_rows or []`
    # over a container that lies about `__len__` turned a populated document into an empty one and
    # disabled the loss guard below.
    # 🔴 `.get("declarations", [])` SERVES A MISSING KEY AS EMPTY — the exact confusion `rows_of`
    # refuses by name two modules over, in the function whose whole job is to notice a declaration
    # that vanished. A document with no `declarations` key is malformed, not empty, and treating it
    # as empty disables the loss guard for a caller that simply built the dict wrong. **Reachable
    # with plain JSON and no adversary.**
    if previous is not None and "declarations" not in previous:
        raise UntrustedRow(
            "previous has no `declarations` key. An empty prior manifest is `declarations: []`; a "
            "missing key is a malformed document, and serving it as empty silently disables the "
            "check that a declaration cannot leave the manifest."
        )
    _prev_rows = (previous or {}).get("declarations", [])
    if previous is not None and type(_prev_rows) is not list:
        # `previous={"declarations": None}` silently disabled the loss guard below — the `or []`
        # turned a malformed document into an empty one, which is the same "serve a broken thing as
        # empty" the assembler's own `rows_of` refuses by name. Unreachable through `generate()`,
        # reachable through the exported `build()`.
        raise UntrustedRow(
            f"previous.declarations is {_prev_rows!r}, not a list. A malformed prior document is "
            f"not an empty one, and treating it as empty disables the check that a declaration "
            f"cannot silently leave the manifest."
        )
    _prev_rows = list(_prev_rows)
    for i, r in enumerate(_prev_rows):
        # 🔴 **THE FOURTH DOOR, AND IT HAD ITS OWN WEAKER DEFINITION OF A ROW.** This read
        # `isinstance(r, dict)`, `r.get("id")` and `r.get("contract_version")` — so a `previous` row
        # carrying an undefined key, a dict-valued field or a non-string key was ACCEPTED here and
        # REFUSED by `rows_of`, measured. Worse, `.get("id")` here and `r["id"]` one line below are
        # two reads of the same fact, which a `dict` subclass answers differently.
        #
        # `previous` is caller-supplied — the docstring above says exactly why that matters — so it
        # goes through the same definition as every other row-reader. Unreachable through
        # `generate()`, where `previous` comes from `load()`; reachable through the exported
        # `build()`, in plain JSON.
        try:
            check_row(r, f"previous.declarations[{i}]")
        except ContractViolation as exc:
            # 🔴 **THE NEW SUBCLASSING MADE `except UntrustedRow` SWALLOW `ContractViolation` AND
            # RE-RAISE IT FLAT**, destroying `.declaration_id` / `.field_path` / `.accepted` — so
            # the same row refused by `rows_of` with a C-12 field path was refused here with prose.
            # It is verbatim the defect fixed 175 lines below, committed in the same change as that
            # fix, and it exists *because* the hierarchy was unified: a broader `except` catches
            # more the moment the class it names gains a subclass.
            raise ContractViolation(exc.declaration_id, exc.field_path, exc.reason,
                                    f"{exc.accepted}. `previous` is caller-supplied, so it is "
                                    f"checked here and not only on the way back in") from exc
        except UntrustedRow as exc:
            raise UntrustedRow(f"{exc}. `previous` is caller-supplied, so it is checked here and "
                               f"not only on the way back in.") from exc
        origin[r["id"]] = r["contract_version"]
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
    # M5 and the duplicate check are properties of the SET, and they now live beside the row clauses
    # in `contract.py` so the read side and the write side cannot disagree about them — which they
    # did: `rows_of` ran neither, and served `members: ['ghost']` to four consumer doors.
    check_document_rows(rows, "declarations")
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
        # 🔴 `exists()` THEN `load()` IS TWO READS OF THE SAME FACT. If the file vanishes between
        # them — a concurrent regeneration, a deploy, a `rm` — `load()` returns `_empty()` and this
        # writes a manifest with **every origin reset and rows silently dropped**, without
        # `bootstrap=` ever being passed. The flag exists to make exactly that operation deliberate,
        # and a race walked around it. So the emptiness is re-checked against the reason we believed
        # the file was there.
        previous = load(path=target)
        if not previous.get("declarations") and not ambient.exists(target):
            raise UntrustedRow(
                f"{target} disappeared between the existence check and the read. Writing now would "
                f"reset every origin and drop every row without `bootstrap=` being asked for."
            )
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
    # 🔴 `type(...) is dict`, not `isinstance` — **the fifth TOCTOU, open four rounds.** Every ROW
    # was exact-typed while the DOCUMENT that supplies them was only `isinstance`-checked, inside
    # this one function. Measured: a `dict` subclass answered `manifest_version=1` /
    # `contract_version='1.0.0'` to the checks and `999` / `'banana'` to the `{**doc}` at the bottom
    # — and `contract_version` is §6.4's queue comparand, so the document that left here had a
    # different comparand from the one that was validated.
    if type(doc) is not dict:
        raise UntrustedRow(
            f"{source}: manifest is a {type(doc).__name__}, not a plain JSON object. A container "
            f"that decides its own answers can answer the validator and the consumer differently."
        )
    # The document schema is closed for the same reason the row schema is: a top-level key nothing
    # defines passed no clause, and `{**doc}` used to carry it through to every reader.
    _extra = sorted(set(doc) - {"manifest_version", "contract_version", "declarations"})
    if _extra:
        raise UntrustedRow(
            f"{source}: manifest carries {_extra}, which the format does not define. One format is "
            f"supported; an unknown key is not a newer file, it is one this reader cannot make "
            f"claims about."
        )
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
    # 🔴 **THE SAME TOCTOU I FIXED IN `surface.py` AND DID NOT LOOK FOR HERE.** `declarations` was
    # `isinstance`-checked and then **iterated twice** — a `list` subclass handed the validator
    # `['t0']` and the consumer `['t0', 'TYPED BY HAND!!']`, the second row violating every clause.
    # `_is_exactly` refuses the subclass; the materialised copy makes the two iterations the same
    # one. Applying a correction where the reviewer pointed, and not to the class, is this run's
    # most-repeated failure and this is its fourth instance.
    if type(rows) is not list:
        raise UntrustedRow(f"{source}: `declarations` is missing or not a plain list")
    rows = list(rows)
    for i, r in enumerate(rows):
        # ONE definition of a valid row, shared with `surface.rows_of`, `_row` and `build(previous=)`
        # — **shape AND clauses**. Three earlier versions of this loop each held their own copy of
        # the clause list; consolidating only the shape left nine classes of row that this door
        # refused and the consumer door accepted. The contract clauses, the two §6.4 stamps and the
        # `owning_service` NFC door all moved into `contract.check_row` verbatim; the duplicate check
        # and M5 into `contract.check_document_rows`, because they are properties of the set.
        try:
            check_row(r, f"declarations[{i}]")
        except ContractViolation as exc:
            # Re-raised as the SAME class, with `source` folded into the field path rather than
            # into a wrapper. Wrapping it in a bare `UntrustedRow` kept the sentence and threw away
            # `.declaration_id` / `.field_path` / `.accepted` — so the two doors refused the same
            # row with two different classes again, one level further down, and C-12's structured
            # promise survived only as prose.
            raise ContractViolation(exc.declaration_id, f"{source}:{exc.field_path}", exc.reason,
                                    exc.accepted) from exc
        except UntrustedRow as exc:
            raise UntrustedRow(f"{source}: {exc}") from exc
    check_document_rows(rows, "declarations")
    # 🔴 **I MATERIALISED THE ITERATION AND RETURNED THE ORIGINAL CONTAINER.** The rows were copied
    # so the loop could not be fed different values twice — and then `return doc` handed the caller
    # the document it came in on. A row's own `.get()` is user code, and this function CALLS it
    # inside the validation loop: that call appended a hand-typed row to the caller's plain list, so
    # `validate_document` **accepted** while `rows_of` / `declarations()` handed the consumer
    # `['book_list', 'TYPED BY HAND!!']`. **No container subclass required.**
    #
    # A validator returns what it validated, or it has validated nothing. The document that leaves
    # here is built from the rows this function actually checked.
    #
    # 🔴 **AND `{**doc}` WAS THE OTHER HALF OF THAT SENTENCE, LEFT UNDONE FOR FOUR ROUNDS.** The
    # ROWS were rebuilt from what was checked and the two document STAMPS were re-read from the
    # caller's object at the return — the same defect one level up, in the same statement as its own
    # fix. Both stamps are now the validated values, so nothing this function returns was read after
    # it was checked.
    return {
        "manifest_version": MANIFEST_VERSION,
        "contract_version": doc_version,
        "declarations": [dict(r) for r in rows],
    }


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
