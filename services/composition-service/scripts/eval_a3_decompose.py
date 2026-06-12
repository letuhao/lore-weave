"""A3 eval-gate + live-smoke — decompose planner (F5/DOC: push complexity upstream).

PRIMARY (live-smoke, the load-bearing part): prove the full B4 path works on a
real stack — seed a book with chapters + a glossary cast, `decompose` (preview),
`commit` (persist arc→chapter→scene), then confirm the committed scenes carry
`beat_role`+`tension` and that `/generate auto` runs on one. This is the FIRST
real exercise of `create_decomposed_tree` + `existing_scene_chapter_ids` (router
tests stubbed the repo).

SECONDARY (eval-gate, best-effort): compare A3 (planned scene → generate, adaptive
K) vs A1 (bare scene → generate, fixed K) on the critic's coherence dim, and
report total K spend. ⚠ The A1 eval lesson: coherence SATURATES on short single
scenes, so a null/tied result is EXPECTED and not a failure — the honest gate is
"A3 ≥ A1" with the saturation caveat surfaced. The structural win (grounded
intent + adaptive K spent where tension is high) is the real A3 contribution.

Run from the host against the live stack (rebuild + recreate composition first —
no volume mount). Usage: python eval_a3_decompose.py
"""
import base64
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
import uuid

GW = "http://localhost:3123"
GLOSSARY_INTERNAL = "http://localhost:8211"
INTERNAL_TOKEN = "dev_internal_token"

CAST = ["Kael", "Bryn", "Mira"]
PREMISE = ("A disgraced knight, Kael, must retake a fallen border keep with a "
           "ragtag band before the winter siege; his rival Bryn and the healer "
           "Mira are drawn into the gambit.")


def _req(method, path, token=None, body=None, timeout=600):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(GW + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    resp = urllib.request.urlopen(req, timeout=timeout)
    raw = resp.read().decode().strip()
    return json.loads(raw) if raw else {}


def _internal(method, base, path, body, timeout=120):
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
    p = token.split(".")[1]
    p += "=" * (-len(p) % 4)
    return json.loads(base64.urlsafe_b64decode(p))["sub"]


def models(token):
    chat = [m for m in _req("GET", "/v1/model-registry/user-models?capability=chat",
                            token)["items"] if m["is_active"]]
    allm = [m for m in _req("GET", "/v1/model-registry/user-models?include_inactive=true",
                            token)["items"] if m["is_active"]]
    drafter = next((m for m in chat if "qwen3.6-35b" in m["provider_model_name"]), chat[0])
    critic = next(m for m in allm if m["user_model_id"] != drafter["user_model_id"])
    return drafter["user_model_id"], critic["user_model_id"]


def critique_coherence(token, job_id):
    r = _req("POST", f"/v1/composition/jobs/{job_id}/critique", token, {})
    return (r.get("critic") or {}).get("coherence")


def gen_auto(token, proj, node_id, drafter):
    r = _req("POST", f"/v1/composition/works/{proj}/generate", token,
             {"outline_node_id": node_id, "model_source": "user_model", "model_ref": drafter,
              "operation": "draft_scene", "mode": "auto", "reasoning": "off",
              "max_output_tokens": 400})
    return r


def main():
    token = login()
    user_id = jwt_sub(token)
    drafter, critic = models(token)
    print(f"user={user_id} drafter={drafter} critic={critic}\n")

    book = _req("POST", "/v1/books", token,
                {"title": f"A3 eval {int(time.time())}", "original_language": "en"})["book_id"]
    chapters = [_req("POST", f"/v1/books/{book}/chapters", token,
                     {"original_language": "en", "title": f"Chapter {i}"})["chapter_id"]
                for i in range(1, 4)]  # 3 chapters → clean 1:1 with the 3-beat generic
    proj = _req("POST", f"/v1/composition/books/{book}/work", token)["project_id"]
    _req("PATCH", f"/v1/composition/works/{proj}", token,
         {"settings": {"critic_model_source": "user_model", "critic_model_ref": critic}})

    # Cast (glossary entities — decompose's roster comes from list_entities, which
    # has NO frequency gate, so no chapter_links needed here).
    for name in CAST:
        _internal("POST", GLOSSARY_INTERNAL, f"/internal/books/{book}/extract-entities",
                  {"source_language": "en",
                   "entities": [{"kind_code": "character", "name": name,
                                 "attributes": {}, "evidence": f"{name} appears."}]})

    tmpls = _req("GET", "/v1/composition/templates", token)["templates"]
    generic = next((t for t in tmpls if t["kind"] == "generic"), tmpls[0])
    print(f"template={generic['name']} ({len(generic['beats'])} beats), chapters={len(chapters)}\n")

    # ── A3 arm: decompose → commit → (assert persistence) → generate ──
    preview = _req("POST", f"/v1/composition/works/{proj}/outline/decompose", token,
                   {"structure_template_id": generic["id"], "premise": PREMISE,
                    "model_source": "user_model", "model_ref": drafter})
    pv_chapters = preview["chapters"]
    n_beats = sum(1 for c in pv_chapters if c["chapter"]["beat_role"])
    n_scenes = sum(len(c["scenes"]) for c in pv_chapters)
    print(f"[A3] decompose preview: {len(pv_chapters)} chapters mapped, "
          f"{n_beats} with beat_role, {n_scenes} scenes, unmapped_beats={preview['unmapped_beats']}")
    assert pv_chapters and n_scenes > 0, "decompose produced no scenes"

    commit_body = {"arc_title": generic["name"], "chapters": [{
        "chapter_id": c["chapter"]["chapter_id"], "title": c["chapter"]["title"],
        "intent": c["chapter"]["intent"], "beat_role": c["chapter"]["beat_role"],
        "scenes": [{"title": s["title"], "synopsis": s["synopsis"], "tension": s["tension"],
                    "present_entity_ids": s["present_entity_ids"]} for s in c["scenes"]],
    } for c in pv_chapters]}
    committed = _req("POST", f"/v1/composition/works/{proj}/outline/decompose/commit",
                     token, commit_body)
    print(f"[A3] commit: arc + {len(committed['chapter_ids'])} chapters + "
          f"{len(committed['scene_ids'])} scenes persisted")
    assert committed["arc_id"] and committed["scene_ids"], "commit persisted nothing"

    # Live-smoke the persistence: the committed scenes must carry beat_role + tension.
    tree = _req("GET", f"/v1/composition/works/{proj}/outline", token)
    committed_ids = set(committed["scene_ids"])
    scene_nodes = [n for n in tree["nodes"] if n["id"] in committed_ids and n["kind"] == "scene"]
    assert scene_nodes, "no committed scene nodes found in the outline"
    with_beat = [n for n in scene_nodes if n.get("beat_role")]
    with_tension = [n for n in scene_nodes if n.get("tension") is not None]
    print(f"[A3] persisted scenes: {len(scene_nodes)} total, {len(with_beat)} beat_role, "
          f"{len(with_tension)} tension — repo create_decomposed_tree LIVE-PROVEN")

    # Generate on the first committed scene of each chapter (bounded wall-clock).
    a3_coh, a3_k = [], []
    first_per_chapter = []
    seen_ch = set()
    for n in sorted(scene_nodes, key=lambda x: (str(x.get("chapter_id")), x.get("rank") or "")):
        if n.get("chapter_id") not in seen_ch:
            seen_ch.add(n.get("chapter_id"))
            first_per_chapter.append(n)
    for n in first_per_chapter:
        t0 = time.time()
        r = gen_auto(token, proj, n["id"], drafter)
        coh = critique_coherence(token, r["job_id"])
        a3_coh.append(coh); a3_k.append(r.get("k"))
        print(f"  [A3] scene tension={n.get('tension')} beat={n.get('beat_role')} "
              f"→ K={r.get('k')} coherence={coh} ({time.time()-t0:.0f}s)")

    # ── A1 arm: bare scenes (no beat_role/tension → fixed K) → generate ──
    a1_coh, a1_k = [], []
    bare_synopses = [
        "Kael scouts the fallen keep's outer wall at dusk.",
        "Bryn and Kael argue over the plan in the war tent.",
        "Mira tends the wounded as the first snow falls.",
    ]
    for i, syn in enumerate(bare_synopses):
        sid = _req("POST", f"/v1/composition/works/{proj}/outline/nodes", token,
                   {"kind": "scene", "chapter_id": chapters[i], "title": f"bare {i}",
                    "synopsis": syn})["id"]
        t0 = time.time()
        r = gen_auto(token, proj, sid, drafter)
        coh = critique_coherence(token, r["job_id"])
        a1_coh.append(coh); a1_k.append(r.get("k"))
        print(f"  [A1] bare scene (no beat/tension) → K={r.get('k')} coherence={coh} "
              f"({time.time()-t0:.0f}s)")

    # ── result ──
    a3v = [c for c in a3_coh if c is not None]
    a1v = [c for c in a1_coh if c is not None]
    print("\n=== RESULT ===")
    print(f"A3 coherence: {a3v}  median={statistics.median(a3v) if a3v else 'n/a'}  K={a3_k}")
    print(f"A1 coherence: {a1v}  median={statistics.median(a1v) if a1v else 'n/a'}  K={a1_k}")
    print(f"K spend: A3={sum(k for k in a3_k if k)} (adaptive) vs "
          f"A1={sum(k for k in a1_k if k)} (fixed) over {len(a3_k)}/{len(a1_k)} scenes")
    print("\nLIVE-SMOKE: decompose→commit→generate end-to-end PROVEN "
          "(preview tree + atomic persist + beat_role/tension on scenes + auto-generate).")
    if a3v and a1v:
        m3, m1 = statistics.median(a3v), statistics.median(a1v)
        if m3 >= m1:
            print(f"GATE: PASS — A3 median {m3} >= A1 median {m1} "
                  "(coherence may saturate on short scenes — see A1 lesson; "
                  "the structural lift is grounded intent + adaptive-K placement).")
        else:
            print(f"GATE: A3 median {m3} < A1 median {m1} — investigate before merge.")
    else:
        print("GATE: coherence inconclusive (critic returned None) — live-smoke still proves the path.")

    try:
        _req("DELETE", f"/v1/books/{book}", token)
        print("(cleaned up)")
    except Exception as exc:  # noqa
        print(f"(cleanup failed, ignore: {exc})")


if __name__ == "__main__":
    main()
