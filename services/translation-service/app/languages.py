"""Content-language registry — the Python mirror of the D-4 SSOT
(contracts/languages.contract.json), the twin of the frontend's src/lib/languages.ts
LANGUAGE_REGISTRY.

Spec: docs/specs/2026-07-01-writing-studio/29_translation_repair.md (D13). This is the
closed set of languages a novel can be translated INTO. The write path normalizes then
validates against it ("VI"→"vi", "zh_CN"→"zh-CN"; anything outside → rejected), so a value
like the legacy free-text "Vietnamese" can no longer enter the store. Reads still tolerate
unknown legacy codes — this constrains WRITES only.

Kept in exact parity with the contract by tests/test_languages_parity.py (and the frontend's
own parity test). Adding a language = one entry in the contract + here + the frontend registry;
the parity tests red until all three agree.
"""
from __future__ import annotations

from typing import TypedDict


class LanguageEntry(TypedDict):
    code: str
    englishName: str
    endonym: str
    script: str
    dir: str
    uiLocale: bool
    translationTarget: bool


# Order mirrors the contract (display order in the pickers). Mirror — NOT loaded from the
# contract file at runtime (the service image does not ship contracts/); the parity test is
# what binds this list to the SSOT.
LANGUAGE_REGISTRY: list[LanguageEntry] = [
    {"code": "en",    "englishName": "English",               "endonym": "English",            "script": "Latin",      "dir": "ltr", "uiLocale": True, "translationTarget": True},
    {"code": "vi",    "englishName": "Vietnamese",            "endonym": "Tiếng Việt",         "script": "Latin",      "dir": "ltr", "uiLocale": True, "translationTarget": True},
    {"code": "ja",    "englishName": "Japanese",              "endonym": "日本語",             "script": "Japanese",   "dir": "ltr", "uiLocale": True, "translationTarget": True},
    {"code": "ko",    "englishName": "Korean",                "endonym": "한국어",             "script": "Hangul",     "dir": "ltr", "uiLocale": True, "translationTarget": True},
    {"code": "zh-CN", "englishName": "Chinese (Simplified)",  "endonym": "简体中文",           "script": "Hans",       "dir": "ltr", "uiLocale": True, "translationTarget": True},
    {"code": "zh-TW", "englishName": "Chinese (Traditional)", "endonym": "繁體中文",           "script": "Hant",       "dir": "ltr", "uiLocale": True, "translationTarget": True},
    {"code": "es",    "englishName": "Spanish",               "endonym": "Español",            "script": "Latin",      "dir": "ltr", "uiLocale": True, "translationTarget": True},
    {"code": "pt-BR", "englishName": "Portuguese (Brazil)",   "endonym": "Português (Brasil)", "script": "Latin",      "dir": "ltr", "uiLocale": True, "translationTarget": True},
    {"code": "fr",    "englishName": "French",                "endonym": "Français",           "script": "Latin",      "dir": "ltr", "uiLocale": True, "translationTarget": True},
    {"code": "de",    "englishName": "German",                "endonym": "Deutsch",            "script": "Latin",      "dir": "ltr", "uiLocale": True, "translationTarget": True},
    {"code": "ru",    "englishName": "Russian",               "endonym": "Русский",            "script": "Cyrillic",   "dir": "ltr", "uiLocale": True, "translationTarget": True},
    {"code": "id",    "englishName": "Indonesian",            "endonym": "Bahasa Indonesia",   "script": "Latin",      "dir": "ltr", "uiLocale": True, "translationTarget": True},
    {"code": "ms",    "englishName": "Malay",                 "endonym": "Bahasa Melayu",      "script": "Latin",      "dir": "ltr", "uiLocale": True, "translationTarget": True},
    {"code": "tr",    "englishName": "Turkish",               "endonym": "Türkçe",             "script": "Latin",      "dir": "ltr", "uiLocale": True, "translationTarget": True},
    {"code": "ar",    "englishName": "Arabic",                "endonym": "العربية",            "script": "Arabic",     "dir": "rtl", "uiLocale": True, "translationTarget": True},
    {"code": "hi",    "englishName": "Hindi",                 "endonym": "हिन्दी",              "script": "Devanagari", "dir": "ltr", "uiLocale": True, "translationTarget": True},
    {"code": "bn",    "englishName": "Bengali",               "endonym": "বাংলা",              "script": "Bengali",    "dir": "ltr", "uiLocale": True, "translationTarget": True},
    {"code": "th",    "englishName": "Thai",                  "endonym": "ภาษาไทย",            "script": "Thai",       "dir": "ltr", "uiLocale": True, "translationTarget": True},
]

# Ordered list of the translation-target codes — the closed set the picker offers and the
# write path accepts. All 18 entries are targets today; the flag keeps room for a
# locale-only future entry.
TRANSLATION_TARGET_CODES: list[str] = [e["code"] for e in LANGUAGE_REGISTRY if e["translationTarget"]]
_TARGET_SET = set(TRANSLATION_TARGET_CODES)


def normalize_language(value: str) -> str:
    """Case-fold + region-normalize a lenient client value BEFORE validation, so a correct
    language typed loosely is fixed rather than rejected:

        "VI"    -> "vi"
        "zh_CN" -> "zh-CN"
        "en-us" -> "en-US"

    A 2-letter subtag after the primary is treated as a region (upper-cased); a 4-letter one
    as a script (title-cased). An unknown free-text string ("Vietnamese") normalizes to
    lower-case and simply fails the registry check downstream.
    """
    s = (value or "").strip().replace("_", "-")
    if not s:
        return s
    parts = s.split("-")
    out = [parts[0].lower()]
    for p in parts[1:]:
        if len(p) == 2:
            out.append(p.upper())
        elif len(p) == 4:
            out.append(p.capitalize())
        else:
            out.append(p.lower())
    return "-".join(out)


def is_translation_target(code: str) -> bool:
    """True iff `code` is exactly in the registry's translation-target set (post-normalize)."""
    return code in _TARGET_SET
