#!/usr/bin/env python3
"""Gate: the Campaigns feature must not be named or described as DRAFTING.

WHY. The feature shipped as the "Auto-Draft Factory", and the README promised it would *"run a
whole drafting campaign across chapters"*. It does not draft. The campaign saga dispatches
knowledge EXTRACTION and TRANSLATION and nothing else — a case-insensitive search of
`services/campaign-service/app/` for "draft" returns only the product name in three module
docstrings. A 2026-09-06 human-sim run measured the claims against the build and this one could
not be reconciled; the PO renamed it to **Campaigns** on 2026-09-13.

WHY A GATE AND NOT JUST THE RENAME. The old name reached EIGHTEEN locale files, two component
fallbacks, a route comment and two README lines. A rename that broad regrows: the next person to
add a string copies a neighbour, and "Auto-Draft" is still the name in the service directory, the
table names and the design docs, which are all deliberately NOT renamed (churn with no user
benefit). So the boundary between "internal name, fine" and "user-facing name, false" is exactly
the thing that needs mechanical defence.

THE THIRD CHECK IS THE STRUCTURAL ONE. Beyond blocking the word, this asserts each locale's
campaigns LIST heading equals that locale's own sidebar label. A page whose heading disagrees with
the nav item that opened it is a new inconsistency, not a fixed one — and that is precisely the
failure mode of a half-applied rename, which is how this defect would come back wearing different
clothes.

WHAT IT DOES NOT DO. It does not touch `services/campaign-service/`, the database tables, or the
design documents. Those keep the internal name on purpose.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
README = REPO / "README.md"
LOCALES = REPO / "frontend" / "src" / "i18n" / "locales"

#: User-facing English phrasings that put this feature back in the drafting business.
ENGLISH_BANNED = ("auto-draft", "auto draft", "drafting campaign")

#: locale -> substrings that mean "draft" in that language, as they appeared in the strings this
#: rename removed. Kept per-locale and explicit rather than one clever regex: a translator adding
#: a language gets an honest gap here, not a rule that silently half-matches their script.
DRAFT_WORDS: dict[str, tuple[str, ...]] = {
    "ar": ("مسودة",), "bn": ("ড্রাফট",), "de": ("Auto-Draft",), "en": ("draft",),
    "es": ("Auto-Draft",), "fr": ("Auto-Draft",), "hi": ("ड्राफ्ट",), "id": ("Auto-Draft",),
    "ja": ("ドラフト",), "ko": ("초안",), "ms": ("Draf",), "pt-BR": ("Rascunho",),
    "ru": ("черновик",), "th": ("Auto-Draft",), "tr": ("Taslak",), "vi": ("nháp",),
    "zh-CN": ("草拟", "草稿"), "zh-TW": ("草稿", "草擬"),
}

#: The two campaigns.json keys that NAME the feature to a user.
TITLE_KEYS = (("wizard", "title"), ("list", "title"))


def _sidebar_label(common: dict) -> str | None:
    """That locale's nav label for Campaigns, wherever it sits in the tree."""
    if isinstance(common, dict):
        for key, value in common.items():
            if key.lower() == "campaigns" and isinstance(value, str):
                return value
            found = _sidebar_label(value)
            if found:
                return found
    return None


def check(readme: str, locales: dict[str, tuple[dict, dict]]) -> list[str]:
    """Problems found. Pure, so `--self-test` drives it on fixtures instead of the real tree."""
    problems: list[str] = []

    for banned in ENGLISH_BANNED:
        for line in readme.splitlines():
            if banned in line.lower():
                problems.append(
                    f"README still describes this feature as drafting ({banned!r}):\n"
                    f"    {line.strip()}\n"
                    f"  It extracts and translates. Say that instead — the engine has no drafting "
                    f"stage, so this is not a wording preference."
                )

    for loc, (campaigns, common) in sorted(locales.items()):
        words = DRAFT_WORDS.get(loc)
        if words is None:
            problems.append(
                f"locale {loc!r} has no DRAFT_WORDS row in this gate. Add one in the same commit "
                f"that adds the locale — an unlisted language is unchecked, and unchecked is how "
                f"the old name survives a rename."
            )
            continue
        for section, key in TITLE_KEYS:
            title = campaigns.get(section, {}).get(key)
            if not isinstance(title, str):
                problems.append(f"{loc}/campaigns.json is missing {section}.{key}")
                continue
            for word in words:
                if word.lower() in title.lower():
                    problems.append(
                        f"{loc} {section}.{key} still names this feature after drafting: "
                        f"{title!r} contains {word!r}."
                    )

        listed = campaigns.get("list", {}).get("title")
        label = _sidebar_label(common)
        if label is None:
            problems.append(f"{loc}/common.json has no Campaigns nav label to compare against.")
        elif isinstance(listed, str) and listed != label:
            problems.append(
                f"{loc}: the campaigns page heading {listed!r} does not match its own sidebar "
                f"label {label!r}. A page that disagrees with the nav item that opened it is a "
                f"new inconsistency, which is what a half-applied rename looks like."
            )

    return problems


def _load() -> tuple[str, dict[str, tuple[dict, dict]]]:
    locales: dict[str, tuple[dict, dict]] = {}
    for d in sorted(p for p in LOCALES.iterdir() if p.is_dir()):
        campaigns, common = d / "campaigns.json", d / "common.json"
        if campaigns.exists() and common.exists():
            locales[d.name] = (
                json.loads(campaigns.read_text(encoding="utf-8")),
                json.loads(common.read_text(encoding="utf-8")),
            )
    return README.read_text(encoding="utf-8"), locales


def self_test() -> int:
    """Each case is a way the old name comes back, and none of them is hypothetical."""
    ok_locale = ({"wizard": {"title": "New Campaign"}, "list": {"title": "Campaigns"}},
                 {"nav": {"campaigns": "Campaigns"}})
    cases = [
        ("a clean README and locale pass", "- **Campaigns** — batch extraction", {"en": ok_locale}, False),
        ("README saying 'Auto-Draft' FAILS",
         "- **Auto-Draft Factory** — run it", {"en": ok_locale}, True),
        ("README saying 'drafting campaign' FAILS",
         "- **Campaigns** — run a whole drafting campaign", {"en": ok_locale}, True),
        ("a locale title that still says draft FAILS", "- **Campaigns** — batch extraction",
         {"en": ({"wizard": {"title": "New Auto-Draft Campaign"}, "list": {"title": "Campaigns"}},
                 {"nav": {"campaigns": "Campaigns"}})}, True),
        ("a heading that disagrees with its own sidebar FAILS", "- **Campaigns** — batch extraction",
         {"en": ({"wizard": {"title": "New Campaign"}, "list": {"title": "Batches"}},
                 {"nav": {"campaigns": "Campaigns"}})}, True),
        ("a locale with no DRAFT_WORDS row FAILS rather than passing unchecked",
         "- **Campaigns** — batch extraction", {"xx": ok_locale}, True),
    ]

    failures = 0
    for desc, readme, locales, expect in cases:
        got = bool(check(readme, locales))
        ok = got == expect
        failures += not ok
        print(f"  {'ok  ' if ok else 'FAIL'} {desc}")

    # And every locale the repo actually ships must have a row here, or the gate reports coverage
    # it does not have — the same hole its own fifth case describes.
    shipped = {p.name for p in LOCALES.iterdir() if p.is_dir() and (p / "campaigns.json").exists()}
    missing = sorted(shipped - set(DRAFT_WORDS))
    if missing:
        print(f"  FAIL locales shipped but unlisted in DRAFT_WORDS: {missing}")
        failures += 1
    else:
        print(f"  ok   all {len(shipped)} shipped locale(s) have a DRAFT_WORDS row")

    total = len(cases) + 1
    print(f"campaign-naming-gate --self-test: {'FAIL' if failures else 'OK'} "
          f"({total - failures}/{total})")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if "--self-test" in args:
        return self_test()

    readme, locales = _load()
    problems = check(readme, locales)
    if problems:
        print("campaign-naming-gate: FAIL")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"campaign-naming-gate: OK -- README + {len(locales)} locale(s) name it for what it does")
    return 0


if __name__ == "__main__":
    sys.exit(main())
