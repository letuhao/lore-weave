"""Golden test for loreweave_context.build_system_message (T3.1).

Pins the renderer BYTE-IDENTICAL to the two original stream_service ladders (A1): the
Anthropic cache path (list[dict] + cache_control) and the plain "\n\n"-joined path. The
matrix covers present/absent blocks, cache vs plain, and the strip-vs-verbatim asymmetry.
"""
from loreweave_context import build_system_message

TAIL = ["steering", "glossary", "knowledge", "universal", "planforge",
        "userskills", "planmode", "skillmeta", "booknote"]


def _plain(**kw):
    base = dict(use_cache=False, kctx_context="", kctx_stable="", kctx_volatile="",
                wm_pinned=None, system_prompt=None, tail_blocks=[])
    base.update(kw)
    return build_system_message(**base)


def _cache(**kw):
    base = dict(use_cache=True, kctx_context="", kctx_stable="S", kctx_volatile="",
                wm_pinned=None, system_prompt=None, tail_blocks=[])
    base.update(kw)
    return build_system_message(**base)


# ── plain path ───────────────────────────────────────────────────────────────
def test_plain_full_order():
    out = _plain(kctx_context="CTX", wm_pinned="WM", system_prompt="SYS", tail_blocks=TAIL)
    assert out == "\n\n".join(["CTX", "WM", "SYS", *TAIL])


def test_plain_empty_is_none():
    assert _plain() is None
    # whitespace-only grounding + system_prompt collapse away; no blocks → None
    assert _plain(kctx_context="   ", system_prompt="  ") is None


def test_plain_skips_absent_and_falsy_tail():
    out = _plain(kctx_context="CTX", tail_blocks=["steering", None, "", "skillmeta"])
    assert out == "CTX\n\nsteering\n\nskillmeta"


def test_plain_strips_grounding_and_system_but_not_wm():
    # grounding + system_prompt are .strip()'d; wm_pinned is verbatim (matches the ladder)
    out = _plain(kctx_context="  CTX  ", wm_pinned="  WM  ", system_prompt="  SYS  ")
    assert out == "CTX\n\n  WM  \n\nSYS"


# ── cache path ───────────────────────────────────────────────────────────────
def test_cache_stable_only():
    assert _cache(kctx_stable="  S  ") == [
        {"type": "text", "text": "S", "cache_control": {"type": "ephemeral"}}
    ]


def test_cache_full_order_and_flags():
    out = _cache(kctx_stable="S", kctx_volatile="V", wm_pinned="WM",
                 system_prompt="SYS", tail_blocks=TAIL)
    assert out[0] == {"type": "text", "text": "S", "cache_control": {"type": "ephemeral"}}
    assert out[1] == {"type": "text", "text": "V"}            # volatile: uncached
    assert out[2] == {"type": "text", "text": "WM"}           # wm_pinned: uncached, verbatim
    assert out[3] == {"type": "text", "text": "SYS", "cache_control": {"type": "ephemeral"}}
    # every tail block is cacheable, in order
    assert [p["text"] for p in out[4:]] == TAIL
    assert all(p["cache_control"] == {"type": "ephemeral"} for p in out[4:])
    assert len(out) == 4 + len(TAIL)


def test_cache_omits_empty_volatile_and_falsy():
    out = _cache(kctx_stable="S", kctx_volatile="   ", wm_pinned=None,
                 system_prompt="   ", tail_blocks=["steering", None, ""])
    # volatile whitespace-only → skipped; wm None → skipped; system whitespace → skipped;
    # only stable + the one real tail block
    assert [p["text"] for p in out] == ["S", "steering"]
