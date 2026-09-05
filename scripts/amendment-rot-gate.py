#!/usr/bin/env python3
"""amendment-rot-gate — an amendment row that nothing watches is a wish with a number on it.

WHAT THIS EXISTS TO ACT ON (measured 2026-07-30)
------------------------------------------------
The PO asked: *"PROPOSED rồi chả dùng, có khi lại bị trôi và kiến trúc thì rot"* —
proposed and then never used, drifting while the architecture rots. It was measured
rather than argued, across the `LLM_MMO_RPG` design track:

  · **15 of 25 `WSA-R*` amendment ids were UNGREPPABLE.** Docs 31 and 32 wrote
    their rows as bare `**R01**` … `**R24**`, with no prefix. An id you cannot
    grep cannot be tracked, audited, or closed. Corpus-wide greppable amendment
    ids went 37 -> 52 the moment this was fixed.

  · **SIX stable-ID prefixes had never been registered at all** — `XST` `PRD`
    `ONT` `EXC` `WSA` `QTY`, introduced by docs 27-35. Unlike the four prior
    RECORD CORRECTIONs in `_boundaries/_LOCK.md`, these docs asserted nothing
    false; they were simply invisible to `01_feature_ownership_matrix.md`, which
    is the file that is supposed to BE the inventory.

  · **A gated batch did not run at its gate.** `19_reconciliation_register.md`
    §15 routed five boundary registrations to *"next `_boundaries` lock claim —
    one batch"*. The next claim happened and did not do them. Root cause is the
    gate's shape, not the claimant's care: *"the next lock claim"* names an
    OCCASION, not an OWNER, so it belongs to nobody and the claimant has no
    reason to open the file that gated it. Recorded as REC-92.

  · And in the other direction: **three rows were already SHIPPED while still
    reading as open** (`XST-R1/R2/R3`, all delivered by the ruleset-core arc).
    Debt already paid that keeps ringing is worse than unpaid debt — it makes
    real work look like backlog and hides how much is genuinely left.

    Intent is not a mechanism. `boundaries-lock-gate` and `deferral-gate`
    exist because the same conclusion was reached twice before. This is
    the third.

WHAT IT CHECKS
--------------
A — PREFIX HYGIENE. No amendment row may carry a bare `**R<n>**` id. Every row
    id must be `PREFIX-R<n>`, so it is greppable from anywhere in the corpus.
    (This is exactly the defect found on 2026-07-30 and fixed in docs 31 + 32.)

B — PREFIX REGISTRATION. Every `PREFIX-R<n>` appearing in the track must have a
    `` `PREFIX-*` `` row in `_boundaries/01_feature_ownership_matrix.md`. The
    matrix is declared the inventory; a prefix absent from it is invisible.

    WHY THIS IS NOT A DUPLICATE OF `design-lint`. That lint already has an
    `unregistered-prefix` check, and it reported **0 findings** while seven
    prefixes were unregistered. It was not broken and it was not vacuous — it
    validates against a DIFFERENT registry: `00_foundation/06_id_catalog.md`.
    All seven prefixes WERE in the catalog; none was in the matrix. The corpus
    keeps two registries and each gate saw only one.

    Its sibling `phantom-registration` was silent for a second, also-correct
    reason: it fires on a line that CLAIMS "(registered …)" for a prefix absent
    from the matrix — the four RECORD CORRECTIONs in `_LOCK.md`. These docs
    claimed nothing, so there was nothing false to catch.

    So the three checks are complementary, not overlapping:
      design-lint symbol        : prefix known to the ID CATALOG?
      design-lint registration  : a registration CLAIM that is false?
      this check                : prefix present in the OWNERSHIP MATRIX?
    The gap that let seven prefixes through was exactly the third question,
    which nothing was asking.

C — GATED-QUEUE DISCHARGE. Items the reconciliation register routes to a
    boundary-registration queue must each appear in the matrix, or be named
    there with an explicit blocked-reason. Parsed from the register, not
    hardcoded, so adding a queue item automatically extends the check.

D — RETIRED-IDENTIFIER CONTAINMENT (added 2026-07-30, REC-97). An identifier a
    sealed doc declares RETIRED may appear only on a line that CITES the
    retirement. Added because the matrix claimed three amendments applied when
    two had never been touched and the third — `SPG-R1`, retiring `ChannelTier`
    — had reached 2 of ~72 sites, leaving a **half-rename**: both vocabularies
    live in one file, and the matrix reporting coverage it did not have. Armed
    with an EMPTY allowlist (the sweep was completed first) because an
    enumerated exemption list is silent about the site added tomorrow. Two
    structural exemptions only: the doc that DECLARES the retirement, and the
    append-only histories (`SESSION_HANDOFF.md`, `_boundaries/99_changelog.md`) —
    both listed in `_HISTORY_DOCS`, because a docstring that names fewer
    exemptions than the code has is an UNdocumented hole, and this one said one.
    SCOPE LIMIT, stated rather than implied: it reads `*.md` under the track only.
    A retired identifier reappearing in `crates/`/`services/` is NOT covered. Today
    that is a boundary and not a hole — `MapKind` is unimplemented, so the subject
    cannot occur in code yet (NV-2). It becomes a hole the day `MapKind` lands:
    tracked as `D-RETIRED-IDENT-CODE-SCOPE`.

Each check is BITE-TESTED in `--selftest`: it constructs the exact defect it
claims to catch and asserts the check goes red. A check that cannot fail is not
a check (docs/standards/non-vacuity.md NV-1). Check D additionally bite-tests
that its escape hatch REACHES ITS REASON (NV rule 4) — a citing line passes, a
bare mention does not — because a hatch that works unconditionally is theatre.

USAGE
-----
    python scripts/amendment-rot-gate.py            # scan; exit 1 on any finding
    python scripts/amendment-rot-gate.py --selftest # prove each check can fail
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRACK = ROOT / "docs" / "03_planning" / "LLM_MMO_RPG"
MATRIX = TRACK / "_boundaries" / "01_feature_ownership_matrix.md"
REGISTER = TRACK / "19_reconciliation_register.md"

# A qualified amendment id: `WSA-R19`, `SPG-R1`, `XST-R13`.
QUALIFIED = re.compile(r"\b([A-Z]{2,4})-R(\d+)\b")

# A table row whose first cell is a BARE amendment id — `| **R19** | ...`.
# This is the ungreppable shape. `\*\*R\d` and nothing before it but the pipe.
BARE_ROW = re.compile(r"^\|\s*\*\*R(\d+)\*\*")

# A prefix registration in the matrix: a cell containing `` `WSA-*` ``.
def _prefix_registered(matrix_text: str, prefix: str) -> bool:
    return f"`{prefix}-*`" in matrix_text


def _rel(p: Path) -> str:
    """Repo-relative path, falling back to the absolute one.

    The fallback is load-bearing for `--selftest`, which builds fixture files in a
    temp dir outside the repo. Without it the selftest crashed instead of running —
    i.e. the bite test could not bite, which is the very failure this gate is about.
    """
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def _track_docs() -> list[Path]:
    """Design docs in the track. Excludes `_boundaries/` (the inventory itself)."""
    out = []
    for p in sorted(TRACK.rglob("*.md")):
        if "_boundaries" in p.parts:
            continue
        out.append(p)
    return out


# ── Check A ───────────────────────────────────────────────────────────────────
def check_bare_ids(docs: list[Path]) -> list[str]:
    """Flag bare `**R<n>**` ids — but ONLY inside an amendment table.

    FALSE POSITIVE THIS NARROWING KILLS (found by the gate's own first run, against
    its author): `TMP_008b_llm_contract_spec.md` has a `| Rule | Check |` table whose
    rows are validation rules `**R1**..**R5**`. Those are correctly scoped to their
    table and are not amendment ids at all — renaming them would have been damage
    done by a gate that was too eager.

    The discriminator is the table HEADER. Every amendment table in this corpus is
    `| # | Target | Change | Confidence |`; a rules table is not. So the check arms
    itself only after seeing a header containing `Target`, and disarms at the next
    header or blank line. This keeps it able to fail (it still reds on docs 31/32/33/34)
    while removing the class it should never have flagged.
    """
    findings = []
    for p in docs:
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        in_amendment_table = False
        for n, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("|"):
                # A header row names its columns; an amendment table names `Target`.
                if "---" not in stripped and "Target" in stripped:
                    in_amendment_table = True
                    continue
            elif not stripped:
                in_amendment_table = False
                continue
            if not in_amendment_table:
                continue
            m = BARE_ROW.match(line)
            if m:
                rel = _rel(p)
                findings.append(
                    f"{rel}:{n}: bare amendment id `**R{m.group(1)}**` — "
                    f"an id without its prefix is ungreppable, therefore untrackable. "
                    f"Use `**XXX-R{m.group(1)}**` with the doc's registered prefix."
                )
    return findings


# ── Check B ───────────────────────────────────────────────────────────────────
def check_prefix_registration(docs: list[Path], matrix_text: str) -> list[str]:
    seen: dict[str, str] = {}  # prefix -> first "file:line" that used it
    for p in docs:
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for n, line in enumerate(lines, 1):
            for m in QUALIFIED.finditer(line):
                seen.setdefault(m.group(1), f"{_rel(p)}:{n}")

    findings = []
    for prefix, where in sorted(seen.items()):
        if not _prefix_registered(matrix_text, prefix):
            findings.append(
                f"{where}: prefix `{prefix}-*` is used by an amendment row but has NO row in "
                f"{MATRIX.relative_to(ROOT).as_posix()}. The matrix is the declared inventory; "
                f"a prefix missing from it is invisible to every audit that reads the inventory. "
                f"(Six prefixes sat like this from docs 27-35 until 2026-07-30.)"
            )
    return findings


# ── Check C ───────────────────────────────────────────────────────────────────
GATED_ROW = re.compile(r"^\|\s*\*\*Boundary registrations\*\*\s*\|(?P<items>.*?)\|", re.S)


def _gated_items(register_text: str) -> list[str]:
    """Backtick-quoted tokens in the register's boundary-registration queue row.

    Parsed rather than hardcoded so that adding a queue item extends this check
    automatically — a hardcoded list would rot the same way the queue did.
    """
    for line in register_text.splitlines():
        m = GATED_ROW.match(line)
        if m:
            return re.findall(r"`([^`]+)`", m.group("items"))
    return []


def check_gated_queue(register_text: str, matrix_text: str) -> list[str]:
    findings = []
    for item in _gated_items(register_text):
        # `ruleset.*` in the queue is a namespace token; the matrix registers it
        # by name. Strip a trailing `.*` / `*` so both spellings match.
        needle = item.rstrip("*").rstrip(".")
        if not needle:
            continue
        if needle not in matrix_text:
            findings.append(
                f"{REGISTER.relative_to(ROOT).as_posix()}: gated boundary registration `{item}` "
                f"is still absent from {MATRIX.relative_to(ROOT).as_posix()}. The register routed it "
                f'to "next `_boundaries` lock claim" — an OCCASION, not an OWNER, which is why it was '
                f"missed once already (REC-92). Register it, or name it in the matrix with an "
                f"explicit blocked-reason."
            )
    return findings


# ── selftest (NV-1: prove each check can fail) ────────────────────────────────
def selftest() -> int:
    import tempfile

    failures = []

    # A — construct the exact defect docs 31/32 carried.
    with tempfile.TemporaryDirectory() as td:
        hdr = "| # | Target | Change | Confidence |\n|---|---|---|---|\n"
        bad = Path(td) / "fake.md"
        bad.write_text(hdr + "| **R19** | `EF_001` | add a variant | verified |\n", encoding="utf-8")
        if not check_bare_ids([bad]):
            failures.append("A: bare-id check did NOT red on `| **R19** |` in an amendment table")
        good = Path(td) / "ok.md"
        good.write_text(hdr + "| **WSA-R19** | `EF_001` | add a variant | verified |\n", encoding="utf-8")
        if check_bare_ids([good]):
            failures.append("A: bare-id check reded on a correctly-prefixed row (false positive)")
        # The narrowing itself must be bite-tested, or it silently disarms check A.
        rules = Path(td) / "rules.md"
        rules.write_text(
            "| Rule | Check |\n|---|---|\n| **R1** | Every input zone_id has a narration |\n",
            encoding="utf-8",
        )
        if check_bare_ids([rules]):
            failures.append("A: reded on a `| Rule | Check |` table — the TMP_008b false positive is back")

    # B — a used prefix that the matrix does not carry.
    with tempfile.TemporaryDirectory() as td:
        doc = Path(td) / "fake.md"
        doc.write_text("see `ZZZ-R7` for the amendment\n", encoding="utf-8")
        if not check_prefix_registration([doc], "matrix with no ZZZ row"):
            failures.append("B: registration check did NOT red on an unregistered prefix")
        if check_prefix_registration([doc], "row: `ZZZ-*` owns it"):
            failures.append("B: registration check reded on a registered prefix (false positive)")

    # C — a queue item absent from the matrix.
    reg = "| **Boundary registrations** | `Foo:Bar` · `baz.*` namespace | next claim |\n"
    if not check_gated_queue(reg, "matrix containing baz but not the other one"):
        failures.append("C: gated-queue check did NOT red on a missing registration")
    if check_gated_queue(reg, "matrix containing Foo:Bar and baz"):
        failures.append("C: gated-queue check reded when both were present (false positive)")

    # D — a retired identifier used live, and the three ways it is legitimate.
    with tempfile.TemporaryDirectory() as td:
        live = Path(td) / "live.md"
        live.write_text("    pub tier: ChannelTier,\n", encoding="utf-8")
        if not check_retired_identifiers([live]):
            failures.append("D: retired-identifier check did NOT red on a live `ChannelTier` use")
        # The escape hatch must REACH ITS REASON (NV rule 4): citing the amendment
        # row is what makes the mention legitimate. If this passed without the
        # citation, the hatch would be unconditional and the check theatre.
        cited = Path(td) / "cited.md"
        cited.write_text("    pub kind: MapKind,   // SPG-R1: was ChannelTier\n", encoding="utf-8")
        if check_retired_identifiers([cited]):
            failures.append("D: reded on a line citing SPG-R1 — the escape hatch does not work")
        # …and it must not be satisfied by an unrelated word. If a bare mention
        # passed, every site would self-exempt and the sweep would have been
        # pointless.
        bare = Path(td) / "bare.md"
        bare.write_text("the ChannelTier ladder is fine actually\n", encoding="utf-8")
        if not check_retired_identifiers([bare]):
            failures.append("D: did NOT red on a bare prose mention with no retirement citation")
        # The DECLARING doc is exempt by structure, not by site list.
        decl = Path(td) / "36_map_architecture.md"
        decl.write_text("ChannelTier = Continent|Country|District|Town|Cell\n", encoding="utf-8")
        if check_retired_identifiers([decl]):
            failures.append("D: reded inside the declaring doc, which must be able to name what it retires")
        # SCOPE. Check D's first version reused `_track_docs()`, which EXCLUDES
        # `_boundaries/` — correct for A/B/C, silently wrong here, and it certified
        # a machine contract that still carried the dead type. The scope must
        # REACH the highest-value directory, so assert that rather than trusting it.
        scope = _retired_scan_docs()
        if not any("_boundaries" in p.parts for p in scope):
            failures.append(
                "D: scope does not reach `_boundaries/` — the machine contracts live there, "
                "and a green gate that skips them certifies the one place a reader most wants checked"
            )
        # CITATION PROXIMITY. On a 12 401-character line (the `geography.*` row) a
        # line-wide match let one unrelated `was` exempt every claim on it.
        far = Path(td) / "far.md"
        far.write_text("was " + ("filler " * 60) + "ChannelTier\n", encoding="utf-8")
        if not check_retired_identifiers([far]):
            failures.append("D: a citation ~420 chars away still excused the use — window not enforced")
        # ML-4 (docs/standards/multilingual.md): the hatch must not be Latin-only.
        # This corpus is BILINGUAL — GEO_001's reject messages are Vietnamese and the
        # PO's decisions are quoted in Vietnamese throughout docs 36/37. The first
        # version ALLOWED "the field was ChannelTier" and BLOCKED "ChannelTier đã bị
        # khai tử": it degraded CLOSED against non-English prose, which forces English
        # into design docs — exactly what ML-4 forbids. Found by /review-impl.
        for label, text in (
            ("vi-diacritics", "ChannelTier đã bị khai tử\n"),
            ("vi-ascii", "truong nay truoc day la ChannelTier\n"),
            ("ja", "ChannelTier は廃止\n"),
        ):
            f = Path(td) / f"{label}.md"
            f.write_text(text, encoding="utf-8")
            if check_retired_identifiers([f]):
                failures.append(
                    f"D: blocked a {label} retirement note — the citation hatch is "
                    f"Latin-only, which is ML-4 (never ship a Latin-only regex as the check)"
                )
        # …and CASE. `\bwas\b` lowercase-only let "it WAS" through on SPIKE_04.
        upper = Path(td) / "upper.md"
        upper.write_text("it WAS a ChannelTier enum\n", encoding="utf-8")
        if check_retired_identifiers([upper]):
            failures.append("D: citation matching is case-sensitive — 'WAS' must count as much as 'was'")

    # E - a RETIRED AMENDMENT ROW cited as if live.
    #
    # Fixtures come in PAIRS: the declaring doc (which may name its own row
    # freely) and a citing doc. One file cannot test this, because the
    # declaring-doc exemption would swallow the citation.
    with tempfile.TemporaryDirectory() as td:
        NL = chr(10)
        decl = Path(td) / "owner.md"
        decl.write_text(
            "| ~~**ZZZ-R2**~~ | ~~narrow the field~~ **RETIRED 2026-01-01** |" + NL +
            "| ~~**ZZZ-R7**~~ | ~~relax the cap~~ **RETIRED 2026-01-01** |" + NL,
            encoding="utf-8",
        )
        if len(discover_retired_rows([decl])) != 2:
            failures.append("E: discovery did not find both struck rows in the declaring doc")

        live = Path(td) / "cite.md"
        live.write_text("the field is narrowed to `MapKind` (`ZZZ-R2`)." + NL, encoding="utf-8")
        if not check_retired_rows([decl, live]):
            failures.append("E: did NOT red on a retired amendment row cited as current")

        ok = Path(td) / "ok.md"
        ok.write_text("`ZZZ-R2` was retired before it was applied." + NL, encoding="utf-8")
        if check_retired_rows([decl, ok]):
            failures.append("E: reded on a citation that names the retirement (false positive)")

        # THE DISCRIMINATING CASE, and the whole reason the window is
        # segmented. This is `36_map_architecture.md:147` verbatim in shape: a
        # LIVE row's retirement word sits ~40 characters from a RETIRED row's
        # id. A plain +/-160 window PASSES it, which is how the real defect
        # survived three months. If this assertion ever goes green by default,
        # the segmentation is disarmed and check E is worth nothing.
        adjacent = Path(td) / "adjacent.md"
        adjacent.write_text(
            "`ChannelTier` is retired (`ZZZ-R1`) and `level_name` is narrowed "
            "to `MapKind` (`ZZZ-R2`)." + NL,
            encoding="utf-8",
        )
        if not check_retired_rows([decl, adjacent]):
            failures.append(
                "E: a NEIGHBOURING live row's retirement word excused a retired "
                "row - the segmented window is disarmed, which is the exact "
                "defect check E was written for"
            )

        # ...and the converse half of the same rule: two RETIRED rows cited
        # together share one marker legitimately. Clipping between them
        # produced a false positive on the ownership matrix on the first run.
        together = Path(td) / "together.md"
        together.write_text(
            "twice before (`ZZZ-R2`/REC-93, `ZZZ-R7`/REC-96) a row marked "
            "verified died on contact with its target." + NL,
            encoding="utf-8",
        )
        if check_retired_rows([decl, together]):
            failures.append("E: two retired rows sharing one marker reded (false positive)")

        hatched = Path(td) / "hatched.md"
        hatched.write_text(
            "the field is narrowed by `ZZZ-R2`.  amendment-rot-gate: ok - quoting "
            "the superseded text on purpose" + NL,
            encoding="utf-8",
        )
        if check_retired_rows([decl, hatched]):
            failures.append("E: the `amendment-rot-gate: ok` pragma did not exempt the line")

        # META-BITE: with nothing retired anywhere, the check MUST report that
        # it cannot fail rather than reporting success.
        empty = Path(td) / "empty.md"
        empty.write_text("nothing is retired here" + NL, encoding="utf-8")
        if not check_retired_rows([empty]):
            failures.append(
                "E: an EMPTY retired set returned OK - a vacuous check that "
                "certifies is worse than a missing one (NV-1)"
            )
    if failures:
        print("SELFTEST FAILED — a check that cannot fail is not a check (NV-1):")
        for f in failures:
            print(f"  ✗ {f}")
        return 1
    print("amendment-rot-gate selftest: OK — all 5 checks red on their defect and green without it")
    return 0


# ── check D — retired-identifier containment ─────────────────────────────────
#
# THE BUG THIS EXISTS TO PREVENT, measured 2026-07-30 (REC-97).
# `_boundaries/01_feature_ownership_matrix.md` claimed "Applied so far: SPG-R1 ·
# SPG-R3 · SPG-R5". All three claims were false. Two rows had never been touched
# (their targets said so correctly — GEO_001 "until SPG-R3 is applied", CSC_001
# "PROPOSED, not applied"). The third, SPG-R1, was applied to **2 of ~72 sites**:
# two struct fields were renamed and the `ChannelTier` enum struck through, while
# ~70 dependent sites kept the retired type — including FOUR fields of the
# `RealityManifest` MACHINE CONTRACT, a ruleset field key, and two acceptance
# criteria (one of which, AC-MAP-3, asserted exhaustiveness over an enum that no
# longer existed, so it could not fail).
#
# A HALF-RENAME IS WORSE THAN NO RENAME. The file then carries both vocabularies
# with nothing marking which sites are outstanding, and the matrix reports
# coverage it does not have — the same shape as a check that cannot fail.
#
# WHY THE ALLOWLIST IS EMPTY, AND STAYS EMPTY. Seeding it with the ~70 sites as
# they stood would be the *default-uncovered* anti-pattern named in
# docs/standards/non-vacuity.md: an enumerated list is silent about the site
# somebody adds tomorrow. So the sweep was completed FIRST and the gate armed
# against zero exemptions. If a retired identifier reappears anywhere, it reds.
#
# THE ESCAPE HATCH REACHES ITS REASON (NV rule 4). A retired name legitimately
# appears in the note explaining its own retirement — "was `ChannelTier`",
# "~~ChannelTier~~", "⛔ RETIRED". Those lines are allowed BECAUSE they cite the
# retirement; a bare live use does not, and reds. The hatch cannot be used
# without naming the reason it is being used.
#
# TWO EXEMPTIONS, BOTH STRUCTURAL — NEITHER IS A SITE LIST.
#   (1) The DECLARING doc. The doc that retires an identifier must be able to name
#       it: doc 36 §7 IS the retirement register, and its rationale quotes the dead
#       enum's variants verbatim. Derived from the data (the value below), not from
#       an enumeration of places.
#   (2) SESSION_HANDOFF. An append-only history whose past entries must describe
#       the vocabulary of their time; rewriting them would falsify the record. This
#       is the same line `deferral-gate.py` already draws — "ids OUTSIDE this block
#       are history, not obligations". The LIVE specs are what this check governs.
# Everything else must cite the retirement to mention the name.
RETIRED_IDENTS: dict[str, tuple[str, str]] = {
    "ChannelTier": (
        "retired by SPG-R1 (36_map_architecture.md §7) and replaced by the MapKind "
        "closed set + containment matrix; applied across the corpus 2026-07-30",
        "36_map_architecture.md",
    ),
}
# Append-only histories, matched by TRACK-RELATIVE PATH rather than basename.
# Basename matching would silently exempt any future `SESSION_HANDOFF.md` added
# anywhere under the track — a default-uncovered set, which is the NV shape this
# gate is otherwise built to refuse.
_HISTORY_DOCS = {"SESSION_HANDOFF.md", "_boundaries/99_changelog.md"}
# How near a retirement citation must be to the occurrence it excuses.
# Line-wide matching was wrong: the geography.* namespace row is 12 401
# characters, so one stray `was` would have exempted every claim on it.
_CITE_WINDOW = 160
# A line may mention a retired identifier only while citing the retirement.
_RETIRE_CITATION = re.compile(
    # ── LANGUAGE-NEUTRAL, and these are the CANONICAL hatch (ML-4) ──
    r"[A-Z]{2,5}-R\d+"            # an amendment row id (SPG-R1, WSA-R19, …)
    r"|~~"                        # struck-through
    r"|⛔"
    # ── per-language convenience terms; NOT the only way to cite ──
    r"|retired|superseded|deprecated"
    r"|\b(?:was|were|had)\b"      # "was `ChannelTier`", "had 5 V1 variants"
    r"|khai tử|khai tu"           # vi: retired
    r"|đã bỏ|da bo|đã thay|da thay|thay thế|thay the"   # vi: dropped / replaced
    r"|trước đây|truoc day"       # vi: formerly
    r"|廃止|已废弃|已棄用",         # ja / zh-Hans / zh-Hant: abolished / deprecated
    # CASE-INSENSITIVE, and that is a fix not a convenience: the first version
    # spelled `\bwas\b` lowercase-only, so `SPIKE_04`'s "it WAS — MAP_001 §3
    # ChannelTier enum had 5 V1 variants" slipped straight through. A citation
    # vocabulary that depends on capitalisation is a hole with a spellcheck.
    re.I,
)
# ⚠ ML-4 (docs/standards/multilingual.md) — WHY THE LIST ABOVE IS SPLIT.
# The first version's vocabulary was `retired|was|were|had` — Latin-only — on a
# corpus that is BILINGUAL: GEO_001's own reject messages are Vietnamese ("Chỉ nút
# thế giới mới có dữ liệu địa lý"), and the PO's decisions are quoted in Vietnamese
# throughout docs 36/37 and the handoff. Proven by running it: "the field was
# ChannelTier" passed while "ChannelTier đã bị khai tử" was BLOCKED. So an author
# documenting a retirement in Vietnamese could not cite it, and the gate degraded
# CLOSED — pushing English into design prose, which is precisely what ML-4 forbids
# ("never ship a Latin-only regex as the check") and the opposite of ML-1's
# required degrade-open behaviour for an English-only rule on a shared path.
#
# THE FIX IS STRUCTURAL, NOT A LONGER WORD LIST. A word list can never be
# complete, so the CANONICAL hatch is the language-neutral one: cite the amendment
# row id (`SPG-R1`), or mark the name `~~struck-through~~` / `⛔`. Those work in any
# language and are what the corpus should prefer anyway, because an id is greppable
# and a word is not. The per-language terms are a convenience for prose, and adding
# a language means adding a row here — not changing the rule.
#
# NOT COVERED BY `scripts/language-bias-gate.py`: that gate enforces ML-2/ML-3/ML-5
# (naive lower, ASCII tokenizing, ensure_ascii). ML-1/ML-4 has no repo-wide gate —
# `multilingual.md`'s enforcement row points at ONE service's coverage test. So this
# class had no mechanism that could have caught it, which is why it is written down
# here at the site instead of trusted to a checklist.


def _retired_scan_docs() -> list[Path]:
    """Check D's scope — the WHOLE track, `_boundaries/` INCLUDED.

    ⚠ THIS FUNCTION EXISTS BECAUSE OF A BUG IN CHECK D'S FIRST VERSION, found the
    same day by the PO asking "did you clear those rots?" instead of taking the
    green light. Check D originally reused `_track_docs()`, which EXCLUDES
    `_boundaries/` — a correct exclusion for checks A/B/C, since the matrix *is*
    the inventory and scanning it for prefix registration would be circular.
    Check D inherited that exclusion SILENTLY, and `_boundaries/` is precisely
    where the MACHINE CONTRACTS live. So the gate reported OK while
    `02_extension_contracts.md` still carried `invalid_channel_tier (per MAP-2
    ChannelTier::Continent)` in its live rule_id registry.

    This is the second shape in docs/standards/non-vacuity.md — "the scope never
    reaches it" — occurring inside the check written to prevent that very class.
    A green gate whose scope omits the highest-value directory is worse than no
    gate, because it certifies the one place a reader would most want checked.
    Bite-tested below in `--selftest` by asserting the scope CONTAINS a
    `_boundaries/` path.
    """
    return sorted(TRACK.rglob("*.md"))


def check_retired_identifiers(docs: list[Path]) -> list[str]:
    """A retired identifier may appear only on a line citing its retirement.

    NOTE ON LINE GRANULARITY: the citation must appear within `_CITE_WINDOW`
    characters of the occurrence, not merely somewhere on the same line. The
    corpus has lines over 12 000 characters long (the `geography.*` namespace row
    is 12 401), where "anywhere on the line" would let one unrelated `was` exempt
    a hundred distinct claims.
    """
    out: list[str] = []
    for p in docs:
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            track_rel = p.relative_to(TRACK).as_posix()
        except ValueError:
            track_rel = p.name          # selftest fixtures live outside the track
        if track_rel in _HISTORY_DOCS:
            continue
        for name, (why, declaring_doc) in RETIRED_IDENTS.items():
            if name not in text or p.name == declaring_doc:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                if name not in line:
                    continue
                # Every occurrence must be covered by a NEARBY citation, not by
                # one that happens to share a 12 000-character line.
                uncovered = False
                for m in re.finditer(re.escape(name), line):
                    lo = max(0, m.start() - _CITE_WINDOW)
                    hi = min(len(line), m.end() + _CITE_WINDOW)
                    if not _RETIRE_CITATION.search(line, lo, hi):
                        uncovered = True
                        break
                if not uncovered:
                    continue
                line = line[max(0, m.start() - 90): m.end() + 90]
                out.append(
                    f"{_rel(p)}:{lineno}: live use of RETIRED identifier "
                    f"`{name}` — {why}. The line neither cites an amendment row "
                    f"nor marks the name as retired, so it reads as current "
                    f"vocabulary:\n      {line.strip()[:150]}"
                )
    return out



# ── check E — a RETIRED AMENDMENT ROW cited as if it were live ────────────────
#
# WHY THIS EXISTS, and it is measured rather than anticipated. On 2026-08-22 two
# sites were found BY HAND that state a retired amendment's change as fact:
#
#   36_map_architecture.md:147  "`Channel.level_name: String` is narrowed to
#                                `MapKind` (`SPG-R2`)"   -- in an AXIOM BODY
#   MAP_001_map_foundation.md:183  "`SPG-R2` narrows ... and touches a LOCKED
#                                file, so it carries its own claim"  -- FUTURE
#                                TENSE, in a `//` comment, three months after
#                                the row was retired the day it was written.
#
# Check D covers a retired IDENTIFIER (`ChannelTier`). An amendment ROW had no
# equivalent, which is NV-3 -- "the scope never reaches it" -- and the same
# shape check D's own `_retired_scan_docs()` docstring records being caught in.
#
# THREE THINGS MAKE THIS CHECK DIFFERENT FROM D, and each is load-bearing:
#
# 1. THE RETIRED SET IS DISCOVERED, NOT HAND-MAINTAINED. `RETIRED_IDENTS` is a
#    dict someone must remember to update -- acceptable for identifiers, which
#    are rare, and hopeless for amendment rows, which retire in the ordinary
#    course of design. So the set is read from the corpus: a row whose id is
#    struck through on a line that also carries a retirement marker. If that
#    discovery ever returns EMPTY the check is vacuous, so an empty set is
#    itself a FINDING (see `_EMPTY_DISCOVERY`), which is the meta-bite.
#
# 2. THE CITATION VOCABULARY OMITS `[A-Z]{2,5}-R\d+`. Check D's canonical hatch
#    is "an amendment id is nearby". Here the SUBJECT is an amendment id, so
#    reusing that vocabulary would match every occurrence and the check could
#    never fail. Reusing `_RETIRE_CITATION` here would have shipped a gate that
#    is green by construction.
#
# 3. THE WINDOW IS SEGMENTED BY THE NEIGHBOURING IDS, not merely +/-N chars.
#    This is the whole reason the gate has teeth on the real defect. Line 147
#    read:
#        "`ChannelTier` is retired (`SPG-R1`) and `Channel.level_name: String`
#         is narrowed to `MapKind` (`SPG-R2`)."
#    A plain proximity window puts "retired" within 160 characters of `SPG-R2`
#    and the rot passes. The word belongs to `SPG-R1`. So an occurrence's window
#    is clipped at the nearest OTHER amendment id on each side: a citation
#    excuses only the id in whose segment it falls. Bite-tested on that exact
#    line below.
_RETIRED_ROW_DECL = re.compile(r"~~\s*\*{0,2}(?P<id>[A-Z]{2,5}-R\d+)\*{0,2}\s*~~")
_AMENDMENT_ID = re.compile(r"[A-Z]{2,5}-R\d+")
# Deliberately WITHOUT the amendment-id alternative -- see note 2 above.
_ROW_RETIRE_MARK = re.compile(
    r"~~|⛔"
    r"|retir|supersed|deprecat|absorb|correct|reversed|died|mis-diagnos"
    r"|\b(?:was|were|had|proposed)\b"
    # ML-4: the same language-neutral discipline as `_RETIRE_CITATION`. The
    # canonical hatch here is `~~` or `⛔`, which need no vocabulary at all.
    r"|khai tử|khai tu|đã bỏ|da bo|đã thay|da thay|thay thế|thay the"  # doc-language-gate: ok - the vocabulary IS the subject matter
    r"|trước đây|truoc day|廃止|已废弃|已棄用",  # doc-language-gate: ok - ML-4 requires it
    re.I,
)
# An explicit, REASONED hatch, same shape as `doc-language-gate`'s. A bare
# allowlist would be a gate with no teeth; a pragma forces the author to say why
# a retired id reads as current on that line.
_ROW_PRAGMA = re.compile(r"amendment-rot-gate:\s*ok\b")
# Documents whose SUBJECT IS the history of decisions. Excluding them is the
# same line check D draws for `_HISTORY_DOCS`, extended by the two registers
# that exist specifically to record retirements -- a REC register that could not
# name a retired row would be unable to do its job.
_ROW_HISTORY_DOCS = _HISTORY_DOCS | {
    "_boundaries/_LOCK.md",
    "19_reconciliation_register.md",
}
_EMPTY_DISCOVERY = (
    "check E discovered ZERO retired amendment rows, so it cannot fail. Either "
    "`_RETIRED_ROW_DECL` no longer matches how a retirement is written, or the "
    "scan scope stopped reaching the amendment tables. A vacuous check is a "
    "worse outcome than a missing one, because it certifies."
)


def discover_retired_rows(docs: list[Path]) -> dict[str, str]:
    """Amendment ids struck through on a line that also cites a retirement."""
    out: dict[str, str] = {}
    for p in docs:
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line in text.splitlines():
            if not _ROW_RETIRE_MARK.search(line):
                continue
            for m in _RETIRED_ROW_DECL.finditer(line):
                out.setdefault(m.group("id"), p.name)
    return out


def check_retired_rows(docs: list[Path]) -> list[str]:
    retired = discover_retired_rows(docs)
    if not retired:
        return [_EMPTY_DISCOVERY]

    out: list[str] = []
    for p in docs:
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            track_rel = p.relative_to(TRACK).as_posix()
        except ValueError:
            track_rel = p.name
        if track_rel in _ROW_HISTORY_DOCS:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if _ROW_PRAGMA.search(line):
                continue
            ids = [(m.start(), m.end(), m.group(0)) for m in _AMENDMENT_ID.finditer(line)]
            for k, (a, b, name) in enumerate(ids):
                if name not in retired:
                    continue
                # The declaring document may name its own row freely; that is
                # where the retirement is recorded.
                if p.name == retired[name]:
                    continue
                # Clip at a NEIGHBOURING ID ONLY IF THAT ID IS NOT ITSELF
                # RETIRED. The clip exists so one row's marker cannot excuse an
                # UNRELATED row (the `SPG-R1`/`SPG-R2` case in the docstring).
                # Two retired rows cited together -- "(`SPG-R2`/REC-93,
                # `SPG-R7`/REC-96) ... both died on contact" -- legitimately
                # SHARE one marker, and clipping between them flagged that
                # sentence in the ownership matrix. Refined after the check's
                # first real run: the discriminating case is a LIVE neighbour,
                # and both halves are bite-tested in `--selftest`.
                def _clip(idx: int, default: int) -> int | None:
                    if not (0 <= idx < len(ids)):
                        return default
                    return None if ids[idx][2] in retired else (
                        ids[idx][1] if idx < k else ids[idx][0]
                    )

                lo_edge = _clip(k - 1, 0)
                hi_edge = _clip(k + 1, len(line))
                lo = max(lo_edge if lo_edge is not None else 0, a - _CITE_WINDOW)
                hi = min(hi_edge if hi_edge is not None else len(line), b + _CITE_WINDOW)
                if _ROW_RETIRE_MARK.search(line[lo:a] + line[b:hi]):
                    continue
                out.append(
                    f"{_rel(p)}:{lineno}: RETIRED amendment row `{name}` "
                    f"(retired in {retired[name]}) cited as if live — nothing "
                    f"between it and its neighbouring ids marks it retired, so "
                    f"it reads as current or pending work:" + chr(10) + "      "
                    f"{line[max(0, a - 90): b + 90].strip()[:150]}"
                )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true", help="prove each check can fail")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    if not TRACK.is_dir():
        print(f"amendment-rot-gate: track not found at {TRACK} — nothing to check")
        return 0

    matrix_text = MATRIX.read_text(encoding="utf-8") if MATRIX.exists() else ""
    register_text = REGISTER.read_text(encoding="utf-8") if REGISTER.exists() else ""
    docs = _track_docs()

    findings = (
        check_bare_ids(docs)
        + check_prefix_registration(docs, matrix_text)
        + check_gated_queue(register_text, matrix_text)
        + check_retired_identifiers(_retired_scan_docs())
        + check_retired_rows(_retired_scan_docs())
    )

    if findings:
        print(f"amendment-rot-gate: {len(findings)} finding(s)\n")
        for f in findings:
            print(f"  ✗ {f}\n")
        return 1

    ids = set()
    for p in docs:
        try:
            ids.update(QUALIFIED.findall(p.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError):
            continue
    print(
        f"amendment-rot-gate: OK — {len(docs)} docs scanned; "
        f"every amendment id is prefixed, every prefix is registered, "
        f"every gated boundary registration is discharged or named."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
