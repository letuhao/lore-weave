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
# Source chars per model call. The model is loaded at ~224K ctx, so this is NOT
# a capacity limit — it's an ATTENTION-quality limit: long inputs degrade
# ("lost in the middle") and an over-stuffed batch makes the model drop/merge
# keys. Moderate chunks keep per-key fidelity high + heal granular. Tunable
# via --chunk-chars.
CHUNK_CHARS = 6000
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
    """Strip ```json fences / prose and parse the first {...} object."""
    t = text.strip()
    if "```" in t:
        t = re.sub(r"^```[a-zA-Z]*\n?|```$", "", t.strip("`\n ")).strip()
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in model output")
    return json.loads(t[start:end + 1])


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
    "Rules: keep every JSON key byte-identical; preserve every {{placeholder}}, $t(...) "
    "reference, and <html/tag> EXACTLY as-is; keep brand/proper names and short technical "
    "tokens (API, URL, ID, PDF) untranslated; produce idiomatic, natural phrasing. "
    "Output ONLY a single JSON object, no commentary, no code fences."
)


def translate_chunk(src: dict[str, str], endonym: str, code: str,
                    script_re: str | None, max_heal: int) -> tuple[dict, dict]:
    user = (f"Target language: {endonym} ({code})\n\n"
            f"{json.dumps(src, ensure_ascii=False, indent=0)}")
    out: dict = {}
    for attempt in range(max_heal + 1):
        try:
            out = extract_json(call_model(SYSTEM, user))
        except (ValueError, json.JSONDecodeError) as e:
            user = (f"Your previous output was not valid JSON ({e}). Re-emit ONLY a "
                    f"JSON object translating these into {endonym}:\n\n"
                    f"{json.dumps(src, ensure_ascii=False)}")
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


def chunk_items(src_flat: dict[str, str], chunk_chars: int = CHUNK_CHARS) -> list[dict[str, str]]:
    chunks, cur, size = [], {}, 0
    for k, v in src_flat.items():
        vlen = len(k) + len(str(v)) + 8
        if cur and size + vlen > chunk_chars:
            chunks.append(cur)
            cur, size = {}, 0
        cur[k] = v
        size += vlen
    if cur:
        chunks.append(cur)
    return chunks


# ── namespace / language orchestration ─────────────────────────────────────
def translate_namespace(code: str, ns_path: Path, endonym: str, script_re: str | None,
                        max_heal: int, force: bool, chunk_chars: int = CHUNK_CHARS) -> dict:
    out_path = LOCALES_DIR / code / ns_path.name
    src_obj = json.loads(ns_path.read_text(encoding="utf-8"))
    src_flat = flatten(src_obj)
    str_leaves = {k: v for k, v in src_flat.items() if isinstance(v, str)}
    passthrough = {k: v for k, v in src_flat.items() if not isinstance(v, str)}

    if out_path.exists() and not force:
        try:
            existing = flatten(json.loads(out_path.read_text(encoding="utf-8")))
            if set(existing) == set(src_flat) and not any(
                verify_chunk(str_leaves, {k: existing.get(k) for k in str_leaves}, script_re)[0]
            ):
                return {"ns": ns_path.name, "status": "skip", "keys": len(str_leaves)}
        except Exception:
            pass  # fall through to re-translate

    translated: dict[str, object] = dict(passthrough)
    soft_all: dict[str, str] = {}
    for chunk in chunk_items(str_leaves, chunk_chars):
        out, soft = translate_chunk(chunk, endonym, code, script_re, max_heal)
        translated.update({k: out.get(k, chunk[k]) for k in chunk})
        soft_all.update(soft)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(unflatten(translated), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    failed = {k: v for k, v in soft_all.items() if str(v).startswith("FAILED")}
    return {"ns": ns_path.name, "status": "ok", "keys": len(str_leaves),
            "soft": len(soft_all) - len(failed), "failed": len(failed),
            "failed_keys": list(failed)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--langs", help="comma list of target codes (default: all)")
    ap.add_argument("--ns", help="comma list of namespace stems (default: all)")
    ap.add_argument("--max-heal", type=int, default=3)
    ap.add_argument("--chunk-chars", type=int, default=CHUNK_CHARS,
                    help=f"source chars per model call (default {CHUNK_CHARS}; "
                         "attention-quality limit, not capacity)")
    ap.add_argument("--workers", type=int, default=4,
                    help="concurrent namespace translations (default 4; urllib releases "
                         "the GIL on I/O + LM Studio continuous-batches)")
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

    grand_failed = 0
    for code in langs:
        if code not in TARGETS:
            print(f"!! unknown lang {code}, skipping")
            continue
        endonym, script_re = TARGETS[code]
        print(f"\n=== {code} ({endonym}) — {len(ns_files)} namespaces ===")
        report: dict[str, list[str]] = {}
        errored: list[str] = []

        def _work(ns: Path):
            # Each namespace is independent (reads its own src, writes its own file),
            # so N run concurrently with no shared mutable state.
            t0 = time.time()
            try:
                r = translate_namespace(code, ns, endonym, script_re, args.max_heal,
                                        args.force, args.chunk_chars)
                return ns, r, time.time() - t0, None
            except Exception as e:  # noqa: BLE001 — one namespace's failure must not abort the batch
                return ns, None, time.time() - t0, e

        # Consume results in the MAIN thread as they complete → prints/aggregation
        # need no lock (single consumer). Worker threads only do HTTP + file writes.
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
            for ns, r, dt, err in (f.result() for f in as_completed(
                    [ex.submit(_work, ns) for ns in ns_files])):
                if err is not None:
                    print(f"  ✗ {ns.name:<24} ERROR: {type(err).__name__}: {err}  ({dt:.0f}s, resumable)")
                    errored.append(ns.name)
                elif r["status"] == "skip":
                    print(f"  = {r['ns']:<24} skip ({r['keys']} keys)")
                else:
                    flag = f" ⚠{r['soft']}" if r["soft"] else ""
                    fail = f" ✗{r['failed']}" if r["failed"] else ""
                    print(f"  ✓ {r['ns']:<24} {r['keys']} keys{flag}{fail}  {dt:.0f}s")
                    if r["failed"]:
                        report[r["ns"]] = r["failed_keys"]
                        grand_failed += r["failed"]
        if errored:
            print(f"  !! {code}: {len(errored)} namespaces errored (resumable): {', '.join(errored)}")
        if report:
            (LOCALES_DIR / code / "_FAILED.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  !! {code}: {sum(len(v) for v in report.values())} keys need manual review "
                  f"→ {code}/_FAILED.json")
    print(f"\nDONE. total FAILED keys needing review: {grand_failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
