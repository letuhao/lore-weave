#!/usr/bin/env python3
"""Pull the service logs for ONE e2e step, by trace id — not by guessing a time window.

WHY
───
Finding "the log lines for the click that failed" used to mean `docker logs --since 2m` across a
dozen containers and reading past everything else that happened in that minute. On a stack with
background jobs, outbox relays and a scheduler, that is a hope rather than a method.

Every Python service accepts an `x-trace-id` header and reuses a well-formed value
(`middleware/trace_id.py`); since 2026-09-04 the frontend sends one, and an e2e run pins a
LABELLED id per step (`write-ch3.9f2a…`). So this asks for that exact token and gets that step's
requests, across every service that handled them.

    python scripts/e2e/collect_run_evidence.py --trace write-ch3.9f2a1c…  --out evidence/ch3
    python scripts/e2e/collect_run_evidence.py --label newbook --out evidence/run   # whole run
    python scripts/e2e/collect_run_evidence.py --since 10m --out evidence/window    # fallback

🔴 SILENCE IS REPORTED, NEVER PRINTED AS SUCCESS. A collector that writes an empty file and exits
0 tells you the step was clean when it may mean the id never reached the server, the container
name changed, or the frontend build predates the header. `--trace`/`--label` with zero matches is
exit 2 (MISUSE) and says which of those to check. This repo has already paid for a gate that
"reported a clean scan of nothing".

WHAT IT DOES NOT DO. It does not parse or judge the lines — a collector that decided what counted
as an error would be a second opinion nobody asked for, and would hide the line it did not
recognise. It writes what matched, per service, plus one merged file in timestamp order.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
from datetime import datetime, timezone

#: Compose projects this repo runs. `lw-iso` is the isolated stack the e2e suite targets.
KNOWN_PROJECTS = ("lw-iso", "infra")

#: A timestamp at the head of a log line, in the shapes these services emit. Used ONLY to order
#: the merged file; a line without one keeps its service-local position rather than being dropped.
_TS = re.compile(r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)")


def containers(project: str) -> list[str]:
    out = subprocess.run(
        ["docker", "ps", "--filter", f"name={project}-", "--format", "{{.Names}}"],
        capture_output=True, text=True, timeout=30,
    )
    return sorted(n for n in out.stdout.split() if n)


def logs_for(container: str, since: str | None) -> str:
    cmd = ["docker", "logs", container]
    if since:
        cmd += ["--since", since]
    # stderr is where most of these services log; merging is the point, not a convenience.
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return (out.stdout or "") + (out.stderr or "")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sel = ap.add_mutually_exclusive_group(required=True)
    sel.add_argument("--trace", help="one exact trace id — a single step")
    sel.add_argument("--label", help="a step-label prefix — every step of a run")
    sel.add_argument("--since", help="docker --since window, e.g. 10m (NO correlation; a fallback)")
    ap.add_argument("--project", default="lw-iso", choices=KNOWN_PROJECTS)
    ap.add_argument("--out", required=True, help="directory to write the evidence into")
    ap.add_argument("--window", default="20m",
                    help="bound a --trace/--label scan by a docker --since window (default 20m); "
                         "widen it for an older run")
    ap.add_argument("--all-history", action="store_true",
                    help="scan each container's FULL log. Slow: unbounded across this stack's 35 "
                         "containers did not finish inside two minutes, which is why --window has "
                         "a default at all.")
    args = ap.parse_args()

    names = containers(args.project)
    if not names:
        print(f"collect-run-evidence: MISUSE — no running containers named `{args.project}-*`. "
              f"The stack is down, or the compose project is not the one you think.",
              file=sys.stderr)
        return 2

    needle = args.trace or args.label
    # 🔴 A DEFAULT WINDOW, AND THIS TOOL'S OWN FIRST RUN IS WHY. Unbounded, `docker logs` reads
    # each container's entire history; across this stack's 35 containers that did not finish
    # inside two minutes. A correlation tool nobody waits for is a tool nobody uses. The window
    # in force is recorded in the manifest and named in the miss message, so a scan that looked
    # past an older run says what it read rather than reporting an absence.
    since = args.since or (None if args.all_history else args.window)
    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    per_service: dict[str, list[str]] = {}
    for c in names:
        text = logs_for(c, since)
        if needle:
            hits = [ln for ln in text.splitlines() if needle in ln]
        else:
            hits = text.splitlines()
        if hits:
            per_service[c] = hits

    total = sum(len(v) for v in per_service.values())

    # ── THE FLOOR. Only for a correlated ask: `--since` legitimately returns nothing when the
    # window is quiet, but `--trace`/`--label` returning nothing means the correlation FAILED,
    # and the three causes below are worth naming because each looks identical from here.
    if needle and total == 0:
        print(
            f"collect-run-evidence: MISUSE — `{needle}` appears in NO log line across "
            f"{len(names)} container(s) in `{args.project}`.\n\n"
            f"  That is not 'the step was clean'. Check, in this order:\n"
            f"    1. Is the FRONTEND IMAGE rebuilt? The header ships in the bundle; a container\n"
            f"       serving a build from before 2026-09-04 sends no `x-trace-id` at all.\n"
            f"    2. Did the step actually pin the id? `window.__LW_TRACE_ID__` must be set\n"
            f"       BEFORE the request, and it is ignored unless it matches\n"
            f"       ^[A-Za-z0-9._-]{{1,128}}$ — an id the server rejects is replaced silently.\n"
            f"    3. Is the request served by a service that logs the trace id? The Go services\n"
            f"       accept the header; not all of them echo it into every line.\n"
            f"    4. Is the WINDOW too narrow? This scan read `--since {since}`. An older run\n"
            f"       needs a wider --window, or --all-history.\n",
            file=sys.stderr)
        return 2

    merged: list[tuple[str, str, str]] = []
    for c, hits in per_service.items():
        short = c.replace(f"{args.project}-", "").rsplit("-", 1)[0]
        (out_dir / f"{short}.log").write_text("\n".join(hits) + "\n", encoding="utf-8")
        for ln in hits:
            m = _TS.search(ln)
            merged.append((m.group(1).replace(" ", "T") if m else "", short, ln))

    # Stable: lines without a timestamp sort first and keep their arrival order, rather than
    # being dropped for not matching a format this collector does not own.
    merged.sort(key=lambda r: r[0])
    (out_dir / "timeline.log").write_text(
        "\n".join(f"{svc:<24} {ln}" for _ts, svc, ln in merged) + "\n", encoding="utf-8")

    manifest = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "project": args.project,
        "selector": {"trace": args.trace, "label": args.label,
                     "since": args.since, "window_used": since},
        "containers_scanned": len(names),
        "containers_with_hits": len(per_service),
        "lines": total,
        "per_service": {k.replace(f"{args.project}-", ""): len(v) for k, v in per_service.items()},
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"collect-run-evidence: {total} line(s) from {len(per_service)} of {len(names)} "
          f"container(s) -> {out_dir}/")
    for svc, n in sorted(manifest["per_service"].items(), key=lambda kv: -kv[1]):
        print(f"    {n:5d}  {svc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
