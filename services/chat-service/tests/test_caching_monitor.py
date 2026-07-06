"""Provider Context Strategy §7–§8 — prompt-cache monitoring math + thrashing.

Pure unit tests (no DB): the per-turn caching metrics and the rolling thrashing
detector, plus proof that the section is surfaced on the contextBudget frame.
"""
from app.services.caching_monitor import (
    STRATEGY_ANTHROPIC_CACHE,
    STRATEGY_STATELESS,
    build_caching_metrics,
    detect_thrashing,
    select_strategy,
)
from app.services.token_budget import compute_budget, context_budget_event

_ANTHROPIC = {"prompt_cache_control": True}
_AUTO = {"auto_prefix_cache": True}


def test_strategy_label_from_capability_not_name():
    assert select_strategy(_ANTHROPIC) == STRATEGY_ANTHROPIC_CACHE
    # auto-prefix providers are policy-stateless (server caches invisibly)
    assert select_strategy(_AUTO) == STRATEGY_STATELESS
    assert select_strategy(None) == STRATEGY_STATELESS
    assert select_strategy({}) == STRATEGY_STATELESS


def test_anthropic_cache_hit_turn_is_net_positive():
    # 12 uncached + 100 write + 4000 read = 4112 total input volume (the folded total)
    m = build_caching_metrics(
        cache_creation_tok=100, cache_read_tok=4000, input_tok=4112,
        capabilities=_ANTHROPIC,
    )
    assert m["strategy"] == STRATEGY_ANTHROPIC_CACHE
    assert m["auto_prefix"] is False
    assert m["uncached_tok"] == 12
    assert m["read_tok"] == 4000 and m["create_tok"] == 100
    assert 0.97 < m["hit_rate"] <= 1.0            # nearly all served from cache
    assert m["cost_delta_ratio"] > 0.5           # big saving vs billing all uncached
    assert m["write_premium_tok"] == 25.0        # 100 * (1.25 - 1)
    assert m["net_negative"] is False


def test_anthropic_priming_turn_is_net_negative_but_not_thrashing():
    # first turn writes the prefix, reads nothing → paid the write premium
    m = build_caching_metrics(
        cache_creation_tok=1000, cache_read_tok=0, input_tok=1012,
        capabilities=_ANTHROPIC,
    )
    assert m["create_tok"] == 1000 and m["read_tok"] == 0
    assert m["cost_delta_ratio"] < 0             # cost MORE than uncached this turn
    assert m["net_negative"] is True
    # a single priming turn must NOT be called thrashing (needs a rolling window)
    assert detect_thrashing([(1000, 0)], capabilities=_ANTHROPIC) is None


def test_openai_auto_prefix_read_is_saving_no_write_charge():
    # the 99% measured LM-Studio /v1/responses turn: 1711 cached of 1727
    m = build_caching_metrics(
        cache_creation_tok=0, cache_read_tok=1711, input_tok=1727,
        capabilities=_AUTO,
    )
    assert m["strategy"] == STRATEGY_STATELESS   # policy-stateless
    assert m["auto_prefix"] is True
    assert m["uncached_tok"] == 16
    assert m["write_premium_tok"] == 0.0         # auto-cache never writes-charges
    assert m["cost_delta_ratio"] > 0             # read discount = pure saving
    assert m["net_negative"] is False


def test_no_cache_turn_is_all_uncached_stable_zeros():
    m = build_caching_metrics(
        cache_creation_tok=0, cache_read_tok=0, input_tok=1000, capabilities=None,
    )
    assert m["strategy"] == STRATEGY_STATELESS
    assert m["uncached_tok"] == 1000
    assert m["hit_rate"] == 0.0
    assert m["cost_delta_ratio"] == 0.0
    assert m["net_negative"] is False


def test_uncached_floored_when_split_exceeds_input():
    # defensive: a provider mis-report where read+create > input must not go negative
    m = build_caching_metrics(
        cache_creation_tok=50, cache_read_tok=5000, input_tok=100, capabilities=_ANTHROPIC,
    )
    assert m["uncached_tok"] == 0


def test_detect_thrashing_auto_cache_never_thrashes():
    # write premium = 0 for auto-cache → no verdict regardless of the window
    assert detect_thrashing([(500, 0), (500, 0), (500, 0)], capabilities=_AUTO) is None
    assert detect_thrashing([(500, 0)] * 5, capabilities=None) is None


def test_detect_thrashing_needs_min_turns():
    assert detect_thrashing([(500, 0), (500, 0)], capabilities=_ANTHROPIC) is None


def test_detect_thrashing_flags_unstable_prefix():
    # 3+ turns paying write premiums with almost no reads back = thrashing
    window = [(500, 10), (500, 0), (400, 20)]
    assert detect_thrashing(window, capabilities=_ANTHROPIC) is True


def test_detect_thrashing_false_when_reads_dominate():
    window = [(100, 4000), (0, 3800), (50, 4100)]
    assert detect_thrashing(window, capabilities=_ANTHROPIC) is False


def test_detect_thrashing_false_when_never_wrote():
    # explicit-cache but the window never wrote (all reads/zeros) → nothing to thrash
    assert detect_thrashing([(0, 0), (0, 100), (0, 50)], capabilities=_ANTHROPIC) is False


def test_caching_metrics_surfaced_on_context_budget_frame():
    # proof-bound (§11a): the caching section actually rides the contextBudget frame,
    # not a stored-but-unread blob. Absent → the key is omitted (strictly additive).
    caching = build_caching_metrics(
        cache_creation_tok=100, cache_read_tok=4000, input_tok=4112,
        capabilities=_ANTHROPIC,
    )
    caching["thrashing"] = False
    budget = compute_budget(used_tokens=4112, context_length=200000, max_output_tokens=1024)

    with_caching = context_budget_event(budget, caching=caching)
    assert "caching" in with_caching
    assert with_caching["caching"]["strategy"] == STRATEGY_ANTHROPIC_CACHE
    assert with_caching["caching"]["read_tok"] == 4000
    assert with_caching["caching"]["thrashing"] is False

    # omitted when not supplied — the meter contract stays byte-identical for old paths
    assert "caching" not in context_budget_event(budget)
