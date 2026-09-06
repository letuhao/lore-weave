#!/usr/bin/env python3
"""Every in-repo `from app.… import …` must resolve — the module AND the name.

WHY THIS EXISTS, AND IT IS A MEASUREMENT NOT A HUNCH. Reconciling
`feat/frontend-tools-mcp-migration` into this branch on 2026-09-03, git merged
`app/tools/executor.py` CLEANLY into a file importing `app.db.neo4j_repos.facts`, a package this
branch had renamed to `app.db.graph_repos`. That line is the P7 chokepoint — the
`search_facts_by_text` leg of `memory_search` — and it is a FUNCTION-LEVEL import, so it survives
startup and raises only when the leg runs. Its own falsifier broke at import beside it, so the
suite could not report it either.

133 gate scripts were in the tree at the time. Not one of them looks at whether an import
resolves.

THE SECOND CASE IS WHY A GREP IS NOT ENOUGH. `app/routers/public/user_data.py` carried TWO dead
imports. The first was the rename (`neo4j_session`), findable by searching for the old name. The
second was `purge_project` — a symbol that MOVED from `app.db.neo4j_helpers` to
`app.db.graph_repos.project_graph` while both modules kept existing. No search for a renamed
*name* can find a moved *symbol*: the module resolves, the import line looks ordinary, and only
running it fails. So this gate checks the NAME too, not just the module.

WHAT IT DELIBERATELY DOES NOT DO. It resolves `app.*` only — the in-repo package of each Python
service. Third-party and stdlib imports are somebody else's problem and pretending to check them
would mean vendoring a dependency graph. It reads the AST, so a name mentioned in a docstring or
a comment is not a definition, and a `from … import x` inside a function is checked exactly like
one at module level (which is the point — see above).

CONSERVATIVE ON PURPOSE. A module may export names this gate cannot see: `__all__` entries built
at runtime, star-imports, attributes installed by a decorator. Where the module itself resolves
but the NAME cannot be found statically, the finding is reported only if the module has no
star-import and no dynamic `__all__`. A gate that cried wolf here would be switched off inside a
week, and a gate switched off catches nothing at all.
"""
from __future__ import annotations

import argparse
import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SERVICES = ROOT / "services"

#: Shrink-only. Raise it only with the reason written beside it, and never to make a red go away.
BASELINE = 0


def _service_roots() -> list[pathlib.Path]:
    """Every `services/<svc>/app` package — the root each `app.…` import is relative to."""
    if not SERVICES.is_dir():
        return []
    return sorted(p for p in SERVICES.glob("*/app") if p.is_dir())


def _module_path(app_root: pathlib.Path, dotted: str) -> pathlib.Path | None:
    """`app.db.graph_repos.facts` -> the .py file or package dir that provides it."""
    parts = dotted.split(".")
    if not parts or parts[0] != "app":
        return None
    rel = app_root.joinpath(*parts[1:])
    if rel.with_suffix(".py").is_file():
        return rel.with_suffix(".py")
    if (rel / "__init__.py").is_file():
        return rel / "__init__.py"
    return None


def _toplevel_names(path: pathlib.Path) -> tuple[set[str], bool]:
    """Names a module provides, and whether it is too dynamic to judge.

    The bool is the ESCAPE HATCH, and it is what keeps this gate usable: a module with a
    star-import or an `__all__` that is not a plain literal can export names no static reader can
    enumerate, so its names are not judged at all.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError):
        return set(), True
    names: set[str] = set()
    dynamic = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                # 🔴 TUPLE UNPACKING BINDS NAMES TOO, and missing it was this gate's own first
                # false positive: `fleiss_kappa, kappa_interpretation = _resolve()` in
                # lore-enrichment's `_ensemble_shim` binds both names, and reading only
                # `ast.Name` targets reported a module that exports them as exporting neither.
                # A gate's first run finding a defect in itself is the cheapest kind.
                for leaf in ast.walk(t):
                    if isinstance(leaf, ast.Name):
                        names.add(leaf.id)
                if isinstance(t, ast.Name) and t.id == "__all__":
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        # A literal `__all__` is the module ASSERTING what it provides. Trust it:
                        # the names may be bound by a decorator or a loop this reader cannot see.
                        names.update(e.value for e in node.value.elts
                                     if isinstance(e, ast.Constant) and isinstance(e.value, str))
                    else:
                        dynamic = True
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.ImportFrom):
            if node.level or node.names[0].name == "*":
                dynamic = dynamic or node.names[0].name == "*"
            for a in node.names:
                names.add(a.asname or a.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                names.add(a.asname or a.name.split(".")[0])
    return names, dynamic


def scan_file(path: pathlib.Path, app_root: pathlib.Path) -> list[str]:
    """Unresolvable `app.…` imports in one file, as reportable lines."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError):
        return []
    # The self-test drives a synthetic tree in a temp dir, which is not under ROOT. Falling back
    # to the raw path keeps the finding readable there instead of raising inside the checker.
    try:
        rel = path.relative_to(ROOT).as_posix()
    except ValueError:
        rel = path.as_posix()
    out: list[str] = []
    for node in ast.walk(tree):
        # ast.walk, NOT tree.body — a function-level import is the case that shipped.
        if not isinstance(node, ast.ImportFrom) or node.level or not node.module:
            continue
        if node.module != "app" and not node.module.startswith("app."):
            continue
        mod = _module_path(app_root, node.module)
        if mod is None:
            try:
                where = app_root.relative_to(ROOT).as_posix()
            except ValueError:
                where = app_root.as_posix()
            out.append(f"  {rel}:{node.lineno}: no module `{node.module}` under {where}")
            continue
        provided, dynamic = _toplevel_names(mod)
        if dynamic:
            continue
        pkg = mod.parent if mod.name == "__init__.py" else None
        for alias in node.names:
            if alias.name == "*" or alias.name in provided:
                continue
            # Module dunders exist on every module at runtime and appear in no AST. Importing
            # one is legal, and inventing a finding out of it is how a gate gets switched off.
            if alias.name.startswith("__") and alias.name.endswith("__"):
                continue
            # `from app.pkg import submodule` is legal and names no top-level symbol.
            if pkg is not None and ((pkg / f"{alias.name}.py").is_file()
                                    or (pkg / alias.name / "__init__.py").is_file()):
                continue
            out.append(f"  {rel}:{node.lineno}: `{node.module}` has no `{alias.name}`")
    return out


def check(services_root: pathlib.Path | None = None) -> int:
    roots = ([p for p in (services_root or SERVICES).glob("*/app") if p.is_dir()]
             if services_root else _service_roots())
    if not roots:
        print("import-resolution-gate: MISUSE — no `services/*/app` package found; a scan of "
              "nothing would report a clean bill of health.", file=sys.stderr)
        return 2
    findings: list[str] = []
    scanned = 0
    for app_root in roots:
        for f in sorted(app_root.rglob("*.py")):
            scanned += 1
            findings.extend(scan_file(f, app_root))
    # REACH FLOOR. A run that read almost nothing must not pass: the services moved, or the
    # layout changed, and either way silence proves nothing.
    if scanned < 100 and services_root is None:
        print(f"import-resolution-gate: MISUSE — only {scanned} file(s) scanned across "
              f"{len(roots)} service(s); the layout changed and this scan means nothing.",
              file=sys.stderr)
        return 2
    if len(findings) > BASELINE:
        print(f"✗ import-resolution-gate: {len(findings)} unresolvable in-repo import(s) "
              f"(baseline {BASELINE}) across {scanned} file(s):\n")
        print("\n".join(sorted(findings)))
        print("\nA renamed module is findable by searching for the old name. A MOVED symbol is "
              "not — the module still resolves and the line still reads ordinary. That is the "
              "case this gate exists for, and the case a merge produces.")
        return 1
    print(f"import-resolution-gate: OK — {scanned} file(s) across {len(roots)} service(s); "
          f"every in-repo `app.…` import resolves to a module and a name.")
    return 0


# ── SELF-TEST ────────────────────────────────────────────────────────────────────────────────
def _tree(tmp: pathlib.Path, files: dict[str, str]) -> pathlib.Path:
    for rel, body in files.items():
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return tmp


def self_test() -> int:
    import tempfile
    cases: list[tuple[str, dict[str, str], int]] = [
        ("a resolvable import passes", {
            "svc/app/__init__.py": "",
            "svc/app/db/__init__.py": "",
            "svc/app/db/facts.py": "def search_facts_by_text():\n    pass\n",
            "svc/app/tools.py": "from app.db.facts import search_facts_by_text\n",
        }, 0),
        ("THE ORIGINAL: a renamed package, imported inside a function", {
            "svc/app/__init__.py": "",
            "svc/app/db/__init__.py": "",
            "svc/app/db/graph_repos/__init__.py": "",
            "svc/app/db/graph_repos/facts.py": "def search_facts_by_text():\n    pass\n",
            "svc/app/tools.py": (
                "def memory_search():\n"
                "    from app.db.neo4j_repos.facts import search_facts_by_text\n"
                "    return search_facts_by_text\n"),
        }, 1),
        ("THE SECOND ONE: a MOVED symbol, both modules present", {
            "svc/app/__init__.py": "",
            "svc/app/db/__init__.py": "",
            "svc/app/db/helpers.py": "def run_read():\n    pass\n",
            "svc/app/db/project_graph.py": "def purge_project():\n    pass\n",
            "svc/app/router.py": "from app.db.helpers import purge_project\n",
        }, 1),
        ("a submodule imported from its package is not a missing name", {
            "svc/app/__init__.py": "",
            "svc/app/db/__init__.py": "",
            "svc/app/db/facts.py": "X = 1\n",
            "svc/app/tools.py": "from app.db import facts\n",
        }, 0),
        ("a star-importing module is NOT judged — the escape hatch", {
            "svc/app/__init__.py": "",
            "svc/app/db/__init__.py": "",
            "svc/app/db/facts.py": "from app.db.other import *\n",
            "svc/app/db/other.py": "Y = 2\n",
            "svc/app/tools.py": "from app.db.facts import anything_at_all\n",
        }, 0),
        ("a third-party import is none of this gate's business", {
            "svc/app/__init__.py": "",
            "svc/app/tools.py": "from fastapi import APIRouter\nfrom pydantic import BaseModel\n",
        }, 0),
        ("a module dunder is not a missing name", {
            "svc/app/__init__.py": "",
            "svc/app/tools.py": "from app import __name__ as n\n",
        }, 0),
    ]
    failures = 0
    for label, files, want in cases:
        with tempfile.TemporaryDirectory() as td:
            root = _tree(pathlib.Path(td), files)
            got = check(services_root=root)
        ok = got == want
        failures += not ok
        print(f"  {'ok  ' if ok else 'FAIL'} {label}: rc={got} (want {want})")
    if failures:
        print(f"import-resolution-gate --selftest: {failures} case(s) FAILED", file=sys.stderr)
        return 1
    print("import-resolution-gate --selftest: every rule bites, and none cries wolf")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", "--self-test", action="store_true", dest="selftest")
    args = ap.parse_args()
    if args.selftest:
        return self_test()
    rc = self_test()
    if rc:
        return rc
    print()
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
