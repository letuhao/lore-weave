"""A-EVAL — longer-form Phase-A validation (replaces the saturated coherence-median).

Tests the actual thesis ("orchestrated reasoning beats V0") on LONGER-FORM output
with a DISCRIMINATING metric: per premise, build a full multi-scene book draft two
ways and have a disjoint judge pick the better + count defects.

  A3-full arm : decompose → commit → generate each planned scene (auto = adaptive-K
                diverge→converge + canon-reflect) → concat per chapter.
  V0 arm      : the bare V0 loop — one single-draft (cowrite, K=1, no plan/rerank/
                reflect) per chapter from a thin synopsis → concat.

The A3-rich-plan vs V0-thin asymmetry IS the thesis under test. Length is roughly
controlled (V0 max_output sized to the chapter's A3 scene count). Judge = pairwise
A/B over the two full books via POST /internal/composition/eval/pairwise-judge
(the critic model, disjoint from the drafter); blind "Draft 1/2" with order SWAPPED
by premise parity to cancel position bias. Gate: A3 wins > losses.

⚠ Honest limits: small n (LLM wall-clock ~20-30 min/run); A3 produces more, shorter,
plan-grounded scenes vs V0's fewer, longer chapter drafts — the judge compares
overall coherence/consistency, not length. Rebuild + recreate composition first.

Usage: python eval_a_validate.py [n_premises]
"""
import base64
import json
import statistics
import sys
import time
import urllib.request

GW = "http://localhost:3123"
COMP_INTERNAL = "http://localhost:8217"   # composition :8093 (internal pairwise-judge)
GLOSSARY_INTERNAL = "http://localhost:8211"
INTERNAL_TOKEN = "dev_internal_token"

PREMISES = [
    ("A disgraced knight retakes a fallen border keep before the winter siege.",
     ["Kael", "Bryn", "Mira"]),
    ("A market thief uncovers a conspiracy and must choose a side before the festival.",
     ["Sora", "Den", "Lia"]),
    ("Two estranged siblings inherit a haunted observatory and a dangerous ledger.",
     ["Aron", "Vesa", "Tomas"]),
]


def _req(method, path, token=None, body=None, stream=False, timeout=600):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(GW + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    resp = urllib.request.urlopen(req, timeout=timeout)
    if stream:
        return resp
    raw = resp.read().decode().strip()
    return json.loads(raw) if raw else {}


def _internal(method, base, path, body, timeout=300):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Internal-Token", INTERNAL_TOKEN)
    resp = urllib.request.urlopen(req, timeout=timeout)
    raw = resp.read().decode().strip()
    return json.loads(raw) if raw else {}


def login():
    return _req("POST", "/v1/auth/login", body={"email": "claude-test@loreweave.dev",
                                                "password": "Claude@Test2026"})["access_token"]


def jwt_sub(token):
    p = token.split(".")[1]; p += "=" * (-len(p) % 4)
    return json.loads(base64.urlsafe_b64decode(p))["sub"]


def models(token):
    chat = [m for m in _req("GET", "/v1/model-registry/user-models?capability=chat",
                            token)["items"] if m["is_active"]]
    allm = [m for m in _req("GET", "/v1/model-registry/user-models?include_inactive=true",
                            token)["items"] if m["is_active"]]
    drafter = next((m for m in chat if "qwen3.6-35b" in m["provider_model_name"]), chat[0])
    critic = next(m for m in allm if m["user_model_id"] != drafter["user_model_id"])
    return drafter["user_model_id"], critic["user_model_id"]


def gen_auto_text(token, proj, node_id, drafter, guide=""):
    r = _req("POST", f"/v1/composition/works/{proj}/generate", token,
             {"outline_node_id": node_id, "model_source": "user_model", "model_ref": drafter,
              "operation": "draft_scene", "mode": "auto", "reasoning": "off",
              "guide": guide, "max_output_tokens": 400})
    return r.get("text", ""), r.get("k")


def cowrite_text(token, proj, node_id, drafter, max_tokens):
    """V0 single draft — drain the cowrite SSE, accumulate token deltas."""
    resp = _req("POST", f"/v1/composition/works/{proj}/generate", token,
                {"outline_node_id": node_id, "model_source": "user_model", "model_ref": drafter,
                 "operation": "draft_scene", "mode": "cowrite", "reasoning": "off",
                 "max_output_tokens": max_tokens}, stream=True)
    parts = []
    for raw in resp:
        line = raw.decode().strip()
        if line.startswith("data:"):
            ev = json.loads(line[5:])
            if ev.get("type") == "token":
                parts.append(ev.get("delta", ""))
            if ev.get("type") == "done":
                break
    return "".join(parts)


def build_one(token, user_id, drafter, critic, premise, cast):
    book = _req("POST", "/v1/books", token,
                {"title": f"A-EVAL {int(time.time()*1000) % 100000}", "original_language": "en"})["book_id"]
    chapters = [_req("POST", f"/v1/books/{book}/chapters", token,
                     {"original_language": "en", "title": f"Chapter {i}"})["chapter_id"]
                for i in range(1, 4)]
    proj = _req("POST", f"/v1/composition/books/{book}/work", token)["project_id"]
    _req("PATCH", f"/v1/composition/works/{proj}", token,
         {"settings": {"critic_model_source": "user_model", "critic_model_ref": critic}})
    for name in cast:
        _internal("POST", GLOSSARY_INTERNAL, f"/internal/books/{book}/extract-entities",
                  {"source_language": "en", "entities": [{"kind_code": "character", "name": name,
                                                          "attributes": {}, "evidence": f"{name} appears."}]})
    tmpls = _req("GET", "/v1/composition/templates", token)["templates"]
    generic = next((t for t in tmpls if t["kind"] == "generic"), tmpls[0])

    # A3-full: decompose → commit → generate each scene → concat per chapter.
    preview = _req("POST", f"/v1/composition/works/{proj}/outline/decompose", token,
                   {"structure_template_id": generic["id"], "premise": premise,
                    "model_source": "user_model", "model_ref": drafter})
    commit_body = {"arc_title": generic["name"], "chapters": [{
        "chapter_id": c["chapter"]["chapter_id"], "title": c["chapter"]["title"],
        "intent": c["chapter"]["intent"], "beat_role": c["chapter"]["beat_role"],
        "scenes": [{"title": s["title"], "synopsis": s["synopsis"], "tension": s["tension"],
                    "present_entity_ids": s["present_entity_ids"]} for s in c["scenes"]],
    } for c in preview["chapters"]]}
    _req("POST", f"/v1/composition/works/{proj}/outline/decompose/commit", token, commit_body)
    tree = _req("GET", f"/v1/composition/works/{proj}/outline", token)
    scenes = [n for n in tree["nodes"] if n["kind"] == "scene" and n.get("beat_role")]
    scenes.sort(key=lambda x: (str(x.get("chapter_id")), x.get("rank") or ""))
    # scene count per chapter — V0 gets one chapter-draft sized to match.
    per_chapter = {}
    for n in scenes:
        per_chapter.setdefault(str(n["chapter_id"]), []).append(n)
    # B (state-reinjection probe): thread the chapter's PRIOR generated scenes into
    # each scene's `guide` so A3 isn't drafted blind to its predecessors (the
    # A-EVAL finding). Cheap simulation of Re3-F2 / the narrative_thread ledger.
    a3_parts, a3_k = [], []
    chapter_running: dict[str, list[str]] = {}
    for n in scenes:
        cid = str(n["chapter_id"])
        prior = chapter_running.get(cid, [])
        guide = ("Continue this chapter coherently and consistently with what came "
                 "before. PREVIOUSLY IN THIS CHAPTER:\n\n" + "\n\n".join(prior)) if prior else ""
        txt, k = gen_auto_text(token, proj, n["id"], drafter, guide=guide)
        a3_parts.append(txt); a3_k.append(k or 0)
        chapter_running.setdefault(cid, []).append(txt)
    a3_draft = "\n\n".join(p for p in a3_parts if p)

    # V0: one bare single-draft per chapter (thin synopsis, no plan), sized to the
    # chapter's A3 scene count so total length is comparable.
    v0_parts, v0_k = [], []
    for i, ch in enumerate(chapters):
        n_sc = len(per_chapter.get(str(ch), [])) or 1
        sid = _req("POST", f"/v1/composition/works/{proj}/outline/nodes", token,
                   {"kind": "scene", "chapter_id": ch, "title": f"bare ch{i+1}",
                    "synopsis": f"{premise} (chapter {i+1})"})["id"]
        txt = cowrite_text(token, proj, sid, drafter, max_tokens=min(1200, 400 * n_sc))
        v0_parts.append(txt); v0_k.append(1)
    v0_draft = "\n\n".join(p for p in v0_parts if p)
    return book, a3_draft, v0_draft, a3_k, v0_k


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    n = max(1, min(n, len(PREMISES)))
    token = login()
    user_id = jwt_sub(token)
    drafter, critic = models(token)
    print(f"user={user_id} drafter={drafter} critic={critic} n={n}\n")

    a3_wins = v0_wins = ties = 0
    a3_def_tot = v0_def_tot = 0
    books = []
    for i, (premise, cast) in enumerate(PREMISES[:n]):
        t0 = time.time()
        book, a3, v0, a3k, v0k = build_one(token, user_id, drafter, critic, premise, cast)
        books.append(book)
        if not a3.strip() or not v0.strip():
            print(f"  P{i}: SKIP — empty draft (a3={len(a3)} v0={len(v0)} chars)")
            continue
        # order swap by parity (cancel position bias); map verdict back to the arm.
        swap = (i % 2 == 1)
        da, db = (v0, a3) if swap else (a3, v0)
        verdict = _internal("POST", COMP_INTERNAL, "/internal/composition/eval/pairwise-judge",
                            {"user_id": user_id, "model_source": "user_model", "model_ref": critic,
                             "draft_a": da, "draft_b": db})
        better = verdict.get("better", "tie")
        a3_label = "2" if swap else "1"
        v0_label = "1" if swap else "2"
        d_a3 = verdict.get(f"defects_{a3_label}", {})
        d_v0 = verdict.get(f"defects_{v0_label}", {})
        a3_def = sum(v for v in d_a3.values() if isinstance(v, int))
        v0_def = sum(v for v in d_v0.values() if isinstance(v, int))
        a3_def_tot += a3_def; v0_def_tot += v0_def
        if better == a3_label:
            a3_wins += 1; who = "A3"
        elif better == v0_label:
            v0_wins += 1; who = "V0"
        else:
            ties += 1; who = "tie"
        print(f"  P{i}: winner={who} | A3 K={a3k} ({len(a3)} chars, {a3_def} defects) "
              f"vs V0 K={v0k} ({len(v0)} chars, {v0_def} defects) | {time.time()-t0:.0f}s")
        if verdict.get("why"):
            print(f"       why: {verdict['why'][:160]}")

    print("\n=== RESULT ===")
    print(f"pairwise wins — A3:{a3_wins}  V0:{v0_wins}  tie:{ties}  (n={n})")
    print(f"total defects — A3:{a3_def_tot}  V0:{v0_def_tot}")
    print("\nLIVE-SMOKE: longer-form A3-THREADED (guide state-reinjection) vs V0 pairwise judge "
          "ran end-to-end (decompose→commit→multi-scene generate + cowrite baseline + pairwise-judge).")
    if a3_wins > v0_wins:
        print(f"GATE: PASS — A3 wins {a3_wins} > V0 {v0_wins} (orchestrated reasoning beats V0 "
              "on longer-form pairwise — the discriminating signal the coherence-median lacked).")
    elif a3_wins == v0_wins:
        print(f"GATE: TIE ({a3_wins}={v0_wins}) — no clear win on this small n; "
              f"defect-count tiebreak A3:{a3_def_tot} vs V0:{v0_def_tot}. Increase n or rethink before Phase B.")
    else:
        print(f"GATE: FAIL — V0 wins {v0_wins} > A3 {a3_wins}. The core does NOT beat V0 on our "
              "models — STOP and rethink before Phase B (the validate-first gate fired).")

    for b in books:
        try:
            _req("DELETE", f"/v1/books/{b}", token)
        except Exception as exc:  # noqa
            print(f"(cleanup failed {b}: {exc})")


if __name__ == "__main__":
    main()
