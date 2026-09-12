#!/usr/bin/env python3
"""Gate: a translated string keeps every placeholder and interpolation the English one has.

WHY. On 2026-09-13 a single fix added ten keys across seventeen languages — 197 strings, produced
by a local model and read by nobody. Several carry runtime interpolation:

    "Asked for ~{{target}} words, delivered {{actual}} ({{pct}}%)."
    "Your rules total ~{{total}} tokens, over the ~{{cap}} that reach the model."

**A dropped placeholder is not a translation-quality opinion, it is a broken string.** i18next
renders what is left, so a Vietnamese author sees "Asked for ~ words, delivered ({{pct}}%)" — a
sentence with a hole in it — while every test stays green, because tests assert on KEYS and the
English bundle is fine.

`i18n_translate.py` already verifies this AT GENERATION TIME. Nothing verified it AT REST, which is
where a hand-edit, a bad merge, or a filtered regeneration lands — and this repo has just done all
three to these files in one day.

SCOPE. `en` is the source of truth. For every other locale, for every key present in both, the set
of `{{name}}` placeholders must match, `$t(...)` references must match, and the value must not be
empty. Keys MISSING from a locale are `i18n-completeness-gate.py`'s job, not this one — two gates
reporting the same defect teach people to read neither.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LOCALES = REPO / "frontend" / "src" / "i18n" / "locales"
SOURCE = "en"

#: i18next interpolation: {{name}}, {{name, format}}, {{- name}} (unescaped).
PLACEHOLDER = re.compile(r"\{\{\s*-?\s*([A-Za-z0-9_.]+)")
#: i18next nesting: $t(some.key)
NESTED = re.compile(r"\$t\(\s*([^)\s,]+)")


def _flat(obj, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(_flat(v, f"{prefix}.{k}" if prefix else k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(_flat(v, f"{prefix}[{i}]"))
    elif isinstance(obj, str):
        out[prefix] = obj
    return out


def check(bundles: dict[str, dict[str, dict]], ns: str = "<ns>") -> list[str]:
    """`bundles` maps locale -> parsed namespace JSON. Pure, so `--self-test` drives fixtures."""
    problems: list[str] = []
    if SOURCE not in bundles:
        return []

    src = _flat(bundles[SOURCE])
    for loc in sorted(bundles):
        if loc == SOURCE:
            continue
        tgt = _flat(bundles[loc])
        for key, en_val in src.items():
            if key not in tgt:
                continue  # completeness is another gate's job — see the module docstring.
            val = tgt[key]

            if not val.strip():
                problems.append(
                    f"{loc}/{ns}: {key!r} is empty or whitespace — it renders as nothing, which "
                    f"reads to a user as a missing feature rather than a missing translation."
                )
                continue

            en_ph, tg_ph = set(PLACEHOLDER.findall(en_val)), set(PLACEHOLDER.findall(val))
            if en_ph != tg_ph:
                lost, extra = sorted(en_ph - tg_ph), sorted(tg_ph - en_ph)
                bits = []
                if lost:
                    bits.append(f"DROPPED {lost}")
                if extra:
                    bits.append(f"INVENTED {extra}")
                problems.append(
                    f"{loc}/{ns}: {key!r} {' and '.join(bits)}. i18next renders what is left, so a "
                    f"dropped placeholder ships a sentence with a hole in it. en={en_val!r} "
                    f"{loc}={val!r}"
                )

            en_n, tg_n = set(NESTED.findall(en_val)), set(NESTED.findall(val))
            if en_n != tg_n:
                problems.append(
                    f"{loc}/{ns}: {key!r} $t() references differ — en={sorted(en_n)} "
                    f"{loc}={sorted(tg_n)}. A broken nest renders the raw key to the user."
                )
    return problems


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if "--self-test" in args:
        return self_test()

    if not LOCALES.is_dir():
        print(f"i18n-placeholder-parity-gate: no {LOCALES}; nothing to check")
        return 0

    src_dir = LOCALES / SOURCE
    if not src_dir.is_dir():
        print(f"i18n-placeholder-parity-gate: FAIL — no '{SOURCE}' source bundle at {src_dir}")
        return 1

    locales = sorted(p.name for p in LOCALES.iterdir() if p.is_dir())
    problems: list[str] = []
    checked_ns = checked_strings = 0

    for ns_file in sorted(src_dir.glob("*.json")):
        ns = ns_file.stem
        bundles: dict[str, dict] = {}
        for loc in locales:
            f = LOCALES / loc / f"{ns}.json"
            if f.is_file():
                try:
                    bundles[loc] = json.loads(f.read_text(encoding="utf-8"))
                except json.JSONDecodeError as e:
                    problems.append(f"{loc}/{ns}: invalid JSON — {e}")
        if SOURCE in bundles:
            checked_ns += 1
            checked_strings += len(_flat(bundles[SOURCE])) * max(0, len(bundles) - 1)
        problems.extend(check(bundles, ns))

    if problems:
        print("i18n-placeholder-parity-gate: FAIL")
        for p in problems[:60]:
            print(f"  - {p}")
        if len(problems) > 60:
            print(f"  ... and {len(problems) - 60} more")
        return 1

    print(
        f"i18n-placeholder-parity-gate: OK -- {checked_strings} translated string(s) across "
        f"{checked_ns} namespace(s) x {len(locales) - 1} locale(s) keep every placeholder"
    )
    return 0


def self_test() -> int:
    """Each case is a string that renders wrong while every key-based test stays green."""
    def b(en: str, other: str) -> dict:
        return {"en": {"k": en}, "vi": {"k": other}}

    cases = [
        ("identical placeholders pass", b("Asked {{n}} got {{m}}", "Hỏi {{n}} nhận {{m}}"), False),
        ("a DROPPED placeholder FAILS", b("Asked {{n}} got {{m}}", "Hỏi {{n}} nhận"), True),
        ("an INVENTED placeholder FAILS", b("Asked {{n}}", "Hỏi {{n}} {{oops}}"), True),
        ("reordered placeholders are fine", b("{{a}} then {{b}}", "{{b}} rồi {{a}}"), False),
        ("an empty translation FAILS", b("Something", "   "), True),
        ("the unescaped form {{- x}} is recognised", b("{{- raw}}", "xin chào"), True),
        ("a format spec is the same placeholder", b("{{n, number}}", "{{n, number}} cái"), False),
        ("a broken $t() nest FAILS", b("see $t(common.more)", "xem $t(common.less)"), True),
        ("a matching $t() nest passes", b("see $t(common.more)", "xem $t(common.more)"), False),
        ("a key missing from the locale is NOT this gate's business",
         {"en": {"a": "x {{n}}", "b": "y"}, "vi": {"a": "x {{n}}"}}, False),
        ("nested objects are walked",
         {"en": {"o": {"k": "{{n}}"}}, "vi": {"o": {"k": "nope"}}}, True),
        ("no en bundle means nothing to compare against", {"vi": {"k": "x"}}, False),
    ]

    failures = 0
    for desc, bundles, expect in cases:
        got = bool(check(bundles))
        ok = got == expect
        failures += not ok
        print(f"  {'ok  ' if ok else 'FAIL'} {desc}")

    print(f"i18n-placeholder-parity-gate --self-test: {'FAIL' if failures else 'OK'} "
          f"({len(cases) - failures}/{len(cases)})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
