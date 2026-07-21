"""Streaming reasoning-loop detector (D-REASONING-LOOP).

The incident this exists for: on a "rewrite the description" ask, a mid-tier
local model (Gemma-4 26B) fell into an INFINITE reasoning-channel loop,
oscillating between two tool choices —

    Actually, I'll try to use book_update_meta first.
    Wait, I'll try to use propose_record_edit with the book_id and see if it works.
    Actually, I'll try to use book_update_meta first.
    Wait, ...                                         (×30+, no tool call emitted)

Every existing loop-breaker (``blank_tool_args_streak``, ``REPEAT_READ_CAP``,
``TOOL_LIST_CATEGORY_CAP``, the planner-call cap) fires in the TOOL-CALL loop,
on an EMITTED call. A model that thrashes in the *reasoning stream* without
emitting a call increments none of them — so it hangs until the user hits Stop.

This detector watches the streamed text itself. It is a defense-in-depth net:
even a perfectly disambiguated tool surface can loop, and a provider stream we
consume (lm_studio/llama.cpp) exposes no sampler-level ``no_repeat_ngram_size``
to us per call. So we detect at the app layer, provider-agnostic.

Algorithm (all stdlib, O(1) amortized per segment):
  * split the incoming deltas into normalized *segments* (a line, or a
    sentence within a long line) — normalization folds case + whitespace so a
    paraphrase-free repeat with trivial spacing differences still matches;
  * keep a bounded window (``deque``) of recent segment strings;
  * trip when EITHER
      (a) one segment recurs >= ``repeat_threshold`` times in the window
          (a stuck single line), OR
      (b) the tail is a length-``p`` block repeated >= ``cycle_repeats`` times
          (a period-``p`` cycle — the "Actually…/Wait…" oscillation is p=2).

Only *substantial* segments count (>= ``min_segment_len`` after normalization),
so short filler ("ok.", blank lines, a lone bullet) never trips it.
"""

from __future__ import annotations

import re
from collections import Counter, deque

# Segment boundary: a newline, or a sentence end (``. `` / ``.\n`` / ``? `` / ``! ``).
# We split on sentence ends too so a loop streamed as one long line (no newlines)
# is still decomposed into the repeating units.
_SEGMENT_BOUNDARY = re.compile(r"[^\n.?!]*[\n.?!]+")


def _normalize(seg: str) -> str:
    """Fold case + collapse whitespace + drop punctuation/markdown so two
    segments that differ only cosmetically hash equal. Inline ``code`` backticks
    and *emphasis* asterisks are removed GLOBALLY (not just trimmed) because the
    model varies them between otherwise-identical repeats; list/quote markers are
    trimmed from the ends."""
    s = seg.lower().replace("`", "").replace("*", "")
    s = " ".join(s.split())
    return s.strip("_-#>.\"' \t")


class ReasoningLoopDetector:
    """Feed streamed reasoning/content deltas; ``feed`` returns True the first
    time a degenerate loop is detected. Stateful and single-purpose — construct
    one per model pass (or per turn) and discard on trip."""

    def __init__(
        self,
        *,
        window: int = 24,
        repeat_threshold: int = 4,
        max_period: int = 4,
        cycle_repeats: int = 3,
        min_segment_len: int = 6,
    ) -> None:
        if repeat_threshold < 2:
            raise ValueError("repeat_threshold must be >= 2")
        if cycle_repeats < 2:
            raise ValueError("cycle_repeats must be >= 2")
        self._window = window
        self._repeat_threshold = repeat_threshold
        self._max_period = max_period
        self._cycle_repeats = cycle_repeats
        self._min_segment_len = min_segment_len
        self._buf = ""
        self._segments: deque[str] = deque(maxlen=window)
        self._counts: Counter[str] = Counter()
        self._tripped = False
        self._reason = ""

    @property
    def tripped(self) -> bool:
        return self._tripped

    @property
    def reason(self) -> str:
        """A short human/log reason for the trip (empty until tripped)."""
        return self._reason

    def feed(self, delta: str) -> bool:
        """Consume a stream delta. Returns True once (and stays True) when a loop
        is detected. Cheap to keep calling after a trip — it short-circuits."""
        if self._tripped:
            return True
        if not delta:
            return False
        self._buf += delta
        for seg in self._drain_complete_segments():
            norm = _normalize(seg)
            if len(norm) < self._min_segment_len:
                continue
            self._push(norm)
            if self._detect():
                self._tripped = True
                return True
        return False

    # ── internals ────────────────────────────────────────────────────────────

    def _drain_complete_segments(self) -> list[str]:
        """Pull every COMPLETE segment out of the buffer, leaving the trailing
        incomplete fragment (no terminator yet) for the next feed."""
        out: list[str] = []
        last_end = 0
        for m in _SEGMENT_BOUNDARY.finditer(self._buf):
            out.append(m.group())
            last_end = m.end()
        if last_end:
            self._buf = self._buf[last_end:]
        return out

    def _push(self, norm: str) -> None:
        if len(self._segments) == self._segments.maxlen:
            evicted = self._segments[0]  # deque will drop this on append
            self._counts[evicted] -= 1
            if self._counts[evicted] <= 0:
                del self._counts[evicted]
        self._segments.append(norm)
        self._counts[norm] += 1

    def _detect(self) -> bool:
        # (a) a single segment stuck on repeat
        norm = self._segments[-1]
        if self._counts[norm] >= self._repeat_threshold:
            self._reason = f"segment repeated {self._counts[norm]}x: {norm[:60]!r}"
            return True
        # (b) a period-p cycle at the tail: last (cycle_repeats * p) segments are
        # the length-p block repeated. p=2 catches the Actually/Wait oscillation.
        n = len(self._segments)
        segs = self._segments
        for p in range(1, self._max_period + 1):
            need = self._cycle_repeats * p
            if n < need:
                continue
            block = list(segs)[-p:]
            tail = list(segs)[-need:]
            if all(tail[i] == block[i % p] for i in range(need)):
                # Require the block to carry signal (not the same one segment,
                # which (a) already handles) — a period>=2 with >=2 distinct segs.
                if p == 1:
                    self._reason = (
                        f"segment repeated {self._cycle_repeats}x consecutively: "
                        f"{block[0][:60]!r}"
                    )
                    return True
                if len(set(block)) >= 2:
                    self._reason = (
                        f"period-{p} cycle x{self._cycle_repeats}: "
                        f"{' | '.join(b[:40] for b in block)}"
                    )
                    return True
        return False
