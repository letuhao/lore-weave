"""Prompt-injection DETECTION for translation, where mutating the text is not an option.

Why translation cannot use the composition defence
--------------------------------------------------
Composition's `packer/sanitize.py` neutralises untrusted text: it fullwidth-escapes `<`/`>`
so injected text cannot forge an assembly delimiter, and wraps directive-looking spans in
`⟦…⟧` so the model reads them as data. That is right for a retrieved lore passage, which is
CONTEXT the model consults.

In translation the untrusted text is the PRODUCT. A chapter of an imported novel is the thing
being translated, and every one of those transformations corrupts it:

  · escaping `<`/`>` changes characters the translation must round-trip;
  · bracketing a directive span writes editing marks into the output — and "you are now the
    head of this house" is dialogue, not an attack;
  · even the pre-normalisation (NFKC + invisible-strip) that the neutralisers apply is a
    silent rewrite of the author's text.

Composition already learned half of this: `sanitize_prose_context` exists precisely because
bracketing was wrong for prose it feeds back to itself. Translation needs the other half —
for the source text, the correct defence mutates NOTHING.

What this does instead
----------------------
Detect and report. `scan_injection` returns spans without touching the text, so a caller can:

  · record that a chapter carries directive-looking spans, on the job and in the logs;
  · surface it to the human who imported the book;

…while translating it faithfully. Refusing to translate a chapter because it contains the
words "system prompt" would break a novel about an AI, and a guard that fires on ordinary
fiction gets switched off.

This is a WEAKER guarantee than neutralisation and it is labelled as one:
`scripts/injection-coverage-lint.py` scores a module as DETECT-covered rather than
MUTATE-covered, so nobody reads a translation module's coverage as the same promise a
composition module makes.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from loreweave_grounding.sanitize import scan_injection

logger = logging.getLogger(__name__)

__all__ = ["InjectionReport", "record_source_injection", "scan_untrusted_source"]


@dataclass(frozen=True)
class InjectionReport:
    """What a scan found in one untrusted string. Never carries the text itself."""

    hits: int = 0
    #: The distinct pattern names that matched, sorted. Names, not spans: this rides a job
    #: record and a log line, and an offset into text nobody kept is not actionable.
    patterns: tuple[str, ...] = ()

    @property
    def clean(self) -> bool:
        return self.hits == 0

    def as_payload(self) -> dict:
        """The shape a job result / event carries. Emitted even when clean.

        Deliberately not omitted-when-empty. "No injection found" and "nobody looked" are
        different facts, and this run has spent its whole length on the difference — a field
        that only appears on a hit makes them identical for every ordinary chapter.
        """
        return {"scanned": True, "hits": self.hits, "patterns": list(self.patterns)}


def scan_untrusted_source(text: str | None, *, where: str) -> InjectionReport:
    """Scan imported text for directive-looking spans. Returns; never raises, never mutates.

    `where` names the call site for the log line — a warning that cannot say which chapter
    it came from is noise.
    """
    try:
        hits = scan_injection(text)
    except Exception:  # pragma: no cover - a detector must never break a translation
        # A scan that raises must not take the translation down with it. This is a REPORT,
        # not a gate, so the failure mode is a missing report — logged, so it is not silent.
        logger.exception("injection scan failed at %s", where)
        return InjectionReport()
    if not hits:
        return InjectionReport()
    patterns = tuple(sorted({name for name, _start, _end in hits}))
    logger.warning(
        "untrusted source carries %d directive-looking span(s) at %s: %s "
        "(translated faithfully; NOT modified)",
        len(hits), where, ", ".join(patterns),
    )
    return InjectionReport(hits=len(hits), patterns=patterns)


async def record_source_injection(pool, chapter_translation_id, text: str | None):
    """Scan a chapter's imported source AND write the count where a human will see it.

    Why the two halves are one function
    -----------------------------------
    They were two, and the live stack proved what that costs. `scan_untrusted_source` was
    called on FIVE chapter paths and the number was persisted on TWO — and the path this
    platform actually runs for a structured chapter (the DECOUPLED BLOCK pipeline, and the V3
    pipeline that delegates to it) was one of the three that only logged. A real translation
    of a chapter carrying `ignore all previous instructions` finished with the log line

        untrusted source carries 1 directive-looking span(s) at block_translate:blocks[0..3]

    and `source_injection_hits = NULL` on the row the importer reads: the detector fired, the
    telling did not, and every unit test was green because each half was tested where it lived.

    Detection is not a defence until somebody is told, so the scan and the telling are now the
    same call and a path cannot take one without the other. `tests/test_injection_persist.py`
    holds the denominator: it derives the chapter entry points from `chapter_worker`'s own
    dispatch, so a SIXTH path fails rather than joining the silent three.

    Written even when clean (`0`), because `0` and `NULL` answer different questions —
    "scanned, nothing found" versus "nobody looked" — and the column is nullable to keep them
    apart. Returns the report so a caller can also ride it on `resume_state`.
    """
    report = scan_untrusted_source(text, where=f"chapter_translation:{chapter_translation_id}")
    await pool.execute(
        "UPDATE chapter_translations SET source_injection_hits=$2 WHERE id=$1",
        chapter_translation_id, report.hits,
    )
    return report
