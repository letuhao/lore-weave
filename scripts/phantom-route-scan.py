#!/usr/bin/env python3
"""PHANTOM ROUTE SCAN — does the frontend call routes the backend still serves?

WHY THIS EXISTS. Five separate bugs in one sweep (2026-07-28) reduced to a single shape: a caller
and a route that stopped agreeing, with green tests in between. The worst was live for months —
`UnknownEntitiesPanel`'s kind-resolution flow called `POST /v1/glossary/kinds` and
`POST /v1/glossary/kind-aliases`, both removed by SS-4. Eight unit tests asserted that flow and
passed, because they mocked the api module. Mocks cannot notice that a route stopped existing.

`GET /v1/glossary/kinds` still worked, which is exactly why nobody caught it: the path looked alive.
Only the METHOD had gone.

THE ORACLE, and why it is safe. Routing runs before authentication, so a deliberately INVALID token
separates the two cases without executing a single handler:

    401 / 403  → the route exists; auth rejected us (as designed)
    404 / 405  → nothing serves this path+method — a PHANTOM

No handler runs, no row is written, no id needs to exist. The scan is read-only by construction,
not by convention, which is what makes it safe to point at a live dev stack.

WHAT IT DELIBERATELY DOES NOT DO: guess. Every call site it cannot parse, and every URL whose
template it cannot resolve, is REPORTED — not skipped. A gate that silently under-discovers is
worse than no gate, because it certifies what it never looked at; this repo learned that twice in
one day from the atom-delete contract, which shipped green while blind to 8 of 14 families.

GT8 · WHAT THIS GATE LACKED. Its ORACLE self-check (below, in --probe) is the best
vacuity guard in this repo — it proves both arms on every run and refuses to report
anything if routing stops preceding auth. What it had no proof of was the EXTRACTOR:
`extract()` is a pure function of file text, and everything downstream is a claim
about what it found. A `--self-test` now drives it over synthetic TypeScript.

Two numbers it printed but did not enforce are now ratchets: UNPARSED call sites
(measured 0 of 74 modules — the blind spot the header calls "the gate's own coverage
gap") and the route count (719). A blind spot that only grows, and a corpus that can
quietly empty, are both ways this scan reports success over less than it did before.

AND ITS STRUCTURAL LIMIT, stated: without `--probe` nothing is verified against a
backend, so the exit code says only that extraction ran. The self-test is what makes
that green mean anything.

USAGE
    python scripts/phantom-route-scan.py                      # extract + report coverage only
    python scripts/phantom-route-scan.py --probe              # probe against localhost:3123
    python scripts/phantom-route-scan.py --probe --base-url http://host:port
    python scripts/phantom-route-scan.py --probe --json out.json

Exit codes: 0 = no phantoms · 1 = phantom routes found · 2 = the scan could not run.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"
DEFAULT_BASE_URL = "http://localhost:3123"

# Any well-formed but certainly-nonexistent id. Never resolved: auth fails first.
FAKE_ID = "00000000-0000-4000-8000-000000000000"
BOGUS_TOKEN = "phantom.route.scan.invalid.token"

SERVED = {401, 403}
PHANTOM = {404, 405}

#: Call sites the extractor could not parse. This IS the gate's blind spot, and the
#: header already said so — it just never changed colour. Measured 2026-08-12: 0 of
#: 74 modules. May only fall.
UNPARSED_CEIL = 0

#: Distinct (method, path) pairs discovered. A corpus that empties reports "0
#: phantoms" over nothing. Measured 2026-08-12: 719.
ROUTE_FLOOR = 500

# `apiJson<T>(url, { method: 'X' })` — the single helper every FE api module goes through.
_CALL = re.compile(r"apiJson\s*(?:<[^(]*?>)?\s*\(\s*", re.S)
# A file-scope `const NAME = '/v1/...'`, which is how each module names its prefix.
_CONST = re.compile(r"^\s*const\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*['\"]([^'\"]*)['\"]\s*;", re.M)
_INTERP = re.compile(r"\$\{[^}]*\}")


# Call sites that are DYNAMIC by design, with the reason. Declared rather than silently skipped —
# same discipline as the atom-delete contract: a gate may exclude something, but it must say what
# and why, or the exclusion becomes an invisible blind spot the next reader inherits.
_KNOWN_DYNAMIC = {
    "frontend/src/api.ts":
        "the helper retrying ITSELF after a token refresh — `path` is its own parameter, and the "
        "real route is whichever call site passed it (already covered there)",
    "frontend/src/features/chat/actionsApi.ts":
        "`${actionsBase(domain)}/…` — domain (glossary|book|translation|…) is a RUNTIME value, so "
        "the path cannot be resolved statically. Covered instead by each provider's own routes",
}

def _strip_comments(src: str) -> str:
    """Blank out comments, PRESERVING offsets so reported line numbers stay accurate.

    A char scanner, not two regexes, and the difference is not academic. The regex version blanked
    real code: this file's own `authoringRuns/api.ts` opens with a `//` comment containing the text
    `/v1/composition/authoring-runs/*`, and `/\\*.*?\\*/` happily treated that `/*` as a block
    opener, swallowing everything up to the next `*/` — including `const BASE = …`, which then made
    26 live call sites look unparseable. Comments, strings and template literals have to be
    tracked as STATES; anything less mis-reads one as the other.
    """
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c in "'\"`":                                  # a string: copy verbatim, comments inert
            quote = c
            out.append(c)
            i += 1
            while i < n:
                if src[i] == "\\":
                    out.append(src[i:i + 2]); i += 2; continue
                out.append(src[i])
                if src[i] == quote:
                    i += 1; break
                i += 1
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            while i < n and src[i] != "\n":
                out.append(" "); i += 1
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            while i < n and not (src[i] == "*" and i + 1 < n and src[i + 1] == "/"):
                out.append("\n" if src[i] == "\n" else " "); i += 1
            out.append("  "); i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


class Unparsed(Exception):
    """A call site we could not turn into a concrete path. Reported, never dropped."""


def _read_url_literal(src: str, i: int, consts: dict[str, str]) -> tuple[str, int]:
    """The first argument at `i` as a URL template, plus its end offset.

    Accepts a string literal (backtick / single / double) OR a bare identifier naming a
    file-scope const — `apiJson<World>(WORLDS, …)` is a real call site, not an unparsed one, and
    counting it as blind spot would overstate the gap as surely as hiding it would understate it.
    """
    while i < len(src) and src[i] in " \t\r\n":
        i += 1
    if i >= len(src):
        raise Unparsed("end of file after apiJson(")
    if src[i] not in "`'\"":
        ident = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*,", src[i:])
        if ident and ident.group(1) in consts:
            return consts[ident.group(1)], i + ident.end()
        raise Unparsed("first argument is not a string literal or a known const")
    quote, j, depth = src[i], i + 1, 0
    while j < len(src):
        c = src[j]
        if c == "\\":
            j += 2
            continue
        if quote == "`" and c == "$" and j + 1 < len(src) and src[j + 1] == "{":
            depth += 1
            j += 2
            continue
        if depth and c == "}":
            depth -= 1
        elif not depth and c == quote:
            return src[i + 1:j], j + 1
        j += 1
    raise Unparsed("unterminated string literal")


def _resolve(url: str, consts: dict[str, str]) -> str:
    """Template → probeable path.

    Two rules, both learned from this scanner's own first run producing 40 false phantoms:

    · NESTED BRACES. `${qs ? `?${qs}` : ''}` is one interpolation, not one ending at the first
      `}`. A regex stopping at `[^}]*` left `)}` glued to paths, so real routes probed as 404.
      The expression is matched by counting depth instead.

    · PATH PARAM vs SUFFIX. `/${id}` (preceded by a slash) is a path segment → a fake id.
      `outline${qs}` (glued to a segment) is a query string or suffix the variable carries → it
      contributes NOTHING to routing, so it resolves to empty. Substituting a fake id there
      invented `/outline00000000-…`, which of course 404s — the scanner would have reported a
      third of the API as phantom, and a gate that cries wolf gets ignored, which is the same
      end state as having no gate at all.
    """
    out, i, n = [], 0, len(url)
    while i < n:
        if url[i] == "$" and i + 1 < n and url[i + 1] == "{":
            depth, j = 1, i + 2
            while j < n and depth:
                depth += (url[j] == "{") - (url[j] == "}")
                j += 1
            if depth:
                raise Unparsed("unterminated interpolation")
            inner = url[i + 2:j - 1].strip()
            if inner in consts:
                out.append(consts[inner])
            elif not out:
                # An interpolation in FIRST position is the BASE (`${actionsBase(domain)}/preview`).
                # Dropping it as a "suffix" produced the path `/preview`, which naturally 404s —
                # a phantom conjured out of an unresolvable prefix. Refuse instead of inventing.
                raise Unparsed(f"unresolvable base expression `${{{inner}}}`")
            elif out[-1].endswith("/"):
                out.append(FAKE_ID)                  # a path segment
            else:
                pass                                  # a suffix / query string — not routing
            i = j
            continue
        out.append(url[i])
        i += 1
    path = "".join(out).split("?", 1)[0].rstrip("/") or "/"
    if not path.startswith("/"):
        raise Unparsed(f"not an absolute path: {path!r}")
    return path


def _methods_in(window: str) -> list[str]:
    """Every HTTP method this call can issue.

    `apiJson` defaults to GET, so NO `method:` key means GET. But a `method:` that is present and
    DYNAMIC must not fall back to that default: `method: pinned ? 'POST' : 'DELETE'` did exactly
    that on the first run, and since the route serves POST+DELETE the GET probe came back 405 —
    the scanner reporting a live, correct call site as a phantom. A conditional yields BOTH verbs;
    a `method:` with no literal at all is not guessed, it is `UNKNOWN` and gets reported.
    """
    m = re.search(r"method\s*:", window)
    if not m:
        return ["GET"]
    expr = window[m.end():]
    expr = expr[:expr.find(",\n")] if ",\n" in expr[:200] else expr[:200]
    verbs = re.findall(r"['\"](GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)['\"]", expr)
    return sorted(set(verbs)) or ["UNKNOWN"]


def extract(files: list[pathlib.Path]) -> tuple[dict[tuple[str, str], str], list[str], list[str]]:
    """{(METHOD, path): 'file:line'}, the call sites we could NOT parse, and the declared-dynamic."""
    routes: dict[tuple[str, str], str] = {}
    unparsed: list[str] = []
    dynamic: list[str] = []
    for f in files:
        rel = f.relative_to(ROOT).as_posix()
        src = _strip_comments(f.read_text(encoding="utf-8", errors="ignore"))
        consts = {n: v for n, v in _CONST.findall(src)}
        for m in _CALL.finditer(src):
            nl = chr(10)
            line_start = src.rfind(nl, 0, m.start()) + 1
            line_end = src.find(nl, m.start())
            line = src[line_start:line_end if line_end != -1 else len(src)]
            # The helper's own DECLARATION and every `import { apiJson }` match the call pattern
            # but are not call sites. Counting them as unparsed would inflate the reported blind
            # spot — a gate has to be honest in both directions about what it did not look at.
            if line.lstrip().startswith("import ") or "function apiJson" in line:
                continue
            where = f"{rel}:{src.count(chr(10), 0, m.start()) + 1}"
            try:
                url, end = _read_url_literal(src, m.end(), consts)
                path = _resolve(url, consts)
            except Unparsed as exc:
                (dynamic if rel in _KNOWN_DYNAMIC else unparsed).append(f"{where}  ({exc})")
                continue
            # The options object belongs to THIS call, so the window is bounded by the call's OWN
            # closing paren — counted, not guessed. "Up to the next apiJson, else 400 chars" read
            # `getUnlistedChapter`'s window straight into the NEXT function, picked up an unrelated
            # `method: 'POST'` (that neighbour uses XHR, so there was no apiJson to stop at) and
            # reported a live GET route as a phantom.
            depth, k = 1, end
            while k < len(src) and depth:
                depth += (src[k] == "(") - (src[k] == ")")
                k += 1
            window = src[end:k]
            for method in _methods_in(window):
                routes.setdefault((method, path), where)
    return routes, unparsed, dynamic


# A 404 whose body carries a DOMAIN error code came from a handler that ran — the route exists and
# the fake id simply matched nothing. Only the framework's own default 404 means "no route".
#   FastAPI  {"detail":"Not Found"}      ·  chi  "404 page not found"
# Without this the scan called 8 live public endpoints phantom: `/v1/catalog/books/{id}` answered
# `{"code":"BOOK_NOT_FOUND"}` and `/v1/users/{id}` answered `{"code":"AUTH_USER_NOT_FOUND"}`. The
# bogus-token oracle only silences handlers on AUTHENTICATED routes; a public one runs regardless,
# and that blind spot is precisely where the false positives clustered.
_FRAMEWORK_404 = ('{"detail":"not found"}', "404 page not found", "cannot ")


def probe(method: str, path: str, base_url: str, timeout: float) -> tuple[int | str, str]:
    """(status, verdict) — verdict ∈ {served, phantom, unknown}."""
    req = urllib.request.Request(
        base_url.rstrip("/") + path, method=method,
        headers={"Authorization": f"Bearer {BOGUS_TOKEN}", "Content-Type": "application/json"},
        # A body only so content-type-sniffing proxies behave; no handler ever reads it.
        data=b"{}" if method in {"POST", "PUT", "PATCH"} else None,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status, body = r.status, r.read(400).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        status, body = e.code, e.read(400).decode("utf-8", "replace")
    except Exception as e:                                   # noqa: BLE001 — surfaced, not hidden
        return f"unreachable: {type(e).__name__}", "unknown"

    if status in SERVED:
        return status, "served"
    if status == 405:
        return status, "phantom"                # the path matched; the METHOD did not. Unambiguous.
    if status == 404:
        squashed = " ".join(body.split()).lower()
        framework = any(squashed.startswith(s) for s in _FRAMEWORK_404) or not squashed
        return status, "phantom" if framework else "served"
    return status, "unknown"


def check_coverage(routes, unparsed, dynamic, *, unparsed_ceil=None, route_floor=None,
                   known_dynamic=None) -> list[str]:
    """The two ratchets and the shrink arm, as a pure function of what extract()
    returned — so a case can drive them without a frontend tree."""
    unparsed_ceil = UNPARSED_CEIL if unparsed_ceil is None else unparsed_ceil
    route_floor = ROUTE_FLOOR if route_floor is None else route_floor
    known_dynamic = _KNOWN_DYNAMIC if known_dynamic is None else known_dynamic
    problems: list[str] = []

    if len(unparsed) > unparsed_ceil:
        problems.append(
            f"{len(unparsed)} unparsed call site(s), ratchet is {unparsed_ceil}. This is the "
            f"gate's blind spot; it may shrink, not grow. Teach the extractor, or raise "
            f"UNPARSED_CEIL with a reason.")
    elif len(unparsed) < unparsed_ceil:
        problems.append(
            f"{len(unparsed)} unparsed call site(s), but the ratchet still says "
            f"{unparsed_ceil}. Set UNPARSED_CEIL={len(unparsed)}.")

    if len(routes) < route_floor:
        problems.append(
            f"only {len(routes)} route(s) extracted, floor is {route_floor}. A corpus that "
            f"emptied reports '0 phantoms' over nothing (BDR-82).")

    # ── SHRINK ARM (GT-F5) on _KNOWN_DYNAMIC. Each row excuses one file's
    # unresolvable call sites; a row whose file no longer HAS any is excusing
    # nothing, and would excuse the next unresolvable thing that appears there.
    seen_files = {d.split(":", 1)[0] for d in dynamic}
    for f in sorted(known_dynamic):
        if f not in seen_files:
            problems.append(
                f"_KNOWN_DYNAMIC names {f!r}, which has no unresolvable call site in this "
                f"tree — the row excuses nothing and would excuse the next one unasked.")
    return problems


# ── SELF-TEST ────────────────────────────────────────────────────────────────
def self_test() -> int:
    import tempfile

    failures = 0

    def case(name: str, want_routes, src: str, *, want_unparsed=0, want_dynamic=0,
             declared=False):
        nonlocal failures
        # INSIDE the repo: extract() computes `relative_to(ROOT)` for its report,
        # so a fixture in the system temp dir raises ValueError before any rule runs.
        with tempfile.TemporaryDirectory(dir=ROOT, prefix=".phantom-selftest-") as d:
            f = pathlib.Path(d) / "api.ts"
            f.write_text(src, encoding="utf-8")
            rel = f.relative_to(ROOT).as_posix()
            # `declared` puts the fixture in _KNOWN_DYNAMIC for one case, which is
            # the only way to exercise the DYNAMIC branch: an unresolvable call in
            # an UNDECLARED file is UNPARSED (loud) by design, and conflating the
            # two would have hidden exactly the blind spot this gate advertises.
            added = declared and rel not in _KNOWN_DYNAMIC
            if added:
                _KNOWN_DYNAMIC[rel] = "self-test fixture"
            try:
                routes, unparsed, dynamic = extract([f])
            except Exception as e:  # noqa: BLE001
                failures += 1
                print(f"  FAIL {name}: raised {type(e).__name__}: {e}")
                return
            finally:
                if added:
                    _KNOWN_DYNAMIC.pop(rel, None)
        got = sorted(routes)
        ok = (got == sorted(want_routes)
              and len(unparsed) == want_unparsed
              and len(dynamic) == want_dynamic)
        failures += 0 if ok else 1
        print(f"  {'ok  ' if ok else 'FAIL'} {name}: {got} "
              f"(+{len(unparsed)} unparsed, {len(dynamic)} dynamic)")

    def rc_case(name: str, want: int, routes, unparsed, dynamic, **kw):
        nonlocal failures
        problems = check_coverage(routes, unparsed, dynamic, **kw)
        got = 1 if problems else 0
        ok = got == want
        failures += 0 if ok else 1
        print(f"  {'ok  ' if ok else 'FAIL'} {name}: {len(problems)} problem(s) "
              f"(want {'some' if want else 'none'})")

    print("phantom-route-scan --self-test")

    # ── the extractor
    case("a literal GET is extracted", [("GET", "/v1/a")],
         'apiJson("/v1/a");\n')
    case("an explicit method is read", [("POST", "/v1/a")],
         'apiJson("/v1/a", { method: "POST" });\n')
    case("a const-referenced path resolves", [("GET", "/v1/base/x")],
         'const B = "/v1/base";\napiJson(`${B}/x`);\n')
    case("an id interpolation becomes a template segment",
         [("GET", "/v1/books/00000000-0000-4000-8000-000000000000/x")],
         'apiJson(`/v1/books/${id}/x`);\n')
    case("two methods on one path are two routes",
         [("DELETE", "/v1/a"), ("GET", "/v1/a")],
         'apiJson("/v1/a");\napiJson("/v1/a", { method: "DELETE" });\n')
    case("a commented-out call is ignored", [],
         '// apiJson("/v1/ghost");\n')
    case("a call inside a block comment is ignored", [],
         '/* apiJson("/v1/ghost"); */\n')
    # An unresolvable call in an UNDECLARED file is UNPARSED — reported as the
    # gate's blind spot, never dropped. That distinction is the header's whole
    # argument ("a gate that silently under-discovers … certifies what it never
    # looked at"), so both halves get a case.
    case("an unresolvable base in an UNDECLARED file is UNPARSED, not dropped", [],
         'apiJson(`${base(x)}/v1/a`);\n', want_unparsed=1)
    case("a non-literal first argument in an UNDECLARED file is UNPARSED", [],
         'apiJson(path, { method: "GET" });\n', want_unparsed=1)
    case("...but in a DECLARED-dynamic file the same call is dynamic, not unparsed", [],
         'apiJson(`${base(x)}/v1/a`);\n', want_dynamic=1, declared=True)

    # ── the ratchets + shrink arm
    many = {("GET", f"/v1/r{i}"): "x" for i in range(600)}
    rc_case("a healthy extraction is clean", 0, many, [], [], known_dynamic={})
    rc_case("an unparsed call site trips the ratchet", 1, many, ["a.ts:1"], [],
            known_dynamic={})
    rc_case("...and the ratchet reds when unparsed FALLS below it", 1, many, [], [],
            unparsed_ceil=1, known_dynamic={})
    rc_case("a shrunken corpus trips the route floor", 1,
            {("GET", "/v1/a"): "x"}, [], [], known_dynamic={})
    rc_case("a _KNOWN_DYNAMIC row with no dynamic site fails", 1, many, [], [],
            known_dynamic={"frontend/src/gone.ts": "why"})
    rc_case("...and passes when that file does have one", 0, many, [],
            ["frontend/src/gone.ts:12  (unresolvable)"],
            known_dynamic={"frontend/src/gone.ts": "why"})

    if failures:
        print(f"phantom-route-scan --self-test: {failures} rule(s) did not behave")
        return 2
    print("phantom-route-scan --self-test: every rule bites, and none cries wolf")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", action="store_true", help="probe each route against a running stack")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("--timeout", type=float, default=10.0)
    ap.add_argument("--json", dest="json_out", help="write the full result to this file")
    ap.add_argument("--self-test", "--selftest", dest="self_test", action="store_true",
                    help="prove the extractor and the ratchets bite, over synthetic sources")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    rc = self_test()
    if rc:
        return rc
    print()

    if not FRONTEND.is_dir():
        print(f"ERROR: {FRONTEND} not found — run from the repo root", file=sys.stderr)
        return 2

    files = sorted(
        p for p in list(FRONTEND.rglob("*.ts")) + list(FRONTEND.rglob("*.tsx"))
        if "__tests__" not in p.parts and "apiJson" in p.read_text(encoding="utf-8", errors="ignore")
    )
    routes, unparsed, dynamic = extract(files)

    print(f"scanned {len(files)} api modules → {len(routes)} distinct (method, path) pairs")

    problems = check_coverage(routes, unparsed, dynamic)
    if problems:
        for pr in problems:
            print(f"ERROR: {pr}", file=sys.stderr)
        return 2

    if unparsed:
        # Loud on purpose. This number IS the gate's blind spot; a gate that hides its own
        # coverage gap is the failure mode this file exists to avoid.
        print(f"\n⚠ {len(unparsed)} call site(s) NOT parsed — these are UNCHECKED, not clean:")
        for u in unparsed[:20]:
            print(f"    {u}")
        if len(unparsed) > 20:
            print(f"    … and {len(unparsed) - 20} more")

    if dynamic:
        print(f"\n{len(dynamic)} declared-dynamic call site(s) — resolvable only at runtime:")
        for d in dynamic:
            print(f"    {d}")
        for f, why in _KNOWN_DYNAMIC.items():
            print(f"    · {f}: {why}")

    if not args.probe:
        print("\n(no --probe: extraction only, NOTHING verified against a backend — this "
              "exit code says extraction ran, not that any route is served. The self-test "
              "above is what makes it mean something.)")
        return 0

    # ── ORACLE SELF-CHECK ──────────────────────────────────────────────────────────────────────
    # The whole scan rests on one assumption: routing runs BEFORE auth, so a bogus token yields
    # 401 for a live route and 404/405 for a dead one. If that ever stops holding — an edge auth
    # layer that rejects before proxying, a gateway that 200s everything — this file would report
    # "0 phantoms" forever and look like good news. That is the exact failure this session hit
    # twice (a gate green because it was blind). So prove the oracle on every run, both arms.
    dead, dead_v = probe("GET", "/v1/glossary/__phantom_route_scan_self_check__", args.base_url, args.timeout)
    live, live_v = probe("GET", "/v1/glossary/kinds", args.base_url, args.timeout)
    if dead_v != "phantom" or live_v != "served":
        print(f"ERROR: the oracle is not holding — a known-DEAD path returned {dead} "
              f"(expected 404/405) and a known-LIVE path returned {live} (expected 401/403).\n"
              f"       Either the stack is down or auth now runs before routing. Results from "
              f"this run would be meaningless, so it is refusing to produce any.", file=sys.stderr)
        return 2
    print(f"oracle ok (dead→{dead}, live→{live})")

    phantoms, unknown, served = [], [], 0
    for (method, path), where in sorted(routes.items()):
        status, verdict = probe(method, path, args.base_url, args.timeout)
        if verdict == "served":
            served += 1
        elif verdict == "phantom":
            phantoms.append((method, path, status, where))
        else:
            unknown.append((method, path, status, where))

    print(f"\nprobed {len(routes)} against {args.base_url}: {served} served, "
          f"{len(phantoms)} phantom, {len(unknown)} inconclusive")

    if unknown:
        print("\n— inconclusive (neither 401/403 nor 404/405; judge these yourself) —")
        for method, path, status, where in unknown:
            print(f"    {status}  {method:6} {path}    {where}")

    if phantoms:
        print("\n🔴 PHANTOM ROUTES — the frontend calls these; nothing serves them:")
        for method, path, status, where in phantoms:
            print(f"    {status}  {method:6} {path}    {where}")

    if args.json_out:
        pathlib.Path(args.json_out).write_text(json.dumps({
            "routes": [{"method": m, "path": p, "where": w} for (m, p), w in sorted(routes.items())],
            "phantoms": [{"method": m, "path": p, "status": s, "where": w} for m, p, s, w in phantoms],
            "unknown": [{"method": m, "path": p, "status": s, "where": w} for m, p, s, w in unknown],
            "unparsed": unparsed,
        }, indent=2), encoding="utf-8")

    return 1 if phantoms else 0


if __name__ == "__main__":
    sys.exit(main())
