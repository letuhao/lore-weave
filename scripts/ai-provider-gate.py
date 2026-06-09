#!/usr/bin/env python3
"""ai-provider-gate.py — enforce LoreWeave's AI provider invariants.

Cross-platform (Python, no bash/`/tmp` — same reason workflow-gate was
ported off bash: Windows pyenv-win shim + path issues). Supersedes the
narrower `lint-no-direct-llm-imports.sh` (which only caught Python
litellm/openai/anthropic imports).

Enforces two ENFORCED rules from CLAUDE.md › Key Rules:

  1. Provider gateway invariant — NO service imports a provider SDK or
     calls a provider API directly. Every LLM/embedding/image/audio/STT
     call goes through provider-registry-service. The ONLY place provider
     SDKs live is the gateway itself (+ the loreweave_llm SDK).

  2. No hardcoded model names — model names resolve from
     provider-registry, never as literals in service runtime code.

(The third rule — MCP-first for AI *agent* logic — is semantic, not
grep-detectable, so it stays doc-enforced + tracked via DEFERRED 066.)

Allowlist (where the above are LEGITIMATE):
  - services/provider-registry-service/  — the gateway: provider SDKs +
    the model catalog live here BY DESIGN.
  - sdks/python/                          — the SDK transport layer.
  - test files                            — fixtures may name models/SDKs.
  - services/knowledge-service/app/pricing.py — KNOWN drift, tracked in
    DEFERRED 065 (D-PRICING-REGISTRY-SOURCE). Allowlisted so the gate
    enforces NEW violations without blocking on the tracked-deferred one;
    remove this entry when 065 is cleared.

Usage:
  python scripts/ai-provider-gate.py            # full scan (CI / manual)
  python scripts/ai-provider-gate.py --staged   # only git-staged files (pre-commit)

Exit 0 = clean (or allowlisted-only). Exit 1 = violation.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SEARCH_DIRS = ("services", "frontend")
SCAN_EXTS = (".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".mjs")
EXCLUDE_DIRS = {
    "node_modules", "__pycache__", ".pytest_cache", ".venv", "venv",
    "dist", "build", ".next", ".git", "vendor", "coverage",
}

# Path prefixes (forward-slash, relative to repo root) where the rules
# do not apply. Keep these tight and comment every entry.
ALLOWLIST_PREFIXES = (
    "services/provider-registry-service/",   # the gateway adapter itself
    "sdks/python/",                          # the loreweave_llm SDK transport
    "services/knowledge-service/app/pricing.py",  # tracked DEFERRED 065 (model→price)
    "services/knowledge-service/app/context/selectors/passages.py",  # DEFERRED 065 (model→embedding-dim)
)

# ── detection patterns ────────────────────────────────────────────────

# Rule 1 — direct provider SDK imports, per language.
PY_SDK = re.compile(
    r"^\s*(?:from|import)\s+"
    r"(litellm|openai|anthropic|cohere|ollama|groq|together|mistralai"
    r"|google\.generativeai|google\.genai)\b"
)
JS_SDK = re.compile(
    r"""(?:from\s+|require\(\s*|import\(\s*)['"]"""
    r"(openai|@anthropic-ai/sdk|@google/generative-ai|@google/genai"
    r"|cohere-ai|ollama|groq-sdk|together-ai|@mistralai/[\w-]+)['\"]"
)
GO_SDK = re.compile(
    r'"(github\.com/sashabaranov/go-openai'
    r"|github\.com/anthropics/anthropic-sdk-go"
    r"|github\.com/google/generative-ai-go[\w/]*"
    r'|github\.com/cohere-ai/[\w-]+)"'
)

# Rule 2 — hardcoded model-name literals (quoted). Tuned to LoreWeave's
# providers; deliberately conservative to avoid false positives on this
# codebase (verified 2026-06-10: only registry/pricing/tests matched).
MODEL_NAME = re.compile(
    r"""['"`]("""
    r"gpt-[0-9o][\w.\-]*"
    r"|o[13]-(?:mini|preview|pro)[\w.\-]*"
    r"|claude-[0-9][\w.\-]*"
    r"|claude-(?:sonnet|opus|haiku)-[\w.\-]*"
    r"|gemini-[0-9][\w.\-]*"
    r"|text-embedding-[\w.\-]+"
    r"|mistral-(?:large|small|medium|tiny)[\w.\-]*"
    r"|llama-?[0-9][\w.\-]*"
    r""")['"`]"""
)


def is_test_file(rel: str) -> bool:
    """Test / story / fixture files — example model names + SDK refs are
    legitimate here (they are not runtime code making provider calls)."""
    base = os.path.basename(rel)
    return (
        "/tests/" in rel
        or "/test/" in rel
        or "/.storybook/" in rel
        or "/fixtures/" in rel
        or "/__fixtures__/" in rel
        or "/__mocks__/" in rel
        or rel.endswith("_test.go")
        or base.startswith("test_")
        or base.endswith((
            ".spec.ts", ".spec.tsx", ".test.ts", ".test.tsx",
            ".stories.ts", ".stories.tsx",
        ))
        or base == "conftest.py"
    )


def is_allowlisted(rel: str) -> bool:
    return rel.startswith(ALLOWLIST_PREFIXES) or is_test_file(rel)


def sdk_pattern_for(rel: str):
    if rel.endswith((".py",)):
        return PY_SDK
    if rel.endswith((".ts", ".tsx", ".js", ".jsx", ".mjs")):
        return JS_SDK
    if rel.endswith(".go"):
        return GO_SDK
    return None


def scan_file(path: str, rel: str) -> list[tuple[str, int, str, str]]:
    """Return (kind, lineno, rel, line) violations for one file."""
    out: list[tuple[str, int, str, str]] = []
    sdk_re = sdk_pattern_for(rel)
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for n, line in enumerate(fh, 1):
                if sdk_re and sdk_re.search(line):
                    out.append(("provider-sdk", n, rel, line.rstrip()))
                if MODEL_NAME.search(line):
                    out.append(("model-name", n, rel, line.rstrip()))
    except OSError:
        pass
    return out


def iter_full_scan():
    for d in SEARCH_DIRS:
        root = os.path.join(REPO_ROOT, d)
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [x for x in dirnames if x not in EXCLUDE_DIRS]
            for fn in filenames:
                if fn.endswith(SCAN_EXTS):
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
        if not rel.startswith(tuple(d + "/" for d in SEARCH_DIRS)):
            continue
        if any(part in EXCLUDE_DIRS for part in rel.split("/")):
            continue
        full = os.path.join(REPO_ROOT, rel)
        if os.path.isfile(full):
            yield full, rel


def main() -> int:
    staged = "--staged" in sys.argv[1:]
    files = iter_staged() if staged else iter_full_scan()

    violations: list[tuple[str, int, str, str]] = []
    for full, rel in files:
        if is_allowlisted(rel):
            continue
        violations.extend(scan_file(full, rel))

    mode = "staged" if staged else "full"
    if not violations:
        print(f"ai-provider-gate ({mode}): OK — no direct provider SDKs / hardcoded model names")
        return 0

    sdk_hits = [v for v in violations if v[0] == "provider-sdk"]
    model_hits = [v for v in violations if v[0] == "model-name"]

    print("ai-provider-gate: FAIL\n")
    if sdk_hits:
        print("[Provider gateway invariant] direct provider-SDK usage is forbidden")
        print("  → route every LLM/embedding/image/audio call through provider-registry-service")
        print("    (loreweave_llm SDK / /v1/llm). The ONLY place a provider SDK belongs is the gateway.\n")
        for _, n, rel, line in sdk_hits:
            print(f"  {rel}:{n}: {line.strip()}")
        print()
    if model_hits:
        print("[No hardcoded model names] resolve model ids from provider-registry, not literals")
        print("  → use the user's registered provider config; do NOT bake model strings into runtime code.\n")
        for _, n, rel, line in model_hits:
            print(f"  {rel}:{n}: {line.strip()}")
        print()
    print("If this is genuine legacy that needs a migration plan, add a row to")
    print("docs/deferred/DEFERRED.md and allowlist the exact path here — never leave it untracked.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
