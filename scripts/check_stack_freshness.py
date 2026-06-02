#!/usr/bin/env python3
"""Stale-image / artifact-behind-HEAD guard (F-LIVE-1).

Catches the recurring failure where `docker compose up -d` recreates a service
from a STALE local image whose /health is constant-ok, so the container reports
healthy while a critical route 404s (ContextHub lesson e16b6f02).

Two checks, both non-fatal when docker/git is unavailable (exit 3):

  DRIFT — per running `infra-<svc>-1` container, is the image behind the service's
    source? Tier 2 (precise) when the image carries an `org.loreweave.git_sha`
    LABEL: `git diff --quiet <sha> HEAD -- services/<svc> sdks contracts` → STALE
    if changes exist. Tier 1 (proxy) otherwise: image `.Created` vs the last commit
    touching `services/<svc>/` → STALE if the image predates it.

  PROBE — the H0-critical internal routes must return ≠404 on the running stack
    (404 = the route is missing = stale/broken deploy).

Exit: 0 = all fresh + routes present · 1 = stale/missing found · 3 = docker/git
unavailable (skip — never breaks an offline run). Advisory by default.

Usage:
  python scripts/check_stack_freshness.py [--drift-only|--probe-only]
                                          [--services a,b] [--quiet]
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

GIT_SHA_LABEL = "org.loreweave.git_sha"

# Map a running compose service → the repo source paths whose change should
# invalidate its image. `services/<name>` always; shared dirs are diffed too
# (cheap + precise under the SHA tier; the timestamp tier uses the service dir).
SHARED_PATHS = ["sdks", "contracts"]

# H0-critical internal routes that silently 404 on a stale image. host_env is the
# env var carrying the host base URL; default is the documented host port.
PROBE_ROUTES = [
    ("knowledge-service", "KNOWLEDGE_SERVICE_URL_H", "http://localhost:8216",
     ["/internal/knowledge/enriched-writeback",
      "/internal/knowledge/enriched-promote",
      "/internal/knowledge/enriched-retract"]),
    ("glossary-service", "GLOSSARY_SERVICE_URL_H", "http://localhost:8211",
     ["/internal/books/00000000-0000-0000-0000-000000000000/entities/"
      "00000000-0000-0000-0000-000000000000/enrichments"]),
    # LE-061: the embed seam every retrieval/enrichment path depends on. A POST
    # with an empty body returns a 4xx (validation), not 404 — so this catches a
    # provider-registry image so stale the route is gone. (It does NOT catch a
    # behavioural bug like the /v1 double-path; that class is covered by tier-2
    # SHA-drift, which requires the image to be SHA-stamped — see drift_note.)
    ("provider-registry-service", "PROVIDER_REGISTRY_URL_H", "http://localhost:8208",
     ["/internal/embed"]),
]


# ── pure decision logic (unit-testable, no IO) ───────────────────────────────

def _parse_iso(ts: str) -> datetime | None:
    """Parse a docker/git ISO-8601 timestamp to an aware datetime, or None."""
    ts = (ts or "").strip()
    if not ts:
        return None
    # docker .Created can be '2026-05-30T11:18:21.246Z' with nanos; trim to micros.
    ts = ts.replace("Z", "+00:00")
    if "." in ts:
        head, _, tail = ts.partition(".")
        frac = "".join(c for c in tail if c.isdigit())[:6]
        off = tail[len(frac):] if len(tail) > len(frac) else ""
        # recover any +HH:MM offset that followed the fractional seconds
        for sign in ("+", "-"):
            if sign in tail:
                off = sign + tail.split(sign, 1)[1]
                break
        ts = f"{head}.{frac or '0'}{off}"
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def decide_drift_by_time(image_created_iso: str, last_commit_iso: str) -> str:
    """Tier-1: 'stale' if the image was built BEFORE the service's last commit,
    'fresh' if at/after, 'unknown' if either timestamp won't parse."""
    img = _parse_iso(image_created_iso)
    commit = _parse_iso(last_commit_iso)
    if img is None or commit is None:
        return "unknown"
    return "stale" if img < commit else "fresh"


def drift_note(has_sha_label: bool) -> str:
    """A first-party image with NO ``org.loreweave.git_sha`` label was built
    OUTSIDE ``build-stack.sh``, so the precise tier-2 SHA-drift check can't run —
    only the coarse ``.Created``-vs-last-commit timestamp proxy, which a rebuilt-
    for-unrelated-reasons image can pass while still carrying stale code. This is
    exactly how the provider-registry embed ``/v1`` staleness went undetected
    (LE-061). Empty when the image IS stamped (tier-2 available)."""
    if has_sha_label:
        return ""
    return "UNSTAMPED (built outside build-stack.sh → drift=tier-1 proxy only) "


def decide_status(drift: str, probe_ok: bool | None) -> str:
    """Combine a service's drift verdict + (optional) probe into one status."""
    if drift == "stale":
        return "STALE"
    if probe_ok is False:
        return "ROUTE-MISSING"
    if drift == "unknown":
        return "UNKNOWN"
    return "FRESH"


# ── docker / git probes (IO) ──────────────────────────────────────────────────

def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return 127, ""
    return p.returncode, (p.stdout or "").strip()


def docker_available() -> bool:
    rc, _ = _run(["docker", "version", "--format", "{{.Server.Version}}"])
    return rc == 0


def running_services() -> list[str]:
    """Compose services with a running `infra-<svc>-1` container → <svc>."""
    rc, out = _run(["docker", "ps", "--format", "{{.Names}}"])
    if rc != 0:
        return []
    svcs = []
    for name in out.splitlines():
        name = name.strip()
        if name.startswith("infra-") and name.endswith("-1"):
            svcs.append(name[len("infra-"):-len("-1")])
    return sorted(set(svcs))


def image_created(container: str) -> str:
    rc, img = _run(["docker", "inspect", "--format", "{{.Image}}", container])
    if rc != 0 or not img:
        return ""
    rc, created = _run(["docker", "image", "inspect", "--format", "{{.Created}}", img])
    return created if rc == 0 else ""


def image_git_sha(container: str) -> str:
    rc, img = _run(["docker", "inspect", "--format", "{{.Image}}", container])
    if rc != 0 or not img:
        return ""
    rc, sha = _run(["docker", "image", "inspect", "--format",
                    '{{ index .Config.Labels "' + GIT_SHA_LABEL + '" }}', img])
    sha = sha.strip()
    return "" if (rc != 0 or sha in ("", "<no value>", "unknown")) else sha


def last_commit_iso(paths: list[str]) -> str:
    rc, out = _run(["git", "log", "-1", "--format=%cI", "--"] + paths)
    return out if rc == 0 else ""


def sha_has_drift(image_sha: str, paths: list[str]) -> str:
    """Tier-2: 'fresh' if no tracked change in `paths` between image_sha and HEAD;
    'stale' if there are changes; 'unknown' if the sha isn't known to git."""
    if _run(["git", "cat-file", "-e", image_sha + "^{commit}"])[0] != 0:
        return "unknown"
    rc, _ = _run(["git", "diff", "--quiet", image_sha, "HEAD", "--"] + paths)
    if rc == 0:
        return "fresh"
    if rc == 1:
        return "stale"
    return "unknown"


def probe_route(base: str, path: str, token: str) -> bool:
    """True if the route EXISTS (any status ≠ 404). A 404 = missing route."""
    req = urllib.request.Request(base.rstrip("/") + path, method="POST",
                                 data=b"{}",
                                 headers={"Content-Type": "application/json",
                                          "X-Internal-Token": token})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status != 404
    except urllib.error.HTTPError as e:
        return e.code != 404
    except (urllib.error.URLError, TimeoutError, OSError):
        return True  # service unreachable ≠ route-missing — don't false-flag here


# ── orchestration ────────────────────────────────────────────────────────────

def check_drift(services: list[str]) -> list[tuple[str, str, str]]:
    rows = []
    for svc in services:
        # Only first-party COMPOSE-BUILT services have a source dir; pulled images
        # (postgres/redis/neo4j/…) and name-mismatched workers have none → skip
        # (they are not built from this repo, so "behind HEAD" is meaningless).
        if not os.path.isdir(os.path.join("services", svc)):
            continue
        container = f"infra-{svc}-1"
        paths = [f"services/{svc}"] + SHARED_PATHS
        sha = image_git_sha(container)
        if sha:
            drift = sha_has_drift(sha, paths)
            detail = f"sha={sha[:10]} (tier-2)"
        else:
            created = image_created(container)
            # tier-1 proxy uses the SERVICE dir only (shared-path timestamps would
            # over-flag every service on any sdk change).
            drift = decide_drift_by_time(created, last_commit_iso([f"services/{svc}"]))
            # LE-061: flag the degraded-detection (unstamped) case so an operator
            # sees WHY a stale binary could slip the tier-1 proxy.
            detail = drift_note(False) + (
                f"built={created[:19]} (tier-1)" if created else "no image meta"
            )
        rows.append((svc, drift, detail))
    return rows


def check_probes(services_filter: list[str] | None) -> list[tuple[str, str, bool]]:
    rows = []
    token = os.environ.get("INTERNAL_SERVICE_TOKEN", "dev_internal_token")
    for svc, env, default, routes in PROBE_ROUTES:
        if services_filter and svc not in services_filter:
            continue
        base = os.environ.get(env, default)
        for path in routes:
            present = probe_route(base, path, token)
            rows.append((svc, path, present))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Stale-image / behind-HEAD guard (F-LIVE-1)")
    ap.add_argument("--drift-only", action="store_true")
    ap.add_argument("--probe-only", action="store_true")
    ap.add_argument("--services", default="", help="comma-separated filter")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if not docker_available():
        print("[stack-freshness] docker/git unavailable — SKIP (advisory, exit 3)",
              file=sys.stderr)
        return 3

    flt = [s.strip() for s in args.services.split(",") if s.strip()] or None
    bad = False

    if not args.probe_only:
        svcs = flt or running_services()
        drift_rows = check_drift(svcs)
        unstamped = []
        for svc, drift, detail in drift_rows:
            status = decide_status(drift, None)
            if status in ("STALE",):
                bad = True
            if detail.startswith("UNSTAMPED"):
                unstamped.append(svc)
            if not args.quiet or status != "FRESH":
                print(f"[drift] {status:<8} {svc:<28} {detail}")
        if unstamped:
            # Advisory (does not fail the run): precise drift detection is degraded
            # for these — rebuild them via scripts/build-stack.sh to SHA-stamp.
            print("[stack-freshness] WARN: unstamped first-party image(s) "
                  f"(drift=tier-1 proxy only): {', '.join(unstamped)} — rebuild via "
                  "scripts/build-stack.sh to enable precise SHA-drift detection",
                  file=sys.stderr)

    if not args.drift_only:
        probe_rows = check_probes(flt)
        for svc, path, present in probe_rows:
            if not present:
                bad = True
                print(f"[probe] ROUTE-MISSING (404) {svc}{path}  → image is stale/broken")
            elif not args.quiet:
                print(f"[probe] present            {svc}{path}")

    if bad:
        print("[stack-freshness] STALE/MISSING detected — rebuild the affected "
              "service(s): docker compose build <svc> && docker compose up -d <svc>",
              file=sys.stderr)
        return 1
    if not args.quiet:
        print("[stack-freshness] OK — running images fresh + H0 routes present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
