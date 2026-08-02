#!/usr/bin/env python3
"""injection-coverage-lint.py — enforce SEC-4 / multilingual ML-4 (prompt-
injection defense) from `docs/standards/security.md`:

    "Every untrusted text entering an LLM prompt — including chat-service —
     passes `neutralize_injection` (sdks/python/loreweave_grounding/sanitize.py)."

Full call-graph proof that every retrieved byte reaches the sanitizer is
undecidable statically, so this is a PRAGMATIC module-level heuristic (the same
allowlist-baseline shape as `scripts/ai-provider-gate.py` and
`scripts/prompt-assembly-discipline-lint.sh`):

  A module in an AI service that BOTH
    (a) assembles an LLM prompt — builds a `{"role": "system"|"user"}` message
        or a `messages` list / `SystemMessage(...)`, AND
    (b) folds in RETRIEVED / EXTERNAL / BOOK / GRAPH text — a variable or field
        named like a passage/chunk/snippet/excerpt/book-text/graph-node/
        entity-summary/tool-result/evidence,
  MUST reference the sanitizer somewhere in the module (`neutralize_injection`
  / `neutralize_proposal_text` / `scan_injection`, or an import of an
  `injection_defense` / `sanitize` shim). A module that assembles a prompt from
  retrieved text with NO nearby sanitize call is flagged.

This catches the *shape* of the chat-service hole (SEC-4's named example: an LLM
prompt built from tool-returned / retrieved text with no neutralize pass) and
guards the NEXT such module. It does NOT prove per-variable coverage — a module
that references the sanitizer but forgets one field passes here; that residual
is for review + the SDK's own tests, noted for the reviewer.

BASELINE below records the CURRENT offenders so the lint exits 0 on today's
tree and fails only on a NEW unsanitized assembly module. chat-service is the
known hole (being fixed in parallel) — baselined so this gate can ship green;
remove those rows as chat-service adopts the sanitizer.

Usage:
  python scripts/injection-coverage-lint.py            # full scan (CI / manual)
  python scripts/injection-coverage-lint.py --staged   # git-staged files only
  python scripts/injection-coverage-lint.py --list     # print all flagged (for baselining)
  python scripts/injection-coverage-lint.py --help

Exit 0 = clean (or baseline-only). Exit 1 = a NEW unsanitized assembly module.
"""
from __future__ import annotations

import ast
import io
import os
import re
import subprocess
import sys
import tokenize
from dataclasses import dataclass

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# AI services whose modules assemble LLM prompts over retrieved/book/graph text.
SCAN_DIRS = (
    "services/chat-service/app",
    "services/knowledge-service/app",
    "services/composition-service/app",
    "services/lore-enrichment-service/app",
    # S4 (2026-08-02) — widened. The four above were the services someone happened to think
    # of; the rule is about ANY module that folds untrusted text into a prompt.
    #
    # translation-service is the one that should have been here first: it processes IMPORTED
    # third-party book text, which is the least trusted content on the platform, and the scan
    # had never looked at it. Widening found SEVEN prompt-assembly modules there with no
    # sanitizer reference (below), plus one in worker-ai.
    #
    # learning / video-gen / campaign / jobs come back CLEAN and are included anyway: the cost
    # is a directory walk, and the value is that a first unsanitized assembly in any of them
    # reds instead of arriving unnoticed the way translation's seven did.
    "services/translation-service/app",
    "services/worker-ai/app",
    "services/learning-service/app",
    "services/video-gen-service/app",
    "services/campaign-service/app",
    "services/jobs-service/app",
)
SCAN_EXTS = (".py",)
EXCLUDE_DIRS = {
    "node_modules", "__pycache__", ".pytest_cache", ".venv", "venv",
    "dist", "build", ".git", "tests", "test", "benchmark", "scripts",
}

# ── BASELINE ──────────────────────────────────────────────────────────────
# Modules that assemble a prompt from retrieved text but do NOT yet route
# through the sanitizer. The lint passes while every flagged module is listed
# here; a NEW one fails. Generated via `--list`; every row is a tracked hole.
#
# Current tracked holes (regenerate with `--list`). Two flavours:
#   - GENUINE GAPS — composition-service references NO sanitizer anywhere; its
#     engine assembles prompts from retrieved book / canon / motif text
#     unsanitized. knowledge context/selectors/passages.py retrieves chapter
#     passages into a prompt without the wiki path's `neutralize_injection`.
#   - SANITIZED-UPSTREAM (per-file coverage limitation) — the two knowledge
#     wiki modules consume the IR that wiki/context.py already neutralized
#     (it calls `neutralize_injection` on every glossary/KG/passage span), and
#     the two chat-service compose modules are fed text sanitized at the
#     stream_service chokepoint (stream_service.py neutralizes kctx.context).
#     They are baselined (not silently cleared) because per-file coverage can't
#     see the sibling sanitize call — a deliberate security-conservative choice.
# NOTE chat-service itself is no longer a whole-service hole: it added
# app/services/injection_defense.py and sanitizes at the retrieval chokepoint.
# Delete each row as the module routes its own retrieved text through the
# sanitizer (or, for the upstream ones, once verified end-to-end).
@dataclass(frozen=True)
class BaselineRow:
    """One tracked hole, and what would end it.

    `wakes_when` is required and checked non-empty: a row without it is a silence with no exit.

    `upstream` is what makes this baseline EXPIRING rather than permanent. A "sanitized
    upstream" row is an exemption whose justification lives in ANOTHER FILE, and per-file
    coverage is why it cannot be seen from here. Naming that file lets the gate verify the
    claim on every run — if the sibling ever stops sanitizing, the row dies with it and the
    finding comes back. Without this the exemption would outlive its own reason, which is the
    escape-hatch-cannot-reach-its-reason defect (NV-6) with a security payload.
    """
    kind: str                  # "GENUINE_GAP" | "SANITIZED_UPSTREAM"
    wakes_when: str
    upstream: str = ""         # required iff kind == "SANITIZED_UPSTREAM"


GENUINE_GAP = "GENUINE_GAP"
SANITIZED_UPSTREAM = "SANITIZED_UPSTREAM"
#: A third kind, and it is deliberately NOT folded into the one above. The upstream covers this
#: module by DETECTING, not by transforming — a strictly weaker promise, and the whole point of
#: the MUTATE/DETECT split is that the two must not read alike. Verified against the
#: detect-only references rather than the mutating ones.
DETECT_UPSTREAM = "DETECT_UPSTREAM"

BASELINE: dict[str, BaselineRow] = {
    # ── sanitized upstream: the claim is checkable, and now checked ───────────────────────
    "services/composition-service/app/services/glossary_build/engine.py": BaselineRow(
        SANITIZED_UPSTREAM,
        "the engine builds no prompt text itself; it would wake if it started assembling one",
        upstream="services/composition-service/app/services/glossary_build/prompts.py"),
    "services/chat-service/app/services/compact_service.py": BaselineRow(
        SANITIZED_UPSTREAM,
        "wakes if compaction ever reads retrieved text that did not come through the stream "
        "chokepoint",
        upstream="services/chat-service/app/services/stream_service.py"),
    "services/chat-service/app/services/composer.py": BaselineRow(
        SANITIZED_UPSTREAM,
        "same chokepoint as compact_service; wakes if the composer gains its own retrieval",
        upstream="services/chat-service/app/services/stream_service.py"),
    "services/composition-service/app/engine/select.py": BaselineRow(
        SANITIZED_UPSTREAM,
        "its content is neutralised by the packer at assembly and by "
        "`cowrite.build_beat_scope` -> `sanitize_prose_context`; wakes if select ever builds "
        "prompt text from retrieved bytes directly instead of through cowrite",
        upstream="services/composition-service/app/engine/cowrite.py"),
    "services/knowledge-service/app/wiki/prompt.py": BaselineRow(
        SANITIZED_UPSTREAM,
        "consumes the IR that wiki/context.py already neutralized span by span; wakes if "
        "prompt.py starts reading a source context.py did not build",
        upstream="services/knowledge-service/app/wiki/context.py"),

    # ── genuine gaps: composition-service references no sanitizer in these paths ──────────
    "services/composition-service/app/engine/canon_check.py": BaselineRow(
        GENUINE_GAP, "wakes when composition routes canon text through the packer sanitizer"),
    "services/composition-service/app/engine/critic.py": BaselineRow(
        GENUINE_GAP, "wakes when the critic's prompt assembly adopts `neutralize`"),
    "services/composition-service/app/engine/motif_conformance.py": BaselineRow(
        GENUINE_GAP, "wakes when motif prompts adopt `neutralize`"),
    "services/composition-service/app/engine/motif_deconstruct.py": BaselineRow(
        GENUINE_GAP, "wakes when the deconstruct chunk prompt adopts `neutralize`"),
    "services/composition-service/app/engine/narrative_thread.py": BaselineRow(
        GENUINE_GAP, "wakes when thread prompts adopt `neutralize`"),
    "services/composition-service/app/engine/self_heal.py": BaselineRow(
        GENUINE_GAP, "wakes when the judge/edit prompts adopt `neutralize` for canon text"),
    "services/composition-service/app/routers/engine.py": BaselineRow(
        GENUINE_GAP, "wakes when the router stops assembling prompt text inline"),
    "services/composition-service/app/worker/operations.py": BaselineRow(
        GENUINE_GAP, "wakes when the worker's prompt assembly adopts `neutralize`"),
    "services/knowledge-service/app/context/selectors/passages.py": BaselineRow(
        GENUINE_GAP,
        "wakes when the passages selector neutralizes like the wiki path already does"),

    # ── S4 2026-08-02: surfaced by widening SCAN_DIRS. Never scanned before; every one a
    # genuine untracked hole. translation-service is the important entry — it builds prompts
    # from IMPORTED book text, the least-trusted bytes on the platform, and references no
    # sanitizer at all. Routing them through `neutralize_injection` is a security change that
    # needs its own measurement: a sanitizer that mangles source text is a TRANSLATION-fidelity
    # bug, which is why the translate rows resolve to OutputKind.MIRROR elsewhere.
    "services/translation-service/app/workers/extraction_worker.py": BaselineRow(
        DETECT_UPSTREAM,
        "both of its prompt sites reach the chapter text through `build_user_prompt`, which "
        "scans it; wakes if this worker ever assembles a prompt without going through there",
        upstream="services/translation-service/app/workers/extraction_prompt.py"),
    "services/worker-ai/app/distill_job.py": BaselineRow(
        GENUINE_GAP, "wakes when the distiller scans the chapter chunks it folds in"),
}


def expired_rows() -> list[str]:
    """Rows whose own justification no longer holds — the EXPIRY, checked every run.

    Three ways a row dies: no `wakes_when` (a silence with no exit), a SANITIZED_UPSTREAM row
    whose named sibling is gone or has stopped sanitizing, and a GENUINE_GAP row that names an
    upstream (a row cannot claim both).
    """
    problems: list[str] = []
    for rel, row in sorted(BASELINE.items()):
        if not row.wakes_when.strip():
            problems.append(f"{rel}: no `wakes_when` — a baseline row with no exit is a "
                            f"permanent silence, not a tracked hole.")
        if row.kind == SANITIZED_UPSTREAM:
            if not row.upstream:
                problems.append(f"{rel}: SANITIZED_UPSTREAM with no `upstream` named — the "
                                f"claim is unverifiable, which is the same as untrue.")
                continue
            up = os.path.join(REPO_ROOT, row.upstream)
            if not os.path.exists(up):
                problems.append(f"{rel}: its upstream {row.upstream} no longer exists. The "
                                f"exemption has outlived its reason.")
            elif not _MUTATE_REF.search(_read(row.upstream)):
                problems.append(f"{rel}: its upstream {row.upstream} NO LONGER SANITIZES. "
                                f"This row was silencing the finding on that file's behalf; "
                                f"the reason is gone, so the row is too.")
        elif row.kind == DETECT_UPSTREAM:
            if not row.upstream:
                problems.append(f"{rel}: DETECT_UPSTREAM with no `upstream` named.")
            elif not os.path.exists(os.path.join(REPO_ROOT, row.upstream)):
                problems.append(f"{rel}: its upstream {row.upstream} no longer exists.")
            elif not DETECT_ONLY_REF.search(_read(row.upstream)):
                problems.append(f"{rel}: its upstream {row.upstream} NO LONGER SCANS. The "
                                f"detect coverage this row leans on is gone.")
        elif row.upstream:
            problems.append(f"{rel}: a GENUINE_GAP row names an upstream. If a sibling "
                            f"sanitizes it, the row's kind is SANITIZED_UPSTREAM.")
    return problems

# ── detection ─────────────────────────────────────────────────────────────

# (a) The module assembles an LLM prompt.
MESSAGE_ASSEMBLY = re.compile(
    r"""["']role["']\s*:\s*["'](?:system|user)["']"""   # {"role": "system"|"user"}
    r"""|\bSystemMessage\s*\("""                          # LangChain-style
    r"""|\bHumanMessage\s*\("""
    r"""|\bmessages\s*(?:=|\.append\s*\(|\.extend\s*\()"""  # messages list build
)

# (b) The module folds in RETRIEVED / EXTERNAL / BOOK / GRAPH text — the
# untrusted content that MUST be sanitized before it reaches the model. Word-ish
# markers, deliberately content-flavored (not generic "context"/"text") to keep
# the flagged set to genuine retrieved-content sites.
RETRIEVED_TEXT = re.compile(
    r"\b("
    r"passages?|chunk(?:_text|s)?|snippet|excerpt|retrieved|retrieval"
    r"|book_text|chapter_text|source_text|context_block|context_text"
    r"|graph_context|neighbor_text|entity_summary|evidence_text"
    r"|tool_result|tool_results|canon_text|mention_text|l3_context"
    r")\b"
)

# (c) The module CALLS the injection sanitizer.
#
# This required only a MENTION until 2026-07-29, and the gap was not theoretical.
# `knowledge-service/app/extraction/canon_check.py` assembled a judge prompt out
# of chapter text with no sanitizer at all; adding the import alone would have
# turned this lint green while changing nothing. Measured on the real tree:
# bypassing the sanitizer but leaving `from …injection_defense import
# neutralize_injection` in place, this lint still reported
#     "OK — every retrieved-text prompt-assembly module routes through the sanitizer"
#
# So the name must be followed by `(`. A bare import, a docstring mention, a
# metric description (`knowledge-service/app/metrics.py` has one) and a comment
# no longer count as coverage.
#
# Verified free: of the 16 non-test modules referencing the sanitizer, all 16
# call it, so tightening this reds nothing today. The one module that references
# it without calling is `metrics.py`, and only inside a metric's help string —
# it assembles no prompt, so it was never a subject.
#
# The known false positive is a module that passes the function as a VALUE
# (`map(neutralize_injection, …)`) rather than calling it. None exists; if one
# appears, it gets a BASELINE row with a note, which is the right amount of
# friction for something that reads as unsanitized at a glance.
# MERGE 2026-08-02 — the tightening above arrived on `main`, and it also DELETED the two
# `from …sanitize import` alternatives this pattern used to carry. That silently un-covered
# six composition-service modules (cowrite · cross_scene_check · error_block_heal ·
# motif_plan · plan_forge/material_search · glossary_build/prompts), because composition does
# not use `loreweave_grounding`'s sanitizer — it has its own, `app/packer/sanitize.py` (§13
# SEC3: fullwidth-escape the assembly delimiters, then TAG directive spans rather than delete
# them). Those six were matched by the import alternative alone, which is exactly the weakness
# main was right to remove.
#
# So the call-forms are named explicitly rather than the import restored. Verified before
# adding, not assumed: each of the six CALLS one of these (read at the call site), and
# `app/packer/sanitize.py` is the ONLY definer of all four names in the repo
# (`grep -rn "^def neutralize(" services sdks` → one hit), so no unrelated module can be
# laundered by a same-named local helper.
SANITIZER_REF = re.compile(
    r"\bneutralize_injection\s*\("
    r"|\bneutralize_proposal_text\s*\("
    r"|\bscan_injection\s*\("
    r"|\bscan_untrusted_source\s*\("
    r"|\bneutralize\s*\("
    r"|\bsanitize_lore\s*\("
    r"|\bsanitize_guide\s*\("
    r"|\bsanitize_prose_context\s*\("
)

#: Two coverage classes, because they are two different promises and merging them would let
#: the weaker one quietly clear rows the stronger one was tracking.
#:
#: MUTATE — the untrusted text is transformed before assembly: delimiters escaped, directive
#: spans bracketed. The model cannot act on the payload. This is what a composition module
#: means by "covered".
#:
#: DETECT — the text is SCANNED and reported, and reaches the model unchanged. Weaker on
#: purpose, and correct where mutation is not available: in translation the untrusted text is
#: the PRODUCT, so escaping a bracket or bracketing a line of dialogue corrupts the author's
#: chapter. A detect-covered module tells a human that a chapter carries directive-looking
#: spans; it does not stop the model from reading them.
#:
#: Named separately so the PASS line cannot say "every module routes through the sanitizer"
#: about a set where seven of them only look. That sentence would be the same
#: two-states-collapsed-into-one defect this lint exists to catch, committed by the lint.
DETECT_ONLY_REF = re.compile(r"\bscan_injection\s*\(|\bscan_untrusted_source\s*\(")


def _code_lines(src: str) -> list[str]:
    """`src` with COMMENT and DOCSTRING lines blanked. Everything else is untouched.

    S4. Every one of this lint's three signals used to be matched against raw file text,
    which reads PROSE as evidence about BEHAVIOUR — and it cuts both ways:

      · FALSE POSITIVE, live: MEASURED 2026-08-02, three modules were flagged (or held a
        BASELINE row calling them a "genuine gap") on the strength of markers appearing ONLY
        in comments, with zero in code — `engine/compress.py`, `engine/canon_reflect.py`,
        `wiki/generate.py`. `engine/select.py`'s own BASELINE row records the same event
        happening before: a feature gave it the word "passage" in prose and the row was
        written rather than rename the word to dodge the regex. That row was the right call
        for the wrong reason — the regex should not have been reading the comment.

      · FALSE NEGATIVE, and this is the dangerous half: `SANITIZER_REF` matched raw text too,
        so a module whose ONLY mention of `neutralize(` was in a comment counted as
        PROTECTED. Measured today: 0 such files — but nothing prevented one, and a security
        gate silenced by a sentence is worse than no gate. This repo already has the rule
        (`docs/standards/`: a claim in a docstring is not a mechanism) and the deferral
        registry already had to grow a stripper for exactly this.

    Regular string literals are DELIBERATELY kept: a prompt template containing "PASSAGE:" is
    code doing the thing, not prose describing it.
    """
    lines = src.splitlines()
    blank: set[int] = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                blank.add(tok.start[0])
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass  # unparseable → fall back to raw text, which is the conservative direction
    try:
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Module, ast.FunctionDef,
                                     ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                blank.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    except (SyntaxError, ValueError):
        pass
    return ["" if i in blank else ln for i, ln in enumerate(lines, 1)]


def classify_file(path: str) -> tuple[bool, bool, bool]:
    """Return (assembles_prompt, uses_retrieved_text, has_sanitizer) for a file."""
    assembles, retrieved, sanitized, _detect = _classify(path)
    return assembles, retrieved, sanitized


def _classify(path: str) -> tuple[bool, bool, bool, bool]:
    """(assembles_prompt, uses_retrieved_text, has_sanitizer, detect_only)."""
    assembles = retrieved = sanitized = detect = False
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            src = fh.read()
    except OSError:
        return False, False, False, False
    for line in _code_lines(src):
        if not assembles and MESSAGE_ASSEMBLY.search(line):
            assembles = True
        if not retrieved and RETRIEVED_TEXT.search(line):
            retrieved = True
        if not sanitized and SANITIZER_REF.search(line):
            sanitized = True
        if not detect and DETECT_ONLY_REF.search(line):
            detect = True
    # DETECT-only means it scans and does NOTHING ELSE. A module that scans AND neutralises
    # is MUTATE-covered — the stronger promise wins, and it must, or adding a scan beside a
    # neutraliser would downgrade a module's reported coverage.
    only_detect = detect and not _MUTATE_REF.search(_read(path))
    return assembles, retrieved, sanitized, only_detect


def _read(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            return "\n".join(_code_lines(fh.read()))
    except OSError:
        return ""


#: The sanitizer calls that TRANSFORM. `SANITIZER_REF` minus the scan-only names.
_MUTATE_REF = re.compile(
    r"\bneutralize_injection\s*\("
    r"|\bneutralize_proposal_text\s*\("
    r"|\bneutralize\s*\("
    r"|\bsanitize_lore\s*\("
    r"|\bsanitize_guide\s*\("
    r"|\bsanitize_prose_context\s*\("
)


def flagged_files(files) -> list[str]:
    """Flag a MODULE that assembles a prompt from retrieved text and does not
    itself reference the sanitizer.

    Coverage is per-FILE (not per-directory) on purpose: this is a security
    gate, so a false negative (a real injection hole missed) is worse than a
    false positive (an extra baseline row). Directory-level "nearby" coverage
    was rejected because it lets a NEW unsanitized module hide among sanitized
    siblings — a module that sanitizes at a chokepoint in a sibling file (e.g.
    knowledge wiki/context.py feeding wiki/prompt.py, or a chat-service compose
    module fed pre-sanitized text) is therefore baselined with a note rather
    than silently cleared."""
    out: list[str] = []
    for full, rel in files:
        a, r, s = classify_file(full)
        if a and r and not s:
            out.append(rel)
    return sorted(set(out))


def iter_full_scan():
    for d in SCAN_DIRS:
        root = os.path.join(REPO_ROOT, d)
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [x for x in dirnames if x not in EXCLUDE_DIRS]
            for fn in filenames:
                if fn.endswith(SCAN_EXTS) and not fn.startswith("test_"):
                    full = os.path.join(dirpath, fn)
                    rel = os.path.relpath(full, REPO_ROOT).replace(os.sep, "/")
                    yield full, rel


def iter_staged():
    try:
        res = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return
    for rel in res.stdout.splitlines():
        rel = rel.strip().replace(os.sep, "/")
        if not rel.endswith(SCAN_EXTS):
            continue
        if not rel.startswith(SCAN_DIRS):
            continue
        if any(part in EXCLUDE_DIRS for part in rel.split("/")):
            continue
        if os.path.basename(rel).startswith("test_"):
            continue
        full = os.path.join(REPO_ROOT, rel)
        if os.path.isfile(full):
            yield full, rel


def main() -> int:
    args = sys.argv[1:]
    if "--help" in args or "-h" in args:
        print(__doc__)
        return 0
    list_mode = "--list" in args
    staged = "--staged" in args
    files = iter_staged() if staged else iter_full_scan()
    flagged = flagged_files(files)

    if list_mode:
        print(f"# {len(flagged)} flagged module(s) — assemble a prompt from "
              f"retrieved text with no sanitizer ref:")
        for rel in flagged:
            print(f'    "{rel}",')
        return 0

    # DoD-4b — the EXPIRY, before anything else. A row whose justification is gone is
    # not a tracked hole any more, it is a silence, and it must not be able to green a
    # run just because the module it covers still looks the same.
    expired = expired_rows()
    if expired:
        print("injection-coverage-lint: FAIL — BASELINE row(s) whose reason no longer holds:")
        for e in expired:
            print("  " + e)
        return 1

    new = [rel for rel in flagged if rel not in BASELINE]
    baselined = [rel for rel in flagged if rel in BASELINE]

    mode = "staged" if staged else "full"

    # S4 — the baseline must be able to SHRINK, and only a full scan can tell.
    #
    # Every row here is documented as "a tracked hole". A row for a module that is no longer
    # flagged is therefore a claim about a hole that does not exist — and it costs more than
    # nothing: it is the exemption that would silence the gate if that module ever DID grow a
    # real unsanitized assembly. Two such rows were found on 2026-08-02 (`canon_reflect.py`,
    # `wiki/generate.py`), both listed as "genuine gaps" on the strength of a marker word that
    # appeared only in a comment.
    #
    # A NOTE, not a failure: a stale row is a documentation defect, not a security one, and
    # reddening CI for it would push the next person to delete rows to get green.
    if not staged:
        stale = sorted(set(BASELINE) - set(flagged))
        if stale:
            print(f"NOTE — {len(stale)} BASELINE row(s) no longer flagged. Each claims a "
                  f"tracked hole that the scan does not find; delete them:")
            for rel in stale:
                print(f"    {rel}")
            print()

    if not new:
        extra = f" ({len(baselined)} baselined)" if baselined else ""
        print(f"injection-coverage-lint ({mode}): OK — every retrieved-text "
              f"prompt-assembly module routes through the sanitizer{extra}")
        # …and then the honest qualifier. A module that only SCANS is covered by this lint
        # and makes a weaker promise: the payload reaches the model unchanged and a human is
        # told. Printing the count is the difference between a gate that reports coverage and
        # one that reports what KIND of coverage — and this file's own history is a module
        # that satisfied it with an import.
        if not staged:
            # Scoped to actual SUBJECTS (assembles a prompt from retrieved text). Without
            # this it also names `injection_report.py` — the reporter itself, which scans
            # because scanning is its job and assembles no prompt at all.
            detect_only = sorted(
                rel for full, rel in iter_full_scan()
                if (lambda c: c[0] and c[1] and c[3])(_classify(full))
            )
            if detect_only:
                print(f"  {len(detect_only)} module(s) are DETECT-only — the untrusted text "
                      f"is scanned and reported, NOT transformed, because it is the product:")
                for rel in detect_only:
                    print(f"    {rel}")
        return 0

    print("injection-coverage-lint: FAIL — prompt built from retrieved/external "
          "text with NO injection sanitizer (SEC-4 / ML-4)\n")
    print("  Untrusted retrieved text (passages, chunks, tool results, graph/book")
    print("  text) must pass `neutralize_injection` (loreweave_grounding.sanitize)")
    print("  before it is concatenated into a system/user prompt.\n")
    for rel in new:
        print(f"  {rel}")
    print()
    print("Route the retrieved text through the sanitizer, or — if a module is a")
    print("reviewed exception — add it to BASELINE in scripts/injection-coverage-")
    print("lint.py with a tracking note (never leave it untracked).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
