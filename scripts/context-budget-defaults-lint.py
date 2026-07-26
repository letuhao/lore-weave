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


def scan_file(path: str) -> list[str]:
    try:
        src = open(path, encoding="utf-8").read()
        tree = ast.parse(src)
    except (OSError, SyntaxError):
        return []
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
        if key in ALLOW:
            return
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
                f"to a bounded page (<= {LIMIT_CEIL}); None returns every row. {path}:{lineno}"
            )
        if isinstance(lim_node, ast.Constant) and isinstance(lim_node.value, int):
            lim = lim_node.value
        elif isinstance(lim_node, ast.Name):
            lim = _resolve_int(lim_node.id, module_ints, path, _const_cache)
            if lim is None:
                problems.append(
                    f"  {key}: limit default `{lim_node.id}` could not be resolved to an int in-file "
                    f"— cannot verify it's <= {LIMIT_CEIL}. {path}:{lineno}"
                )
        if isinstance(lim, int) and lim > LIMIT_CEIL:
            problems.append(
                f"  {key}: limit defaults to {lim} (> {LIMIT_CEIL}) — a default page that big crowds "
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

    return problems


def iter_files(staged: bool) -> list[str]:
    if staged:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        ).stdout.split()
        return [os.path.join(REPO_ROOT, f) for f in out if "/mcp/" in f.replace("\\", "/") and f.endswith(".py")]
    files = []
    for root, _dirs, names in os.walk(os.path.join(REPO_ROOT, "services")):
        r = root.replace("\\", "/")
        if "/mcp" not in r or "__pycache__" in r:
            continue
        files.extend(os.path.join(root, n) for n in names if n.endswith(".py"))
    return files


def main() -> int:
    staged = "--staged" in sys.argv
    problems: list[str] = []
    for f in iter_files(staged):
        problems.extend(scan_file(f))
    if problems:
        print("✗ context-budget-defaults-lint: LIST tool(s) default to a context-crowding shape:\n")
        print("\n".join(problems))
        print(
            "\nFix: default `detail=\"summary\"` and `limit <= %d`; `detail=\"full\"` / a larger limit are "
            "explicit opt-ins the caller narrows UP to (OUT-2). A deliberate exemption gets a row in "
            "ALLOW with a reason." % LIMIT_CEIL
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
