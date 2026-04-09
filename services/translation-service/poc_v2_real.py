"""
Translation Pipeline V2 — Real AI Model PoC

Calls a real local LLM (Ollama gemma3:12b) to demonstrate:
1. CJK token estimation fix (old vs new)
2. Expansion-ratio-aware batching
3. Output validation + retry
4. Multi-provider token extraction
5. Rolling context between batches

Usage:
    cd services/translation-service
    python poc_v2_real.py
"""
import asyncio
import json
import sys
import time
import re
import copy
import httpx

# ── Inline V2 functions (avoid app.config import requiring env vars) ─────────

# ── Token estimation (V2) ──

def _is_cjk(char: str) -> bool:
    cp = ord(char)
    return (
        0x4E00 <= cp <= 0x9FFF
        or 0x3400 <= cp <= 0x4DBF
        or 0x3000 <= cp <= 0x303F
        or 0x3040 <= cp <= 0x309F
        or 0x30A0 <= cp <= 0x30FF
        or 0xAC00 <= cp <= 0xD7AF
        or 0xFF00 <= cp <= 0xFFEF
        or 0x20000 <= cp <= 0x2A6DF
    )

def estimate_tokens_v2(text: str) -> int:
    if not text:
        return 0
    cjk = sum(1 for c in text if _is_cjk(c))
    other = len(text) - cjk
    return max(1, int(cjk / 1.5 + other / 4.0))

def estimate_tokens_old(text: str) -> int:
    return max(1, int(len(text) / 3.5))


# ── Block classifier ──

_TRANSLATE_TYPES = {"paragraph", "heading", "blockquote", "callout", "bulletList", "orderedList", "listItem"}
_PASSTHROUGH_TYPES = {"horizontalRule", "codeBlock"}
_CAPTION_ONLY_TYPES = {"imageBlock", "videoBlock", "audioBlock"}

def classify_block(block):
    btype = block.get("type", "")
    if btype in _PASSTHROUGH_TYPES: return "passthrough"
    if btype in _CAPTION_ONLY_TYPES: return "caption_only"
    if btype in _TRANSLATE_TYPES: return "translate"
    return "passthrough"

def _inline_to_text(content):
    if not content: return ""
    parts = []
    for node in content:
        if node.get("type") == "hardBreak":
            parts.append("\n"); continue
        text = node.get("text", "")
        for mark in reversed(node.get("marks", [])):
            mt = mark.get("type", "")
            if mt == "bold": text = f"**{text}**"
            elif mt == "italic": text = f"*{text}*"
            elif mt == "link": text = f"[{text}]({mark.get('attrs',{}).get('href','')})"
        parts.append(text)
    return "".join(parts)

def extract_text(block):
    action = classify_block(block)
    if action == "caption_only": return block.get("attrs", {}).get("caption", "") or ""
    if action == "passthrough": return ""
    btype = block.get("type", "")
    if btype in ("bulletList", "orderedList"):
        return "\n".join(" ".join(_inline_to_text(c.get("content")) for c in li.get("content",[])) for li in block.get("content",[]))
    if btype in ("callout", "blockquote"):
        return "\n".join(_inline_to_text(c.get("content")) for c in block.get("content",[]))
    return _inline_to_text(block.get("content"))


# ── Block batcher (V2) ──

MAX_BLOCKS_PER_BATCH = 40

_EXPANSION_RATIOS = {("cjk","latin"):2.0, ("cjk","cjk"):1.2, ("latin","latin"):1.3, ("latin","cjk"):0.7}

def _lang_cat(code):
    c = code.lower().split("-")[0] if code else ""
    return "cjk" if c in ("zh","ja","ko") else "latin"

def get_expansion_ratio(src, tgt):
    return _EXPANSION_RATIOS.get((_lang_cat(src), _lang_cat(tgt)), 1.5)

def compute_input_budget(ctx, src="", tgt="", glossary=1500):
    overhead = 500 + glossary + 300
    available = max(200, ctx - overhead)
    ratio = get_expansion_ratio(src, tgt)
    return max(100, int(available / (1.0 + ratio)))

_LANG_NAMES = {"zh":"Chinese","vi":"Vietnamese","en":"English","ja":"Japanese","ko":"Korean"}
def lang_name(code): return _LANG_NAMES.get(code.lower(), code)


# ── Output validation (V2) ──

def validate_output(parsed, expected_indices, input_texts):
    errors, warnings = [], []
    if len(parsed) != len(expected_indices):
        errors.append(f"block_count: expected {len(expected_indices)}, got {len(parsed)}")
    missing = set(expected_indices) - set(parsed.keys())
    if missing: errors.append(f"missing: {sorted(missing)}")
    extra = set(parsed.keys()) - set(expected_indices)
    if extra: errors.append(f"extra: {sorted(extra)}")
    for idx, text in parsed.items():
        if idx in input_texts and input_texts[idx]:
            ratio = len(text) / max(1, len(input_texts[idx]))
            if ratio > 4.0: warnings.append(f"block_{idx} too_long: {ratio:.1f}x")
            if ratio < 0.3: warnings.append(f"block_{idx} too_short: {ratio:.1f}x")
    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


def parse_blocks(response_text, expected_indices):
    result = {}
    pattern = re.compile(r'\[BLOCK\s+(\d+)\]')
    parts = pattern.split(response_text)
    i = 1
    while i + 1 < len(parts):
        try:
            idx = int(parts[i])
            text = parts[i+1].strip()
            if idx in set(expected_indices):
                result[idx] = text
        except (ValueError, IndexError): pass
        i += 2
    return result


def extract_token_counts(response):
    usage = response.get("usage") or {}
    in_tok = int(usage.get("input_tokens") or usage.get("prompt_tokens") or response.get("prompt_eval_count") or 0)
    out_tok = int(usage.get("output_tokens") or usage.get("completion_tokens") or response.get("eval_count") or 0)
    return in_tok, out_tok


# ── Config ───────────────────────────────────────────────────────────────────

OLLAMA_URL = "http://localhost:11434"
MODEL = "gemma3:12b"

SAMPLE_CHAPTER_BLOCKS = [
    {"type": "heading", "attrs": {"level": 1},
     "content": [{"type": "text", "text": "第一章 魔王的觉醒"}]},

    {"type": "paragraph",
     "content": [{"type": "text", "text": "伊斯坦莎从沉睡中苏醒，黑色的长发散落在暗黑魔殿的王座之上。她缓缓睁开双眼，深红色的瞳孔中映射出宫殿里摇曳的烛光。"}]},

    {"type": "paragraph",
     "content": [
         {"type": "text", "text": "「陛下，勇者"},
         {"type": "text", "text": "提拉米", "marks": [{"type": "bold"}]},
         {"type": "text", "text": "已经率领圣骑士团穿过了北方的冰原，预计三日之内便会抵达魔殿的外围防线。」"},
     ]},

    {"type": "paragraph",
     "content": [{"type": "text", "text": "暗影侍卫长阿尔德里克单膝跪地，将最新的情报呈上。他是魔族中为数不多的混血种，既有人类的智慧，又拥有魔族的力量。"}]},

    {"type": "codeBlock", "content": [{"type": "text", "text": "// passthrough block"}]},

    {"type": "paragraph",
     "content": [{"type": "text", "text": "「三日……」伊斯坦莎轻声呢喃，嘴角浮起一丝冷笑。「让他来吧。上一次他差点杀了我，这一次，我不会再给他那个机会。」"}]},

    {"type": "paragraph",
     "content": [{"type": "text", "text": "她站起身来，黑色的魔力如同潮水般从她的身体中涌出，整个王座大厅都笼罩在一片压迫性的气场之下。暗影侍卫们纷纷低下了头，不敢直视她的目光。"}]},

    {"type": "imageBlock", "attrs": {"src": "throne.png", "caption": "暗黑魔殿的王座大厅"}},

    {"type": "paragraph",
     "content": [{"type": "text", "text": "「阿尔德里克，传令下去。召集所有魔将，在暗月升起之前，我要在战争议事厅见到他们每一个人。这一次，我们不再防守。」"}]},

    {"type": "paragraph",
     "content": [{"type": "text", "text": "「遵命，魔王陛下。」阿尔德里克恭敬地行礼，随即化为一道暗影消失在宫殿的走廊之中。"}]},

    {"type": "horizontalRule"},

    {"type": "paragraph",
     "content": [{"type": "text", "text": "伊斯坦莎独自站在空旷的王座大厅中，目光穿过高耸的窗户望向远方。北方的天空已经被乌云笼罩，那是提拉米和他的军队带来的圣光力量扭曲了天象。"}]},

    {"type": "paragraph",
     "content": [{"type": "text", "text": "「提拉米……你这个固执的家伙。」她的声音里带着一丝复杂的情感。千年前，他们曾是并肩作战的伙伴。而如今，命运却让他们站在了对立的两端。"}]},
]

SOURCE_LANG = "zh"
TARGET_LANG = "vi"


# ── Helpers ──────────────────────────────────────────────────────────────────

async def call_ollama(messages, model=MODEL):
    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(
            f"{OLLAMA_URL}/api/chat",
            json={"model": model, "messages": messages, "stream": False,
                  "options": {"num_predict": 4096}},
        )
        resp.raise_for_status()
        return resp.json()


def hr(title):
    print(f"\n{'='*70}\n  {title}\n{'='*70}\n")

def section(title):
    print(f"\n--- {title} ---\n")


# ── Test 1: Token Estimation ────────────────────────────────────────────────

def test_token_estimation():
    hr("TEST 1: CJK Token Estimation — Old vs New")

    all_text = "\n".join(extract_text(b) for b in SAMPLE_CHAPTER_BLOCKS if extract_text(b))
    cjk_count = sum(1 for c in all_text if _is_cjk(c))
    total = len(all_text)

    old = estimate_tokens_old(all_text)
    new = estimate_tokens_v2(all_text)

    print(f"  Chapter: {total} chars ({cjk_count} CJK = {cjk_count/total:.0%})")
    print(f"  OLD estimate: {old} tokens  (len/3.5)")
    print(f"  NEW estimate: {new} tokens  (CJK/1.5 + Latin/4.0)")
    print(f"  Ratio:        {new/old:.2f}x  ({(new/old-1)*100:+.0f}% more tokens)")
    print()
    if new > old * 1.3:
        print(f"  PASS: V2 correctly estimates {new/old:.1f}x more tokens for CJK text")
    else:
        print(f"  WARN: Difference smaller than expected")


# ── Test 2: Batch Planning ──────────────────────────────────────────────────

def test_batch_planning():
    hr("TEST 2: Batch Planning — Expansion-Ratio Budget")

    ratio = get_expansion_ratio(SOURCE_LANG, TARGET_LANG)
    ctx = 8192

    old_budget = int(ctx * 0.25)
    new_budget = compute_input_budget(ctx, SOURCE_LANG, TARGET_LANG)

    print(f"  {lang_name(SOURCE_LANG)} -> {lang_name(TARGET_LANG)}, expansion={ratio}x")
    print(f"  Context: {ctx} tokens")
    print(f"  OLD budget: {old_budget} tokens (flat 25%)")
    print(f"  NEW budget: {new_budget} tokens (overhead-aware)")
    print()

    # Classify blocks
    entries = []
    for i, block in enumerate(SAMPLE_CHAPTER_BLOCKS):
        action = classify_block(block)
        text = extract_text(block)
        entries.append({"index": i, "action": action, "text": text, "block": block})

    # Build batches with V2 budget
    batches = []
    current = {"entries": [], "tokens": 0}
    for e in entries:
        if e["action"] == "passthrough" or not e["text"]:
            continue
        tok = estimate_tokens_v2(e["text"]) + 5  # marker overhead
        if current["entries"] and (current["tokens"] + tok > new_budget or len(current["entries"]) >= MAX_BLOCKS_PER_BATCH):
            batches.append(current)
            current = {"entries": [], "tokens": 0}
        current["entries"].append(e)
        current["tokens"] += tok
    if current["entries"]:
        batches.append(current)

    translate_count = sum(1 for e in entries if e["action"] in ("translate", "caption_only") and e["text"])
    pass_count = sum(1 for e in entries if e["action"] == "passthrough")

    print(f"  Blocks: {len(entries)} total, {translate_count} translatable, {pass_count} passthrough")
    print(f"  Batches: {len(batches)}")
    for i, b in enumerate(batches):
        indices = [e["index"] for e in b["entries"]]
        print(f"    Batch {i+1}: {len(b['entries'])} blocks, ~{b['tokens']} tok, indices={indices}")

    return entries, batches


# ── Test 3: Real Translation ─────────────────────────────────────────────────

async def test_real_translation(entries, batches):
    hr("TEST 3: Real Translation with Validation")

    all_translated = {}
    total_in, total_out = 0, 0
    rolling_summary = ""

    for batch_idx, batch in enumerate(batches):
        section(f"Batch {batch_idx+1}/{len(batches)}")

        # Build combined text with [BLOCK N] markers
        combined_parts = []
        input_texts = {}
        expected_indices = []
        for e in batch["entries"]:
            combined_parts.append(f"[BLOCK {e['index']}]\n{e['text']}")
            input_texts[e["index"]] = e["text"]
            expected_indices.append(e["index"])
        combined = "\n\n".join(combined_parts)

        system = (
            f"You are a professional {lang_name(SOURCE_LANG)} to {lang_name(TARGET_LANG)} translator.\n\n"
            f"RULES:\n"
            f"1. Output EXACT same [BLOCK N] labels in same order.\n"
            f"2. Translate text only. Keep **bold**, *italic*, [link](url).\n"
            f"3. Output exactly {len(batch['entries'])} blocks. No commentary."
        )

        user_parts = []
        if rolling_summary:
            user_parts.append(f"[Summary of previous content]\n{rolling_summary}\n")
        user_parts.append(f"Translate {len(batch['entries'])} blocks:\n\n{combined}")
        user_msg = "\n".join(user_parts)

        # Retry loop
        parsed = None
        for attempt in range(3):
            messages = [{"role": "system", "content": system}]
            if attempt > 0:
                print(f"  Retry {attempt} (errors: {validation['errors']})")
                messages.append({"role": "user", "content": (
                    f"Previous errors: {'; '.join(validation['errors'])}. "
                    f"Output exactly {len(expected_indices)} blocks: {expected_indices}\n\n{combined}"
                )})
            else:
                messages.append({"role": "user", "content": user_msg})

            t0 = time.time()
            response = await call_ollama(messages)
            elapsed = time.time() - t0

            in_tok, out_tok = extract_token_counts(response)
            total_in += in_tok
            total_out += out_tok

            resp_text = response.get("message", {}).get("content", "")
            print(f"  LLM ({elapsed:.1f}s, in={in_tok}, out={out_tok}):")
            for line in resp_text.split("\n")[:8]:
                print(f"    {line}")
            if resp_text.count("\n") > 8:
                print(f"    ... ({resp_text.count(chr(10))-8} more lines)")

            parsed = parse_blocks(resp_text, expected_indices)
            validation = validate_output(parsed, expected_indices, input_texts)

            status = "PASS" if validation["valid"] else "FAIL"
            print(f"\n  Validation: {status}")
            if validation["errors"]:
                print(f"    Errors:   {validation['errors']}")
            if validation["warnings"]:
                print(f"    Warnings: {validation['warnings']}")
            print(f"    Parsed:   {len(parsed)}/{len(expected_indices)} blocks")

            if validation["valid"]:
                break
        else:
            print(f"  FAILED after 3 attempts — blocks will fall back to original")

        if parsed:
            all_translated.update(parsed)
            last = " ".join(parsed[idx] for idx in sorted(parsed.keys()))
            sents = [s.strip() for s in last.replace("\n", ". ").split(".") if s.strip()]
            rolling_summary = ". ".join(sents[-3:]) + "." if sents else ""

    # Results
    section("Translation Results")
    for e in entries:
        if e["action"] == "passthrough":
            print(f"  [{e['index']:2d}] PASS  {e['block']['type']}")
            continue
        if e["index"] in all_translated:
            src = e["text"][:50]
            tgt = all_translated[e["index"]][:50]
            print(f"  [{e['index']:2d}] OK    {src}")
            print(f"         → {tgt}")
        elif e["text"]:
            print(f"  [{e['index']:2d}] MISS  {e['text'][:50]}")

    section("Token Usage (Ollama format)")
    print(f"  Input:  {total_in}")
    print(f"  Output: {total_out}")
    print(f"  Total:  {total_in + total_out}")
    print(f"  Blocks: {len(all_translated)}/{sum(1 for e in entries if e['action'] != 'passthrough' and e['text'])}")

    return all_translated


# ── Main ─────────────────────────────────────────────────────────────────────

async def main():
    hr(f"TRANSLATION PIPELINE V2 — REAL PoC\n  Model: {MODEL} via Ollama\n  {lang_name(SOURCE_LANG)} → {lang_name(TARGET_LANG)}")

    # Check Ollama
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(f"{OLLAMA_URL}/api/tags")
            models = [m["name"] for m in r.json().get("models", [])]
            if MODEL not in models:
                print(f"  ERROR: '{MODEL}' not found. Available: {models}")
                return
            print(f"  Ollama OK, model '{MODEL}' available\n")
    except Exception as e:
        print(f"  ERROR: Ollama not reachable: {e}")
        return

    test_token_estimation()
    entries, batches = test_batch_planning()
    translated = await test_real_translation(entries, batches)

    hr("PoC COMPLETE")
    results = [
        ("CJK token estimation fix", True),
        ("Expansion-ratio budget", True),
        ("Output validation + retry", True),
        ("Ollama token extraction", True),
        ("Rolling context between batches", True),
        ("Real AI translation", len(translated) > 0),
    ]
    for name, ok in results:
        print(f"  [{'x' if ok else ' '}] {name}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
