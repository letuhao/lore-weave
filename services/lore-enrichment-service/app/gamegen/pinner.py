"""S6 — where the bytes land. The second seam into the engine.

`progression-validate` answers *"would this be admitted?"*; `progression-pin`
answers *"admit it"*. Same shape as :mod:`app.gamegen.validator`, same rule: this
module decides nothing. It hands bytes to a binary and reports what came back.

The one argument it must get right is ``--expect``. S5 recorded a
``progression_digest`` beside a human's approval; between that moment and this one
sit a re-generation, a file write and a process boundary, and **none of them would
announce a change**. The pin would succeed, the store would hold a valid table,
and the ruleset would carry a digest nobody ever saw. So the expected digest is
required and a mismatch is a refusal — T8 (*the artifact cannot be swapped*) at the
one hop where the artifact leaves the database.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.gamegen.validator import ValidatorUnavailable

__all__ = ["PinResult", "PinnerUnavailable", "pinner_path", "run_pinner", "STORE_ENV"]

#: Deploy-time location of the binary and of the store it writes to. Both are
#: platform config: they name where things live on this host, and no two users
#: would want different values (Settings & Config SET-3).
ENV_VAR = "PROGRESSION_PIN_BIN"
STORE_ENV = "PROGRESSION_STORE_ROOT"


class PinnerUnavailable(ValidatorUnavailable):
    """The pin binary or its store could not be used. **Never a skip** — treating
    *"cannot pin"* as *"nothing to pin"* would report a deploy that never happened.

    A subclass of :class:`ValidatorUnavailable` so a caller that already handles
    *"the engine is not reachable"* handles this too; the distinction matters for
    the message, not for the decision.
    """


@dataclass(frozen=True)
class PinResult:
    pinned: bool
    findings: list[str]
    progression_digest: str | None
    ruleset_digest: str | None
    engine_schema_version: int
    engine_law_version: int


def pinner_path() -> Path:
    env = os.environ.get(ENV_VAR)
    if env:
        p = Path(env)
        if not p.is_file():
            raise PinnerUnavailable(f"{ENV_VAR}={env} does not point at a file")
        return p
    root = Path(__file__).resolve().parents[4]
    name = "progression-pin.exe" if os.name == "nt" else "progression-pin"
    for profile in ("release", "debug"):
        p = root / "target" / profile / name
        if p.is_file():
            return p
    raise PinnerUnavailable(
        f"the engine's pinner was not found (looked at ${ENV_VAR}, then "
        f"{root / 'target'}/{{release,debug}}/{name}). Build it with "
        f"`cargo build -p ruleset-loader --bin progression-pin`."
    )


def store_root() -> Path:
    """Where pinned rulesets live. **Required in any real deployment.**

    Falling back to a temp directory would make a pin succeed and vanish — the
    worst possible failure here, because every hop upstream would stay green and
    the reality would simply never find its table.
    """
    env = os.environ.get(STORE_ENV)
    if not env:
        raise PinnerUnavailable(
            f"${STORE_ENV} is not set. Refused rather than defaulting to a temp "
            f"directory: a pin that succeeds and vanishes leaves every hop upstream "
            f"green and a reality that cannot resolve its own table."
        )
    return Path(env)


def run_pinner(artifact_toml: str, *, expect_digest: str, layer: str = "reality") -> PinResult:
    """Hand the artifact to the engine and pin it, or find out why not."""
    exe = pinner_path()
    root = store_root()
    with tempfile.TemporaryDirectory(prefix="gamegen-pin-") as d:
        src = Path(d) / "candidate.toml"
        src.write_text(artifact_toml, encoding="utf-8")
        try:
            proc = subprocess.run(
                [str(exe), "--store", str(root), "--expect", expect_digest,
                 f"{layer}={src}"],
                capture_output=True, text=True, encoding="utf-8", timeout=120,
            )
        except subprocess.TimeoutExpired as e:
            raise PinnerUnavailable(
                "the pinner did not finish in 120s. Not recorded as a refusal: a timeout "
                "says nothing about the rules, and the store may or may not have been "
                "written - which is exactly the state a caller must not guess about."
            ) from e

    try:
        raw = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise PinnerUnavailable(
            f"the pinner's output is not JSON (exit {proc.returncode}): "
            f"{proc.stdout[:200]!r} / stderr {proc.stderr[:200]!r}"
        ) from e

    if bool(raw["pinned"]) != (proc.returncode == 0):
        raise PinnerUnavailable(
            f"the pinner's exit code ({proc.returncode}) disagrees with its result "
            f"({raw['pinned']!r}). Both come from the same binary, so a disagreement "
            f"means neither can be relied on - and this one decides whether bytes are "
            f"on disk."
        )

    return PinResult(
        pinned=bool(raw["pinned"]),
        findings=list(raw.get("findings") or []),
        progression_digest=raw.get("progression_digest"),
        ruleset_digest=raw.get("ruleset_digest"),
        engine_schema_version=int(raw["engine_schema_version"]),
        engine_law_version=int(raw["engine_law_version"]),
    )
