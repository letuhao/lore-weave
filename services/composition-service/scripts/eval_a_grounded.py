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
import uuid

GW = "http://localhost:3123"
COMP_INTERNAL = "http://localhost:8217"
GLOSSARY_INTERNAL = "http://localhost:8211"
KNOWLEDGE_INTERNAL = "http://localhost:8216"
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


# ── B4 chapter-assembly arms ──

def mark_scene_done(token, node_id):
    """PATCH a scene to status='done' so the stitch gate (all-scenes-done) passes."""
    _req("PATCH", f"/v1/composition/outline/nodes/{node_id}", token, {"status": "done"})


def gen_chapter_text(token, proj, chapter_id, drafter, persist=False):
    """B2 chapter single-pass endpoint → the whole chapter in one draft."""
    r = _req("POST", f"/v1/composition/works/{proj}/chapters/{chapter_id}/generate", token,
             {"model_source": "user_model", "model_ref": drafter, "reasoning": "off",
              "max_output_tokens": 2048, "persist": persist})
    return r.get("text", ""), r


def stitch_chapter_text(token, proj, chapter_id, drafter, persist=False):
    """B3 stitch endpoint → merge the chapter's done scene drafts into one chapter.
    Requires all the chapter's scenes status='done' (gate)."""
    r = _req("POST", f"/v1/composition/works/{proj}/chapters/{chapter_id}/stitch", token,
             {"model_source": "user_model", "model_ref": drafter, "reasoning": "off",
              "max_output_tokens": 2048, "persist": persist})
    return r.get("text", ""), r


def prose_plain_text(token, proj, chapter_id):
    """GET the chapter draft and project the Tiptap doc back to plain text (join
    each paragraph's _text) — the persist round-trip check."""
    draft = _req("GET", f"/v1/composition/works/{proj}/chapters/{chapter_id}/prose", token)
    body = draft.get("body") or {}
    paras = [n.get("_text", "") for n in (body.get("content") or []) if isinstance(n, dict)]
    return "\n\n".join(p for p in paras if p)


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


def seed_kg_timeline(token, user_id, proj, book, chapters, per_chapter, cast):
    """Populate the KG timeline with each chapter's PLAN events (chapter_index=i →
    event_order=i×1e6) so a scene in chapter N grounds on chapters <N via the
    LOOM-33-fixed timeline lens (before_order=scene_at_order). Simulates production
    publish-as-you-write extraction WITHOUT the slow/flaky real publish+extract.
    Seed ALL chapters up front — the lens position-bounds each scene to prior
    chapters, so no interleave needed."""
    cast_names = [n for n, _ in cast]
    total = 0
    for ci, ch in enumerate(chapters, start=1):  # chapters created in order → sort_order = ci
        events = [{
            "name": (s.get("title") or "scene"), "kind": "event",
            "participants": cast_names, "participant_ids": [None] * len(cast_names),
            "location": None, "time_cue": None,
            "summary": (s.get("synopsis") or s.get("title") or ""),
            "confidence": 0.9, "event_id": None, "event_date": None, "status_effects": [],
        } for s in per_chapter.get(str(ch), [])]
        if not events:
            continue
        total += len(events)
        _internal("POST", KNOWLEDGE_INTERNAL, "/internal/extraction/persist-pass2", {
            "user_id": user_id, "project_id": proj, "source_type": "chapter",
            "source_id": f"seed:{ch}", "job_id": str(uuid.uuid4()),
            "extraction_model": "grounded-kg-seed", "entities": [], "relations": [], "facts": [],
            "events": events,
            "hierarchy_paths": {"book_id": book, "book_path": "book", "book_title": None,
                                "part_id": str(uuid.uuid4()), "part_path": "book/p1", "part_index": 1,
                                "part_title": None, "chapter_id": ch,
                                "chapter_path": f"book/p1/c{ci}", "chapter_index": ci,
                                "chapter_title": None, "scenes": []},
            "provenance": "human_authored"})
    return total


def build_one(token, user_id, drafter, premise, cast, seed_kg=False, arms=("per_scene",)):
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

    if seed_kg:
        seeded = seed_kg_timeline(token, user_id, proj, book, chapters, per_chapter, cast)
        print(f"    KG timeline seeded: {seeded} events across {len(chapters)} chapters "
              f"(chapter N+1 now grounds on chapters <N+1 via the fixed lens)")

    # ── assembly arms (all on the SAME book + decompose plan = apples-to-apples) ──
    arms_text, a3_k = {}, []

    # per-scene auto drafts feed BOTH the per_scene arm AND the stitch arm (the
    # stitch endpoint reads each scene's completed generation job).
    if "per_scene" in arms or "stitch" in arms:
        parts = []
        for n in scenes:
            txt, k = gen_auto_text(token, proj, n["id"], drafter)
            parts.append(txt); a3_k.append(k or 0)
        if "per_scene" in arms:
            arms_text["per_scene"] = "\n\n".join(p for p in parts if p)

    if "stitch" in arms:
        for n in scenes:
            mark_scene_done(token, n["id"])  # the all-scenes-done stitch gate
        st = [stitch_chapter_text(token, proj, ch, drafter)[0] for ch in chapters]
        arms_text["stitch"] = "\n\n".join(p for p in st if p)

    if "chapter" in arms:
        ch_t = [gen_chapter_text(token, proj, ch, drafter)[0] for ch in chapters]
        arms_text["chapter"] = "\n\n".join(p for p in ch_t if p)

    v0_parts = []
    for i, ch in enumerate(chapters):
        n_sc = len(per_chapter.get(str(ch), [])) or 1
        sid = _req("POST", f"/v1/composition/works/{proj}/outline/nodes", token,
                   {"kind": "scene", "chapter_id": ch, "title": f"bare ch{i+1}",
                    "synopsis": f"{premise} (chapter {i+1})"})["id"]
        v0_parts.append(cowrite_text(token, proj, sid, drafter, max_tokens=min(1200, 400 * n_sc)))
    v0 = "\n\n".join(p for p in v0_parts if p)
    return book, proj, chapters, arms_text, v0, a3_k


ARMS_ALL = ["per_scene", "stitch", "chapter"]


def _judge_arm(user_id, critic, arm_text, v0, swap):
    """Pairwise-judge one assembly arm vs V0 (order-swapped). Returns
    (winner in {'arm','v0','tie'}, arm_defects, v0_defects, why)."""
    da, db = (v0, arm_text) if swap else (arm_text, v0)
    verdict = _internal("POST", COMP_INTERNAL, "/internal/composition/eval/pairwise-judge",
                        {"user_id": user_id, "model_source": "user_model", "model_ref": critic,
                         "draft_a": da, "draft_b": db})
    arm_label = "2" if swap else "1"; v0_label = "1" if swap else "2"
    d_arm = sum(v for v in (verdict.get(f"defects_{arm_label}") or {}).values() if isinstance(v, int))
    d_v0 = sum(v for v in (verdict.get(f"defects_{v0_label}") or {}).values() if isinstance(v, int))
    better = verdict.get("better", "tie")
    who = "arm" if better == arm_label else ("v0" if better == v0_label else "tie")
    return who, d_arm, d_v0, verdict.get("why", "")


def persist_round_trip_smoke(token, proj, chapter_id, drafter):
    """D-COMP-ASSEMBLY-LIVE-SMOKE — chapter-generate with persist=True, then GET
    the book draft and confirm the assembled prose round-tripped as valid Tiptap
    (catches D-COMP-TIPTAP-SHAPE-DRIFT)."""
    text, r = gen_chapter_text(token, proj, chapter_id, drafter, persist=True)
    if not r.get("persisted"):
        print(f"  PERSIST ROUND-TRIP: FAIL (persisted={r.get('persisted')} "
              f"err={r.get('persist_error')})")
        return False
    back = prose_plain_text(token, proj, chapter_id)
    head = (text or "").strip()[:60]
    ok = bool(head) and head in back
    print(f"  PERSIST ROUND-TRIP: {'PASS' if ok else 'FAIL'} "
          f"(draft v{r.get('draft_version')}, {len(back)} chars back, head-match={ok})")
    return ok


def main():
    pos = [a for a in sys.argv[1:] if not a.startswith("--")]
    n = int(pos[0]) if pos else 2
    n = max(1, min(n, len(PREMISES)))
    seed_kg = "--seed-kg" in sys.argv  # also seed the KG timeline per chapter (LOOM-34 re-measure)
    asm = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--assembly=")), "per_scene")
    arms = ARMS_ALL if asm == "all" else [asm]
    persist_smoke = "--persist-smoke" in sys.argv  # live cross-service persist round-trip
    token = login()
    user_id = jwt_sub(token)
    drafter, critic = models(token)
    mode = "bios + KG-timeline-seeding" if seed_kg else "bios only"
    print(f"user={user_id} drafter={drafter} judge-critic={critic} n={n} mode={mode} "
          f"arms={arms} persist_smoke={persist_smoke}\n")

    built = []  # (premise, cast, book, proj, chapters, arms_text, v0, a3_k)
    for premise, cast in PREMISES[:n]:
        print(f"  building: {premise[:60]}...")
        t0 = time.time()
        book, proj, chapters, arms_text, v0, a3k = build_one(
            token, user_id, drafter, premise, cast, seed_kg=seed_kg, arms=arms)
        built.append((premise, cast, book, proj, chapters, arms_text, v0, a3k))
        sizes = " ".join(f"{a}={len(t)}" for a, t in arms_text.items())
        print(f"    {sizes} | V0 {len(v0)} chars (K={a3k}) | {time.time()-t0:.0f}s")

    json.dump([{"premise": p, "cast": [c[0] for c in cast], "arms": at, "v0": v0}
               for p, cast, _, _, _, at, v0, _ in built],
              open(DUMP, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\ndrafts → {DUMP}\n")

    # ── live cross-service persist round-trip (once, on the first book) ──
    if persist_smoke and built and ("chapter" in arms or "stitch" in arms):
        _, _, _, proj0, chapters0, _, _, _ = built[0]
        if chapters0:
            persist_round_trip_smoke(token, proj0, chapters0[0], drafter)

    # ── judge each arm vs V0 with the DISTINCT critic (order-swapped per premise) ──
    print("\n=== RESULT (GROUNDED, per arm vs V0) ===")
    for arm in arms:
        w = l = ties = 0
        d_arm = d_v0 = 0
        for i, (premise, cast, book, proj, chapters, arms_text, v0, a3k) in enumerate(built):
            at = arms_text.get(arm, "")
            if not at.strip() or not v0.strip():
                print(f"  [{arm}] P{i}: SKIP empty"); continue
            who, da, dv, why = _judge_arm(user_id, critic, at, v0, swap=(i % 2 == 1))
            d_arm += da; d_v0 += dv
            if who == "arm": w += 1
            elif who == "v0": l += 1
            else: ties += 1
            print(f"  [{arm}] P{i}: winner={who} | {arm} {da} defects vs V0 {dv} defects")
            if why:
                print(f"        why: {why[:150]}")
        print(f"  >> {arm}: {arm} {w} / V0 {l} / tie {ties} (n={n}) | "
              f"defects {arm}:{d_arm} vs V0:{d_v0}\n")

    print("Reference: eval_a_fair chapter-granularity = A3 3-0 vs V0; "
          "per-scene concat historically loses on granularity, not state.")
    print(f"Read {DUMP}: does stitch close the granularity gap while keeping canon guards?")

    for _, _, book, _, _, _, _, _ in built:
        try:
            _req("DELETE", f"/v1/books/{book}", token)
        except Exception as exc:  # noqa
            print(f"(cleanup {book}: {exc})")


if __name__ == "__main__":
    main()
