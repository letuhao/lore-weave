"""The seam where the pipeline hands its work to the **engine's own binary**.

`PGN-A7`: *the validator is the engine's binary, and the verdict records which
binary.* This module is deliberately thin — its whole job is to run
``progression-validate`` and parse what it said. Every temptation here is a
temptation to re-implement a rule Python has no business owning:

* it does **not** decide admitted/refused — the exit code and the JSON do;
* it does **not** supply the engine versions — they come out of the binary, which
  compiled them in;
* it does **not** summarise the findings — they are the engine's own ``Display``
  strings, all of them, because ``validate`` returns every finding precisely so a
  reviewer does not fix one, re-run, and find another.

A verdict this module could produce on its own would be *a mirror nothing forces
to agree* wearing the real engine's version number — which is worse than no
verdict, because it looks like one.

## Locating the binary

Env var first (deployments put it wherever they put it), then the workspace
target dir for a dev checkout. **Not found is an error, never a skip**: a
pipeline that silently treated "no validator" as "nothing to validate" would
admit every candidate on a host where the build failed.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

__all__ = ["Verdict", "ValidatorUnavailable", "validator_path", "run_validator"]

#: Deploy-time location. Platform config, not a user setting: it names where a
#: binary lives on this host, and no two users would want different values.
ENV_VAR = "PROGRESSION_VALIDATE_BIN"


class ValidatorUnavailable(RuntimeError):
    """The engine's validator could not be run. **Never downgraded to a skip.**"""


@dataclass(frozen=True)
class Verdict:
    admitted: bool
    findings: list[str]
    engine_schema_version: int
    engine_law_version: int
    progression_digest: str | None


def validator_path() -> Path:
    env = os.environ.get(ENV_VAR)
    if env:
        p = Path(env)
        if not p.is_file():
            raise ValidatorUnavailable(
                f"{ENV_VAR}={env} does not point at a file. Refused rather than falling "
                f"back to a search path: a deployment that names its validator and is "
                f"wrong should fail loudly, not quietly validate with a different one."
            )
        return p

    # Dev checkout: gamegen -> app -> service -> services -> repo root.
    # `parents[3]` (which this had first) lands on `services/` and every engine
    # test silently SKIPPED — a wrong depth here does not fail, it disappears.
    root = Path(__file__).resolve().parents[4]
    name = "progression-validate.exe" if os.name == "nt" else "progression-validate"
    for profile in ("release", "debug"):
        p = root / "target" / profile / name
        if p.is_file():
            return p
    raise ValidatorUnavailable(
        f"the engine's progression validator was not found (looked at ${ENV_VAR}, then "
        f"{root / 'target'}/{{release,debug}}/{name}). Build it with "
        f"`cargo build -p ruleset-loader --bin progression-validate`. This is an ERROR "
        f"and not a skip: treating 'no validator' as 'nothing to validate' would admit "
        f"every candidate on a host where the build failed."
    )


def run_validator(artifact_toml: str, *, layer: str = "reality") -> Verdict:
    """Run the engine's validator over generated TOML and return what it said.

    :raises ValidatorUnavailable: when the binary is missing, or when it produced
        something this module cannot read. A verdict that cannot be parsed is not
        a refusal — refusing on a parse error would report an engine finding that
        the engine never made.
    """
    exe = validator_path()
    with tempfile.TemporaryDirectory(prefix="gamegen-admit-") as d:
        # A temp dir per call, and the file inside it: two concurrent admissions
        # of different candidates must not read each other's bytes.
        src = Path(d) / "candidate.toml"
        src.write_text(artifact_toml, encoding="utf-8")
        try:
            proc = subprocess.run(
                [str(exe), f"{layer}={src}"],
                capture_output=True, text=True, encoding="utf-8", timeout=60,
            )
        except subprocess.TimeoutExpired as e:
            raise ValidatorUnavailable(
                f"the validator did not finish in 60s. Not a refusal: a timeout says "
                f"nothing about the rules, and recording it as one would attribute a "
                f"finding to the engine that the engine never made."
            ) from e

    try:
        raw = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise ValidatorUnavailable(
            f"the validator's output is not JSON (exit {proc.returncode}): "
            f"{proc.stdout[:200]!r} / stderr {proc.stderr[:200]!r}"
        ) from e

    admitted = raw["verdict"] == "admitted"
    if admitted != (proc.returncode == 0):
        # The binary promises exit 0 = admitted. If the two disagree, something is
        # wrong with the binary itself and BOTH signals are suspect - so neither
        # is trusted rather than picking the one that happens to be convenient.
        raise ValidatorUnavailable(
            f"the validator's exit code ({proc.returncode}) disagrees with its verdict "
            f"({raw['verdict']!r}). Both signals come from the same binary, so a "
            f"disagreement means neither can be relied on."
        )

    return Verdict(
        admitted=admitted,
        findings=list(raw.get("findings") or []),
        engine_schema_version=int(raw["engine_schema_version"]),
        engine_law_version=int(raw["engine_law_version"]),
        progression_digest=raw.get("progression_digest"),
    )
