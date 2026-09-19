#!/usr/bin/env python3
"""why-red — gather everything about one failed test into one folder.

    python scripts/e2e/why-red.py <run-id> "<part of the test title>"
    python scripts/e2e/why-red.py latest "<part of the test title>"
    python scripts/e2e/why-red.py --self-test

For a test recorded by scripts/e2e/run-evidence-suite.py, it writes
`frontend/tests/e2e/runs/<run-id>/why-red/<slug>/` with:
  1. trace.txt   the test's trace, screenshot and video paths (kept by the runner, so a later
                 re-run cannot have erased them);
  2. logs/       every lw-iso container's log lines inside the test's time window (±15 s),
                 plus one merged timeline.log;
  3. llm_jobs.tsv  the LLM jobs that started in that window: usage purpose, model, status, error;
  4. clock.txt   the clock steps the run's preflight measured.

WHY (plan 2026-09-19, T7). Every red in the v0.1.0 run took a hand investigation: find the
trace, find the service logs for that minute, query `llm_jobs`, and remember whether the VM clock
had stepped. Two reds still have no cause because that evidence was never assembled. This does it
in one command.

Read-only: `docker logs` and a `SELECT` on the throwaway stack's provider-registry DB.
Exit: 0 ok · 1 the test is not in the ledger or did not fail · 2 misuse / self-test failed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUNS = REPO / "frontend" / "tests" / "e2e" / "runs"
LEDGER = RUNS / "LEDGER.jsonl"
PAD_S = 15


def sh(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "test"


def parse_utc(s: str) -> dt.datetime:
    s = s.strip().replace("Z", "+00:00")
    if "." in s:
        head, rest = s.split(".", 1)
        frac, _, tz = rest.partition("+")
        s = f"{head}.{frac[:6]}+{tz}" if tz else f"{head}.{frac[:6]}"
    t = dt.datetime.fromisoformat(s)
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def window(row: dict) -> tuple[dt.datetime, dt.datetime]:
    start = parse_utc(row["start"])
    end = start + dt.timedelta(milliseconds=row.get("duration_ms") or 0)
    return start - dt.timedelta(seconds=PAD_S), end + dt.timedelta(seconds=PAD_S)


def find_row(rows: list[dict], run: str, needle: str) -> dict | None:
    """The FAILED row of `run` whose title contains `needle` (case-insensitive)."""
    needle = needle.lower()
    hits = [r for r in rows if r.get("kind") == "test" and r.get("run") == run
            and needle in (r.get("title") or "").lower() and r.get("status") not in ("passed", "skipped")]
    return hits[-1] if hits else None


def read_ledger() -> list[dict]:
    if not LEDGER.exists():
        return []
    return [json.loads(l) for l in LEDGER.read_text(encoding="utf-8").splitlines() if l.strip()]


def collect_logs(project: str, since: dt.datetime, until: dt.datetime, out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    names = [n for n in sh(["docker", "ps", "--filter", f"name={project}-", "--format", "{{.Names}}"]).stdout.split() if n]
    merged: list[str] = []
    for n in names:
        r = sh(["docker", "logs", "--timestamps", "--since", since.isoformat(), "--until", until.isoformat(), n])
        lines = [l for l in (r.stdout + r.stderr).splitlines() if l.strip()]
        if lines:
            (out / f"{n}.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
            merged += [f"{l.split(' ', 1)[0]} {n} {l.split(' ', 1)[1] if ' ' in l else ''}" for l in lines]
    merged.sort()
    (out / "timeline.log").write_text("\n".join(merged) + "\n", encoding="utf-8")
    return len(merged)


def llm_jobs(since: dt.datetime, until: dt.datetime) -> str:
    sql = ("select started_at, job_meta->>'usage_purpose', model_ref, status, coalesce(error_code,''), "
           r"regexp_replace(left(coalesce(error_message,''),240), '\s+', ' ', 'g') from llm_jobs "
           f"where started_at between '{since.isoformat()}' and '{until.isoformat()}' order by started_at")
    r = sh(["docker", "exec", "lw-iso-postgres-1", "psql", "-U", "loreweave", "-d", "loreweave_provider_registry",
            "-At", "-F", "\t", "-c", sql])
    return r.stdout if r.returncode == 0 else f"(query failed: {r.stderr.strip()[:200]})\n"


def self_test() -> int:
    ok = True

    def check(name: str, cond: bool) -> None:
        nonlocal ok
        print(f"  {'ok  ' if cond else 'FAIL'} {name}")
        ok = ok and cond

    rows = [
        {"kind": "test", "run": "r1", "title": "a.spec › does the thing", "status": "passed"},
        {"kind": "test", "run": "r1", "title": "a.spec › does the OTHER thing", "status": "failed",
         "start": "2026-09-19T05:00:00.000Z", "duration_ms": 2000},
        {"kind": "test", "run": "r2", "title": "a.spec › does the other thing", "status": "failed",
         "start": "2026-09-19T06:00:00Z", "duration_ms": 0},
    ]
    r = find_row(rows, "r1", "other thing")
    check("finds the failed row of the right run", r is not None and r["start"].startswith("2026-09-19T05"))
    check("a passed test is not a red", find_row(rows, "r1", "does the thing") is None)
    lo, hi = window(rows[1])
    check("the window pads the test by 15 s each side",
          (hi - lo).total_seconds() == 2 + 2 * PAD_S and lo.isoformat().startswith("2026-09-19T04:59:45"))
    check("slug is filesystem-safe", slug("a.spec › does the OTHER thing!") == "a-spec-does-the-other-thing")
    print("self-test:", "OK" if ok else "FAILED")
    return 0 if ok else 2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("run", nargs="?")
    ap.add_argument("title", nargs="?")
    ap.add_argument("--project", default="lw-iso")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    if not a.run or not a.title:
        ap.print_usage()
        return 2
    rows = read_ledger()
    run = a.run
    if run == "latest":
        runs = [r["run"] for r in rows if r.get("kind") == "run"]
        run = runs[-1] if runs else ""
    row = find_row(rows, run, a.title)
    if not row:
        print(f"why-red: no failed test matching {a.title!r} in run {run!r} ({LEDGER.relative_to(REPO)})")
        return 1
    since, until = window(row)
    out = RUNS / run / "why-red" / slug(row["title"])
    out.mkdir(parents=True, exist_ok=True)
    att = row.get("attachments") or {}
    (out / "trace.txt").write_text(
        f"test:   {row['title']}\nstatus: {row['status']}\nerror:  {row.get('error')}\n"
        f"window: {since.isoformat()} .. {until.isoformat()}\n"
        + "".join(f"{k}: {v}\n" for k, v in att.items())
        + (f"\nopen it: npx playwright show-trace \"{att['trace']}\"\n" if "trace" in att else "\n(no trace recorded)\n"),
        encoding="utf-8")
    n = collect_logs(a.project, since, until, out / "logs")
    (out / "llm_jobs.tsv").write_text(llm_jobs(since, until), encoding="utf-8")
    pre = RUNS / run / "preflight.json"
    steps = (json.loads(pre.read_text(encoding="utf-8")).get("clock") or {}).get("steps") if pre.exists() else None
    (out / "clock.txt").write_text(
        f"clock steps measured by this run's preflight (seconds into the probe, size): {steps}\n"
        "A backward step can reorder time-ordered data (DEFERRED #164).\n", encoding="utf-8")
    print(f"why-red: {row['title']}")
    print(f"  trace   {att.get('trace', '(none)')}")
    print(f"  logs    {n} line(s) from the stack in {since:%H:%M:%S}..{until:%H:%M:%S} UTC")
    print(f"  llm     {sum(1 for l in (out / 'llm_jobs.tsv').read_text(encoding='utf-8').splitlines() if l.strip())} job(s)")
    print(f"  clock   {steps}")
    print(f"  -> {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
