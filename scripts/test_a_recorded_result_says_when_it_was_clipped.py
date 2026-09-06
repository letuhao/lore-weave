"""D-RECORDED-TOOL-RESULTS-ARE-TRUNCATED-AT-4000-CHARS.

fe_runner recorded `str(ev.get("content"))[:4000]` and said nothing about it.

    THE INVARIANT. A recorded value that was truncated must say so, and by how much.
    A truncation that does not announce itself is indistinguishable from data.

MEASURED OVER EVERY RAW RECORD ON DISK, 2026-08-27:

    4,690  tool results recorded
      676  sit at exactly 4000 characters and end mid-token   (14.4%)
      676  of those fail json.loads                           (100% of them)

So every sweep this loop ran that PARSED a result was under-counting by 14%, and always in
the direction that looks like a finding: an empty parse reads as "the tool returned nothing",
not as "the recording is clipped". It cost two false provenance defects, both refuted by
hand — kg_build's project_id "from kg_project_list on 0 of 10 runs", and
composition_arc_apply's arc_template_id "on 0 of 5". The clipped tools are the list tools:
kg_project_list 190, world_list 97, settings_list_models 97,
glossary_list_system_standards 83, composition_motif_search 64.

THE ROW'S OPEN QUESTION IS SETTLED, AND IT IS THE INSTRUMENT. `stream_events.tool_call_result`
builds its content with a plain `json.dumps` and no cap, and chat-service has no 4000 anywhere
near a tool result — so the MODEL saw the whole thing and only the recording was clipped. The
suspiciously round 4000 was fe_runner's own literal.

THE CAP IS NOT THE FIX, THE ANNOUNCEMENT IS. A cap can always be exceeded. `content_length` is
recorded whether or not it clipped, and `parsed_result()` REFUSES a clipped record instead of
raising a JSONDecodeError an analysis will catch and read as emptiness.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

import fe_runner as fr  # noqa: E402


def test_the_cap_clears_every_result_these_tools_actually_return():
    """Measured live 2026-08-27 against the tools whose results clip most. The cap is an order
    of magnitude above the largest, so today's whole population records COMPLETE."""
    largest_measured = 23_390          # composition_arc_template_list
    assert fr.RESULT_CAP >= 10 * largest_measured
    assert fr.RESULT_CAP > fr._LEGACY_CAP * 40


def test_the_recorder_writes_the_TRUE_length():
    """🔴 THE CALL SITE, and the durable half. Raising the cap alone would move the cliff, not
    remove it — the next result past it would be silently clipped exactly as before."""
    src = (ROOT / "scripts" / "toolloop" / "fe_runner.py").read_text(encoding="utf-8")
    at = src.index('out["results"].append(')
    seg = src[at:at + 500]
    assert '"content_length": len(_content)' in seg, "the true length is not recorded"
    assert '"truncated": len(_content) > RESULT_CAP' in seg
    assert "[:RESULT_CAP]" in seg, "the cap is still a literal at the call site"
    assert "[:4000]" not in src, "the old literal cap is still somewhere in the recorder"


def test_a_complete_result_parses():
    assert fr.parsed_result(
        {"content": '{"ok": true}', "content_length": 12, "truncated": False}) == {"ok": True}


def test_a_clipped_result_is_REFUSED_not_returned_empty():
    """The whole point. A JSONDecodeError gets caught by an analysis and read as emptiness;
    this raises something that names the cause and the size."""
    with pytest.raises(fr.TruncatedResult, match="clipped at"):
        fr.parsed_result({"content": "x" * 50, "content_length": 999_999, "truncated": True})


def test_a_LEGACY_record_is_refused_too():
    """676 landmines are already on disk with no length field. A record of exactly the old cap
    is the signature of a clip, and refusing is the safe direction: the caller is told to
    re-run rather than told a number."""
    with pytest.raises(fr.TruncatedResult, match="predates the length field"):
        fr.parsed_result({"content": "y" * fr._LEGACY_CAP})


def test_a_legacy_record_that_is_merely_SHORT_still_parses():
    """PRECISION. The legacy rule keys on the exact old cap, not on 'large' — flagging every
    long result would make the refusal useless."""
    assert fr.parsed_result({"content": '{"a": ' + '"' + "z" * 3000 + '"}'}) is not None


def test_the_landmines_are_still_on_disk_and_the_reader_names_them():
    """ANTI-VACUITY against the real corpus. If the recorded population had no clipped results
    this file would be guarding nothing — and the reader must refuse them, not parse them."""
    clipped = []
    for f in sorted((ROOT / "docs" / "eval" / "toolloop").rglob("*-raw.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, list):
            continue
        for r in d:
            for res in (r.get("results") or []) if isinstance(r, dict) else []:
                if len(res.get("content") or "") == fr._LEGACY_CAP and "content_length" not in res:
                    clipped.append(res)
    assert len(clipped) >= 100, f"only {len(clipped)} clipped records found — re-derive"
    for res in clipped[:25]:
        with pytest.raises(fr.TruncatedResult):
            fr.parsed_result(res)


def test_the_wire_itself_is_NOT_capped():
    """The row asked whether the MODEL saw the truncated text too — 'very different defects'.
    It did not: the emitter json.dumps the whole result. Pinned, because a cap appearing there
    later would make this file's premise false and its conclusion wrong."""
    src = (ROOT / "services" / "chat-service" / "app" / "services" / "stream_events.py").read_text(
        encoding="utf-8")
    at = src.index('"type": "TOOL_CALL_RESULT"')
    body = src[src.rindex("if tc.get(\"ok\"):", 0, at):at]
    assert 'json.dumps({"ok": True, "result": tc.get("result")})' in body
    assert "[:" not in body, f"the emitter now slices the content: {body!r}"
