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
    (must become `loreweave_logging`, or adopt orphan `contracts/logging`).
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

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SEARCH_DIRS = ("services", "frontend/src")
SCAN_EXTS = (".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".mjs")
EXCLUDE_DIRS = {
    "node_modules", "__pycache__", ".pytest_cache", ".venv", "venv",
    "dist", "build", ".next", ".git", "vendor", "coverage",
    "storybook-static",
}

# Path prefixes where these symbols BELONG (the shared home) — never flagged.
ALLOWLIST_PREFIXES = (
    "sdks/",       # the SDK layer — the intended single owner
    "contracts/",  # shared Go modules (adminjwt, events, logging, …)
)

# ── detection patterns (symbol-level) ─────────────────────────────────

# SDK-2 · security-critical platform JWT verifier re-declared per service.
JWT_VERIFY = re.compile(r"\bjwt\.ParseWithClaims\b")
# The algorithm-pin half of a hand-rolled verifier — pinned to the VERIFY
# site (`!= jwt.SigningMethodHS256`) so test token MINTING
# (`jwt.NewWithClaims(jwt.SigningMethodHS256, …)`) does not match.
JWT_ALG_PIN = re.compile(r"!=\s*jwt\.SigningMethodHS256\b")

# SDK-2 · the copy-pasted logging_config.py trio (Python).
LOGGING_REDACT = re.compile(r"^\s*class\s+RedactFilter\b")
LOGGING_SETUP = re.compile(r"^\s*def\s+setup_logging\s*\(")
LOGGING_SECRETS = re.compile(r"^\s*_SECRET_PATTERNS\s*=")

# SDK-2 · the duplicated notification wire struct (Go).
TERMINAL_EVENT = re.compile(r"\btype\s+(?:TerminalEvent|terminalEvent)\b")

DETECTORS = [
    ("jwt-verifier", JWT_VERIFY),
    ("jwt-alg-pin", JWT_ALG_PIN),
    ("logging-redact-filter", LOGGING_REDACT),
    ("logging-setup", LOGGING_SETUP),
    ("logging-secret-patterns", LOGGING_SECRETS),
    ("terminal-event-struct", TERMINAL_EVENT),
]

RULE_LABELS = {
    "jwt-verifier": "platform JWT verifier re-declared (use shared contracts/platformjwt)",
    "jwt-alg-pin": "hand-rolled JWT algorithm pin (belongs in the shared verifier)",
    "logging-redact-filter": "RedactFilter re-declared (use loreweave_logging / contracts/logging)",
    "logging-setup": "setup_logging re-defined (use loreweave_logging / contracts/logging)",
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


def is_allowlisted(rel: str) -> bool:
    return rel.startswith(ALLOWLIST_PREFIXES) or is_test_file(rel)


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


def iter_full_scan():
    for d in SEARCH_DIRS:
        root = os.path.join(REPO_ROOT, *d.split("/"))
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [x for x in dirnames if x not in EXCLUDE_DIRS]
            for fn in filenames:
                if fn.endswith(SCAN_EXTS):
                    full = os.path.join(dirpath, fn)
                    rel = os.path.relpath(full, REPO_ROOT).replace(os.sep, "/")
                    yield full, rel


def iter_staged():
    try:
        res = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
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


def main() -> int:
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        print(USAGE)
        return 0

    if "--update-baseline" in args:
        found = collect(iter_full_scan())
        fps = sorted({fingerprint(r, rel, ln) for r, _, rel, ln in found})
        print("BASELINE = {")
        for fp in fps:
            print(f"    {fp!r},")
        print("}")
        print(f"\n# {len(fps)} baselined duplications", file=sys.stderr)
        return 0

    staged = "--staged" in args
    files = iter_staged() if staged else iter_full_scan()
    found = collect(files)

    new = [v for v in found if fingerprint(v[0], v[2], v[3]) not in BASELINE]

    mode = "staged" if staged else "full"
    if not new:
        print(f"sdk-duplication-gate ({mode}): OK — no new SDK-tier duplications "
              f"(baseline: {len(BASELINE)} known)")
        return 0

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
    return 1


# Seeded from the current repo (2026-07-04). Re-generate with --update-baseline.
# 19 known duplications from the enterprise-hardening audit (Area 8): JWT
# verifier x4 (+ alg-pin x4), logging_config trio x3, TerminalEvent dup x2.
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
BASELINE = {
    'jwt-alg-pin|services/auth-service/internal/authjwt/jwt.go|if t.Method != jwt.SigningMethodHS256 {',
    'jwt-verifier|services/auth-service/internal/authjwt/jwt.go|t, err := jwt.ParseWithClaims(tokenStr, &AccessClaims{}, func(t *jwt.Token) (interface{}, error) {',
    'logging-redact-filter|services/composition-service/app/logging_config.py|class RedactFilter(logging.Filter):',
    'logging-redact-filter|services/knowledge-service/app/logging_config.py|class RedactFilter(logging.Filter):',
    'logging-redact-filter|services/lore-enrichment-service/app/logging_config.py|class RedactFilter(logging.Filter):',
    'logging-secret-patterns|services/composition-service/app/logging_config.py|_SECRET_PATTERNS = [',
    'logging-secret-patterns|services/knowledge-service/app/logging_config.py|_SECRET_PATTERNS = [',
    'logging-secret-patterns|services/lore-enrichment-service/app/logging_config.py|_SECRET_PATTERNS = [',
    'logging-setup|services/composition-service/app/logging_config.py|def setup_logging(level: str = "INFO") -> None:',
    'logging-setup|services/knowledge-service/app/logging_config.py|def setup_logging(level: str = "INFO") -> None:',
    'logging-setup|services/lore-enrichment-service/app/logging_config.py|def setup_logging(level: str = "INFO") -> None:',
    'terminal-event-struct|services/notification-service/internal/consumer/consumer.go|type terminalEvent struct {',
    'terminal-event-struct|services/provider-registry-service/internal/jobs/notifier.go|type TerminalEvent struct {',
}


if __name__ == "__main__":
    sys.exit(main())
