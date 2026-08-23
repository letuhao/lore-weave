#!/usr/bin/env python3
"""Every env-gated skip must name a variable the registry documents.

A suite that skips is not a suite that passes. Measured 2026-08-23: the knowledge-service run
reported **4748 passed / 728 skipped** and read as green, while 24 of the skipped tests covered
`PgVectorStore` — the store T25 cut production passage reads onto. Three of them still asserted
the StreamingDiskANN design QC-3 had replaced, and the adapter was emitting `SET LOCAL diskann.*`
in every search transaction against an index type that no longer existed. The tests that would
have caught it were dark, so the adoption landed against them and nobody saw either half.

With every documented database present the same suite runs **5157 passed / 319 skipped**.

⚠️ **This gate does NOT fail on skips.** A developer without the containers must still be able to
run the suite, and a gate that punished that would be turned off within a day. What it refuses is
a skip whose variable is UNDOCUMENTED — a suite that can go dark with no instruction anywhere for
turning it back on.
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#: EVERY service, not one. The first version scanned `knowledge-service` alone, and
#: composition-service was sitting on **403** skipped tests behind
#: `TEST_COMPOSITION_DB_URL` — in the service that owns QC-5's critic. A registry gate
#: scoped to the service that motivated it cannot see the next one.
SERVICES = os.path.join(ROOT, "services")
REGISTRY = os.path.join(ROOT, "docs", "dev", "TEST_DATABASES.md")

#: A `pytest.skip("… TEST_FOO …")` names its variable in the message. Derived from the message
#: rather than from the `os.environ` lookup: the lookup may sit in a helper three frames up,
#: but the message is what a reader of the skip output actually sees.
_SKIP = re.compile(r"pytest\.skip\(\s*f?[\"']([^\"']{0,200})", re.S)
_VAR = re.compile(r"\bTEST_[A-Z][A-Z0-9_]*\b")

MAX_UNDOCUMENTED_TEST_VARS = 0


def scan(tests_root: str | None = None, registry_text: str | None = None):
    """`(vars named in skips, those the registry does not document)`."""
    if tests_root is None:
        tests_root = SERVICES
    named: set[str] = set()
    if os.path.isdir(tests_root):
        for base, _dirs, files in os.walk(tests_root):
            # Only test trees. Scanning a whole service would pick up `pytest.skip` mentioned
            # in application code or docs and invent variables nobody can set.
            if f"{os.sep}tests" not in base + os.sep:
                continue
            for f in sorted(files):
                if not f.endswith(".py"):
                    continue
                try:
                    src = open(os.path.join(base, f), encoding="utf-8", errors="replace").read()
                except OSError:
                    continue
                for msg in _SKIP.findall(src):
                    named |= set(_VAR.findall(msg))
    if registry_text is None:
        try:
            registry_text = open(REGISTRY, encoding="utf-8", errors="replace").read()
        except OSError:
            registry_text = ""
    # ⚠️ A WORD match, not a substring. The first version used `v not in registry_text`
    # and BITE 32 walked straight through it: renaming the entry to
    # `TEST_VECTOR_DB_URL_RENAMED` still "documents" `TEST_VECTOR_DB_URL`, because one
    # is a substring of the other. That is the SAME defect `conftest` records for T42a
    # — a guard matching `":7688"` as a substring sailed past `localhost:27688` — in
    # the opposite direction.
    missing = sorted(
        v for v in named
        if not re.search(r"\b" + re.escape(v) + r"\b(?![A-Z0-9_])", registry_text)
    )
    return sorted(named), missing


def selftest() -> int:
    print("test-env-registry-gate - selftest (offline)")
    ok = True
    import tempfile

    def _mk(body: str) -> str:
        """A synthetic service tree, INCLUDING the `tests/` directory.

        The scan only walks `tests/` trees — a whole-service walk would pick up `pytest.skip`
        named in application code or docs and invent variables nobody can set. The first
        version of this helper wrote to a bare tempdir, and every case silently scanned
        NOTHING the moment that filter landed: two selftest cases went red together, which is
        the only reason it was noticed rather than passing vacuously.
        """
        d = os.path.join(tempfile.mkdtemp(), "svc", "tests")
        os.makedirs(d)
        with open(os.path.join(d, "test_x.py"), "w", encoding="utf-8") as fh:
            fh.write(body)
        return os.path.dirname(d)

    # The case the gate exists for.
    d = _mk('pytest.skip("TEST_WIDGET_URL not set — skipping")\n')
    if scan(d, "nothing here") != (["TEST_WIDGET_URL"], ["TEST_WIDGET_URL"]):
        print("  FAIL — an UNDOCUMENTED env-gated skip was not reported"); ok = False
    else:
        print("  PASS  an undocumented env-gated skip is reported")

    # Documented -> silent. Without this the gate is satisfiable by reporting everything.
    if scan(d, "| `TEST_WIDGET_URL` | 3 tests | run a widget |")[1]:
        print("  FAIL — a DOCUMENTED variable was still reported"); ok = False
    else:
        print("  PASS  a documented variable is not reported")

    # A LONGER name must not "document" a shorter one. BITE 32 walked through the first
    # version, which used `v not in registry_text`: `TEST_WIDGET_URL` is a substring of
    # `TEST_WIDGET_URL_RENAMED`. That is the SAME defect conftest records for T42a, where a
    # guard matching ":7688" as a substring sailed past "localhost:27688".
    if not scan(d, "| `TEST_WIDGET_URL_RENAMED` | 3 tests |")[1]:
        print("  FAIL — a RENAMED entry still counted as documenting the original; the check "
              "is matching a substring, not a name")
        ok = False
    else:
        print("  PASS  a longer name does not document a shorter one")

    # A skip with no variable is not this gate's business — plenty are legitimately
    # conditional on a missing optional dependency, and inventing a variable for them would
    # make the registry a list of things nobody can set.
    d2 = _mk('pytest.skip("kuzu is an optional dependency")\n')
    if scan(d2, "")[0]:
        print("  FAIL — a skip naming NO variable was scored as env-gated"); ok = False
    else:
        print("  PASS  a skip that names no variable is ignored")

    # The real tree must be clean, and this is the arm that would catch the registry going
    # stale after a new suite lands.
    named, missing = scan()
    if missing:
        print(f"  FAIL — the real tree has undocumented variables: {missing}"); ok = False
    else:
        print(f"  PASS  the real tree: {len(named)} env-gated variable(s), all documented")

    print("\n  all checks passed" if ok else "\n  FAILURES above")
    return 0 if ok else 1


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    named, missing = scan()
    if len(missing) > MAX_UNDOCUMENTED_TEST_VARS:
        print(f"[test-env-registry-gate] FAIL — {len(missing)} env-gated skip variable(s) are "
              f"not documented: {missing}\n")
        print(f"  Add them to {os.path.relpath(REGISTRY, ROOT)} with the command that satisfies")
        print("  them. A suite that can go dark with no instruction for turning it back on is")
        print("  how QC-3's adoption landed against three tests that contradicted it.")
        return 1
    print(f"[test-env-registry-gate] OK — {len(named)} env-gated variable(s) named in skips, "
          f"all documented in docs/dev/TEST_DATABASES.md ({len(missing)} undocumented)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
