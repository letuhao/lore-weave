#!/usr/bin/env python3
"""release-targets — which services get a versioned Docker image on release.

DERIVED, NOT WRITTEN DOWN. Same reason `dependabot.yml` uses directory globs and
`gate-wiring-gate.py` walks `scripts/` instead of naming files: a hand-written list of
"services we release" goes stale the moment a service is added, and stays stale silently — the
next release just quietly ships without the new image and nobody notices until someone goes
looking for it. This reads the buildable service set straight from `infra/docker-compose.yml`
(anything with a `build:` key IS a service this repo builds an image for; that fact already has
to be true for local dev to work, so it can't drift out from under a release without also
breaking `docker compose build`).

EXCLUSIONS ARE THE ONLY HAND-MAINTAINED PART, AND THEY ARE NAMED, NOT GUESSED. `postgres` is a
base-image customization, not a LoreWeave service — publishing `ghcr.io/.../postgres` would be
confusing at best. Add to `EXCLUDE` with a one-line reason; anything not listed here ships by
default, which is the safe direction for THIS list specifically (an accidentally-excluded real
service is a silent gap; an accidentally-included one is just an extra image nobody asked for).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent.parent
COMPOSE = REPO / "infra" / "docker-compose.yml"

EXCLUDE = {
    "postgres": "base-image customization (extensions), not a LoreWeave service",
}


def _repo_relative(path: Path, repo_root: Path) -> str:
    """POSIX-style path relative to `repo_root`, resolved (no `..` or symlink surprises left
    in) — GitHub Actions runners are Linux, and `docker/build-push-action`'s `context`/`file`
    inputs are both resolved relative to the actions runner's CWD (repo root at checkout), not
    relative to each other, so BOTH must land here already repo-root-relative."""
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def targets(compose_path: Path = COMPOSE) -> list[dict]:
    doc = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    services = doc.get("services", {}) or {}
    compose_dir = compose_path.resolve().parent
    repo_root = compose_path.resolve().parent.parent if compose_dir.name == "infra" else compose_dir
    out = []
    for name in sorted(services):
        spec = services[name]
        if not isinstance(spec, dict) or "build" not in spec:
            continue
        if name in EXCLUDE:
            continue
        build = spec["build"]
        if isinstance(build, str):
            raw_context, raw_dockerfile = build, "Dockerfile"
        else:
            raw_context = build.get("context", ".")
            raw_dockerfile = build.get("dockerfile", "Dockerfile")
        # `context` is relative to the compose file's own directory (docker-compose semantics);
        # `dockerfile` is then relative to THAT resolved context, not to the compose file again.
        abs_context = (compose_dir / raw_context).resolve()
        abs_dockerfile = (abs_context / raw_dockerfile).resolve()
        out.append({
            "service": name,
            "context": _repo_relative(abs_context, repo_root),
            "dockerfile": _repo_relative(abs_dockerfile, repo_root),
        })
    return out


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    result = targets()
    if "--list" in argv:
        for t in result:
            print(t["service"])
    else:
        # Default: GitHub Actions `matrix` JSON on one line.
        print(json.dumps(result))
    if not result:
        print("release-targets: 0 buildable services found — the compose file could not be "
              "read correctly, or every service was excluded. Refusing to emit an empty "
              "release matrix silently.", file=sys.stderr)
        return 1
    return 0


def _selftest() -> int:
    import tempfile
    fixture = """
services:
  real-service:
    build:
      context: ..
      dockerfile: services/real-service/Dockerfile
  narrow-context-service:
    build:
      context: ../services/narrow-context-service
      dockerfile: Dockerfile
  postgres:
    build: .
  no-build-service:
    image: redis:7
"""
    failures = 0
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        # Mirror the real layout: compose lives in infra/, repo root is its parent.
        infra_dir = root / "infra"
        infra_dir.mkdir()
        p = infra_dir / "docker-compose.yml"
        p.write_text(fixture, encoding="utf-8")
        result = targets(p)
        names = {t["service"] for t in result}
        checks = [
            ("a buildable service is included", "real-service" in names),
            ("postgres is excluded", "postgres" not in names),
            ("a non-build (image:-only) service is excluded", "no-build-service" not in names),
            ("repo-root context resolves to '.'", any(
                t["service"] == "real-service" and t["context"] == "."
                for t in result)),
            ("dockerfile is repo-root-relative even though context is repo root", any(
                t["service"] == "real-service"
                and t["dockerfile"] == "services/real-service/Dockerfile"
                for t in result)),
            ("a narrower context resolves relative to repo root, not to itself", any(
                t["service"] == "narrow-context-service"
                and t["context"] == "services/narrow-context-service"
                and t["dockerfile"] == "services/narrow-context-service/Dockerfile"
                for t in result)),
        ]
        for label, ok in checks:
            print(f"  {'ok  ' if ok else 'FAIL'} {label}")
            if not ok:
                failures += 1
    # And against the REAL compose file: must find at least one real service, never zero.
    real = targets()
    ok = len(real) > 0
    print(f"  {'ok  ' if ok else 'FAIL'} the real infra/docker-compose.yml yields >0 targets ({len(real)})")
    if not ok:
        failures += 1
    if failures:
        print(f"\nrelease-targets --self-test: {failures} case(s) failed")
        return 1
    print(f"\nrelease-targets --self-test: all cases passed")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(_selftest())
    sys.exit(main())
