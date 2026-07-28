#!/usr/bin/env python3
"""Build the committed 20k-entity glossary test corpus from Wikipedia dumps.

WHY THIS EXISTS
---------------
`select_known_entities` (worker-ai) matches a book's whole canon vocabulary
against each chunk of prose. Its correctness and its cost both depend on
properties that ONLY real language has:

  * nesting      — "Lâm" ⊂ "Lâm Uyên" ⊂ "Lâm Uyên Các"
  * diacritics   — "Ha Noi" as a real alias of "Hà Nội"
  * no spaces    — CJK, where an ASCII word-boundary means nothing and
                   "林" matches inside "森林"
  * scale        — tens of thousands of surface forms per book

Synthetic names have none of that, and an LLM asked to invent names produces
a distribution it also has to be trusted about. Wikipedia article titles are
real proper nouns at volume, free, and — critically — REDIRECTS give real
human-authored aliases (abbreviations, alternate spellings, unaccented forms).

We are testing a STRING MATCHER, not extraction quality, so no gold labels
are needed. Morphology is the whole requirement.

WHAT IT PRODUCES
----------------
    services/worker-ai/tests/testdata/glossary_corpus_20k.tsv.gz
        name <TAB> alias1|alias2|...      (aliases may be empty)
    services/worker-ai/tests/testdata/ATTRIBUTION.md

The OUTPUT is committed (~200 KB) so the scale tests always run. This script
exists for provenance and regeneration, NOT as a test-time dependency — a
test that downloads 130 MB gets skipped in CI and then rots.

USAGE
-----
    python scripts/build-glossary-test-corpus.py --cache-dir <dir-with-dumps>

Expects these files already downloaded into --cache-dir:
    viwiki-latest-all-titles-in-ns0.gz
    zhwiki-latest-all-titles-in-ns0.gz
    viwiki-latest-redirect.sql.gz
    viwiki-latest-page.sql.gz          (optional — omit for no real aliases)
"""

from __future__ import annotations

import argparse
import gzip
import random
import re
import sys
import unicodedata
from pathlib import Path

# Fixed so a regeneration from the SAME dumps reproduces the SAME corpus.
# (A later dump legitimately yields different titles; the committed output is
# the fixture of record, this script is provenance.)
SEED = 20260728

TOTAL = 20_000
VI_QUOTA = 14_000
ZH_QUOTA = TOTAL - VI_QUOTA

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "services" / "worker-ai" / "tests" / "testdata"


# ── MediaWiki SQL dump parsing ────────────────────────────────────────────
#
# The dumps ship the CREATE TABLE statement ahead of the INSERTs, so we read
# the column order from the dump itself instead of hardcoding it. MediaWiki
# has reordered/dropped `page` columns several times (page_counter,
# page_restrictions); a hardcoded index silently reads the WRONG column and
# produces a corpus that looks plausible and is garbage.

_COL_RE = re.compile(r"^\s*`(\w+)`\s")


def read_columns(path: Path, table: str) -> list[str]:
    """Extract the column order of `table` from the dump's CREATE TABLE."""
    cols: list[str] = []
    in_create = False
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not in_create:
                if line.startswith(f"CREATE TABLE `{table}`"):
                    in_create = True
                continue
            if line.startswith(")"):
                break
            m = _COL_RE.match(line)
            if m:
                cols.append(m.group(1))
    if not cols:
        raise SystemExit(f"could not read CREATE TABLE `{table}` from {path.name}")
    return cols


def iter_rows(path: Path, table: str):
    """Yield each INSERT tuple of `table` as a list of raw string fields.

    Hand-rolled because the values contain commas, escaped quotes and
    parentheses inside string literals — `str.split(',')` corrupts perhaps 1
    row in 10_000, which is exactly the silent-garbage failure mode above.
    """
    prefix = f"INSERT INTO `{table}` VALUES "
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not line.startswith(prefix):
                continue
            buf = line[len(prefix):]
            i, n = 0, len(buf)
            while i < n:
                if buf[i] != "(":
                    i += 1
                    continue
                i += 1
                fields: list[str] = []
                cur: list[str] = []
                in_str = False
                while i < n:
                    c = buf[i]
                    if in_str:
                        if c == "\\" and i + 1 < n:
                            nxt = buf[i + 1]
                            # MySQL escapes: keep the literal char, drop the
                            # backslash, so `Cote d\'Ivoire` reads correctly.
                            cur.append({"n": "\n", "t": "\t", "r": "\r"}.get(nxt, nxt))
                            i += 2
                            continue
                        if c == "'":
                            in_str = False
                            i += 1
                            continue
                        cur.append(c)
                        i += 1
                        continue
                    if c == "'":
                        in_str = True
                        i += 1
                        continue
                    if c == ",":
                        fields.append("".join(cur))
                        cur = []
                        i += 1
                        continue
                    if c == ")":
                        fields.append("".join(cur))
                        i += 1
                        break
                    cur.append(c)
                    i += 1
                yield fields


# ── title filtering ───────────────────────────────────────────────────────


def clean_title(raw: str) -> str:
    return raw.replace("_", " ").strip()


def _is_cjk(ch: str) -> bool:
    o = ord(ch)
    return 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF


def acceptable_vi(name: str) -> bool:
    """Keep titles that read like a proper noun an author would put in a glossary."""
    if not (2 <= len(name) <= 40):
        return False
    # Namespace leftovers, subpages, disambiguators, list/meta pages — none of
    # these are entity names, and their punctuation would skew the matcher test.
    if any(c in name for c in ":/(){}[]|#<>"):
        return False
    if not any(ch.isalpha() for ch in name):
        return False
    if name[0].isdigit():
        return False
    # Latin script only (a vi dump still carries foreign-script titles).
    return all(ch.isspace() or not _is_cjk(ch) for ch in name)


def acceptable_zh(name: str) -> bool:
    """CJK names: short, dense, no spaces — the case ASCII boundaries can't handle."""
    if not (2 <= len(name) <= 12):
        return False
    if any(c in name for c in ":/(){}[]|#<> "):
        return False
    cjk = sum(1 for ch in name if _is_cjk(ch))
    return cjk >= max(2, int(len(name) * 0.8))


def load_titles(path: Path, accept) -> list[str]:
    out: list[str] = []
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
        next(fh, None)  # header line: "page_title"
        for line in fh:
            name = clean_title(line)
            if accept(name):
                out.append(name)
    return out


# ── real aliases from the redirect graph ──────────────────────────────────


def build_alias_map(page_path: Path, redirect_path: Path) -> dict[str, list[str]]:
    """canonical title -> [alias titles], from ns0 redirects.

    A Wikipedia redirect is a human saying "this other name means the same
    thing" — precisely a glossary alias, and free of our own biases about what
    an alias looks like.
    """
    pcols = read_columns(page_path, "page")
    i_id, i_ns = pcols.index("page_id"), pcols.index("page_namespace")
    i_title, i_red = pcols.index("page_title"), pcols.index("page_is_redirect")

    redirect_titles: dict[str, str] = {}
    for f in iter_rows(page_path, "page"):
        if len(f) != len(pcols):
            continue
        if f[i_ns] != "0" or f[i_red] != "1":
            continue
        redirect_titles[f[i_id]] = clean_title(f[i_title])
    print(f"  redirect pages: {len(redirect_titles):,}", file=sys.stderr)

    rcols = read_columns(redirect_path, "redirect")
    j_from, j_ns = rcols.index("rd_from"), rcols.index("rd_namespace")
    j_title = rcols.index("rd_title")

    aliases: dict[str, list[str]] = {}
    for f in iter_rows(redirect_path, "redirect"):
        if len(f) != len(rcols) or f[j_ns] != "0":
            continue
        alias = redirect_titles.get(f[j_from])
        if not alias:
            continue
        target = clean_title(f[j_title])
        if alias == target or not acceptable_vi(alias):
            continue
        aliases.setdefault(target, []).append(alias)
    print(f"  targets with aliases: {len(aliases):,}", file=sys.stderr)
    return aliases


# ── sampling ──────────────────────────────────────────────────────────────


def sample(pool: list[str], k: int, rng: random.Random) -> list[str]:
    """Deterministic sample. Sorted first so file order can't affect the result."""
    uniq = sorted(set(pool))
    if len(uniq) <= k:
        return uniq
    return rng.sample(uniq, k)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", required=True, type=Path)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = ap.parse_args()

    cache: Path = args.cache_dir
    vi_titles_f = cache / "viwiki-latest-all-titles-in-ns0.gz"
    zh_titles_f = cache / "zhwiki-latest-all-titles-in-ns0.gz"
    page_f = cache / "viwiki-latest-page.sql.gz"
    redirect_f = cache / "viwiki-latest-redirect.sql.gz"

    for f in (vi_titles_f, zh_titles_f):
        if not f.exists():
            raise SystemExit(f"missing required dump: {f}")

    rng = random.Random(SEED)

    print("reading vi titles…", file=sys.stderr)
    vi_pool = load_titles(vi_titles_f, acceptable_vi)
    print(f"  vi usable: {len(vi_pool):,}", file=sys.stderr)

    print("reading zh titles…", file=sys.stderr)
    zh_pool = load_titles(zh_titles_f, acceptable_zh)
    print(f"  zh usable: {len(zh_pool):,}", file=sys.stderr)

    alias_map: dict[str, list[str]] = {}
    if page_f.exists() and redirect_f.exists():
        print("building alias map from redirects…", file=sys.stderr)
        alias_map = build_alias_map(page_f, redirect_f)
    else:
        # Degrading loudly: a corpus with no aliases still tests nesting and
        # CJK, but NOT the alias path — say so rather than emit a quiet subset.
        print(
            "WARNING: page/redirect dumps absent — corpus will have NO aliases",
            file=sys.stderr,
        )

    # Bias the vi half toward titles that actually HAVE aliases (that is the
    # interesting path) without making the corpus unrealistically alias-dense.
    vi_set = set(vi_pool)
    with_alias = [t for t in alias_map if t in vi_set]
    want_aliased = min(len(with_alias), int(VI_QUOTA * 0.6))
    picked_aliased = sample(with_alias, want_aliased, rng)
    rest_pool = [t for t in vi_pool if t not in set(picked_aliased)]
    picked_plain = sample(rest_pool, VI_QUOTA - len(picked_aliased), rng)
    vi_pick = picked_aliased + picked_plain
    zh_pick = sample(zh_pool, ZH_QUOTA, rng)

    rows: list[tuple[str, list[str]]] = []
    for name in vi_pick + zh_pick:
        al = sorted(set(alias_map.get(name, [])))[:5]
        rows.append((name, al))
    rows.sort()

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_f = out_dir / "glossary_corpus_20k.tsv.gz"
    with gzip.open(out_f, "wt", encoding="utf-8", newline="\n") as fh:
        fh.write("# name\taliases(|-separated) — see ATTRIBUTION.md\n")
        for name, al in rows:
            fh.write(f"{name}\t{'|'.join(al)}\n")

    n_alias = sum(1 for _, a in rows if a)
    n_forms = sum(1 + len(a) for _, a in rows)
    print(
        f"wrote {out_f} — {len(rows):,} entries, {n_alias:,} with aliases, "
        f"{n_forms:,} surface forms, {out_f.stat().st_size:,} bytes",
        file=sys.stderr,
    )

    (out_dir / "ATTRIBUTION.md").write_text(
        "# glossary_corpus_20k.tsv.gz — attribution\n\n"
        "Derived from Wikipedia database dumps (`dumps.wikimedia.org`):\n\n"
        "- `viwiki-latest-all-titles-in-ns0.gz` — Vietnamese article titles\n"
        "- `zhwiki-latest-all-titles-in-ns0.gz` — Chinese article titles\n"
        "- `viwiki-latest-page.sql.gz` + `viwiki-latest-redirect.sql.gz` — "
        "redirects, used as real human-authored aliases\n\n"
        "Wikipedia text and titles are licensed **CC BY-SA 4.0**. This file is a "
        "filtered, deterministic sample of article *titles* only — no article "
        "prose is included.\n\n"
        "## Why this corpus\n\n"
        "It is test data for a **string matcher**, not for extraction quality, so "
        "it carries no gold labels. What it must supply is real morphology: "
        "nesting (`Lâm` ⊂ `Lâm Uyên`), Vietnamese diacritics and their unaccented "
        "alias forms, and CJK names with no whitespace — the case where an ASCII "
        "word boundary is meaningless.\n\n"
        "Regenerate with `scripts/build-glossary-test-corpus.py --cache-dir <dumps>`. "
        "The committed file is the fixture of record; regenerating against a newer "
        "dump legitimately produces different titles.\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
