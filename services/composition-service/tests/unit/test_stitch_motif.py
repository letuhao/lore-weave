"""W-STITCH (§17.2, R2.7) — motif-library STITCH enhancements.

Covers the five R2.7 deltas layered on the chapter stitch pass:
  1. cross-scene repetition signal (n-gram/shingle overlap at scene boundaries)
  2. dial-respect (voice/style preserved; seams smoothed, prose NOT homogenized)
  3. ≤2-scene over-resolve detection (a beat the next scene must still do)
  4. overlapping-window boundary analysis (each join seen with both neighbours)
  5. eval-gate — repetition reduced WITHOUT flattening (non-regression)

These exercise the in-code signal (pure, no LLM) plus the prompt-threading into
``stitch_chapter`` via a fake LLM that echoes the prompt it received, so we can
assert the findings + preservation directive actually reach the model.
"""

from __future__ import annotations

from app.engine.stitch import (
    _RepetitionFinding,
    boundary_windows,
    detect_over_resolve,
    repetition_findings,
    stitch_chapter,
)
from app.packer.profile import NEUTRAL, BookProfile


# ── overlapping-window boundaries (pure) ──

def test_boundary_windows_each_interior_scene_in_two_windows():
    # 4 scenes → 3 boundaries; scene index 1 and 2 each appear in two windows.
    wins = boundary_windows(4)
    assert wins == [(0, 1), (1, 2), (2, 3)]


def test_boundary_windows_single_scene_has_no_boundary():
    assert boundary_windows(1) == []
    assert boundary_windows(0) == []


# ── repetition signal (pure, no LLM) ──

def test_repetition_finding_detects_echoed_phrase_across_boundary():
    # Scene 1 ends introducing the lighthouse; scene 2 re-introduces it verbatim.
    s1 = "They walked all day. The old stone lighthouse stood against the grey sky."
    s2 = "The old stone lighthouse stood against the grey sky. She climbed the stair."
    findings = repetition_findings([s1, s2], shingle_k=4)
    assert findings, "expected a cross-boundary repetition finding"
    f = findings[0]
    assert isinstance(f, _RepetitionFinding)
    assert f.left_scene == 1 and f.right_scene == 2
    assert "lighthouse" in f.phrase.lower()


def test_repetition_no_finding_when_boundaries_distinct():
    s1 = "They walked all day under a hot sun across the cracked salt flats."
    s2 = "Night fell quickly and the harbour lamps blinked awake one by one."
    assert repetition_findings([s1, s2], shingle_k=4) == []


def test_repetition_only_compares_adjacent_boundaries_not_whole_scenes():
    # Identical phrase appears at the HEAD of s1 and HEAD of s3 (not at the
    # s1↔s2 or s2↔s3 boundary) → must NOT be flagged (we only look at seams).
    common = "the bell tower rang twice over the empty square at dawn"
    s1 = f"{common}. Then a long stretch of unrelated travel prose follows here."
    s2 = "A wholly different middle scene with its own distinct imagery entirely."
    s3 = f"{common}. And yet more unrelated closing prose that shares nothing else."
    assert repetition_findings([s1, s2, s3], shingle_k=5) == []


# ── ≤2-scene over-resolve detection (pure) ──

def test_detect_over_resolve_flags_completed_beat_reopened():
    s1 = "He finally forgave his brother, and the long feud was over at last."
    s2 = "He could not forgive his brother. The feud still gnawed at him."
    flags = detect_over_resolve([s1, s2])
    assert flags and flags[0].left_scene == 1 and flags[0].right_scene == 2


def test_detect_over_resolve_scoped_to_local_window_only():
    # A resolution in s1 with NO re-opening in the adjacent s2 → no flag.
    s1 = "She closed the door on that chapter of her life for good."
    s2 = "The next morning brought fresh bread and a quiet, ordinary kitchen."
    assert detect_over_resolve([s1, s2]) == []


# ── stitch_chapter prompt threading (fake LLM echoes prompt) ──

class _Job:
    def __init__(self, status, result):
        self.status = status
        self.result = result


class _EchoLLM:
    """Echoes the assembled user+system prompt back as the 'stitched' output so a
    test can assert what instructions reached the model."""

    def __init__(self):
        self.calls = []

    async def submit_and_wait(self, **kw):
        self.calls.append(kw)
        msgs = kw["input"]["messages"]
        joined = "\n".join(m["content"] for m in msgs)
        return _Job("completed", {"messages": [{"content": joined}], "finish_reason": "stop"})


async def _stitch(llm, drafts, profile=NEUTRAL, **over):
    kw = dict(user_id="u", model_source="user_model", model_ref="m",
              scene_drafts=drafts, chapter_intent="intent", profile=profile,
              max_tokens=2048, max_input_chars=10000)
    kw.update(over)
    return await stitch_chapter(llm, **kw)


async def test_stitch_injects_repetition_findings_into_prompt():
    llm = _EchoLLM()
    s1 = "They walked all day. The old stone lighthouse stood against the grey sky."
    s2 = "The old stone lighthouse stood against the grey sky. She climbed the stair."
    out, _ = await _stitch(llm, [s1, s2])
    # The echoed prompt must mention the de-dup finding so the LLM can act on it.
    assert "lighthouse" in out.lower()
    assert "repeat" in out.lower() or "echo" in out.lower()


async def test_stitch_threads_voice_preservation_directive():
    profile = BookProfile(voice="terse, hard-boiled noir", density_level=80)
    llm = _EchoLLM()
    out, _ = await _stitch(llm, ["a scene", "another scene"], profile=profile)
    # dial-respect: the voice + an explicit do-not-flatten guard must be present.
    assert "hard-boiled noir" in out
    low = out.lower()
    assert "voice" in low and ("not flatten" in low or "do not homogen" in low
                               or "preserve" in low)


# ── eval-gate: reduces repetition WITHOUT flattening ──

class _DedupLLM:
    """A controlled 'editor' fake modelling a real seam-aware de-dup: it reads the
    injected SEAM NOTES, and for each flagged repeated phrase drops the SECOND
    cross-boundary occurrence — but touches nothing else, so deliberate (un-flagged)
    content is preserved verbatim. This is exactly the advisory contract: the in-code
    signal points; the editor acts only on what was pointed at."""

    def __init__(self):
        self.calls = []

    async def submit_and_wait(self, **kw):
        self.calls.append(kw)
        import re
        user = kw["input"]["messages"][-1]["content"]
        # Extract the flagged phrases from the SEAM NOTES block.
        flagged = re.findall(r'their join: "([^"]+)"', user)
        bodies = re.split(r"\[SCENE \d+\]\n", user)
        bodies = [b.strip() for b in bodies
                  if b.strip() and not b.lower().startswith("chapter intent")
                  and not b.startswith("SEAM NOTES")]
        text = "\n\n".join(bodies)
        # Drop the 2nd occurrence of each flagged phrase (cross-boundary de-dup).
        for phrase in flagged:
            first = text.lower().find(phrase.lower())
            if first == -1:
                continue
            second = text.lower().find(phrase.lower(), first + len(phrase))
            if second != -1:
                text = text[:second] + text[second + len(phrase):]
        text = re.sub(r"\s+\.", ".", text)  # tidy a dangling space before a period
        return _Job("completed", {"messages": [{"content": text}], "finish_reason": "stop"})


def _count(haystack: str, needle: str) -> int:
    return haystack.lower().count(needle.lower())


async def test_eval_gate_reduces_seam_repetition_without_flattening():
    motif = "the old stone lighthouse stood against the grey sky"
    deliberate = "Grief is a lighthouse you keep walking back to."  # intentional motif echo
    s1 = f"They walked all day. {motif.capitalize()}. {deliberate}"
    s2 = f"{motif.capitalize()}. She climbed the spiralling stair to the lamp room."

    raw_concat = "\n\n".join([s1, s2])
    llm = _DedupLLM()
    stitched, _ = await _stitch(llm, [s1, s2])

    # 1) repetition REDUCED: the duplicated motif sentence at the seam collapses.
    assert _count(stitched, motif) < _count(raw_concat, motif)
    # 2) NON-FLATTEN: the deliberate (non-duplicate) motif line survives verbatim.
    assert deliberate in stitched
    # 3) NOT blander/shorter than dropping a whole scene: s2's unique content stays.
    assert "spiralling stair" in stitched
    # 4) a repetition finding was actually computed for this fixture.
    assert repetition_findings([s1, s2]) != []
