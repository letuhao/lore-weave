"""T2-M1 pure segmentation unit tests."""
from app.workers.segmentation import segment_blocks, segment_source_hash


def blk(i, text, btype="paragraph", h=None):
    return {"block_index": i, "block_type": btype, "text_content": text, "content_hash": h or f"h{i}"}


def test_small_chapter_is_one_segment():
    segs = segment_blocks([blk(0, "a"), blk(1, "b")], max_tokens=2000)
    assert len(segs) == 1
    assert (segs[0].start_block_index, segs[0].end_block_index) == (0, 1)
    assert segs[0].block_hashes == ["h0", "h1"]
    assert segs[0].segment_text == "a\n\nb"


def test_groups_contiguously_until_cap():
    big = "字" * 30  # ~20 tokens (CJK 1.5 chars/token)
    blocks = [blk(i, big) for i in range(5)]
    segs = segment_blocks(blocks, max_tokens=40)  # ~2 blocks/segment
    assert len(segs) >= 2
    # every block covered exactly once, in order, no gaps
    covered = []
    for s in segs:
        covered += list(range(s.start_block_index, s.end_block_index + 1))
    assert covered == [0, 1, 2, 3, 4]
    assert [s.segment_index for s in segs] == list(range(len(segs)))


def test_heading_starts_a_new_segment():
    blocks = [blk(0, "para0"), blk(1, "Title", btype="heading"), blk(2, "para2")]
    segs = segment_blocks(blocks, max_tokens=2000)
    assert len(segs) == 2
    assert segs[0].end_block_index == 0          # para0 flushed at the heading
    assert segs[1].start_block_index == 1         # heading opens the next segment
    assert segs[1].end_block_index == 2


def test_oversized_single_block_stays_whole():
    huge = "字" * 9000  # ~6000 tokens, far over the cap
    segs = segment_blocks([blk(0, huge)], max_tokens=2000)
    assert len(segs) == 1
    assert (segs[0].start_block_index, segs[0].end_block_index) == (0, 0)


def test_empty_blocks_yield_no_segments():
    assert segment_blocks([], max_tokens=2000) == []


def test_source_hash_is_stable_and_content_sensitive():
    s_x1 = segment_blocks([blk(0, "a", h="X")], 2000)[0]
    s_x2 = segment_blocks([blk(0, "a", h="X")], 2000)[0]
    s_y = segment_blocks([blk(0, "a", h="Y")], 2000)[0]
    assert segment_source_hash(s_x1) == segment_source_hash(s_x2)
    assert segment_source_hash(s_x1) != segment_source_hash(s_y)  # block change → re-segment
