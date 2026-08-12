#!/usr/bin/env python3
"""dockerfile-replace-copy-gate — a Go `replace` the image build cannot resolve.

WHY THIS EXISTS
---------------
T30 (OD-1) made `glossary-service` take a module dependency on `contracts/events` — the
event-name SSOT — replacing five hand-mirrored copies of the wire names. It shipped with
the whole Go suite green, the gates green, and `go build` clean.

**The image could not be built at all.** The Dockerfile never COPYed `contracts/events`
into the build context, so `go mod download` died on the first `docker compose build`
after it:

    go: github.com/loreweave/foundation/contracts/events@v0.0.0-...
        (replaced by ../../contracts/events): reading /src/contracts/events/go.mod:
        no such file or directory

Nothing caught it because nothing could: `go build` on a developer machine and in CI
resolves the `replace` against the real path on disk, where the module obviously exists.
Only the container has a build context, and **no workflow in this repo builds a service
image** — so the deploy artefact of a service was broken for a day and every signal stayed
green. A test cannot catch this class. A static comparison of the two files can.

WHAT IT CHECKS
--------------
For every containerised Go service (`services/*/` with BOTH `go.mod` and `Dockerfile`):
every `replace ... => <relative path>` target that points OUTSIDE the service directory
must be COPYed into the image by some `COPY` instruction — directly, or via an ancestor
directory. A Dockerfile that copies the whole context (`COPY . …`) is exempt: it cannot
miss anything.

    python scripts/dockerfile-replace-copy-gate.py            # gate
    python scripts/dockerfile-replace-copy-gate.py --list     # every pair, resolved
    python scripts/dockerfile-replace-copy-gate.py --selftest # prove it can go red

MEASURED 2026-08-12: 43 replace targets across the containerised Go services, 0 uncopied
once the glossary Dockerfile was fixed. The floor is ZERO and stays there — unlike this
repo's shrink-only ceilings there is no backlog to work off, because a violation is not
technical debt, it is an image that does not build.

Exit 0 = every replace resolves inside the image · 1 = at least one does not.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# `replace foo => ../../bar` and the same line inside a `replace ( … )` block. Only
# path-form targets matter: `replace foo => bar v1.2.3` swaps in a PUBLISHED module and
# needs nothing in the build context.
_REPLACE_TARGET = re.compile(r"^\s*(?:replace\s+)?\S+\s+=>\s+(\.\.?[^\s]*)\s*$")
# COPY [--from=x --chown=y] <src> [<src>…] <dest>
_COPY = re.compile(r"^COPY\s+((?:--\S+\s+)*)(.+)$", re.M)


def _replace_targets(gomod_path: str) -> list[str]:
    """Path-form replace targets, verbatim as written."""
    targets: list[str] = []
    in_block = False
    with open(gomod_path, encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped.startswith("replace ("):
                in_block = True
                continue
            if in_block and stripped == ")":
                in_block = False
                continue
            if stripped.startswith("replace ") or in_block:
                match = _REPLACE_TARGET.match(line)
                if match:
                    targets.append(match.group(1))
    return targets


def _copied_sources(dockerfile_text: str) -> tuple[list[str], bool]:
    """(source paths this Dockerfile copies, copies-the-whole-context)."""
    sources: list[str] = []
    whole = False
    for _flags, rest in _COPY.findall(dockerfile_text):
        parts = rest.split()
        if len(parts) < 2:
            continue
        for src in parts[:-1]:          # the last token is the destination
            if src in (".", "./"):
                whole = True
            sources.append(src.rstrip("/"))
    return sources, whole


def _satisfied(repo_rel: str, sources: list[str]) -> bool:
    """A COPY of the path itself, or of any ancestor directory, brings it in."""
    return any(
        repo_rel == src or repo_rel.startswith(src + "/")
        for src in sources
    )


def audit(root: str) -> tuple[list[tuple[str, str, str]], int]:
    """Returns (violations, total targets checked). A violation is
    (service, replace-as-written, repo-relative target)."""
    services_dir = os.path.join(root, "services")
    violations: list[tuple[str, str, str]] = []
    checked = 0
    if not os.path.isdir(services_dir):
        return violations, checked

    for service in sorted(os.listdir(services_dir)):
        service_dir = os.path.join(services_dir, service)
        gomod = os.path.join(service_dir, "go.mod")
        dockerfile = os.path.join(service_dir, "Dockerfile")
        if not (os.path.isfile(gomod) and os.path.isfile(dockerfile)):
            continue
        with open(dockerfile, encoding="utf-8") as fh:
            sources, whole = _copied_sources(fh.read())
        if whole:
            continue
        for written in _replace_targets(gomod):
            absolute = os.path.normpath(os.path.join(service_dir, written))
            repo_rel = os.path.relpath(absolute, root).replace(os.sep, "/")
            # A replace pointing back INSIDE the service is copied by the service's own
            # COPY line; it is not a shared-module dependency at all.
            if repo_rel.startswith(f"services/{service}/"):
                continue
            checked += 1
            if not _satisfied(repo_rel, sources):
                violations.append((service, written, repo_rel))
    return violations, checked


# ── selftest ────────────────────────────────────────────────────────────────────────────
# A gate wired to CI with no proof it can go red is a claim in the costume of evidence.
# This builds a throwaway service tree BOTH ways and asserts the verdicts differ.

_SELFTEST_GOMOD = """module github.com/loreweave/selftest-service

go 1.25

require github.com/loreweave/shared/thing v0.0.0

replace github.com/loreweave/shared/thing => ../../sdks/go/thing

replace (
\tgithub.com/loreweave/shared/other => ../../contracts/other
\tgithub.com/published/dep => github.com/fork/dep v1.4.0
)
"""

_DOCKERFILE_GOOD = """FROM golang:1.25-alpine AS build
WORKDIR /src
COPY sdks/go/thing /src/sdks/go/thing
COPY contracts/other /src/contracts/other
COPY services/selftest-service /src/services/selftest-service
RUN go mod download
"""

# The real bug, exactly: one shared module silently absent from the context.
_DOCKERFILE_MISSING = """FROM golang:1.25-alpine AS build
WORKDIR /src
COPY sdks/go/thing /src/sdks/go/thing
COPY services/selftest-service /src/services/selftest-service
RUN go mod download
"""

# An ANCESTOR copy must satisfy it — otherwise the gate reds on Dockerfiles that are
# perfectly correct, and a noisy gate gets disabled.
_DOCKERFILE_ANCESTOR = """FROM golang:1.25-alpine AS build
WORKDIR /src
COPY sdks /src/sdks
COPY contracts /src/contracts
COPY services/selftest-service /src/services/selftest-service
RUN go mod download
"""

_DOCKERFILE_WHOLE_CONTEXT = """FROM golang:1.25-alpine AS build
WORKDIR /src
COPY . /src
RUN go mod download
"""


def _write_tree(root: str, dockerfile: str) -> None:
    service = os.path.join(root, "services", "selftest-service")
    os.makedirs(service, exist_ok=True)
    for shared in ("sdks/go/thing", "contracts/other"):
        os.makedirs(os.path.join(root, shared), exist_ok=True)
    with open(os.path.join(service, "go.mod"), "w", encoding="utf-8") as fh:
        fh.write(_SELFTEST_GOMOD)
    with open(os.path.join(service, "Dockerfile"), "w", encoding="utf-8") as fh:
        fh.write(dockerfile)


def selftest() -> int:
    cases = [
        ("every replace copied", _DOCKERFILE_GOOD, 0, 2),
        ("one shared module never copied", _DOCKERFILE_MISSING, 1, 2),
        ("an ANCESTOR copy satisfies it", _DOCKERFILE_ANCESTOR, 0, 2),
        ("COPY . takes the whole context", _DOCKERFILE_WHOLE_CONTEXT, 0, 0),
    ]
    failures: list[str] = []
    for label, dockerfile, want_violations, want_checked in cases:
        tmp = tempfile.mkdtemp(prefix="dfrc-gate-")
        try:
            _write_tree(tmp, dockerfile)
            violations, checked = audit(tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        ok = len(violations) == want_violations and checked == want_checked
        print(f"  [{'ok' if ok else 'XX'}] {label}: "
              f"{len(violations)} violation(s), {checked} checked "
              f"(want {want_violations}/{want_checked})")
        if not ok:
            failures.append(label)

    # The published-module replace must NEVER be counted — `=> github.com/fork/dep v1.4.0`
    # is not a path and needs nothing in the context. It is in the fixture go.mod above,
    # and `want_checked == 2` (not 3) is what asserts it was skipped.
    if failures:
        print(f"\n[dockerfile-replace-copy-gate] SELFTEST FAIL — {failures}")
        return 1
    print("\n[dockerfile-replace-copy-gate] SELFTEST PASS — reds on a missing COPY, stays "
          "green on an ancestor copy and on a whole-context copy (non-vacuous)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true",
                        help="print every replace target and how it is satisfied")
    parser.add_argument("--selftest", action="store_true",
                        help="prove the gate can go red")
    args = parser.parse_args()

    if args.selftest:
        return selftest()

    violations, checked = audit(ROOT)

    if args.list:
        services_dir = os.path.join(ROOT, "services")
        for service in sorted(os.listdir(services_dir)):
            gomod = os.path.join(services_dir, service, "go.mod")
            dockerfile = os.path.join(services_dir, service, "Dockerfile")
            if not (os.path.isfile(gomod) and os.path.isfile(dockerfile)):
                continue
            targets = _replace_targets(gomod)
            if targets:
                print(f"{service}: {len(targets)} replace target(s)")
                for written in targets:
                    print(f"    {written}")

    print(f"[dockerfile-replace-copy-gate] {checked} shared-module replace target(s) "
          f"across containerised Go services; {len(violations)} not copied into the image")

    if violations:
        print("\n[dockerfile-replace-copy-gate] FAIL — these images cannot be built:\n")
        for service, written, repo_rel in violations:
            print(f"  {service}: go.mod has `=> {written}` but the Dockerfile never "
                  f"COPYs {repo_rel}")
        print("\n  Add `COPY <path> /src/<path>` before the service's own COPY line. "
              "`go build` on\n  a developer machine resolves the replace against the real "
              "directory, so no test\n  and no CI leg here will tell you — only a "
              "`docker build` will.\n")
        return 1

    print("[dockerfile-replace-copy-gate] PASS — every path replace is in the build context")
    return 0


if __name__ == "__main__":
    sys.exit(main())
