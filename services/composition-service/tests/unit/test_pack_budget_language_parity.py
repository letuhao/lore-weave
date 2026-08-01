"""D-PACK-CL100K-STARVES-NONLATIN — `pack_token_budget` meant two different things.

The packer counted with `cl100k_base`. knowledge-service retired that encoding on
2026-07-07 after a live gateway measurement (M3): cl100k tokenizes CJK/Vietnamese ~1.5x
above what the platform actually serves (GPT-4o's o200k, and the local gemma/qwen models
at ~1 token per CJK char). Its own docstring names the consequence — *"CJK books were
trimmed to a smaller REAL budget than Latin ones"*. composition never received the fix.

Measured on real Vietnamese prose from the dogfood book, characters of grounding that
survive a 6000-token budget:

    English                29,756
    Vietnamese · cl100k    11,777   ← the bug
    Vietnamese · o200k     17,636   ← after

## Why these tests are written in CHARACTERS

Every existing pack/budget test injects a deterministic word counter (`_wc`) so it does
not depend on tiktoken. That is right for testing the *ladder*, and it is exactly why the
suite could not see this defect: swapping the encoder changes no injected-counter test.

A token count is not a fixed unit — it is the output of the very thing under test, so an
assertion in tokens re-states the change instead of checking it. **Characters are
estimator-invariant.** These tests ask the only question that survives an encoder swap:
*for a fixed budget, how much actual Vietnamese content reaches the model?*
"""
from __future__ import annotations

import pytest

from app.packer import budget as B

# Real Vietnamese prose (diacritics intact — they are what cl100k over-counts). Kept
# inline rather than read from a fixture so the sample cannot drift away from the
# thresholds derived from it.
_VI = (
    "Khói bụi từ những cột đá sụp đổ vẫn lơ lửng trong không trung, che khuất đi ánh "
    "trăng lạnh lẽo đang rọi xuống bãi chiến trường hoang tàn. Giữa trung tâm của sự "
    "hủy diệt, Lâm Uyên đứng đó, tà áo trắng đã nhuốm màu xám xịt của tro tàn và vệt "
    "đỏ thẫm của máu khô. Dưới chân chàng, Huyết Vô Thường nằm co quắp như một con thú "
    "bị thương nặng, lồng ngực phập phồng theo từng nhịp thở đứt quãng, khàn đặc. "
)
_EN = (
    "The ruins of the great hall lay scattered across the courtyard, splintered beams "
    "jutting from the rubble like the ribs of some enormous beast. Wind moved through "
    "the broken lattice and carried the cold of the night with it, and the young lord "
    "stood at the centre of it all with his white robes greyed by ash and dried blood. "
)

#: Chars of Vietnamese per budget-token, measured 2026-07-31:
#:   o200k  2.94   ·   cl100k  1.96
#: The floor sits between them, closer to cl100k, so the gate reds on a regression to
#: cl100k while tolerating normal drift in the sample or a tiktoken version bump.
_VI_CHARS_PER_TOKEN_FLOOR = 2.4


def _survivors(text: str, budget: int) -> int:
    """Characters that survive `enforce_budget` at `budget`, using the REAL default
    counter — the whole point is to exercise the production encoder, not a stub."""
    # Repeat the sample so there is always far more candidate text than the budget can
    # hold; otherwise the assertion measures the sample size, not the trim.
    unit = 200
    corpus = text * 40
    segs = [B.Segment("lore", corpus[i:i + unit], B.PRIO_LORE)
            for i in range(0, len(corpus), unit)]
    res = B.enforce_budget(segs, budget, B.default_counter())
    return sum(len(s.text) for s in res.kept)


class TestTheBudgetMeansTheSameThingInEveryLanguage:
    def test_vietnamese_is_not_starved_by_an_over_counting_encoder(self):
        budget = 2000
        chars = _survivors(_VI, budget)
        per_token = chars / budget
        assert per_token >= _VI_CHARS_PER_TOKEN_FLOOR, (
            f"only {per_token:.2f} chars of Vietnamese per budget token "
            f"(floor {_VI_CHARS_PER_TOKEN_FLOOR}). An encoder that over-counts non-Latin "
            "text trims the book's grounding to a fraction of what the same budget buys "
            "an English book — the D-PACK-CL100K-STARVES-NONLATIN regression."
        )

    def test_english_is_unaffected(self):
        """o200k and cl100k agree on Latin, so this fix must move English by ~nothing.
        A change here would mean the swap did something other than what it claims."""
        budget = 2000
        per_token = _survivors(_EN, budget) / budget
        assert 3.5 <= per_token <= 6.5, f"English drifted to {per_token:.2f} chars/token"

    def test_the_language_gap_is_bounded(self):
        """Vietnamese genuinely tokenizes denser than English — that part is real and
        stays. What must not return is the ADDITIONAL ~1.5x penalty: under cl100k the
        Vietnamese pack held ~40% of the English one; it should now sit near ~60%."""
        budget = 2000
        ratio = _survivors(_VI, budget) / _survivors(_EN, budget)
        assert ratio >= 0.5, (
            f"Vietnamese holds only {ratio:.0%} of the English pack at the same budget "
            "— the non-Latin over-count is back"
        )


class TestTheEncoderChoiceIsPinnedAndHonest:
    def test_the_pack_budgets_with_o200k(self):
        """Pins the decision itself. A silent revert to cl100k reds here rather than
        showing up months later as 'the Vietnamese book reads thin'."""
        assert B.encoder_name() == "o200k_base", (
            f"packing with {B.encoder_name()!r}; cl100k over-counts CJK/Vietnamese ~1.5x "
            "(retired repo-wide 2026-07-07 after the M3 live-gateway measurement)"
        )

    def test_a_missing_tiktoken_degrades_loudly_instead_of_raising_inside_a_pack(self, monkeypatch, caplog):
        """Before this fix `_tiktoken_counter` did a bare `import tiktoken` +
        `get_encoding` with no fallback — and tiktoken fetches its BPE file over HTTPS on
        first use, so an air-gapped or cold container raised INSIDE `enforce_budget`,
        failing a draft. knowledge-service already had the chain; composition did not."""
        import builtins

        real_import = builtins.__import__

        def _no_tiktoken(name, *a, **kw):
            if name == "tiktoken":
                raise ImportError("simulated: no tiktoken wheel / no network")
            return real_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", _no_tiktoken)
        monkeypatch.setattr(B, "_encoder", None)
        monkeypatch.setattr(B, "_encoder_name", "")

        with caplog.at_level("WARNING"):
            n = B._tiktoken_counter("một đoạn văn tiếng Việt")
        assert n > 0, "the degraded counter must still return a usable estimate"
        assert B.encoder_name() == "heuristic"
        assert any("tiktoken unavailable" in r.message for r in caplog.records), (
            "a degraded budget must be visible in the log, not silent"
        )
        # Reset so the module-level cache does not leak the degraded state.
        monkeypatch.setattr(B, "_encoder", None)
        monkeypatch.setattr(B, "_encoder_name", "")


def test_pack_token_budget_was_deliberately_not_retuned():
    """The constant is denominated in the encoder's units, so an encoder swap and a
    budget retune are the same semantic change and must be decided together.

    6000 was always meant to buy ~6000 REAL tokens. Under cl100k it bought that only for
    Latin books. Keeping it is the fix; lowering it would have preserved the starvation
    while looking like a correction.

    The same reasoning covers the 413 `PROMPT_TOO_LARGE` ceiling, which is
    `_pack_budget * 2` in the SAME counter units (`routers/engine.py`). It therefore moved
    with the encoder automatically: a Vietnamese prompt used to be refused at ~8k real
    tokens while an English one was allowed 12k. Both are now 12k. Selection edits that
    start passing are edits that were being refused wrongly — that is the fix landing, not
    a loosened guard."""
    from app.config import settings

    assert settings.pack_token_budget == 6000
