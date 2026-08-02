#!/usr/bin/env python3
"""citation-gate — a `file:line` citation in a design doc must point at something real.

THE BUG THIS EXISTS TO PREVENT (`U-10`, `D-281`, `D-314`)
---------------------------------------------------------
The 2026-08-02 actor-hub round measured that **no repo gate can reach its own
documents**: `design-lint.py`'s corpus is hard-defaulted to
`docs/03_planning/LLM_MMO_RPG` and pointing it at `docs/specs` fails outright
(*"id catalog not found"*). So **none of the ~45 citations those contracts carry
was checked by anything**, and the only audit they ever had was done by hand.

In that same round the project produced **three separate phantom-citation
incidents, two of them inside correction blocks written to fix citation errors**:

  * `resource/table.rs:242-247` — a line range **past end of file**;
  * `layer.rs:41` cited for an `enum` that is at `:22`;
  * `island/mod.rs:92-100` cited for a discard that is at `:301` — the cited
    lines are a **doc comment**, which CLAUDE.md already records as *"prose that
    happens to live in a source file"*.

The failure mode is therefore **not carelessness** — the same author, warned,
knowing the rate, produced it again. It is the absence of a mechanism, which is
what this repo's own standard says a rule without one becomes.

WHAT IT CHECKS
--------------
  C1 anchored-exists     a citation containing `/` resolves to exactly one real
                         file — by repo-root path, or by unique path SUFFIX
                         (docs write `sim-core/src/types.rs`, the tree has
                         `crates/sim-core/src/types.rs`). Zero matches, or more
                         than one, is a finding.
  C2 line-exists         `:N` / `:N-M` must be within the file. This is the
                         `resource/table.rs:242-247` defect exactly.
  C3 unanchored          a BARE filename WITH a line number (`resolve.rs:84`) is
                         only checkable if exactly one file in the tree has that
                         name. Zero or several is a finding, because a reader
                         cannot resolve it either.
  C4 link-target         a markdown link to a relative path must resolve from
                         the citing document's directory.

WHAT IT CANNOT CHECK, STATED SO NOBODY TRUSTS IT TOO FAR
--------------------------------------------------------
**It checks that a citation RESOLVES, never that it says what the citing sentence
claims.** Of the three phantom citations above it would have caught exactly one —
the line range past end of file. `layer.rs:41` cited for an `enum` that is at
`:22` points at a real line of a real file, and `island/mod.rs:92-100` cited for a
discard that is at `:301` points at a real doc comment. **Both pass this gate.**

That residual is not a reason to skip the gate; it is a reason not to call a green
run an audit. The remaining half is a reader's job, and the hand audit that found
those two remains the only thing that does it.

WHAT STILL WALKS PAST IT, NAMED RATHER THAN IMPLIED
---------------------------------------------------
`SOURCE_EXT` is an enumerated list, so an extension nobody added is unchecked —
the same NV-3 shape this file enforces elsewhere, kept because the alternative
(any dotted token) reds on version strings and package names. HTML anchors
(`<a href="x.md">`) and nested brackets in link text are not matched. **A green
run is not an audit**, and neither is the sibling limit below.

A bare filename with NO line number is deliberately NOT checked: those are prose
mentions, and one of them in this very corpus is a *deliberate* reference to a
DELETED file (`2026-08-02-handoffs-to-features.md`, whose deletion is the point
of the sentence). A gate that reds on a correct sentence gets switched off.

SCOPE — a tree for the strict half, added-lines for the rest
------------------------------------------------------------
`STRICT_TREES` are scanned **in full, recursively**, so a document created there
tomorrow is covered on its first line rather than being default-uncovered
(`docs/standards/non-vacuity.md`, NV-3).

Everything else under `docs/` is checked in `--staged` mode on **added lines
only** — the same policy `doc-language-gate` uses, for the same measured reason:
the legacy corpus has a baseline that would make every touch of an old file
uncommittable, and a gate that blocks legitimate work is off within a day.
`--all` reports that baseline and never blocks. **The residual is stated rather
than hidden:** a legacy doc's existing citations are checked only when a commit
touches the line they sit on.

    python scripts/citation-gate.py            # strict trees, in full
    python scripts/citation-gate.py --staged   # + added lines anywhere in docs/
    python scripts/citation-gate.py --all      # baseline report, never blocks
    python scripts/citation-gate.py --self-test
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from urllib.parse import unquote
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Scanned in full. Directories, never a file list.
STRICT_TREES = (
    "docs/specs/2026-08-02-actor-hub",
)

# ...minus the derivation record. `_index.md` states its status: "Nothing here is
# a decision… no part of it binds anyone." It is 9 700 lines of HISTORY, and its
# citations are history too — several point at code that has since moved or been
# deleted, which is what a derivation record is FOR. Blocking a commit on them
# would make the gate cry wolf on correct content, and a gate that does that is
# switched off within a day.
#
# This is a subtree exclusion, not a file list: a NEW contract added at the top
# level of the strict tree tomorrow is still covered on its first line. The
# excluded count is PRINTED on every run, so the hole is visible rather than
# silent — `--all` reports the baseline inside it.
EXCLUDED_SUBTREES = (
    "docs/specs/2026-08-02-actor-hub/analysis",
)

# Deliberately EMPTY, and the reason is a measurement.
#
# The obvious candidate was the round's RUN-STATE. Scanning it in full produced
# 25 findings, and **almost all of them are HISTORY**: `D-1`..`D-291` cite code
# as it stood during the design round. Worse, six of those citations
# (`actor.rs:31`, `registry.rs:20`, `modifier.rs:101`, …) were UNAMBIGUOUS when
# they were written and became ambiguous **because this very build added a second
# `actor.rs` and a second `registry.rs`** — so a full scan would red a commit for
# making a correct past sentence ambiguous, which is the gate crying wolf on
# work it should be helping.
#
# The RUN-STATE is therefore covered by the `--staged` added-lines policy like
# any other document: the lines a commit ADDS are checked, its historical record
# is not. That is the same trade `doc-language-gate` makes, for the same reason.
STRICT_FILES: tuple[str, ...] = ()

DOC_ROOT = "docs"

# Longest alternative FIRST. Python alternation is ordered and everything after
# the extension is optional, so `ts|tsx` makes `tsx` unreachable: `App.test.tsx`
# matched as `App.test.ts`, was reported missing, AND lost its line number. Same
# for `js` before `json`. A review found both branches dead and both producing
# commit-blocking false positives on files that demonstrably exist.
# Longest-alternative-first, and NO bare single letters. `c` and `h` were in the
# first version and truncated `.cypher` -> `.c`, `.conf` -> `.c`, `.cpp` -> `.c`,
# `.hpp` -> `.h`, producing 36 commit-blocking false positives on correctly
# written citations. The same ordered-alternation defect as `ts|tsx`, one more
# level along. They are simply removed: this repo has no `.c`/`.h` worth citing,
# and a MISS is the safe direction for a gate whose cry-wolf mode blocks work.
SOURCE_EXT = (
    r"(?:rs|pyi|py|go|tsx|ts|jsonl|json|jsx|mjs|cjs|js|md|ya?ml|toml|sql|sh|ps1"
    r"|html|css|txt|lock|ini|tf|proto|cypher|conf)"
)

# `path/to/file.ext` or `file.ext`, optionally `:N` or `:N-M`.
CITATION_RE = re.compile(
    # A leading `.` is allowed: `.github/workflows/gates.yml`, `.claude/settings.json`
    # and `.gitleaks.toml` are all tracked files, and the first version of this
    # class truncated the dot and then reported the result missing — a
    # commit-blocking false positive on exactly the paths a gate-wiring doc cites.
    #
    # `\\` is allowed so a Windows-style path is recognised AS a path. It is
    # normalised before lookup rather than matched: without it, `crates\made\up\
    # dir\layer.rs:41` degraded to the bare `layer.rs:41`, resolved uniquely, and
    # a wholly wrong directory passed.
    rf"(?P<path>\.?[A-Za-z0-9_][A-Za-z0-9_./\\-]*\.{SOURCE_EXT})"
    # `\d+` alone truncated `:9_99999` to line 9 — a typo became a valid
    # citation. Matching the separator makes it a syntax the gate REFUSES.
    # `[0-9]`, not `\d`: Python's `\d` matches every Unicode decimal, so
    # `b.md:1\u0663` was absorbed as line 13 — the typo-becomes-a-valid-citation
    # class the trailing-junk rule exists for, one character along.
    r"(?::(?P<start>[0-9][0-9_]*)(?:-(?P<end>[0-9][0-9_]*))?)?"
)

# A markdown link whose target is a relative path (not a URL, not an anchor).
# CommonMark allows `[x](target "title")` and `[x](<target>)`. Both are matched.
#
# `[x](<target with spaces>)` is NOT — `[^>\s]+` stops at the space, so such a
# link matches nothing and is silently unchecked. That is a MISS and it is named
# here rather than claimed as support: an earlier version of this comment said
# the angle-bracket form handled spaces, which it never did.
# The scheme test is done in CODE, not by a lookahead before an optional `<`.
# `<?(?!https?:…)` backtracks: the engine tries `<?` greedy, the lookahead fails,
# it gives the `<` back, and the lookahead then passes because the next character
# is `<`. So `[x](<https://example.com/a.md>)` was reported as a dead repo file.
# Same defect in both link rules — see `_is_external`.
LINK_RE = re.compile(
    r"\[[^\]]*\]\("
    r"(?:<(?P<angled>[^>\s]+)>|(?P<plain>[^)\s]+))"
    r"(?:\s+[\"'\(][^)]*)?"
    r"\)"
)


# Schemes that name something outside this repository.
EXTERNAL_SCHEMES = ("http", "https", "mailto", "file", "ftp", "ftps", "tel", "data")


def _is_external(target: str) -> bool:
    """A URL, an anchor, or a mail link — not a path in this repository."""
    t = target.strip().lower()
    # `file://`, `ftp://` and `tel:` were each reported as a dead repo file --
    # twice over, since `URL_RE` did not blank them either. Four live `file:///`
    # links exist in `docs/`.
    return (
        t.startswith("#") or t.startswith("//")
        or any(t.startswith(f"{sch}:") for sch in EXTERNAL_SCHEMES)
    )

# A URL. Blanked before the citation scan, because `example.com/a.md` and
# `github.com/o/r/blob/main/docs/X.md` are paths on SOMEONE ELSE'S filesystem —
# reporting them as missing repo files is the gate crying wolf on a correct link.
URL_RE = re.compile(
    r"(?:https?|file|ftps?)://\S+"
    r"|(?<![\w.])github\.com/\S+"
)

# A reference-style link DEFINITION: `[ref]: some/path.md`.
#
# THE TARGET MUST LOOK LIKE A PATH — it needs a `/` or a known extension. The
# first version accepted any token and produced eleven false positives on correct
# content: `[SYSTEM]: 1240 tokens` in a budget table, `[k: string]: unknown;`
# inside a TypeScript code block, `[1024,16384]: 1024,` in a findings table, and
# every footnote `[^1]: text`. A label followed by a colon is a markdown idiom
# long before it is a link.
#
# `[^…]` (a footnote) is excluded outright, and a `|` before the bracket (a table
# row) likewise.
# No `(?!\s*\|)` table guard: `^\s*\[` already refuses any line starting with
# `|`, so the lookahead could never change a verdict — a false-positive guard,
# shipped in the round about false positives, that guarded nothing. Its self-test
# case went green with the lookahead deleted.
LINK_DEF_RE = re.compile(
    r"^\s*\[(?!\^)[^\]]+\]:\s*"
    r"(?:<(?P<angled>[^>\s]+)>|(?P<plain>\S+))\s*$"
)

PRAGMA = "citation-gate: ok"
PRAGMA_LOOKBACK = 3


class Finding:
    def __init__(self, rule: str, doc: str, line: int, detail: str):
        self.rule, self.doc, self.line, self.detail = rule, doc, line, detail

    def __str__(self) -> str:
        return f"  {self.rule:16} {self.doc}:{self.line}  {self.detail}"


# The pragma must be followed by a reason, and must sit inside an HTML comment.
# Without the first, `citation-gate: ok` alone silenced three lines while the
# failure message promised `— <reason>`. Without the second, any prose that
# QUOTES the pragma — such as a document explaining this gate — silences its own
# next three lines.
PRAGMA_RE = re.compile(rf"<!--[^>]*{re.escape(PRAGMA)}\s*[-—:]\s*\S[^>]*-->")


# A target that is a bare filename with a recognised extension, e.g. `nowhere.md`.
EXT_ONLY_RE = re.compile(rf"\.{SOURCE_EXT}$")


# A template's placeholder link, e.g. `[L<N>_*.md](.../L<N>_*.md)`. Widening the
# inline target class to `[^)\s]+` made these two live template files red; they
# are documents ABOUT a naming shape, and the "link" is the shape.
PLACEHOLDER_RE = re.compile(r"[<>*{}]")


def _is_placeholder(target: str) -> bool:
    return bool(PLACEHOLDER_RE.search(target))


def _check_link(tree: "Tree", rel: str, n: int, doc_dir: str, target: str, kind: str) -> list["Finding"]:
    """One resolution rule for BOTH link forms.

    They had two: the inline rule reported `escapes the repository` for an
    absolute target while the reference rule said `does not resolve` for the
    identical input. Two arms of one gate answering differently is the shape
    `Tree.normalise`'s own docstring was written to kill.
    """
    joined = Tree.normalise(f"{doc_dir}/{target}" if doc_dir else target)
    escaped = (
        joined.startswith("..")
        or bool(re.match(r"^[A-Za-z]:", target))
        or target.startswith("/")
    )
    if escaped:
        return [Finding("C4-link", rel, n, f"{kind} `{target}` escapes the repository")]
    # Resolved against the same TREE the citation rules use, not against the host
    # filesystem. `Path.exists()` sees gitignored build output, so one link gave
    # opposite verdicts depending on whether `npm install` had been run — CI on a
    # fresh clone reddened a link a developer saw as green, and the `--all`
    # baseline was not reproducible between machines. That is exactly the
    # two-answers-for-one-input defect this function was created to kill.
    #
    # **NARROWED, NOT CLOSED, and stated so rather than recorded as closed.**
    # `Tree.from_git` folds in `--others --exclude-standard`, so an untracked-but-
    # unignored file still differs between a clean clone and a working checkout.
    # That residual is deliberate: without it, a citation to a file created by the
    # SAME commit would not resolve, and every honest new-crate commit would be
    # refused. The gitignored-build-output class — the one that actually bit — is
    # gone.
    if not tree.knows(joined):
        return [Finding("C4-link", rel, n, f"{kind} `{target}` does not resolve")]
    return []


def _pragma_covers(lines: list[str], idx: int) -> bool:
    lo = max(0, idx - PRAGMA_LOOKBACK)
    return any(PRAGMA_RE.search(lines[k]) for k in range(lo, idx + 1))


class Tree:
    """The repo's tracked files, indexed for suffix and basename lookup."""

    def __init__(self, paths: list[str]):
        self.paths = paths
        self._set = set(paths)
        self._dirs: set[str] = set()
        self.by_name: dict[str, list[str]] = {}
        for p in paths:
            self.by_name.setdefault(p.rsplit("/", 1)[-1], []).append(p)
            parts = p.split("/")
            for k in range(1, len(parts)):
                self._dirs.add("/".join(parts[:k]))

    @classmethod
    def from_git(cls) -> "Tree":
        out = subprocess.run(
            ["git", "ls-files"], cwd=REPO, capture_output=True, text=True
        )
        if out.returncode != 0:
            print("citation-gate: `git ls-files` failed", file=sys.stderr)
            sys.exit(2)
        tracked = [p.strip().replace("\\", "/") for p in out.stdout.splitlines() if p.strip()]
        # Untracked-but-present files count too: a citation added in the same
        # commit that creates its target must resolve, or the gate would refuse
        # every honest new-crate commit.
        extra = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=REPO, capture_output=True, text=True,
        )
        tracked += [p.strip().replace("\\", "/") for p in extra.stdout.splitlines() if p.strip()]
        return cls(tracked)

    @staticmethod
    def normalise(cited: str) -> str:
        """Windows separators to `/`, and `a/../b` collapsed to `b`.

        Both were bypasses. `crates\\made\\up\\layer.rs:41` matched only its
        basename and resolved uniquely against a wholly different directory;
        `docs/../crates/x.rs` matched nothing while `Path.resolve()` in the C4
        rule normalised the same syntax happily — two rules of one gate
        disagreeing about what a path is.
        """
        parts: list[str] = []
        for seg in cited.replace("\\", "/").split("/"):
            if seg in ("", "."):
                continue
            if seg == ".." and parts and parts[-1] != "..":
                parts.pop()
                continue
            parts.append(seg)
        return "/".join(parts)

    def knows(self, path: str) -> bool:
        """Is this exact repo-relative path in the tree — file OR directory?

        Directories are not listed by `git ls-files`, so they are derived from the
        prefixes of the paths that are. A link to a directory is a legitimate
        markdown link.
        """
        return path in self._set or path in self._dirs

    def resolve(self, cited: str) -> list[str]:
        """Every tracked path the citation could mean."""
        cited = self.normalise(cited)
        if cited in self.paths:
            return [cited]
        if "/" in cited:
            return [p for p in self.paths if p == cited or p.endswith("/" + cited)]
        return list(self.by_name.get(cited, []))

    def line_count(self, path: str) -> int:
        f = REPO / path
        try:
            return len(f.read_text(encoding="utf-8", errors="replace").splitlines())
        except OSError:
            return 0


# NO FENCE EXCLUSION, and its removal is a correction worth stating.
#
# A previous round excluded every fenced block, claiming *"539 findings, every one
# of them a false positive"*. Re-measured by a review: **538 findings, of which
# 155 carry a `:N` line number** — genuine `file:line` citations living in blocks
# titled *"Current architecture (evidence)"*. One was a `C2-past-eof` on a 59-line
# file **inside this gate's own blocking corpus**: the exact defect class the
# module docstring names as the reason the gate exists. It also blinded **97 057
# of 522 781 doc lines (18.6 %)** without saying so anywhere.
#
# The false positives it was aimed at were the NO-LINE-NUMBER class, which is now
# handled directly and by its real name. **A scope cut justified by a number
# nobody re-measured is the same defect as a claim nobody re-measured.**

# A markdown link. A citation appearing as the link TEXT is resolvable by
# definition — the href beside it IS the resolution — so the C3-unanchored rule's
# justification ("a reader cannot resolve it either") is false for every one.
# Measured at 398 findings, including all ten remaining `+`-idiom blockers.
# Matches the same two forms `LINK_RE` does, including the CommonMark title.
# An earlier version required `)` immediately after a space-free href, so a
# titled link's text was still checked while a plain one's was not — the two
# regexes disagreeing about what a link is.
LINK_SPAN_RE = re.compile(r"\[[^\]]*\]\(<?[^)\s>]+>?(?:\s+[\"'\(][^)]*)?\)")


# An inline code span. `` `[x](nowhere.md)` `` in prose ABOUT markdown is a
# quotation, not a link — the same class the fence rule was aimed at, one
# delimiter along, and it was left unnamed when fences were excluded.
CODE_SPAN_RE = re.compile(r"`[^`]*`")


def _code_span_ranges(line: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in CODE_SPAN_RE.finditer(line)]


def _link_text_spans(line: str) -> list[tuple[int, int]]:
    """Character ranges of the `[…]` half of every inline markdown link."""
    out = []
    for m in LINK_SPAN_RE.finditer(line):
        text_end = line.index("](", m.start())
        out.append((m.start() + 1, text_end))
    return out


def scan_doc(tree: Tree, rel: str, text: str, only_lines: set[int] | None = None) -> list[Finding]:
    """Findings in one document. `only_lines` restricts to added lines (1-based)."""
    lines = text.splitlines()
    out: list[Finding] = []
    doc_dir = rel.rsplit("/", 1)[0] if "/" in rel else ""

    for i, line in enumerate(lines):
        n = i + 1
        if only_lines is not None and n not in only_lines:
            continue
        if _pragma_covers(lines, i):
            continue
        link_text = _link_text_spans(line)

        # URLs first: a path inside one belongs to another host's filesystem.
        scan_line = URL_RE.sub(lambda m: " " * len(m.group(0)), line)
        for m in CITATION_RE.finditer(scan_line):
            cited = m.group("path")
            start, end = m.group("start"), m.group("end")
            anchored = "/" in cited or "\\" in cited
            # A citation that IS the text of a markdown link resolves through the
            # href beside it — so reporting it *unresolvable* was the gate telling
            # a reader that a link they can click does not work.
            #
            # **It answers WHICH FILE and says nothing about WHICH LINE.** The
            # first version `continue`d before the line-exists check, which
            # silently disabled `C2` for every citation written as link text and
            # hid three live broken ranges. So the skip is recorded and applied to
            # the resolution arm only; `C2` still runs below.
            is_link_text = any(a <= m.start() < b for a, b in link_text)
            if start is None:
                # **A citation with NO LINE NUMBER is a prose mention**, whether
                # or not it carries a directory. Measured: 3 382 of the 8 095
                # findings across `docs/` are this shape, and the dominant one is
                # this repo's planning idiom -- a table row naming a file the plan
                # proposes to CREATE ("| P1 | `services/x/test_new.py` | to WRITE |").
                # That blocked a commit on correct content.
                #
                # The docstring already carved out BARE filenames with no line
                # number for exactly this reason; nothing justified the asymmetry
                # with anchored ones, and nothing stated it.
                #
                # **With a line number the meaning changes**: you are pointing at
                # content that must already exist, and that is what this gate is
                # for (`resource/table.rs:242-247`, past end of file).
                continue

            # Junk immediately after the line number: `…:1e9` read as line 1,
            # a typo silently becoming a valid citation.
            #
            # `+` is NOT junk. `entity_resolver.py:125+` is this repo's established
            # idiom for "line 125 and following" and appears 26 times; refusing it
            # blocked commits on correct prose. `.`, `-`, `,`, `)` are ordinary
            # punctuation. What is left is an alphanumeric or `_` glued to the
            # number, which is never a citation anyone meant to write.
            tail = scan_line[m.end():m.end() + 1]
            if start is not None and tail and (tail.isalnum() or tail == "_"):
                out.append(
                    Finding("C2-bad-range", rel, n,
                            f"`{m.group(0)}{tail}` has junk after its line number")
                )
                continue

            matches = tree.resolve(cited)
            # A doc-relative target is legitimate and common: `analysis/foo.md`
            # inside `docs/specs/x/` means `docs/specs/x/analysis/foo.md`.
            if not matches and doc_dir:
                candidate = f"{doc_dir}/{cited}"
                matches = tree.resolve(candidate)
            if not matches:
                if not is_link_text:
                    rule = "C1-missing" if anchored else "C3-unanchored"
                    out.append(Finding(rule, rel, n, f"`{m.group(0)}` matches no file in the tree"))
                continue
            if len(matches) > 1:
                if not is_link_text:
                    rule = "C1-ambiguous" if anchored else "C3-unanchored"
                    out.append(
                        Finding(
                            rule, rel, n,
                            f"`{m.group(0)}` matches {len(matches)} files "
                            f"({', '.join(sorted(matches)[:3])}…) — a reader cannot resolve it either",
                        )
                    )
                continue
            if start is None:
                continue
            target = matches[0]
            have = tree.line_count(target)
            if "_" in start or (end and "_" in end):
                out.append(
                    Finding("C2-bad-range", rel, n, f"`{m.group(0)}` has a separator in its line number")
                )
                continue
            lo, hi = int(start), int(end) if end else int(start)
            # BOTH ends are checked, and the range must not be degenerate.
            # The first version wrote `last = int(end) if end else int(start)`
            # and dropped `start` entirely — so `types.rs:99999-2` passed, which
            # is the EXACT past-EOF class this rule was built for, and `:0`
            # passed too although line 0 is not a line.
            if lo < 1:
                out.append(
                    Finding("C2-bad-range", rel, n, f"`{m.group(0)}` starts at line {lo}; lines are 1-based")
                )
            elif end is not None and hi < lo:
                out.append(
                    Finding(
                        "C2-bad-range", rel, n,
                        f"`{m.group(0)}` is a reversed range ({lo} > {hi})",
                    )
                )
            elif max(lo, hi) > have:
                out.append(
                    Finding(
                        "C2-past-eof", rel, n,
                        f"`{m.group(0)}` cites line {max(lo, hi)} of `{target}`, which has {have}",
                    )
                )

        # Links inside an inline code span are a QUOTATION of markdown, not a
        # link. The exclusion is applied HERE, to the link rules only.
        #
        # It is deliberately NOT applied to CITATIONS: this repo writes almost
        # every citation in backticks (`resolve.rs:84`), so excluding code spans
        # from the citation scan would blind the gate to nearly all of its
        # subject. An earlier version of this block was a no-op loop that
        # iterated the links, skipped the spans and then did nothing at all --
        # the exclusion was written and never reached the check it was for.
        spans = _code_span_ranges(line)
        # NO code-span check on this arm, and its absence is the point.
        # `LINK_DEF_RE` is anchored `^\s*\[`, so its match can only ever start at
        # column 0 or after whitespace — never inside a backtick span. Adding the
        # check here would be the third occurrence this round of a guard that
        # cannot change a verdict (`(?!\s*\|)`, the table-row self-test, and this),
        # and it went in before a bite-test caught it: the mutation removing it
        # left the whole self-test green.
        for m in LINK_DEF_RE.finditer(line):
            raw = m.group("angled") or m.group("plain") or ""
            if _is_external(raw):
                continue
            target = unquote(raw.split("#", 1)[0])
            # Must look like a path, or it is a markdown label and not a link.
            if not target or _is_placeholder(target):
                continue
            if not ("/" in target or EXT_ONLY_RE.search(target)):
                continue
            out.extend(_check_link(tree, rel, n, doc_dir, target, "reference definition"))

        for m in LINK_RE.finditer(line):
            if any(a <= m.start() < b for a, b in spans):
                continue
            raw = m.group("angled") or m.group("plain") or ""
            if _is_external(raw):
                continue
            target = unquote(raw.split("#", 1)[0])
            if not target or _is_placeholder(target):
                continue
            # Resolved as a REPO-RELATIVE string, never through the host
            # filesystem's idea of absoluteness. `Path.resolve()` made this rule
            # answer differently on Windows and Linux for the same input:
            # `[x](/etc/passwd)` red here and green in CI, `[x](C:/Windows)` the
            # reverse. A gate with two answers for one input is worse than none.
            out.extend(_check_link(tree, rel, n, doc_dir, target, "link target"))
    return out


def _strict_docs() -> list[str]:
    docs: list[str] = []
    excluded = 0
    for tree in STRICT_TREES:
        root = REPO / tree
        if not root.is_dir():
            print(
                f"citation-gate: strict tree `{tree}` is missing, so nothing under it was "
                "checked. That is a SCOPE failure, not a clean run.",
                file=sys.stderr,
            )
            sys.exit(2)
        for p in sorted(root.rglob("*.md")):
            rel = str(p.relative_to(REPO)).replace("\\", "/")
            if any(rel.startswith(x + "/") for x in EXCLUDED_SUBTREES):
                excluded += 1
                continue
            docs.append(rel)
    for f in STRICT_FILES:
        if not (REPO / f).is_file():
            print(
                f"citation-gate: strict file `{f}` is missing — it was renamed or deleted and "
                "the gate silently stopped covering it.",
                file=sys.stderr,
            )
            sys.exit(2)
        docs.append(f)
    _strict_docs.excluded = excluded  # type: ignore[attr-defined]
    return docs


def _staged_added_lines() -> dict[str, set[int]]:
    out = subprocess.run(
        ["git", "diff", "--cached", "-U0", "--", DOC_ROOT],
        cwd=REPO, capture_output=True, text=True,
    )
    added: dict[str, set[int]] = {}
    current: str | None = None
    lineno = 0
    for raw in out.stdout.splitlines():
        if raw.startswith("+++ b/"):
            current = raw[6:].strip()
            continue
        if raw.startswith("@@"):
            m = re.search(r"\+(\d+)", raw)
            lineno = int(m.group(1)) if m else 0
            continue
        if raw.startswith("+") and current and current.endswith(".md"):
            added.setdefault(current, set()).add(lineno)
            lineno += 1
    return added


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--staged", action="store_true")
    ap.add_argument("--all", action="store_true", help="baseline report; never blocks")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    tree = Tree.from_git()
    findings: list[Finding] = []

    if args.all:
        root = REPO / DOC_ROOT
        for p in sorted(root.rglob("*.md")):
            rel = str(p.relative_to(REPO)).replace("\\", "/")
            findings += scan_doc(tree, rel, p.read_text(encoding="utf-8", errors="replace"))
        print(f"citation-gate --all: {len(findings)} baseline finding(s) across docs/ (never blocks)")
        for f in findings[:60]:
            print(f)
        return 0

    for rel in _strict_docs():
        findings += scan_doc(tree, rel, (REPO / rel).read_text(encoding="utf-8", errors="replace"))

    if args.staged:
        strict_set = set(_strict_docs())
        for rel, lines in _staged_added_lines().items():
            # Membership, not a prefix. `rel.startswith("docs/specs/2026-08-02-actor-hub")`
            # also swallowed `…-actor-hub-v2/x.md` and `…-actor-hubXYZ.md`, which
            # `rglob` never reaches — default-uncovered from birth — and it
            # swallowed `analysis/`, which the strict walk EXCLUDES, so that
            # subtree received neither kind of coverage while every other
            # document in the repo gets at least added-lines.
            if rel in strict_set:
                continue  # already scanned in full
            p = REPO / rel
            if p.is_file():
                findings += scan_doc(
                    tree, rel, p.read_text(encoding="utf-8", errors="replace"), only_lines=lines
                )

    if findings:
        skipped = getattr(_strict_docs, "excluded", 0)
        if skipped:
            print(
                f"citation-gate: NOTE — {skipped} derivation-record file(s) are excluded "
                "from the strict walk (EXCLUDED_SUBTREES); they get added-lines coverage only."
            )
        print(f"citation-gate: {len(findings)} finding(s)\n")
        for f in findings:
            print(f)
        print(
            "\nA citation nobody can follow is worse than none: it reports evidence and silences\n"
            "review. This round produced three phantom citations, TWO of them inside correction\n"
            f"blocks written to fix citation errors. A genuine exception carries `{PRAGMA} — <reason>`\n"
            f"on the line or up to {PRAGMA_LOOKBACK} lines above it."
        )
        return 1

    docs = _strict_docs()
    skipped = getattr(_strict_docs, "excluded", 0)
    print(
        f"citation-gate: OK — {len(docs)} strict document(s); every file:line citation resolves"
        + (f" ({skipped} derivation-record file(s) excluded by policy — see EXCLUDED_SUBTREES)"
           if skipped else "")
    )
    return 0


# ── non-vacuity ──────────────────────────────────────────────────────────────

def self_test() -> int:
    """Every rule against input that violates it AND input that must not trip it."""
    tree = Tree(["crates/sim-core/src/types.rs", "docs/a/b.md", "docs/a/b.json",
                 "docs/a/c.tsx", "docs/a/d.jsx", ".github/w/gates.yml", "crates/x/resolve.rs",
                 "crates/y/resolve.rs", "scripts/only_here.py",
                 # REAL files: the C2 and extension cases need a line count, and
                 # `line_count` reads the filesystem rather than this list -- so a
                 # synthetic path would report 0 lines and red on line 1.
                 "scripts/citation-gate.py",
                 "contracts/frontend-tools.contract.json",
                 "frontend/src/app/shell/AppShell.tsx",
                 ".github/workflows/gates.yml"])
    real_lines = tree.line_count

    def count(text: str, rel: str = "docs/a/doc.md") -> list[Finding]:
        return scan_doc(tree, rel, text)

    cases: list[tuple[str, str, int]] = [
        ("C1 a path that matches nothing", "see crates/nope/gone.rs:3", 1),
        ("C1 a suffix match with no line number is a prose mention", "see sim-core/src/types.rs", 0),
        ("C3 a bare name matching two files", "see resolve.rs:84", 1),
        # F6 — the first version of this case carried NO line number, so it
        # exited at the prose guard and never reached `Tree.resolve` at all.
        ("C3 a bare name matching one file resolves", "see citation-gate.py:1", 0),
        ("a bare name with NO line is prose, not a citation", "the old handoffs.md is deleted", 0),
        ("C4 a dead relative link", "[x](nowhere.md)", 1),
        ("a URL is not a path", "[x](https://example.com/a.md)", 0),
        ("a bare github URL is not a path", "see github.com/o/r/blob/main/docs/X.md", 0),
        ("an anchor-only link is not a path", "[x](#section)", 0),
        (f"the pragma on the line", f"see crates/nope/gone.rs:3 <!-- {PRAGMA} — reason -->", 0),
        (f"the pragma two lines above", f"<!-- {PRAGMA} — reason -->\n\nsee crates/nope/gone.rs:3", 0),
        # F1 — the flagship defect class, which walked straight through.
        ("C2 a reversed range", "see scripts/citation-gate.py:99999-2", 1),
        ("C2 line zero", "see scripts/citation-gate.py:0", 1),
        ("C2 a valid range", "see scripts/citation-gate.py:1-2", 0),
        # F2 — dead alternation branches made these commit-blocking false positives.
        ("a .json citation is not truncated to .js", "see contracts/frontend-tools.contract.json:3", 0),
        ("a .tsx citation is not truncated to .ts", "see frontend/src/app/shell/AppShell.tsx:3", 0),
        # F3 — a leading dot was truncated and the result reported missing.
        ("a dotfile directory resolves", "see .github/workflows/gates.yml:3", 0),
        # F4 — a Windows path degraded to its basename and resolved elsewhere.
        ("a Windows-style path is a path, not a bare name", "see crates\\made\\up\\resolve.rs:1", 1),
        # F13
        ("a separator in a line number is refused", "see docs/a/b.md:9_99999", 1),
        # F9b — trailing junk silently truncated the line number. These cite a
        # REAL file with enough lines: the first version used `docs/a/b.md`,
        # which exists only in the fake tree, so `line_count` returned 0 and
        # `C2-past-eof` fired with or without the rule under test. Both cases
        # passed with the rule DELETED — a self-test that could not fail, in the
        # file whose header enshrines NV-1.
        ("an exponent after a line number is refused", "see scripts/citation-gate.py:1e9", 1),
        ("a letter glued to a line number is refused", "see scripts/citation-gate.py:1abc", 1),
        # F14 — Python's `\d` matches every Unicode decimal, so `:1٣` was
        # absorbed as line 13 and passed. `[0-9]` stops at the ASCII digit and
        # the trailing-junk rule then sees the rest.
        ("a unicode digit glued to a line number is refused",
         "see scripts/citation-gate.py:1٣", 1),
        # ...and `+` is NOT junk: `file.py:125+` means "and following" and is used
        # 26 times in this repo. Refusing it blocked commits on correct prose.
        ("a trailing + means 'and following' and is allowed", "see scripts/citation-gate.py:1+", 0),
        ("a trailing comma is ordinary punctuation", "see scripts/citation-gate.py:1, and", 0),
        # F9a — the jsx branch was dead behind js, exactly as tsx was behind ts.
        ("a .jsx citation keeps its extension and its line", "see crates/nope/gone.jsx:3", 1),
        # F9c — reference-style links were wholly uncovered.
        ("a dead reference-style link definition is caught", "[ref]: nowhere.md", 1),
        # F4 — `Tree._dirs`: a link to a DIRECTORY is legitimate, and `git
        # ls-files` never lists one. Deleting the `_dirs` population left the
        # whole self-test green while changing 258 verdicts on the live corpus.
        ("a link to a directory that exists resolves", "[x](../../scripts)", 0),
        ("a link to a directory that does not exist is caught", "[x](../../nope-dir)", 1),
        # F6 — a placeholder must be skipped by BOTH link arms, not one.
        ("a placeholder inline link is skipped", "[x](docs/nope*.md)", 0),
        ("a placeholder reference definition is skipped too", "[ref]: docs/nope*.md", 0),
        # A markdown link QUOTED inside backticks is a quotation, not a link.
        # The exclusion is on the LINK rules only -- applying it to citations
        # would blind the gate, since this repo writes almost every citation in
        # backticks. An earlier version wired it to a no-op loop that iterated
        # the links, skipped the spans and then did nothing at all.
        ("a link quoted inside backticks is not a link", "`[x](nowhere.md)`", 0),
        ("...but the same link outside backticks still reds", "[x](nowhere.md)", 1),
        ("a CITATION in backticks is still checked", "see `crates/nope/gone.rs:3`", 1),
        # F3 — a citation with no line number is a prose mention, ANCHORED or not.
        ("an anchored path with no line number is a plan naming a file to create",
         "| P1 | `services/x/tests/test_probe_new.py` | Test to WRITE |", 0),
        ("...but with a line number it must exist", "see services/x/nope.py:3", 1),
        # F1 — a citation inside a fence is still a citation.
        ("a real citation inside a code fence is still checked",
         "```\nsee crates/nope/gone.rs:3\n```", 1),
        # F2 — the link-text skip must not disable the LINE-EXISTS rule.
        ("a link's text is not reported unresolvable",
         "[`gone.rs:3`](../../scripts/citation-gate.py)", 0),
        ("...but a link's text with a line past EOF still reds",
         "[`citation-gate.py:99999`](../../scripts/citation-gate.py)", 1),
        # F3 — the eleven false positives this rule produced on correct content.
        ("a budget table row is not a link definition", "[SYSTEM]: 1240 tokens (template-defined),", 0),
        # ...and one that ONLY the trailing `\s*$` anchor refuses: a path-shaped
        # first token followed by more prose is a sentence, not a definition.
        ("a definition-shaped line with trailing prose is prose", "[note]: crates/x/resolve.rs is the entry", 0),
        ("a TypeScript index signature is not a link definition", "  [k: string]: unknown;", 0),
        ("a numeric range row is not a link definition", "[1024,16384]: 1024,", 0),
        # A footnote's target ("see") also fails the path-shape filter, so this
        # case is double-guarded. It is kept as behaviour, and the `(?!\^)` guard
        # gets a case only it can satisfy: a footnote whose text IS path-shaped.
        ("a footnote is not a link definition", "[^1]: see the appendix", 0),
        ("a footnote whose text looks like a path is still not a link", "[^1]: crates/x/resolve.rs", 0),
        # A table row still is not a link definition, but the reason is `^\s*\[`
        # and NOT a dedicated guard — see the note on LINK_DEF_RE. Kept as a
        # behaviour case, with its true mechanism named.
        ("a table row is not a link definition (via the line anchor)", "| [x]: y | z |", 0),
        # ...and one that ONLY the `^` anchor refuses: an indented table row whose
        # target IS path-shaped and does NOT resolve, so every other narrowing
        # would let it through. The previous case was double-guarded and stayed
        # green with the anchor deleted -- a vacuous case replacing a vacuous case.
        ("an indented table row with a dead path-shaped target is still not a link",
         "  | [ref]: crates/nope/gone.rs | x |", 0),
        # F4 — an angle-bracketed URL was reported as a dead repo file, in BOTH
        # link rules, because the scheme lookahead backtracked past the `<`.
        ("an angle-bracketed URL definition is external", "[ref]: <https://example.com/x.md>", 0),
        ("an angle-bracketed URL link is external", "[x](<https://example.com/a.md>)", 0),
        ("an angle-bracketed mailto is external", "[x](<mailto:a@b.com>)", 0),
        ("a file:// link is external", "[x](file:///c:/tmp/x.md)", 0),
        ("a tel: link is external", "[x](tel:+123)", 0),
        ("a template placeholder is not a link to check", "[L<N>_x.md](dir/L<N>_x.md)", 0),
        # F1 — the two classes that produced the entire cry-wolf surface.
        ("a citation that is a link's TEXT resolves through its href",
         "[`coverage.py:67+`](b.md)", 0),
        ("...but a bare unanchored citation outside a link still reds",
         "see resolve.rs:84", 1),
        ("a live reference-style link definition is fine", "[ref]: ../../scripts/citation-gate.py", 0),
        # F15
        ("a `..` segment is normalised", "see docs/x/../../scripts/citation-gate.py:3", 0),
        # F8
        ("a dead link with a title is still caught", "[x](nowhere.md 'title')", 1),
        ("an angle-bracket link to a real file is fine", "[x](<../../scripts/citation-gate.py>)", 0),
        # F9
        ("an absolute link escapes the repo", "[x](/etc/passwd)", 1),
        ("a drive-qualified link escapes the repo", "[x](C:/Windows/system32)", 1),
        ("a parent-escaping link escapes the repo", "[x](../../../../etc/passwd)", 1),
        # F10
        ("a pragma with no reason does not silence", f"see crates/nope/gone.rs:3 <!-- {PRAGMA} -->", 1),
        ("the pragma quoted in prose does not silence", f"the pragma is `{PRAGMA} — like this`\n\n\nsee crates/nope/gone.rs:3", 1),
    ]
    failures = 0
    for name, text, expected in cases:
        got = len(count(text))
        ok = got == expected
        failures += 0 if ok else 1
        print(f"  {'ok ' if ok else 'FAIL'} {name}: expected {expected}, got {got}")

    # The repo-escape rule needs its VERDICT asserted, not just a finding count:
    # both the escape arm and the does-not-resolve arm produce exactly one
    # finding, so every count-only case stayed green with the whole rule deleted.
    live0 = Tree.from_git()
    for text, want in [
        ("[x](/etc/passwd)", "escapes the repository"),
        ("[x](C:/Windows/system32)", "escapes the repository"),
        ("[x](../../../../etc/passwd)", "escapes the repository"),
        ("[x](nowhere-at-all.md)", "does not resolve"),
    ]:
        got = scan_doc(live0, "docs/a/doc.md", text)
        detail = got[0].detail if got else "<no finding>"
        ok = want in detail
        failures += 0 if ok else 1
        print(f"  {'ok ' if ok else 'FAIL'} escape verdict for {text}: {detail[:60]}")

    # C2 needs a real file, so it is measured against this script itself.
    live = Tree.from_git()
    me = "scripts/citation-gate.py"
    n = live.line_count(me)
    past = len(scan_doc(live, "docs/t.md", f"see {me}:{n + 500}"))
    inside = len(scan_doc(live, "docs/t.md", f"see {me}:{max(1, n - 1)}"))
    if past != 1:
        failures += 1
        print(f"  FAIL C2 did not bite on a line past EOF (got {past})")
    else:
        print("  ok  C2 bites on a line past end-of-file")
    if inside != 0:
        failures += 1
        print(f"  FAIL C2 cried wolf on a line inside the file (got {inside})")
    else:
        print("  ok  C2 is silent on a line inside the file")

    # The pragma window must be BOUNDED, or one pragma silences a whole document.
    far = f"<!-- {PRAGMA} — reason -->\n\n\n\nsee crates/nope/gone.rs:3"
    if len(count(far)) != 1:
        failures += 1
        print("  FAIL the pragma window is unbounded")
    else:
        print("  ok  the pragma window is bounded at 3 lines")

    # The scope must be a directory walk, or a document written tomorrow is
    # default-uncovered (NV-3).
    file_scoped = [t for t in STRICT_TREES if t.endswith(".md")]
    if file_scoped:
        failures += 1
        for t in file_scoped:
            print(f"  FAIL STRICT_TREES contains a FILE ({t}); the strict scope must be directories")
    else:
        # This was a `for/else` with no `break`, so the `else` ran unconditionally
        # and printed `ok` on the same run as its own FAIL. A non-vacuity
        # self-test that reports green for a rule it just failed is the exact
        # costume the standard is named after.
        print("  ok  the strict scope is directories, not a file list")

    _ = real_lines
    if failures:
        print(f"\ncitation-gate --self-test: {failures} rule(s) did not behave")
        return 1
    print("\ncitation-gate --self-test: every rule bites, and none cries wolf")
    return 0


if __name__ == "__main__":
    sys.exit(main())
