"""Is the local stack actually up? One answer, read from ONE place.

    THE INVARIANT. A test that needs a live stack skips when, and only when, the probe
    `gate-wiring-gate` already uses says no stack is answering.

🔴 THIS EXISTS BECAUSE TWO "needs the local stack" GUARDS COULD NEVER SKIP IN CI, and 22
red-ability proofs ran there and failed as a result. The two guards were:

    pytest.mark.skipif(not (ROOT / "infra").exists(), ...)   # `infra/` is CHECKED IN
    pytest.mark.skipif(docker ps returncode != 0, ...)       # runners HAVE docker

Both test a proxy that is TRUE on a GitHub runner, so neither ever fired there. The failures
read like real defects — `cypher_query: could not read NEO4J_PASSWORD from
infra-knowledge-service-1`, `SnapshotUnavailable: loreweave_jobs`, `httpx.ConnectError`,
`psql failed` — and every one of them says only "there is no stack here". They stayed
invisible until a `deprecated-tool-scan` fix let the job reach the step that runs them.

A skip guard has to probe THE THING, not something correlated with it. `gate-wiring-gate`
already decided what that means: a TCP connect to the isolated knowledge-pg on 25556, the
store the bare-runnable gates default to. Its own comment explains the choice — "a probe of
anything else could say 'up' while the thing they read is down".

So this module does not define a second answer. It imports the first one, and if it cannot,
it says NO STACK rather than guessing: a wrong "up" makes CI red for the wrong reason, and a
wrong "down" only skips a test that was going to be skipped on the runner anyway.
"""
from __future__ import annotations

import importlib.util
import os

SCRIPTS = os.path.dirname(os.path.abspath(__file__))


def _probe():
    """`gate-wiring-gate.stack_reachable`, or None when it cannot be loaded.

    The filename has hyphens, so it is not importable by name — the same importlib load
    `gate-number-visibility-gate` uses to read that file's `NEEDS_STACK`.
    """
    try:
        spec = importlib.util.spec_from_file_location(
            "_gwg_stack", os.path.join(SCRIPTS, "gate-wiring-gate.py"))
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return getattr(mod, "stack_reachable", None)
    except Exception:
        return None


def up() -> bool:
    """True only when the SSOT probe says a stack is answering.

    Fails CLOSED: an unloadable probe returns False, so a test guarded by this skips rather
    than running against nothing and reporting the absence as a defect.
    """
    probe = _probe()
    if probe is None:
        return False
    try:
        return bool(probe())
    except Exception:
        return False


#: The reason string every guarded test shares, so a skip says WHY and names the probe.
REASON = ("needs the local stack — no TCP answer at the anchor gate-wiring-gate probes "
          "(127.0.0.1:25556, the isolated knowledge-pg)")


def _selftest() -> int:
    """Prove the two properties that matter, without needing a stack either way."""
    ok = True

    def expect(what: str, got, want) -> None:
        nonlocal ok
        good = got == want
        ok = ok and good
        print(f"  {'ok  ' if good else 'FAIL'} {what}: {got!r} (want {want!r})")

    # 1. The SSOT is READABLE. If this breaks, `up()` silently returns False forever and
    #    every guarded test skips everywhere — green by absence, which is the failure this
    #    file was written to end.
    expect("gate-wiring-gate.stack_reachable is importable", _probe() is not None, True)

    # 2. It answers the actual probe, not a proxy. `infra/` exists in every checkout and
    #    docker runs on every CI runner; neither may decide this.
    infra_exists = os.path.isdir(os.path.join(os.path.dirname(SCRIPTS), "infra"))
    expect("`infra/` exists in this checkout (so it cannot be the guard)", infra_exists, True)
    expect("up() is a bool, not a truthy path/exit code", isinstance(up(), bool), True)

    print(f"\nlive_stack: {'PASS' if ok else 'FAIL'} — stack is "
          f"{'UP' if up() else 'DOWN'} here")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(_selftest())
