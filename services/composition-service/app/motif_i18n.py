"""Motif i18n — the translatable payload, its hash, and language resolution.

One motif = one row in its `original_language`; every other language is a
`motif_translation` row. This module is the single definition of *what is text*
(and therefore translatable) versus *what is structure* (and therefore lives only
on the source row). The migration, the seeder, the read path, and
`scripts/motif_translate.py` all import from here so the four can never drift —
a drift here is exactly the class of bug that shipped a Vietnamese motif summary
into an English book's scene prompt (docs/specs/2026-07-29-motif-i18n.md).

Design notes worth keeping:

* **Structure is never translated.** `code`, `kind`, `category` (a machine
  taxonomy — `romance.proximity`), `genre_tags`, `roles[].key`, `roles[].actant`,
  `beats[].key`, `beats[].tension_target`, `beats[].order`, `tension_target`,
  `annotations`, `info_asymmetry`. A translation therefore cannot add, drop, or
  reshape a motif — only re-word it.

* **Resolution merges PER LEAF, not all-or-nothing.** A translation covering 5 of
  6 beats renders the 6th in the original language rather than blank. This is the
  same no-silent-drop posture `scripts/i18n_translate.py` takes (a key it cannot
  translate ships as its English source, never empty).

* **Fallback is always reported.** `resolve_text` returns `text_language` and
  `text_fallback`, so no caller — model prompt or FE — can receive text without
  knowing which language it is in. The bug this replaces was silent.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

# ── what is translatable ───────────────────────────────────────────────────
# Scalars carried on the motif row itself.
TRANSLATABLE_SCALARS: tuple[str, ...] = ("name", "summary", "emotion_target")

# JSONB lists. `key` names the field that identifies an element across languages
# (so a reordered translation still merges correctly); None = positional match.
# `fields` are the translatable leaves inside each element — everything else in
# the element is structure and is taken from the SOURCE, always.
TRANSLATABLE_LISTS: dict[str, dict[str, Any]] = {
    "roles":         {"key": "key", "fields": ("label", "constraints")},
    "beats":         {"key": "key", "fields": ("label", "intent")},
    "preconditions": {"key": None,  "fields": ("text",)},
    "effects":       {"key": None,  "fields": ("text",)},
    "examples":      {"key": None,  "fields": ("text",)},
}

TRANSLATABLE_FIELDS: tuple[str, ...] = TRANSLATABLE_SCALARS + tuple(TRANSLATABLE_LISTS)


def _as_list(value: Any) -> list[dict[str, Any]]:
    """JSONB columns arrive as a list, or as a JSON string from some drivers."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return []
    if not isinstance(value, list):
        return []
    return [v for v in value if isinstance(v, dict)]


def extract_translatable(row: Any) -> dict[str, Any]:
    """Project a motif (row, dict, or model) down to only its translatable leaves.

    The result is what gets hashed, what gets handed to a translator, and the
    shape a `motif_translation` row stores.
    """
    get = row.get if isinstance(row, dict) else (lambda k, d=None: getattr(row, k, d))
    out: dict[str, Any] = {}
    for field in TRANSLATABLE_SCALARS:
        val = get(field)
        out[field] = val if isinstance(val, str) else ("" if val is None else str(val))
    for field, spec in TRANSLATABLE_LISTS.items():
        key_field, leaves = spec["key"], spec["fields"]
        elems = []
        for elem in _as_list(get(field)):
            projected: dict[str, Any] = {}
            if key_field:
                projected[key_field] = elem.get(key_field)
            for leaf in leaves:
                if leaf in elem:
                    projected[leaf] = elem[leaf]
            elems.append(projected)
        out[field] = elems
    return out


def translatable_hash(payload: dict[str, Any]) -> str:
    """Stable hash of a translatable payload — the staleness signal.

    Canonical JSON (sorted keys, no whitespace drift) so the same content always
    hashes the same regardless of dict ordering; see the repo's
    etag-stable-hash-all-response-fields lesson.
    """
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def source_hash(row: Any) -> str:
    """Hash of a motif's CURRENT translatable payload."""
    return translatable_hash(extract_translatable(row))


# ── the on-disk translation-file shape ─────────────────────────────────────
# A translation file is `{code: entry}`, and an entry keys its role/beat text BY
# KEY rather than by position:
#
#   {"romance.forced_proximity": {
#      "name": "…", "summary": "…", "emotion_target": "…",
#      "roles":  {"lead":    {"label": "…", "constraints": ["…"]}},
#      "beats":  {"trapped": {"label": "…", "intent": "…"}},
#      "preconditions": ["…"], "effects": ["…"], "examples": ["…"]}}
#
# Keying by `key` (not index) is what makes a translation robust: a translator
# reordering beats, or a source pack gaining one, cannot silently shift wording onto
# the wrong beat. It also makes an unknown key a loud validation error instead of a
# quiet mis-merge. The bare-string lists have no keys to drift onto, so they stay
# positional — and merge tolerantly (a short list just falls back per element).


class TranslationFileError(ValueError):
    """A translation file that would mis-merge — always loud, never tolerated."""


def build_translation_entry(payload: dict[str, Any]) -> dict[str, Any]:
    """Translatable payload → the on-disk entry shape (used by the converter/tool)."""
    entry: dict[str, Any] = {}
    for field in TRANSLATABLE_SCALARS:
        if payload.get(field):
            entry[field] = payload[field]
    for field, spec in TRANSLATABLE_LISTS.items():
        elems = payload.get(field) or []
        if spec["key"]:
            keyed = {}
            for e in elems:
                k = e.get(spec["key"])
                if k is None:
                    continue
                leaves = {lf: e[lf] for lf in spec["fields"] if e.get(lf)}
                if leaves:
                    keyed[k] = leaves
            if keyed:
                entry[field] = keyed
        else:
            leaf = spec["fields"][0]
            texts = [e.get(leaf, "") for e in elems]
            if any(texts):
                entry[field] = texts
    return entry


def parse_translation_entry(
    entry: dict[str, Any], source_payload: dict[str, Any], *, where: str = ""
) -> dict[str, Any]:
    """On-disk entry → the `motif_translation` column payload, validated.

    `source_payload` is the motif's own translatable payload — it defines which
    role/beat keys legitimately exist. A key the source does not have is a
    TranslationFileError, never a silent drop: a drifted key is precisely how a
    translation stops applying while the file on disk still looks complete.
    """
    if not isinstance(entry, dict):
        raise TranslationFileError(f"{where}: entry must be an object, got {type(entry).__name__}")

    out: dict[str, Any] = {}
    for field in TRANSLATABLE_SCALARS:
        val = entry.get(field)
        out[field] = val if isinstance(val, str) else ""

    for field, spec in TRANSLATABLE_LISTS.items():
        key_field, leaves = spec["key"], spec["fields"]
        src_elems = source_payload.get(field) or []
        given = entry.get(field)
        if key_field:
            given = given or {}
            if not isinstance(given, dict):
                raise TranslationFileError(
                    f"{where}.{field}: must be an object keyed by {key_field}, "
                    f"got {type(given).__name__}"
                )
            valid = {e.get(key_field) for e in src_elems}
            unknown = sorted(str(k) for k in given if k not in valid)
            if unknown:
                raise TranslationFileError(
                    f"{where}.{field}: unknown {key_field}(s) {unknown} — the source motif has "
                    f"{sorted(str(v) for v in valid)}. A drifted key would silently fail to merge."
                )
            out[field] = [
                {key_field: k, **{lf: v[lf] for lf in leaves if isinstance(v, dict) and v.get(lf)}}
                for k, v in given.items()
            ]
        else:
            leaf = leaves[0]
            given = given or []
            if not isinstance(given, list):
                raise TranslationFileError(
                    f"{where}.{field}: must be an array of strings, got {type(given).__name__}"
                )
            if len(given) > len(src_elems):
                raise TranslationFileError(
                    f"{where}.{field}: has {len(given)} entries but the source motif has "
                    f"{len(src_elems)} — a longer list cannot be positionally matched."
                )
            out[field] = [{leaf: t} for t in given if isinstance(t, str)]
    return out


# ── resolution ─────────────────────────────────────────────────────────────
def _merge_list(field: str, src: list[dict], tr: list[dict]) -> list[dict]:
    """Overlay a translated list onto the source list, per leaf.

    Structure always comes from `src`. An element the translation does not cover
    (missing key, short list, absent leaf) keeps its source wording — never blank.
    """
    spec = TRANSLATABLE_LISTS[field]
    key_field, leaves = spec["key"], spec["fields"]
    if key_field:
        by_key = {e.get(key_field): e for e in tr if e.get(key_field) is not None}
        pick = lambda i, e: by_key.get(e.get(key_field), {})  # noqa: E731
    else:
        pick = lambda i, e: tr[i] if i < len(tr) else {}      # noqa: E731

    merged = []
    for i, elem in enumerate(src):
        out = dict(elem)
        overlay = pick(i, elem)
        for leaf in leaves:
            val = overlay.get(leaf)
            if val not in (None, "", []):
                out[leaf] = val
        merged.append(out)
    return merged


def resolve_text(
    source: Any,
    translation: Any | None,
    want_language: str | None,
    *,
    current_hash: str | None = None,
) -> dict[str, Any]:
    """Resolve a motif's display/prompt text into `want_language`.

    Returns the resolved translatable fields plus three metadata keys:
      `text_language` — the language the returned text is actually in
      `text_fallback` — True when the caller asked for a language we do not have
      `text_stale`    — True when a translation exists but was made from older source

    Never raises, never blanks. Asking for the original language, or for a
    language with no translation, both return the source text — the difference
    being that only the latter sets `text_fallback`.
    """
    original = getattr(source, "original_language", None)
    if isinstance(source, dict):
        original = source.get("original_language", original)
    original = original or "en"

    sget = source.get if isinstance(source, dict) else (
        lambda k, d=None: getattr(source, k, d))
    # The merge target is the source's FULL elements, not its extracted payload. Merging
    # onto the extracted one silently dropped every structure field a translated list
    # carried — `beats[].tension_target` and `beats[].order` vanished from the resolved
    # motif, in the fallback path too, so a book that asked for ANY language lost its beat
    # pacing. Caught by a test that asserted structure survives translation.
    full: dict[str, Any] = {f: sget(f) for f in TRANSLATABLE_SCALARS}
    for field in TRANSLATABLE_LISTS:
        full[field] = [dict(e) for e in _as_list(sget(field))]

    if not want_language or want_language == original or translation is None:
        return {
            **full,
            "text_language": original,
            "text_fallback": bool(want_language) and want_language != original,
            "text_stale": False,
        }

    tget = translation.get if isinstance(translation, dict) else (
        lambda k, d=None: getattr(translation, k, d))
    tr_payload = extract_translatable(translation)

    resolved: dict[str, Any] = {}
    for field in TRANSLATABLE_SCALARS:
        val = tr_payload.get(field)
        resolved[field] = val if val else full.get(field)
    for field in TRANSLATABLE_LISTS:
        resolved[field] = _merge_list(field, full[field], tr_payload.get(field) or [])

    stored_hash = tget("source_content_hash") or ""
    live_hash = (
        current_hash if current_hash is not None
        else translatable_hash(extract_translatable(source))
    )

    return {
        **resolved,
        "text_language": tget("language_code") or want_language,
        "text_fallback": False,
        # A stale translation is still served — wrong-vintage wording in the right
        # language beats correct wording in a language the reader cannot read — but
        # it is reported so a re-translate can be scheduled and the FE can badge it.
        "text_stale": bool(stored_hash) and stored_hash != live_hash,
    }
