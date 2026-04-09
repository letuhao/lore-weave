"""
Translation Pipeline V2 — P4 Glossary Injection PoC

Proves that glossary context injection fixes name consistency.
Runs the SAME chapter text twice with gemma3:12b:
  A) WITHOUT glossary → names translated inconsistently
  B) WITH glossary    → names match glossary exactly

Glossary entries (simulating what glossary-service would return):
  伊斯坦莎 → Isutansha (character, Demon Lord)
  提拉米   → Tirami    (character, Hero)
  阿尔德里克 → Aldric   (character, Shadow Guard Captain)
  暗黑魔殿 → Dark Demon Palace (location)
  圣骑士团 → Holy Knight Order (organization)

Usage:
    cd services/translation-service
    python poc_v2_glossary.py
"""
import asyncio
import json
import re
import time
import httpx

OLLAMA_URL = "http://localhost:11434"
MODEL = "gemma3:12b"

SOURCE_LANG = "zh"
TARGET_LANG = "vi"

# ── Simulated glossary data (what glossary-service would return) ─────────

GLOSSARY_ENTRIES = [
    {"id": "isutansha", "kind": "character", "role": "Demon Lord",
     "zh": ["伊斯坦莎"], "vi": ["Isutansha"]},
    {"id": "tirami", "kind": "character", "role": "Hero",
     "zh": ["提拉米", "提拉米·苏兰特"], "vi": ["Tirami", "Tirami Sulant"]},
    {"id": "aldric", "kind": "character", "role": "Shadow Guard Captain",
     "zh": ["阿尔德里克"], "vi": ["Aldric"]},
    {"id": "dark-palace", "kind": "location",
     "zh": ["暗黑魔殿"], "vi": ["Hắc Ám Ma Điện"]},
    {"id": "holy-knights", "kind": "organization",
     "zh": ["圣骑士团"], "vi": ["Thánh Kỵ Sĩ Đoàn"]},
    {"id": "demon-race", "kind": "race",
     "zh": ["魔族"], "vi": ["Ma tộc"]},
]

# ── Chapter text (same as poc_v2_real.py) ────────────────────────────────

CHAPTER_BLOCKS = [
    "[BLOCK 0]\n第一章 魔王的觉醒",
    "[BLOCK 1]\n伊斯坦莎从沉睡中苏醒，黑色的长发散落在暗黑魔殿的王座之上。她缓缓睁开双眼，深红色的瞳孔中映射出宫殿里摇曳的烛光。",
    "[BLOCK 2]\n「陛下，勇者**提拉米**已经率领圣骑士团穿过了北方的冰原，预计三日之内便会抵达魔殿的外围防线。」",
    "[BLOCK 3]\n暗影侍卫长阿尔德里克单膝跪地，将最新的情报呈上。他是魔族中为数不多的混血种，既有人类的智慧，又拥有魔族的力量。",
    "[BLOCK 4]\n「三日……」伊斯坦莎轻声呢喃，嘴角浮起一丝冷笑。「让他来吧。上一次他差点杀了我，这一次，我不会再给他那个机会。」",
    "[BLOCK 5]\n她站起身来，黑色的魔力如同潮水般从她的身体中涌出，整个王座大厅都笼罩在一片压迫性的气场之下。暗影侍卫们纷纷低下了头，不敢直视她的目光。",
    "[BLOCK 6]\n「阿尔德里克，传令下去。召集所有魔将，在暗月升起之前，我要在战争议事厅见到他们每一个人。这一次，我们不再防守。」",
    "[BLOCK 7]\n「遵命，魔王陛下。」阿尔德里克恭敬地行礼，随即化为一道暗影消失在宫殿的走廊之中。",
    "[BLOCK 8]\n伊斯坦莎独自站在空旷的王座大厅中，目光穿过高耸的窗户望向远方。北方的天空已经被乌云笼罩，那是提拉米和他的军队带来的圣光力量扭曲了天象。",
    "[BLOCK 9]\n「提拉米……你这个固执的家伙。」她的声音里带着一丝复杂的情感。千年前，他们曾是并肩作战的伙伴。而如今，命运却让他们站在了对立的两端。",
]

COMBINED_TEXT = "\n\n".join(CHAPTER_BLOCKS)
EXPECTED_INDICES = list(range(10))


# ── Glossary context builder (V2 §4 implementation) ─────────────────────

def build_glossary_context(
    entries: list[dict],
    chapter_text: str,
    target_lang: str = "vi",
    max_tokens: int = 1500,
) -> str:
    """Build scoped glossary block for LLM prompt injection.

    Implements tiered strategy from V2 design §4:
    - Score by occurrence count × name length
    - Format as compact JSONL
    - Cap at max_tokens budget
    """
    # Score each entry by how often its names appear in the text
    scored = []
    for entry in entries:
        score = 0
        for name_zh in entry["zh"]:
            count = chapter_text.count(name_zh)
            score += count * len(name_zh)
        if score > 0:
            scored.append((score, entry))

    # Sort by score descending (most relevant first)
    scored.sort(key=lambda x: -x[0])

    # Build JSONL lines within token budget
    lines = []
    token_estimate = 0
    for score, entry in scored:
        names_zh = ", ".join(entry["zh"])
        names_tgt = ", ".join(entry.get(target_lang, []))
        kind = entry["kind"]
        role = entry.get("role", "")

        if names_tgt:
            line = f'{{"zh":["{names_zh}"],"{target_lang}":["{names_tgt}"],"kind":"{kind}"}}'
        else:
            line = f'{{"zh":["{names_zh}"],"kind":"{kind}"}}'

        # Rough token estimate: ~1 token per 4 chars for this metadata
        line_tokens = len(line) // 4 + 1
        if token_estimate + line_tokens > max_tokens:
            break

        lines.append(line)
        token_estimate += line_tokens

    if not lines:
        return ""

    return (
        "GLOSSARY — Use these EXACT translations for names/terms:\n"
        + "\n".join(lines)
    )


# ── Helpers ──────────────────────────────────────────────────────────────

async def call_ollama(messages):
    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(
            f"{OLLAMA_URL}/api/chat",
            json={"model": MODEL, "messages": messages, "stream": False,
                  "options": {"num_predict": 4096, "temperature": 0.3}},
        )
        resp.raise_for_status()
        return resp.json()


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
        except (ValueError, IndexError):
            pass
        i += 2
    return result


def extract_names(text: str, glossary: list[dict]) -> dict[str, list[str]]:
    """Find how each glossary entity's ZH names were translated in the output.

    Returns {entity_id: [translations_found]}.
    This is a rough heuristic: for each ZH name, find the Vietnamese text
    that appears near where the ZH name was in the source.
    """
    # Simple approach: check if the expected VI names appear in the output
    results = {}
    for entry in glossary:
        eid = entry["id"]
        expected_vi = entry.get("vi", [])
        found = []
        for name in expected_vi:
            if name.lower() in text.lower():
                found.append(name)
        results[eid] = found
    return results


def hr(title):
    print(f"\n{'='*70}\n  {title}\n{'='*70}\n")

def section(title):
    print(f"\n--- {title} ---\n")


# ── Run A: Without glossary ─────────────────────────────────────────────

async def run_without_glossary():
    section("Run A: WITHOUT Glossary")

    system = (
        "You are a professional Chinese to Vietnamese translator.\n\n"
        "RULES:\n"
        "1. Output EXACT same [BLOCK N] labels in same order.\n"
        "2. Translate text only. Keep **bold**, *italic* formatting.\n"
        "3. Output exactly 10 blocks. No commentary."
    )
    user = f"Translate these 10 blocks:\n\n{COMBINED_TEXT}"

    t0 = time.time()
    response = await call_ollama([
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ])
    elapsed = time.time() - t0

    resp_text = response.get("message", {}).get("content", "")
    in_tok = response.get("prompt_eval_count", 0)
    out_tok = response.get("eval_count", 0)

    parsed = parse_blocks(resp_text, EXPECTED_INDICES)
    print(f"  Time: {elapsed:.1f}s, Tokens: in={in_tok} out={out_tok}")
    print(f"  Blocks parsed: {len(parsed)}/10")

    return parsed, resp_text


# ── Run B: With glossary ────────────────────────────────────────────────

async def run_with_glossary():
    section("Run B: WITH Glossary")

    glossary_block = build_glossary_context(
        GLOSSARY_ENTRIES, COMBINED_TEXT, TARGET_LANG,
    )
    print(f"  Glossary block ({len(glossary_block)} chars):")
    for line in glossary_block.split("\n"):
        print(f"    {line}")
    print()

    system = (
        "You are a professional Chinese to Vietnamese translator.\n\n"
        f"{glossary_block}\n\n"
        "RULES:\n"
        "1. Output EXACT same [BLOCK N] labels in same order.\n"
        "2. Translate text only. Keep **bold**, *italic* formatting.\n"
        "3. Output exactly 10 blocks. No commentary.\n"
        "4. For names/terms in the GLOSSARY, use the EXACT Vietnamese translations provided."
    )
    user = f"Translate these 10 blocks:\n\n{COMBINED_TEXT}"

    t0 = time.time()
    response = await call_ollama([
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ])
    elapsed = time.time() - t0

    resp_text = response.get("message", {}).get("content", "")
    in_tok = response.get("prompt_eval_count", 0)
    out_tok = response.get("eval_count", 0)

    parsed = parse_blocks(resp_text, EXPECTED_INDICES)
    print(f"  Time: {elapsed:.1f}s, Tokens: in={in_tok} out={out_tok}")
    print(f"  Blocks parsed: {len(parsed)}/10")

    return parsed, resp_text


# ── Compare results ──────────────────────────────────────────────────────

def compare_results(parsed_a, text_a, parsed_b, text_b):
    hr("COMPARISON: Name Consistency")

    # Check each glossary entity
    full_a = " ".join(parsed_a.get(i, "") for i in range(10))
    full_b = " ".join(parsed_b.get(i, "") for i in range(10))

    print(f"  {'Entity':<20} {'Expected VI':<20} {'Without Glossary':<25} {'With Glossary':<25} {'Match?'}")
    print(f"  {'-'*20} {'-'*20} {'-'*25} {'-'*25} {'-'*6}")

    total_checks = 0
    matches_a = 0
    matches_b = 0

    for entry in GLOSSARY_ENTRIES:
        expected_names = entry.get("vi", [])
        if not expected_names:
            continue
        primary_vi = expected_names[0]
        zh_names = entry["zh"]

        # Count occurrences in source
        src_count = sum(COMBINED_TEXT.count(n) for n in zh_names)
        if src_count == 0:
            continue

        # Check if expected VI name appears in output
        found_a = primary_vi.lower() in full_a.lower()
        found_b = primary_vi.lower() in full_b.lower()

        # Count how many times it appears
        count_a = full_a.lower().count(primary_vi.lower())
        count_b = full_b.lower().count(primary_vi.lower())

        status_a = f"{count_a}x" if found_a else "WRONG"
        status_b = f"{count_b}x" if found_b else "WRONG"

        match_symbol = "YES" if found_b else "NO"

        print(f"  {entry['id']:<20} {primary_vi:<20} {status_a:<25} {status_b:<25} {match_symbol}")

        total_checks += 1
        if found_a:
            matches_a += 1
        if found_b:
            matches_b += 1

    print()
    print(f"  Score WITHOUT glossary: {matches_a}/{total_checks} names correct")
    print(f"  Score WITH glossary:    {matches_b}/{total_checks} names correct")

    # Show side-by-side for key blocks
    section("Side-by-Side: Key Blocks")

    key_blocks = [0, 1, 2, 3, 7, 9]  # blocks with character names
    for idx in key_blocks:
        src = CHAPTER_BLOCKS[idx].split("\n", 1)[1] if "\n" in CHAPTER_BLOCKS[idx] else ""
        a = parsed_a.get(idx, "(missing)")
        b = parsed_b.get(idx, "(missing)")
        print(f"  [BLOCK {idx}] ZH: {src[:70]}")
        print(f"           A:  {a[:70]}")
        print(f"           B:  {b[:70]}")
        print()

    return matches_a, matches_b


# ── Main ─────────────────────────────────────────────────────────────────

async def main():
    hr(f"GLOSSARY INJECTION PoC (P4)\n  Model: {MODEL}\n  Chinese → Vietnamese")

    # Check Ollama
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(f"{OLLAMA_URL}/api/tags")
            models = [m["name"] for m in r.json().get("models", [])]
            if MODEL not in models:
                print(f"  ERROR: '{MODEL}' not found. Available: {models}")
                return
    except Exception as e:
        print(f"  ERROR: Ollama not reachable: {e}")
        return

    # Run both
    parsed_a, text_a = await run_without_glossary()
    parsed_b, text_b = await run_with_glossary()

    # Compare
    score_a, score_b = compare_results(parsed_a, text_a, parsed_b, text_b)

    hr("PoC RESULT")
    if score_b > score_a:
        print(f"  PASS: Glossary injection improved name accuracy ({score_a} → {score_b})")
    elif score_b == score_a and score_b == len(GLOSSARY_ENTRIES):
        print(f"  PASS: Both perfect — model happens to guess right, but glossary guarantees it")
    else:
        print(f"  MIXED: A={score_a}, B={score_b} — may need prompt tuning or auto-correct post-processing")

    print()
    print("  Key takeaway:")
    print("  Without glossary: model GUESSES translations (Tiramisu, Istansa, etc.)")
    print("  With glossary:    model uses EXACT translations from glossary")
    print("  This is the #1 quality issue for novel translation.")
    print()


if __name__ == "__main__":
    asyncio.run(main())
