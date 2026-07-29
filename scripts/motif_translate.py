#!/usr/bin/env python3
"""motif_translate.py — translate the platform motif seed packs into the supported
locales, via a LOCAL model (LM Studio / OpenAI-compatible), with verify + self-heal.

Dev-time authoring tool. Its output is committed static seed content, so — exactly
like `i18n_translate.py`, whose machinery this REUSES — it does not go through
provider-registry (that invariant governs *service runtime* LLM calls).

WHY THIS REUSES RATHER THAN CLONES
  `i18n_translate.py` already solved the hard part for the FE locale files: chunk by
  key count (the real drop-avoidance knob), verify key-set identity + placeholder
  parity + target script, self-heal by naming the exact defects, isolate-retry a key
  the model silently echoed back in English, gap-fill on resume, and NEVER drop a key
  silently. All of that is corpus-independent. The only genuinely motif-specific
  parts are the source, the domain prompt, and the structural gate below — so the
  system prompt became a parameter there and everything else is imported.

WHAT MAKES THE MOTIF CORPUS DIFFERENT
  · KEY INVARIANCE IS LOAD-BEARING, NOT COSMETIC. A translation merges onto its
    source by `beats[].key` / `roles[].key`. A drifted key does not error at runtime —
    it silently fails to merge, and the file on disk still looks complete. The flat
    keys here ARE those keys (`beats.trapped.label`), so `verify_chunk`'s key-set
    identity check is the invariance check; on top of it, every written file is
    re-parsed through `parse_translation_entry` against the real source before this
    script reports success.
  · STRUCTURE IS NOT TRANSLATABLE and never reaches the model: `code`, `kind`,
    `category`, `genre_tags`, `tension_target`, `order`, the greimas `actant`.
    `app.motif_i18n.extract_translatable` is the single definition of that split, so
    this tool cannot drift from what the seeder and the read path believe.
  · A MOTIF IS THE UNIT OF CONTEXT. Beat labels are only translatable well if the
    model knows what motif they belong to, so each motif's English name/summary/kind
    is injected into the system prompt for its own chunks.
  · SOME LANGUAGES ARE HAND-WRITTEN. `vi` is literary Vietnamese a human wrote. This
    script REFUSES to touch an authored language without --force-authored, and the
    seeder's upsert refuses to let machine output overwrite an authored row. Two
    independent guards, because losing it would be irreversible.

Usage:
  python scripts/motif_translate.py --langs ja --packs mystery      # proof run
  python scripts/motif_translate.py --langs ja,ko,zh-CN             # a few locales
  python scripts/motif_translate.py                                 # every locale
  python scripts/motif_translate.py --check ja                      # verify only
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "services" / "composition-service"))

from i18n_translate import (  # noqa: E402  (path set above)
    TARGETS,
    is_untranslated_echo,
    chunk_items,
    flatten,
    isolate_retry_soft,
    translate_chunk,
    unflatten,
    verify_chunk,
)

from app.motif_i18n import (  # noqa: E402
    TranslationFileError,
    build_translation_entry,
    extract_translatable,
    parse_translation_entry,
    source_hash,
)

PACK_DIR = REPO / "services" / "composition-service" / "app" / "db" / "seed_motif_packs"
TRANSLATION_DIR = PACK_DIR / "translations"
PACKS = (
    "cultivation", "revenge", "intrigue", "hooks", "emotion_arcs",
    "romance", "mystery", "rebirth", "wuxia", "survival",
)
# Human-written translations. Machine output must never land on top of these.
AUTHORED_LANGUAGES = frozenset({"vi"})

# A motif is ~15-25 short strings and they are COHESIVE (a beat label reads against
# the motif's summary), unlike the FE's unrelated UI keys — so the reliability cap can
# sit a little higher here than i18n_translate's 12. The self-heal loop, which names
# each missing key back to the model, is what actually makes this safe.
MAX_KEYS = 16
CHUNK_CHARS = 3000

SYSTEM_BASE = (
    "You are a literary translator localizing a NARRATIVE CRAFT library for a "
    "novel-writing tool. Each entry describes a reusable story pattern — its name, "
    "what it does, and the beats it runs through. Translate ONLY the JSON string "
    "values into the target language.\n"
    # Without this the model renders craft vocabulary as film/screenwriting jargon,
    # which reads wrong inside a prose-fiction tool and drifts between motifs.
    "DOMAIN TERMS — these are PROSE-FICTION craft terms, not screenwriting ones: a "
    "'beat' is a unit of dramatic movement inside a scene (NOT a musical beat and NOT "
    "a screenplay slug); a 'motif' is a recurring narrative pattern; an 'arc' is a "
    "character or plot trajectory; a 'reveal' is when withheld information reaches a "
    "character or the reader; a 'reversal' is when a situation inverts against the "
    "party who seemed to hold it. Keep the register LITERARY and CONCRETE — these "
    "strings are read by authors and fed to a writing model, so vague abstractions "
    "are worse than plain words.\n"
    "Rules: keep every JSON key BYTE-IDENTICAL (the keys are machine identifiers that "
    "join a translation to its source — a changed key silently breaks it); preserve "
    "every {{placeholder}} and <tag> exactly; produce idiomatic, natural phrasing, not "
    "a literal gloss. NEVER put a raw double-quote (\") inside a value — use the "
    "target language's own marks (« », „ “, 「 」, ‘ ’). Output ONLY a single JSON "
    "object, no commentary, no code fences."
)


def _motif_system(motif: dict) -> str:
    """The domain prompt PLUS this motif's own English context.

    A beat label like "The account is given" is untranslatable in isolation — the
    model needs to know it belongs to a mystery motif about a witness whose lie is
    not about the crime. This is why chunks are built per motif rather than per pack.
    """
    return (
        f"{SYSTEM_BASE}\n\n"
        f"CONTEXT — the strings below all belong to ONE motif:\n"
        f"  kind: {motif.get('kind', 'sequence')}\n"
        f"  name: {motif.get('name', '')}\n"
        f"  summary: {motif.get('summary', '')}\n"
        f"Translate its parts so they read as one coherent entry."
    )


def load_source() -> dict[str, list[dict]]:
    """{pack: [motif, …]} straight from the seed packs (the English source)."""
    out: dict[str, list[dict]] = {}
    for pack in PACKS:
        out[pack] = json.loads((PACK_DIR / f"{pack}.json").read_text(encoding="utf-8"))
    return out


def entry_of(motif: dict) -> dict:
    """The motif's translatable leaves in on-disk entry shape (structure excluded)."""
    return build_translation_entry(extract_translatable(motif))


def _existing(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (ValueError, OSError):
        return {}


def plan_pack(lang: str, pack: str, motifs: list[dict], *, force: bool,
              retry_keys: frozenset) -> dict:
    """Chunk what still needs translating. GAP-FILL: an existing key that is present,
    non-empty and not listed in _FAILED is CARRIED, so a re-run fills new motifs and
    retries prior failures without clobbering anything already good — including a
    hand-corrected string."""
    out_path = TRANSLATION_DIR / lang / f"{pack}.json"
    have = {} if force else _existing(out_path)

    chunks, systems, carry, source_flat = [], [], {}, {}
    for motif in motifs:
        code = motif["code"]
        src_flat = {f"{code}|{k}": v for k, v in flatten(entry_of(motif)).items()
                    if isinstance(v, str) and v}
        source_flat.update(src_flat)
        existing_flat = {f"{code}|{k}": v for k, v in flatten(have.get(code, {})).items()}
        todo = {}
        for k, v in src_flat.items():
            ev = existing_flat.get(k)
            if k not in retry_keys and isinstance(ev, str) and ev:
                carry[k] = ev
            else:
                todo[k] = v
        for chunk in chunk_items(todo, CHUNK_CHARS, MAX_KEYS):
            chunks.append(chunk)
            systems.append(_motif_system(motif))

    return {
        "lang": lang, "pack": pack, "out_path": out_path, "chunks": chunks,
        "systems": systems, "carry": carry, "source_flat": source_flat,
        "results": {}, "soft": {}, "n_new": sum(len(c) for c in chunks),
        "n_keys": len(source_flat),
    }


def assemble(plan: dict, motifs: list[dict]) -> dict:
    """Merge carried + freshly-translated keys back into {code: entry} and WRITE.

    A key that failed every heal round is written as its ENGLISH source, never blank —
    a blank name renders as an empty motif card, which looks like data loss rather
    than a missing translation.
    """
    flat = dict(plan["carry"])
    for i, chunk in enumerate(plan["chunks"]):
        got = plan["results"].get(i, {})
        flat.update({k: got.get(k, chunk[k]) for k in chunk})

    by_code: dict[str, dict] = {}
    for key, val in flat.items():
        code, _, leaf = key.partition("|")
        by_code.setdefault(code, {})[leaf] = val
    doc = {code: unflatten(leaves) for code, leaves in sorted(by_code.items())}

    # THE STRUCTURAL GATE — re-parse every entry against its real source before this
    # is allowed to count as output. verify_chunk already caught key drift per chunk;
    # this catches anything the assembly itself could have broken (a mis-split dotted
    # key, an unflatten that produced a list where an object was expected).
    src_by_code = {m["code"]: extract_translatable(m) for m in motifs}
    for code, entry in doc.items():
        parse_translation_entry(entry, src_by_code[code], where=f"{plan['lang']}/{plan['pack']}:{code}")

    plan["out_path"].parent.mkdir(parents=True, exist_ok=True)
    plan["out_path"].write_text(
        json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    write_source_hashes(plan["lang"], plan["pack"], motifs)

    failed = {k: v for k, v in plan["soft"].items() if str(v).startswith("FAILED")}
    return {"pack": plan["pack"], "codes": len(doc), "keys": plan["n_keys"],
            "failed": len(failed), "soft": len(plan["soft"]) - len(failed),
            "failed_keys": sorted(failed)}


def _flat_entry(entry, prefix: str = "") -> dict[str, str]:
    """String leaves of an on-disk entry, dotted — the same shape plan_pack chunks."""
    out: dict[str, str] = {}
    if isinstance(entry, dict):
        for k, v in entry.items():
            out.update(_flat_entry(v, f"{prefix}.{k}" if prefix else k))
    elif isinstance(entry, list):
        for i, v in enumerate(entry):
            out.update(_flat_entry(v, f"{prefix}[{i}]"))
    elif isinstance(entry, str):
        out[prefix] = entry
    return out


def write_source_hashes(lang: str, pack: str, motifs: list[dict]) -> None:
    """Record WHICH source text each translation was made from, in `_source_hash.json`.

    Without this the staleness signal is decorative for platform seeds: the seeder
    stamps `hash(current source)` on every translation it loads, so editing an English
    summary and NOT re-translating leaves the old wording flagged perfectly fresh — the
    exact "the JSON in git says one thing, what ships says another" shape this repo
    keeps re-learning. Writing it HERE is honest, because here is the one moment we
    know what was actually translated.

    `_`-prefixed, so the seeder's translation glob skips it as a report file.
    """
    path = TRANSLATION_DIR / lang / "_source_hash.json"
    have = _existing(path)
    have.update({m["code"]: source_hash(m) for m in motifs})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(have, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")




# ── audit ──────────────────────────────────────────────────────────────────
# Everything the tool can know about the committed state, in one pass, with no
# model calls. This is the artifact the run itself is judged by — before it
# existed the only record was a scratch console log, `_FAILED.json` (which stays
# empty when nothing fails, so its absence proved nothing), and a per-locale
# `--check` nobody aggregated.
#
# Four independent failure modes, because each is invisible to the others:
#   MISSING   a motif the locale never got            (coverage)
#   BROKEN    an entry that would mis-merge           (structural — the loud one)
#   STALE     translated from English that has moved  (recorded hash vs live)
#   ECHOED    present, non-empty, and still English   (the silent one)
# The completeness-check shape most projects have only ever catches MISSING.

def audit_locale(lang: str, source: dict[str, list[dict]]) -> dict:
    recorded = _existing(TRANSLATION_DIR / lang / "_source_hash.json")
    out = {"lang": lang, "packs": 0, "motifs": 0, "keys": 0,
           "missing": [], "broken": [], "stale": [], "echoed": [],
           "authored": lang in AUTHORED_LANGUAGES}
    for pack, motifs in source.items():
        path = TRANSLATION_DIR / lang / f"{pack}.json"
        doc = _existing(path)
        if not doc:
            out["missing"].extend(m["code"] for m in motifs)
            continue
        out["packs"] += 1
        src_by_code = {m["code"]: m for m in motifs}
        for code, motif in src_by_code.items():
            entry = doc.get(code)
            if not entry:
                out["missing"].append(code)
                continue
            out["motifs"] += 1
            src_payload = extract_translatable(motif)
            try:
                parse_translation_entry(entry, src_payload, where=f"{lang}/{pack}:{code}")
            except TranslationFileError as e:
                out["broken"].append({"code": code, "pack": pack, "why": str(e)[:160]})
                continue
            live = source_hash(motif)
            if recorded.get(code) not in (None, live):
                out["stale"].append({"code": code, "pack": pack})
            src_flat = _flat_entry(entry_of(motif))
            for leaf, val in _flat_entry(entry).items():
                out["keys"] += 1
                if leaf in src_flat and is_untranslated_echo(src_flat[leaf], val):
                    out["echoed"].append({"code": code, "pack": pack, "leaf": leaf,
                                          "text": val[:70]})
        for code in set(doc) - set(src_by_code):
            out["broken"].append({"code": code, "pack": pack,
                                  "why": "code is not a seeded motif (renamed upstream?)"})
    return out


def audit_all(source: dict[str, list[dict]], langs: list[str]) -> list[dict]:
    return [audit_locale(lang, source) for lang in langs]


def _fmt_report(reports: list[dict], source: dict[str, list[dict]]) -> str:
    total_motifs = sum(len(m) for m in source.values())
    lines = [
        "# Motif translation audit",
        "",
        f"Source: {total_motifs} motifs across {len(source)} packs, authored in English.",
        "",
        "| locale | source | motifs | keys | missing | broken | stale | echoed |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in reports:
        lines.append(
            f"| {r['lang']} | {'authored' if r['authored'] else 'machine'} | "
            f"{r['motifs']}/{total_motifs} | {r['keys']} | {len(r['missing'])} | "
            f"{len(r['broken'])} | {len(r['stale'])} | {len(r['echoed'])} |")
    clean = [r for r in reports if not any(
        (r["missing"], r["broken"], r["stale"], r["echoed"]))]
    lines += ["", f"**{len(clean)}/{len(reports)} locales clean.**", ""]
    for r in reports:
        problems = []
        for kind in ("broken", "stale", "echoed"):
            for item in r[kind][:6]:
                where = f"{item['pack']}:{item['code']}"
                extra = item.get("leaf") or item.get("why") or ""
                problems.append(f"  - `{kind.upper()}` {where} {extra}"[:150])
        if r["missing"]:
            problems.append(f"  - `MISSING` {len(r['missing'])}: {r['missing'][:5]}")
        if problems:
            lines.append(f"### {r['lang']}")
            lines += problems
            lines.append("")
    return "\n".join(lines) + "\n"


def fixable(report: dict) -> dict[str, set[str]]:
    """Which motif codes this locale should re-translate. Everything except BROKEN —
    a structural break means the file disagrees with the source about what a motif IS,
    and re-translating would just re-break it under a human's nose."""
    codes = set(report["missing"])
    codes |= {i["code"] for i in report["stale"]}
    codes |= {i["code"] for i in report["echoed"]}
    return codes


def auto_fix(report: dict, source: dict[str, list[dict]]) -> int:
    """Drop the offending entries so the next round's gap-fill re-translates exactly
    them. An ECHOED leaf is dropped leaf-wise (its siblings are fine); a STALE motif is
    dropped whole, because the English it was made from has moved and every leaf of it
    is suspect."""
    lang = report["lang"]
    if report["authored"]:
        return 0                      # never machine-touch a human-written locale
    stale_codes = {i["code"] for i in report["stale"]}
    dropped = 0
    by_pack: dict[str, list] = {}
    for item in report["echoed"]:
        by_pack.setdefault(item["pack"], []).append(item)
    for pack in set(by_pack) | {i["pack"] for i in report["stale"]}:
        path = TRANSLATION_DIR / lang / f"{pack}.json"
        doc = _existing(path)
        if not doc:
            continue
        for code in stale_codes:
            if doc.pop(code, None) is not None:
                dropped += 1
        for item in by_pack.get(pack, []):
            if item["code"] in stale_codes:
                continue              # already dropped whole
            entry = doc.get(item["code"])
            if entry is None:
                continue
            parts = [p for p in item["leaf"].replace("[", ".").replace("]", "").split(".") if p]
            node = entry
            for part in parts[:-1]:
                node = node[int(part)] if part.isdigit() else node.get(part)
                if node is None:
                    break
            if node is None:
                continue
            last = parts[-1]
            if isinstance(node, list) and last.isdigit():
                node[int(last)] = ""
            elif isinstance(node, dict):
                node.pop(last, None)
            dropped += 1
        path.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
    return dropped


# ── one translation pass ───────────────────────────────────────────────────
def run_once(langs: list[str], source: dict[str, list[dict]], args) -> int:
    plans = []
    for lang in langs:
        failed_map: dict = {}
        fpath = TRANSLATION_DIR / lang / "_FAILED.json"
        if fpath.exists():
            try:
                failed_map = json.loads(fpath.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                pass
        for pack, motifs in source.items():
            plans.append(plan_pack(lang, pack, motifs, force=args.force,
                                   retry_keys=frozenset(failed_map.get(pack, []))))

    work = [p for p in plans if p["chunks"]]
    tasks = [(p, i) for p in work for i in range(len(p["chunks"]))]
    if not tasks:
        for p in plans:
            assemble(p, source[p["pack"]])      # re-validate + refresh the sidecar
        return 0

    print(f"  planned: {len(work)} pack-language pair(s) / {len(tasks)} chunks")
    remaining = {id(p): len(p["chunks"]) for p in work}
    by_lang: dict[str, list[dict]] = {}
    done = grand_failed = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futs = {
            ex.submit(translate_chunk, p["chunks"][i], TARGETS[p["lang"]][0], p["lang"],
                      TARGETS[p["lang"]][1], args.max_heal, p["systems"][i]): (p, i)
            for (p, i) in tasks
        }
        for fut in as_completed(futs):
            p, i = futs[fut]
            try:
                out, soft = fut.result()
            except Exception as e:  # noqa: BLE001 — a dead chunk falls back to en, never aborts
                out, soft = {}, {k: f"FAILED:call {type(e).__name__}" for k in p["chunks"][i]}
            p["results"][i] = out
            p["soft"].update(soft)
            done += 1
            remaining[id(p)] -= 1
            if remaining[id(p)] == 0:
                isolate_retry_soft(p, TARGETS[p["lang"]][0], p["lang"],
                                   TARGETS[p["lang"]][1], p["systems"][0])
                try:
                    r = assemble(p, source[p["pack"]])
                except TranslationFileError as e:
                    print(f"    x {p['lang']:<6} {p['pack']:<14} STRUCTURAL: {e}")
                    grand_failed += 1
                    continue
                by_lang.setdefault(p["lang"], []).append(r)
                grand_failed += r["failed"]
                flag = f" ~{r['soft']}" if r["soft"] else ""
                fail = f" x{r['failed']}" if r["failed"] else ""
                print(f"    ok {p['lang']:<6} {p['pack']:<14} {r['codes']} motifs{flag}{fail}"
                      f"  [{done}/{len(tasks)}, {time.time()-t0:.0f}s]")

    for lang, results in by_lang.items():
        report = {r["pack"]: r["failed_keys"] for r in results if r["failed"]}
        fpath = TRANSLATION_DIR / lang / "_FAILED.json"
        if report:
            fpath.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        elif fpath.exists():
            fpath.unlink()
    return grand_failed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--langs", help="comma list of target codes (default: all non-authored)")
    ap.add_argument("--packs", help="comma list of pack stems (default: all)")
    ap.add_argument("--max-heal", type=int, default=3)
    ap.add_argument("--max-keys", type=int, default=MAX_KEYS)
    ap.add_argument("--chunk-chars", type=int, default=CHUNK_CHARS)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--rounds", type=int, default=3,
                    help="self-healing rounds: translate, audit, re-translate whatever the "
                         "audit flags, repeat until clean (default 3). --rounds 1 disables it.")
    ap.add_argument("--force", action="store_true", help="re-translate even where output exists")
    ap.add_argument("--force-authored", action="store_true",
                    help="allow writing a HUMAN-AUTHORED language (vi). You almost certainly "
                         "do not want this — it overwrites hand-written literary prose.")
    ap.add_argument("--audit", action="store_true",
                    help="report the committed state and exit. No model calls.")
    args = ap.parse_args()

    source = load_source()
    if args.packs:
        wanted = set(args.packs.split(","))
        source = {p: m for p, m in source.items() if p in wanted}

    all_langs = [c for c in TARGETS if (TRANSLATION_DIR / c).is_dir()] or list(TARGETS)
    if args.audit:
        reports = audit_all(source, sorted(all_langs))
        text = _fmt_report(reports, source)
        (TRANSLATION_DIR / "AUDIT.md").write_text(text, encoding="utf-8")
        print(text)
        print(f"written: {TRANSLATION_DIR / 'AUDIT.md'}")
        return 1 if any(r["broken"] for r in reports) else 0

    langs = args.langs.split(",") if args.langs else [
        c for c in TARGETS if c not in AUTHORED_LANGUAGES]
    for code in list(langs):
        if code not in TARGETS:
            print(f"!! unknown lang {code}, skipping")
            langs.remove(code)
        elif code in AUTHORED_LANGUAGES and not args.force_authored:
            print(f"!! {code} is a HUMAN-AUTHORED translation — refusing to overwrite it. "
                  f"Pass --force-authored only if you really mean to replace hand-written "
                  f"prose with model output.")
            langs.remove(code)
    if not langs:
        return 1

    t0 = time.time()
    for rnd in range(1, max(1, args.rounds) + 1):
        print(f"── round {rnd}/{args.rounds}")
        run_once(langs, source, args)
        reports = audit_all(source, langs)
        outstanding = {r["lang"]: fixable(r) for r in reports}
        n = sum(len(v) for v in outstanding.values())
        broken = sum(len(r["broken"]) for r in reports)
        print(f"   audit: {n} motif(s) still flagged across {sum(1 for v in outstanding.values() if v)} "
              f"locale(s); {broken} structural")
        if n == 0:
            break
        if rnd == max(1, args.rounds):
            print("   rounds exhausted — the remainder is in AUDIT.md for review "
                  "(a true cognate re-translates to itself and will never clear)")
            break
        dropped = sum(auto_fix(r, source) for r in reports)
        print(f"   auto-resolve: dropped {dropped} entry/leaf for re-translation")

    reports = audit_all(source, sorted(all_langs))
    text = _fmt_report(reports, source)
    (TRANSLATION_DIR / "AUDIT.md").write_text(text, encoding="utf-8")
    print(f"\nDONE in {time.time()-t0:.0f}s. audit written to {TRANSLATION_DIR / 'AUDIT.md'}")
    print(_fmt_report(reports, source).split("\n\n")[2])
    return 0


if __name__ == "__main__":
    sys.exit(main())
