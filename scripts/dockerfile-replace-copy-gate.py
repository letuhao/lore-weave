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
directory. A Dockerfile that copies the whole context (`COPY . …`) is exempt ONLY when the
context it is BUILT with actually contains the target.

🔴 **AMENDED 2026-08-30. That exemption was unconditional, and it was wrong — measured.**
This gate reported `43 replace target(s) · 0 not copied` while TWO services could not be built
at all, and both were skipped by exactly this branch:

    alert-recorder      compose declares `context: ../services/alert-recorder` — the SERVICE
                        directory. `COPY . .` then copies the service and nothing else, so
                        `../../contracts/alerts` can never be inside it. Its Dockerfile also
                        carried `COPY ../../contracts/alerts/`, a source that ESCAPES any
                        context and so resolves to nothing in every context.
    canary-controller   nothing declares an image build for it anywhere. `deploy.yml` runs
                        `cd services/canary-controller && go build ./...` on the HOST, where
                        the replace resolves on disk, so its Dockerfile is never exercised.

`COPY . .` does not mean "everything"; it means "the build context", and this gate never asked
what that was. An exemption that assumes a fact it does not check is the shape this repo keeps
paying for — and here it kept a critical bug green for months while its own deferral
(`D-NO-CI-BUILDS-ANY-SERVICE-IMAGE`) sat filed as out of scope.

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
import glob
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


def declared_contexts(root: str) -> dict[str, str]:
    """`{service name: repo-relative build context}`, DERIVED from the compose files.

    Derived because the whole defect was an assumption about the context. A service absent
    from this map has no declared image build at all, which is not a reason to exempt it —
    it is a reason to say so.
    """
    out: dict[str, str] = {}
    pats = [os.path.join(root, "infra", "*.yml"), os.path.join(root, "infra", "*.yaml")]
    for path in sorted(q for pat in pats for q in glob.glob(pat)):
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        here = os.path.dirname(path)
        ctx = None
        for line in text.splitlines():
            m = re.match(r"\s*context:\s*(\S+)", line)
            if m:
                ctx = m.group(1).strip().strip('"').strip("'")
                continue
            m = re.match(r"\s*dockerfile:\s*(\S+)", line)
            if m and ctx is not None:
                dfile = m.group(1).strip().strip('"').strip("'")
                joined = os.path.normpath(os.path.join(here, ctx, dfile))
                rel_ctx = os.path.relpath(os.path.normpath(os.path.join(here, ctx)), root)
                svc = os.path.basename(os.path.dirname(joined))
                out.setdefault(svc, rel_ctx.replace(os.sep, "/"))
                ctx = None
    return out


def whole_context_covers(ctx, repo_rel: str) -> bool:
    """Does `COPY . .` under this declared context bring `repo_rel` in?

    `None` — nothing declares a build — is NOT coverage. That is canary-controller, whose
    Dockerfile no workflow has ever run.
    """
    if ctx is None:
        return False
    ctx = ctx.strip("./")
    return ctx in ("", ".") or repo_rel == ctx or repo_rel.startswith(ctx + "/")


def escaping_sources(sources):
    """COPY sources that leave the build context. Docker resolves every source from the
    context ROOT, so a `../` prefix never reaches the parent — it addresses a path that is
    simply absent, in every context. Always a defect, never a style choice."""
    return [s for s in sources if s.startswith("../") or "/../" in s]


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
    contexts = declared_contexts(root)
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
        ctx = contexts.get(service)
        # A source that escapes the context can never resolve, whatever the context is.
        for bad in escaping_sources(sources):
            violations.append((service, bad, "COPY source escapes the build context"))
        for written in _replace_targets(gomod):
            absolute = os.path.normpath(os.path.join(service_dir, written))
            repo_rel = os.path.relpath(absolute, root).replace(os.sep, "/")
            # A replace pointing back INSIDE the service is copied by the service's own
            # COPY line; it is not a shared-module dependency at all.
            if repo_rel.startswith(f"services/{service}/"):
                continue
            checked += 1
            if _satisfied(repo_rel, sources):
                continue
            if whole and whole_context_covers(ctx, repo_rel):
                continue
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


# alert-recorder's real shape: a source with `../..`, which Docker resolves from the CONTEXT
# ROOT and therefore never finds. It NAMES the target, which is why it read as correct.
_DOCKERFILE_ESCAPES = """FROM golang:1.25-alpine AS build
WORKDIR /src
COPY ../../sdks/go/thing /src/sdks/go/thing
COPY ../../contracts/other /src/contracts/other
COPY . /src
RUN go mod download
"""


def _write_tree(root: str, dockerfile: str, context: str | None = None,
                dockerfile_path: str = "services/selftest-service/Dockerfile") -> None:
    """`context` writes an infra/ compose file DECLARING the build context.

    Added 2026-08-30 with the amendment: `COPY . .` is coverage only under a context that
    contains the target, so a case that does not say what its context is cannot assert
    either verdict. `None` = no declared image build, which is canary-controller's shape.
    """
    service = os.path.join(root, "services", "selftest-service")
    os.makedirs(service, exist_ok=True)
    for shared in ("sdks/go/thing", "contracts/other"):
        os.makedirs(os.path.join(root, shared), exist_ok=True)
    with open(os.path.join(service, "go.mod"), "w", encoding="utf-8") as fh:
        fh.write(_SELFTEST_GOMOD)
    with open(os.path.join(service, "Dockerfile"), "w", encoding="utf-8") as fh:
        fh.write(dockerfile)
    if context is not None:
        infra = os.path.join(root, "infra")
        os.makedirs(infra, exist_ok=True)
        with open(os.path.join(infra, "docker-compose.yml"), "w", encoding="utf-8") as fh:
            fh.write("services:\n  selftest-service:\n    build:\n"
                     "      context: " + context + "\n"
                     "      dockerfile: " + dockerfile_path + chr(10))


def selftest() -> int:
    cases = [
        ("every replace copied", _DOCKERFILE_GOOD, 0, 2, None),
        ("one shared module never copied", _DOCKERFILE_MISSING, 1, 2, None),
        ("an ANCESTOR copy satisfies it", _DOCKERFILE_ANCESTOR, 0, 2, None),
        # ── the amendment, 2026-08-30 ────────────────────────────────────────────────
        # `COPY . .` used to be an unconditional exemption. It reported 0 violations while
        # two services could not be built, so each of these three says WHICH context.
        ("COPY . under a REPO-ROOT context takes everything",
         _DOCKERFILE_WHOLE_CONTEXT, 0, 2, ".."),
        ("COPY . under the SERVICE-DIR context takes only the service — alert-recorder",
         _DOCKERFILE_WHOLE_CONTEXT, 2, 2, "../services/selftest-service"),
        ("COPY . with NO declared build at all is not coverage — canary-controller",
         _DOCKERFILE_WHOLE_CONTEXT, 2, 2, None),
        ("a COPY source that ESCAPES the context is a defect in every context",
         _DOCKERFILE_ESCAPES, 2, 2, ".."),
    ]
    failures: list[str] = []
    for label, dockerfile, want_violations, want_checked, context in cases:
        tmp = tempfile.mkdtemp(prefix="dfrc-gate-")
        try:
            _write_tree(tmp, dockerfile, context)
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
