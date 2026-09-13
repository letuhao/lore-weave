#!/usr/bin/env python3
"""A string 15 locales translated and one left in English is a GAP, not a convention.

    python scripts/i18n-untranslated-outlier-gate.py
    python scripts/i18n-untranslated-outlier-gate.py --self-test

WHAT THIS CATCHES THAT `i18n-placeholder-parity-gate.py` CANNOT
--------------------------------------------------------------
Placeholder parity proves a translation is STRUCTURALLY sound: every `{{name}}` in the
English survives into the other 17 locales. It verified 150,365 strings and it is worth
having. It is also, by construction, blind to a value that was never translated at all --
`"Project"` left as `"Project"` in Russian has perfect placeholder parity, because it has
the same placeholders as the English it was copied from.

That blindness is not theoretical. AC-8 of `docs/plans/2026-09-13-v0.1.0-ship-acceptance.md`
reads *"No user-facing string reaches a user that neither a person nor a mechanical check has
validated"*, and the honest status has been that 17 locales are machine-translated and unread.
This is a second mechanical check over the same population, aimed at the one defect a machine
translator actually produces often: silently passing text through.

THE SIGNAL, AND WHY IT IS A RATIO AND NOT A LIST
------------------------------------------------
Plenty of strings are identical to English on purpose -- `"OK"`, `"PDF"`, `"API"`, brand
names. Measured across this repo: **31 keys are identical in all 17 locales and 67 in 16**,
and those are conventions, not bugs. Flagging them would produce a gate nobody reads.

The defect has the opposite shape. **A key that 15+ locales translated and ONE left in English
is a gap in that one locale.** So the predicate is comparative: flag a key only when at most
`MAX_LOCALES` locales kept the English, and at least one of them writes in a NON-LATIN script,
where an English string is visibly foreign to the reader rather than merely borrowed.

WHAT IT CANNOT TELL YOU -- and this is the whole limit of it
------------------------------------------------------------
Nothing here reads meaning. A fluent, confident MISTRANSLATION passes this gate exactly as it
passes placeholder parity. This finds strings that were never translated; it cannot find
strings translated wrongly. AC-8 does not reach `met` on the strength of this file, and the
review record it is meant to support still needs a person.

Exit 0 = no NEW outlier; 1 = a new one; 2 = misuse / self-test failure.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

ROOT = "frontend/src/i18n/locales"
BASE = "en"

#: At most this many locales may keep the English before it reads as a convention rather
#: than a gap. 2 is deliberate: one locale is a clear miss, two can still be a miss, and by
#: three the balance tips toward "this word is borrowed" -- the histogram of this repo shows
#: the population thinning from 513 keys at one locale to 93 at three.
MAX_LOCALES = 2

#: Scripts where an untranslated English string is visibly foreign rather than a loanword.
#: Latin-script locales borrow English constantly (`de` alone keeps 473 strings), so including
#: them would bury the signal under normal German.
NON_LATIN = {"ar", "bn", "hi", "ja", "ko", "ru", "th", "zh-CN", "zh-TW"}

#: Values that are identical everywhere ON PURPOSE. Keyed by the English value, lowercased.
#: This is a term list, not a key list, so a new key carrying the same term is covered the day
#: it lands rather than the day someone remembers to add it.
UNIVERSAL_TERMS = {
    "api key", "api", "json", "raw json", "url", "uri", "id", "uuid", "pdf", "csv", "html",
    "markdown", "bearer token", "client id", "client secret", "oauth", "token", "webhook",
    "http", "https", "sse", "mcp", "llm", "rag", "ok", "email", "e-mail", "png", "jpeg",
    "svg", "yaml", "toml", "sql", "epub", "docx", "txt", "zip", "beta", "alpha", "temperature",
    "top_p", "top-p", "gpt", "wiki", "id token", "access token", "refresh token",
}

#: 🔴 THE BASELINE IS DEBT, NOT PERMISSION. Each row is a real outlier found on 2026-09-13 that
#: this gate is deliberately NOT failing on, because fixing them means WRITING TRANSLATIONS --
#: a native-language judgement that belongs to a person, not to an agent, and is tracked as T8
#: on the ship plan. The gate reds the moment a NEW one appears, so the debt cannot grow while
#: nobody is looking. Delete a row when its string is translated; do not add one to get green.
BASELINE: dict[str, str] = {
    "chat.inspector.title": "th kept 'Agent runtime' -- needs a Thai rendering (T8)",
    "composition.branchdiff.todo": "ja kept 'todo' (T8)",
    "kgOntology.adopt.scope.project": "ru kept 'Project' -- Russian localises this (T8)",
    "kgOntology.adopt.scope.user": "ru kept 'User' -- Russian localises this (T8)",
    "knowledge.temporal.timeline.interval.open": "ja kept '[{{from}} -> open)' (T8)",
    "studio.checkpoints.insert": "bn kept 'Inserted' (T8)",
    "usage.purpose.chunk_edit": "bn kept 'Chunk Edit' (T8)",
}


def _flatten(d: dict, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in (d or {}).items():
        kk = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flatten(v, kk))
        elif isinstance(v, str):
            out[kk] = v
    return out


def load(root: str = ROOT) -> dict[str, dict[str, str]]:
    data: dict[str, dict[str, str]] = {}
    if not os.path.isdir(root):
        return data
    for locale in sorted(os.listdir(root)):
        d = os.path.join(root, locale)
        if not os.path.isdir(d):
            continue
        merged: dict[str, str] = {}
        for f in sorted(glob.glob(os.path.join(d, "*.json"))):
            ns = os.path.basename(f)[:-5]
            try:
                with open(f, encoding="utf-8") as fh:
                    parsed = json.load(fh)
            except Exception:
                continue
            for k, v in _flatten(parsed).items():
                merged[f"{ns}.{k}"] = v
        data[locale] = merged
    return data


def outliers(data: dict[str, dict[str, str]], max_locales: int = MAX_LOCALES
             ) -> list[tuple[str, str, list[str]]]:
    """Keys left identical to English by at most `max_locales` locales, one non-Latin.

    Pure, and separate from the reporting, so both arms are testable without a locale tree.
    """
    en = data.get(BASE) or {}
    others = [l for l in data if l != BASE]
    found = []
    for key, raw in en.items():
        e = raw.strip()
        # Too short to be prose, or has no letters at all (`{{n}}`, `--`, `1`): identity here
        # says nothing. Length 3 is the shortest string worth an opinion; `OK` is not one.
        if len(e) <= 3 or not any(c.isalpha() for c in e):
            continue
        if e.lower() in UNIVERSAL_TERMS:
            continue
        same = [l for l in others if (data[l].get(key) or "").strip() == e]
        if not same or len(same) > max_locales:
            continue
        if not any(l in NON_LATIN for l in same):
            continue
        found.append((key, e, sorted(same)))
    return sorted(found)


def self_test() -> int:
    """Both arms, on synthetic data -- a gate that cannot go red is not a gate."""
    fails: list[str] = []

    # A key 3 locales translated and `ru` did not: MUST flag.
    d = {
        "en": {"a.b": "Project"},
        "ru": {"a.b": "Project"},
        "de": {"a.b": "Projekt"},
        "fr": {"a.b": "Projet"},
    }
    got = outliers(d)
    if len(got) != 1 or got[0][0] != "a.b" or got[0][2] != ["ru"]:
        fails.append(f"did NOT flag a string only `ru` left in English (vacuous): {got}")

    # The same shape, but every locale kept it: a CONVENTION, must NOT flag.
    d2 = {"en": {"a.b": "Webhook"}, "ru": {"a.b": "Webhook"}, "de": {"a.b": "Webhook"},
          "fr": {"a.b": "Webhook"}, "ja": {"a.b": "Webhook"}}
    if outliers(d2, max_locales=2):
        fails.append("flagged a term every locale keeps -- that is a convention, not a gap")

    # Only LATIN-script locales kept it: borrowing, must NOT flag.
    d3 = {"en": {"a.b": "Dashboard"}, "de": {"a.b": "Dashboard"}, "ja": {"a.b": "ダッシュボード"}}
    if outliers(d3):
        fails.append("flagged a Latin-script borrowing -- `de` keeping an English word is normal")

    # A universal technical term, kept by `ru` alone: must NOT flag.
    d4 = {"en": {"a.b": "API Key"}, "ru": {"a.b": "API Key"}, "de": {"a.b": "API-Schlüssel"}}
    if outliers(d4):
        fails.append("flagged a UNIVERSAL_TERMS entry")

    # A genuinely translated string: must NOT flag.
    d5 = {"en": {"a.b": "Settings"}, "ru": {"a.b": "Настройки"}, "de": {"a.b": "Einstellungen"}}
    if outliers(d5):
        fails.append("flagged a string that IS translated everywhere")

    if fails:
        print("i18n-untranslated-outlier-gate SELF-TEST FAILED:")
        for f in fails:
            print(f"  - {f}")
        return 2
    print("i18n-untranslated-outlier-gate: self-test OK — flags a one-locale English "
          "leftover, and stays quiet on conventions, Latin borrowings and real translations")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--root", default=ROOT)
    a = ap.parse_args()
    if a.self_test:
        return self_test()

    data = load(a.root)
    if len(data) < 2 or BASE not in data:
        # Zero locales is the shape of not looking, and it must never be spellable as a pass.
        print(f"i18n-untranslated-outlier-gate: FAIL — found {len(data)} locale dir(s) under "
              f"{a.root!r} and need '{BASE}' plus at least one other. The SCAN is empty, "
              f"not the tree.")
        return 1

    found = outliers(data)
    new = [(k, e, s) for k, e, s in found if k not in BASELINE]
    stale = [k for k in BASELINE if k not in {f[0] for f in found}]

    print(f"i18n-untranslated-outlier-gate: {len(data)} locales, "
          f"{len(data[BASE])} keys, {len(found)} outlier(s), {len(new)} new.")

    if stale:
        print(f"\n{len(stale)} BASELINE row(s) are STALE — the string is translated now:\n")
        for k in sorted(stale):
            print(f"  {k}")
        print("\nDelete the row. A baseline that never shrinks stops being debt and becomes "
              "a permanent exemption.")
        return 1

    if new:
        print(f"\n{len(new)} NEW untranslated outlier(s):\n")
        for k, e, s in new:
            print(f"  {','.join(s):14} {k}")
            print(f"  {'':14} kept the English: {e!r}")
        print("\nEvery other locale translated these. Translate them, or — if the term really "
              "is universal — add it to UNIVERSAL_TERMS with the reason.")
        return 1

    print(f"No NEW outlier. {len(BASELINE)} known, each tracked as T8 (a person must write "
          f"the translation).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
