"""Parity guard: the frozen Python T2S dict must equal the shared source-of-truth
TSV (sdks/data/han_t2s.tsv), which the Go SDK (sdks/go/loreweave_extraction) is
also generated from. This is what keeps the CJK simplified/traditional fold
identical across the Python (knowledge-service) and Go (glossary-service) dedup
paths — D-GLOSSARY-ST-DEDUP / D-KG-TL-SIMPLIFIED-TRADITIONAL-DUP.

If you edit the table, edit sdks/data/han_t2s.tsv, then regenerate the Go table
(`go generate ./...` in the Go module) and update _han_simplified_table.py — all
three stay in lockstep or this test (and the Go TestT2SParityWithSoT) fail.
"""

from __future__ import annotations

from pathlib import Path

from loreweave_extraction._han_simplified_table import T2S

# sdks/python/tests/test_extraction/ -> sdks/data/han_t2s.tsv
_TSV = Path(__file__).resolve().parents[3] / "data" / "han_t2s.tsv"


def _load_sot() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for line in _TSV.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        trad, simp = line.split("\t")
        assert len(trad) == 1 and len(simp) == 1, f"each side must be one char: {line!r}"
        mapping[trad] = simp
    return mapping


def test_tsv_exists():
    assert _TSV.is_file(), f"shared SoT TSV missing at {_TSV}"


def test_python_table_matches_sot():
    sot = _load_sot()
    assert T2S == sot, (
        "Python T2S drifted from the shared SoT TSV — edit sdks/data/han_t2s.tsv "
        "and regenerate both tables"
    )
