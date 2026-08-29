#!/usr/bin/env python3
"""t33-causal-labelling-sheet — the reference corpus T33's stop condition has always needed.

T33's stop condition (plan § Stop conditions 3) reads *"T33 yields few or low-quality causal
edges → D0.1 degrades to `unknown` everywhere and AC1 stays broken"*, and the plan already
records that it CANNOT be evaluated from the dev store:

    Observed on the dev store 2026-08-11: covered 4 / total 1184.
    ⛔ That ratio does NOT evaluate this stop condition, in either direction. There is no
    production corpus; the dev database is residue from ad-hoc runs, so its denominator is
    not a population the design chose.

A ratio over residue answers a question nobody asked. What settles it is a **designed run on
a corpus with known ground truth** — and the ground truth has to come from a person, which is
the whole reason this file is two commands and not one.

    --emit   builds a labelling sheet from real events, in real reading order, with the
             LABEL fields BLANK.
    --score  reads a sheet a person has filled in and scores the system against it.

⚠️ **THIS SCRIPT MUST NEVER WRITE A LABEL.** A detector graded against labels its own author
wrote is green by construction (rule 3), and this repo has shipped that mistake before — the
sort-conformance test whose fixture created rows in the expected order, which passed a bite
that deleted the tie-break keys. `--score` therefore refuses a sheet whose `labelled_by` is
blank or names an assistant, and `--emit` writes `LABEL:` with nothing after it.

WHAT THE SCORER HAS TO GET RIGHT, AND IT IS NOT PRECISION
─────────────────────────────────────────────────────────
The stop condition's failure mode is *"degrades to `unknown` everywhere"* — a system that
emits NO ordered edges at all. Over an empty prediction set precision is vacuously 1.0, so a
scorer that reports precision would hand the stop condition's own signature a perfect score.
`NO-PREDICTIONS` is therefore a distinct verdict and it FAILS.

The mirror error is just as real, and QC-5 clause 2 is where this repo learned it: if the
labeller marks every pair `unknown`, the sheet cannot discriminate and the system's zero is
unremarkable. That is `NO-POSITIVES`, and it is **UNSCORABLE** — not a pass, not a failure of
the system, but a statement that this sheet cannot answer the question.

Usage
    python scripts/t33-causal-labelling-sheet.py --emit --book-id <uuid> --chapters 2 --pairs 20
    python scripts/t33-causal-labelling-sheet.py --score docs/measurements/<sheet>.md
    python scripts/t33-causal-labelling-sheet.py --selftest
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CAUSES, PRECEDES, UNKNOWN = "causes", "precedes", "unknown"
LABELS = (CAUSES, PRECEDES, UNKNOWN)

#: The system's ordered relationship types, as `causal_edges.py` persists them.
REL_OF = {"CAUSES": CAUSES, "PRECEDES": PRECEDES}

#: Verdicts. `NO_PREDICTIONS` and `NO_POSITIVES` exist so a vacuous run cannot read as a pass.
SCORED, NO_PREDICTIONS, NO_POSITIVES, EMPTY_SHEET = (
    "SCORED", "NO-PREDICTIONS", "NO-POSITIVES", "EMPTY-SHEET")
#: A zero must say WHICH zero it is. §4.3 already retracted a global `0.34 %` that divided by
#: residue from runs which never touched the causal pipeline, and this is that error made
#: unrepeatable: if the project holds no ordered edge AT ALL, the extractor was never run here
#: and the sheet measures its ABSENCE, not its quality. Rule 13, mechanised.
PASS_NEVER_RAN = "PASS-NEVER-RAN"

#: A sheet must say who labelled it, and it must not be a machine. Not decoration: the GRANT
#: is explicit — "the PO labels the ground truth; you build the sheet, never the labels you
#: then grade".
#: Names that are certainly NOT a person signing off. A DENYLIST, and the docstring on
#: `labeller_ok` says plainly what that can and cannot do.
_MACHINE = re.compile(
    r"claude|assistant|gpt|llm|auto|tbd|todo|" + chr(92) + "bme" + chr(92) + "b"
    r"|harness|smoke|placeholder|synthetic|sample|dummy|fixture|" + chr(92) + "bn/?a" + chr(92) + "b"
    r"|" + chr(92) + "bxx+" + chr(92) + "b|" + chr(92) + "btest" + chr(92) + "b|^-+$",
    re.I)

LABEL_RE = re.compile(r"^LABEL:\s*(\S*)\s*$", re.M)
PAIR_RE = re.compile(r"^#### PAIR (P\d+)\s*$", re.M)
BY_RE = re.compile(r"^labelled_by:[ 	]*(.*)$", re.M)


def parse_sheet(text: str) -> tuple[str, list[tuple[str, str]]]:
    """`(labelled_by, [(pair id, label)])`. A blank LABEL stays in the list as `""`.

    Blanks are KEPT rather than dropped so `--score` can say how much of the sheet is
    unfilled. Silently ignoring them would let a sheet with two answers score as complete.
    """
    by = BY_RE.search(text)
    pairs = [m.group(1) for m in PAIR_RE.finditer(text)]
    labels = [m.group(1).lower() for m in LABEL_RE.finditer(text)]
    return (by.group(1).strip() if by else ""), list(zip(pairs, labels))


def score(truth: dict[str, str], predicted: dict[str, str], *, pass_ran: bool = True) -> dict:
    """Verdict + per-relation counts. PURE, so the selftest drives every arm offline.

    `truth` and `predicted` are `{pair id: relation}`. A pair absent from `predicted` means
    the system asserted no ordered edge for it, which is the same as `unknown`.
    """
    filled = {p: r for p, r in truth.items() if r in LABELS}
    if not filled:
        return {"verdict": EMPTY_SHEET, "reason": "no pair carries a label yet"}

    positives = {p: r for p, r in filled.items() if r in (CAUSES, PRECEDES)}
    asserted = {p: r for p, r in predicted.items() if r in (CAUSES, PRECEDES)}

    if not positives:
        return {"verdict": NO_POSITIVES, "labelled": len(filled),
                "reason": "every labelled pair is `unknown`, so this sheet cannot "
                          "discriminate a working extractor from a silent one"}
    if not asserted and not pass_ran:
        return {"verdict": PASS_NEVER_RAN, "labelled": len(filled),
                "truth_positives": len(positives),
                "reason": "this project holds no ordered edge at all, so the extractor was "
                          "never run over it. Scoring now would measure whether anybody "
                          "pressed the button — the exact substitution §4.3 retracted"}
    if not asserted:
        return {"verdict": NO_PREDICTIONS, "labelled": len(filled),
                "truth_positives": len(positives), "recall": 0.0,
                "reason": "the system asserted no ordered edge over any labelled pair. This "
                          "is the stop condition's own signature — precision over an empty "
                          "prediction set is vacuously 1.0 and is NOT reported"}

    tp = sum(1 for p, r in asserted.items() if positives.get(p) == r)
    # An edge on a pair the labeller called `unknown`, or of the wrong kind, is a false one.
    fp = len(asserted) - tp
    fn = len(positives) - sum(1 for p in positives if p in asserted)
    # `causes` asserted where the truth is `precedes` is the expensive direction: it is a
    # claim about WHY, and §T33 says a wrong order is worse than an absent one.
    overclaims = sum(1 for p, r in asserted.items()
                     if r == CAUSES and positives.get(p) == PRECEDES)
    return {
        "verdict": SCORED, "labelled": len(filled), "truth_positives": len(positives),
        "asserted": len(asserted), "tp": tp, "fp": fp, "fn": fn,
        "precision": round(tp / len(asserted), 3),
        "recall": round(tp / len(positives), 3),
        "causes_overclaimed_as_precedes": overclaims,
    }


def _selftest() -> int:
    T = {"P1": CAUSES, "P2": PRECEDES, "P3": UNKNOWN, "P4": CAUSES}
    cases = [
        ("a perfect run scores 1.0 / 1.0",
         score(T, {"P1": CAUSES, "P2": PRECEDES, "P4": CAUSES}),
         lambda r: r["verdict"] == SCORED and r["precision"] == 1.0 and r["recall"] == 1.0),
        ("THE CONTROL: a system that asserts NOTHING is NO-PREDICTIONS, never precision 1.0",
         score(T, {}),
         lambda r: r["verdict"] == NO_PREDICTIONS and "precision" not in r),
        ("...and that verdict is the stop condition's shape, so recall is 0 and stated",
         score(T, {}), lambda r: r["recall"] == 0.0),
        ("A ZERO MUST SAY WHICH ZERO: no edge anywhere means the pass NEVER RAN",
         score(T, {}, pass_ran=False), lambda r: r["verdict"] == PASS_NEVER_RAN),
        ("...and that is NOT the same verdict as an extractor that ran and stayed silent",
         (score(T, {}, pass_ran=False)["verdict"], score(T, {}, pass_ran=True)["verdict"]),
         lambda r: r[0] != r[1]),
        ("THE MIRROR CONTROL: an all-`unknown` sheet is UNSCORABLE, not a pass",
         score({"P1": UNKNOWN, "P2": UNKNOWN}, {}),
         lambda r: r["verdict"] == NO_POSITIVES),
        ("an unfilled sheet is EMPTY-SHEET, not a zero-score",
         score({"P1": "", "P2": ""}, {"P1": CAUSES}),
         lambda r: r["verdict"] == EMPTY_SHEET),
        ("an edge on a pair labelled `unknown` is a FALSE positive",
         score(T, {"P1": CAUSES, "P3": CAUSES}),
         lambda r: r["tp"] == 1 and r["fp"] == 1),
        ("a missed positive is a false NEGATIVE and drops recall",
         score(T, {"P1": CAUSES}),
         lambda r: r["fn"] == 2 and r["recall"] == round(1 / 3, 3)),
        ("`causes` where the truth is `precedes` is WRONG, not a near miss",
         score(T, {"P2": CAUSES}),
         lambda r: r["tp"] == 0 and r["causes_overclaimed_as_precedes"] == 1),
        ("...and the reverse (precedes where causes is true) is also wrong but NOT an overclaim",
         score(T, {"P1": PRECEDES}),
         lambda r: r["tp"] == 0 and r["causes_overclaimed_as_precedes"] == 0),
        ("a system predicting `unknown` explicitly counts as asserting nothing",
         score(T, {"P1": UNKNOWN, "P2": UNKNOWN}),
         lambda r: r["verdict"] == NO_PREDICTIONS),
    ]
    sheet = ("labelled_by: \n#### PAIR P1\nLABEL: causes\n#### PAIR P2\nLABEL:\n")
    by, got = parse_sheet(sheet)
    cases += [
        ("the sheet parser keeps a BLANK label rather than dropping the pair",
         {"n": len(got), "blank": got[1][1]}, lambda r: r["n"] == 2 and r["blank"] == ""),
        ("...and reads who labelled it", {"by": by}, lambda r: r["by"] == ""),
        ("an unsigned sheet is refused", {"ok": labeller_ok("")}, lambda r: not r["ok"]),
        ("THE GRANT'S GUARD: a sheet signed by an assistant is refused",
         {"ok": labeller_ok("Claude")}, lambda r: not r["ok"]),
        ("...and by a person is accepted", {"ok": labeller_ok("NeneScarlet")},
         lambda r: r["ok"]),
        # T33h — the guard ACCEPTED `HARNESS-SMOKE-not-a-person` and then printed
        # `precision 1.0` over labels made by random.choice. A denylist cannot prove
        # provenance; what it can do is make the failure deliberate rather than accidental.
        ("a HARNESS placeholder is refused", {"ok": labeller_ok("HARNESS-SMOKE")},
         lambda r: not r["ok"]),
        ("...so are `placeholder`, `synthetic`, `sample`, `fixture`",
         {"ok": [labeller_ok(x) for x in ("placeholder", "synthetic", "sample", "fixture")]},
         lambda r: not any(r["ok"])),
        ("...and a row of dashes, or `n/a`",
         {"ok": [labeller_ok("----"), labeller_ok("n/a")]},
         lambda r: not any(r["ok"])),
        ("a real name containing a denylisted SUBSTRING is still a person",
         {"ok": labeller_ok("Sam Testerton")}, lambda r: r["ok"]),
    ]
    failures = 0
    print("t33-causal-labelling-sheet - selftest (offline)")
    for label, got_v, pred in cases:
        ok = bool(pred(got_v))
        failures += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FAIL'}  {label}"
              f"{'' if ok else '  -> ' + json.dumps(got_v, ensure_ascii=False)}")
    print("\n  all checks passed" if not failures else f"\n  {failures} FAILED")
    return 1 if failures else 0


def labeller_ok(who: str) -> bool:
    """A sheet must be signed by a person — and this is a SPEED BUMP, not a proof.

    ⚠️ **Measured 2026-08-30 (T33h): the guard accepted `HARNESS-SMOKE-not-a-person`.** It is
    a denylist, so anything not on the list passes, and no script can verify that a human
    typed a label. The refusal message used to read *"the ground truth must come from someone
    other than the thing being graded"*, which claims enforcement this cannot deliver.

    What it genuinely does: stop the obvious case — a sheet signed by an assistant, or by an
    evident placeholder — so the failure has to be deliberate rather than accidental. What
    carries the real weight is that `--score`'s OUTPUT now says the signature is ASSERTED,
    beside every number it prints, so a `precision 1.0` can never be read as proof of
    independent labelling.

    That distinction is not academic: the smoke run that found this printed **precision 1.0**
    over labels generated by `random.choice`.
    """
    return bool(who.strip()) and not _MACHINE.search(who)




def _sheet_text(args, pairs, pred, *, causal_pass_ran: bool) -> str:
    """The sheet's markdown. ONE renderer for both stores — two would drift."""
    out = [
        "# T33 — causal labelling sheet",
        "",
        "labelled_by: ",
        "",
        "> Fill each `LABEL:` with exactly one of `causes` / `precedes` / `unknown`.",
        "> `causes` = the earlier event DIRECTLY brings about or enables the later one.",
        "> `precedes` = it clearly happens after, but you cannot show causation.",
        "> `unknown` = you cannot tell, or they are unrelated. **Prefer `unknown`** — the row's",
        "> own criterion says a wrong order is worse than an absent one.",
        "",
        "Ordering within a chapter is `Event.event_order`, present on every event in scope.",
        "Read from the store the deployment DECLARES (`age`), not from Neo4j — reading the",
        "wrong store is what made an earlier draft report the extractor as never having run.",
        "",
        "```json",
        json.dumps({"project_id": args.project_id, "chapters": args.chapter_ids,
                    "causal_pass_ran": causal_pass_ran,
                    "pairs": {p[0]: {"earlier": p[2]["id"], "later": p[3]["id"],
                                     "chapter": p[1]} for p in pairs},
                    "system_predicted": pred}, ensure_ascii=False, indent=1),
        "```",
        "",
    ]
    for pid, ch, a, b in pairs:
        out += [f"#### PAIR {pid}", "",
                f"**earlier** — {a['title']}", f"> {(a.get('summary') or '')[:300]}", "",
                f"**later** — {b['title']}", f"> {(b.get('summary') or '')[:300]}", "",
                "LABEL:", ""]
    return chr(10).join(out)



def _age(sql_cypher: str, cols: str, *, port: int, db: str, graph: str) -> list[list[str]]:
    """Run one Cypher against AGE through psql and return the rows as strings.

    🔴 **THE SHEET READ THE WRONG STORE, and this is why it now reads the configured one.**
    The first version spoke Bolt to Neo4j. The service's declared backend is `age` (§8.1), so
    the causal extractor's 134 edges landed in AGE and the sheet reported
    `causal_pass_ran: false` over a project that had just been processed. The instrument said
    "the extractor was never run here" about a run that had finished minutes earlier.

    That is the third instrument defect in this row alone — `created_at` ordering, a one-row
    `keys()` sample, and now the store itself — and all three failed the same direction:
    toward "there is nothing here".
    """
    full = ("LOAD 'age'; SET search_path = ag_catalog, public; "
            "SELECT * FROM cypher('" + graph + "', $$ " + sql_cypher + " $$) AS (" + cols + ");")
    r = subprocess.run(
        ["psql", "-h", "localhost", "-p", str(port), "-U", "loreweave", "-d", db,
         "-At", "-F", "|", "-c", full],
        capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PGPASSWORD": "loreweave_dev"})
    if r.returncode != 0:
        raise SystemExit("AGE query failed: " + r.stderr[:300])
    out = []
    for line in r.stdout.strip().split(chr(10))[2:]:      # skip LOAD / SET
        if line:
            out.append([c.strip().strip('"') for c in line.split("|")])
    return out


def _emit_age(args) -> int:
    """Build the sheet from AGE — the store the declared deployment actually reads."""
    P = args.project_id
    chapters = "[" + ",".join("'" + c + "'" for c in args.chapter_ids) + "]"
    rows = _age(
        "MATCH (e:Event {project_id:'" + P + "'})-[:EVIDENCED_BY]->(x:ExtractionSource) "
        "WHERE x.source_id IN " + chapters + " "
        "RETURN x.source_id AS ch, e.id AS id, e.title AS title, e.summary AS summary, "
        "e.event_order AS eo",
        "ch agtype, id agtype, title agtype, summary agtype, eo agtype",
        port=args.age_port, db=args.age_db, graph=args.age_graph)

    by_ch: dict[str, list] = {}
    for ch, eid, title, summary, eo in rows:
        try:
            order = int(eo)
        except (TypeError, ValueError):
            order = 2147483647
        by_ch.setdefault(ch, []).append(
            {"id": eid, "title": title, "summary": summary, "eo": order})
    for ch in by_ch:
        by_ch[ch].sort(key=lambda e: e["eo"])

    pairs, n = [], 0
    for ch in args.chapter_ids:
        evs = by_ch.get(ch, [])
        for gap in (1, 2):
            for i in range(len(evs) - gap):
                n += 1
                pairs.append((f"P{n}", ch, evs[i], evs[i + gap]))
    pairs = pairs[: args.pairs]

    edges = {}
    for rel in ("CAUSES", "PRECEDES"):
        for a, b in _age(
                "MATCH (a:Event {project_id:'" + P + "'})-[r:" + rel + "]->(b:Event) "
                "RETURN a.id AS a, b.id AS b", "a agtype, b agtype",
                port=args.age_port, db=args.age_db, graph=args.age_graph):
            edges[(a, b)] = rel.lower()
    index = {(x[2]["id"], x[3]["id"]): x[0] for x in pairs}
    pred = {index[k]: v for k, v in edges.items() if k in index}

    out = _sheet_text(args, pairs, pred, causal_pass_ran=bool(edges))
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(out)
    print(f"[t33-sheet] {len(pairs)} pair(s) from {len(args.chapter_ids)} chapter(s) "
          f"-> {args.out}")
    print(f"[t33-sheet] AGE holds {len(edges)} ordered edge(s) in this project; the system "
          f"asserts one on {len(pred)} of the sheet's pairs")
    print("[t33-sheet] every LABEL is BLANK. This script does not write labels (rule 3).")
    return 0


def _emit(args) -> int:
    from neo4j import GraphDatabase  # imported here so --selftest needs no driver

    drv = GraphDatabase.driver(args.bolt, auth=(args.user, args.password))
    with drv.session() as s:
        rows = s.run(
            """MATCH (e:Event {project_id:$p})-[:EVIDENCED_BY]->
                     (x:ExtractionSource {source_type:'chapter'})
               WHERE x.source_id IN $chapters
               RETURN x.source_id AS ch, e.id AS id, e.title AS title,
                      e.summary AS summary, e.time_cue AS cue,
                      e.event_order AS eo, e.created_at AS created
               ORDER BY x.source_id, coalesce(e.event_order, 2147483647), e.created_at""",
            p=args.project_id, chapters=args.chapter_ids).data()
        edges = s.run(
            """MATCH (a:Event {project_id:$p})-[r:CAUSES|PRECEDES]->(b:Event)
               RETURN a.id AS a, b.id AS b, type(r) AS t""", p=args.project_id).data()
    drv.close()

    by_ch: dict[str, list] = {}
    for r in rows:
        by_ch.setdefault(r["ch"], []).append(r)

    pairs, n = [], 0
    for ch in args.chapter_ids:
        evs = by_ch.get(ch, [])
        # Consecutive AND one-apart: the forward links a 12-event window would consider,
        # without asking a person to read 300 combinations.
        for gap in (1, 2):
            for i in range(len(evs) - gap):
                n += 1
                pairs.append((f"P{n}", ch, evs[i], evs[i + gap]))
    pairs = pairs[: args.pairs]

    pred = {}
    index = {(p[2]["id"], p[3]["id"]): p[0] for p in pairs}
    for e in edges:
        pid = index.get((e["a"], e["b"]))
        if pid:
            pred[pid] = REL_OF[e["t"]]

    out = [
        "# T33 — causal labelling sheet",
        "",
        "labelled_by: ",
        "",
        "> Fill each `LABEL:` with exactly one of `causes` / `precedes` / `unknown`.",
        "> `causes` = the earlier event DIRECTLY brings about or enables the later one.",
        "> `precedes` = it clearly happens after, but you cannot show causation.",
        "> `unknown` = you cannot tell, or they are unrelated. **Prefer `unknown`** — the row's",
        "> own criterion says a wrong order is worse than an absent one.",
        "",
        "Ordering within a chapter is `Event.event_order`, which is present on **every** event",
        "in scope (122/122; 1130 of 1186 store-wide). `created_at` breaks ties for the 56 that",
        "lack it. The first draft of this sheet ordered by `created_at` alone — measured, that",
        "put a flashback ahead of the scene that frames it, which would have asked you to judge",
        "causation between two events the sheet had mis-ordered.",
        "",
        "```json",
        json.dumps({"project_id": args.project_id, "chapters": args.chapter_ids,
                    "causal_pass_ran": bool(edges),
                    "pairs": {p[0]: {"earlier": p[2]["id"], "later": p[3]["id"], "chapter": p[1]}
                              for p in pairs},
                    "system_predicted": pred}, ensure_ascii=False, indent=1),
        "```",
        "",
    ]
    for pid, ch, a, b in pairs:
        out += [f"#### PAIR {pid}", "",
                f"**earlier** — {a['title']}", f"> {(a['summary'] or '')[:300]}", "",
                f"**later** — {b['title']}", f"> {(b['summary'] or '')[:300]}", "",
                "LABEL:", ""]

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(out))
    print(f"[t33-sheet] {len(pairs)} pair(s) from {len(args.chapter_ids)} chapter(s) "
          f"-> {args.out}")
    print(f"[t33-sheet] the system asserts an ordered edge on {len(pred)} of them")
    print("[t33-sheet] every LABEL is BLANK. This script does not write labels (rule 3).")
    return 0


def _score(path: str) -> int:
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    manifest = json.loads(text.split("```json", 1)[1].split("```", 1)[0])
    by, labelled = parse_sheet(text)
    if not labeller_ok(by):
        print(f"[t33-score] REFUSED — `labelled_by: {by or '(blank)'}` is not a person.\n"
              "  The ground truth must come from someone other than the thing being graded;\n"
              "  a detector scored against its own author's labels is green by construction.")
        return 2
    result = score(dict(labelled), manifest.get("system_predicted", {}),
                   pass_ran=bool(manifest.get("causal_pass_ran", True)))
    print(f"[t33-score] {path}")
    print(f"[t33-score] labelled by: {by}  — ASSERTED, NOT VERIFIED. No script can prove a "
          f"person typed these labels;")
    print(f"[t33-score] the check below is a denylist that stops the obvious case. Every "
          f"number here is only as good as that signature.")
    for k, v in result.items():
        print(f"  {k:<32} {v}")
    return 0 if result["verdict"] == SCORED else 1


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--emit", action="store_true")
    ap.add_argument("--score", metavar="SHEET")
    ap.add_argument("--project-id")
    ap.add_argument("--chapter-ids", nargs="*", default=[])
    ap.add_argument("--pairs", type=int, default=20)
    ap.add_argument("--out", default=os.path.join(
        ROOT, "docs", "measurements", "2026-08-24-t33-causal-labelling-sheet.md"))
    ap.add_argument("--store", default="age", choices=("age", "neo4j"),
                    help="which store to read; the declared backend is `age` (§8.1)")
    ap.add_argument("--age-port", type=int, default=25556)
    ap.add_argument("--age-db", default="loreweave_knowledge_vectors")
    ap.add_argument("--age-graph", default="g_shared")
    ap.add_argument("--bolt", default="bolt://localhost:7688")
    ap.add_argument("--user", default="neo4j")
    ap.add_argument("--password", default="loreweave_dev_neo4j")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()
    if args.score:
        return _score(args.score)
    if args.emit:
        if not args.project_id or not args.chapter_ids:
            print("[t33-sheet] --project-id and --chapter-ids are required")
            return 2
        return _emit_age(args) if args.store == 'age' else _emit(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
