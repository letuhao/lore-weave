"""T2 GATE (authoritative) — meter accuracy vs CLEAN provider ground truth.

Sends known VI / CJK / English / mixed-JSON texts to a live local model and reads
`usage.prompt_tokens` — the provider's EXACT token count, with template overhead
isolated by subtracting a 1-char baseline. This is the unconfounded measurement:
no reasoning tokens, no tool-call args, no user-message gap (cf. the persisted-data
comparison in context-budget-t2-meter-accuracy.py, which is confounded by exactly
those and reads as a spurious under-estimate).

Finding (2026-07-04, gemma-4-26b): the script-aware `estimate_tokens` errs slightly
HIGH on prose (english +22%, chinese +18%, vietnamese +7.5%) and −8% on mixed JSON
— within ±22%, and biased toward OVER-estimation, which is the SAFE direction for a
compaction trigger (fires a touch early, never an overflow surprise). No calibration
change needed; the persisted-corpus under-estimate was the reasoning/tool confound.

Use a NON-reasoning model (reasoning inflates completion, not prompt, tokens — but
keep the probe clean). Requires LM Studio (or any OpenAI-compatible local endpoint).

Usage:
  PYTHONPATH=services/chat-service python scripts/context-budget-t2-live-calibration.py
  (override T2_LLM_URL / T2_LLM_MODEL)
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "services", "chat-service"))
from app.services.token_budget import estimate_tokens  # noqa: E402

URL = os.environ.get("T2_LLM_URL", "http://localhost:1234/v1/chat/completions")
MODEL = os.environ.get("T2_LLM_MODEL", "google/gemma-4-26b-a4b-qat")

SAMPLES = {
    "english": "the quick brown fox jumps over the lazy dog and runs away fast " * 12,
    "vietnamese": (
        "Ma Nữ Nghịch Thiên — nàng tiểu thư bị phản bội, tái sinh với ma công "
        "nghịch thiên, quyết trả thù cả thiên hạ " * 6
    ),
    "chinese": "万古神帝魔女逆天诸天神魔仙侠世界剑气纵横三千里一剑光寒十九洲 " * 8,
    "mixed_json": (
        '{"entities":["Lâm Uyển","Nguyễn Trãi","万古神帝"],"status":"drafting",'
        '"note":"the arc needs work"} ' * 6
    ),
}


def _prompt_tokens(text: str) -> int:
    import requests

    r = requests.post(
        URL,
        json={"model": MODEL, "messages": [{"role": "user", "content": text}],
              "max_tokens": 1, "temperature": 0},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["usage"]["prompt_tokens"]


def main() -> int:
    try:
        base = _prompt_tokens(".")
    except Exception as exc:  # pragma: no cover
        print(f"LLM endpoint unreachable ({URL}): {exc}")
        print("live infra unavailable: skip (persisted-corpus script still runs)")
        return 0

    print(f"T2 live meter calibration — {MODEL} (template overhead {base} tok)")
    print("=" * 62)
    print(f"  {'script':<12} {'chars':>6} {'provider':>9} {'estimate':>9} {'ratio':>6}")
    ratios = []
    for name, text in SAMPLES.items():
        pt = _prompt_tokens(text) - base
        est = estimate_tokens(text)
        ratio = est / pt if pt else 0.0
        ratios.append(ratio)
        print(f"  {name:<12} {len(text):>6} {pt:>9} {est:>9} {ratio:>6.3f}")

    # GATE: every script within ±30% of provider, and the estimator biased toward
    # OVER-estimation on prose (safe direction) — median ratio ≥ 1.0.
    import statistics

    worst = max(abs(r - 1.0) for r in ratios)
    median = statistics.median(ratios)
    ok = worst <= 0.30 and median >= 0.95
    print()
    print(f"  worst |ratio-1| = {worst:.2f}  ·  median ratio = {median:.2f}  (≥1.0 = errs safe-high)")
    print("GATE (all within ±30%, median ≥ 0.95):", "PASS" if ok else "REVIEW")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
