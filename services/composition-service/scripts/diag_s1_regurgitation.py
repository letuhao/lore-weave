"""DIAG (a) — does S1 state-reinjection cause REGURGITATION?

Hypothesis (from the n=3 GATE FAIL): A3's defects are dominated by repetition
("repeating entire paragraphs") because S1 reinjects raw prior-scene prose into
the `recent` block and the drafter echoes it back.

This runs the A3 arm for ONE premise (default P0 — the one the n=3 judge flagged
for paragraph repetition), saves every scene's generated text, then measures
cross-scene paragraph overlap: for each scene i>0, what fraction of its
paragraphs are near-duplicates of a paragraph in some PRIOR scene. High overlap
across scene boundaries ⟹ the drafter is regurgitating reinjected prose ⟹ S1 is
(partly) self-defeating.

Cost control (respects the LM-Studio load/unload thrashing concern): critic is
set to the SAME model as the drafter, so the auto path's rerank + canon-reflect
never swap weights. Regurgitation is a DRAFTER behaviour, independent of the
critic's identity, so this does not affect the diagnosis.

Usage: python diag_s1_regurgitation.py [premise_index 0..2]
Dump : services/composition-service/scripts/_diag_dump.json (untracked; delete after)
"""
import base64
import difflib
import json
import sys
import time
import urllib.request

GW = "http://localhost:3123"
GLOSSARY_INTERNAL = "http://localhost:8211"
INTERNAL_TOKEN = "dev_internal_token"
DUMP_PATH = "_diag_dump.json"

PREMISES = [
    ("A disgraced knight retakes a fallen border keep before the winter siege.",
     ["Kael", "Bryn", "Mira"]),
    ("A market thief uncovers a conspiracy and must choose a side before the festival.",
     ["Sora", "Den", "Lia"]),
    ("Two estranged siblings inherit a haunted observatory and a dangerous ledger.",
     ["Aron", "Vesa", "Tomas"]),
]


def _req(method, path, token=None, body=None, timeout=600):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(GW + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    resp = urllib.request.urlopen(req, timeout=timeout)
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


def drafter_model(token):
    chat = [m for m in _req("GET", "/v1/model-registry/user-models?capability=chat",
                            token)["items"] if m["is_active"]]
    return next((m for m in chat if "qwen3.6-35b" in m["provider_model_name"]), chat[0])["user_model_id"]


def gen_auto(token, proj, node_id, drafter):
    r = _req("POST", f"/v1/composition/works/{proj}/generate", token,
             {"outline_node_id": node_id, "model_source": "user_model", "model_ref": drafter,
              "operation": "draft_scene", "mode": "auto", "reasoning": "off",
              "guide": "", "max_output_tokens": 400})
    return r.get("text", ""), r.get("k")


def paras(text):
    return [p.strip() for p in text.split("\n") if len(p.strip()) > 40]  # ignore tiny lines


def main():
    idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    premise, cast = PREMISES[idx]
    token = login()
    user_id = jwt_sub(token)
    drafter = drafter_model(token)
    print(f"user={user_id} drafter={drafter} (critic=drafter, no-swap) premise=P{idx}\n{premise}\n")

    book = _req("POST", "/v1/books", token,
                {"title": f"DIAG {int(time.time()*1000) % 100000}", "original_language": "en"})["book_id"]
    chapters = [_req("POST", f"/v1/books/{book}/chapters", token,
                     {"original_language": "en", "title": f"Chapter {i}"})["chapter_id"]
                for i in range(1, 4)]
    proj = _req("POST", f"/v1/composition/books/{book}/work", token)["project_id"]
    # critic = drafter → the auto path's rerank + reflect never swap models.
    _req("PATCH", f"/v1/composition/works/{proj}", token,
         {"settings": {"critic_model_source": "user_model", "critic_model_ref": drafter}})
    for name in cast:
        _internal("POST", GLOSSARY_INTERNAL, f"/internal/books/{book}/extract-entities",
                  {"source_language": "en", "entities": [{"kind_code": "character", "name": name,
                                                          "attributes": {}, "evidence": f"{name} appears."}]})
    tmpls = _req("GET", "/v1/composition/templates", token)["templates"]
    generic = next((t for t in tmpls if t["kind"] == "generic"), tmpls[0])

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
    scenes.sort(key=lambda x: (str(x.get("chapter_id")), x.get("story_order") or 0, x.get("rank") or ""))

    dump = []
    for n in scenes:
        txt, k = gen_auto(token, proj, n["id"], drafter)
        dump.append({"chapter_id": str(n["chapter_id"]), "story_order": n.get("story_order"),
                     "title": n.get("title"), "k": k, "text": txt})
        print(f"  scene story_order={n.get('story_order')} k={k} chars={len(txt)}")

    with open(DUMP_PATH, "w", encoding="utf-8") as f:
        json.dump({"premise": premise, "scenes": dump}, f, ensure_ascii=False, indent=2)
    print(f"\ndump → {DUMP_PATH}")

    # ── cross-scene paragraph-overlap analysis ──
    # For each scene i, its paragraphs; flag any para that near-matches (ratio>=0.80)
    # a paragraph in ANY PRIOR scene (cross-boundary echo) or earlier in the SAME
    # scene (intra-scene repeat). Both are the "repeating entire paragraphs" defect.
    print("\n===== REGURGITATION ANALYSIS (ratio>=0.80) =====")
    scene_paras = [paras(s["text"]) for s in dump]
    total_paras = cross_echo = intra_echo = 0
    for i, ps in enumerate(scene_paras):
        prior = [p for j in range(i) for p in scene_paras[j]]
        for pi, p in enumerate(ps):
            total_paras += 1
            if any(difflib.SequenceMatcher(None, p, q).ratio() >= 0.80 for q in prior):
                cross_echo += 1
                print(f"  [CROSS-ECHO] scene#{i} para#{pi}: {p[:90]!r}")
            elif any(difflib.SequenceMatcher(None, p, q).ratio() >= 0.80 for q in ps[:pi]):
                intra_echo += 1
                print(f"  [INTRA-ECHO] scene#{i} para#{pi}: {p[:90]!r}")
    print(f"\ntotal paragraphs={total_paras}  cross-scene echoes={cross_echo}  "
          f"intra-scene echoes={intra_echo}")
    pct = (cross_echo + intra_echo) / total_paras * 100 if total_paras else 0
    print(f"REGURGITATION RATE = {pct:.1f}%  "
          f"({'CONFIRMED — S1 reinjection is echoing' if cross_echo else 'no cross-scene echo — hypothesis WEAK'})")

    _req("DELETE", f"/v1/books/{book}", token)


if __name__ == "__main__":
    main()
