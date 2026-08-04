"""CP-1.4 · M4 — construction IS validation.

`ARCHITECTURE.md` §6.1. **An `Admitted[D]` exists only if the contract check produced it**, so
"is this declaration valid?" is not a question a caller can ask wrongly — holding the object is the
answer.

**What this replaces.** The thing being replaced is not "no validator". It is a validator with
**14 call sites against 58 constructions** in one service (`MustValidateToolMeta` vs `NewToolMeta`).
A validator you must remember to call is a validator that is 76% not called, and no amount of
discipline fixes that shape — which is why the mechanism has to be the *type*, not a function.

**THE GUARANTEE, STATED AS WHAT IS ACTUALLY ENFORCEABLE.** §6.1 originally said a bypass would be a
*compile error*. It would not: Python has no compile-time access control, and **no type checker runs
on this service** — no `mypy`/`pyright` config, no `pyproject.toml`, no type-check job. The spec was
amended before this file was written rather than after a verifier found the gap. Five guarantees,
and one honest residual:

1. **`admit()` is the only producer** — `__init__` requires a module-private token that nothing else
   can name. `Admitted(decl)` raises.
2. **It cannot be mutated into a different declaration** — frozen, with `__slots__`, so there is no
   attribute assignment and no `__dict__` to reach around it.
3. **It cannot be round-tripped into existence** — `__reduce__`, `__copy__` and `__deepcopy__`
   refuse. Pickle and `copy` are the two standard ways a "private" constructor is bypassed by
   accident rather than malice.
4. **A forged instance is unusable** — `object.__new__(Admitted)` cannot be prevented by any Python
   mechanism, and is not claimed to be. It leaves every slot **unset**, so the first read raises
   `AttributeError` instead of returning a plausible value. The failure is loud and immediate, which
   is the property that matters: this checkpoint's expensive defects were all quiet wrong answers.
5. **The construction site stays single** — `scripts/agentruntime-membrane-gate.py` counts them.

**The residual is row 4 and it is named, not hidden.** A caller can *allocate* an `Admitted` without
passing the check. What it cannot do is get a **usable** one, or a **silent** one.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from .contract import ContractViolation, Declaration, check_contract

D = TypeVar("D", bound=Declaration)


class _AdmissionToken:
    """The capability to construct an `Admitted`. One instance, module-private, never exported.

    A sentinel rather than a flag: a boolean argument can be passed by anyone who reads the
    signature, and `__all__` is a convention that `import` ignores. Holding the object IS the
    permission, and only this module's `admit()` holds it.
    """

    __slots__ = ()


_TOKEN = _AdmissionToken()


@dataclass(frozen=True, slots=True)
class Admitted(Generic[D]):
    """A declaration that has passed C-0…C-17. **Cannot be constructed any other way.**

    Generic over the declaration kind so a tool, a skill and a workflow are admitted by one
    mechanism rather than three — §3: *"the membrane is over declarations, not over tools, so a
    legacy skill and a legacy workflow step are excluded by the same construction."*
    """

    declaration: D
    contract_version: str

    def __init__(self, declaration: D, contract_version: str, _token: Any = None) -> None:
        if _token is not _TOKEN:
            raise TypeError(
                "Admitted() is not constructible. It is produced by agentruntime.admit(), which is "
                "the contract check — construction IS validation (ARCHITECTURE §6.1 / M4)."
            )
        object.__setattr__(self, "declaration", declaration)
        object.__setattr__(self, "contract_version", contract_version)

    # Round-trip forgery. `copy` and `pickle` reconstruct objects WITHOUT calling `__init__`, so a
    # private constructor alone does not stop them — this is the bypass that happens by accident.
    def __reduce__(self) -> Any:
        raise TypeError("Admitted is not serialisable; re-admit from the declaration instead.")

    def __copy__(self) -> Any:
        raise TypeError("Admitted is not copyable; it would duplicate an admission decision.")

    def __deepcopy__(self, memo: dict) -> Any:
        raise TypeError("Admitted is not copyable; it would duplicate an admission decision.")

    @property
    def id(self) -> str:
        return self.declaration.id

    @property
    def kind(self) -> str:
        return self.declaration.kind


def admit(declaration: D) -> Admitted[D]:
    """The **only** producer of an `Admitted`. Raises `ContractViolation` on any failing clause.

    Deliberately has no `force=`, no `skip_checks=`, no `strict=False`. §6.4: *a declaration that
    fails admission is not patched into compliance and re-run — the failure is data about the
    contract.* An escape hatch here would make every guarantee above advisory, and `require_meta` in
    this repository already demonstrates the shape: a validator that ships its own documented
    exemption.
    """
    contract_version = check_contract(declaration)
    return Admitted(declaration, contract_version, _TOKEN)


def try_admit(declaration: D) -> tuple[Admitted[D] | None, ContractViolation | None]:
    """`admit` for callers that must survive a rejection — generation reporting every bad row at
    once rather than stopping at the first. **Not a bypass:** it returns `None` where `admit` would
    raise, and there is no path on which a failing declaration yields an `Admitted`.
    """
    try:
        return admit(declaration), None
    except ContractViolation as exc:
        return None, exc
