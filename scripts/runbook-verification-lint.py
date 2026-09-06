#!/usr/bin/env python3
"""runbook-verification-lint — L7.B.17 (RAID cycle 35).

Two responsibilities:
  1. Every alert in infra/prometheus/alerts/**/*.yaml MUST link to a runbook
     (SR1-D6). Either a `runbook:`/`runbook_url:` annotation, or the alert is
     named by some runbook's `applies_to_alerts`.
  2. Every runbook in docs/sre/runbooks/ MUST carry YAML frontmatter with the
     required fields, and `verification_method` must be from the closed set.

Stubs (Q-L7B-1) are PRESENT — they count as runbooks — but `verification_method`
must be exactly 'stub' and `last_verified` must be '1970-01-01' so they read as
overdue.

Exit 0 = clean · 1 = violations · 2 = misuse / nothing scanned / self-test failure.

GT8 · what this gate lacked
---------------------------
It lived in a `python3 - <<'PY'` heredoc inside the shell wrapper, which is why
it had no self-test: there was nothing to call. Extracted here, parameterised on
its two directories and its two ratchets, exactly as
`migration-idempotency-validator.sh` already delegates to its `.py`.

**Both of its interesting numbers were unratcheted.** Measured 2026-08-12:
**27 of 27 runbooks are stubs** — every single one is a placeholder with
`last_verified: 1970-01-01`. The gate printed that and moved on. A gate called
*runbook-VERIFICATION* whose whole corpus is unverified should say so in a way
that changes colour when someone drains one, so `STUB_CEIL` is a ratchet: a new
stub reds, and draining one reds until the constant follows.

**The alert-link leg was advisory** — 5 of 33 alerts have no runbook, printed as
WARN with the note *"until cycle 36+ alert-rule-validator backfill"*. Cycle 36
came and went. `GTD-13`'s shape for the fifth time on this board; now a ratchet
at 5, both directions.

**A renamed alerts directory scanned zero alerts and said nothing** —
`if alerts_dir.is_dir():` and then silence. Now a floor.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUNBOOKS_REL = "docs/sre/runbooks"
ALERTS_REL = "infra/prometheus/alerts"

REQUIRED_FIELDS = [
    "runbook_id", "version", "owner", "applies_to_alerts", "applies_to_services",
    "last_verified", "verification_method", "next_verification_due",
]
ALLOWED_METHODS = {"reading_review", "tabletop", "chaos_drill", "stub"}

#: The V1 launch gate (Q-L7B-1 / SR3 §12AF.4). A minimum, not a ratchet.
RUNBOOK_MIN = 27

#: How many runbooks are still placeholders. Measured 2026-08-12: 27 of 27.
#: May only FALL — a new stub reds, and draining one reds until this follows.
STUB_CEIL = 27

#: Alerts with no runbook link. Measured 2026-08-12: 5 of 33. Same ratchet.
UNLINKED_ALERT_CEIL = 5

SKIP_RUNBOOKS = {"README.md", "TEMPLATE.md", "INDEX.md"}


def parse_fm(text: str) -> dict | None:
    """Frontmatter parser: `key: value`, `key:` + `  - item` lists, `[a, b]`."""
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    fm: dict = {}
    cur_list = None
    for line in text[4:end].splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        if line.startswith("  - "):
            if cur_list is not None:
                cur_list.append(line[4:].strip())
            continue
        m = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*):\s*(.*)$", line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if val == "":
            fm[key] = []
            cur_list = fm[key]
            continue
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            fm[key] = [] if not inner else [s.strip() for s in inner.split(",")]
            cur_list = None
            continue
        fm[key] = val
        cur_list = None
    return fm


def check(runbooks_dir: Path, alerts_dir: Path, repo: Path = REPO,
          runbook_min: int = RUNBOOK_MIN, stub_ceil: int = STUB_CEIL,
          unlinked_ceil: int = UNLINKED_ALERT_CEIL) -> int:
    errors: list[str] = []

    if not runbooks_dir.is_dir():
        print(f"[runbook-verification-lint] ERROR: {runbooks_dir} is not a directory; "
              f"the runbook leg has no subject.", file=sys.stderr)
        return 2
    if not alerts_dir.is_dir():
        print(f"[runbook-verification-lint] ERROR: {alerts_dir} is not a directory; "
              f"the alert leg would scan nothing and report no problems.", file=sys.stderr)
        return 2

    runbook_count = 0
    stub_count = 0
    runbook_alert_index: dict[str, list[str]] = {}
    for path in sorted(runbooks_dir.rglob("*.md")):
        if path.name in SKIP_RUNBOOKS:
            continue
        text = path.read_text(encoding="utf-8")
        fm = parse_fm(text)
        try:
            rel = path.relative_to(repo).as_posix()
        except ValueError:
            rel = path.as_posix()
        if fm is None:
            errors.append(f"{rel}: missing YAML frontmatter")
            continue
        runbook_count += 1
        for fld in REQUIRED_FIELDS:
            if fld not in fm:
                errors.append(f"{rel}: missing required frontmatter field '{fld}'")
        method = fm.get("verification_method", "")
        if method not in ALLOWED_METHODS:
            errors.append(f"{rel}: verification_method='{method}' not in {sorted(ALLOWED_METHODS)}")
        if method == "stub":
            stub_count += 1
            if fm.get("last_verified") != "1970-01-01":
                errors.append(f"{rel}: stub MUST have last_verified=1970-01-01 "
                              f"(got '{fm.get('last_verified')}')")
        for a in (fm.get("applies_to_alerts") or []):
            runbook_alert_index.setdefault(a, []).append(rel)

    alerts_seen = 0
    alerts_without_runbook: list[tuple[str, str]] = []
    for path in sorted(alerts_dir.rglob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        try:
            rel = path.relative_to(repo).as_posix()
        except ValueError:
            rel = path.as_posix()
        current_alert = None
        runbook_set = False
        for line in text.splitlines():
            alert_m = re.match(r"^\s*-\s*alert:\s*(\S+)", line)
            if alert_m:
                if current_alert and not runbook_set and current_alert in runbook_alert_index:
                    runbook_set = True
                if current_alert and not runbook_set:
                    alerts_without_runbook.append((rel, current_alert))
                current_alert = alert_m.group(1)
                runbook_set = False
                alerts_seen += 1
                continue
            if current_alert and re.search(r"runbook(_url)?:\s*\S", line):
                runbook_set = True
        if current_alert and not runbook_set and current_alert in runbook_alert_index:
            runbook_set = True
        if current_alert and not runbook_set:
            alerts_without_runbook.append((rel, current_alert))

    # ── REACH FLOOR on the alert leg. A directory that exists but holds no
    # alert rules produces "0 unlinked", which is the best possible result and
    # means nothing.
    if alerts_seen == 0:
        print(f"[runbook-verification-lint] ERROR: 0 alert rules found under {alerts_dir}. "
              f"Zero unlinked alerts out of zero alerts is not compliance.", file=sys.stderr)
        return 2

    if runbook_count < runbook_min:
        errors.append(f"V1 LAUNCH GATE FAIL: {runbook_count} runbooks present; "
                      f"SR3 §12AF.4 requires {runbook_min}")

    # ── THE STUB RATCHET. Every runbook here is a placeholder; a gate called
    # runbook-VERIFICATION should change colour when that stops being true, and
    # when it gets worse.
    if stub_count > stub_ceil:
        errors.append(f"{stub_count} stub runbook(s), ratchet is {stub_ceil}. A new placeholder "
                      f"is not a verified runbook — drain one or raise STUB_CEIL with a reason.")
    elif stub_count < stub_ceil:
        errors.append(f"{stub_count} stub runbook(s), but the ratchet still says {stub_ceil}. "
                      f"A ratchet that never falls stops being one. Set STUB_CEIL={stub_count}.")

    # ── THE UNLINKED-ALERT RATCHET, replacing an advisory WARN whose "until
    # cycle 36+" backfill note outlived cycle 36.
    n_unlinked = len(alerts_without_runbook)
    if n_unlinked > unlinked_ceil:
        errors.append(f"{n_unlinked} alert(s) with no runbook link, ratchet is {unlinked_ceil} "
                      f"(SR1-D6). Link it, or raise the ratchet with a reason.")
    elif n_unlinked < unlinked_ceil:
        errors.append(f"{n_unlinked} alert(s) with no runbook link, but the ratchet still says "
                      f"{unlinked_ceil}. Set UNLINKED_ALERT_CEIL={n_unlinked}.")

    print(f"[runbook-verification-lint] runbooks={runbook_count} stubs={stub_count}"
          f"(ratchet {stub_ceil}) alerts_scanned={alerts_seen} "
          f"unlinked={n_unlinked}(ratchet {unlinked_ceil})")
    for af, alert in alerts_without_runbook[:10]:
        print(f"[runbook-verification-lint] unlinked: {alert} in {af}")

    for e in errors:
        print(f"[runbook-verification-lint] ERROR: {e}", file=sys.stderr)
    return 1 if errors else 0


# ── SELF-TEST ────────────────────────────────────────────────────────────────
GOOD_FM = """---
runbook_id: rb-001
version: 1
owner: sre
applies_to_alerts:
  - LWThingBroken
applies_to_services:
  - svc
last_verified: 1970-01-01
verification_method: stub
next_verification_due: 2027-01-01
---

# Runbook
"""

ALERT_LINKED = """groups:
  - name: g
    rules:
      - alert: LWThingBroken
        expr: up == 0
"""
ALERT_ANNOTATED = """groups:
  - name: g
    rules:
      - alert: LWOtherThing
        expr: up == 0
        annotations:
          runbook: docs/sre/runbooks/other.md
"""
ALERT_UNLINKED = """groups:
  - name: g
    rules:
      - alert: LWOrphan
        expr: up == 0
"""


def self_test() -> int:
    import contextlib
    import io
    import tempfile

    failures = 0

    def probe(name: str, want: int, *, runbooks: dict[str, str] | None = None,
              alerts: dict[str, str] | None = None, runbook_min: int = 1,
              stub_ceil: int = 1, unlinked_ceil: int = 0,
              no_runbooks_dir: bool = False, no_alerts_dir: bool = False) -> None:
        nonlocal failures
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            rb = root / RUNBOOKS_REL
            al = root / ALERTS_REL
            # Writing a fixture file re-creates its parent, so a "missing dir"
            # probe must skip the writes too — otherwise it never reaches its own
            # fixture and reports rc=0 while claiming to test a missing tree.
            if not no_runbooks_dir:
                rb.mkdir(parents=True, exist_ok=True)
                for rel, body in (runbooks if runbooks is not None
                                  else {"a.md": GOOD_FM}).items():
                    (rb / rel).parent.mkdir(parents=True, exist_ok=True)
                    (rb / rel).write_text(body, encoding="utf-8")
            if not no_alerts_dir:
                al.mkdir(parents=True, exist_ok=True)
                for rel, body in (alerts if alerts is not None
                                  else {"a.yaml": ALERT_LINKED}).items():
                    (al / rel).parent.mkdir(parents=True, exist_ok=True)
                    (al / rel).write_text(body, encoding="utf-8")
            try:
                with contextlib.redirect_stdout(io.StringIO()), \
                        contextlib.redirect_stderr(io.StringIO()):
                    got = check(rb, al, root, runbook_min, stub_ceil, unlinked_ceil)
            except Exception as e:  # noqa: BLE001 - a crash is what this asserts against
                failures += 1
                print(f"  FAIL {name}: raised {type(e).__name__}: {e} — it must return a code")
                return
        ok = got == want
        failures += 0 if ok else 1
        print(f"  {'ok  ' if ok else 'FAIL'} {name}: rc={got} (want {want})")

    print("runbook-verification-lint --self-test")

    probe("a linked alert and a valid stub runbook pass", 0)

    # runbook frontmatter
    probe("a runbook with no frontmatter fails", 1,
          runbooks={"a.md": GOOD_FM, "b.md": "# no frontmatter\n"})
    probe("a missing required field fails", 1,
          runbooks={"a.md": GOOD_FM.replace("owner: sre\n", "")})
    # stub_ceil=0: a non-stub runbook would otherwise trip the STUB ratchet and
    # the probe would pass on that instead of on the closed-set rule.
    probe("a verification_method outside the closed set fails", 1,
          runbooks={"a.md": GOOD_FM.replace("verification_method: stub",
                                            "verification_method: vibes")},
          stub_ceil=0)
    probe("a stub whose last_verified is not 1970-01-01 fails", 1,
          runbooks={"a.md": GOOD_FM.replace("last_verified: 1970-01-01",
                                            "last_verified: 2026-01-01")})
    # runbook_min=0 + stub_ceil=0: a skipped README leaves zero runbooks and zero
    # stubs, which must be CLEAN. If SKIP_RUNBOOKS stops applying, README counts,
    # stub_count becomes 1 and the run reds — the only signal in this fixture.
    # …and the alert must be linked by ANNOTATION, because with zero runbooks the
    # reverse lookup is empty and the unlinked-alert ratchet would red instead.
    # Three rules had to be silenced before this fixture could speak for one.
    probe("README/TEMPLATE/INDEX are not runbooks", 0,
          runbooks={"README.md": GOOD_FM}, alerts={"a.yaml": ALERT_ANNOTATED},
          runbook_min=0, stub_ceil=0)

    # the alert leg
    probe("an alert named by a runbook's applies_to_alerts is linked", 0)
    probe("an alert with a runbook: annotation is linked", 0,
          runbooks={"a.md": GOOD_FM}, alerts={"a.yaml": ALERT_LINKED,
                                              "b.yaml": ALERT_ANNOTATED})
    probe("an UNLINKED alert trips the ratchet", 1,
          alerts={"a.yaml": ALERT_LINKED, "b.yaml": ALERT_UNLINKED})
    probe("...and passes when the ratchet expects it", 0,
          alerts={"a.yaml": ALERT_LINKED, "b.yaml": ALERT_UNLINKED}, unlinked_ceil=1)
    probe("...and the ratchet reds when the count FALLS below it", 1, unlinked_ceil=1)

    # the stub ratchet
    probe("an EXTRA stub trips the ratchet", 1,
          runbooks={"a.md": GOOD_FM, "b.md": GOOD_FM.replace("rb-001", "rb-002")},
          runbook_min=1, stub_ceil=1)
    probe("...and the stub ratchet reds when the count FALLS", 1, stub_ceil=2)

    # the launch-gate minimum
    probe("fewer runbooks than the V1 minimum fails", 1, runbook_min=2)

    # floors
    probe("a MISSING runbooks dir is misuse, not a pass", 2, no_runbooks_dir=True)
    probe("a MISSING alerts dir is misuse, not a pass", 2, no_alerts_dir=True)
    probe("an alerts dir with NO alert rules is misuse, not compliance", 2,
          alerts={"empty.yaml": "groups: []\n"}, unlinked_ceil=0)

    if failures:
        print(f"runbook-verification-lint --self-test: {failures} rule(s) did not behave")
        return 2
    print("runbook-verification-lint --self-test: every rule bites, and none cries wolf")
    return 0


def main(argv: list[str]) -> int:
    if "--self-test" in argv or "--selftest" in argv:
        return self_test()
    rc = self_test()
    if rc:
        return rc
    print()
    return check(REPO / RUNBOOKS_REL, REPO / ALERTS_REL)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
