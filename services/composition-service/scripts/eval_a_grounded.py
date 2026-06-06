"""GROUNDING-FIRST eval (validate-first before building cross-chapter carry).

The n=3 GATE FAIL + diagnostic (a) showed A3's defects were dominated by
(1) a character GENDER FLIP (Bryn male→female) and (2) chapter-boundary
RE-ESTABLISHMENT — and that BOTH trace to the autonomous eval *under-grounding*:
it seeded **bare glossary stubs** (`attributes:{}`, no gender/bio) and published
nothing, so the packer's `present`/canon lenses had nothing to inject. The
drafter therefore invented entity identity per-chapter.

This eval gives BOTH arms PRODUCTION-LIKE grounding — glossary entities seeded
with a real bio (gender + role) — then re-measures. If the gender flip stops and
defects drop, the gap was an eval artifact (grounding), NOT a missing mechanism.

Round 1 = glossary bios only (robust; no KG position-scale risk). KG-timeline
seeding (for the plot/re-establishment axis) is round 2 if a residual remains.

Cost/thrashing control (LM Studio load/unload): the auto path's rerank +
canon-reflect run with **critic = drafter** (same model → zero weight swaps);
the DISTINCT pairwise judge runs ONCE per premise at the end (1 swap), keeping
the judge disjoint/unbiased. Generation config thus differs from the n=3 baseline
(which used a distinct critic in-loop) — so compare defect TYPES qualitatively
(is the gender flip / re-establishment gone?), not only W/L.

Usage: python eval_a_grounded.py [n_premises]
Dump : _grounded_dump.json (untracked — drafts saved for gender/re-establishment read)
"""
import base64
import json
import sys
import time
import urllib.request

GW = "http://localhost:3123"
COMP_INTERNAL = "http://localhost:8217"
GLOSSARY_INTERNAL = "http://localhost:8211"
INTERNAL_TOKEN = "dev_internal_token"
DUMP = "_grounded_dump.json"

# (premise, [(name, bio-with-gender+role)]). Bios are the GROUNDING under test:
# explicit gender + role so the `present` lens can anchor identity every scene.
PREMISES = [
    ("A disgraced knight retakes a fallen border keep before the winter siege.",
     [("Kael", "Kael is a disgraced male knight, once warden of the border keep; grim and exiled, he seeks redemption."),
      ("Bryn", "Bryn is a loyal male scout and soldier, Kael's longtime companion, quick-witted and weather-worn."),
      ("Mira", "Mira is a sharp-eyed female quartermaster among the keep's survivors, practical and unflinching.")]),
    ("A market thief uncovers a conspiracy and must choose a side before the festival.",
     [("Sora", "Sora is a nimble young female street thief who works the market district, wary and resourceful."),
      ("Den", "Den is a grizzled male informant and fence who warns Sora of danger, cautious and indebted."),
      ("Lia", "Lia is an ambitious female festival organizer secretly tied to the conspiracy, poised and persuasive.")]),
    ("Two estranged siblings inherit a haunted observatory and a dangerous ledger.",
     [("Aron", "Aron is the elder male sibling, a meticulous astronomer, reserved and guilt-ridden."),
      ("Vesa", "Vesa is the younger female sibling, estranged and skeptical, fierce and pragmatic."),
      ("Tomas", "Tomas is the family's aging male lawyer who keeps the dangerous ledger, formal and evasive.")]),
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


def gen_auto_text(token, proj, node_id, drafter):
    r = _req("POST", f"/v1/composition/works/{proj}/generate", token,
             {"outline_node_id": node_id, "model_source": "user_model", "model_ref": drafter,
              "operation": "draft_scene", "mode": "auto", "reasoning": "off",
              "guide": "", "max_output_tokens": 400})
    return r.get("text", ""), r.get("k")


def cowrite_text(token, proj, node_id, drafter, max_tokens):
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


def seed_bios(token, user_id, book, ch_ids, cast):
    """Seed each cast member as a glossary entity with a gender+role bio.

    short_description is a COLUMN on glossary_entities, NOT an EAV attribute —
    extract-entities silently no-ops on it (confirmed: canon_content_handler.go
    docstring). So we create the entity (extract-entities, linked to all chapters
    → freq>=2 clears the known-entities gate), THEN set the canonical bio via the
    dedicated canon-content endpoint (the same SSOT write lore-enrichment uses).
    Returns {name: entity_id}."""
    ids = {}
    links = [{"chapter_id": c, "chapter_title": f"Chapter {i+1}", "chapter_index": i + 1,
              "relevance": "appears"} for i, c in enumerate(ch_ids)]
    for name, bio in cast:
        er = _internal("POST", GLOSSARY_INTERNAL, f"/internal/books/{book}/extract-entities",
                       {"source_language": "en",
                        "entities": [{"kind_code": "character", "name": name,
                                      "attributes": {}, "evidence": bio, "chapter_links": links}]})
        ents = er.get("entities") or []
        if not ents:
            continue
        eid = ents[0]["entity_id"]
        ids[name] = eid
        # short_description is a COLUMN → set it via canon-content (extract no-ops on it).
        _internal("POST", GLOSSARY_INTERNAL,
                  f"/internal/books/{book}/entities/{eid}/canon-content",
                  {"short_description": bio})
    return ids


def probe_bios(book, user_id, cast):
    """FAIL-FAST: confirm the seeded bios actually surface via select-for-context
    (the same call gather_present makes) BEFORE the expensive generation. Returns
    the count of cast members whose short_description is non-empty."""
    grounded = 0
    for name, _ in cast:
        try:
            r = _internal("POST", GLOSSARY_INTERNAL, f"/internal/books/{book}/select-for-context",
                          {"user_id": user_id, "query": name, "max_entities": 20, "max_tokens": 1000})
        except Exception:  # noqa
            continue
        for e in r.get("entities") or []:
            if (e.get("cached_name") == name or name in (e.get("cached_name") or "")) \
                    and (e.get("short_description") or "").strip():
                grounded += 1
                break
    return grounded


def build_one(token, user_id, drafter, premise, cast):
    book = _req("POST", "/v1/books", token,
                {"title": f"GRND {int(time.time()*1000) % 100000}", "original_language": "en"})["book_id"]
    chapters = [_req("POST", f"/v1/books/{book}/chapters", token,
                     {"original_language": "en", "title": f"Chapter {i}"})["chapter_id"]
                for i in range(1, 4)]
    proj = _req("POST", f"/v1/composition/books/{book}/work", token)["project_id"]
    # critic = DRAFTER → auto-path rerank + reflect never swap models (no thrash).
    _req("PATCH", f"/v1/composition/works/{proj}", token,
         {"settings": {"critic_model_source": "user_model", "critic_model_ref": drafter}})

    seed_bios(token, user_id, book, chapters, cast)
    grounded = probe_bios(book, user_id, cast)
    print(f"    grounding probe: {grounded}/{len(cast)} bios surface via select-for-context")
    if grounded == 0:
        raise RuntimeError("NO bios surfaced — grounding seed failed; fix before generating")

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
    per_chapter = {}
    for n in scenes:
        per_chapter.setdefault(str(n["chapter_id"]), []).append(n)

    a3_parts, a3_k = [], []
    for n in scenes:
        txt, k = gen_auto_text(token, proj, n["id"], drafter)
        a3_parts.append(txt); a3_k.append(k or 0)
    a3 = "\n\n".join(p for p in a3_parts if p)

    v0_parts = []
    for i, ch in enumerate(chapters):
        n_sc = len(per_chapter.get(str(ch), [])) or 1
        sid = _req("POST", f"/v1/composition/works/{proj}/outline/nodes", token,
                   {"kind": "scene", "chapter_id": ch, "title": f"bare ch{i+1}",
                    "synopsis": f"{premise} (chapter {i+1})"})["id"]
        v0_parts.append(cowrite_text(token, proj, sid, drafter, max_tokens=min(1200, 400 * n_sc)))
    v0 = "\n\n".join(p for p in v0_parts if p)
    return book, a3, v0, a3_k


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    n = max(1, min(n, len(PREMISES)))
    token = login()
    user_id = jwt_sub(token)
    drafter, critic = models(token)
    print(f"user={user_id} drafter={drafter} judge-critic={critic} n={n} (gen critic=drafter, no-swap)\n")

    built = []  # (premise, cast, book, a3, v0, a3_k)
    for premise, cast in PREMISES[:n]:
        print(f"  building: {premise[:60]}...")
        t0 = time.time()
        book, a3, v0, a3k = build_one(token, user_id, drafter, premise, cast)
        built.append((premise, cast, book, a3, v0, a3k))
        print(f"    A3 {len(a3)} chars (K={a3k}) | V0 {len(v0)} chars | {time.time()-t0:.0f}s")

    json.dump([{"premise": p, "cast": [c[0] for c in cast], "a3": a3, "v0": v0}
               for p, cast, _, a3, v0, _ in built],
              open(DUMP, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\ndrafts → {DUMP}\n")

    # ── judge ALL at the end with the DISTINCT critic (1 model swap total) ──
    a3_w = v0_w = ties = 0
    a3_def = v0_def = 0
    for i, (premise, cast, book, a3, v0, a3k) in enumerate(built):
        if not a3.strip() or not v0.strip():
            print(f"  P{i}: SKIP empty"); continue
        swap = (i % 2 == 1)
        da, db = (v0, a3) if swap else (a3, v0)
        verdict = _internal("POST", COMP_INTERNAL, "/internal/composition/eval/pairwise-judge",
                            {"user_id": user_id, "model_source": "user_model", "model_ref": critic,
                             "draft_a": da, "draft_b": db})
        a3_label = "2" if swap else "1"; v0_label = "1" if swap else "2"
        da3 = sum(v for v in (verdict.get(f"defects_{a3_label}") or {}).values() if isinstance(v, int))
        dv0 = sum(v for v in (verdict.get(f"defects_{v0_label}") or {}).values() if isinstance(v, int))
        a3_def += da3; v0_def += dv0
        better = verdict.get("better", "tie")
        who = "A3" if better == a3_label else ("V0" if better == v0_label else "tie")
        if who == "A3": a3_w += 1
        elif who == "V0": v0_w += 1
        else: ties += 1
        print(f"  P{i}: winner={who} | A3 {da3} defects vs V0 {dv0} defects")
        if verdict.get("why"):
            print(f"       why: {verdict['why'][:160]}")

    print("\n=== RESULT (GROUNDED) ===")
    print(f"pairwise — A3:{a3_w} V0:{v0_w} tie:{ties} (n={n}) | defects A3:{a3_def} vs V0:{v0_def}")
    print("Compare to n=3 UNGROUNDED baseline: A3:1 V0:2 tie:0, defects A3:16 vs V0:9.")
    print(f"Read {DUMP}: is the gender flip GONE? is chapter-boundary re-establishment reduced?")

    for _, _, book, _, _, _ in built:
        try:
            _req("DELETE", f"/v1/books/{book}", token)
        except Exception as exc:  # noqa
            print(f"(cleanup {book}: {exc})")


if __name__ == "__main__":
    main()
