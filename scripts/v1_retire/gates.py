#!/usr/bin/env python3
"""G1..G6 — the gates that make D7 ("regression is impossible") true.

🔴 WHY A SEPARATE FILE FROM runstate.py. The board REPORTS; a gate REFUSES. Keeping them in one
file makes it tempting to let a clause print a warning and still exit 0, which is exactly what
`problem_remaining.py` did ("STOPPING IS NOT YET LEGITIMATE", exit 0) while 13 invariants stayed
invisible.

🔴 EVERY GATE CARRIES ITS OWN FALSIFIER. `--selftest` seeds each gate's original defect into an
in-memory copy of its input and asserts the gate goes RED on it. A gate that has never been
observed failing is not a gate — this repo has shipped three green-with-the-fix-deleted guards,
each an anchored substring that matched an import line or a comment rather than behaviour. So no
gate here may pass `--selftest` by construction: the seed is the REAL historical defect, quoted
in each gate's docstring.

Usage:
    python scripts/v1_retire/gates.py             # run every gate; exit 1 on any RED
    python scripts/v1_retire/gates.py --selftest  # prove every gate red-able; exit 1 if one is vacuous
    python scripts/v1_retire/gates.py --json
"""
from __future__ import annotations

import argparse
import ast
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
CATALOG = ROOT / "contracts/tool-catalog-cache.json"
MANIFEST = ROOT / "contracts/agent-runtime-manifest.json"

#: Tools legitimately served by the consumer itself. Widen DELIBERATELY — this is G1's whole
#: escape hatch, and `confirm_action` lived outside any such list for six weeks.
CONSUMER_LOCAL_OK = {"tool_list", "tool_load", "compose_prose", "workflow_list", "workflow_load"}

Result = tuple[str, str]  # (state, detail); state in {"GREEN", "RED"}


def _read(p: pathlib.Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return ""


def _docs() -> list[pathlib.Path]:
    """Guidance files a human or agent reads for direction.

    Excludes evidence and session logs: a batch record SHOULD carry the count that was true when
    it ran, and rewriting a historical ledger is forbidden by this loop's own goal.
    """
    out = [ROOT / "AGENTS.md", ROOT / "CLAUDE.md", ROOT / "CONTRIBUTING.md"]
    for p in (ROOT / "docs").rglob("*.md"):
        s = p.as_posix()
        # Records, not guidance. A dogfood log or an eval writeup SHOULD carry the count that was
        # true when it ran; "correcting" it would falsify the record.
        if any(d in s for d in ("/evidence/", "/sessions/", "/archive/", "/dogfood/", "/eval/")):
            continue
        # 🔴 A DATED FILENAME IS A DATED SNAPSHOT. Without this the gate reported 373 findings,
        # of which the overwhelming majority were dated plan and dogfood documents accurately
        # recording a past figure. A gate with a 3%-signal output does not get read twice — the
        # cost of a loose detector is not a false alarm, it is the gate being ignored.
        # The date can be on the FILE or on its DIRECTORY: docs/specs/2026-07-09-mcp-tool-
        # liveness-eval/contracts.md is as much a dated record as a dated filename is.
        # Checking only the basename left 61 findings, ~55 of them inside dated spec dirs.
        if any(re.match(r"^20\d\d-\d\d-\d\d[-.]", part) for part in p.parts):
            continue
        out.append(p)
    return [p for p in out if p.is_file()]


# ---------------------------------------------------------------------------------------------
# G1 · no-local-agent-tool
# ---------------------------------------------------------------------------------------------
def g1_no_local_agent_tool(catalog_raw: str | None = None) -> Result:
    """Every advertised tool resolves from the federated catalogue or the named allowlist.

    WOULD HAVE CAUGHT: `confirm_action` advertised out of chat-service's own
    `generic_frontend_tool_def` on every turn from 2026-07 to 2026-09-03 — never federated, so
    no catalogue row could contradict it, and no test asked whether it had one.
    """
    raw = catalog_raw if catalog_raw is not None else _read(CATALOG)
    try:
        cat = json.loads(raw)
    except ValueError as exc:
        return "RED", f"catalogue unreadable: {exc}"
    # 🔴 THE CATALOGUE IS A NAME->ROW MAP. The first draft read `cat["tools"]`, found nothing,
    # and reported all three tools missing — a RED that looked like the very defect the gate
    # hunts. A gate whose parse failure is indistinguishable from a real finding trains its
    # reader to dismiss it.
    names = set(cat) if isinstance(cat, dict) else set()
    if not names:
        return "RED", "catalogue parsed to zero rows — the READER is broken, not the repo"
    missing = sorted(n for n in ("confirm_action", "glossary_confirm_action",
                                "glossary_propose_entity_edit") if n not in names)
    if missing:
        return "RED", (f"advertised but not in the federated catalogue: {', '.join(missing)} "
                       f"(add a provider, or name it in CONSUMER_LOCAL_OK with a reason)")
    return "GREEN", f"{len(names)} catalogue rows; the 3 KIND-C tools all federate"


# ---------------------------------------------------------------------------------------------
# G2 · manifest-lifecycle
# ---------------------------------------------------------------------------------------------
def g2_manifest_lifecycle(manifest_raw: str | None = None) -> Result:
    """No served tool row may name chat-service as its owner, outside the allowlist.

    WOULD HAVE CAUGHT: `glossary_propose_entity_edit` sitting `admitted` with
    `owning_service: chat-service` — a domain tool whose declared home was the consumer.
    """
    raw = manifest_raw if manifest_raw is not None else _read(MANIFEST)
    try:
        man = json.loads(raw)
    except ValueError as exc:
        return "RED", f"manifest unreadable: {exc}"
    bad = []
    for row in man.get("entries", man.get("rows", [])) or []:
        if not isinstance(row, dict):
            continue
        if row.get("kind") != "tool":
            continue
        if row.get("lifecycle") not in ("admitted", "deprecated"):
            continue
        if row.get("owning_service") == "chat-service" and row.get("name") not in CONSUMER_LOCAL_OK:
            bad.append(row.get("name"))
    if bad:
        return "RED", f"served tool rows owned by chat-service: {', '.join(sorted(map(str, bad)))}"
    return "GREEN", "no served tool row is owned by chat-service outside the allowlist"


# ---------------------------------------------------------------------------------------------
# G3 · gate-totality
# ---------------------------------------------------------------------------------------------
def g3_gate_totality(census: dict | None = None) -> Result:
    """Every confirm-mint site opens a durable task, or sits on a CITED exemption.

    WOULD HAVE CAUGHT: all 14 sites of the spec's §3 — including knowledge-service's, which mints
    with its own `mint_action_token` helper and was invisible to a census keyed on the kit's
    spelling alone.

    Delegates to runstate's census so there is ONE definition of "ungated". Two implementations of
    the same question is how the ledger came to read `200 of 198`.
    """
    # 🔴 THIS GATE WAS VACUOUSLY GREEN AND ITS SELFTEST SAID RED-ABLE. The first draft read
    # `census["remaining"]`; the real `_gate_census()` returns `{service: [sites]}` with no such
    # key, so `.get` fell through to `{}` and the gate passed over 17 live sites. The selftest
    # missed it because I had fed it a hand-built dict WITH a "remaining" key — a harness that
    # exercises a shape the production caller never produces proves only that the harness works.
    # The selftest now passes the same shape `_gate_census()` returns.
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import runstate  # noqa: PLC0415
    if census is None:
        census = runstate._gate_census()
    if not isinstance(census, dict) or not all(isinstance(v, list) for v in census.values()):
        return "RED", f"census shape is not {{service: [sites]}} — the READER is broken: {type(census)}"
    exempt = runstate._exempt_sites()
    remaining = {svc: [s for s in sites if s.split("  (line")[0] not in exempt]
                 for svc, sites in census.items()}
    remaining = {k: v for k, v in remaining.items() if v}
    n_exempt = sum(1 for sites in census.values()
                   for s in sites if s.split("  (line")[0] in exempt)
    if remaining:
        n = sum(len(v) for v in remaining.values())
        return "RED", (f"{n} confirm-mint site(s) neither gated nor exempt: "
                       + "; ".join(f"{k}: {len(v)}" for k, v in sorted(remaining.items())))
    return "GREEN", f"{n_exempt} cited exemptions; no uncited bare confirm mint"


# ---------------------------------------------------------------------------------------------
# G4 · doc-count-drift
# ---------------------------------------------------------------------------------------------
#: "315 tools", "198 live tools", "199 v1 tools" — a bare figure asserted as current.
#: NOT PRECEDED BY A COLON. `frontend_tools.py:339 tool def` is a LINE REFERENCE, and the
#: first draft reported it as a drifted count of 339 tools. A gate that cannot tell a
#: coordinate from a quantity keeps producing findings nobody can act on.
_COUNT_RE = re.compile(r"(?<![:\w])(\d{2,4})\s+(?:live\s+|legacy\s+|v1\s+|v2\s+|total\s+)?tools?\b", re.I)
#: What makes a figure a SNAPSHOT rather than a claim about now. A date, or an explicit hedge.
_DATED_RE = re.compile(r"(measured|as of|snapshot|on)\s+20\d\d-\d\d-\d\d|20\d\d-\d\d-\d\d\)", re.I)


def g4_doc_count_drift(docs: dict[pathlib.Path, str] | None = None,
                       truth: set[int] | None = None) -> Result:
    """A hardcoded "N tools" figure must match the SSOT or be marked a dated snapshot.

    WOULD HAVE CAUGHT: `mcp-tool-io.md` asserting 315/198 against a true 316/199 — two numbers a
    human typed once and no generator ever revisited.

    🔴 THE FIX FOR A DRIFTED COUNT IS A DATE OR A POINTER, NOT A NEW NUMBER. A corrected bare
    figure is drifted again the next time a tool ships; that is how the first one got there.
    """
    if truth is None:
        try:
            cat = json.loads(_read(CATALOG))
        except ValueError as exc:
            return "RED", f"catalogue unreadable, cannot establish the SSOT: {exc}"
        if not isinstance(cat, dict) or not cat:
            return "RED", "catalogue parsed to zero rows — the READER is broken, not the repo"
        legacy = sum(1 for r in cat.values()
                     if (r.get("meta") or {}).get("visibility", "live") == "legacy")
        truth = {len(cat), len(cat) - legacy, legacy}
    if docs is None:
        docs = {p: _read(p) for p in _docs()}
    bad: list[str] = []
    for path, text in docs.items():
        lines = text.splitlines()
        for i, line in enumerate(lines):
            # A WRAPPED SENTENCE PUTS ITS DATE ON ANOTHER LINE. AGENTS.md reads 'Measured
            # 2026-09-03 by / running ...: 316 tools' — dated, but not on the matching line,
            # so a line-local check called it undated. Widen to the sentence's neighbourhood.
            window = "\n".join(lines[max(0, i - 2):i + 1])
            for m in _COUNT_RE.finditer(line):
                n = int(m.group(1))
                if n in truth or _DATED_RE.search(window):
                    continue
                # 🔴 "25 tools" IS A SUBSET, NOT A DRIFTED TOTAL. Comparing every "N tools" to the
                # global SSOT produced 223 findings, nearly all of them docs correctly counting a
                # domain, a tier or a batch. The drift signature is a number CLOSE to an SSOT
                # value but not equal to it — 316 for 319, 198 for 202, 315 for 319: a figure that
                # was copied when it was true and never revisited. A count far from every SSOT
                # value is measuring something else, and this gate has nothing to say about it.
                if not any(abs(n - t) <= max(1, t * 0.10) for t in truth if t):
                    continue
                rel = path.as_posix().replace(ROOT.as_posix() + "/", "")
                bad.append(f"{rel}: '{m.group(0)}' (SSOT: {sorted(truth)})")
    if bad:
        return "RED", f"{len(bad)} undated count(s) disagreeing with the SSOT: " + " | ".join(bad[:6])
    return "GREEN", f"every hardcoded tool count matches the SSOT {sorted(truth)} or is dated"


# ---------------------------------------------------------------------------------------------
# G5 · status-contradiction
# ---------------------------------------------------------------------------------------------
#: A header field claiming the work is unfinished, in the doc's first 40 lines.
_OPEN_HDR_RE = re.compile(r"^\s*(?:[-*|]\s*)?(?:\*\*)?status(?:\*\*)?\s*[:|]\s*(?:\*\*)?\s*"
                          r"(open|pending|in progress|in-progress|wip)\b", re.I)
#: A body line that says the same work finished.
_DONE_RE = re.compile(r"THE LOOP IS CLOSED|LOOP CLOSED|\bstatus\b\s*[:|]\s*(?:\*\*)?\s*"
                      r"(?:complete|completed|closed|done|sealed)\b", re.I)


def g5_status_contradiction(docs: dict[pathlib.Path, str] | None = None) -> Result:
    """A doc whose header says open while its body says closed.

    WOULD HAVE CAUGHT: `toolv2-loop-RUNBOOK.md` — line 3 "open", line 1531 "THE LOOP IS CLOSED".
    A reader who checks the header believes there is work left; one who reads to the end believes
    there is not. Both then act, and one of them is wrong.
    """
    if docs is None:
        docs = {p: _read(p) for p in _docs()}
    bad: list[str] = []
    for path, text in docs.items():
        lines = text.splitlines()
        hdr = next((i for i, l in enumerate(lines[:40]) if _OPEN_HDR_RE.search(l)), None)
        if hdr is None:
            continue
        done = next((i for i, l in enumerate(lines) if i != hdr and _DONE_RE.search(l)), None)
        if done is not None:
            rel = path.as_posix().replace(ROOT.as_posix() + "/", "")
            bad.append(f"{rel}: header line {hdr + 1} says open, line {done + 1} says finished")
    if bad:
        return "RED", f"{len(bad)} doc(s) contradicting themselves: " + " | ".join(bad[:6])
    return "GREEN", "no doc claims open in its header and finished in its body"


# ---------------------------------------------------------------------------------------------
# G6 · stale-docstring
# ---------------------------------------------------------------------------------------------
#: Spans that QUOTE rather than assert. A correction records the old wording verbatim, so a bare
#: word-search fires on the very fix that removed the defect — the failure this repo has shipped
#: three times (an import line, a dead string, a window boundary; each green with the fix deleted).
#: Stripped before matching.
_QUOTED_RE = re.compile(r'"[^"]{0,400}"' + r"|\u201c[^\u201d]{0,400}\u201d" + r"|`[^`]{0,200}`", re.S)
#: A line explicitly recording history rather than describing now.
_CORRECTION_RE = re.compile(r"\U0001f534|used to (?:say|read)|trailed|until 20\d\d|"
                            r"this docstring|was false|no longer (?:says|reads)", re.I)
#: The claim must be about THIS SYMBOL, in the docstring's own voice.
#:
#: 🔴 "the DORMANT arc lens" IS NOT A DORMANCY CLAIM. It describes a runtime STATE of another
#: object (structure_repo=None). The first draft was a bare word-search and returned 8 findings:
#: three such state descriptions, one correction quoting the defect it fixed, and zero real
#: defects. A gate at 0% precision is worse than none — it teaches its reader to skip the output.
_DORMANT_RE = re.compile(
    r"\b(?:this|it)\b[^.]{0,120}?\b(?:is|are|was)\b[^.]{0,60}?"
    r"\b(?:dormant|not wired|defined but unused)\b"
    r"|\b(?:this|it)\b[^.]{0,80}?\bnever fires\b",
    re.I | re.S)


#: 🔴 A CONDITIONAL IS NOT A CLAIM. `_empty_str`'s docstring reads "placeholder for the arc lens
#: WHEN IT IS DORMANT" — "it" is the arc lens, and the clause describes a runtime state the
#: function exists to handle. An unconditional "this is dormant" describes the symbol itself.
#: That distinction is the whole gate: without it the last false positive survives, and one
#: permanent false positive is enough to make a gate ignorable.
_CONDITIONAL_RE = re.compile(r"\b(?:when|while|if|unless|whenever|until)\s+$", re.I)


def _asserts_dormant(doc: str) -> bool:
    """True when the docstring CLAIMS this symbol is dormant, in its own voice."""
    cleaned = _QUOTED_RE.sub(" ", doc)
    cleaned = "\n".join(l for l in cleaned.splitlines() if not _CORRECTION_RE.search(l))
    for m in _DORMANT_RE.finditer(cleaned):
        if _CONDITIONAL_RE.search(cleaned[max(0, m.start() - 12):m.start()]):
            continue
        return True
    return False


def g6_stale_docstring(files: dict[pathlib.Path, str] | None = None,
                       callers: dict[str, int] | None = None) -> Result:
    """A docstring claiming a symbol is dormant, while that symbol has a live caller.

    WOULD HAVE CAUGHT: `task_detect.py`'s two dormancy claims — "this never fires (dormant-safe)"
    and "defined but unused (dormant)" — while `knowledge_client.py` had been calling
    `tasks_capability_meta()` under a default-True flag since 2026-07-20. An agent auditing whether
    v1 could be retired read the file implementing the REPLACEMENT and concluded the replacement
    was off.

    🔴 BEHAVIOURAL, NOT SUBSTRING. An earlier draft of this gate grepped for the word `dormant`,
    which matched the correction that QUOTES the old claim — so the gate went green only because
    the fix happened to contain the same word as the defect. This one pairs the claim with an AST
    census of that symbol's callers, and fires only when a claim and a caller coexist.
    """
    if files is None:
        files = {}
        for svc in sorted((ROOT / "services").glob("*/")):
            for f in (svc / "app").rglob("*.py") if (svc / "app").is_dir() else []:
                if "/tests/" in f.as_posix():
                    continue
                files[f] = _read(f)
    if callers is None:
        callers = {}
        for f, src in files.items():
            try:
                tree = ast.parse(src)
            except SyntaxError:
                continue
            for n in ast.walk(tree):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
                    callers[n.func.id] = callers.get(n.func.id, 0) + 1
                elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                    callers[n.func.attr] = callers.get(n.func.attr, 0) + 1
    bad: list[str] = []
    for path, src in files.items():
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            doc = ast.get_docstring(n) or ""
            if not _asserts_dormant(doc):
                continue
            # The claim is only STALE if the symbol is actually called somewhere.
            hits = callers.get(n.name, 0)
            # Its own definition is not a call; a self-recursive call would be. Require >0.
            if hits > 0:
                rel = path.as_posix().replace(ROOT.as_posix() + "/", "")
                bad.append(f"{rel}::{n.name} claims dormant but has {hits} call site(s)")
    if bad:
        return "RED", f"{len(bad)} stale dormancy claim(s): " + " | ".join(bad[:6])
    return "GREEN", "no docstring claims a called symbol is dormant"


GATES = [
    ("G1 no-local-agent-tool", g1_no_local_agent_tool),
    ("G2 manifest-lifecycle", g2_manifest_lifecycle),
    ("G3 gate-totality", g3_gate_totality),
    ("G4 doc-count-drift", g4_doc_count_drift),
    ("G5 status-contradiction", g5_status_contradiction),
    ("G6 stale-docstring", g6_stale_docstring),
]


def _selftest() -> list[tuple[str, bool, str]]:
    """Seed each gate's ORIGINAL defect and require it to go RED.

    The seed is never a synthetic string chosen to match the detector — it is the historical
    defect, reconstructed. A gate that cannot be made red by the very thing it was written for is
    reported as VACUOUS and fails the run.
    """
    out: list[tuple[str, bool, str]] = []

    # G1 — the catalogue WITHOUT the three KIND-C rows, i.e. exactly the state on 2026-09-02 when
    # chat-service advertised them from its own generic_frontend_tool_def.
    cat = json.loads(_read(CATALOG))
    seeded = {k: v for k, v in cat.items()
              if k not in ("confirm_action", "glossary_confirm_action",
                           "glossary_propose_entity_edit")}
    st, detail = g1_no_local_agent_tool(json.dumps(seeded))
    out.append(("G1 no-local-agent-tool", st == "RED", detail))

    # G2 — glossary_propose_entity_edit sitting `admitted` under chat-service.
    st, detail = g2_manifest_lifecycle(json.dumps({"entries": [
        {"name": "glossary_propose_entity_edit", "kind": "tool",
         "lifecycle": "admitted", "owning_service": "chat-service"}]}))
    out.append(("G2 manifest-lifecycle", st == "RED", detail))

    # G3 — one ungated mint site, the shape all 14 of §3 had.
    # The shape `_gate_census()` actually returns: {service: [ "file::symbol  (line N)" ]}.
    # An unexempt symbol name, so the exemption subtraction cannot make it disappear.
    st, detail = g3_gate_totality({"composition-service": [
        "services/composition-service/app/mcp/server.py::_a_symbol_no_exemption_names"
        "  (line 1)"]})
    out.append(("G3 gate-totality", st == "RED", detail))

    # G4 — mcp-tool-io.md's undated "315 tools", against a true 316.
    st, detail = g4_doc_count_drift(
        {pathlib.Path("docs/standards/mcp-tool-io.md"): "The gateway federates 315 tools today."},
        truth={316, 199, 117})
    out.append(("G4 doc-count-drift", st == "RED", detail))

    # G5 — the runbook's own contradiction, header vs body.
    st, detail = g5_status_contradiction(
        {pathlib.Path("docs/plans/toolv2-loop-RUNBOOK.md"):
         "# Tool v2 loop\n\nStatus: open\n\n...\n\nTHE LOOP IS CLOSED\n"})
    out.append(("G5 status-contradiction", st == "RED", detail))

    # G6 — task_detect.py's claim, with tasks_capability_meta genuinely called.
    src = ('def tasks_capability_meta():\n'
           '    """Until then this is defined but unused (dormant)."""\n'
           '    return {}\n')
    st, detail = g6_stale_docstring({pathlib.Path("app/services/task_detect.py"): src},
                                    callers={"tasks_capability_meta": 1})
    out.append(("G6 stale-docstring", st == "RED", detail))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true",
                    help="prove every gate red-able on its own historical defect")
    a = ap.parse_args()

    if a.selftest:
        res = _selftest()
        for name, ok, detail in res:
            print(f"[{'RED-ABLE' if ok else 'VACUOUS '}] {name}")
            if not ok:
                print(f"           gate stayed GREEN on its own seeded defect: {detail}")
        vac = [n for n, ok, _ in res if not ok]
        print()
        print(f"{len(res) - len(vac)} of {len(res)} gates proven red-able"
              + (f"; VACUOUS: {', '.join(vac)}" if vac else ""))
        return 1 if vac else 0

    results = [(name, *fn()) for name, fn in GATES]
    if a.json:
        print(json.dumps({n: {"state": s, "detail": d} for n, s, d in results}, indent=2))
    else:
        print("V1 RETIREMENT GATES — G1..G6")
        print("=" * 66)
        for name, state, detail in results:
            print(f"[{state:5}] {name}")
            print(f"         {detail}")
        print("=" * 66)
    red = [n for n, s, _ in results if s == "RED"]
    print(f"OVERALL: {'ALL GATES GREEN' if not red else 'RED: ' + ', '.join(red)}")
    return 1 if red else 0


if __name__ == "__main__":
    raise SystemExit(main())
