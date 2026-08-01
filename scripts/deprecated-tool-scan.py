#!/usr/bin/env python3
"""Find references to RETIRED or PHANTOM MCP tools in agent-facing instructions.

Why this exists
---------------
A skill, rail, or tool description that names a tool the agent cannot discover does not
fail loudly — it sends the model hunting for that name and burns the turn in a discovery
loop. We shipped eight of these before anyone noticed, including a whole `autonomous-
drafting` rail built on `composition_authoring_run_create` (retired), and `book_delete`,
which has never existed at all.

The catalog is derived from the OWNING SERVICES, never hand-maintained. Two earlier
guards used hand-copied lists and both went blind the moment a new service retired a
tool family — that is the failure this replaces.

    visibility="legacy"                     (Python: require_meta / @mcp_server.tool)
    lwmcp.VisibilityLegacy                  (Go: WithVisibility)
    superseded_by= / WithSupersededBy(...)  (the replacement, reported in the finding)

What it scans
-------------
Agent-facing instruction TEXT only — string literals, with comments stripped first. A
code comment recording history ("superseded by X in 2026-07") is not a claim to the
model and must not fail the scan; a rail step or a skill sentence naming the same tool is.

    services/chat-service/app/services/*_skill.py   the skills
    services/agent-registry-service/.../migrate.go   the agent rails (steps + prose)
    services/*/app/mcp/server.py                     tool descriptions (Python)
    services/*/internal/api/*.go                     tool descriptions (Go)

Usage
-----
    python scripts/deprecated-tool-scan.py            # scan; exit 1 on findings
    python scripts/deprecated-tool-scan.py --list     # print the derived catalog
    python scripts/deprecated-tool-scan.py --json     # machine-readable findings

Wire as a pre-commit hook alongside scripts/ai-provider-gate.py. A genuine false
positive gets an inline `deprecated-tool-scan: ok — <reason>` on the same line.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OK_MARKER = "deprecated-tool-scan: ok"

#: Retired→retired references held as tracked debt (see main()). Ratcheted: any change reds
#: the gate, so this cannot drift up silently and progress cannot go unrecorded.
#: 2026-07-31 — 9, the residue of the 2026-07-22 catalog unification.
DEAD_TO_DEAD_BASELINE = 9

# Tools that are real and always advertised but declared outside a normal MCP server
# (consumer-local meta-tools + the frontend/human-gated set).
_CORE_EXTRA = {
    "tool_list", "tool_load", "find_tools", "confirm_action", "web_search",
    "load_skill", "run_subagent", "workflow_list", "workflow_load",
    "glossary_propose_entity_edit", "glossary_confirm_action", "propose_edit",
}


# ── catalog ─────────────────────────────────────────────────────────────────────────

def _scan_go(src: str) -> tuple[dict[str, str | None], set[str]]:
    """(legacy → replacement, advertised) for one Go file.

    Each registration's block is bounded at the NEXT registration. A fixed-size window
    bleeds the following tool's `VisibilityLegacy` onto an advertised one — that misread
    `book_list` (the unified `ls`) as retired and nearly got it "fixed" out of a skill.
    """
    legacy: dict[str, str | None] = {}
    advertised: set[str] = set()
    marks = [(m.start(), m.group(1)) for m in
             re.finditer(r'addTool\w*\(\s*srv,\s*"([a-z_][a-z0-9_]*)"', src)]
    marks += [(m.start(), m.group(1)) for m in
              re.finditer(r'lwmcp\.RegisterTool\([^)]*?Name:\s*"([a-z_][a-z0-9_]*)"', src, re.S)]
    # A third shape, found 2026-07-27: provider-registry (and any service using a LOCAL
    # helper) registers as `registerTool(srv, &mcp.Tool{Name: "...", ...}, handler)`. Neither
    # pattern above matches a struct literal, so the scanner was SILENTLY BLIND to that whole
    # service — it reported its live tools as nonexistent and never scanned its descriptions
    # for retired names during the migration sweep. Under-reporting is the dangerous failure
    # for this tool: a missed finding looks exactly like a clean scan.
    marks += [(m.start(), m.group(1)) for m in
              re.finditer(r'[Rr]egisterTool\w*\(\s*\w+,\s*&mcp\.Tool\{[^}]*?Name:\s*"([a-z_][a-z0-9_]*)"',
                          src, re.S)]
    # A tool can match more than one pattern; keep the FIRST occurrence of each name so the
    # block bounds below stay correct.
    seen: set[str] = set()
    marks = [m for m in sorted(marks) if not (m[1] in seen or seen.add(m[1]))]
    marks.sort()
    for i, (pos, name) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else min(len(src), pos + 2500)
        blk = src[pos:end]
        if "VisibilityLegacy" in blk:
            sb = re.search(r'WithSupersededBy\([^,]+,\s*"([a-z_][a-z0-9_]*)"', blk)
            legacy[name] = sb.group(1) if sb else None
        else:
            advertised.add(name)
    return legacy, advertised


def _scan_py(src: str) -> tuple[dict[str, str | None], set[str]]:
    legacy: dict[str, str | None] = {}
    advertised: set[str] = set()
    for b in re.split(r"@mcp_server\.tool\(", src)[1:]:
        m = re.search(r'name="([a-z_][a-z0-9_]*)"', b)
        if not m:
            continue
        head = b[:b.find("\nasync def")] if "\nasync def" in b else b[:3000]
        if 'visibility="legacy"' in head:
            sb = re.search(r'superseded_by="([a-z_][a-z0-9_]*)"', head)
            legacy[m.group(1)] = sb.group(1) if sb else None
        else:
            advertised.add(m.group(1))
    return legacy, advertised


def build_catalog() -> tuple[dict[str, str | None], set[str]]:
    legacy: dict[str, str | None] = {}
    advertised: set[str] = set(_CORE_EXTRA)
    for f in ROOT.glob("services/*/internal/api/*.go"):
        if f.name.endswith("_test.go"):
            continue
        lg, ad = _scan_go(f.read_text(encoding="utf-8", errors="ignore"))
        legacy.update(lg)
        advertised |= ad
    for f in ROOT.glob("services/*/app/mcp/server.py"):
        lg, ad = _scan_py(f.read_text(encoding="utf-8", errors="ignore"))
        legacy.update(lg)
        advertised |= ad
    # A name re-registered discoverably wins over any legacy registration of the same name.
    for name in advertised:
        legacy.pop(name, None)
    return legacy, advertised


# ── instruction extraction ──────────────────────────────────────────────────────────

def _strip_comments(text: str, lang: str) -> str:
    """Blank out comments so a historical note ("superseded by X") is not read as a claim.
    Replaced with spaces, not deleted, so line numbers survive."""
    pat = r"^[ \t]*#.*$" if lang == "py" else r"^[ \t]*//.*$"
    return re.sub(pat, lambda m: " " * len(m.group(0)), text, flags=re.M)


def _skill_prompt(src: str) -> str:
    """Only the PROMPT constant — a skill module's docstring is developer history, not
    something the model ever reads, and it legitimately records what was retired."""
    m = re.search(r'^[A-Z_]*SKILL_PROMPT\s*=\s*r?f?"""(.*?)"""', src, re.S | re.M)
    return m.group(1) if m else ""


def instruction_files() -> list[tuple[str, Path, str]]:
    out: list[tuple[str, Path, str]] = []
    for f in sorted((ROOT / "services/chat-service/app/services").glob("*_skill.py")):
        out.append(("skill", f, "py"))
    mg = ROOT / "services/agent-registry-service/internal/migrate/migrate.go"
    if mg.exists():
        out.append(("agent-rail", mg, "go"))
    for f in sorted(ROOT.glob("services/*/app/mcp/server.py")):
        out.append(("tool-desc", f, "py"))
    for f in sorted(ROOT.glob("services/*/internal/api/*.go")):
        if not f.name.endswith("_test.go"):
            out.append(("tool-desc", f, "go"))
    return out


TOKEN = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")
_LOGGING = re.compile(r"\b(?:slog|logger|logging|log)\.\w+\(|logger\.(?:warning|info|debug|error)")
#: Tool names used as DISPATCH KEYS, not as prose.
#:
#: `_dispatch(ctx, "kg_create_node", args)` is how a unified tool reaches its implementation.
#: `undoResult("book_chapter_delete", …)` / `_undo(…)` emit `_meta.undo_hint = {tool, args}` —
#: the name there is the key a client calls to REVERSE the operation, with args shaped for that
#: exact tool. Retired tools deliberately stay CALLABLE (hidden, not deleted) so undo and cached
#: workflows keep working, so pointing an undo hint at the "replacement" would hand it a tool
#: with a different signature and silently break the undo.
#:
#: An earlier version of this file argued the opposite — that an undo hint naming a retired tool
#: was the bug. It is not: it is the mechanism working as designed.
_INTERNAL_DISPATCH = re.compile(r"_dispatch\(|undoResult\(|_undo\(")


def _paren_delta(line: str) -> int:
    """Net paren balance of `line`, ignoring parens INSIDE string literals (a description
    like "(arcs are the durable spec layer)" must not move the depth counter)."""
    bare = _STRINGS.sub('""', line)
    return bare.count("(") - bare.count(")")


def _internal_dispatch_lines(body: str) -> set[int]:
    """1-based line numbers sitting inside a `_dispatch(` / `undoResult(` / `_undo(` call,
    INCLUDING its continuation lines.

    The exclusion above was applied per-line, so it only ever fired when the call and its
    tool-name argument shared a line. Real code wraps:

        return await _dispatch(
            ctx, "kg_world_query",          # ← the name lands on the CONTINUATION line

    and the continuation was then read as agent-facing prose. That single blind spot produced
    19 of this scanner's 43 findings — every one of them a dispatch key or an undo hint, i.e.
    exactly the two things the rule above exists to exempt. The rule was right; it just could
    not see past the line the `(` was on."""
    out: set[int] = set()
    depth = 0
    for i, line in enumerate(body.splitlines(), 1):
        if depth > 0:
            out.add(i)
            depth = max(0, depth + _paren_delta(line))
            continue
        m = _INTERNAL_DISPATCH.search(line)
        if m:
            out.add(i)
            depth = max(0, _paren_delta(line[m.end() - 1:]))
    return out


def _block_bounds(body: str) -> list[tuple[int, int]]:
    """(start, end) 1-based line spans, one per tool registration — a tool's own description
    block. Used to scope the "names its own replacement" exemption, which was also written
    per-line and so missed a `NOTE: superseded by X` sitting one line below the reference."""
    starts = [i for i, ln in enumerate(body.splitlines(), 1) if _OWNER.search(ln)]
    if not starts:
        return []
    n = len(body.splitlines())
    return [(s, (starts[k + 1] - 1) if k + 1 < len(starts) else n)
            for k, s in enumerate(starts)]


def _block_text_at(body_lines: list[str], bounds: list[tuple[int, int]], lineno: int) -> str:
    for s, e in bounds:
        if s <= lineno <= e:
            return "\n".join(body_lines[s - 1:e])
    return ""
#: Only text INSIDE a string literal can reach the model. A bare identifier is code — and the
#: unified `*_edit` tools legitimately CALL their retired predecessors' handler functions
#: (`composition_outline_node_edit` dispatches into `composition_outline_node_create`), which is
#: exactly how a retired tool stays callable. Scanning those as instructions produced 150+ false
#: positives in one file and would have made this scanner useless on day one.
_STRINGS = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"' r"|'([^'\\]*(?:\\.[^'\\]*)*)'" r"|`([^`]*)`")


_OWNER = re.compile(r'(?:addTool\w*\(\s*srv,\s*|Name:\s*|name=)"([a-z_][a-z0-9_]*)"')


def _owner_at(raw: str, lineno: int) -> str | None:
    """The tool whose registration most recently PRECEDES this line — i.e. whose description
    the reference sits in. Used to tell a live claim from dead-to-dead staleness."""
    lines = raw.splitlines()[:lineno]
    for ln in reversed(lines):
        m = _OWNER.search(ln)
        if m:
            return m.group(1)
    return None


def _string_text(line: str) -> str:
    """Concatenated contents of every string literal on the line (Go/Python, incl. backticks)."""
    return " ".join(g for m in _STRINGS.finditer(line) for g in m.groups() if g)


def scan(legacy: dict[str, str | None], advertised: set[str]) -> list[dict]:
    findings: list[dict] = []
    reg = re.compile(r'(?:addTool\w*\(\s*srv,\s*|Name:\s*|name=)"([a-z_][a-z0-9_]*)"')
    for kind, path, lang in instruction_files():
        raw = path.read_text(encoding="utf-8", errors="ignore")
        raw_lines = raw.splitlines()
        if kind == "skill":
            body = _skill_prompt(raw)
            # keep line numbers meaningful by offsetting to where the prompt starts
            offset = raw[:raw.find(body)].count("\n") if body else 0
        elif kind == "tool-desc" and lang == "py":
            # Skip the module docstring — it is a string literal, so `_string_text` would read
            # it, but it is developer documentation and legitimately narrates what was retired.
            first = raw.find("@mcp_server.tool(")
            offset = raw[:first].count("\n") if first > 0 else 0
            body = _strip_comments(raw[first:] if first > 0 else raw, lang)
        else:
            body, offset = _strip_comments(raw, lang), 0
        body_lines = body.splitlines()
        dispatch_lines = _internal_dispatch_lines(body)
        bounds = _block_bounds(body)
        for i, line in enumerate(body_lines, 1):
            lineno = i + offset
            if 0 < lineno <= len(raw_lines) and OK_MARKER in raw_lines[lineno - 1]:
                continue
            # Log lines never reach the model. Everything else in these files that mentions a
            # tool by name does: a description, or an error string the agent reads and acts on
            # ("use X to edit it") — an error that points at a retired tool is the same trap.
            if _LOGGING.search(line) or i in dispatch_lines:
                continue
            # A registration line NAMES the tool it defines — not a reference to it.
            defined = set(reg.findall(line))
            # A skill prompt is already pure prose; everything else must be quoted to count.
            haystack = line if kind == "skill" else _string_text(line)
            owner = _owner_at(raw, lineno) if kind == "tool-desc" else None
            block = _block_text_at(body_lines, bounds, i) if kind == "tool-desc" else ""
            for tok in set(TOKEN.findall(haystack)):
                if tok in advertised or tok in defined:
                    continue
                # A tool naming ITSELF is describing its own reverse, not pointing anywhere:
                # `book_chapter_set_part` → "Reverse: book_chapter_set_part with the prior
                # part_id". There is no dangling pointer in a self-reference.
                if kind == "tool-desc" and tok == owner:
                    continue
                # A tool DESCRIPTION may name its own replacement/deprecation inline; that is
                # the documented migration pointer, not an instruction to call it. Scoped to the
                # DESCRIPTION, not the line — glossary_user_patch carries its "NOTE: superseded
                # by glossary_ontology_upsert" one line BELOW the reference it excuses, so the
                # line-scoped form never matched the case it was written for.
                if kind == "tool-desc" and tok in legacy and (
                        "DEPRECATED" in block or "superseded" in block.lower()):
                    continue
                if tok in legacy:
                    findings.append({
                        "kind": kind, "file": str(path.relative_to(ROOT)).replace("\\", "/"),
                        "line": lineno, "tool": tok, "problem": "retired",
                        "replacement": legacy[tok],
                        # Which tool's description this sits in, and whether the MODEL can see it.
                        # A retired tool's description referencing another retired tool never
                        # reaches anyone — real staleness, but not the loop bug. Sorting by this
                        # is what turns a flat list into a migration order.
                        "owner": owner,
                        # Whether the MODEL can be handed this text.
                        #
                        # This used to read `owner is None or owner in advertised`, on the premise
                        # that "a retired tool's description referencing another retired tool never
                        # reaches anyone". Checked against ai-gateway 2026-07-31: FALSE, and false in
                        # the direction that hides the bug. `toolLoadResult` (find-tools.ts) applies
                        # NO legacy filter — it resolves any tool BY NAME and returns
                        # `description: toolDescription(t)`, stamping `deprecated:true` +
                        # `superseded_by` rather than withholding it. `visibleTools` does the same.
                        # That is deliberate (find-tools.ts:164): legacy tools are LABELLED instead
                        # of dropped precisely so `tool_list` can "show + redirect" and an agent can
                        # migrate itself. So an agent steered toward a deprecated tool then calls
                        # `tool_load` on it and reads its description — which makes a stale pointer
                        # inside a legacy description MORE likely to be read, not less.
                        #
                        # Reachable therefore means "in the catalog at all". The field stays because
                        # the hot-set distinction is still real and still orders the migration —
                        # `tool_list` defaults `includeDeprecated=false`, so an advertised owner is
                        # reached without the agent asking for it.
                        "reaches_model": True,
                        "in_default_hotset": owner is None or owner in advertised,
                    })
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="print the derived catalog and exit")
    ap.add_argument("--json", action="store_true", help="machine-readable findings")
    args = ap.parse_args()

    legacy, advertised = build_catalog()
    if args.list:
        print(f"{len(advertised)} advertised · {len(legacy)} retired\n")
        for t in sorted(legacy):
            print(f"  {t:44} -> {legacy[t] or '(no replacement declared)'}")
        return 0

    findings = scan(legacy, advertised)
    if args.json:
        print(json.dumps(findings, indent=2))
        return 1 if findings else 0

    # Two populations, and only one of them is a live bug.
    #
    # BLOCKING — a tool the agent sees WITHOUT asking (advertised: `tool_list` defaults
    # `includeDeprecated=false`) whose text names a retired tool. That is the discovery loop:
    # the model is steered out of the live catalog by a description it did not go looking for.
    #
    # DEBT — a retired tool's description naming a retired sibling. Reachable (an agent that
    # `tool_load`s the legacy tool reads it), but internally COHERENT: the sibling it names is
    # itself still callable, because retiring hides a tool without deleting it. Nothing loops.
    # It breaks as a class the day the legacy generation is dropped — which is why it is
    # ratcheted rather than ignored. Repointing these at the unified `*_edit` replacement is
    # NOT the fix; see the `_INTERNAL_DISPATCH` note — the reverse-op and undo pointers must
    # keep naming the tool whose SIGNATURE matches, or undo silently breaks.
    blocking = [f for f in findings if f["in_default_hotset"]]
    debt = [f for f in findings if not f["in_default_hotset"]]

    def _dump(rows: list[dict]) -> None:
        by_file: dict[str, list[dict]] = {}
        for f in rows:
            by_file.setdefault(f"[{f['kind']}] {f['file']}", []).append(f)
        for fk, items in sorted(by_file.items()):
            print(f"── {fk}")
            for it in sorted(items, key=lambda x: x["line"]):
                rep = it["replacement"] or "NO replacement declared — describe the capability instead"
                print(f"   line {it['line']:>5}  {it['tool']}  ->  {rep}")

    if blocking:
        print(f"deprecated-tool-scan: {len(blocking)} reference(s) to retired tools from an "
              f"ADVERTISED tool's instructions\n")
        _dump(blocking)
        print("\nA named-but-undiscoverable tool sends the agent into a discovery loop.")
        print("Point at the replacement, or describe the capability without naming a tool.")
        return 1

    # Ratchet. A bare count would let this rot back in silently; asserting equality means a NEW
    # dead-to-dead reference reds the gate, and clearing one reds it too (lower the constant).
    if len(debt) != DEAD_TO_DEAD_BASELINE:
        verb = "grew to" if len(debt) > DEAD_TO_DEAD_BASELINE else "dropped to"
        print(f"deprecated-tool-scan: dead-to-dead references {verb} {len(debt)} "
              f"(baseline {DEAD_TO_DEAD_BASELINE})\n")
        _dump(debt)
        if len(debt) > DEAD_TO_DEAD_BASELINE:
            print("\nA NEW retired→retired reference was added. Point it at a live tool, or "
                  "describe the capability without naming a tool.")
        else:
            print(f"\nProgress — lower DEAD_TO_DEAD_BASELINE to {len(debt)} in {__file__}.")
        return 1

    print(f"deprecated-tool-scan: clean on the live catalog "
          f"({len(advertised)} advertised · {len(legacy)} retired tools known)")
    print(f"  {len(debt)} retired→retired reference(s) held at baseline — tracked migration "
          f"debt, not a live loop (each names a still-callable sibling).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
