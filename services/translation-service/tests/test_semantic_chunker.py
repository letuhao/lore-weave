"""M3 (G5): V3 semantic chunker — dialogue/scene-aware grouping + group-aware batching."""
from app.workers.v3.semantic_chunker import tag_groups, _has_dialogue
from app.workers.block_batcher import build_batch_plan


def _para(text: str) -> dict:
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


def _heading(text: str) -> dict:
    return {"type": "heading", "attrs": {"level": 1},
            "content": [{"type": "text", "text": text}]}


def _hr() -> dict:
    return {"type": "horizontalRule"}


# ── _has_dialogue ─────────────────────────────────────────────────────────────

def test_has_dialogue_cjk_brackets():
    assert _has_dialogue("「你好」")
    assert _has_dialogue("『古文』")


def test_has_dialogue_curly_and_straight_quotes():
    assert _has_dialogue("“hello”")
    assert _has_dialogue('she said "hi"')


def test_has_dialogue_leading_dash():
    assert _has_dialogue("— Xin chào, anh ấy nói.")
    assert _has_dialogue("  – leading en dash")


def test_has_dialogue_negative():
    assert not _has_dialogue("just plain narration text")
    assert not _has_dialogue("")
    # a dash mid-sentence is not a dialogue lead
    assert not _has_dialogue("a well-known fact")


# ── tag_groups ──────────────────────────────────────────────────────────────—

def test_tag_groups_paragraph_cluster_shares_gid():
    blocks = [_para("one"), _para("two"), _para("three")]
    assert tag_groups(blocks) == {0: 0, 1: 0, 2: 0}


def test_tag_groups_dialogue_run_is_atomic_and_separate():
    blocks = [_para("narration"), _para("「talk」"), _para("「more」"), _para("narration again")]
    groups = tag_groups(blocks)
    # paragraph, then a dialogue run (same gid), then a new paragraph cluster
    assert groups == {0: 0, 1: 1, 2: 1, 3: 2}


def test_tag_groups_scene_boundaries_increment():
    blocks = [_para("body"), _heading("Chapter 2"), _para("new scene"),
              _hr(), _para("after break")]
    groups = tag_groups(blocks)
    assert groups == {0: 0, 1: 1, 2: 2, 3: 3, 4: 4}


def test_tag_groups_consecutive_scene_blocks_split():
    # heading immediately followed by a horizontalRule → two distinct groups
    blocks = [_heading("Title"), _hr(), _para("text")]
    assert tag_groups(blocks) == {0: 0, 1: 1, 2: 2}


# ── group-aware build_batch_plan ──────────────────────────────────────────────
# Legacy budget path (no langs): max_tokens = max(int(context*0.25), 100). With
# context=200 the 100-token floor applies. Each 160-char latin block ≈ 40 tokens
# + ~4 marker overhead ≈ 44; two fit per 100-token batch (≈89), a third overflows.

_BIG = "x" * 160  # ~40 latin tokens


def test_group_aware_keeps_dialogue_run_together():
    blocks = [_para(_BIG), _para("「" + _BIG + "」"), _para("「" + _BIG + "」")]
    group_ids = tag_groups(blocks)  # {0:0, 1:1, 2:1}

    plain = build_batch_plan(blocks, context_window_tokens=200)
    grouped = build_batch_plan(blocks, context_window_tokens=200, group_ids=group_ids)

    # Plain greedy packs [0,1] then splits the dialogue run → block 2 alone.
    plain_idx = [b.block_indices for b in plain.batches]
    assert plain_idx == [[0, 1], [2]]

    # Group-aware flushes before the dialogue group → [0] then [1,2] together.
    grouped_idx = [b.block_indices for b in grouped.batches]
    assert grouped_idx == [[0], [1, 2]]


def test_group_larger_than_budget_falls_back_to_greedy():
    # A dialogue group of 3 blocks (~72 tok) exceeds a full batch (50) → no
    # forced flush; greedy splitting handles it (the §3 fallback).
    blocks = [_para(_BIG)] + [_para("「" + _BIG + "」") for _ in range(3)]
    group_ids = tag_groups(blocks)  # {0:0, 1:1, 2:1, 3:1}
    plan = build_batch_plan(blocks, context_window_tokens=200, group_ids=group_ids)
    idx = [b.block_indices for b in plan.batches]
    # group too big to keep whole → it still splits across batches
    assert sum(len(b) for b in idx) == 4
    assert len(idx) >= 2


def test_group_ids_none_is_parity():
    blocks = [_para(_BIG), _para("「" + _BIG + "」"), _para("「" + _BIG + "」")]
    omitted = build_batch_plan(blocks, context_window_tokens=200)
    explicit_none = build_batch_plan(blocks, context_window_tokens=200, group_ids=None)
    assert [b.block_indices for b in omitted.batches] == \
           [b.block_indices for b in explicit_none.batches]
