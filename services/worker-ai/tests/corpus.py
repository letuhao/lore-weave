"""Loader for the committed 20k-entity glossary corpus.

The corpus is real Wikipedia article titles + real redirect-derived aliases
(see `testdata/ATTRIBUTION.md`). It supplies the three properties synthetic
names cannot: nesting (`Bộ Cá chình` / `Cá chình`), Vietnamese diacritic
variants (`Borăscu` / `Borascu`), and CJK names with no whitespace — the case
where an ASCII word boundary means nothing.

It is COMMITTED rather than downloaded at test time on purpose: a scale test
gated on a 130 MB download gets skipped in CI and then rots.
"""

from __future__ import annotations

import gzip
import random
from functools import lru_cache
from pathlib import Path

CORPUS_PATH = Path(__file__).parent / "testdata" / "glossary_corpus_20k.tsv.gz"


@lru_cache(maxsize=1)
def load_corpus() -> tuple[tuple[str, tuple[str, ...]], ...]:
    """The whole corpus as the `(name, aliases)` shape `select_known_entities` takes."""
    rows: list[tuple[str, tuple[str, ...]]] = []
    with gzip.open(CORPUS_PATH, "rt", encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            name, _, alias_blob = line.rstrip("\n").partition("\t")
            if not name:
                continue
            rows.append((name, tuple(a for a in alias_blob.split("|") if a)))
    return tuple(rows)


def canon(limit: int | None = None) -> list[tuple[str, list[str]]]:
    """Corpus in the mutable shape the production signature expects."""
    rows = load_corpus()
    if limit is not None:
        rows = rows[:limit]
    return [(n, list(a)) for n, a in rows]


def surface_forms() -> list[str]:
    out: list[str] = []
    for name, aliases in load_corpus():
        out.append(name)
        out.extend(aliases)
    return out


def synth_chapter(
    corpus: list[tuple[str, list[str]]],
    *,
    mentions: int = 60,
    target_chars: int = 8_000,
    seed: int = 4242,
) -> tuple[str, set[str]]:
    """A chapter-sized text that really mentions `mentions` corpus entries.

    Returns ``(text, expected_names)`` — the canonical names whose name-or-alias
    was planted, so a test can assert selection recall exactly.

    This text is ASSEMBLED, not authored: the surface forms are real, the
    connective prose is filler. That is deliberate for a timing fixture — a
    match costs more than a miss, so a match-dense text measures the pessimistic
    case, which is the bound we actually want to know.
    """
    rng = random.Random(seed)
    picked = rng.sample(corpus, mentions)
    parts: list[str] = []
    expected: set[str] = set()
    for name, aliases in picked:
        # Plant an alias when there is one — that is the path a chapter really
        # takes ("Thiếu chủ", not "Lâm Uyên") and the one selection must survive.
        surface = rng.choice(aliases) if aliases else name
        parts.append(f"Người ta nhắc đến {surface} trong buổi chiều hôm ấy.")
        expected.add(name)
    filler = (
        "Gió thổi qua khe núi, mang theo mùi đất ẩm và tiếng lá khô lạo xạo dưới chân. "
        "他抬起头，看向远处的山脊，没有说话。"
    )
    while sum(len(p) for p in parts) < target_chars:
        parts.append(filler)
    rng.shuffle(parts)
    return " ".join(parts), expected
