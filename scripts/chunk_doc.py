#!/usr/bin/env python3
"""
chunk_doc.py — split a large markdown file into smaller chunks at heading
boundaries, with byte-level data-loss verification.

Subcommands:
    split   RULES [--dry-run] [--force]   Write chunks from source
    verify  RULES                         Verify existing chunks reconstruct source
    preview RULES                         Show planned chunk layout (no writes)
    scan    SOURCE [--min N] [--max N]    List headings with byte offsets

Rules file is JSON. Paths are resolved relative to the rules file's directory.

    {
      "source":     "../02_STORAGE_ARCHITECTURE.md",
      "output_dir": ".",
      "preamble":   "00_overview_and_schema.md",
      "with_meta":  true,
      "boundaries": [
        ["^## §12A\\b",  "R01_event_volume.md"],
        ["^## §12B\\b",  "R02_projection_rebuild.md"]
      ]
    }

How the data-loss check works:
    Each chunk is the verbatim byte range of the source between two boundaries.
    When with_meta=true, the tool prepends a strippable HTML comment header:

        <!-- CHUNK-META
        source: 02_STORAGE_ARCHITECTURE.md
        chunk: R01_event_volume.md
        byte_range: 12345-23456
        sha256: abcdef...
        generated_by: scripts/chunk_doc.py
        -->

        <verbatim original bytes from source[12345:23456]>

    'verify' strips that header from each chunk, concatenates the chunks in
    source order, and compares the result byte-for-byte (and by SHA-256) to
    the source file. A passing verify proves zero data loss.

Exit codes:
    0   success
    1   rules load / source missing
    2   output collision (use --force)
    3   chunk file missing during verify
    4   reconstruction mismatch (data-loss detected)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

# Matches the exact header we write. Tolerant of CRLF line endings.
CHUNK_META_RE = re.compile(
    rb"\A<!-- CHUNK-META\b.*?-->\r?\n\r?\n",
    re.DOTALL,
)


def _resolve(base: Path, p: str) -> Path:
    path = Path(p)
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def load_rules(rules_path: Path) -> dict:
    raw = json.loads(rules_path.read_text(encoding="utf-8"))
    for key in ("source", "output_dir", "boundaries"):
        if key not in raw:
            raise ValueError(f"rules missing required key: {key!r}")
    if not isinstance(raw["boundaries"], list) or not raw["boundaries"]:
        raise ValueError("rules.boundaries must be a non-empty list")
    base = rules_path.parent
    raw["_source_path"] = _resolve(base, raw["source"])
    raw["_output_dir"] = _resolve(base, raw["output_dir"])
    raw.setdefault("with_meta", True)
    raw.setdefault("preamble", None)
    raw.setdefault("allow_multi_match", False)
    return raw


def find_boundaries(
    source_bytes: bytes,
    patterns: list,
    allow_multi_match: bool,
) -> list[tuple[int, str, str]]:
    """
    Return list of (offset, filename, pattern) sorted by offset.
    Raises if a pattern is missing, matches mid-line, or matches multiple
    times when allow_multi_match is False.
    """
    result: list[tuple[int, str, str]] = []
    for entry in patterns:
        if not (isinstance(entry, list) and len(entry) == 2):
            raise ValueError(f"each boundary must be [pattern, filename]; got {entry!r}")
        pattern, filename = entry
        regex = re.compile(pattern.encode("utf-8"), re.MULTILINE)
        matches = list(regex.finditer(source_bytes))
        if not matches:
            raise ValueError(f"boundary pattern not found in source: {pattern!r}")
        if len(matches) > 1 and not allow_multi_match:
            offsets = [m.start() for m in matches]
            raise ValueError(
                f"boundary pattern {pattern!r} matched {len(matches)} times "
                f"at offsets {offsets}. Make the pattern more specific, or set "
                f'"allow_multi_match": true in the rules file (the first match wins).'
            )
        m = matches[0]
        start = m.start()
        if start > 0 and source_bytes[start - 1:start] != b"\n":
            raise ValueError(
                f"pattern {pattern!r} matched mid-line at byte {start}; "
                f"boundaries must match at the start of a line (use ^ anchor)"
            )
        result.append((start, filename, pattern))

    result.sort(key=lambda t: t[0])
    seen_offsets = [t[0] for t in result]
    if len(set(seen_offsets)) != len(seen_offsets):
        raise ValueError(f"duplicate boundary offsets (patterns collapse to same line): {seen_offsets}")
    seen_names = [t[1] for t in result]
    if len(set(seen_names)) != len(seen_names):
        raise ValueError(f"duplicate chunk filenames: {seen_names}")
    return result


def plan_chunks(source_bytes: bytes, rules: dict) -> list[tuple[str, int, int]]:
    """Return list of (chunk_filename, start_offset, end_offset) in source order."""
    boundaries = find_boundaries(source_bytes, rules["boundaries"], rules["allow_multi_match"])
    chunks: list[tuple[str, int, int]] = []
    first_off = boundaries[0][0]
    if first_off > 0:
        if not rules.get("preamble"):
            raise ValueError(
                f"source has {first_off} bytes before the first boundary but "
                f"rules.preamble is not set; add a preamble chunk name"
            )
        chunks.append((rules["preamble"], 0, first_off))
    elif rules.get("preamble"):
        raise ValueError(
            "rules.preamble is set but the first boundary is at byte 0 "
            "(there is no content before it)"
        )
    for i, (off, name, _pat) in enumerate(boundaries):
        end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(source_bytes)
        chunks.append((name, off, end))
    return chunks


def make_meta(source_name: str, chunk_name: str, start: int, end: int, sha: str) -> bytes:
    return (
        f"<!-- CHUNK-META\n"
        f"source: {source_name}\n"
        f"chunk: {chunk_name}\n"
        f"byte_range: {start}-{end}\n"
        f"sha256: {sha}\n"
        f"generated_by: scripts/chunk_doc.py\n"
        f"-->\n\n"
    ).encode("utf-8")


def strip_meta(data: bytes) -> bytes:
    m = CHUNK_META_RE.match(data)
    return data[m.end():] if m else data


def cmd_split(rules: dict, dry_run: bool, force: bool) -> int:
    source = rules["_source_path"]
    out_dir = rules["_output_dir"]
    if not source.exists():
        print(f"ERROR: source not found: {source}", file=sys.stderr)
        return 1
    source_bytes = source.read_bytes()
    chunks = plan_chunks(source_bytes, rules)

    print(f"Source     : {source} ({len(source_bytes)} bytes)")
    print(f"Output dir : {out_dir}")
    print(f"With meta  : {rules['with_meta']}")
    print(f"Chunks     : {len(chunks)}")
    print()

    existing = [n for n, _, _ in chunks if (out_dir / n).exists()]
    if existing and not force and not dry_run:
        print(f"ERROR: {len(existing)} chunk file(s) already exist. Use --force to overwrite:",
              file=sys.stderr)
        for n in existing:
            print(f"  {out_dir / n}", file=sys.stderr)
        return 2

    if dry_run:
        for name, start, end in chunks:
            print(f"  [{start:>9}..{end:>9})  {end - start:>8} bytes  {name}")
        print()
        print("(dry-run; no files written)")
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    for name, start, end in chunks:
        content = source_bytes[start:end]
        sha = hashlib.sha256(content).hexdigest()
        out_path = out_dir / name
        if rules["with_meta"]:
            out_path.write_bytes(make_meta(source.name, name, start, end, sha) + content)
        else:
            out_path.write_bytes(content)
        print(f"  wrote {name:<48} {end - start:>8} bytes  sha256={sha[:12]}")
    print()
    return cmd_verify(rules)


def cmd_verify(rules: dict) -> int:
    source = rules["_source_path"]
    out_dir = rules["_output_dir"]
    if not source.exists():
        print(f"ERROR: source not found: {source}", file=sys.stderr)
        return 1
    source_bytes = source.read_bytes()
    chunks = plan_chunks(source_bytes, rules)

    reconstructed = bytearray()
    missing: list[str] = []
    per_chunk_sha: list[tuple[str, str]] = []
    for name, start, end in chunks:
        p = out_dir / name
        if not p.exists():
            missing.append(name)
            continue
        content = strip_meta(p.read_bytes())
        reconstructed.extend(content)
        per_chunk_sha.append((name, hashlib.sha256(content).hexdigest()[:12]))

    if missing:
        print(f"FAIL: {len(missing)} chunk file(s) missing:", file=sys.stderr)
        for n in missing:
            print(f"  {out_dir / n}", file=sys.stderr)
        return 3

    source_sha = hashlib.sha256(source_bytes).hexdigest()
    if bytes(reconstructed) == source_bytes:
        print(f"VERIFY OK")
        print(f"  bytes         : {len(source_bytes)}")
        print(f"  source sha256 : {source_sha}")
        print(f"  chunks        : {len(chunks)}")
        for name, sha in per_chunk_sha:
            print(f"    {name:<48} sha256[:12]={sha}")
        return 0

    # Diagnose
    rec_sha = hashlib.sha256(bytes(reconstructed)).hexdigest()
    print("VERIFY FAIL — reconstruction does not match source", file=sys.stderr)
    print(f"  source_len         = {len(source_bytes)}", file=sys.stderr)
    print(f"  reconstructed_len  = {len(reconstructed)}", file=sys.stderr)
    print(f"  source_sha256      = {source_sha}", file=sys.stderr)
    print(f"  reconstructed_sha  = {rec_sha}", file=sys.stderr)
    limit = min(len(source_bytes), len(reconstructed))
    for i in range(limit):
        if source_bytes[i] != reconstructed[i]:
            lo, hi = max(0, i - 60), min(limit, i + 60)
            print(f"  first differing byte at offset {i}:", file=sys.stderr)
            print(f"    source       [{lo}..{hi}]   = {source_bytes[lo:hi]!r}", file=sys.stderr)
            print(f"    reconstructed[{lo}..{hi}]   = {bytes(reconstructed[lo:hi])!r}", file=sys.stderr)
            return 4
    print(f"  (one is a strict prefix of the other; length differs)", file=sys.stderr)
    return 4


def cmd_preview(rules: dict) -> int:
    source = rules["_source_path"]
    if not source.exists():
        print(f"ERROR: source not found: {source}", file=sys.stderr)
        return 1
    source_bytes = source.read_bytes()
    chunks = plan_chunks(source_bytes, rules)
    covered = sum(e - s for _, s, e in chunks)
    print(f"Source : {source} ({len(source_bytes)} bytes)")
    print(f"Planned: {len(chunks)} chunks, {covered} bytes covered (delta={len(source_bytes) - covered})")
    print()
    print(f"  {'name':<48} {'bytes':>9}  {'lines':>6}  byte_range")
    for name, start, end in chunks:
        lines = source_bytes.count(b"\n", start, end)
        print(f"  {name:<48} {end - start:>9}  {lines:>6}  [{start}..{end})")
    return 0


def cmd_scan(source_path: Path, level_min: int, level_max: int) -> int:
    if not source_path.exists():
        print(f"ERROR: source not found: {source_path}", file=sys.stderr)
        return 1
    data = source_path.read_bytes()
    pattern = re.compile(rb"^(#{1,6})[ \t]+(.+?)[ \t]*$", re.MULTILINE)
    count = 0
    for m in pattern.finditer(data):
        level = len(m.group(1))
        if level_min <= level <= level_max:
            text = m.group(2).decode("utf-8", errors="replace")
            print(f"  L{level}  byte={m.start():>9}  {text}")
            count += 1
    print(f"\n{count} heading(s) at level {level_min}..{level_max}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="Split a large markdown file into chunks at heading boundaries, "
                    "with byte-level data-loss verification.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("split", help="write chunks from source")
    sp.add_argument("rules", type=Path)
    sp.add_argument("--dry-run", action="store_true")
    sp.add_argument("--force", action="store_true")

    sv = sub.add_parser("verify", help="verify existing chunks reconstruct the source")
    sv.add_argument("rules", type=Path)

    pr = sub.add_parser("preview", help="show the planned chunk layout (no writes)")
    pr.add_argument("rules", type=Path)

    sc = sub.add_parser("scan", help="list headings in a source file with byte offsets")
    sc.add_argument("source", type=Path)
    sc.add_argument("--min", type=int, default=1, dest="level_min", help="min heading level (default 1)")
    sc.add_argument("--max", type=int, default=3, dest="level_max", help="max heading level (default 3)")

    args = p.parse_args()

    if args.cmd == "scan":
        return cmd_scan(args.source.resolve(), args.level_min, args.level_max)

    try:
        rules = load_rules(args.rules.resolve())
    except Exception as e:
        print(f"ERROR loading rules: {e}", file=sys.stderr)
        return 1

    if args.cmd == "split":
        return cmd_split(rules, args.dry_run, args.force)
    if args.cmd == "verify":
        return cmd_verify(rules)
    if args.cmd == "preview":
        return cmd_preview(rules)
    return 2


if __name__ == "__main__":
    sys.exit(main())
