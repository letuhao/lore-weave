#!/usr/bin/env python3
"""i18n_translate.py — generate locale JSON from the `en` source via a LOCAL
model (LM Studio / OpenAI-compatible), with a verify + self-heal loop.

Dev-time tool. Its output is committed static content, so it does NOT go
through provider-registry (that invariant governs *service runtime* LLM calls,
not a local authoring script). Default backend: LM Studio on :1234 with
google/gemma-4-26b-a4b-qat.

Design (matches the repo's verify-by-effect / no-silent-drop culture):
  1. Flatten each en namespace to dotted-key string leaves (nested JSON +
     lists supported; non-string leaves pass through untouched).
  2. Chunk by character budget — NOT for capacity (model is at ~224K ctx) but
     for attention quality: long inputs degrade ("lost in the middle") and
     over-stuffed batches make the model drop/merge keys. Tunable --chunk-chars.
  3. Translate each chunk → the target endonym.
  4. VERIFY: valid JSON · key-set identical · every {{placeholder}}/$t()/<tag>
     preserved · non-empty · (soft) target-script present (catches "answered
     in English").
  5. SELF-HEAL: on a HARD failure, re-prompt with the *specific* defects, up
     to --max-heal rounds.
  6. NO SILENT DROP: keys still failing after heal are recorded in a
     `<lang>/_FAILED.json` report and left as the English source, never blank.
  7. RESUMABLE: a namespace whose output already exists and re-verifies is
     skipped unless --force.

Usage:
  python scripts/i18n_translate.py --langs ru,ar --ns common,notifications   # proof run
  python scripts/i18n_translate.py                                           # all langs × all ns
  python scripts/i18n_translate.py --check ru/common.json                    # verify only
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# ── config ────────────────────────────────────────────────────────────────
REPO = Path(__file__).resolve().parents[1]
LOCALES_DIR = REPO / "frontend" / "src" / "i18n" / "locales"
SRC_LANG = "en"
ENDPOINT = "http://localhost:1234/v1/chat/completions"
MODEL = "google/gemma-4-26b-a4b-qat"
# Chunk limits — NOT a context-capacity cap (model is at ~224K ctx) but a
# RELIABILITY cap: given too many keys in one call the model truncates / drops
# the tail (an 80-key chunk lost most; a 10-key chunk is flawless). We cap BY
# KEY COUNT (the real failure driver) and by chars, whichever hits first.
CHUNK_CHARS = 2500
MAX_KEYS_PER_CHUNK = 12
REQUEST_TIMEOUT = 420       # the 26B at high ctx is slow; be patient

# code → (endonym, expected-script regex | None for Latin-script languages).
# MUST stay in parity with frontend/src/lib/languages.ts LANGUAGE_REGISTRY.
TARGETS: dict[str, tuple[str, str | None]] = {
    "vi":    ("Tiếng Việt",         None),
    "ja":    ("日本語",              r"[぀-ヿ一-鿿]"),
    "ko":    ("한국어",              r"[가-힯]"),
    "zh-CN": ("简体中文",            r"[一-鿿]"),
    "zh-TW": ("繁體中文",            r"[一-鿿]"),
    "es":    ("Español",            None),
    "pt-BR": ("Português (Brasil)", None),
    "fr":    ("Français",           None),
    "de":    ("Deutsch",            None),
    "ru":    ("Русский",            r"[Ѐ-ӿ]"),
    "id":    ("Bahasa Indonesia",   None),
    "ms":    ("Bahasa Melayu",      None),
    "tr":    ("Türkçe",             None),
    "ar":    ("العربية",            r"[؀-ۿ]"),
    "hi":    ("हिन्दी",              r"[ऀ-ॿ]"),
    "bn":    ("বাংলা",              r"[ঀ-৿]"),
    "th":    ("ภาษาไทย",            r"[฀-๿]"),
}

PLACEHOLDER_RE = re.compile(r"\{\{.*?\}\}|\$t\([^)]*\)|<[^>]+>")
_ASCII_LETTER_RE = re.compile(r"[A-Za-z]")


# ── flatten / unflatten (string leaves only; structure preserved) ──────────
def flatten(obj, prefix: str = "") -> dict[str, object]:
    out: dict[str, object] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(flatten(v, f"{prefix}.{k}" if prefix else k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(flatten(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = obj
    return out


def unflatten(flat: dict[str, object]) -> object:
    root: dict = {}
    for key, val in flat.items():
        parts = re.findall(r"[^.\[\]]+|\[\d+\]", key)
        cur = root
        for i, p in enumerate(parts):
            last = i == len(parts) - 1
            idx = p[1:-1] if p.startswith("[") else None
            token = int(idx) if idx is not None else p
            if last:
                _assign(cur, token, val)
            else:
                nxt = parts[i + 1]
                want_list = nxt.startswith("[")
                cur = _descend(cur, token, want_list)
    return root


def _assign(cur, token, val):
    if isinstance(token, int):
        while len(cur) <= token:
            cur.append(None)
        cur[token] = val
    else:
        cur[token] = val


def _descend(cur, token, want_list):
    child_default = [] if want_list else {}
    if isinstance(token, int):
        while len(cur) <= token:
            cur.append(None)
        if cur[token] is None:
            cur[token] = child_default
        return cur[token]
    if token not in cur or cur[token] is None:
        cur[token] = child_default
    return cur[token]


def placeholders(s: str) -> set[str]:
    return set(PLACEHOLDER_RE.findall(s)) if isinstance(s, str) else set()


# ── model call ─────────────────────────────────────────────────────────────
def call_model(system: str, user: str, *, temperature: float = 0.2) -> str:
    # Suppress thinking-mode on the local model — otherwise reasoning_tokens make
    # every call slow (and can swallow the JSON). Mirrors how the platform disables
    # it for local OpenAI-compatible servers (provider-registry adapters.go: local
    # base_url keeps chat_template_kwargs + reasoning_effort). llama.cpp/LM Studio
    # ignore whichever key the model's template doesn't use.
    body = json.dumps({
        "model": MODEL, "temperature": temperature,
        "reasoning_effort": "none",
        "chat_template_kwargs": {"enable_thinking": False, "thinking": False},
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
    }).encode("utf-8")
    last_err = None
    # Only 2 attempts: hammering a wedged LM Studio queue with retries makes it
    # worse (see the lm-studio-queue-wedge lesson). One retry covers a transient blip.
    for attempt in range(2):
        try:
            req = urllib.request.Request(ENDPOINT, data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
        except (urllib.error.URLError, TimeoutError, KeyError) as e:
            last_err = e
            time.sleep(3)
    raise RuntimeError(f"model call failed after retries: {last_err}")


def extract_json(text: str) -> dict:
    """Strip ```json fences / prose and parse the first {...} object.

    Tolerates the single most common LLM-JSON slip: an UNESCAPED double-quote
    inside a value (e.g. translating «the "bible"» to a value containing a raw
    `"`). Our keys are quote-free dotted identifiers, so a flat regex extraction
    (value = everything up to a `"` that is followed by `,` or `}`) recovers the
    pairs when strict json.loads chokes.
    """
    t = text.strip()
    if "```" in t:
        t = re.sub(r"^```[a-zA-Z]*\n?|```$", "", t.strip("`\n ")).strip()
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in model output")
    blob = t[start:end + 1]
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        pairs = re.findall(r'"([^"\n]+)"\s*:\s*"(.*?)"(?=\s*[,}])', blob, re.DOTALL)
        if pairs:
            return {k: v for k, v in pairs}
        raise


# ── verify ──────────────────────────────────────────────────────────────────
def verify_chunk(src: dict[str, str], out: dict, script_re: str | None):
    """Return (hard_failures, soft_failures) as {key: reason}."""
    hard: dict[str, str] = {}
    soft: dict[str, str] = {}
    for key, src_val in src.items():
        if key not in out:
            hard[key] = "missing key"
            continue
        val = out[key]
        if not isinstance(val, str) or val == "":
            hard[key] = "empty/non-string"
            continue
        if placeholders(src_val) != placeholders(val):
            hard[key] = (f"placeholder drift: src={sorted(placeholders(src_val))} "
                         f"out={sorted(placeholders(val))}")
            continue
        # soft: value looks untranslated (has ASCII words but no target-script char)
        if script_re and _ASCII_LETTER_RE.search(val) and not re.search(script_re, val):
            stripped = PLACEHOLDER_RE.sub("", val)
            if len(_ASCII_LETTER_RE.findall(stripped)) > 3:
                soft[key] = "possibly untranslated (no target script)"
    for key in out:
        if key not in src:
            hard[key] = "extra key not in source"
    return hard, soft


# ── translate one chunk with self-heal ─────────────────────────────────────
SYSTEM = (
    "You are a professional UI localization engine for a novel-writing/translation app. "
    "Translate ONLY the JSON string values from English into the target language. "
    # DOMAIN GLOSSARY (this app's book-structure terms — translate the CONCEPT, never a near-synonym).
    # Without this, machine translation renders a manuscript 'Part' as 'chapter'/'act' in CJK (章节 / 幕),
    # breaking the Part-vs-Arc-vs-Chapter distinction the whole rail depends on.
    "DOMAIN TERMS — use the target language's word for these EXACT book-structure concepts: a 'Part' / "
    "'Parts' is a top-level book DIVISION that groups chapters (zh 部 / ja パート / ko 부) — NEVER render it "
    "as a chapter (章 / 章节 / チャプター) or a dramatic 'act' (幕); an 'Arc' is a narrative planning unit "
    "distinct from a Part; a 'Chapter' is 章 / 章 / 장; a 'Scene' is 场景 / シーン / 장면. "
    "Rules: keep every JSON key byte-identical; preserve every {{placeholder}}, $t(...) "
    "reference, and <html/tag> EXACTLY as-is; keep brand/proper names and short technical "
    "tokens (API, URL, ID, PDF) untranslated; produce idiomatic, natural phrasing. "
    "NEVER put a raw double-quote (\") inside a value — if the text needs quotation marks, "
    "use the target language's native marks (« », „ “, 「 」, ‘ ’); the output MUST be "
    "strictly valid JSON. Output ONLY a single JSON object, no commentary, no code fences."
)


def translate_chunk(src: dict[str, str], endonym: str, code: str,
                    script_re: str | None, max_heal: int) -> tuple[dict, dict]:
    user = (f"Target language: {endonym} ({code})\n\n"
            f"{json.dumps(src, ensure_ascii=False, indent=0)}")
    out: dict = {}
    for attempt in range(max_heal + 1):
        try:
            # Flatten the model's output: gemma sometimes RE-NESTS a flat dotted key
            # ({"graph.counts": x} → {"graph": {"counts": x}}); flattening normalizes
            # both shapes back to dotted-flat so verify compares like-for-like.
            out = flatten(extract_json(call_model(SYSTEM, user)))
        except (ValueError, json.JSONDecodeError) as e:
            user = (f"Your previous output was not valid JSON ({e}) — most likely an "
                    f"unescaped double-quote inside a value. Do NOT use \" inside values "
                    f"(use « » or „ “ or ‘ ’). Re-emit ONLY a strictly-valid JSON object "
                    f"translating these into {endonym}:\n\n{json.dumps(src, ensure_ascii=False)}")
            continue
        hard, soft = verify_chunk(src, out, script_re)
        if not hard:
            return out, soft
        # self-heal: name the exact defects
        defects = "\n".join(f"- {k}: {r}" for k, r in list(hard.items())[:40])
        need = {k: src[k] for k in hard if k in src}
        user = (f"Your translation to {endonym} had these problems:\n{defects}\n\n"
                f"Fix them. Return the COMPLETE corrected JSON object (all keys). "
                f"Preserve placeholders/$t()/tags verbatim. Source for the affected keys:\n"
                f"{json.dumps(need, ensure_ascii=False)}\n\nFull source:\n"
                f"{json.dumps(src, ensure_ascii=False)}")
    # exhausted heal rounds — keep good keys, mark the rest FAILED (source fallback)
    hard, soft = verify_chunk(src, out, script_re)
    for k in hard:
        out[k] = src.get(k, out.get(k, ""))
    return out, {**soft, **{k: f"FAILED:{r}" for k, r in hard.items()}}


def isolate_retry_soft(p: dict, endonym: str, code: str, script_re: str | None) -> None:
    """Self-heal only fires on HARD failures (translate_chunk returns early once
    `hard` is empty) — a key the model silently echoed back in English inside a
    12-key batch surfaces merely as a SOFT "possibly untranslated" flag and is
    never retried, so it ships as an English fallback with no report entry
    forcing a future re-run to fix it. Isolating that ONE key into its own
    single-key call reliably fixes it (proven live 2026-07-06: zh-TW's
    `configure.pagesPerChunkHint` failed 3x batched, succeeded instantly alone).
    Cheap: this soft signal is rare (a handful of keys per run, not per chunk).
    Also gives a HARD-exhausted ("FAILED:...") key one more isolated shot —
    heal-exhaustion inside a crowded batch doesn't mean the model can't do it
    alone, only that it couldn't while also juggling 11 sibling keys.
    """
    if not script_re:
        return  # no target-script signal for Latin-script targets, nothing to detect
    src_by_key: dict[str, str] = {}
    for chunk in p["chunks"]:
        src_by_key.update(chunk)
    candidates = [k for k, v in p["soft"].items()
                  if k in src_by_key and (v == "possibly untranslated (no target script)"
                                          or str(v).startswith("FAILED:"))]
    for key in candidates:
        try:
            out, soft = translate_chunk({key: src_by_key[key]}, endonym, code, script_re, max_heal=1)
        except Exception:
            continue
        fixed = out.get(key)
        if not fixed or soft.get(key, "").startswith("FAILED"):
            continue
        if script_re and _ASCII_LETTER_RE.search(fixed) and not re.search(script_re, fixed):
            continue  # still untranslated even isolated — leave the soft flag as-is
        for i, chunk in enumerate(p["chunks"]):
            if key in chunk:
                p["results"].setdefault(i, {})[key] = fixed
                break
        del p["soft"][key]


def chunk_items(src_flat: dict[str, str], chunk_chars: int = CHUNK_CHARS,
                max_keys: int = MAX_KEYS_PER_CHUNK) -> list[dict[str, str]]:
    chunks, cur, size = [], {}, 0
    for k, v in src_flat.items():
        vlen = len(k) + len(str(v)) + 8
        if cur and (size + vlen > chunk_chars or len(cur) >= max_keys):
            chunks.append(cur)
            cur, size = {}, 0
        cur[k] = v
        size += vlen
    if cur:
        chunks.append(cur)
    return chunks


# ── namespace planning / assembly (chunk-level parallelism) ────────────────
# The unit of parallel work is a CHUNK, not a namespace — so a single big
# namespace still saturates all workers (the "4 workers but 1 call" fix). A
# plan is built per namespace (with resume-skip), all its chunks are submitted
# to a shared pool, and the namespace file is written the moment its chunks
# finish (incremental → resumable against a mid-run process death).
def plan_namespace(code: str, ns_path: Path, script_re: str | None, force: bool,
                   chunk_chars: int, max_keys: int, retry_keys: frozenset = frozenset()) -> dict:
    out_path = LOCALES_DIR / code / ns_path.name
    src_flat = flatten(json.loads(ns_path.read_text(encoding="utf-8")))
    str_leaves = {k: v for k, v in src_flat.items() if isinstance(v, str)}
    passthrough = {k: v for k, v in src_flat.items() if not isinstance(v, str)}

    # GAP-FILL + KEY-LEVEL RETRY: on a plain resume, KEEP every existing key that is
    # already a valid translation (present, non-empty, placeholder-faithful, and NOT
    # flagged in _FAILED) and (re)translate ONLY the keys that are missing, broken, or
    # listed in _FAILED.json. This makes the tool safe to run anytime — it fills new
    # `en` keys + retries prior failures WITHOUT clobbering existing (incl.
    # hand-authored) translations. `--force` re-translates everything.
    carry: dict[str, str] = {}
    to_translate = str_leaves
    if out_path.exists() and not force:
        try:
            existing = flatten(json.loads(out_path.read_text(encoding="utf-8")))
            for k, srcv in str_leaves.items():
                ev = existing.get(k)
                if (k not in retry_keys and isinstance(ev, str) and ev
                        and placeholders(ev) == placeholders(srcv)):
                    carry[k] = ev
            to_translate = {k: v for k, v in str_leaves.items() if k not in carry}
            if not to_translate:
                return {"status": "skip", "code": code, "ns": ns_path.name, "keys": len(str_leaves)}
        except Exception:
            carry, to_translate = {}, str_leaves  # unreadable → full re-translate

    return {"status": "work", "code": code, "ns": ns_path.name, "out_path": out_path,
            "chunks": chunk_items(to_translate, chunk_chars, max_keys),
            "passthrough": passthrough, "carry": carry, "keys": len(str_leaves),
            "n_new": len(to_translate), "results": {}, "soft": {}}


def assemble_and_write(plan: dict) -> dict:
    # Start from non-string passthrough + the CARRIED existing translations
    # (gap-fill preserves them), then overlay the freshly-translated chunks.
    translated: dict[str, object] = dict(plan["passthrough"])
    translated.update(plan.get("carry", {}))
    for i, chunk in enumerate(plan["chunks"]):
        out = plan["results"].get(i, {})
        translated.update({k: out.get(k, chunk[k]) for k in chunk})
    plan["out_path"].parent.mkdir(parents=True, exist_ok=True)
    plan["out_path"].write_text(
        json.dumps(unflatten(translated), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    failed = {k: v for k, v in plan["soft"].items() if str(v).startswith("FAILED")}
    return {"ns": plan["ns"], "keys": plan["keys"], "failed": len(failed),
            "soft": len(plan["soft"]) - len(failed), "failed_keys": list(failed)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--langs", help="comma list of target codes (default: all)")
    ap.add_argument("--ns", help="comma list of namespace stems (default: all)")
    ap.add_argument("--max-heal", type=int, default=3)
    ap.add_argument("--chunk-chars", type=int, default=CHUNK_CHARS,
                    help=f"max source chars per model call (default {CHUNK_CHARS})")
    ap.add_argument("--max-keys", type=int, default=MAX_KEYS_PER_CHUNK,
                    help=f"max keys per model call (default {MAX_KEYS_PER_CHUNK}; the real "
                         "drop-avoidance knob — the model truncates big key-sets)")
    ap.add_argument("--workers", type=int, default=4,
                    help="concurrent chunk translations across ALL namespaces (default 4; "
                         "blocking urllib releases the GIL + LM Studio continuous-batches)")
    ap.add_argument("--force", action="store_true", help="re-translate even if valid output exists")
    ap.add_argument("--check", help="verify one <lang>/<ns>.json against en and exit")
    args = ap.parse_args()

    src_dir = LOCALES_DIR / SRC_LANG
    if args.check:
        code, name = args.check.split("/")
        src = flatten(json.loads((src_dir / name).read_text(encoding="utf-8")))
        out = flatten(json.loads((LOCALES_DIR / code / name).read_text(encoding="utf-8")))
        strs = {k: v for k, v in src.items() if isinstance(v, str)}
        hard, soft = verify_chunk(strs, {k: out.get(k) for k in strs}, TARGETS[code][1])
        print(f"{args.check}: {len(hard)} hard, {len(soft)} soft")
        for k, r in {**hard, **soft}.items():
            print(f"  {k}: {r}")
        return 1 if hard else 0

    langs = args.langs.split(",") if args.langs else list(TARGETS)
    ns_files = sorted(src_dir.glob("*.json"))
    if args.ns:
        wanted = set(args.ns.split(","))
        ns_files = [f for f in ns_files if f.stem in wanted]

    # PLAN every (lang, namespace): resume-skip up-to-date ones, chunk the rest.
    # A namespace listed in the language's _FAILED.json is force-retried even on
    # a plain resume (its keys currently sit as en fallback, which passes the
    # structural skip-check — so without this a re-run would never fix them).
    plans: list[dict] = []
    for code in langs:
        if code not in TARGETS:
            print(f"!! unknown lang {code}, skipping")
            continue
        _, script_re = TARGETS[code]
        failed_map: dict[str, list] = {}
        fpath = LOCALES_DIR / code / "_FAILED.json"
        if fpath.exists():
            try:
                failed_map = json.loads(fpath.read_text(encoding="utf-8"))
            except Exception:
                pass
        for ns in ns_files:
            try:
                plans.append(plan_namespace(code, ns, script_re, args.force, args.chunk_chars,
                                            args.max_keys, frozenset(failed_map.get(ns.name, []))))
            except Exception as e:  # noqa: BLE001
                print(f"  ✗ {code}/{ns.name} PLAN ERROR: {type(e).__name__}: {e}")
    work = [p for p in plans if p["status"] == "work"]
    skips = [p for p in plans if p["status"] == "skip"]
    tasks = [(p, i, chunk) for p in work for i, chunk in enumerate(p["chunks"])]
    print(f"planned: {len(work)} namespaces / {len(tasks)} chunks to translate; "
          f"{len(skips)} already up-to-date; {args.workers} workers")

    # Drive EVERY chunk (across all langs+namespaces) through ONE pool so the
    # model stays saturated. Write each namespace the instant its chunks finish.
    remaining = {id(p): len(p["chunks"]) for p in work}
    grand_failed = done = 0
    by_lang: dict[str, list[dict]] = {}
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futs = {ex.submit(translate_chunk, chunk, TARGETS[p["code"]][0], p["code"],
                          TARGETS[p["code"]][1], args.max_heal): (p, i)
                for (p, i, chunk) in tasks}
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
            if remaining[id(p)] == 0:  # namespace complete → write it now (resumable)
                isolate_retry_soft(p, TARGETS[p["code"]][0], p["code"], TARGETS[p["code"]][1])
                r = assemble_and_write(p)
                by_lang.setdefault(p["code"], []).append(r)
                grand_failed += r["failed"]
                flag = f" ⚠{r['soft']}" if r["soft"] else ""
                fail = f" ✗{r['failed']}" if r["failed"] else ""
                gap = f" +{p['n_new']} new" if p.get("n_new", 0) < p["keys"] else ""
                print(f"  ✓ {p['code']:<6} {r['ns']:<22} {r['keys']} keys{gap}{flag}{fail}  "
                      f"[{done}/{len(tasks)} chunks, {time.time()-t0:.0f}s]")

    # Per-language _FAILED.json report (keys left as en after heal exhausted).
    # Clear a stale report when a re-run resolves everything.
    for code, results in by_lang.items():
        report = {r["ns"]: r["failed_keys"] for r in results if r["failed"]}
        fpath = LOCALES_DIR / code / "_FAILED.json"
        if report:
            fpath.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        elif fpath.exists():
            fpath.unlink()
    print(f"\nDONE. {len(work)} namespaces written, {len(skips)} skipped. "
          f"total FAILED keys needing review: {grand_failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
