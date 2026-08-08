"""CP-2.7 · M4 — **the registration entry point refuses to boot on an incomplete contract.**

Spec: ``ARCHITECTURE.md`` §3 (M4). Checkpoint: RUNSTATE → L2 · CP-2.7.

**M4 has been recorded as FALSE since CP-1, by name, in the board's own words:**

> *"the registration entry point **refuses to boot** on an incomplete contract"* — 🔴 **STILL
> FALSE, and it is not CP-1's to make true.** Nothing imports `app.agentruntime`, so there is no
> boot to refuse — the check runs where a declaration is *admitted*, not at service start. Wiring
> an import so the phrase becomes true would be pulling CP-2 forward. **Recorded as unmet rather
> than reworded.**

This is the change that makes it true, and the acceptance test §3 states for it is literal:
**remove one required clause, watch the service fail to start.**

WHY IT IS FAIL-CLOSED, AND WHY THAT IS THE CHEAP DIRECTION HERE
----------------------------------------------------------------
A malformed manifest takes chat-service down. That is a real cost and it is the correct one:

* the alternative is a service that starts with a **silently empty or partial** declaration set,
  which is *"invisibility implemented as a filter"* arriving through the boot path — the exact
  shape §3 forbids everywhere else;
* the blast radius is bounded by what the manifest is. `contracts/agent-runtime-manifest.json` is a
  **generated, committed** file with a CI drift gate over it, so a bad one cannot arrive by
  accident between deploys — it arrives in a diff, and this makes that diff fail loudly at the
  earliest possible moment rather than at the first turn that needed a declaration;
* **a missing manifest is NOT a refusal.** `load()` reads absent as `declarations: []`, which is a
  legitimate state meaning *no declarations* — and it is today's state. Refusing to boot on it
  would make the empty membrane unshippable, and would confuse *"nothing is declared"* with
  *"something is wrong"*, which are the two facts this whole effort keeps separating.

WHAT THIS IS NOT
-----------------
It is **not the request-path route.** A turn still cannot be served by this package, so the four
V-LIVE items inherited into 2.7 — the agent *says* it has no declarations, no legacy declaration is
reachable, the empty state is *recorded* rather than displayed, P1 visible in the row — remain
`CANNOT DETERMINE`. This closes M4 and gives the package its first production importer; it does not
close 2.7.
"""
from __future__ import annotations

from .contract import UntrustedRow
from .manifest import load, manifest_path


class WillNotBoot(RuntimeError):
    """The manifest exists and is not admissible. **Raised at startup, not at first use.**

    A `RuntimeError` rather than an `UntrustedRow`: every other refusal in this package answers
    *"this input is not admissible"* to a caller who asked. This one answers *"this process must
    not run"*, to nobody — there is no caller who can do anything with it, which is what makes it a
    boot failure rather than a validation error.
    """


def boot() -> dict:
    """Validate the manifest, or refuse to start. Returns the document it validated.

    Every clause is `load()`'s — the contract check over every row, the two §6.4 stamps, the closed
    top-level schema, M5's foreign keys. **Nothing is re-implemented here**, because a second
    definition of *valid* is how `rows_of` and `load()` came to disagree about nine shapes while a
    docstring said they were one door.

    What this adds is **when**: at process start, on a path with no caller, so a manifest that
    cannot be served makes the service fail to start rather than making the first turn that needed
    a declaration fail in a way somebody has to reproduce.
    """
    try:
        return load()
    except UntrustedRow as exc:
        raise WillNotBoot(
            f"the agent-runtime manifest at {manifest_path()} is not admissible, so this process "
            f"will not start (M4, ARCHITECTURE §3). A service that boots with a silently partial "
            f"declaration set is 'invisibility implemented as a filter' arriving through the boot "
            f"path. Fix the manifest or regenerate it; an ABSENT manifest is a legitimate empty "
            f"state and is not this error. Cause: {exc}"
        ) from exc


__all__ = ["WillNotBoot", "boot"]
