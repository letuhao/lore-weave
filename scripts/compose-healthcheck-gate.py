#!/usr/bin/env python3
"""A healthcheck must declare `start_period`, and a readiness check must test READINESS.

    python scripts/compose-healthcheck-gate.py
    python scripts/compose-healthcheck-gate.py --self-test

🔴 THE COLD START THIS CLOSES, measured 2026-09-13 on the `lw-iso` stack's first `up`.

`provider-registry-service` declares `depends_on: rabbitmq: condition: service_healthy`, and it
still came up to a closed port:

    amqp dial: dial tcp 172.20.0.5:5672: connect: connection refused     (x7, over 18 seconds)

Two independent defects, and the run needed both to fail.

**1. `service_healthy` did not mean ready.** rabbitmq's healthcheck was `rabbitmq-diagnostics
ping`, and rabbitmq's own help says ping *"Checks that the node OS process is up, registered with
EPMD and CLI tools can authenticate with it"* — **nothing about listeners**. It goes green while
5672 is still closed. `check_port_connectivity` is *"Basic TCP connectivity health check for each
listener's port"*, which is the question `depends_on` is actually asking.

**2. No `start_period`.** Docker counts health failures from t=0, so a service that is merely
STARTING gets reported unhealthy. provider-registry-service needed ~18s while it retried rabbitmq;
`interval: 10s, retries: 3` exhausts at ~30s. It was a dead heat, and compose lost it — *"dependency
failed to start: container lw-iso-provider-registry-service-1 is unhealthy"* aborted the whole
`up`, leaving the frontend and every downstream service unstarted. Thirty seconds later the same
container was `Up (healthy)`.

**The failure looks like a broken service and is a broken WAIT.** Worse, it is intermittent: the
long-running dev stack's volumes are never cold, so it never reproduces there — the same shape as
the `rabbitmq start_period: 75s` note already in the compose file, which was found the same way.

WHAT IT CHECKS
  H-1 · every `healthcheck` declares `start_period`.
  H-2 · no readiness check uses a liveness-only probe (a curated list of known-wrong commands).

Exit 0 = clean; 1 = a finding; 2 = misuse / self-test failure.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_FILES = [REPO / "infra" / "docker-compose.yml",
                 REPO / "infra" / "docker-compose.isolated.yml"]

#: Commands that answer "is the process alive" when the caller is asking "can I connect".
#: value = (what it actually checks, what to use instead)
LIVENESS_ONLY = {
    "rabbitmq-diagnostics ping": (
        "the Erlang node answers EPMD and CLI auth -- NOT that any listener is bound",
        "rabbitmq-diagnostics -q check_port_connectivity"),
    "rabbitmq-diagnostics -q ping": (
        "the Erlang node answers EPMD and CLI auth -- NOT that any listener is bound",
        "rabbitmq-diagnostics -q check_port_connectivity"),
}

SVC_RE = re.compile(r'^  ([a-z][a-z0-9-]*):\n((?:    .*\n|\n)*)', re.M)


def services_with_healthchecks(text: str) -> dict[str, str]:
    """{service: healthcheck block}. Pure — takes text, so the self-test needs no file."""
    out: dict[str, str] = {}
    for m in SVC_RE.finditer(text):
        name, body = m.group(1), m.group(2)
        if "healthcheck:" not in body:
            continue
        h = body.index("healthcheck:")
        nxt = re.search(r'\n    [a-z_]+:', body[h:])
        out[name] = body[h: h + (nxt.start() if nxt else len(body) - h)]
    return out


def findings(text: str) -> tuple[list[str], list[tuple[str, str, str]]]:
    """(services missing start_period, [(service, matched command, why)])."""
    missing, liveness = [], []
    for name, block in services_with_healthchecks(text).items():
        if "start_period" not in block:
            missing.append(name)
        flat = " ".join(re.findall(r'"([^"]+)"', block))
        for cmd, (why, fix) in LIVENESS_ONLY.items():
            parts = cmd.split()
            if all(p in flat.split() for p in parts) and "check_port_connectivity" not in flat:
                liveness.append((name, cmd, f"{why}. Use: {fix}"))
                break
    return sorted(missing), sorted(liveness)


def self_test() -> int:
    fails: list[str] = []

    bad = (
        "services:\n"
        "  alpha:\n"
        "    image: x\n"
        "    healthcheck:\n"
        '      test: ["CMD", "wget", "-qO-", "http://localhost:1/health"]\n'
        "      interval: 10s\n"
        "      retries: 3\n"
        "  beta:\n"
        "    image: y\n"
        "    healthcheck:\n"
        '      test: ["CMD", "rabbitmq-diagnostics", "ping"]\n'
        "      interval: 5s\n"
        "      retries: 10\n"
        "      start_period: 75s\n"
    )
    miss, live = findings(bad)
    if miss != ["alpha"]:
        fails.append(f"did not flag the healthcheck with no start_period (got {miss})")
    if not any(n == "beta" for n, _, _ in live):
        fails.append("did not flag `rabbitmq-diagnostics ping` as a liveness-only probe (vacuous)")

    good = (
        "services:\n"
        "  alpha:\n"
        "    image: x\n"
        "    healthcheck:\n"
        '      test: ["CMD", "wget", "-qO-", "http://localhost:1/health"]\n'
        "      interval: 10s\n"
        "      retries: 3\n"
        "      start_period: 30s\n"
        "  beta:\n"
        "    image: y\n"
        "    healthcheck:\n"
        '      test: ["CMD", "rabbitmq-diagnostics", "-q", "check_port_connectivity"]\n'
        "      interval: 5s\n"
        "      retries: 10\n"
        "      start_period: 75s\n"
    )
    miss2, live2 = findings(good)
    if miss2:
        fails.append(f"flagged a compliant healthcheck as missing start_period: {miss2}")
    if live2:
        fails.append(f"flagged check_port_connectivity as liveness-only: {live2}")

    # A service with NO healthcheck must not be flagged -- the gate is about checks that exist.
    none = "services:\n  gamma:\n    image: z\n    ports:\n      - \"1:1\"\n"
    if findings(none) != ([], []):
        fails.append("flagged a service that declares no healthcheck at all")

    if fails:
        print("compose-healthcheck-gate SELF-TEST FAILED:")
        for f in fails:
            print(f"  - {f}")
        return 2
    print("compose-healthcheck-gate: self-test OK — flags a missing start_period AND a "
          "liveness-only probe, and stays quiet on a compliant check and on a service with none")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--file", action="append")
    a = ap.parse_args()
    if a.self_test:
        return self_test()

    files = [Path(f) for f in a.file] if a.file else DEFAULT_FILES
    files = [f for f in files if f.exists()]
    if not files:
        print("compose-healthcheck-gate: FAIL — no compose file found. The SCAN is empty, "
              "not the tree.")
        return 1

    rc, total = 0, 0
    for f in files:
        text = f.read_text(encoding="utf-8")
        checks = services_with_healthchecks(text)
        total += len(checks)
        miss, live = findings(text)
        if miss:
            rc = 1
            print(f"\n{f.name}: {len(miss)} healthcheck(s) with NO start_period:\n")
            for n in miss:
                print(f"  {n}")
            print("\n  Docker counts failures from t=0, so a STARTING service reads as unhealthy —")
            print("  and a `depends_on: service_healthy` turns that into an aborted `up` for")
            print("  everything downstream. Give it a start_period above its real startup time.")
        if live:
            rc = 1
            print(f"\n{f.name}: {len(live)} readiness check(s) using a LIVENESS-only probe:\n")
            for n, cmd, why in live:
                print(f"  {n}: `{cmd}`")
                print(f"      {why}")
            print("\n  `condition: service_healthy` promises the dependency is USABLE. A probe that")
            print("  only proves the process exists makes that promise false, and the caller meets")
            print("  a closed port while compose reports everything healthy.")

    if rc == 0:
        print(f"compose-healthcheck-gate: OK — {total} healthcheck(s) across {len(files)} file(s); "
              f"each declares a start_period and none uses a liveness-only probe as a readiness "
              f"check.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
