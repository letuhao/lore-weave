#!/usr/bin/env python
"""D-LLM-BUDGET-SSOT — every LLM call must declare where its output budget came from.

The defect
----------
The reasoning axis is already adaptive: ``UserReasoningPref="auto"`` →
``resolve_reasoning(auto_effort=score_effort(signals))``, scoring real per-call signals into
a level. The budget axis is ~40 flat literals. **Both draw from the same token allowance** —
reasoning tokens are spent BEFORE the visible output — so having one that adapts and one
that is a constant is not an omission, it is the bug. It already bit: a scene prompt asked
for 900 Vietnamese words (~2300 tokens) while the wire allowed 1024, and it looked like the
model writing short. Measured targets of 900/850/800/750/800 produced 445/414/532/618/736.

``sdks/python/loreweave_llm/budget.py`` is the seam. This gate is what stops the literals
growing back.

Three forms, because a one-form gate greens on the common one
-------------------------------------------------------------
1. **call-site literal** — ``input={… "max_tokens": 1200}``
2. **signature default** — ``def f(…, max_tokens: int = 1200)``; the *most* common form,
   and the one a call-site-only gate would have reported clean
3. **absent entirely** — no cap at all, so the provider decides

What this gate deliberately does NOT sweep
------------------------------------------
``max_tokens`` is overloaded in this repo. ``select_for_context(max_tokens=800)`` and
``build_glossary_context(max_tokens=1500)`` are INPUT packing budgets — how much glossary
context to select — not output ceilings. They are a different concept that happens to share
a spelling, and folding them in would be the one-name-two-concepts drift the frontend-tool
contract exists to prevent. So a budget only counts when it reaches an **LLM request
payload**, established structurally rather than by name.

Two tiers
---------
**HARD** — an LLM call site whose payload declares no budget AT ALL fails. "Deliberately
unbounded" is sayable (``OutputKind.MIRROR`` → ``0``, this platform's existing wire sentinel
for *omit the cap*), so the only thing that reds here is a site that never decided. Silence
and intent must not look alike.

**RATCHET** — sites whose budget is a bare literal or a variable not traceable to
``call_budget``. That is the migration backlog; it may not grow, and shrinking it is
recorded. Making it hard today would mean ~30 findings and no path to green.

    python scripts/llm-budget-ssot-gate.py           # gate
    python scripts/llm-budget-ssot-gate.py --list    # every call site with its verdict
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Unattributed budgets (bare literal, or a variable not traceable to `call_budget`).
#: Ratcheted. 2026-07-31: **59** — MEASURED, after `/review-impl`.
#:
#: The committed value was 32, and it was wrong for a reason worth keeping: the gate bailed
#: to `opaque` on any payload containing a `**spread`, and `**no_thinking_fields()` is the
#: dominant idiom in composition-service — so 27 sites with a perfectly visible budget were
#: discarded, and the baseline understated the real backlog by 46%. A ratchet set from a
#: detector's blind spot ratchets the blind spot.
#: 2026-07-31 M2 — 59 → **29** after composition-service adopted its registry: 18 signature
#: defaults resolved (`sigs` is now 0 repo-wide) and 12 of the call sites they feed followed.
UNATTRIBUTED_BASELINE = 29

#: Budget calls that pass NO adaptive signal — no `target`, `language`, `reasoning` or
#: `context_length`. Ratcheted, and it is a SECOND axis from the one above: a site here is
#: correctly attributed to `call_budget` and still resolves to the same number every time,
#: which this seam's own module docstring names for what it is —
#:
#:     "A seam that carries no signal is a renamed constant. If a call site calls
#:      call_budget(OutputKind.VERDICT) with no arguments, a future adaptive policy has
#:      nothing to adapt on and this file is ceremony."
#:
#: MEASURED 2026-08-01: **28 of 30** call sites repo-wide passed nothing (the two that
#: do are the judges, fixed the same hour the truncation was found). The seam did not
#: rot — it shipped unwired, and the first gate could not see it because attribution was the
#: only thing it checked. A judge truncated in production (`finish_reason=length`, zero
#: verdicts parsed, the HARD tier silently dead) is what surfaced it.
#:
#: Ratchet rather than hard-fail for the same reason as the line above: ~29 findings and no
#: path to green helps nobody. It may not GROW.
#:
#: 2026-08-02 — **28 → 9**, and the number means something different now. The old count was
#: "sites passing none of four kwargs"; this one is "sites passing none their KIND READS",
#: with `signal_inert` rows excluded because no signal can reach them at all. The old 28 was
#: clearable by adding `language=` to a STRUCTURED call, which `call_budget` discards.
#:
#: What the remaining 9 are, so nobody re-derives them: SIX plan-forge steps (the response is
#: a whole planning package and its item count is what the step generates), `audit_promises`
#: and `extract_tracked_promises` (the list length IS the output — any `target` would be
#: invented), and `compress` (`target`/`language` are eaten by its ceiling; only
#: `context_length` could move it and the call site does not know the model's window).
#: Every one is a call whose size is genuinely undiscoverable before the call, NOT a site
#: nobody got to — which is why this number should be expected to move slowly, or not at all.
NO_SIGNAL_BASELINE = 9

#: The kwargs that make a budget call adaptive. `floor`/`ceiling` are deliberately absent —
#: they are per-call CONSTANTS from the registry, not per-call signal.
ADAPTIVE_SIGNAL = frozenset({"target", "language", "reasoning", "context_length"})

#: …but a kwarg only counts if the KIND actually reads it, and this is the correction that
#: makes the axis above mean anything.
#:
#: MEASURED 2026-08-02, against `call_budget`: `language` is turned into a per-word rate and
#: then consulted ONLY on the PROSE and VERDICT branches. STRUCTURED sizes on
#: `target * _TOKENS_PER_ITEM` and EDIT on `target / 3`; neither looks at it. MIRROR returns
#: the omit sentinel before the sizing model runs and reads NOTHING.
#:
#: So the first version of this ratchet was satisfiable with theatre: adding `language=` to a
#: STRUCTURED call site cleared it from the backlog and changed no resolved budget, ever. A
#: gate that can be turned green without changing behaviour is worse than no gate, because it
#: reports the debt as paid. Verified by probe in each service's registry test.
_KIND_READS: dict[str, frozenset[str]] = {
    "PROSE": frozenset({"target", "language"}),
    "VERDICT": frozenset({"target", "language"}),
    "STRUCTURED": frozenset({"target"}),
    "EDIT": frozenset({"target"}),
    "MIRROR": frozenset(),
}

#: Read on every non-MIRROR branch regardless of kind: `reasoning` scales `need`, and
#: `context_length` applies the window clamp AFTER the floor — which is why it can move even a
#: row whose ceiling equals its floor. That last fact overturned a confident "this row is
#: inert" claim during this slice; it is recorded here so the next reader does not re-derive
#: the wrong version of it.
_KIND_ALWAYS_READS = frozenset({"reasoning", "context_length"})

#: Methods that submit an LLM request with a payload DICT. Structural, not name-based: what
#: makes a budget an OUTPUT budget is that it rides in one of these payloads.
#:
#: `submit` is deliberately absent. It would match `Executor.submit(...)` and any other
#: unrelated `.submit()` — zero false positives today, but a gate should not be one stdlib
#: idiom away from counting a thread pool as an LLM call.
_SUBMIT = {"submit_and_wait", "submit_job"}

#: The OTHER call shape: a request OBJECT, not a payload dict — `client.stream(ChatRequest(…))`.
#: Missing this was the gate's own completeness lie: it printed "79 LLM call sites; every one
#: declares a budget" while never looking at the entire chat streaming path (11 sites), where
#: the budget is `ChatRequest.max_tokens` (models.py:148) and `stream_service.py:366-368`
#: normalises it to None on purpose. The AI-Task Standard had already documented a no-budget
#: site on exactly this seam.
_STREAM = {"stream", "submit_and_await_event"}
_PAYLOAD_KWARGS = ("input", "payload", "body")
_BUDGET_KEYS = {"max_tokens", "max_output_tokens", "max_out", "max_completion_tokens"}

#: A third shape this gate does NOT parse: a raw `POST /internal/llm/stream` with a JSON body
#: (chat-service, lore-enrichment-service, video-gen-service). Named here, and named in the
#: PASS line, because an unscanned surface that goes unmentioned is how "every one" becomes
#: a false claim. Tracked for a follow-up rather than silently excluded.
UNSCANNED_SURFACES = "raw POST /internal/llm/stream (chat, lore-enrichment, video-gen)"

_SKIP_PARTS = ("/tests/", "/build/", "/.venv/", "/node_modules/")


def _is_scanned(p: Path) -> bool:
    s = p.as_posix()
    if any(part in s for part in _SKIP_PARTS):
        return False
    name = p.name
    if name.startswith("test_") or name.endswith("_test.py"):
        return False
    # Diagnostic/eval one-offs under a service's scripts/ dir are not product call paths.
    return "/scripts/" not in s or "/services/" not in s


def budget_provider_names(roots: list[Path]) -> set[str]:
    """Top-level names exported by a module that genuinely resolves through `call_budget`.

    Tier 2 of this design is a per-service call-profile registry — the per-operation knowledge
    belongs to the SERVICE (`PASS_REGISTRY`, `_OPERATION_INSTRUCTIONS` are the precedent) while
    the SDK owns only the mechanism. So the real call site reads
    `"max_tokens": budget_for("translate_chunk")`, and a gate that only recognises a literal
    `call_budget(...)` at the call site would mark every correctly-migrated site UNATTRIBUTED —
    measured: the backlog went UP by 4 after the first migration. A gate that punishes the
    architecture it is enforcing pushes people back to inlining.

    This is EARNED, not a naming exemption: a module contributes names only if it actually
    imports and calls `call_budget`. A file called `llm_budget.py` full of literals gets nothing.
    """
    out: set[str] = set()
    for root in roots:
        for p in sorted(root.rglob("*.py")):
            if not _is_scanned(p):
                continue
            try:
                tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError:
                continue
            calls_it = any(
                isinstance(n, ast.Call)
                and (n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", ""))
                == "call_budget"
                for n in ast.walk(tree)
            )
            if not calls_it:
                continue
            for n in tree.body:
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out.add(n.name)
                elif isinstance(n, ast.Assign):
                    for t in n.targets:
                        if isinstance(t, ast.Name):
                            out.add(t.id)
                elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
                    out.add(n.target.id)
    # These names are repo-global once collected, so a generic one launders every same-named
    # symbol in every other service. The first run returned {'PROFILES', 'TranslationCall',
    # '__all__', 'budget_for'} — and the repo has 453 other top-level `PROFILES`/`__all__`
    # definitions, any of which would have been read as "traced to call_budget". A dunder
    # certainly is not an accessor; a single-word generic is not distinctive enough to be one.
    out.discard("call_budget")
    return {n for n in out
            if not n.startswith("__")
            and ("budget" in n.lower() or "max_tokens" in n.lower() or "output" in n.lower())}


def _call_budget_names(tree: ast.AST) -> set[str]:
    """Names bound to a `call_budget(...)` result (or one of its attributes) in this module.

    `b = call_budget(OutputKind.PROSE, …)` then `"max_tokens": b.max_output_tokens`, and the
    direct `mt = call_budget(…).max_output_tokens`, are both attributed."""
    out: set[str] = set()
    for n in ast.walk(tree):
        if not isinstance(n, ast.Assign):
            continue
        val = n.value
        if isinstance(val, ast.Attribute):
            val = val.value
        if isinstance(val, ast.Call):
            fn = val.func.attr if isinstance(val.func, ast.Attribute) else getattr(val.func, "id", "")
            if fn == "call_budget":
                for t in n.targets:
                    if isinstance(t, ast.Name):
                        out.add(t.id)
    return out


def _ssot_local_names_by_call(tree: ast.AST, providers: set[str]) -> dict[int, set[str]]:
    """{id(call node): names the ENCLOSING function assigned from an SSOT call}.

    The sentinel-resolution shape:

        def propose_cast(…, max_tokens: int | None = None):
            max_tokens = max_tokens or max_tokens_for("propose_cast", target=…)
            …
            input={… "max_tokens": max_tokens}

    This gate previously understood only two shapes: a name bound directly to `call_budget`,
    and a parameter whose DEFAULT resolves through the SSOT. The second is what the sentinel
    conversion deliberately removes — a default argument is evaluated once at import, so it
    can never carry a per-call signal, which is the entire point of paying this rot down.

    So without this the gate PUNISHES the migration it exists to drive: converting twelve
    correct call sites to the adaptive shape moved them from `attributed` to `unattributed`
    and the backlog went UP by eleven. That is the same failure the registry indirection hit
    once already, recorded in `budget_provider_names` two functions above; it is the shape of
    mistake this file keeps making, so it is now named twice.

    Tighter than `_attributed` in TWO ways, and both were needed.

    1. The assigned value must CONTAIN a real call to `call_budget` or a registry accessor. A
       mere reference to an already-attributed name does not bind a new one, so
       `later = round(mt * 0.5)` stays unattributed rather than laundering itself.
    2. The binding is FUNCTION-SCOPED, unlike `_param_defaults_by_call` above. A module-wide
       version of this cleared three sites that nothing in this slice touched — among them
       `self_heal._chat`, a helper whose `max_tokens` comes from its CALLERS, one of which
       passes a flat `400`. The name matched, so the literal would have been laundered into
       `attributed` by an assignment four hundred lines away. Shrinking a backlog by widening
       the detector is how a ratchet stops meaning anything.
    """
    out: dict[int, set[str]] = {}
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        bound: set[str] = set()
        for n in ast.walk(fn):
            if not isinstance(n, (ast.Assign, ast.AnnAssign)):
                continue
            value = getattr(n, "value", None)
            if value is None:
                continue
            has_ssot_call = any(
                isinstance(sub, ast.Call)
                and ((sub.func.attr if isinstance(sub.func, ast.Attribute)
                      else getattr(sub.func, "id", "")) in providers | {"call_budget"})
                for sub in ast.walk(value)
            )
            if not has_ssot_call:
                continue
            targets = [n.target] if isinstance(n, ast.AnnAssign) else n.targets
            bound.update(t.id for t in targets if isinstance(t, ast.Name))
        if not bound:
            continue
        for sub in ast.walk(fn):
            if isinstance(sub, ast.Call):
                out.setdefault(id(sub), set()).update(bound)
    return out


def _attributed(node: ast.AST, names: set[str], providers: set[str]) -> bool:
    """Does this payload value trace to `call_budget` — directly, or via a service registry?"""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            fn = sub.func.attr if isinstance(sub.func, ast.Attribute) else getattr(sub.func, "id", "")
            if fn == "call_budget" or fn in providers:
                return True
        if isinstance(sub, ast.Name) and (sub.id in names or sub.id in providers):
            return True
    return False


def _param_defaults_by_call(tree: ast.AST, names: set[str], providers: set[str]) -> dict[int, set[str]]:
    """{id(call node): parameter names whose DEFAULT resolves through the SSOT}.

    The migrated shape is `def propose_cast(…, max_tokens: int = max_tokens_for("propose_cast"))`
    with `input={… "max_tokens": max_tokens}` — the budget IS attributed, one function boundary
    away. Without this the gate reports every correctly-migrated site as unattributed, which is
    the same "punishes its own architecture" failure the registry indirection already hit: the
    18 signature defaults would clear and the 24 call sites they feed would not move at all.

    Scopes are unioned rather than resolved innermost-first — a name bound in an enclosing
    function is visible in a closure anyway, and a false ATTRIBUTED here is bounded (the site
    genuinely does read a budget-derived parameter) while a false unattributed is the bug above.
    """
    out: dict[int, set[str]] = {}
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        a = fn.args
        pairs = list(zip(a.args[len(a.args) - len(a.defaults):], a.defaults))
        pairs += list(zip(a.kwonlyargs, a.kw_defaults))
        attributed = {arg.arg for arg, d in pairs
                      if d is not None and _attributed(d, names, providers)}
        if not attributed:
            continue
        for sub in ast.walk(fn):
            if isinstance(sub, ast.Call):
                out.setdefault(id(sub), set()).update(attributed)
    return out


def _classify_stream(rel: str, node: ast.Call, names: set[str], providers: set[str]) -> dict:
    """Budget verdict for the request-OBJECT shape: `client.stream(ChatRequest(max_tokens=…))`.

    The budget may be a kwarg on an inline request literal, or the request may be built
    off-site (`client.stream(request)`) — in which case it is honestly opaque rather than
    assumed clean."""
    site = {"file": rel, "line": node.lineno}
    for arg in list(node.args) + [kw.value for kw in node.keywords]:
        if not isinstance(arg, ast.Call):
            continue                                  # a bare name → request built off-site
        for kw in arg.keywords:
            if kw.arg in _BUDGET_KEYS:
                if _attributed(kw.value, names, providers):
                    return {**site, "verdict": "attributed"}
                if isinstance(kw.value, ast.Constant) and kw.value.value == 0:
                    return {**site, "verdict": "attributed"}
                if isinstance(kw.value, ast.Constant):
                    return {**site, "verdict": "literal"}
                return {**site, "verdict": "unattributed"}
        # An inline request literal with NO budget kwarg really has no budget.
        return {**site, "verdict": "ABSENT"}
    return {**site, "verdict": "opaque"}


def scan() -> tuple[list[dict], list[dict]]:
    """(call sites, signature defaults that feed an LLM payload)."""
    sites: list[dict] = []
    sigs: list[dict] = []
    roots = [ROOT / "services", ROOT / "sdks"]
    providers = budget_provider_names(roots)
    for root in roots:
        for p in sorted(root.rglob("*.py")):
            if not _is_scanned(p):
                continue
            try:
                tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError:
                continue
            rel = p.relative_to(ROOT).as_posix()
            names = _call_budget_names(tree)
            param_budgets = _param_defaults_by_call(tree, names, providers)
            local_budgets = _ssot_local_names_by_call(tree, providers)
            for _cid, _bound in local_budgets.items():
                param_budgets.setdefault(_cid, set()).update(_bound)

            for n in ast.walk(tree):
                if not isinstance(n, ast.Call):
                    continue
                fn = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
                if fn in _STREAM:
                    sites.append(_classify_stream(
                        rel, n, names | param_budgets.get(id(n), set()), providers))
                    continue
                if fn not in _SUBMIT:
                    continue
                payload = next((kw.value for kw in n.keywords if kw.arg in _PAYLOAD_KWARGS), None)
                if payload is None or not isinstance(payload, ast.Dict):
                    # Built elsewhere — this gate cannot see it, and saying otherwise would
                    # be the "asserted with nothing behind it" shape it exists to reject.
                    sites.append({"file": rel, "line": n.lineno, "verdict": "opaque"})
                    continue
                # Read the EXPLICIT keys first, then decide about any `**spread`.
                #
                # This used to bail to `opaque` the moment a payload contained a spread —
                # and `input={…, "max_tokens": max_tokens, **no_thinking_fields()}` is the
                # dominant idiom in composition-service, so 27 sites with a perfectly
                # visible budget were thrown away over an unrelated `**`. Same
                # bail-on-a-construct-you-could-handle shape as deprecated-tool-scan's
                # per-line reading of a wrapped call.
                #
                # The dangerous half was the other direction: a payload with a spread and
                # NO budget key reported `opaque`, so the HARD rule was silently bypassed
                # by an idiom that has nothing to do with budgets. Measured 0 such sites
                # today — one `**kwargs` away from being live.
                val = None
                for k, v in zip(payload.keys, payload.values):
                    if isinstance(k, ast.Constant) and k.value in _BUDGET_KEYS:
                        val = v
                if val is None and any(k is None for k in payload.keys):
                    # No explicit budget, but a spread COULD carry one — genuinely unknown.
                    sites.append({"file": rel, "line": n.lineno, "verdict": "opaque"})
                    continue
                if val is None:
                    sites.append({"file": rel, "line": n.lineno, "verdict": "ABSENT"})
                elif _attributed(val, names | param_budgets.get(id(n), set()), providers):
                    sites.append({"file": rel, "line": n.lineno, "verdict": "attributed"})
                elif isinstance(val, ast.Constant) and val.value == 0:
                    # The wire sentinel for "omit the cap" — a decision, not a gap.
                    sites.append({"file": rel, "line": n.lineno, "verdict": "attributed"})
                elif isinstance(val, ast.Constant):
                    sites.append({"file": rel, "line": n.lineno, "verdict": "literal"})
                else:
                    sites.append({"file": rel, "line": n.lineno, "verdict": "unattributed"})

            # Form 2 — a signature default that is threaded into an LLM payload. Counted only
            # when the SAME module submits a request, so a context-packer's `max_tokens=800`
            # (a different concept sharing a spelling) is not swept in.
            if not any(s["file"] == rel for s in sites):
                continue
            for n in ast.walk(tree):
                if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                a = n.args
                pairs = list(zip(a.args[len(a.args) - len(a.defaults):], a.defaults))
                pairs += list(zip(a.kwonlyargs, a.kw_defaults))
                for arg, d in pairs:
                    if arg.arg in _BUDGET_KEYS and isinstance(d, ast.Constant) \
                            and isinstance(d.value, int) and d.value != 0:
                        sigs.append({"file": rel, "line": n.lineno,
                                     "fn": n.name, "arg": arg.arg, "default": d.value})
    return sites, sigs


def load_registry_rows() -> dict[str, dict]:
    """code -> {kind, signal_inert, service}, read STATICALLY from each service's registry.

    Parsed rather than imported on purpose. CI runs this gate in the `lints` job, which is a
    bare checkout with no `pip install` — importing `app.llm_budget` would need the service's
    deps AND `loreweave_llm` on the path, so the gate would crash there while passing locally.
    Wrapping that import in a `try/except` would be worse: every row would silently vanish,
    every site would look exempt, and the gate would report PASS for the wrong reason. That is
    the fail-open shape this repo keeps paying for, so the parse is the honest option.

    A row this cannot read is simply absent, and an absent row makes its call sites fall back
    to the kwarg-only rule below — narrower than the truth, never wider.
    """
    rows: dict[str, dict] = {}
    for reg in sorted((ROOT / "services").glob("*/app/llm_budget.py")):
        service = reg.relative_to(ROOT / "services").parts[0]
        try:
            tree = ast.parse(reg.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            target_names = (
                [node.target] if isinstance(node, ast.AnnAssign)
                else getattr(node, "targets", [])
            )
            if not any(getattr(t, "id", None) == "PROFILES" for t in target_names):
                continue
            if not isinstance(getattr(node, "value", None), ast.Dict):
                continue
            for key, val in zip(node.value.keys, node.value.values):
                if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                    continue
                if not isinstance(val, ast.Call):
                    continue
                kind = None
                # `CallProfile(OutputKind.VERDICT, …)` — positional first, keyword otherwise.
                for cand in list(val.args) + [k.value for k in val.keywords if k.arg == "kind"]:
                    if isinstance(cand, ast.Attribute) and \
                            getattr(cand.value, "id", None) == "OutputKind":
                        kind = cand.attr
                        break
                inert = any(
                    k.arg == "signal_inert" and isinstance(k.value, ast.Constant)
                    and k.value.value is True
                    for k in val.keywords
                )
                rows[key.value] = {"kind": kind, "signal_inert": inert, "service": service}
    return rows


def _codes_at(node: ast.Call) -> list[str]:
    """Every profile code this budget call could resolve to.

    A LIST, not a value, because `decoupled_translate` picks its row with a conditional —
    `budget_for("compact_memo" if action[0] == "compact" else "translate_session_chunk")` —
    and collapsing that to "unknown" would drop a real site into the fallback path. Both
    branches are resolved and the site is exempt only if EVERY branch it can take is inert.
    """
    if not node.args:
        return []
    a = node.args[0]
    if isinstance(a, ast.Constant) and isinstance(a.value, str):
        return [a.value]
    if isinstance(a, ast.IfExp):
        return [b.value for b in (a.body, a.orelse)
                if isinstance(b, ast.Constant) and isinstance(b.value, str)]
    return []


def scan_signal() -> list[dict]:
    """Every `budget_for` / `max_tokens_for` call, and whether it passes any adaptive signal.

    A SECOND axis from `scan()`. That one asks "is this budget traceable to the seam"; this
    one asks "does the seam get told anything". A call can pass the first and fail this — 29
    of 31 did on the day this was written — and the failure is invisible precisely because the
    first check is green.
    """
    out: list[dict] = []
    rows = load_registry_rows()
    for py in (ROOT / "services").rglob("*.py"):
        posix = py.as_posix()
        if "/tests/" in posix or "/build/" in posix:
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if fn not in ("budget_for", "max_tokens_for"):
                continue
            # The registry's own definition of `max_tokens_for` forwards **kw; it is the
            # mechanism, not a call site.
            if py.name == "llm_budget.py":
                continue
            passed = {k.arg for k in node.keywords} & ADAPTIVE_SIGNAL
            codes = _codes_at(node)
            code = codes[0] if len(codes) == 1 else ("|".join(codes) if codes else "?")

            # Score the kwargs against what the KIND reads, not against the kwarg set. A
            # `language=` on a STRUCTURED row is discarded by `call_budget`, so counting it
            # would let this ratchet be cleared without a single budget changing.
            known = [rows[c] for c in codes if c in rows]
            if known:
                readable: set[str] = set()
                for r in known:
                    readable |= _KIND_READS.get(r["kind"] or "", ADAPTIVE_SIGNAL)
                    if r["kind"] != "MIRROR":
                        readable |= _KIND_ALWAYS_READS
                effective = passed & readable
                # Exempt only when EVERY row this site can resolve to declares itself inert —
                # a conditional whose branches disagree is not exempt.
                inert = all(r["signal_inert"] for r in known)
            else:
                # Unresolvable row: fall back to the raw kwarg test rather than guessing a
                # kind. Narrower than the truth, never wider — an unknown row can never be
                # granted an exemption it did not declare.
                effective, inert = passed, False

            out.append({"file": posix.split("/services/")[-1], "line": node.lineno,
                        "code": code, "signal": sorted(effective),
                        "declared": sorted(passed), "inert": inert,
                        "kind": known[0]["kind"] if known else None})
    return out


def main() -> int:
    sites, sigs = scan()
    absent = [s for s in sites if s["verdict"] == "ABSENT"]
    literal = [s for s in sites if s["verdict"] == "literal"]
    unattr = [s for s in sites if s["verdict"] == "unattributed"]
    attributed = [s for s in sites if s["verdict"] == "attributed"]
    opaque = [s for s in sites if s["verdict"] == "opaque"]
    backlog = len(literal) + len(unattr) + len(sigs)

    if "--list" in sys.argv:
        print(f"{len(sites)} LLM call site(s)\n")
        for s in sites:
            print(f"  [{s['verdict']:12}] {s['file']}:{s['line']}")
        print(f"\n{len(sigs)} signature default(s) in modules that submit LLM requests")
        for s in sigs:
            print(f"  {s['file']}:{s['line']}  {s['fn']}({s['arg']}={s['default']})")
        return 0

    rc = 0
    if absent:
        print("FAIL — LLM call site with NO output budget declared:\n")
        for s in absent:
            print(f"   {s['file']}:{s['line']}")
        print("\n   Decide, then say so. If the model's natural stop IS correct here")
        print("   (translation, transcription — the output's length is set by the input),")
        print("   declare it: `call_budget(OutputKind.MIRROR).max_output_tokens` → 0, which")
        print("   the SDK strips (models.py) so the wire is unchanged. Otherwise size it")
        print("   from the kind. Silence and intent must not look alike.")
        rc = 1

    if backlog != UNATTRIBUTED_BASELINE:
        verb = "grew to" if backlog > UNATTRIBUTED_BASELINE else "dropped to"
        print(f"\n{'FAIL' if backlog > UNATTRIBUTED_BASELINE else 'NOTE'} — budgets not "
              f"traceable to call_budget() {verb} {backlog} (baseline {UNATTRIBUTED_BASELINE}).")
        if backlog > UNATTRIBUTED_BASELINE:
            print("   A new flat literal is exactly what the seam was built to stop.")
            for s in (literal + unattr)[-6:]:
                print(f"     {s['file']}:{s['line']}")
            for s in sigs[-4:]:
                print(f"     {s['file']}:{s['line']}  {s['fn']}({s['arg']}={s['default']})")
        else:
            print(f"   Progress — lower UNATTRIBUTED_BASELINE to {backlog} in "
                  f"{Path(__file__).name}.")
        rc = 1

    signal_sites = scan_signal()
    # Three classes now, where there used to be two. A row that declares `signal_inert` is
    # not backlog — no signal can reach it — and lumping it in with sites that DO have signal
    # to give made the ratchet a number nobody could act on.
    inert_sites = [s for s in signal_sites if s["inert"]]
    no_signal = [s for s in signal_sites if not s["signal"] and not s["inert"]]

    # A site passing a kwarg its kind discards. Reported explicitly because it is the exact
    # move that would clear a site from the ratchet without changing a budget, and a reviewer
    # reading a shrinking backlog cannot otherwise tell the difference.
    theatre = [s for s in signal_sites
               if not s["inert"] and s["declared"] and not s["signal"]]
    if theatre:
        print("\nFAIL — budget call passes a signal its KIND does not read:\n")
        for s in theatre:
            print(f"   {s['file']}:{s['line']}  {s['code']} ({s['kind']}) "
                  f"passes {s['declared']} — discarded by call_budget")
        print("\n   `language` is read only on PROSE and VERDICT; STRUCTURED and EDIT size on")
        print("   `target` alone; MIRROR reads nothing. Pass what the kind consumes, or mark")
        print("   the row `signal_inert=True` if genuinely nothing can size it.")
        rc = 1

    if len(no_signal) != NO_SIGNAL_BASELINE:
        grew = len(no_signal) > NO_SIGNAL_BASELINE
        print(f"\n{'FAIL' if grew else 'NOTE'} — budget calls passing NO adaptive signal "
              f"{'grew to' if grew else 'dropped to'} {len(no_signal)} "
              f"(baseline {NO_SIGNAL_BASELINE}).")
        if grew:
            print("   A budget call with no target/language/reasoning/context_length is a")
            print("   renamed constant — this seam's own docstring says so. Pass what the")
            print("   call site already knows.")
            for s in no_signal[-6:]:
                print(f"     {s['file']}:{s['line']}  {s['code']}")
        else:
            print(f"   Progress — lower NO_SIGNAL_BASELINE to {len(no_signal)} in "
                  f"{Path(__file__).name}.")
        rc = 1

    if rc == 0:
        # "every one declares a budget" was this gate's own completeness lie — true of the
        # sites it scanned, printed as though it were true of the repo. The scanned surface
        # is now named, and so is the one that is not.
        print(f"llm-budget-ssot-gate: PASS — {len(sites)} LLM call site(s) scanned "
              f"(payload-dict + request-object shapes); none leaves its budget undeclared.")
        print(f"  {len(attributed)} traced to call_budget() · {backlog} held at baseline "
              f"({len(literal)} literal, {len(unattr)} unattributed, {len(sigs)} signature "
              f"defaults) · {len(opaque)} built off-site, not statically visible.")
        print(f"  NOT scanned: {UNSCANNED_SURFACES}.")
        carrying = len(signal_sites) - len(no_signal) - len(inert_sites)
        print(f"  adaptive signal: {carrying}/{len(signal_sites)} budget calls carry one that "
              f"their KIND reads · {len(inert_sites)} declared signal_inert "
              f"(nothing can size them) · {len(no_signal)} held at baseline.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
