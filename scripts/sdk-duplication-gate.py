#!/usr/bin/env python3
"""sdk-duplication-gate.py — enforce LoreWeave's SDK-first standard.

Standard: docs/standards/sdk-first.md (rule SDK-2 · always-SDK categories).
Modelled on scripts/ai-provider-gate.py: cross-platform pure-Python, an
embedded BASELINE so the gate PASSES on today's known duplications and only
FAILS on the NEXT new copy (baseline seeded from the enterprise-hardening
audit, docs/plans/2026-07-04-enterprise-hardening-audit.md › Area 8).

Why this exists: copy-paste across services is the top driver of
cross-service drift. Security-critical verifiers and wire types that cross a
service boundary MUST live in `sdks/<lang>/` or a shared `contracts/*`
module, never re-declared per service. This is a symbol-level grep-gate:
it flags the tell-tale RE-DECLARATIONS outside `sdks/` and `contracts/` that
should be imported from a shared module.

Detected symbols (SDK-2 always-SDK categories):
  - `jwt.ParseWithClaims` — the platform user-JWT verifier, re-implemented
    ~8x in Go (must use one shared `contracts/platformjwt` verifier, the
    template is the adversarially-tested `contracts/adminjwt`).
  - `SigningMethodHS256` used to VERIFY (`t.Method != jwt.SigningMethodHS256`)
    — same defect, the algorithm-pin half of a copy-pasted verifier.
  - `class RedactFilter` / `def setup_logging(` / `_SECRET_PATTERNS` — the
    `logging_config.py` copied byte-identical across 3 Python services
    (must become `loreweave_obs.setup_logging`; the Go orphan `contracts/logging`
    was retired P2·A2b — Go uses slog + `sdks/go/observability`).
  - `type TerminalEvent` / `terminalEvent` — the notification wire struct
    duplicated between provider-registry and notification-service (must move
    to a shared `contracts/events` / notification envelope contract).

Allowlist (where these symbols LEGITIMATELY live — the shared home):
  - sdks/       — the SDK layer (the intended owner).
  - contracts/  — shared Go modules incl. adminjwt (the verifier template).
  - test files  — fixtures mint tokens (`jwt.NewWithClaims`) + build events.

Usage:
  python scripts/sdk-duplication-gate.py             # full scan (CI / manual)
  python scripts/sdk-duplication-gate.py --staged    # only git-staged files (pre-commit)
  python scripts/sdk-duplication-gate.py --update-baseline   # re-seed BASELINE (maintainers)

Exit 0 = clean (or baseline-only). Exit 1 = a NEW duplication.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

#: A child with no timeout hangs the pre-commit hook forever, with no
#: output and nothing to kill but the terminal. Surfaced by the bite
#: harness's unbounded-child survey when this gate joined its table.
GIT_TIMEOUT_S = 60

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SEARCH_DIRS = ("services", "frontend/src")
SCAN_EXTS = (".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".mjs")
EXCLUDE_DIRS = {
    "node_modules", "__pycache__", ".pytest_cache", ".venv", "venv",
    "dist", "build", ".next", ".git", "vendor", "coverage",
    "storybook-static",
}

# Path prefixes where these symbols BELONG (the shared home) — never flagged.
#
# EMPTY, and that is the fix rather than an omission. It held `sdks/` and
# `contracts/` — neither of which `SEARCH_DIRS` reaches, since the walk covers
# `services/` and `frontend/src/` only. Every relative path handed to
# `is_allowlisted` therefore begins with one of those two, and the prefix test
# could never be true: an allowlist unreachable by construction, `NV-1`, next to
# a docstring listing it as one of the gate's three protections. The shared homes
# are out of scope because they are the intended owner — that is expressed by
# not scanning them, and needs no row here. `is_allowlisted` keeps its test-file
# arm, which does fire.
ALLOWLIST_PREFIXES: tuple[str, ...] = ()

# ── detection patterns (symbol-level) ─────────────────────────────────

# SDK-2 · security-critical platform JWT verifier re-declared per service.
JWT_VERIFY = re.compile(r"\bjwt\.ParseWithClaims\b")
# The algorithm-pin half of a hand-rolled verifier — pinned to the VERIFY
# site (`!= jwt.SigningMethodHS256`) so test token MINTING
# (`jwt.NewWithClaims(jwt.SigningMethodHS256, …)`) does not match.
JWT_ALG_PIN = re.compile(r"!=\s*jwt\.SigningMethodHS256\b")

# SDK-2 · the copy-pasted Python platform USER-JWT verifier — an ASSIGNMENT-anchored
# HS256 `jwt.decode` (`data = jwt.decode(token, secret, algorithms=["HS256"])`, the
# exact shape ~6 Python services copy-pasted). P3 (SDK-first) migrated every one to
# `loreweave_authn.verify_access_token`; this guards a regression. Anchored to a
# STATEMENT (`<ident> = (py)jwt.decode(`) so a descriptive docstring/comment that
# merely mentions the old shape does NOT match; the RS256 admin-token verify
# (`algorithms=["RS256"]`) and the deliberate `verify_signature=False` stub don't
# match either (different algorithm / no HS256 pin).
PY_JWT_VERIFY = re.compile(
    r'^\s*[\w.]+\s*=\s*(?:pyjwt|jwt)\.decode\(.*algorithms\s*=\s*\[["\']HS256'
)

# SDK-2 · a copy of the shared best-effort model-NAME resolver (P3 SDK-first). Its
# tell-tale is the provider-registry model-info URL literal
# `/internal/models/{model_source}/{model_ref}/info` — the SDK owns the one
# implementation (allowlisted under sdks/), and the per-service shims delegate to
# `loreweave_internal_client.resolve_model_name` WITHOUT that literal. One known copy
# remains (worker-ai's client-method variant), baselined until its migration wave.
PY_MODEL_NAME_COPY = re.compile(r"/internal/models/\{model_source\}")

# SDK-2 · a per-service re-derivation of the shared transient-status set (P3
# SDK-first W2-tail). The tell-tale is an inline membership test against EXACTLY
# {429, 502, 503} (in any order) — the `retryable = resp.status_code in (502,503,429)`
# every S2S client independently wrote. The SDK owns this as `is_retryable_status`
# / `RETRYABLE_STATUSES` / `InternalClientError`-derives-it; a copy should call the
# predicate, not re-list the codes. Matched to a 3-element tuple ONLY so a site with
# a DIFFERENT set — e.g. lore-enrichment `generation/complete.py`'s 504-INCLUSIVE
# `(429, 502, 503, 504)` — does NOT match (that site keeps its own list per the
# RETRYABLE_STATUSES caveat). Test files / success-status checks (`in (200, 201)`) /
# dispatch 404-409-as-success (`in (404, 409)`) never match — different codes.
# Open/close brackets are a permissive class `[(\[{]…[)\]}]` so a set/list form
# (`in {429,502,503}` / `in [429,502,503]`) is caught too, not just a tuple — a
# heuristic detector, so a (never-real) mismatched-bracket pair is acceptable.
PY_INLINE_RETRYABLE = re.compile(
    r"status_code\s+in\s+[(\[{]\s*(?:429|502|503)\s*(?:,\s*(?:429|502|503)\s*){2}[)\]}]"
)

# SDK-2 · the copy-pasted logging_config.py trio (Python).
LOGGING_REDACT = re.compile(r"^\s*class\s+RedactFilter\b")
LOGGING_SETUP = re.compile(r"^\s*def\s+setup_logging\s*\(")
LOGGING_SECRETS = re.compile(r"^\s*_SECRET_PATTERNS\s*=")

# SDK-2 · a re-DECLARED notification wire struct (Go). Matches a struct DEFINITION
# (`type TerminalEvent struct {`) only — NOT a type ALIAS (`type TerminalEvent =
# notifyevent.TerminalEvent`), which is the sanctioned shared-import fix (both
# services now alias contracts/notifyevent.TerminalEvent) and the OPPOSITE of a dup.
TERMINAL_EVENT = re.compile(r"\btype\s+(?:TerminalEvent|terminalEvent)\s+struct\b")

DETECTORS = [
    ("jwt-verifier", JWT_VERIFY),
    ("jwt-alg-pin", JWT_ALG_PIN),
    ("py-jwt-verifier", PY_JWT_VERIFY),
    ("py-model-name-copy", PY_MODEL_NAME_COPY),
    ("py-inline-retryable", PY_INLINE_RETRYABLE),
    ("logging-redact-filter", LOGGING_REDACT),
    ("logging-setup", LOGGING_SETUP),
    ("logging-secret-patterns", LOGGING_SECRETS),
    ("terminal-event-struct", TERMINAL_EVENT),
]

RULE_LABELS = {
    "jwt-verifier": "platform JWT verifier re-declared (use shared contracts/platformjwt)",
    "jwt-alg-pin": "hand-rolled JWT algorithm pin (belongs in the shared verifier)",
    "py-jwt-verifier": "Python user-JWT verifier re-declared (use loreweave_authn.verify_access_token)",
    "py-model-name-copy": "resolve_model_name copy (use loreweave_internal_client.resolve_model_name)",
    "py-inline-retryable": "inline retryable-status set re-derived (use loreweave_internal_client.is_retryable_status)",
    "logging-redact-filter": "RedactFilter re-declared (use loreweave_obs.setup_logging)",
    "logging-setup": "setup_logging re-defined (use loreweave_obs.setup_logging)",
    "logging-secret-patterns": "_SECRET_PATTERNS re-declared (use the shared redactor)",
    "terminal-event-struct": "TerminalEvent wire struct duplicated (move to contracts/events)",
}


def is_test_file(rel: str) -> bool:
    base = os.path.basename(rel)
    return (
        "/tests/" in rel
        or "/test/" in rel
        or "/.storybook/" in rel
        or "/fixtures/" in rel
        or "/__fixtures__/" in rel
        or "/__mocks__/" in rel
        or rel.endswith("_test.go")
        or base.startswith("test_")
        or base.endswith((
            ".spec.ts", ".spec.tsx", ".test.ts", ".test.tsx",
            ".stories.ts", ".stories.tsx",
        ))
        or base == "conftest.py"
    )


def is_allowlisted(rel: str, prefixes: tuple[str, ...] = ALLOWLIST_PREFIXES) -> bool:
    return (bool(prefixes) and rel.startswith(prefixes)) or is_test_file(rel)


def fingerprint(rule: str, rel: str, line: str) -> str:
    """Line-number-independent identity: rule + path + normalized code."""
    return f"{rule}|{rel}|{' '.join(line.split())}"


def scan_file(path: str, rel: str) -> list[tuple[str, int, str, str]]:
    out: list[tuple[str, int, str, str]] = []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for n, line in enumerate(fh, 1):
                for rule, rx in DETECTORS:
                    if rx.search(line):
                        out.append((rule, n, rel, line.rstrip()))
    except OSError:
        pass
    return out


def iter_full_scan(repo_root: str = REPO_ROOT, search_dirs=SEARCH_DIRS):
    for d in search_dirs:
        root = os.path.join(repo_root, *d.split("/"))
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [x for x in dirnames if x not in EXCLUDE_DIRS]
            for fn in filenames:
                if fn.endswith(SCAN_EXTS):
                    full = os.path.join(dirpath, fn)
                    rel = os.path.relpath(full, repo_root).replace(os.sep, "/")
                    yield full, rel


def iter_staged():
    try:
        res = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
            timeout=GIT_TIMEOUT_S,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return
    prefixes = tuple(d + "/" for d in SEARCH_DIRS)
    for rel in res.stdout.splitlines():
        rel = rel.strip().replace(os.sep, "/")
        if not rel.endswith(SCAN_EXTS):
            continue
        if not rel.startswith(prefixes):
            continue
        if any(part in EXCLUDE_DIRS for part in rel.split("/")):
            continue
        full = os.path.join(REPO_ROOT, rel)
        if os.path.isfile(full):
            yield full, rel


def collect(files) -> list[tuple[str, int, str, str]]:
    out: list[tuple[str, int, str, str]] = []
    for full, rel in files:
        if is_allowlisted(rel):
            continue
        out.extend(scan_file(full, rel))
    return out


USAGE = """sdk-duplication-gate.py — enforce docs/standards/sdk-first.md (SDK-2)

Symbol-level grep-gate: flags tell-tale RE-DECLARATIONS outside sdks/ and
contracts/ that should be imported from a shared SDK (platform JWT verifier,
RedactFilter/setup_logging/_SECRET_PATTERNS logging trio, TerminalEvent wire
struct). An embedded BASELINE lets the gate pass on today's known copies and
fail only on the NEXT new copy.

Usage:
  python scripts/sdk-duplication-gate.py               full scan (CI / manual)
  python scripts/sdk-duplication-gate.py --staged      only git-staged files (pre-commit)
  python scripts/sdk-duplication-gate.py --update-baseline   re-seed BASELINE (maintainers)
  python scripts/sdk-duplication-gate.py --help        this message

Exit 0 = clean (or baseline-only). Exit 1 = a new duplication."""


def check(repo_root: str = REPO_ROOT, search_dirs=SEARCH_DIRS, baseline=None,
          prefixes: tuple[str, ...] = ALLOWLIST_PREFIXES, staged: bool = False) -> int:
    """The REAL checker, parameterised so `--self-test` can drive it over a
    synthetic tree instead of re-implementing its rules."""
    baseline = BASELINE if baseline is None else baseline
    files = list(iter_staged() if staged else iter_full_scan(repo_root, search_dirs))

    found: list[tuple[str, int, str, str]] = []
    subjects: dict[str, int] = {rule: 0 for rule, _ in DETECTORS}
    n_files = 0
    for full, rel in files:
        n_files += 1
        for rule, n, r, line in scan_file(full, rel):
            subjects[rule] += 1
            if not is_allowlisted(rel, prefixes):
                found.append((rule, n, r, line))

    problems: list[str] = []
    if not staged:
        # ── REACH FLOOR (GT-F3). A per-rule subject floor would be WRONG here and
        # the distinction matters: for a duplication detector, zero subjects is
        # the goal — the copy was removed. Measured 2026-08-12, 5 of the 9 rules
        # match nothing in this tree, and that is success, not blindness. What
        # must not be silent is the WALK reaching nothing, and every rule going
        # quiet at once (a renamed services/ looks exactly like a clean fleet).
        if n_files == 0:
            print(f"sdk-duplication-gate: ERROR — scanned 0 file(s) across "
                  f"{list(search_dirs)} (BDR-82).", file=sys.stderr)
            return 2
        if not any(subjects.values()):
            print(f"sdk-duplication-gate: ERROR — {n_files} file(s) scanned and NOT ONE "
                  f"matched any of the {len(DETECTORS)} detectors, not even at a known "
                  f"baselined site. Every rule going quiet together is a broken scan, not "
                  f"a clean fleet.", file=sys.stderr)
            return 2

        # ── SHRINK ARM (GT-F5). A baseline row is a standing waiver on one exact
        # line; when the duplication is migrated away the row survives it and
        # re-waives that line the day anything takes its place.
        live = {fingerprint(r, rel, ln) for r, _, rel, ln in found}
        for row in sorted(set(baseline) - live):
            problems.append(f"BASELINE row matches nothing: {row[:110]}")

    new = [v for v in found if fingerprint(v[0], v[2], v[3]) not in baseline]
    mode = "staged" if staged else "full"

    if not new and not problems:
        quiet = [r for r, c in subjects.items() if c == 0]
        print(f"sdk-duplication-gate ({mode}): OK — no new SDK-tier duplications "
              f"({n_files} file(s); baseline: {len(baseline)} known; "
              f"{len(DETECTORS) - len(quiet)}/{len(DETECTORS)} detector(s) have a subject "
              f"in this tree)")
        return 0

    if new:
        print("sdk-duplication-gate: FAIL — NEW SDK-tier duplication(s)\n")
        print("Standard: docs/standards/sdk-first.md (SDK-2 · always-SDK categories)\n")
        for rule, _ in DETECTORS:
            rule_hits = [v for v in new if v[0] == rule]
            if not rule_hits:
                continue
            print(f"[{RULE_LABELS[rule]}]")
            for _, n, rel, line in rule_hits:
                print(f"  {rel}:{n}: {line.strip()}")
            print()
        print("A security-critical verifier, a wire type crossing a service boundary,")
        print("or a redaction/logging helper is SDK-tier (SDK-2) — import it from a")
        print("shared sdks/<lang>/ or contracts/* module, do not re-declare it per service.")
        print("\nIf this is intentional/legacy, add a row to docs/deferred/DEFERRED.md and")
        print("re-seed the baseline (python scripts/sdk-duplication-gate.py --update-baseline).")
    for pr in problems:
        print(f"sdk-duplication-gate: FAIL — {pr}")
    return 1


# ── SELF-TEST ────────────────────────────────────────────────────────────────
# Every probe tree carries one live subject (a baselined JWT verifier), so the
# all-quiet floor stays down and each case below tests exactly one rule.
SEED_REL = "services/auth/keep.go"
SEED_LINE = "\tt, err := jwt.ParseWithClaims(s, &C{}, f)"
SEED_FP = f"jwt-verifier|{SEED_REL}|{' '.join(SEED_LINE.split())}"


def self_test() -> int:
    import contextlib
    import io
    import tempfile

    failures = 0

    def probe(name: str, want: int, files: dict[str, str], *, baseline=None,
              prefixes: tuple[str, ...] = (), seed: bool = True) -> None:
        nonlocal failures
        with tempfile.TemporaryDirectory() as d:
            if seed:
                files = {SEED_REL: SEED_LINE + "\n", **files}
            for rel, body in files.items():
                full = os.path.join(d, *rel.split("/"))
                os.makedirs(os.path.dirname(full), exist_ok=True)
                with open(full, "w", encoding="utf-8") as fh:
                    fh.write(body)
            os.makedirs(os.path.join(d, "services"), exist_ok=True)
            try:
                with contextlib.redirect_stdout(io.StringIO()), \
                        contextlib.redirect_stderr(io.StringIO()):
                    got = check(d, ("services", "frontend/src"),
                                {SEED_FP} if baseline is None else baseline, prefixes)
            except Exception as e:  # noqa: BLE001
                failures += 1
                print(f"  FAIL {name}: raised {type(e).__name__}: {e}")
                return
        ok = got == want
        failures += 0 if ok else 1
        print(f"  {'ok  ' if ok else 'FAIL'} {name}: rc={got} (want {want})")

    print("sdk-duplication-gate --self-test")

    probe("a baselined duplication alone passes", 0, {})

    # one case per detector
    probe("a NEW jwt.ParseWithClaims fails", 1, {
        "services/b/j.go": "t, err := jwt.ParseWithClaims(s, &C{}, f)\n"})
    probe("a hand-rolled algorithm pin fails", 1, {
        "services/b/j.go": "if t.Method != jwt.SigningMethodHS256 {\n"})
    probe("...but MINTING with HS256 does not", 0, {
        "services/b/j.go": "tok := jwt.NewWithClaims(jwt.SigningMethodHS256, c)\n"})
    probe("a python HS256 jwt.decode assignment fails", 1, {
        "services/b/a.py": 'data = jwt.decode(tok, sec, algorithms=["HS256"])\n'})
    probe("...but an RS256 decode does not", 0, {
        "services/b/a.py": 'data = jwt.decode(tok, k, algorithms=["RS256"])\n'})
    probe("...nor a comment describing the old shape", 0, {
        "services/b/a.py": '# data = jwt.decode(tok, sec, algorithms=["HS256"])\n'})
    probe("a resolve_model_name copy fails", 1, {
        "services/b/m.py": 'URL = f"/internal/models/{model_source}/{model_ref}/info"\n'})
    probe("an inline retryable-status set fails", 1, {
        "services/b/c.py": "retry = resp.status_code in (502, 503, 429)\n"})
    probe("...but the 504-inclusive set does not", 0, {
        "services/b/c.py": "retry = resp.status_code in (429, 502, 503, 504)\n"})
    probe("...nor a success-status check", 0, {
        "services/b/c.py": "ok = resp.status_code in (200, 201)\n"})
    probe("a RedactFilter class fails", 1, {
        "services/b/l.py": "class RedactFilter(logging.Filter):\n"})
    probe("a setup_logging def fails", 1, {"services/b/l.py": "def setup_logging():\n"})
    probe("a _SECRET_PATTERNS assignment fails", 1, {
        "services/b/l.py": "_SECRET_PATTERNS = [\n"})
    probe("a TerminalEvent struct DEFINITION fails", 1, {
        "services/b/e.go": "type TerminalEvent struct {\n"})
    probe("...but the type ALIAS (the sanctioned fix) does not", 0, {
        "services/b/e.go": "type TerminalEvent = notifyevent.TerminalEvent\n"})

    # exclusions
    probe("a duplication in a test file is excluded", 0, {
        "services/b/tests/t.go": "t, err := jwt.ParseWithClaims(s, &C{}, f)\n"})
    probe("an ALLOWLISTED prefix excludes it", 0, {
        "services/legacy/j.go": "t, err := jwt.ParseWithClaims(s, &C{}, f)\n"},
        prefixes=("services/legacy/",))

    # the shrink arm
    probe("a BASELINE row matching nothing fails", 1, {},
          baseline={SEED_FP, "jwt-verifier|services/gone/j.go|t, err := jwt.ParseWithClaims("})

    # floors
    probe("no files at all is misuse, not a pass", 2, {}, seed=False)
    probe("every detector quiet at once is misuse", 2, {
        "services/b/main.go": "package main\n"}, seed=False, baseline=set())

    if failures:
        print(f"sdk-duplication-gate --self-test: {failures} rule(s) did not behave")
        return 2
    print("sdk-duplication-gate --self-test: every rule bites, and none cries wolf")
    return 0


def main() -> int:
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        print(USAGE)
        return 0
    if "--self-test" in args or "--selftest" in args:
        return self_test()

    if "--update-baseline" in args:
        found = collect(iter_full_scan())
        fps = sorted({fingerprint(r, rel, ln) for r, _, rel, ln in found})
        print("BASELINE = {")
        for fp in fps:
            print(f"    {fp!r},")
        print("}")
        print(f"\n# {len(fps)} baselined duplications", file=sys.stderr)
        return 0

    rc = self_test()
    if rc:
        return rc
    print()
    return check(staged="--staged" in args)


# Seeded from the current repo (2026-07-04). Re-generate with --update-baseline.
# 11 known duplications (Area 8): JWT verifier x1 (+ alg-pin x1) — only auth-service,
# the token MINTER, remains after the D-JWT-ROLE-GATE migration; logging_config trio
# x3 (RedactFilter + _SECRET_PATTERNS + setup_logging across composition/knowledge/
# lore-enrichment). The TerminalEvent dup was retired into contracts/notifyevent.
# JWT-migration 2026-07-04: book/glossary/notification/sharing migrated to the
# shared contracts/platformjwt verifier (8 entries retired below). The 3 that
# D-JWT-ROLE-GATE 2026-07-04: agent-registry/provider-registry/usage-billing migrated
# their user-JWT verify to contracts/platformjwt AND their admin gate to the RS256
# contracts/adminjwt (glossary requireAdminScope pattern) — 6 entries retired below.
# auth-service is the token MINTER (owns AccessClaims incl. the `sid` session claim
# platformjwt does not carry), so it legitimately parses its own tokens — NOT a
# duplicate consumer; its 2 entries stay.
# Each is a line-number-independent `rule|relpath|normalized-code` fingerprint,
# so the gate passes today and fails only on the NEXT new copy.
#
# GT8 · 2026-08-12: **6 of the 11 rows were DEAD** — the whole logging_config
# trio (RedactFilter + _SECRET_PATTERNS + setup_logging across composition,
# knowledge and lore-enrichment) had been migrated to loreweave_obs, and the
# rows outlived their subjects by months. 55% dead, the worst ratio on the
# gate-teeth board since runbook-drift's 91%. Trimmed to 5; the shrink arm
# below now reds instead of waiting for someone to look.
BASELINE = {
    'jwt-alg-pin|services/auth-service/internal/authjwt/jwt.go|if t.Method != jwt.SigningMethodHS256 {',
    'jwt-verifier|services/auth-service/internal/authjwt/jwt.go|t, err := jwt.ParseWithClaims(tokenStr, &AccessClaims{}, func(t *jwt.Token) (interface{}, error) {',
    'logging-setup|services/composition-service/app/logging_config.py|def setup_logging(level: str = "INFO") -> None:',
    'logging-setup|services/knowledge-service/app/logging_config.py|def setup_logging(level: str = "INFO") -> None:',
    'logging-setup|services/lore-enrichment-service/app/logging_config.py|def setup_logging(level: str = "INFO") -> None:',
}


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    sys.exit(main())
