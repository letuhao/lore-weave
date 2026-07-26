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

import os
import re
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# AI services whose modules assemble LLM prompts over retrieved/book/graph text.
SCAN_DIRS = (
    "services/chat-service/app",
    "services/knowledge-service/app",
    "services/composition-service/app",
    "services/lore-enrichment-service/app",
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
BASELINE: frozenset[str] = frozenset({
    # sanitized upstream at the stream_service chokepoint (kctx.context)
    "services/chat-service/app/services/compact_service.py",
    "services/chat-service/app/services/composer.py",
    # genuine gaps — composition-service has no sanitizer anywhere
    "services/composition-service/app/engine/canon_check.py",
    "services/composition-service/app/engine/canon_reflect.py",
    "services/composition-service/app/engine/cowrite.py",
    "services/composition-service/app/engine/critic.py",
    "services/composition-service/app/engine/motif_conformance.py",
    "services/composition-service/app/engine/motif_deconstruct.py",
    "services/composition-service/app/engine/narrative_thread.py",
    "services/composition-service/app/engine/self_heal.py",
    "services/composition-service/app/routers/engine.py",
    "services/composition-service/app/worker/operations.py",
    # genuine gap — passages selector doesn't neutralize like the wiki path
    "services/knowledge-service/app/context/selectors/passages.py",
    # sanitized upstream in knowledge wiki/context.py (IR spans neutralized)
    "services/knowledge-service/app/wiki/generate.py",
    "services/knowledge-service/app/wiki/prompt.py",
})

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

# (c) The module routes through the injection sanitizer (any reference counts as
# "nearby" — module-level proximity, per the pragmatic heuristic).
SANITIZER_REF = re.compile(
    r"\bneutralize_injection\b"
    r"|\bneutralize_proposal_text\b"
    r"|\bscan_injection\b"
    r"|\binjection_defense\b"
    r"|\bfrom\s+[\w.]*sanitize\s+import\b"
    r"|\bimport\s+[\w.]*sanitize\b"
)


def classify_file(path: str) -> tuple[bool, bool, bool]:
    """Return (assembles_prompt, uses_retrieved_text, has_sanitizer) for a file."""
    assembles = retrieved = sanitized = False
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if not assembles and MESSAGE_ASSEMBLY.search(line):
                    assembles = True
                if not retrieved and RETRIEVED_TEXT.search(line):
                    retrieved = True
                if not sanitized and SANITIZER_REF.search(line):
                    sanitized = True
                if assembles and retrieved and sanitized:
                    break
    except OSError:
        pass
    return assembles, retrieved, sanitized


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

    new = [rel for rel in flagged if rel not in BASELINE]
    baselined = [rel for rel in flagged if rel in BASELINE]

    mode = "staged" if staged else "full"
    if not new:
        extra = f" ({len(baselined)} baselined)" if baselined else ""
        print(f"injection-coverage-lint ({mode}): OK — every retrieved-text "
              f"prompt-assembly module routes through the sanitizer{extra}")
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
