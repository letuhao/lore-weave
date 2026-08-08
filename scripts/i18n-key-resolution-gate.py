#!/usr/bin/env python3
"""Every literal `t('key')` a component calls resolves in the `en` bundle.

WHY THIS EXISTS
---------------
`i18n-completeness-gate.py` compares BUNDLE against BUNDLE: for each namespace it
checks that every locale holds the keys `en` holds. That is the right check for the
question it asks, and it is structurally blind to this one.

A string written as `t('some.key', { defaultValue: 'Some text' })` where `some.key`
is in NO bundle renders `'Some text'` and looks perfectly healthy in the app. But
`scripts/i18n_translate.py` generates translations by reading the `en` bundle, so a
key that is not there is never handed to it and never reaches the other locales. The
string stays in its source language in all 19 of them, permanently, while the
completeness gate reports full parity — because from the bundles' point of view
nothing is missing. Both tools are correct; the string is simply outside what either
can see.

Measured when this gate was written (2026-08-08): **609 keys** were in that state,
found by hand while reconciling PR #184 rather than by any check, 89% of them
predating that contribution. The same audit found what the blind spot costs: 30
user-facing strings had been authored in Russian — including the crash page every
user sees — and nothing could report it, because a defaultValue is not a bundle
entry and `doc-language-gate` reads `docs/`.

HOW IT RESOLVES A CALL
----------------------
i18next offers several shapes and getting these wrong produces false positives, which
is how a gate earns being ignored. Each of these was a wrong answer on an early run:

  * `const { t } = useTranslation('chat')` binds `t` to chat, but a file may hold
    SEVERAL bindings — `const { t: tKnowledge } = useTranslation('knowledge')` beside
    it. Namespaces are therefore tracked per identifier, not per file.
  * `t('common.cancel', { ns: 'common' })` overrides the binding for that one call.
  * `t('prefix.' + variant)` is a runtime-built key. Its literal prefix must not be
    mistaken for a whole key, hence the trailing `[,)]` in the pattern.
  * `t(key, 'a default')` passes its default positionally rather than as options.
  * A key may legitimately resolve to a LIST — `t(key, { returnObjects: true })` reads
    a whole array. A dict is still a failure: that is a subtree, not a string.

Keys built at runtime cannot be resolved statically, so they are counted and reported
rather than guessed at — the blind spot stays visible instead of implied.

    python scripts/i18n-key-resolution-gate.py            # all components
    python scripts/i18n-key-resolution-gate.py --staged   # staged files only
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_result import GateResult  # noqa: E402  (repo-local helper; path set above)

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "frontend" / "src"
EN = SRC / "i18n" / "locales" / "en"

# `const { t } = useTranslation('ns')` / `const { t: alias, i18n } = useTranslation('ns')`
BINDING = re.compile(r"const\s*\{([^}]*)\}\s*=\s*useTranslation\(\s*'([A-Za-z][A-Za-z0-9-]*)'")
# the `t` or `t: alias` inside that destructuring
T_BINDING = re.compile(r"\bt\s*(?::\s*(\w+))?\s*(?:,|$)")
# `{ ns: 'x' }` in a call's options — a per-call namespace override
NS_OPTION = re.compile(r"\bns:\s*'([A-Za-z][A-Za-z0-9-]*)'")


def call_pattern(ident: str) -> re.Pattern[str]:
    """A COMPLETE literal key passed to `ident`, plus any options object.

    The trailing `[,)]` is what separates `t('a.b')` from the prefix of
    `t('a.b.' + v)`; without it the latter is reported as a key ending in a dot."""
    return re.compile(
        r"\b" + re.escape(ident) + r"\(\s*'([A-Za-z][A-Za-z0-9_.]*)'\s*(?:,\s*(\{[^{}]*\}))?\s*[,)]"
    )


def dynamic_pattern(ident: str) -> re.Pattern[str]:
    return re.compile(r"\b" + re.escape(ident) + r"\(\s*(?!')[`A-Za-z_$({]")


def load_namespace(ns: str, _cache: dict = {}) -> dict | None:
    if ns not in _cache:
        path = EN / f"{ns}.json"
        try:
            _cache[ns] = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
        except json.JSONDecodeError:
            _cache[ns] = None
    return _cache[ns]


# i18next resolves `t(key, { count })` to a PLURAL SIBLING (`key_one`, `key_other`, …),
# and a bare `key` need not exist at all. Treating one of these as the whole key reports
# a working call as broken — measured on gap.bulkPromote.cta, which has _one/_other/_zero.
PLURAL_SUFFIXES = ("_zero", "_one", "_two", "_few", "_many", "_other")


def _leaf(bundle: dict, key: str):
    node = bundle
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _usable(node) -> bool:
    # A list is a legitimate leaf: `t(key, { returnObjects: true })` reads a whole array.
    # A dict is not — that is a subtree, and the caller wanted a string.
    return isinstance(node, str) or (
        isinstance(node, list) and all(isinstance(x, str) for x in node)
    )


def resolves(bundle: dict, key: str) -> bool:
    if _usable(_leaf(bundle, key)):
        return True
    return any(_usable(_leaf(bundle, key + suffix)) for suffix in PLURAL_SUFFIXES)


def bindings(text: str) -> dict[str, str]:
    """identifier -> namespace, for every useTranslation binding in the file."""
    out: dict[str, str] = {}
    for destructured, ns in BINDING.findall(text):
        m = T_BINDING.search(destructured)
        if m:
            out[m.group(1) or "t"] = ns
    return out


def components(staged_only: bool) -> list[Path]:
    if staged_only:
        listed = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            capture_output=True, text=True, cwd=REPO,
        ).stdout.split("\n")
        paths = [REPO / p for p in listed if p.endswith((".tsx", ".ts"))]
    else:
        paths = sorted(SRC.rglob("*.tsx"))
    return [p for p in paths if p.is_file() and "__tests__" not in p.as_posix()]


def main() -> int:
    staged_only = "--staged" in sys.argv
    result = GateResult(gate="rules")

    if not EN.is_dir() or not any(EN.glob("*.json")):
        # Either state would make every lookup below fail — or, written the other way
        # round, trivially pass. Refuse instead of reporting on nothing.
        print("i18n-key-resolution-gate: FAIL — no readable en bundle at "
              "frontend/src/i18n/locales/en; the check would not be meaningful.")
        return 1

    files = components(staged_only)
    checked = dynamic = 0
    scanned = 0

    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        bound = bindings(text)
        if not bound:
            continue
        scanned += 1
        rel = path.relative_to(REPO).as_posix()
        seen: set[tuple[str, str]] = set()
        for ident, file_ns in bound.items():
            dynamic += len(dynamic_pattern(ident).findall(text))
            for key, options in call_pattern(ident).findall(text):
                ns_override = NS_OPTION.search(options) if options else None
                ns = ns_override.group(1) if ns_override else file_ns
                if (ns, key) in seen:
                    continue
                seen.add((ns, key))
                bundle = load_namespace(ns)
                if bundle is None:
                    result.blocker(
                        id=f"i18n-ns-{ns}",
                        summary=f"{rel}: namespace '{ns}' has no readable en/{ns}.json",
                        file=rel,
                    )
                    continue
                checked += 1
                if not resolves(bundle, key):
                    result.blocker(
                        id=f"i18n-key-{ns}-{key}",
                        summary=f"{rel}: t('{key}') has no entry in en/{ns}.json",
                        file=rel,
                    )

    scope = "staged" if staged_only else "full-repo"
    if result.findings:
        print(f"i18n-key-resolution-gate ({scope}): FAIL — {len(result.findings)} "
              f"key(s) reachable from code but absent from the en bundle.\n")
        for finding in result.findings[:40]:
            print(f"  ✗ {finding.summary}")
        if len(result.findings) > 40:
            print(f"  … +{len(result.findings) - 40} more")
        print("\nA key with no en entry renders its defaultValue (or the key itself) and is\n"
              "never translated: i18n_translate.py reads the bundle, not the call site. Add it\n"
              "to frontend/src/i18n/locales/en/<ns>.json with the text already in the call, then:\n"
              "  python scripts/i18n_translate.py --ns <ns>")
        print(result.render())
        return result.exit_code()

    if checked == 0 and not staged_only:
        # Full-repo, zero keys found means the call shapes above stopped matching reality —
        # the gate would then "pass" every run while checking nothing, which is the exact
        # vacuity NV-2 describes. A STAGED run legitimately sees no components (a commit
        # touching only .ts helpers), so this must not apply there or the hook blocks
        # ordinary commits.
        print(f"i18n-key-resolution-gate: FAIL — no literal t() keys found across "
              f"{len(files)} file(s). This gate cannot pass by finding nothing to check; "
              "the call shapes it recognises have probably drifted.")
        return 1
    if staged_only and checked == 0:
        print("i18n-key-resolution-gate (staged): OK — no component with t() calls staged.")
        return 0

    result.note(f"{checked} literal key(s) across {scanned} component(s) resolve in en")
    if dynamic:
        result.note(f"{dynamic} runtime-built t() call(s) are not statically checkable")
    print(f"i18n-key-resolution-gate ({scope}): OK — {checked} literal key(s) resolve in en"
          + (f"; {dynamic} runtime-built call(s) skipped" if dynamic else ""))
    print(result.render())
    return result.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
