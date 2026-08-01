#!/usr/bin/env python3
"""Gate: every persisted artifact this repo produces is written in ENGLISH.

WHY. Design docs, handoffs and commit messages kept arriving as English prose with
Vietnamese fragments pasted through them -- most often a verbatim PO quote dropped into a
design document, which then makes the surrounding paragraph bilingual. The artifact is not
the conversation: chat with the user happens in whatever language they wrote in, but what
lands in git is read later, by other agents and by CI, and a half-translated paragraph is
read by neither reliably. Doc 40/41 shipped with eight such fragments and had to be swept.

THE RULE (CLAUDE.md -> Key Rules -> "Written artifacts are ENGLISH", LOCKED 2026-07-31)
  * English: design/architecture/spec/planning docs, SESSION_HANDOFF + deferred rows, ADRs,
    READMEs, code + comments + docstrings, identifiers, log/error messages, test names.
  * Quote the MEANING in English. Never paste the original and leave it.
  * Non-English is allowed only where the text IS the subject matter, not the exposition:
    corpus/fixture content and cited spans, i18n bundles, translated user-facing strings,
    test data exercising CJK/RTL/normalisation, and domain terminology with no English
    equivalent (glossed in English on first use).

SCOPE -- DEFAULT-COVERED ON PURPOSE (NV-3). This gate does not carry a list of files it
watches; it watches everything staged whose suffix is text, minus the subject-matter
allowlist below. A doc created tomorrow in a directory nobody thought of is covered.

ADDED LINES ONLY. Measured 2026-07-31: 468 of 1962 tracked docs already contain Vietnamese.
Blocking on file contents would make every touch of a legacy doc uncommittable and the gate
would be switched off within a day. So --staged reads the diff and judges only lines this
commit ADDS. Legacy text is reported by --all as a baseline, never as a failure.

ESCAPE HATCH -- and it must reach its reason. Put ``doc-language-gate: ok -- <reason>`` on
the offending line, or open a block with ``<!-- doc-language-gate: ok -- <reason> -->`` and
close it with ``<!-- doc-language-gate: end -->``. A block with no reason text is itself a
finding: an exemption that cannot say why is the shape CLAUDE.md's non-vacuity standard
calls "the escape hatch cannot reach its reason".

Run: ``python scripts/doc-language-gate.py --staged`` (pre-commit) ·
     ``python scripts/doc-language-gate.py --all`` (baseline / CI report, never blocks).
"""
from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys
import unicodedata

ROOT = pathlib.Path(__file__).resolve().parents[1]

# --- detection ---------------------------------------------------------------------
#
# Vietnamese-SPECIFIC letters only. Deliberately excludes the accents Vietnamese shares
# with French/Spanish/Portuguese (e a o i u with acute/grave/circumflex/tilde), because
# those appear in ordinary English technical prose -- "Soufflé" is a Datalog engine this
# repo cites, "naïve", "café", "Gödel". Including them would make the gate cry wolf, and a
# gate that cries wolf gets switched off. The hook-above, dot-below and horn diacritics
# below are Vietnamese in practice, and real Vietnamese prose reaches one within a few
# words.
# doc-language-gate: ok -- this gate's own detection tables ARE Vietnamese by necessity;
# the alphabet it matches cannot be written in English. Scope is the two literals below.
_VN_CHARS = (
    "ăđơư"                                # ă đ ơ ư
    "ảạằắẳẵặ"                # ả ạ ằ ắ ẳ ẵ ặ
    "ầấẩẫậ"                            # ầ ấ ẩ ẫ ậ
    "ẻẽẹềếểễệ"          # ẻ ẽ ẹ ề ế ể ễ ệ
    "ỉĩị"                                        # ỉ ĩ ị
    "ỏọồốổỗộ"                # ỏ ọ ồ ố ổ ỗ ộ
    "ờớởỡợ"                            # ờ ớ ở ỡ ợ
    "ủũụừứửữự"          # ủ ũ ụ ừ ứ ử ữ ự
    "ỳỷỹỵ"                                  # ỳ ỷ ỹ ỵ
)
_VN_RE = re.compile(f"[{_VN_CHARS}{_VN_CHARS.upper()}]")

# Second signal, for Vietnamese typed WITHOUT diacritics -- a real habit in commit
# messages and handoff notes, and invisible to the character check. Requires several
# distinct hits on one line so that an English line mentioning "la" or "cua" cannot trip
# it; every word here is also not an English word.
_VN_STOPWORDS = {
    "khong", "duoc", "nhung", "nguoi", "viec", "cua", "thi", "cung", "hoac",
    "chung", "phai", "nen", "rat", "day", "kien", "truc", "lam", "mot", "cai",
    "vay", "moi", "voi", "trong", "cho", "tai", "hay", "gio", "biet", "hieu",
}
# doc-language-gate: end
_MIN_STOPWORDS = 3
_WORD_RE = re.compile(r"[a-z]+")

_PRAGMA_RE = re.compile(r"doc-language-gate:\s*ok\s*[-—:]+\s*(?P<reason>\S.*)", re.I)
_BLOCK_OPEN_RE = re.compile(r"doc-language-gate:\s*ok\b", re.I)
_BLOCK_END_RE = re.compile(r"doc-language-gate:\s*end\b", re.I)

# --- scope -------------------------------------------------------------------------

_TEXT_SUFFIXES = {
    ".md", ".markdown", ".rst", ".txt",
    ".py", ".rs", ".ts", ".tsx", ".js", ".jsx", ".go", ".java", ".sql", ".sh",
    ".toml", ".yaml", ".yml", ".json", ".cfg", ".ini",
}

#: Paths where non-English text IS the subject matter. Substring match on the POSIX path.
#: Add a row only with a reason; never to silence a document that simply was not translated.
_SUBJECT_MATTER = (
    "/fixtures/",        # corpus fixtures + their cited spans (39 CQ corpus, gamegen)
    "/fixture/",
    "/testdata/",
    "/corpora/",
    "/corpus/",
    "/locales/",         # i18n bundles: the translation IS the payload
    "/i18n/",
    "/translations/",
    "/snapshots/",       # recorded model output, kept byte-exact on purpose
    "/.remember/",       # the session memory buffer records the user's own words
    "/.claude/worktrees/",
)


def _in_subject_matter(rel: str) -> bool:
    p = "/" + rel.replace("\\", "/").lstrip("/")
    return any(marker in p for marker in _SUBJECT_MATTER)


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text)
                   if unicodedata.category(c) != "Mn")


def judge_line(line: str) -> str | None:
    """Return a reason string if this line looks like Vietnamese, else None."""
    if _VN_RE.search(line):
        return "Vietnamese diacritics"
    words = set(_WORD_RE.findall(_strip_accents(line).lower()))
    hits = words & _VN_STOPWORDS
    if len(hits) >= _MIN_STOPWORDS:
        return f"Vietnamese words without diacritics ({', '.join(sorted(hits)[:5])})"
    return None


# --- staged mode -------------------------------------------------------------------

def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                          text=True, encoding="utf-8", errors="replace").stdout


def staged_findings() -> tuple[list[tuple[str, int, str, str]], int, list[str]]:
    """(findings, files_scanned, bad_pragmas) over ADDED lines in the staged diff."""
    diff = _git("diff", "--cached", "-U0", "--no-color", "--diff-filter=ACMR")
    findings: list[tuple[str, int, str, str]] = []
    bad_pragmas: list[str] = []
    scanned: set[str] = set()

    rel = ""
    covered = False
    lineno = 0
    in_block = False
    for raw in diff.splitlines():
        if raw.startswith("+++ b/"):
            rel = raw[6:]
            covered = (pathlib.Path(rel).suffix.lower() in _TEXT_SUFFIXES
                       and not _in_subject_matter(rel))
            in_block = False
            if covered:
                scanned.add(rel)
            continue
        if raw.startswith("@@"):
            m = re.search(r"\+(\d+)", raw)
            lineno = int(m.group(1)) if m else 0
            continue
        if not raw.startswith("+") or raw.startswith("+++") or not covered:
            continue

        line = raw[1:]
        if _BLOCK_END_RE.search(line):
            in_block = False
            lineno += 1
            continue
        if _BLOCK_OPEN_RE.search(line):
            m = _PRAGMA_RE.search(line)
            if not m or len(m.group("reason").strip(" -—>")) < 8:
                bad_pragmas.append(f"{rel}:{lineno}: exemption with no reason -- "
                                   f"an escape hatch that cannot say why is not an "
                                   f"exemption, it is a silencer")
            in_block = True
            lineno += 1
            continue
        if not in_block:
            why = judge_line(line)
            if why:
                findings.append((rel, lineno, why, line.strip()[:110]))
        lineno += 1

    return findings, len(scanned), bad_pragmas


# --- baseline mode -----------------------------------------------------------------

def baseline() -> tuple[int, int]:
    """(files containing Vietnamese, files scanned) across tracked text files."""
    hits = 0
    total = 0
    for rel in _git("ls-files").splitlines():
        if pathlib.Path(rel).suffix.lower() not in _TEXT_SUFFIXES:
            continue
        if _in_subject_matter(rel):
            continue
        path = ROOT / rel
        if not path.is_file():
            continue
        total += 1
        try:
            if _VN_RE.search(path.read_text(encoding="utf-8", errors="ignore")):
                hits += 1
        except OSError:
            continue
    return hits, total


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--staged", action="store_true",
                    help="judge only lines ADDED by the staged diff (pre-commit mode)")
    ap.add_argument("--all", action="store_true",
                    help="report the legacy baseline across tracked files; never blocks")
    args = ap.parse_args()

    if args.all or not args.staged:
        hits, total = baseline()
        print(f"doc-language-gate: baseline -- {hits} of {total} tracked text file(s) "
              f"contain Vietnamese outside the subject-matter allowlist.")
        print("doc-language-gate: INFO (baseline mode never blocks; "
              "use --staged to gate a commit)")
        return 0

    findings, scanned, bad_pragmas = staged_findings()

    for rel, line, why, text in findings:
        print(f"{rel}:{line}: {why}\n    {text}")
    for msg in bad_pragmas:
        print(msg)

    if findings or bad_pragmas:
        print(f"\ndoc-language-gate: FAIL -- {len(findings) + len(bad_pragmas)} finding(s) "
              f"across {scanned} staged file(s).")
        print("Artifacts committed to this repo are written in ENGLISH (CLAUDE.md -> Key "
              "Rules). Quote the MEANING in English rather than pasting the original.")
        print("If the non-English text IS the subject matter (a cited corpus span, an i18n "
              "string, CJK test data), add `doc-language-gate: ok -- <reason>` on the line, "
              "or wrap the region in `<!-- doc-language-gate: ok -- <reason> -->` ... "
              "`<!-- doc-language-gate: end -->`.")
        return 1

    print(f"doc-language-gate: OK -- no non-English prose in lines added by "
          f"{scanned} staged file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
