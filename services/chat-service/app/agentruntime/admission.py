"""CP-1.4 · M4 — construction IS validation.

`ARCHITECTURE.md` §6.1. **An `Admitted[D]` exists only if the contract check produced it**, so
"is this declaration valid?" is not a question a caller can ask wrongly — holding the object is the
answer.

**What this replaces.** The thing being replaced is not "no validator". It is a validator with
**14 call sites against 58 constructions** in one service (`MustValidateToolMeta` vs `NewToolMeta`).
A validator you must remember to call is a validator that is 76% not called, and no amount of
discipline fixes that shape — which is why the mechanism has to be the *type*, not a function.

**🔴 WHAT THIS TYPE DOES NOT DO, first, because two drafts of §6.1 got it wrong in the same
direction.** The clause first promised a *compile error* (there is no compile step and no type
checker on this service), and then five "actually enforceable" guarantees — **three of which a
verifier falsified, and the builder then reproduced by execution:**

* `_TOKEN` is a single-underscore module attribute, so `from …admission import _TOKEN` works and
  `Admitted(d, v, _TOKEN)` **succeeds**. `import` does not honour naming conventions.
* `object.__setattr__(a, "declaration", other)` **succeeds** — `frozen=True` blocks `a.x = …`, not
  the two-argument form this class's own `__init__` uses.
* `object.__new__(Admitted)` followed by two `object.__setattr__` calls yields a **fully usable**
  forgery. Subclassing is unrestricted too.

**No wording fixes that. Python cannot make this unforgeable**, and asserting otherwise is what both
earlier drafts did instead of probing.

**So M4 is defence in depth (§6.1), and this type is only the first layer:**

1. **accident boundary — this file.** `Admitted(decl, ver)` raises; `copy`, `deepcopy` and `pickle`
   raise. That stops the *unintentional* producer, which is the entire 14-call-sites-against-58-
   constructions shape being replaced. It stops nothing deliberate, and does not claim to.
2. **detection boundary — the gate.** A bypass must name a private symbol or call
   `object.__setattr__` on an `Admitted`. Both are greppable, so a deliberate bypass is **loud in a
   diff** rather than impossible in a process.
3. **correctness boundary — revalidation, in `manifest.py`.** The writer re-runs the contract on
   every row it writes and the reader on every row it loads. **This is the load-bearing layer**, and
   it is the one that does not depend on this type being trustworthy.

Layer 3 exists because trusting the type hid two real defects: `build()` wrote a row for any object
with a `.declaration` attribute, and `load()` served whatever JSON was on disk. **A type may express
an invariant; it may not be the only thing enforcing one across a persistence boundary.**
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
