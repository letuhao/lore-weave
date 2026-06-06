"""A-EVAL (C) — FAIR plan-value eval: planned vs unplanned SINGLE-PASS chapters.

A-EVAL + (B) found A3-concat loses V0 partly because of SCENE-GRANULARITY (9
stitched scene-drafts vs 3 single-pass chapter-drafts), which confounds the
decompose PLAN's value with fragmentation. This isolates the plan: BOTH arms
generate ONE single-pass cowrite draft per chapter (equal granularity); they
differ ONLY in the scene-node synopsis —

  A3-planned : synopsis = the decompose chapter intent + its scene beats (a
               detailed outline — the DOC/F5 "push complexity upstream" lever).
  V0         : synopsis = the bare premise (no plan).

Pairwise-judged (critic, disjoint) over the two full books; order swapped by
premise parity. If A3-planned beats V0, the PLAN's value is real and the
long-form-assembly problem (granularity + state-reinjection, D-COMP-LONGFORM-
STATE-REINJECTION) is SEPARATE. If not, the decompose plan doesn't help even at
fair granularity → rethink decompose.

Reuses eval_a_validate's helpers + the internal pairwise-judge endpoint. Eval-only.
Usage: python eval_a_fair.py [n_premises]
"""
import statistics
import sys
import time

sys.path.insert(0, "D:/Works/source/lore-weave/services/composition-service/scripts")
import eval_a_validate as E  # noqa: E402


def _a3_synopsis(chapter_preview):
    """A detailed single-pass outline for the chapter: its intent + scene beats."""
    intent = (chapter_preview["chapter"]["intent"] or chapter_preview["chapter"]["title"]).strip()
    beats = "\n".join(f"- {s['synopsis']}" for s in chapter_preview["scenes"] if s.get("synopsis"))
    return f"{intent}\n\nBeats to cover, in order:\n{beats}" if beats else intent


def build_fair(token, user_id, drafter, critic, premise, cast):
    book = E._req("POST", "/v1/books", token,
                  {"title": f"A-FAIR {int(time.time()*1000) % 100000}", "original_language": "en"})["book_id"]
    chapters = [E._req("POST", f"/v1/books/{book}/chapters", token,
                       {"original_language": "en", "title": f"Chapter {i}"})["chapter_id"]
                for i in range(1, 4)]
    proj = E._req("POST", f"/v1/composition/books/{book}/work", token)["project_id"]
    E._req("PATCH", f"/v1/composition/works/{proj}", token,
           {"settings": {"critic_model_source": "user_model", "critic_model_ref": critic}})
    for name in cast:
        E._internal("POST", E.GLOSSARY_INTERNAL, f"/internal/books/{book}/extract-entities",
                    {"source_language": "en", "entities": [{"kind_code": "character", "name": name,
                                                           "attributes": {}, "evidence": f"{name} appears."}]})
    tmpls = E._req("GET", "/v1/composition/templates", token)["templates"]
    generic = next((t for t in tmpls if t["kind"] == "generic"), tmpls[0])
    preview = E._req("POST", f"/v1/composition/works/{proj}/outline/decompose", token,
                     {"structure_template_id": generic["id"], "premise": premise,
                      "model_source": "user_model", "model_ref": drafter})

    # Both arms: ONE single-pass cowrite draft per chapter (equal granularity).
    MAX = 1100
    a3_parts, v0_parts = [], []
    for i, (ch_id, cprev) in enumerate(zip(chapters, preview["chapters"])):
        a3_node = E._req("POST", f"/v1/composition/works/{proj}/outline/nodes", token,
                         {"kind": "scene", "chapter_id": ch_id, "title": f"A3 ch{i+1}",
                          "synopsis": _a3_synopsis(cprev)})["id"]
        a3_parts.append(E.cowrite_text(token, proj, a3_node, drafter, max_tokens=MAX))
        v0_node = E._req("POST", f"/v1/composition/works/{proj}/outline/nodes", token,
                         {"kind": "scene", "chapter_id": ch_id, "title": f"V0 ch{i+1}",
                          "synopsis": f"{premise} (chapter {i+1})"})["id"]
        v0_parts.append(E.cowrite_text(token, proj, v0_node, drafter, max_tokens=MAX))
    return book, "\n\n".join(p for p in a3_parts if p), "\n\n".join(p for p in v0_parts if p)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    n = max(1, min(n, len(E.PREMISES)))
    token = E.login()
    user_id = E.jwt_sub(token)
    drafter, critic = E.models(token)
    print(f"user={user_id} drafter={drafter} critic={critic} n={n}\n")

    a3_wins = v0_wins = ties = 0
    a3_def = v0_def = 0
    books = []
    for i, (premise, cast) in enumerate(E.PREMISES[:n]):
        t0 = time.time()
        book, a3, v0 = build_fair(token, user_id, drafter, critic, premise, cast)
        books.append(book)
        if not a3.strip() or not v0.strip():
            print(f"  P{i}: SKIP empty (a3={len(a3)} v0={len(v0)})"); continue
        swap = (i % 2 == 1)
        da, db = (v0, a3) if swap else (a3, v0)
        verdict = E._internal("POST", E.COMP_INTERNAL, "/internal/composition/eval/pairwise-judge",
                             {"user_id": user_id, "model_source": "user_model", "model_ref": critic,
                              "draft_a": da, "draft_b": db})
        a3_lbl, v0_lbl = ("2", "1") if swap else ("1", "2")
        better = verdict.get("better", "tie")
        a3_def += sum(v for v in verdict.get(f"defects_{a3_lbl}", {}).values() if isinstance(v, int))
        v0_def += sum(v for v in verdict.get(f"defects_{v0_lbl}", {}).values() if isinstance(v, int))
        who = "A3-planned" if better == a3_lbl else ("V0" if better == v0_lbl else "tie")
        a3_wins += better == a3_lbl; v0_wins += better == v0_lbl; ties += better == "tie"
        print(f"  P{i}: winner={who} | A3-planned {len(a3)} chars vs V0 {len(v0)} chars | {time.time()-t0:.0f}s")
        if verdict.get("why"):
            print(f"       why: {verdict['why'][:170]}")

    print("\n=== RESULT (FAIR — equal single-pass granularity, plan vs no-plan) ===")
    print(f"pairwise wins — A3-planned:{a3_wins}  V0:{v0_wins}  tie:{ties}  (n={n})")
    print(f"total defects — A3-planned:{a3_def}  V0:{v0_def}")
    print("\nLIVE-SMOKE: fair plan-isolation eval ran end-to-end (decompose plan → single-pass "
          "cowrite per chapter, both arms + pairwise-judge).")
    if a3_wins > v0_wins:
        print(f"GATE: PASS — A3-planned {a3_wins} > V0 {v0_wins}. The decompose PLAN lifts a "
              "single-pass chapter (DOC/F5 holds at fair granularity); the long-form-assembly gap "
              "(granularity + state-reinjection) is SEPARATE → D-COMP-LONGFORM-STATE-REINJECTION.")
    elif a3_wins == v0_wins:
        print(f"GATE: TIE ({a3_wins}={v0_wins}). Plan-value inconclusive at this n; defect tiebreak "
              f"A3:{a3_def} vs V0:{v0_def}. Increase n.")
    else:
        print(f"GATE: FAIL — V0 {v0_wins} > A3-planned {a3_wins}. The decompose plan does NOT help "
              "even at fair single-pass granularity → rethink the decompose plan's content/utility.")

    for b in books:
        try:
            E._req("DELETE", f"/v1/books/{b}", token)
        except Exception as exc:  # noqa
            print(f"(cleanup failed {b}: {exc})")


if __name__ == "__main__":
    main()
