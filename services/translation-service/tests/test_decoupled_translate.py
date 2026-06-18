"""Phase 2b-T2 — pure state-machine coverage for the decoupled text translate
engine. The DB/SDK shell + consumer are covered by the live-smoke; here we lock
the resumable state transitions (incl. compaction) that drive correctness."""

from app.workers import decoupled_translate as d


def _msg() -> dict:
    return {"target_language": "vi", "model_source": "user_model", "model_ref": "m", "user_id": "u"}


def test_new_resume_state():
    rs = d.new_resume_state(["a", "b"], "Chinese")
    assert rs["chunks"] == ["a", "b"]
    assert rs["chunk_idx"] == 0
    assert rs["session_history"] == []
    assert rs["compact_memo"] == ""
    assert rs["translated_parts"] == []
    assert rs["awaiting"] == "translate"
    assert rs["source_lang"] == "Chinese"


def test_decide_translate_when_history_small():
    rs = d.new_resume_state(["a", "b"], "zh")
    assert d.decide_next_action(rs, context_window=8192) == ("translate", 0)


def test_decide_finalize_when_all_chunks_done():
    rs = d.new_resume_state(["a"], "zh")
    rs["chunk_idx"] = 1  # past the last chunk
    assert d.decide_next_action(rs, context_window=8192) == ("finalize",)


def test_decide_compact_when_history_exceeds_half_context():
    rs = d.new_resume_state(["a", "b"], "zh")
    # A tiny context window so a modest history exceeds half.
    rs["session_history"] = [{"role": "assistant", "content": "x " * 500}]
    assert d.decide_next_action(rs, context_window=100) == ("compact",)


def test_apply_translate_result_advances_and_accumulates():
    rs = d.new_resume_state(["chunk-0", "chunk-1"], "zh")
    out = d.apply_translate_result(rs, "dịch-0", in_tok=10, out_tok=5, msg=_msg())
    assert out["translated_parts"] == ["dịch-0"]
    assert out["total_input"] == 10
    assert out["total_output"] == 5
    assert out["chunk_idx"] == 1
    # session history gained a user + assistant exchange
    assert len(out["session_history"]) == 2
    assert out["session_history"][1] == {"role": "assistant", "content": "dịch-0"}
    # input rs is untouched (pure)
    assert rs["chunk_idx"] == 0 and rs["translated_parts"] == []


def test_apply_compact_result_sets_memo_and_resets_history():
    rs = d.new_resume_state(["a"], "zh")
    rs["session_history"] = [{"role": "user", "content": "x"}]
    out = d.apply_compact_result(rs, "MEMO-v1")
    assert out["compact_memo"] == "MEMO-v1"
    assert out["session_history"] == []
    assert rs["session_history"] != []  # pure: input untouched


def test_full_two_chunk_no_compaction_sequence():
    # translate(0) -> apply -> translate(1) -> apply -> finalize
    rs = d.new_resume_state(["c0", "c1"], "zh")
    assert d.decide_next_action(rs, 8192) == ("translate", 0)
    rs = d.apply_translate_result(rs, "t0", 1, 1, _msg())
    assert d.decide_next_action(rs, 8192) == ("translate", 1)
    rs = d.apply_translate_result(rs, "t1", 1, 1, _msg())
    assert d.decide_next_action(rs, 8192) == ("finalize",)
    assert rs["translated_parts"] == ["t0", "t1"]
    assert "\n\n".join(rs["translated_parts"]) == "t0\n\nt1"


def test_compaction_then_translate_sequence():
    # After a chunk pushes history over half context, decide=compact; after the
    # compact result, history resets and decide=translate again.
    rs = d.new_resume_state(["c0", "c1"], "zh")
    rs = d.apply_translate_result(rs, "x " * 500, 1, 1, _msg())  # huge output
    assert rs["chunk_idx"] == 1
    assert d.decide_next_action(rs, context_window=100) == ("compact",)
    rs = d.apply_compact_result(rs, "MEMO")
    # history reset → not over half → translate the next chunk
    assert d.decide_next_action(rs, context_window=100) == ("translate", 1)
    assert rs["compact_memo"] == "MEMO"
