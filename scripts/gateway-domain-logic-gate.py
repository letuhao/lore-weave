#!/usr/bin/env python3
"""gateway-domain-logic-gate — the KAL gateway must forward, not decide (plan T26).

D0.1: the gateway is a bounded, authenticated forwarding surface. The owning services hold
the domain rules, because they are the processes that own the substrates those rules
describe.

WHY THIS GATE EXISTS RATHER THAN A CODE-REVIEW HABIT
----------------------------------------------------
`temporalCapability()` computed, from the GATEWAY's own `KG_TEMPORAL_ENABLED` env var,
whether a graph it does not own could answer a story-time question. Nothing tied that flag
to the graph. A gateway with it on, in front of an unmigrated knowledge-service, advertised
`ordinal_valid_time` and forwarded `as_of` to a substrate answering in transaction time —
a spoiler leak produced by two processes disagreeing about a boolean.

That is not a rule anyone breaks on purpose. It arrives one convenient `if` at a time, in a
file that already has the config object imported. So it is a gate.

WHAT IS FORBIDDEN, AND WHAT IS NOT
-----------------------------------
Forbidden: a CONDITIONAL whose branch depends on substrate / capability / budget / salience
/ tenancy semantics. Those are the five vocabularies D0.1 names.

NOT forbidden, and deliberately so — a gateway that could not do these would not be a
gateway:
  * parsing and shape guards (`Number.isFinite`, `Array.isArray`) — rejecting "NaN" is not
    a domain decision,
  * auth and routing (`KalAuthGuard`, path building),
  * transport concerns (timeouts, aborts, retries, caching).

The check is AST-based, not grep: `// kg is temporal_unsupported here` in a comment is
documentation, and a gate that fires on prose gets disabled by the third false positive.

    python scripts/gateway-domain-logic-gate.py [--baseline]

Exit 0 = clean · 1 = a domain conditional was found · 2 = could not run.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "services" / "knowledge-gateway" / "src"
BASELINE = ROOT / "scripts" / "gateway-domain-logic-gate.baseline.json"

# The five vocabularies D0.1 names. Matched as identifiers/properties, not as substrings of
# arbitrary prose — `capabilityCheck` counts, `incapable` does not.
DOMAIN_TOKENS = {
    # `temporal` is FIRST because it is the founding incident, and the first version of this
    # gate did not have it: the bite reintroduced
    #     if (process.env.KG_TEMPORAL_ENABLED === 'false') return { … }
    # and the gate passed. Its only domain word lived inside a string literal, which the
    # comment/string blanking below removes — so the vocabulary has to name the IDENTIFIERS
    # a rule is written in, not the values it compares against. A gate that cannot catch the
    # incident it was written for is worse than none: it certifies the absence it cannot see.
    # Case-insensitive on purpose: the first fix still missed the bite, because
    # `KG_TEMPORAL_ENABLED` is upper-case and `[tT]emporal` does not match `TEMPORAL`.
    "temporal": r"(?i:temporal)|as_of|asOf|ordinal_valid_time|valid_time|from_order",
    "substrate": r"substrate",
    "capability": r"capabilit(y|ies)",
    "budget": r"budget|token[_A-Z]?[Ll]imit",
    "salience": r"salience",
    "tenancy": r"tenanc(y|ies)|ownerScope|isOwner",
}
_TOKEN_RE = re.compile("|".join(f"(?:{p})" for p in DOMAIN_TOKENS.values()))

# Lines that are unmistakably not decisions.
_ALLOWED_CALL_RE = re.compile(
    r"await\s+temporalCapability\(|"          # forwarding the fetched value
    r"temporal_capability\s*:|"               # stamping it onto a response
    r"^\s*(//|\*|/\*)"                        # comments
)

# Handling an `as_of` VALUE is not deciding anything: `if (asOf) qs.set('as_of', asOf)` is
# forwarding, and `Number.isFinite(parsed)` is a wire-shape guard. What makes a line a
# DECISION is consulting local configuration — that is precisely the step that lets the
# gateway disagree with the substrate it describes.
#
# So the rule is: an as_of-family token alone is fine; an as_of-family token TOGETHER with a
# config/env lookup is not, and any other domain vocabulary is not. `if (asOf &&
# cfg.kgTemporalEnabled)` is still caught, which is the case that matters.
_ASOF_FAMILY_RE = re.compile(r"as_of|asOf")
_LOCAL_DECISION_RE = re.compile(r"loadConfig\(|process\.env|this\.cfg|\bcfg\.|\bconfig\.")


def _strip_comments_and_strings(text: str) -> list[str]:
    """Blank out comments and string literals, keeping line numbers intact.

    Line-preserving because the finding has to name a line a human can open. Blanking rather
    than deleting is what stops a doc comment describing the old rule — this repo has
    several — from being reported as the rule itself.
    """
    out, i, n = [], 0, len(text)
    line = []
    state = None  # None | '//' | '/*' | quote char
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if state is None:
            if c == "/" and nxt == "/":
                state, i = "//", i + 2
                continue
            if c == "/" and nxt == "*":
                state, i = "/*", i + 2
                continue
            if c in "\"'`":
                state, i = c, i + 1
                line.append(" ")
                continue
            if c == "\n":
                out.append("".join(line))
                line = []
                i += 1
                continue
            line.append(c)
        else:
            if state == "//" and c == "\n":
                state = None
                out.append("".join(line))
                line = []
                i += 1
                continue
            if state == "/*" and c == "*" and nxt == "/":
                state, i = None, i + 2
                continue
            if state in "\"'`" and c == state:
                state = None
            if c == "\n":
                out.append("".join(line))
                line = []
            else:
                line.append(" ")
        i += 1
    out.append("".join(line))
    return out


def scan() -> list[tuple[str, int, str]]:
    findings: list[tuple[str, int, str]] = []
    for path in sorted(SRC.rglob("*.ts")):
        text = path.read_text(encoding="utf-8")
        for lineno, code in enumerate(_strip_comments_and_strings(text), start=1):
            if not code.strip():
                continue
            # A conditional: if / ternary / logical branch / switch-case.
            is_conditional = bool(
                re.search(r"\bif\s*\(|\bswitch\s*\(|\?\s*[^:]+\s*:|&&|\|\|", code)
            )
            if not is_conditional:
                continue
            if not _TOKEN_RE.search(code):
                continue
            raw = text.splitlines()[lineno - 1].strip()
            if _ALLOWED_CALL_RE.search(raw):
                continue
            # Strip as_of-family mentions; whatever domain vocabulary REMAINS is a decision.
            others = _TOKEN_RE.sub(
                lambda m: "" if _ASOF_FAMILY_RE.fullmatch(m.group(0)) else m.group(0), code
            )
            handles_as_of_only = not _TOKEN_RE.search(others)
            if handles_as_of_only and not _LOCAL_DECISION_RE.search(code):
                continue
            findings.append((str(path.relative_to(ROOT)).replace("\\", "/"), lineno, raw))
    return findings


def main() -> int:
    if not SRC.is_dir():
        print(f"[gateway-domain-logic-gate] FAIL(setup): {SRC} not found", file=sys.stderr)
        return 2

    findings = scan()
    if "--baseline" in sys.argv:
        BASELINE.write_text(
            json.dumps([{"file": f, "line": ln, "code": c} for f, ln, c in findings], indent=2)
            + "\n",
            encoding="utf-8",
        )
        print(f"[gateway-domain-logic-gate] baseline written: {len(findings)} entry/entries")
        return 0

    known = set()
    if BASELINE.exists():
        known = {(e["file"], e["code"]) for e in json.loads(BASELINE.read_text(encoding="utf-8"))}

    fresh = [f for f in findings if (f[0], f[2]) not in known]
    if fresh:
        print("[gateway-domain-logic-gate] FAIL — domain conditional(s) in the gateway:")
        for file, line, code in fresh:
            print(f"  {file}:{line}\n    {code}")
        print(
            "\n  D0.1: the gateway forwards what the owning service reports. A rule decided\n"
            "  here can disagree with the substrate it describes — which is exactly how\n"
            "  temporalCapability() leaked spoilers (plan T26). Move it to the service.",
        )
        return 1

    stale = known - {(f[0], f[2]) for f in findings}
    scanned = len(list(SRC.rglob("*.ts")))
    if stale:
        # A baseline entry that no longer matches is a fixed finding nobody removed. Left
        # in place it silently re-permits that exact line the day someone reintroduces it.
        print(f"[gateway-domain-logic-gate] FAIL — {len(stale)} stale baseline entry/entries:")
        for file, code in sorted(stale):
            print(f"  {file}\n    {code}")
        print("\n  Re-run with --baseline to drop them.")
        return 1

    print(
        f"[gateway-domain-logic-gate] PASS — {scanned} file(s) scanned, "
        f"{len(known)} baselined"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
