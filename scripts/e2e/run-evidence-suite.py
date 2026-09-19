#!/usr/bin/env python3
"""run-evidence-suite — run the Playwright E2E suite so that every run leaves evidence.

    python scripts/e2e/run-evidence-suite.py                    # preflight + full suite + ledger
    python scripts/e2e/run-evidence-suite.py --preflight-only   # just the checks
    python scripts/e2e/run-evidence-suite.py -- specs/foo.spec.ts --grep bar   # passthrough
    python scripts/e2e/run-evidence-suite.py --self-test

WHY THIS EXISTS (plan docs/plans/2026-09-19-evidence-runner-and-model-lease.md, T5).
Getting the v0.1.0 suite green took six full runs, and every red cost a hand investigation.
The causes were not in the product under test:
  - the Docker VM's wall clock stepping back 1.4 s every 30 s;
  - a knowledge scheduler firing 10 minutes after a restart and asking the one local model
    server for a second model mid-run;
  - uncommitted edits baked into a test image;
  - a solo re-run that wiped `test-results/`, and with it the only trace of a red.
Two reds still have no cause because their evidence was gone.

So this wrapper:
  1. PREFLIGHT, which WARNS AND RECORDS but never refuses (PO decision Q3):
     - clock steps (60 s probe inside a stack container);
     - schedulers due during the run;
     - models loaded in LM Studio (a READ; this never loads or unloads anything);
     - image provenance: git sha, dirty scope, and staleness against HEAD.
  2. RUN, with `--output runs/<run-id>/results`, which is outside `test-results/`, so no later
     run can erase it. `--trace=retain-on-failure` is on.
  3. LEDGER: append one line per test and one line per run to `runs/LEDGER.jsonl`, so "failed
     once in N runs" is a fact on record rather than a memory.

It is deliberately NOT named *-gate / *-lint: gate-wiring-gate --run-all would run it in CI with
no stack. It writes nothing to any database. Loopback targets only.

Exit: the Playwright exit code for a run (0 = all passed); 0 for --preflight-only; 2 for misuse
or a failed self-test.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FRONTEND = REPO / "frontend"
RUNS = FRONTEND / "tests" / "e2e" / "runs"
LEDGER = RUNS / "LEDGER.jsonl"

#: Background loops that start a fixed delay after their container starts, then repeat.
#: Measured from the code 2026-09-19 (knowledge-service app/jobs/*). A run that overlaps one of
#: these can collide with the suite's own model use (plan 2026-09-18 Cycle 9: summary regen at
#: +600 s asked for a second model and LM Studio aborted both loads).
SCHEDULERS: dict[str, list[tuple[str, int, int]]] = {
    "knowledge-service": [
        ("anchor refresh", 300, 24 * 3600),
        ("summary regen (project)", 600, 24 * 3600),
        ("summary regen (global)", 900, 7 * 24 * 3600),
        ("job logs retention", 1200, 24 * 3600),
        ("reconcile evidence count", 1500, 24 * 3600),
        ("quarantine cleanup", 1800, 12 * 3600),
        ("mirror drift", 2100, 6 * 3600),
    ],
}

CLOCK_STEP_S = 0.2


def log(msg: str) -> None:
    print(f"[run-evidence-suite] {msg}", flush=True)


def sh(args: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, **kw)


def is_loopback(url: str) -> bool:
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1"}


# ── pure helpers (self-tested) ─────────────────────────────────────────────────────────────

def parse_utc(s: str) -> dt.datetime:
    """Docker/ISO timestamps, with or without fractional seconds and 'Z'."""
    s = s.strip().replace("Z", "+00:00")
    if "." in s:
        head, rest = s.split(".", 1)
        frac, _, tz = rest.partition("+")
        s = f"{head}.{frac[:6]}+{tz}" if tz else f"{head}.{frac[:6]}"
    t = dt.datetime.fromisoformat(s)
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def schedulers_due(started: dt.datetime, now: dt.datetime, window_s: int,
                   jobs: list[tuple[str, int, int]]) -> list[tuple[str, dt.datetime]]:
    """Every (job, fire time) inside [now, now + window]."""
    end = now + dt.timedelta(seconds=window_s)
    out = []
    for name, delay, interval in jobs:
        t = started + dt.timedelta(seconds=delay)
        while t < now:
            t += dt.timedelta(seconds=interval)
        if t <= end:
            out.append((name, t))
    return out


def dirty_overlaps(scope: str, context_rel: str) -> list[str]:
    """Which dirty-scope entries fall inside a service's build context (both repo-relative)."""
    if scope in ("", "clean", "unknown"):
        return []
    ctx = context_rel.strip("/").replace("\\", "/")
    hits = []
    for entry in scope.split(","):
        entry = entry.strip().strip("/")
        if not entry:
            continue
        if ctx in ("", ".") or entry == ctx or entry.startswith(ctx + "/") or ctx.startswith(entry + "/"):
            hits.append(entry)
    return hits


def ledger_rows(report: dict, run_id: str) -> list[dict]:
    """Flatten a Playwright JSON report into one ledger row per test (last result wins)."""
    rows: list[dict] = []

    def walk(suite: dict, titles: list[str]) -> None:
        here = titles + ([suite["title"]] if suite.get("title") else [])
        for spec in suite.get("specs", []):
            for test in spec.get("tests", []):
                results = test.get("results") or [{}]
                last = results[-1]
                rows.append({
                    "kind": "test", "run": run_id,
                    "file": spec.get("file"), "title": " › ".join(here + [spec.get("title", "")]),
                    "status": last.get("status") or test.get("status"),
                    "outcome": test.get("status"),
                    "duration_ms": last.get("duration"),
                    "attempts": len(results),
                    "error": ((last.get("error") or {}).get("message") or "")[:300] or None,
                    # why-red needs WHEN (for the log window) and WHERE (for the trace).
                    "start": last.get("startTime"),
                    "attachments": {a.get("name"): a.get("path") for a in last.get("attachments", [])
                                    if a.get("path")} or None,
                })
        for child in suite.get("suites", []):
            walk(child, here)

    for s in report.get("suites", []):
        walk(s, [])
    return rows


# ── preflight checks (each returns (info, warnings)) ──────────────────────────────────────

def containers(project: str) -> list[dict]:
    r = sh(["docker", "ps", "--filter", f"name={project}-", "--format", "{{json .}}"])
    return [json.loads(l) for l in r.stdout.splitlines() if l.strip()]


def check_clock(project: str, seconds: int) -> tuple[dict, list[str]]:
    target = next((c["Names"] for c in containers(project) if "composition-service" in c["Names"]), None)
    if not target:
        return {"skipped": "no composition-service container"}, ["clock probe skipped: no probe container"]
    code = (
        "import time,json\n"
        "p=time.time();pm=time.monotonic();t0=pm;steps=[]\n"
        f"while time.monotonic()-t0<{seconds}:\n"
        "  time.sleep(0.02);n=time.time();m=time.monotonic()\n"
        f"  d=(n-p)-(m-pm)\n  if abs(d)>{CLOCK_STEP_S}: steps.append([round(m-t0,2),round(d,3)])\n"
        "  p=n;pm=m\n"
        "print(json.dumps(steps))\n"
    )
    r = sh(["docker", "exec", target, "python", "-c", code], env={**os.environ, "MSYS_NO_PATHCONV": "1"})
    try:
        steps = json.loads(r.stdout.strip() or "[]")
    except ValueError:
        return {"error": r.stderr[-300:]}, ["clock probe failed to run"]
    back = [s for s in steps if s[1] < 0]
    info = {"container": target, "seconds": seconds, "steps": steps}
    warns = []
    if back:
        warns.append(f"wall clock stepped BACK {len(back)}x in {seconds}s (largest {min(s[1] for s in back):+.3f}s): "
                     "time-ordered data and token iat checks can misbehave (DEFERRED #164)")
    return info, warns


def check_schedulers(project: str, window_s: int) -> tuple[dict, list[str]]:
    now = dt.datetime.now(dt.timezone.utc)
    info: dict = {}
    warns: list[str] = []
    for c in containers(project):
        for svc, jobs in SCHEDULERS.items():
            if f"-{svc}-" not in c["Names"] + "-":
                continue
            started = parse_utc(sh(["docker", "inspect", "-f", "{{.State.StartedAt}}", c["Names"]]).stdout)
            due = schedulers_due(started, now, window_s, jobs)
            info[c["Names"]] = {"started": started.isoformat(),
                                "due": [[n, t.isoformat()] for n, t in due]}
            for name, t in due:
                mins = (t - now).total_seconds() / 60
                warns.append(f"{svc}: '{name}' fires in {mins:.1f} min, inside this run "
                             "(it may ask the local model server for another model mid-run)")
    return info, warns


def check_models(lmstudio: str) -> tuple[dict, list[str]]:
    try:
        with urllib.request.urlopen(f"{lmstudio}/api/v0/models", timeout=5) as r:  # a READ only
            data = json.load(r).get("data", [])
    except Exception as e:  # noqa: BLE001 — a preflight check must not stop the run
        return {"error": str(e)}, [f"LM Studio not reachable at {lmstudio}: model-gated tests may skip or fail"]
    loaded = [m["id"] for m in data if m.get("state") == "loaded"]
    return {"loaded": loaded}, []


def compose_contexts(project: str) -> dict[str, list[str]]:
    """Each first-party service's build scope, repo-relative.

    Calls `docker compose` directly with iso.sh's own -p/-f arguments: from Python on Windows,
    `bash` can resolve to WSL's bash.exe rather than Git Bash, and then iso.sh never runs.
    Many services build with the REPO ROOT as context; for those, "everything" is not a useful
    scope, so it is the Dockerfile's own directory plus sdks/ (what those Dockerfiles copy)."""
    infra = REPO / "infra"
    r = sh(["docker", "compose", "-p", project, "-f", str(infra / "docker-compose.yml"),
            "-f", str(infra / "docker-compose.isolated.yml"), "config", "--format", "json"])
    try:
        svcs = json.loads(r.stdout)["services"]
    except (ValueError, KeyError):
        return {}
    out: dict[str, list[str]] = {}
    for name, spec in svcs.items():
        build = spec.get("build") or {}
        if not build.get("context"):
            continue
        try:
            ctx = Path(build["context"]).resolve().relative_to(REPO).as_posix()
        except ValueError:
            continue
        if ctx in ("", "."):
            dockerfile = (build.get("dockerfile") or "").replace("\\", "/")
            scope = [str(Path(dockerfile).parent.as_posix())] if "/" in dockerfile else []
            out[name] = scope + ["sdks"]
        else:
            out[name] = [ctx]
    return out


def check_images(project: str) -> tuple[dict, list[str]]:
    head = sh(["git", "-C", str(REPO), "rev-parse", "HEAD"]).stdout.strip()
    ctxs = compose_contexts(project)
    info: dict = {}
    warns: list[str] = []
    for c in containers(project):
        svc = c["Names"].removeprefix(f"{project}-").rsplit("-", 1)[0]
        if svc not in ctxs:
            continue
        # The image the CONTAINER runs, by id — not the tag. After a rebuild the tag points at the
        # new image while the running container still runs the old one, and that is exactly the
        # "tested the previous commit" trap this check exists to catch.
        img = sh(["docker", "inspect", "-f", "{{.Image}}", c["Names"]]).stdout.strip() or c["Image"]
        got = sh(["docker", "image", "inspect", "-f", "{{json .Config.Labels}}", img])
        if got.returncode != 0:
            # A rebuild can remove the old image from the store while its container keeps running
            # it: the container is then, by definition, not running the image that was just built.
            info[svc] = {"image": img, "context": ctxs[svc], "replaced": True}
            warns.append(f"{svc}: the container runs an image that was replaced by a rebuild — restart it")
            continue
        try:
            labels = json.loads(got.stdout or "null") or {}
        except ValueError:
            labels = {}
        newest = sh(["docker", "image", "inspect", "-f", "{{.Id}}", f"{project}-{svc}"]).stdout.strip()
        if newest and newest != img:
            warns.append(f"{svc}: a newer {project}-{svc} image exists but the container still runs the old one — restart it")
        sha = labels.get("org.loreweave.git_sha", "unknown")
        scope = labels.get("org.loreweave.git_dirty_scope", "unknown")
        entry = {"image": img, "git_sha": sha, "build_time": labels.get("org.loreweave.build_time"),
                 "dirty_scope": scope, "context": ctxs[svc]}
        paths = ctxs[svc]
        if sha == "unknown":
            warns.append(f"{svc}: image has no git sha label (built outside iso.sh/build-stack.sh)")
        elif sha != head:
            changed = sh(["git", "-C", str(REPO), "diff", "--quiet", sha, "HEAD", "--", *paths]).returncode != 0
            entry["behind_head"] = changed
            if changed:
                warns.append(f"{svc}: image built at {sha[:9]}, and {', '.join(paths)} changed since — rebuild before trusting a result")
        hits = sorted({h for p in paths for h in dirty_overlaps(scope, p)})
        if hits:
            entry["dirty_in_context"] = hits
            warns.append(f"{svc}: image was built with UNCOMMITTED changes in {', '.join(hits)}")
        info[svc] = entry
    return info, warns


def preflight(args) -> dict:
    report: dict = {"at": dt.datetime.now(dt.timezone.utc).isoformat(), "warnings": []}
    for key, fn in (
        ("schedulers", lambda: check_schedulers(args.project, args.expected_minutes * 60)),
        ("models", lambda: check_models(args.lmstudio)),
        ("images", lambda: check_images(args.project)),
        ("clock", lambda: check_clock(args.project, args.probe_seconds)),
    ):
        log(f"preflight: {key} …")
        info, warns = fn()
        report[key] = info
        for w in warns:
            log(f"WARN {w}")
        report["warnings"].extend(warns)
    log(f"preflight: {len(report['warnings'])} warning(s) — recorded, not blocking")
    return report


# ── run ────────────────────────────────────────────────────────────────────────────────────

def run_suite(args, run_id: str, run_dir: Path, pre: dict) -> int:
    results_dir = run_dir / "results"
    json_path = run_dir / "report.json"
    env = {**os.environ, "PLAYWRIGHT_BASE_URL": args.base_url, "PLAYWRIGHT_JSON_OUTPUT_NAME": str(json_path)}
    cmd = ["npx", "playwright", "test", "--reporter=list,json", "--retries=0",
           "--trace=retain-on-failure", f"--output={results_dir}", *args.passthrough]
    log(f"run {run_id}: {' '.join(cmd)}")
    started = dt.datetime.now(dt.timezone.utc)
    with open(run_dir / "run.log", "w", encoding="utf-8") as out:
        proc = subprocess.Popen(cmd, cwd=FRONTEND, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace", shell=(os.name == "nt"))
        for line in proc.stdout:  # type: ignore[union-attr]
            sys.stdout.write(line)
            out.write(line)
        rc = proc.wait()
    ended = dt.datetime.now(dt.timezone.utc)
    try:
        report = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        report = {}
    rows = ledger_rows(report, run_id)
    totals: dict[str, int] = {}
    for r in rows:
        totals[r["status"] or "unknown"] = totals.get(r["status"] or "unknown", 0) + 1
    RUNS.mkdir(parents=True, exist_ok=True)
    with open(LEDGER, "a", encoding="utf-8", newline=chr(10)) as led:  # LF: the ledger is committed
        for r in rows:
            led.write(json.dumps(r) + "\n")
        led.write(json.dumps({
            "kind": "run", "run": run_id, "started": started.isoformat(), "ended": ended.isoformat(),
            "exit": rc, "totals": totals, "passthrough": args.passthrough,
            "warnings": pre.get("warnings", []),
            "images": {k: {"git_sha": v.get("git_sha"), "dirty_scope": v.get("dirty_scope")}
                       for k, v in (pre.get("images") or {}).items()},
            "clock_steps": (pre.get("clock") or {}).get("steps"),
        }) + "\n")
    log(f"run {run_id}: exit {rc}, totals {totals} — ledger {LEDGER.relative_to(REPO)}; evidence {run_dir.relative_to(REPO)}")
    return rc


# ── self-test ──────────────────────────────────────────────────────────────────────────────

def self_test() -> int:
    ok = True

    def check(name: str, cond: bool) -> None:
        nonlocal ok
        print(f"  {'ok  ' if cond else 'FAIL'} {name}")
        ok = ok and cond

    t0 = parse_utc("2026-09-19T10:00:00.123456789Z")
    check("parse_utc truncates nanoseconds", t0.microsecond == 123456)
    jobs = [("summary", 600, 86400)]
    now = t0 + dt.timedelta(seconds=300)
    check("a job 5 min away is due in a 30-min run", len(schedulers_due(t0, now, 1800, jobs)) == 1)
    check("a job 5 min away is NOT due in a 2-min run", schedulers_due(t0, now, 120, jobs) == [])
    check("a job already past repeats a day later, not now",
          schedulers_due(t0, t0 + dt.timedelta(seconds=700), 1800, jobs) == [])
    check("dirty scope inside the context is reported", dirty_overlaps("frontend/src,docs/plans", "frontend") == ["frontend/src"])
    check("dirty scope outside the context is not", dirty_overlaps("docs/plans", "frontend") == [])
    check("'clean' and 'unknown' report nothing", dirty_overlaps("clean", "frontend") == [] and dirty_overlaps("unknown", "x") == [])
    check("a context nested under a dirty dir is reported", dirty_overlaps("services/book-service", "services/book-service/x") == ["services/book-service"])
    rep = {"suites": [{"title": "a.spec.ts", "specs": [{"title": "t1", "file": "a.spec.ts",
            "tests": [{"status": "expected", "results": [{"status": "passed", "duration": 5}]}]}],
            "suites": [{"title": "group", "specs": [{"title": "t2", "file": "a.spec.ts",
            "tests": [{"status": "unexpected", "results": [{"status": "failed", "duration": 7, "error": {"message": "boom"},
            "startTime": "2026-09-19T05:00:00.000Z", "attachments": [{"name": "trace", "path": "/r/trace.zip"}]}]}]}]}]}]}
    rows = ledger_rows(rep, "r1")
    check("ledger flattens nested suites", [r["title"] for r in rows] == ["a.spec.ts › t1", "a.spec.ts › group › t2"])
    check("ledger keeps status and error", rows[1]["status"] == "failed" and rows[1]["error"] == "boom")
    check("ledger keeps start time and trace path",
          rows[1]["start"] == "2026-09-19T05:00:00.000Z" and rows[1]["attachments"] == {"trace": "/r/trace.zip"})
    check("loopback only", is_loopback("http://localhost:25174") and not is_loopback("https://example.com"))
    print("self-test:", "OK" if ok else "FAILED")
    return 0 if ok else 2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base-url", default="http://localhost:25174")
    ap.add_argument("--project", default="lw-iso")
    ap.add_argument("--lmstudio", default="http://localhost:1234")
    ap.add_argument("--probe-seconds", type=int, default=60)
    ap.add_argument("--expected-minutes", type=int, default=30)
    ap.add_argument("--preflight-only", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("passthrough", nargs="*", help="after `--`: extra Playwright args (specs, --grep …)")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if not is_loopback(args.base_url):
        log(f"refusing non-loopback target {args.base_url}: these journeys register accounts and write data")
        return 2
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = RUNS / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    pre = preflight(args)
    (run_dir / "preflight.json").write_text(json.dumps(pre, indent=1), encoding="utf-8")
    if args.preflight_only:
        log(f"preflight written to {(run_dir / 'preflight.json').relative_to(REPO)}")
        return 0
    return run_suite(args, run_id, run_dir, pre)


if __name__ == "__main__":
    sys.exit(main())
