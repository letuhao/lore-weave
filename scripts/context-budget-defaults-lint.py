#!/usr/bin/env python3
"""context-budget-defaults-lint.py — enforce Context Budget Law OUT-2 defaults, cross-service.

Spec: docs/standards/mcp-tool-io.md · OUT-2 ("Default to the smaller shape").

The RUNTIME size gate (loreweave_mcp Tool.run → _check_size) already WARNS when a tool
result crosses 8 KB — but a warning nobody acts on is not protection (jobs_list warned
`bytes=52351` on every default call for weeks; K36). This is the static teeth: it makes
the *defaults* that produce those payloads a CI/pre-commit failure, so a LIST-returning
MCP tool cannot ship (or regress back to) a context-crowding default.

THE RULE — a tool whose signature has BOTH a `detail` selector AND a `limit` param is a
LIST tool (returns many rich rows). Its DEFAULTS must be the small shape:
  1. `detail` defaults to "summary"  (drop each row's heavy fields; full is opt-in)
  2. `limit`  defaults to <= LIMIT_CEIL rows  (a page the caller's context can hold)
Both compound — jobs_list at detail=full × limit=50 was 45.6 KB; summary × 10 is 4.5 KB.

A single-item tool (has `detail`, no `limit`) is EXEMPT — `full` for one object is fine.

Named limit defaults (`limit=KG_GRAPH_LIMIT_DEFAULT`) are resolved from a `NAME = <int>`
assignment in the SAME file; an unresolvable name is reported (not silently passed).

Deliberate exemptions live in ALLOW below with a reason. The current offenders are seeded
as tracked DEBT (K37) — each is a FLIP-PENDING follow-up (drop it from ALLOW when the tool
is migrated to summary + a small limit, K36-style, with its own by-effect test).

Usage:
  python scripts/context-budget-defaults-lint.py            # full scan (CI / manual)
  python scripts/context-budget-defaults-lint.py --staged   # only git-staged files
Exit 0 = clean. Exit 1 = a LIST tool defaults to a context-crowding shape.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys

#: A child with no timeout hangs the pre-commit hook forever, with no
#: output and nothing to kill but the terminal. Surfaced by the bite
#: harness's unbounded-child survey when this gate joined its table.
GIT_TIMEOUT_S = 60

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# A default page a caller's context can comfortably hold. jobs_list uses 10; 25 is the
# generous ceiling (a genuinely list-heavy tool may justify more via an ALLOW reason).
LIMIT_CEIL = 25

# service::tool -> reason. The K37 drain is COMPLETE — 14/14 offenders fully migrated to
# summary + a bounded, SIGNALLED limit ≤25. ALLOW is now EMPTY: even the graph reads fit the
# ≤25 ceiling (a LIVE seed+measure confirmed summary/25 = 6.7 KB, under the 8 KB warn, on a real
# 150-edge graph — my earlier "graph justifies a conscious 60" was disproven by that data; 60
# was still 14.7 KB, over warn). A NEW list tool must comply or earn an explicit reason here.
ALLOW: dict[str, str] = {
    # (empty — no conscious exceptions remain; every detail-selector LIST tool defaults to
    # summary + a bounded, signalled limit ≤25.)
    # kg_entity_edge_timeline: DRAINED (K37) — a FLAT temporal chain, so limit 500→25 (≤ ceiling)
    # + the handler over-fetches limit+1 and stamps meta.truncated (OUT-5). Removed from ALLOW.
    # kg_triage_list: DRAINED (K37) — limit 100→25 (repo over-fetches limit+1 → real has_more,
    # never a silent drop), MCP signature detail=summary. Removed from ALLOW → lint-enforced.
    # (The Args-model / OpenAI-schema detail default is still "full" — the K38 lockstep gap,
    # tracked separately; it affects every "detail-drained" tool, not just this one.)
    # composition_list_outline: DRAINED (K37) — like translation, list_tree fetches ALL nodes
    # and `limit` feeds only apply_response_contract, so a flat-count default (None→25) caps the
    # true total + reports `truncated` (a signalled prefix, never a silent drop; the description
    # documents the flat-prefix behaviour). Removed from ALLOW.
    # translation_job_status / translation_list_versions: DRAINED (K37) — limit None→25. Their
    # SQL fetches ALL rows and `limit` feeds only apply_response_contract, so the cap sees the
    # true total and reports `truncated` — a bounded default page, never a silent drop. Removed
    # from ALLOW → lint-enforced.
}


def _service_of(path: str) -> str:
    parts = path.replace("\\", "/").split("/")
    return parts[parts.index("services") + 1] if "services" in parts else "?"


def _module_int_consts(path: str) -> dict[str, int]:
    """Module-level `NAME = <int>` assignments in one file."""
    try:
        tree = ast.parse(open(path, encoding="utf-8").read())
    except (OSError, SyntaxError):
        return {}
    out: dict[str, int] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, int):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    out[t.id] = node.value.value
    return out


def _import_sources(path: str) -> dict[str, tuple[str, str]]:
    """local-name -> (module string, ORIGINAL name). Tracks the original through an alias
    (`from x import FOO as BAR` → BAR: (x, "FOO")) so the target file is queried by the name
    it actually defines, not the alias."""
    try:
        tree = ast.parse(open(path, encoding="utf-8").read())
    except (OSError, SyntaxError):
        return {}
    out: dict[str, tuple[str, str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for a in node.names:
                out[a.asname or a.name] = (("." * node.level) + node.module, a.name)
    return out


def _module_to_file(module: str, importer_path: str) -> str | None:
    """Resolve a `from` module string to a file under the SAME service's app/. Handles
    relative (`.definitions`) and absolute (`app.tools.definitions`) forms — collision-safe
    because it stays within the importer's own service tree (TIMELINE_LIMIT_DEFAULT is 20 in
    one service file and 500 in another; following the real import picks the right one)."""
    p = importer_path.replace("\\", "/").split("/")
    if "services" not in p:
        return None
    svc_root = "/".join(p[: p.index("services") + 2])  # services/<svc>
    if module.startswith("."):
        base = os.path.dirname(importer_path)
        for _ in range(len(module) - len(module.lstrip("."))):
            base = os.path.dirname(base)
        rel = module.lstrip(".").replace(".", "/")
        cand = os.path.join(base, rel + ".py")
    else:
        cand = os.path.join(svc_root, module.replace(".", "/") + ".py")
    return cand if os.path.isfile(cand) else None


def _resolve_int(name: str, module_ints: dict[str, int], path: str, cache: dict[str, dict[str, int]]) -> int | None:
    if name in module_ints:
        return module_ints[name]
    # follow the import to its defining file, within this service (resolving by the ORIGINAL
    # name so an alias like `TIMELINE_LIMIT_DEFAULT as KG_TIMELINE_LIMIT_DEFAULT` works).
    src = _import_sources(path).get(name)
    if not src:
        return None
    src_mod, orig_name = src
    src_file = _module_to_file(src_mod, path)
    if not src_file:
        return None
    if src_file not in cache:
        cache[src_file] = _module_int_consts(src_file)
    return cache[src_file].get(orig_name)


def _default_map(fn: ast.AST) -> dict[str, ast.expr]:
    """param-name -> default AST node (positional tail + kwonly)."""
    args = fn.args
    out: dict[str, ast.expr] = {}
    pos = args.args
    off = len(pos) - len(args.defaults)
    for i, a in enumerate(pos):
        if i >= off:
            out[a.arg] = args.defaults[i - off]
    for a, d in zip(args.kwonlyargs, args.kw_defaults):
        if d is not None:
            out[a.arg] = d
    return out


def scan_file(path: str, allow: dict[str, str] | None = None,
              limit_ceil: int | None = None):
    """Returns (problems, subjects, unnecessary_exemptions).

    `subjects` is every LIST tool this file contributed — the gate's REACH. A
    scan that found no `detail`+`limit` pair has not found compliance; it has
    found nothing, and the two are byte-identical without this count (BDR-82).

    `unnecessary_exemptions` is the second death an ALLOW row can die: the tool
    it names now COMPLIES, so the row is waiving a rule the code already keeps —
    and it will go on waiving it the day the code stops (GT-F5)."""
    allow = ALLOW if allow is None else allow
    limit_ceil = LIMIT_CEIL if limit_ceil is None else limit_ceil
    subjects: list[str] = []
    unnecessary: list[str] = []
    try:
        src = open(path, encoding="utf-8").read()
        tree = ast.parse(src)
    except (OSError, SyntaxError):
        return [], subjects, unnecessary
    # module-level int constants for named-limit resolution
    module_ints: dict[str, int] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, int):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    module_ints[t.id] = node.value.value
    svc = _service_of(path)
    _const_cache: dict[str, dict[str, int]] = {}
    problems: list[str] = []

    def _check_pair(key: str, det_node, lim_node, lineno: int) -> None:
        subjects.append(key)
        # The rule is evaluated FIRST and the exemption applied to the RESULT, so
        # an ALLOW row that suppresses nothing can be detected. Returning early on
        # `key in ALLOW` made the two indistinguishable.
        found: list[str] = []
        _eval_pair(key, det_node, lim_node, lineno, found)
        if key in allow:
            if not found:
                unnecessary.append(
                    f"  ALLOW['{key}'] suppresses nothing — the tool already complies. "
                    f"Delete the row, or it keeps waiving the rule the day the code stops "
                    f"keeping it. (reason on file: {allow[key][:60]!r})")
            return
        problems.extend(found)

    def _eval_pair(key: str, det_node, lim_node, lineno: int, problems: list[str]) -> None:
        det = det_node.value if isinstance(det_node, ast.Constant) else None
        if det != "summary":
            problems.append(
                f"  {key}: detail defaults to {det!r} — a LIST tool must default detail=\"summary\" "
                f"(OUT-2). {path}:{lineno}"
            )
        lim = None
        # An UNBOUNDED default (`limit=None`) is the worst case: apply_response_contract treats
        # None as "no cap" (response.py: `items[:limit] if limit is not None else items`), so the
        # default reply grows with the user's data. A LIST tool must default to a bounded page.
        if isinstance(lim_node, ast.Constant) and lim_node.value is None:
            problems.append(
                f"  {key}: limit defaults to None (UNBOUNDED — no cap) — a LIST tool must default "
                f"to a bounded page (<= {limit_ceil}); None returns every row. {path}:{lineno}"
            )
        if isinstance(lim_node, ast.Constant) and isinstance(lim_node.value, int):
            lim = lim_node.value
        elif isinstance(lim_node, ast.Name):
            lim = _resolve_int(lim_node.id, module_ints, path, _const_cache)
            if lim is None:
                problems.append(
                    f"  {key}: limit default `{lim_node.id}` could not be resolved to an int in-file "
                    f"— cannot verify it's <= {limit_ceil}. {path}:{lineno}"
                )
        if isinstance(lim, int) and lim > limit_ceil:
            problems.append(
                f"  {key}: limit defaults to {lim} (> {limit_ceil}) — a default page that big crowds "
                f"the caller's context (OUT-2). {path}:{lineno}"
            )

    def _field_default(node):
        """The default AST node of a pydantic field: `x = 20` → 20; `x = Field(default=Y)` → Y."""
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "Field":
            for kw in node.keywords:
                if kw.arg == "default":
                    return kw.value
            return None  # Field(...) with no default → required (no default to check)
        return node

    # (1) inline function-param tools: `async def foo(..., detail=…, limit=…)`
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        params = {a.arg for a in fn.args.args + fn.args.kwonlyargs}
        if "detail" not in params or "limit" not in params:
            continue
        defaults = _default_map(fn)
        _check_pair(f"{svc}::{fn.name}", defaults.get("detail"), defaults.get("limit"), fn.lineno)

    # (2) request-MODEL tools: a pydantic class with both `detail` and `limit` fields — the
    # tool takes a single `args: SomeArgs`, so its LIST-ness is invisible to (1). This is the
    # blind spot that let composition `_MotifSearchArgs` (detail=full) ship un-flagged (K38).
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef):
            continue
        fields = {
            b.target.id: b.value
            for b in cls.body
            if isinstance(b, ast.AnnAssign) and isinstance(b.target, ast.Name) and b.value is not None
        }
        if "detail" in fields and "limit" in fields:
            _check_pair(
                f"{svc}::{cls.name}",
                _field_default(fields["detail"]), _field_default(fields["limit"]), cls.lineno,
            )

    return problems, subjects, unnecessary


def iter_files(staged: bool, services_root: str | None = None) -> list[str]:
    services_root = services_root or os.path.join(REPO_ROOT, "services")
    if staged:
        try:
            out = subprocess.run(
                ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
                cwd=REPO_ROOT, capture_output=True, text=True,
                timeout=GIT_TIMEOUT_S,
            ).stdout.split()
        except subprocess.TimeoutExpired:
            # NOT an empty list: that would make this gate scan nothing and
            # print PASS over a commit it never read.
            print(f"CANNOT RUN — `git diff --cached` did not return within "
                  f"{GIT_TIMEOUT_S}s; refusing to report a verdict on a file list "
                  f"that was never read.", file=sys.stderr)
            raise SystemExit(2)
        return [os.path.join(REPO_ROOT, f) for f in out if "/mcp/" in f.replace("\\", "/") and f.endswith(".py")]
    files = []
    for root, _dirs, names in os.walk(services_root):
        r = root.replace("\\", "/")
        if "/mcp" not in r or "__pycache__" in r:
            continue
        files.extend(os.path.join(root, n) for n in names if n.endswith(".py"))
    return files


def check(staged: bool = False, services_root: str | None = None,
          allow: dict[str, str] | None = None, limit_ceil: int | None = None) -> int:
    """The REAL checker, parameterised so `--self-test` can drive it over a
    synthetic tree instead of re-implementing its rules."""
    allow = ALLOW if allow is None else allow
    limit_ceil = LIMIT_CEIL if limit_ceil is None else limit_ceil

    files = iter_files(staged, services_root)
    problems: list[str] = []
    subjects: list[str] = []
    unnecessary: list[str] = []
    for f in files:
        p, s, u = scan_file(f, allow, limit_ceil)
        problems.extend(p)
        subjects.extend(s)
        unnecessary.extend(u)

    # ── REACH FLOORS (GT-F3). Only on a full scan: a staged run over a commit
    # touching no MCP file legitimately sees nothing.
    #
    # There is deliberately NO separate `not files` clause. Zero MCP files implies
    # zero subjects, so it would be strictly shadowed by the floor below and could
    # never produce a finding the sibling does not — deletable with the suite
    # green, which is the defect this whole board removes (`GTD-7`). The bite is
    # what said so: the arm disabling it still went red, on the other rule.
    if not staged:
        if not subjects:
            # The rule's SUBJECT is the `detail`+`limit` pair. If that convention is
            # renamed, this gate finds zero LIST tools and reports success in the same
            # bytes as full compliance. Measured 2026-08-12: 16 subjects across 14 files.
            print(f"✗ context-budget-defaults-lint: {len(files)} MCP file(s) scanned and "
                  f"NOT ONE declares a `detail`+`limit` pair. The rule has no subject, so "
                  f"its silence proves nothing — the convention was renamed, or the tools "
                  f"moved.", file=sys.stderr)
            return 2

        # ── SHRINK ARM (GT-F5), death #1: the row names a tool that no longer exists.
        # (Death #2 — the tool now complies — is `unnecessary`, raised in scan_file.)
        seen = set(subjects)
        for key in sorted(set(allow) - seen):
            unnecessary.append(
                f"  ALLOW['{key}'] names no LIST tool in this tree — it exempts nothing "
                f"today and would exempt that tool again the day the name returns.")

    if problems or unnecessary:
        if problems:
            print("✗ context-budget-defaults-lint: LIST tool(s) default to a context-crowding shape:\n")
            print("\n".join(problems))
            print(
                "\nFix: default `detail=\"summary\"` and `limit <= %d`; `detail=\"full\"` / a larger limit are "
                "explicit opt-ins the caller narrows UP to (OUT-2). A deliberate exemption gets a row in "
                "ALLOW with a reason." % limit_ceil
            )
        if unnecessary:
            print("✗ context-budget-defaults-lint: dead ALLOW row(s):\n")
            print("\n".join(unnecessary))
        return 1

    print(f"context-budget-defaults-lint: OK — {len(subjects)} LIST tool(s) across "
          f"{len(files)} MCP file(s) default to summary + limit <= {limit_ceil}; "
          f"{len(allow)} exemption(s).")
    return 0


# ── SELF-TEST ────────────────────────────────────────────────────────────────
# Every probe tree carries one COMPLIANT list tool, so the two reach floors stay
# quiet and each case below tests exactly one rule.
CLEAN_TOOL = (
    'async def things_list(detail: str = "summary", limit: int = 10):\n'
    '    return []\n'
)


def self_test() -> int:
    import contextlib
    import io
    import tempfile

    failures = 0

    def probe(name: str, want: int, body: str | None, *, allow=None, limit_ceil=25,
              rel="svc/app/mcp/tools.py", seed_clean=True) -> None:
        nonlocal failures
        with tempfile.TemporaryDirectory() as d:
            services = os.path.join(d, "services")
            # `seed_clean` is independent of `body`. An earlier draft wrote the
            # clean tool whenever a body was given, so the "no detail+limit pair
            # anywhere" probe silently got one and never reached its own fixture.
            if seed_clean:
                clean = os.path.join(services, "svc", "app", "mcp", "clean.py")
                os.makedirs(os.path.dirname(clean), exist_ok=True)
                with open(clean, "w", encoding="utf-8") as fh:
                    fh.write(CLEAN_TOOL)
            if body is not None:
                full = os.path.join(services, *rel.split("/"))
                os.makedirs(os.path.dirname(full), exist_ok=True)
                with open(full, "w", encoding="utf-8") as fh:
                    fh.write(body)
            os.makedirs(services, exist_ok=True)
            try:
                with contextlib.redirect_stdout(io.StringIO()), \
                        contextlib.redirect_stderr(io.StringIO()):
                    got = check(False, services, allow or {}, limit_ceil)
            except Exception as e:  # noqa: BLE001 - a crash is what this asserts against
                failures += 1
                print(f"  FAIL {name}: raised {type(e).__name__}: {e} — it must return a code")
                return
        ok = got == want
        failures += 0 if ok else 1
        print(f"  {'ok  ' if ok else 'FAIL'} {name}: rc={got} (want {want})")

    print("context-budget-defaults-lint --self-test")

    probe("a summary+small-limit list tool passes", 0, CLEAN_TOOL)

    # the rule, both halves
    probe("detail defaulting to full fails", 1,
          'async def t(detail: str = "full", limit: int = 10):\n    return []\n')
    probe("a limit above the ceiling fails", 1,
          'async def t(detail: str = "summary", limit: int = 50):\n    return []\n')
    probe("...and the ceiling is what decides it", 0,
          'async def t(detail: str = "summary", limit: int = 50):\n    return []\n',
          limit_ceil=50)
    probe("an UNBOUNDED limit=None fails", 1,
          'async def t(detail: str = "summary", limit=None):\n    return []\n')
    probe("a single-item tool (detail, no limit) is exempt", 0,
          'async def t(detail: str = "full"):\n    return {}\n')

    # named constants
    probe("a named limit constant over the ceiling fails", 1,
          'CAP = 500\nasync def t(detail: str = "summary", limit: int = CAP):\n    return []\n')
    probe("...but a small one passes", 0,
          'CAP = 10\nasync def t(detail: str = "summary", limit: int = CAP):\n    return []\n')
    probe("an UNRESOLVABLE named limit fails rather than passing silently", 1,
          'async def t(detail: str = "summary", limit: int = MYSTERY):\n    return []\n')

    # the request-MODEL blind spot (K38)
    probe("a pydantic request model with detail=full fails", 1,
          'class Args:\n    detail: str = "full"\n    limit: int = 10\n')
    probe("...including one using Field(default=...)", 1,
          'class Args:\n    detail: str = Field(default="full")\n    limit: int = Field(default=10)\n')
    # The case above reds whether or not `Field(default=…)` is unwrapped — an
    # un-unwrapped Call is not the constant "summary" either, so it violates for
    # the wrong reason. THIS is the case that isolates the unwrapping: a
    # COMPLIANT Field model must come back clean, and does not without it.
    probe("...and a COMPLIANT Field(default=...) model does not cry wolf", 0,
          'class Args:\n    detail: str = Field(default="summary")\n    limit: int = Field(default=10)\n')

    # ALLOW + both shrink-arm deaths
    probe("an ALLOW row suppresses a real violation", 0,
          'async def t(detail: str = "full", limit: int = 10):\n    return []\n',
          allow={"svc::t": "tracked debt"})
    probe("an ALLOW row for a COMPLIANT tool fails (reason expired)", 1,
          'async def t(detail: str = "summary", limit: int = 10):\n    return []\n',
          allow={"svc::t": "tracked debt"})
    probe("an ALLOW row naming no tool at all fails (subject gone)", 1, CLEAN_TOOL,
          allow={"svc::vanished": "tracked debt"})

    # scope + reach
    probe("a tool OUTSIDE an mcp/ directory is not scanned", 0,
          'async def t(detail: str = "full", limit: int = 99):\n    return []\n',
          rel="svc/app/routers/things.py")
    probe("no MCP files at all is misuse (the subject floor catches it)", 2, None,
          seed_clean=False)
    probe("MCP files with NO detail+limit pair is misuse, not a pass", 2,
          'async def t(limit: int = 10):\n    return []\n', seed_clean=False)

    if failures:
        print(f"context-budget-defaults-lint --self-test: {failures} rule(s) did not behave")
        return 2
    print("context-budget-defaults-lint --self-test: every rule bites, and none cries wolf")
    return 0


def main() -> int:
    if "--self-test" in sys.argv or "--selftest" in sys.argv:
        return self_test()
    rc = self_test()
    if rc:
        return rc
    print()
    return check("--staged" in sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
