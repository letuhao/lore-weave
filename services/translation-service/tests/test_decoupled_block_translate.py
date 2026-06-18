"""Phase 2b-T3a — pure state-machine coverage for the decoupled BLOCK translate
engine. The DB/SDK shell + consumer are covered by the live-smoke; here we lock the
resumable transitions: per-batch accept/retry (the validate→correction loop), the
final-attempt failed-block accounting, reassembly, and the memo."""

from app.workers import decoupled_block_translate as d


def _para(text: str) -> dict:
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


def _rs(n_batches: int = 1, max_retries: int = 2) -> dict:
    batches = [
        {
            "block_indices": [i],
            "combined": f"[BLOCK {i}]\nsrc{i}",
            "input_texts": {str(i): f"src{i}"},
            "token_estimate": 10,
        }
        for i in range(n_batches)
    ]
    rs = d.new_block_resume_state(
        blocks=[_para(f"src{i}") for i in range(n_batches)],
        batches=batches, glossary_prompt_block="", glossary_correction_map={},
        source_lang="zh", target_code="vi", translatable_count=n_batches,
        max_retries=max_retries, extra_system="",
    )
    return rs


def test_new_state_defaults():
    rs = _rs(2)
    assert rs["mode"] == "block"
    assert rs["batch_idx"] == 0 and rs["attempt"] == 0
    assert rs["translated_texts"] == {} and rs["failed_blocks"] == []
    assert rs["awaiting"] == "translate_batch"


def test_decide_translate_then_finalize():
    rs = _rs(1)
    assert d.decide_block_action(rs) == ("translate_batch", 0, 0)
    rs["batch_idx"] = 1
    assert d.decide_block_action(rs) == ("finalize",)


def test_apply_valid_accepts_and_advances():
    rs = _rs(2)
    out = d.apply_batch_result(rs, parsed={0: "dịch0"}, in_tok=5, out_tok=3,
                               valid=True, errors=[])
    assert out["translated_texts"] == {"0": "dịch0"}
    assert out["batch_idx"] == 1 and out["attempt"] == 0
    assert out["correction_hint"] == ""
    assert out["total_input"] == 5 and out["total_output"] == 3
    assert out["rolling_summary"]  # non-empty
    # pure: input untouched
    assert rs["batch_idx"] == 0 and rs["translated_texts"] == {}


def test_apply_invalid_with_attempts_left_retries_same_batch():
    rs = _rs(1, max_retries=2)
    out = d.apply_batch_result(rs, parsed={}, in_tok=1, out_tok=1,
                               valid=False, errors=["missing_blocks: [0]"])
    assert out["batch_idx"] == 0          # NOT advanced
    assert out["attempt"] == 1            # bumped
    assert "missing_blocks" in out["correction_hint"]
    assert out["translated_texts"] == {}  # nothing merged on a retry


def test_apply_invalid_final_attempt_accepts_partial_and_records_failed():
    rs = _rs(1, max_retries=1)
    rs["attempt"] = 1  # last attempt (attempts_left = 1 < 1 is False)
    out = d.apply_batch_result(rs, parsed={}, in_tok=1, out_tok=1,
                               valid=False, errors=["missing_blocks: [0]"])
    assert out["batch_idx"] == 1          # advanced (gave up)
    assert out["failed_blocks"] == [0]    # block 0 never parsed → failed
    assert out["attempt"] == 0


def test_reassemble_uses_translation_or_original():
    rs = _rs(2)
    rs["translated_texts"] = {"0": "dịch0"}   # block 1 never translated
    blocks, count = d.reassemble_blocks(rs)
    assert count == 1
    # block 0 rebuilt with the translation; block 1 kept original src1
    assert "dịch0" in str(blocks[0])
    assert "src1" in str(blocks[1])


def test_memo_is_translated_only_in_order():
    rs = _rs(3)
    rs["translated_texts"] = {"2": "c", "0": "a", "1": ""}
    # ordered by int key, empty skipped
    assert d.memo_from_translated(rs) == "a\nc"


def test_build_messages_first_attempt_vs_retry():
    rs = _rs(1)
    first = d.build_batch_messages(rs)
    assert first[0]["role"] == "system"
    assert "Translate the following" in first[-1]["content"]
    # retry: a correction_hint replaces the plain user content
    rs["attempt"] = 1
    rs["correction_hint"] = "Your previous output had errors: missing_blocks: [0]."
    retry = d.build_batch_messages(rs)
    assert any("fix the output" in m["content"] for m in retry)
    assert "previous output had errors" in retry[-1]["content"]


def test_full_two_batch_sequence():
    rs = _rs(2)
    assert d.decide_block_action(rs) == ("translate_batch", 0, 0)
    rs = d.apply_batch_result(rs, {0: "t0"}, 1, 1, valid=True, errors=[])
    assert d.decide_block_action(rs) == ("translate_batch", 1, 0)
    rs = d.apply_batch_result(rs, {1: "t1"}, 1, 1, valid=True, errors=[])
    assert d.decide_block_action(rs) == ("finalize",)
    assert rs["translated_texts"] == {"0": "t0", "1": "t1"}
    blocks, count = d.reassemble_blocks(rs)
    assert count == 2 and d.memo_from_translated(rs) == "t0\nt1"
