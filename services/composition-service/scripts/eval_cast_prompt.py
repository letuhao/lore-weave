"""CAST-PROMPT EVAL - did asking for `roles` change what the cast pass DECIDES? (SPEC 4.2c)

WHY THIS EXISTS
---------------
T37b part 1 edited an LLM output contract: `build_propose_cast_messages` now asks for one
more key (`roles`, the structured half of `relationships`) and names it in the return schema.
The spec sequenced the change to land *with* this eval rather than beside it, in one sentence:

    "a prompt change that shifts `is_new` classification or cast sizing would be a regression
     the graph write is not worth."

So those are the two metrics, and they are not chosen here - they are read off the spec.

"ADDITIVE BY CONSTRUCTION" IS AN ARGUMENT, NOT A MEASUREMENT
------------------------------------------------------------
The change requests one key more and removes none, and the parser defaults it to `[]`. That
argument is why the change was safe to WRITE. It is not evidence about a model, because a
model does not read a diff - it reads a longer instruction with a JSON example embedded in
it, and "the schema line got longer" is exactly the kind of edit that quietly costs a model a
slot in its output array or tips a borderline `is_new` judgement.

SEPARATING THE PROMPT FROM THE SAMPLER
--------------------------------------
`propose_cast` runs at temperature 0.4. Two runs of the SAME prompt disagree. So a single
A-vs-B comparison cannot separate "the prompt moved the model" from "the sampler moved", and
a criterion that cannot tell those apart is not a criterion.

Both arms are therefore repeated and compared with an EXACT PERMUTATION TEST: pool the 2R
observations, enumerate every way to split them back into two arms of R, and ask how often
chance alone reproduces a mean gap at least as large as the observed one. That fraction is
the p-value; below 0.05 the metric SHIFTED.

    Rejected: `floor = max(range(control), range(treatment))`, which was the first design here
    and is quietly self-serving - the arm UNDER TEST can buy its own acquittal by being noisy,
    because widening the treatment's spread raises the bar its own mean shift has to clear. A
    permutation test has no such knob: the treatment's variance goes into the null
    distribution on the same footing as the control's.

R < 4 IS REFUSED, AND THAT IS RULE 3 IN ARITHMETIC
--------------------------------------------------
With R repeats per arm there are C(2R, R) splits, and the observed split plus its mirror are
always at least as extreme as themselves. So the smallest p-value the test can EVER return is
2 / C(2R, R):

    R = 3  ->  2/20  = 0.100    already above alpha=0.05: the test cannot fire. Ever.
    R = 4  ->  2/70  = 0.029    can fire, on a complete separation.

At R=3 this eval would be incapable of reporting SHIFT no matter what the model did - green
by construction, which is the exact failure this file was written to prevent. It refuses to
run instead.

Honest limit, stated rather than hidden: this convicts on a shift in LOCATION. A change that
left the means alone while widening the distribution would pass, so both arms' ranges are
printed on every run for a human to read.

A FAILED PARSE IS AN ERROR, NOT AN AGREEMENT
--------------------------------------------
If a run fails to parse, its cast size is 0 and its `is_new` count is 0. Folded into a mean
those look like data and can even make two arms agree. The suite next door
(`app/eval/suite.py`) already learned this: an outage scored as a quiet detector is fiction.
Any unparsed run makes the whole eval ERROR.

WHAT IT TALKS TO
----------------
The engine's REAL `build_propose_cast_messages` and `parse_cast` - the production functions,
not a copy, so a later prompt edit is measured rather than missed. Production's temperature,
budget call and no-thinking fields are mirrored (an A/B baseline that does not model
production measures a different system).

The model is called directly at an OpenAI-compatible base URL and PINNED by name. That is
deliberate and it is why this file lives in `services/<svc>/scripts/eval_*` - the provider
gate exempts exactly this shape, for exactly this reason: an eval that silently switches
models measures nothing.

USAGE
    python eval_cast_prompt.py --model google/gemma-4-26b-a4b-qat --repeats 4
    python eval_cast_prompt.py --model <id> --write baselines/cast-prompt-v1.json
    python eval_cast_prompt.py --model <id> --against baselines/cast-prompt-v1.json
    python eval_cast_prompt.py --selftest          # offline; proves the criterion can RED

EXIT 0 = no shift detected. 1 = a shift, or a broken instrument (ERROR).
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import statistics
import sys
import urllib.error
import urllib.request

# The service package lives one level up; say so relatively rather than as a host path.
_SVC = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SVC))
sys.path.insert(0, str(_SVC.parent.parent / "sdks" / "python"))

# `app.engine.cast_plan` imports the settings object at module scope. This eval never opens a
# DB - it calls two pure functions and one HTTP endpoint - so the DSN is a deliberate dead end
# (port 1 on loopback) rather than any real database. Set before the import, not after.
for _k, _v in (("COMPOSITION_DB_URL", "postgresql://u:p@127.0.0.1:1/eval-never-connects"),
               ("INTERNAL_SERVICE_TOKEN", "eval-unused"),
               ("JWT_SECRET", "s" * 32), ("CONFIRM_TOKEN_SIGNING_SECRET", "s" * 32)):
    os.environ.setdefault(_k, _v)

from app.engine.cast_plan import (  # noqa: E402
    _INVENTED_CAST_ALLOWANCE, _MAX_KNOWN_CAST, build_propose_cast_messages, parse_cast,
)
from app.llm_budget import max_tokens_for  # noqa: E402
from loreweave_llm import no_thinking_fields  # noqa: E402

# Reused from `eval_a_validate` rather than invented, so this measures the same premises the
# other A-evals do. Each row is (premise, the book's existing roster).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import eval_a_validate as E  # noqa: E402

BASE_URL = os.environ.get("EVAL_CHAT_BASE_URL", "http://127.0.0.1:1234/v1")

# --------------------------------------------------------------------------------------
# The control arm: the prompt as it stood BEFORE T37b part 1.
# --------------------------------------------------------------------------------------
# Expressed as the exact inverse of the shipped diff, applied to the LIVE prompt, so the two
# arms can never differ in anything but the change under test - a hand-copied "old prompt"
# constant would rot the first time an unrelated word changed, and would then be measuring two
# differences while reporting one.
#
# Both patches are ASSERTED to apply. If a future edit moves these spans the eval REFUSES to
# run instead of silently comparing the live prompt against itself and reporting "no shift" -
# the failure mode this whole file exists to prevent.
_REVERSE_PATCHES = (
    ('"relationships" (ties to other cast, as prose), '
     '"roles" (the SAME ties, structured: '
     '[{"predicate":"betrayed","object":"<other cast NAME>"}]; predicate a short verb '
     'phrase, object another character name; [] if none), ',
     '"relationships" (ties to other cast), '),
    ('"relationships":...,"roles":[...],"summary":...',
     '"relationships":...,"summary":...'),
)


class PromptDrift(RuntimeError):
    """The live prompt no longer contains a span this eval removes to build its control."""


def control_system(system: str) -> str:
    """The pre-T37b system prompt, derived from the live one."""
    out = system
    for old, new in _REVERSE_PATCHES:
        if old not in out:
            raise PromptDrift(
                "the cast prompt changed and this eval's control is stale - it can no longer "
                "remove:\n  " + old[:90] + "\nRe-derive _REVERSE_PATCHES against the current "
                "build_propose_cast_messages before trusting any verdict.")
        out = out.replace(old, new)
    return out


# --------------------------------------------------------------------------------------
# Running one observation
# --------------------------------------------------------------------------------------
def _chat(model: str, system: str, user: str, max_tokens: int, timeout: int = 300) -> str:
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        # Mirrors `propose_cast` exactly: an A/B whose baseline does not model production
        # measures a system nobody runs.
        "temperature": 0.4, "max_tokens": max_tokens, **no_thinking_fields(),
    }
    req = urllib.request.Request(BASE_URL.rstrip("/") + "/chat/completions",
                                 data=json.dumps(body).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode())
    return payload["choices"][0]["message"]["content"] or ""


def observe(model: str, premise: str, roster: list[str], *, arm: str) -> dict:
    """One run of one arm. `parsed` False is an ERROR signal, never a zero."""
    system, user = build_propose_cast_messages(
        premise, "en", ["fantasy"], known_cast=roster, canon="")
    if arm == "control":
        system = control_system(system)
    elif arm == "sabotage":
        # Only reachable from --sabotage. See its help: this is the arm that proves the
        # criterion can red against a REAL model, not just against synthetic numbers.
        system = system + " Return EXACTLY two characters, no more."
    budget = max_tokens_for("propose_cast",
                            target=len(roster[:_MAX_KNOWN_CAST]) + _INVENTED_CAST_ALLOWANCE,
                            context_length=None)
    try:
        content = _chat(model, system, user, budget)
    except (urllib.error.URLError, OSError, KeyError, ValueError) as exc:
        return {"arm": arm, "parsed": False, "why": f"{type(exc).__name__}: {exc}",
                "cast_size": 0, "is_new": 0, "roles_rows": 0}
    cast = parse_cast(content)
    if not cast:
        return {"arm": arm, "parsed": False, "why": "parse_cast returned []",
                "cast_size": 0, "is_new": 0, "roles_rows": 0}
    return {"arm": arm, "parsed": True, "why": "",
            "cast_size": len(cast),
            "is_new": sum(1 for c in cast if c.is_new),
            "roles_rows": sum(len(c.roles) for c in cast)}


# --------------------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------------------
#: Below this p-value a metric is called SHIFTED. Pre-registered here rather than chosen after
#: reading a run - a threshold picked once the numbers are on screen measures the analyst.
ALPHA = 0.05

#: Enumerating C(2R, R) splits is exact and cheap at the repeat counts this eval uses
#: (R=4 -> 70, R=8 -> 12 870). Past this many, sample instead of enumerating; the p-value
#: becomes an estimate and `exact` says so rather than letting the report imply otherwise.
_MAX_EXACT_SPLITS = 200_000


def permutation_p(ctrl: list[float], treat: list[float]) -> tuple[float, bool]:
    """Two-sided p for |mean(treat) - mean(ctrl)| under the null that the label is arbitrary.

    Every split is counted, INCLUDING the observed one. Excluding it would let a complete
    separation reach p=0 and report certainty that R observations cannot support.
    """
    import itertools
    import math
    import random

    pool = list(ctrl) + list(treat)
    n, k = len(pool), len(ctrl)
    observed = abs(statistics.mean(treat) - statistics.mean(ctrl))
    total_sum = sum(pool)
    # A split is fully determined by which indices land in the control arm; the gap follows
    # from that arm's sum, so there is no need to materialise both sides.
    def _gap(csum: float) -> float:
        return abs((total_sum - csum) / (n - k) - csum / k)

    n_splits = math.comb(n, k)
    if n_splits <= _MAX_EXACT_SPLITS:
        hits = sum(1 for combo in itertools.combinations(range(n), k)
                   if _gap(sum(pool[i] for i in combo)) >= observed - 1e-12)
        return hits / n_splits, True
    rng = random.Random(0)  # fixed seed: a p-value that changes between reruns is not evidence
    draws = _MAX_EXACT_SPLITS
    idx = list(range(n))
    hits = 0
    for _ in range(draws):
        rng.shuffle(idx)
        if _gap(sum(pool[i] for i in idx[:k])) >= observed - 1e-12:
            hits += 1
    return hits / draws, False


def score_metric(ctrl: list[float], treat: list[float]) -> dict:
    """Did the label 'treatment' explain the gap, or would any relabelling do as well?"""
    delta = abs(statistics.mean(treat) - statistics.mean(ctrl))
    p, exact = permutation_p(ctrl, treat)
    return {"control_mean": round(statistics.mean(ctrl), 3),
            "treatment_mean": round(statistics.mean(treat), 3),
            "control_range": max(ctrl) - min(ctrl),
            "treatment_range": max(treat) - min(treat),
            "delta": round(delta, 3), "p": round(p, 4), "exact": exact,
            "shifted": p < ALPHA}


def score_run(rows: list[dict]) -> dict:
    """rows: every observation, each carrying `premise_idx`, `arm`, and the metrics."""
    unparsed = [r for r in rows if not r["parsed"]]
    per_premise = []
    for idx in sorted({r["premise_idx"] for r in rows}):
        c = [r for r in rows if r["premise_idx"] == idx and r["arm"] == "control"]
        t = [r for r in rows if r["premise_idx"] == idx and r["arm"] != "control"]
        if not c or not t:
            continue
        per_premise.append({
            "premise_idx": idx,
            "cast_size": score_metric([r["cast_size"] for r in c], [r["cast_size"] for r in t]),
            "is_new": score_metric([r["is_new"] for r in c], [r["is_new"] for r in t]),
            "treatment_roles_rows": sum(r["roles_rows"] for r in t),
        })
    shifted = [p for p in per_premise
               if p["cast_size"]["shifted"] or p["is_new"]["shifted"]]
    if unparsed:
        verdict = "ERROR"
    elif shifted:
        verdict = "SHIFT"
    else:
        verdict = "NO-SHIFT"
    return {"verdict": verdict, "per_premise": per_premise,
            "unparsed": [{"premise_idx": r["premise_idx"], "arm": r["arm"], "why": r["why"]}
                         for r in unparsed],
            "shifted_premises": [p["premise_idx"] for p in shifted]}


def render(result: dict) -> str:
    lines = []
    for p in result["per_premise"]:
        lines.append(f"  premise #{p['premise_idx']}")
        for key in ("cast_size", "is_new"):
            m = p[key]
            flag = "SHIFT" if m["shifted"] else "ok"
            lines.append(
                f"    {key:<10} control {m['control_mean']:>5} (range {m['control_range']})"
                f"  treatment {m['treatment_mean']:>5} (range {m['treatment_range']})"
                f"  delta {m['delta']}  p={m['p']}{'' if m['exact'] else '~'}  -> {flag}")
        lines.append(f"    roles rows produced by the treatment arm: {p['treatment_roles_rows']}")
    for u in result["unparsed"]:
        lines.append(f"  UNPARSED premise #{u['premise_idx']} arm={u['arm']}: {u['why']}")
    lines.append(f"  VERDICT: {result['verdict']}")
    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# Self-test - offline, and it must prove the criterion CAN fail
# --------------------------------------------------------------------------------------
def _rows(arm: str, sizes, is_new, roles_rows=0, idx=0) -> list[dict]:
    if not isinstance(is_new, (list, tuple)):
        is_new = [is_new] * len(sizes)
    return [{"premise_idx": idx, "arm": arm, "parsed": True, "why": "",
             "cast_size": s, "is_new": n, "roles_rows": roles_rows}
            for s, n in zip(sizes, is_new)]


def selftest() -> int:
    fails = []

    def check(name, cond, detail=""):
        print(f"  {'PASS' if cond else 'FAIL'}  {name}"
              + (f" - {detail}" if detail and not cond else ""))
        if not cond:
            fails.append(name)

    # 1. The control derivation still applies to the LIVE prompt. This is the drift guard:
    #    without it every other check below could be green while both arms ran the same text.
    live, _ = build_propose_cast_messages("p", "en", None, known_cast=["Kael"])
    try:
        ctrl, applied = control_system(live), True
    except PromptDrift as exc:
        ctrl, applied = str(exc), False
    check("reverse-patches apply to the live prompt", applied, str(ctrl)[:140])
    if applied:
        check("control prompt does NOT ask for roles", '"roles"' not in ctrl)
        check("treatment prompt DOES ask for roles", '"roles"' in live)
        check("control is genuinely shorter", len(ctrl) < len(live),
              f"ctrl={len(ctrl)} live={len(live)}")

    # 2. The criterion reds on a real shift. Sizes collapse 8 -> 3 while the sampler's own
    #    spread is 1: if this scored NO-SHIFT the eval could never fail and would be theatre.
    check("a collapsed cast size scores SHIFT",
          score_run(_rows("control", (8, 8, 7, 8), 2)
                    + _rows("treatment", (3, 3, 4, 3), 2, 4))["verdict"] == "SHIFT")

    # 3. ...and on an is_new shift alone, with cast size held identical - the spec names TWO
    #    metrics, so a suite that only watches one of them is half an instrument.
    check("an is_new swing scores SHIFT",
          score_run(_rows("control", (8, 8, 8, 8), [1, 1, 2, 1])
                    + _rows("treatment", (8, 8, 8, 8), [6, 6, 7, 6], 4))["verdict"] == "SHIFT")

    # 4. It stays quiet when only the sampler moved - the other half of a real criterion.
    #    Means identical, both arms noisy. A suite that flags this cries wolf every run.
    check("sampler noise alone scores NO-SHIFT",
          score_run(_rows("control", (8, 7, 8, 9), 2)
                    + _rows("treatment", (9, 8, 7, 8), 2, 4))["verdict"] == "NO-SHIFT")

    # 4b. THE REWRITE, PINNED. This is the case the first design here acquitted: the treatment
    #     buys itself a wide range (5,5,5,9 spans 4) and the old rule was
    #     `delta > max(range_c, range_t)` - 4 > 4 is False, so a cast halved from 10 to ~6
    #     scored "ok". A permutation test convicts it, because a noisy arm cannot raise its own
    #     bar. If this check ever goes green-by-passing again, the floor design came back.
    check("a noisy treatment cannot buy its own acquittal",
          score_run(_rows("control", (10, 10, 10, 10), 2)
                    + _rows("treatment", (5, 5, 5, 9), 2, 4))["verdict"] == "SHIFT")

    # 4c. The refusal in main() is arithmetic, not taste: at R=3 even a COMPLETE separation -
    #     every treatment value below every control value - cannot clear alpha. An eval that
    #     accepted R=3 would be green by construction.
    p3, _ = permutation_p([8, 8, 8], [3, 3, 3])
    p4, _ = permutation_p([8, 8, 8, 8], [3, 3, 3, 3])
    check("R=3 cannot reach alpha even on a complete separation", p3 >= ALPHA, f"p={p3}")
    check("R=4 can", p4 < ALPHA, f"p={p4}")

    # 5. A failed run is ERROR, never a datapoint. An unparsed run contributes cast_size 0,
    #    and two arms that both fail would otherwise agree perfectly and report NO-SHIFT.
    dead = [{"premise_idx": 0, "arm": a, "parsed": False, "why": "boom",
             "cast_size": 0, "is_new": 0, "roles_rows": 0}
            for a in ("control",) * 3 + ("treatment",) * 3]
    check("a total outage scores ERROR, not NO-SHIFT", score_run(dead)["verdict"] == "ERROR")

    # 6. One dead run among good ones still errors. This is the partial-outage case, and it is
    #    the one that would otherwise slip through: five clean runs plus one timeout still
    #    produce a mean, and a mean always looks like a measurement.
    check("a single unparsed run poisons the verdict",
          score_run(_rows("control", (8, 8, 8), 2) + _rows("treatment", (8, 8), 2, 4)
                    + [{"premise_idx": 0, "arm": "treatment", "parsed": False,
                        "why": "timeout", "cast_size": 0, "is_new": 0,
                        "roles_rows": 0}])["verdict"] == "ERROR")

    print(f"\n  {len(fails)} failure(s)" if fails else "\n  all checks passed")
    return 1 if fails else 0


# --------------------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model", help="chat model id, pinned (see the module docstring)")
    ap.add_argument("--repeats", type=int, default=4,
                    help="runs per arm per premise; <4 is refused - see the module docstring, "
                         "at R=3 the permutation test's smallest attainable p is 0.1 and the "
                         "eval could never report SHIFT")
    ap.add_argument("--premises", type=int, default=len(E.PREMISES))
    ap.add_argument("--sabotage", action="store_true",
                    help="run the treatment arm with a cast-capping instruction appended; the "
                         "eval MUST report SHIFT. Proves the criterion reds against a real "
                         "model, not only against the synthetic rows in --selftest.")
    ap.add_argument("--write", help="record this result as a baseline")
    ap.add_argument("--against", help="compare the verdict to a recorded baseline")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        print("cast-prompt eval - selftest (offline)")
        return selftest()
    if not args.model:
        ap.error("--model is required (or use --selftest)")
    if args.repeats < 4:
        ap.error("--repeats must be >= 4: at R=3 the exact permutation test's smallest "
                 f"attainable p is 2/C(6,3) = 0.1, which never clears alpha={ALPHA} - the eval "
                 "would be structurally incapable of reporting SHIFT")

    treat_arm = "sabotage" if args.sabotage else "treatment"
    print(f"cast-prompt eval - model={args.model} repeats={args.repeats} "
          f"premises={args.premises} arms=control/{treat_arm}")
    rows = []
    for idx, (premise, roster) in enumerate(E.PREMISES[:args.premises]):
        for arm in ("control", treat_arm):
            for r in range(args.repeats):
                print(f"  premise #{idx} - {arm} - run {r + 1}/{args.repeats} ...", flush=True)
                obs = observe(args.model, premise, roster, arm=arm)
                obs["premise_idx"] = idx
                rows.append(obs)
                if not obs["parsed"]:
                    print(f"    unparsed: {obs['why']}")

    result = score_run(rows)
    print()
    print(render(result))

    if args.write:
        pathlib.Path(args.write).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(args.write).write_text(
            json.dumps({"model": args.model, "repeats": args.repeats, **result}, indent=2) + "\n")
        print(f"  wrote baseline -> {args.write}")
        return 0
    if args.against:
        prior = json.loads(pathlib.Path(args.against).read_text())
        if prior["verdict"] != result["verdict"]:
            print(f"  BASELINE MOVED: {prior['verdict']} -> {result['verdict']}")
            return 1

    if args.sabotage:
        # Inverted on purpose: under --sabotage a NO-SHIFT verdict is the failure. An eval that
        # cannot detect a cast capped at two would report NO-SHIFT for any prompt at all.
        ok = result["verdict"] == "SHIFT"
        print(f"  SABOTAGE ARM: expected SHIFT, got {result['verdict']} -> "
              f"{'the criterion can red' if ok else 'THE CRITERION IS BLIND'}")
        return 0 if ok else 1
    return 0 if result["verdict"] == "NO-SHIFT" else 1


if __name__ == "__main__":
    sys.exit(main())
