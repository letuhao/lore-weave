"""A2 eval-gate — the SEEDED-CONTRADICTION harness (gone-cast → FIRE + repair).

Proves the full A2 entity-status canon arc end-to-end on a live stack:

    seed :EntityStatus{gone} (chapter 1)
      → outline a scene in chapter 2 whose cast includes the gone character
      → generate (mode=auto)
      → the engine's canon reflect loop:
          fact_for_check (knowledge) → SCORE symbolic guard → distinct LLM-judge
          confirm → reflect(check → revise ≤ N)

For n scenarios it builds a FRESH throwaway book each time (no shared canon),
seeds a death in chapter 1 via the knowledge persist-pass2 path, then asks the
composition engine to draft a chapter-2 scene that portrays the dead character
as actively present. A correctly-wired arc must DETECT that contradiction.

DETECTION CRITERION — `status=="checked"` AND `iterations>=1`.
  `iterations>=1` is the true "contradiction FIRED" signal: the engine only runs
  a revise pass after the symbolic guard finds a gone-cast candidate AND the
  distinct judge confirms it (`confirmed is True`). `resolved` is NOT the gate —
  it is the *repair outcome* (`True` = the revise pass removed the gone character,
  the desired result; `False` = it survived). Gating on `resolved==false` (the
  first-pass CLARIFY guess) would FAIL the eval precisely when the reflect loop
  works best. We report `resolved` as informational and gate on the FIRE.

Seeding mechanics (no real extraction job needed):
  1. POST gateway /v1/books + 2 chapters (book-service assigns chapter sort_order
     1, 2 — the scene's reading position axis).
  2. POST gateway /v1/composition/books/{book}/work — this creates the bound
     knowledge_projects row (project_id ↔ book_id) the anchor loader needs.
  3. POST glossary internal /internal/books/{book}/extract-entities — mint the
     character as a real glossary entity → glossary_entity_id (the cast id).
  4. POST knowledge internal /internal/extraction/persist-pass2 with
     hierarchy_paths(chapter_index=1) + an event carrying
     status_effects=[{entity_ref, status:"gone"}]. The anchor loader fetches the
     glossary entity → creates :Entity{glossary_entity_id} in Neo4j; the writer's
     Tier-A.2 resolution writes :EntityStatus{from_order=1_000_000, status:"gone"}.
  5. Outline a scene on chapter 2 (sort_order 2 → at_order 2_000_000) with
     present_entity_ids=[glossary_entity_id]. fact_for_check resolves the cast id
     via the glossary_entity_id FK, sees from_order(1M) ≤ at_order(2M) → gone.

Run from the host against the gateway (public) + the internal service ports.

Usage: python eval_a2_canon.py [n_scenarios]
"""
import base64
import json
import sys
import time
import urllib.error
import urllib.request
import uuid

GW = "http://localhost:3123"            # api-gateway-bff (public, JWT)
KNOWLEDGE_INTERNAL = "http://localhost:8216"  # knowledge-service :8092
GLOSSARY_INTERNAL = "http://localhost:8211"   # glossary-service :8088
INTERNAL_TOKEN = "dev_internal_token"

# (character name, scene synopsis that portrays them as ACTIVELY present).
# Distinct names so the n runs don't share canon by accident; each synopsis
# names the character as the acting subject so the symbolic guard reliably
# matches the literal name in the drafted prose.
SCENARIOS = [
    ("Kai",
     "Kai strode through the eastern gate at dawn, fully rested, and personally "
     "rallied the troops for the coming siege, shouting orders across the yard."),
    ("Mira",
     "Mira laughed as she crossed the river bridge, waving to the merchants and "
     "calling fresh orders to her crew as she stepped aboard the moored barge."),
    ("Theron",
     "Theron rose from the great chair, drew his sword, and led the charge down "
     "the marble hall, his voice ringing off the columns as the guards followed."),
    ("Selene",
     "Selene knelt by the fountain, dipped her hands in the cool water, then "
     "stood and addressed the gathered crowd, her words steady and clear."),
    ("Darian",
     "Darian vaulted onto his horse at the crossroads, reined it about, and "
     "galloped toward the burning village, calling for the riders to follow."),
]


def _req(method, path, token=None, body=None, timeout=300):
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
    r = _req("POST", "/v1/auth/login", body={"email": "claude-test@loreweave.dev",
                                             "password": "Claude@Test2026"})
    return r["access_token"]


def jwt_sub(token):
    """The user_id is the JWT `sub` claim — decode the payload (no verify; we
    only need the id, and we already hold a valid token)."""
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)  # base64url pad
    return json.loads(base64.urlsafe_b64decode(payload))["sub"]


def models(token):
    chat = [m for m in _req("GET", "/v1/model-registry/user-models?capability=chat",
                            token)["items"] if m["is_active"]]
    allm = [m for m in _req("GET", "/v1/model-registry/user-models?include_inactive=true",
                            token)["items"] if m["is_active"]]
    drafter = next((m for m in chat if "qwen3.6-35b" in m["provider_model_name"]), chat[0])
    # The judge MUST be a distinct model (anti-self-reinforcement) or the engine
    # runs symbolic-only (confirmed stays None → advisory → never auto-revises).
    critic = next(m for m in allm if m["user_model_id"] != drafter["user_model_id"])
    return drafter["user_model_id"], critic["user_model_id"]


def seed_gone_entity(token, user_id, book, project, ch1, ch2, name):
    """Mint `name` as a glossary entity, then seed an :EntityStatus{gone} in
    chapter 1 via persist-pass2. Returns the glossary entity_id (the cast id).

    The glossary entity is linked to BOTH chapters (frequency=2). The knowledge
    anchor loader (run inside persist-pass2) fetches anchors via the glossary
    `known-entities` endpoint, which HAVING-filters `COUNT(chapter_entity_links)
    >= 2` (its default min_frequency). Without ≥2 distinct chapter links the
    entity is invisible to the loader → no anchored :Entity → the status_effect
    can't resolve → no :EntityStatus is written (the failure mode this seeds
    around)."""
    # 1. Glossary entity — a real cast member with a stable glossary_entity_id,
    #    linked to 2 chapters so it clears the known-entities frequency gate.
    er = _internal("POST", GLOSSARY_INTERNAL, f"/internal/books/{book}/extract-entities",
                   {"source_language": "en",
                    "entities": [{"kind_code": "character", "name": name,
                                  "attributes": {}, "evidence": f"{name} dies in battle.",
                                  "chapter_links": [
                                      {"chapter_id": ch1, "chapter_title": "Chapter 1",
                                       "chapter_index": 1, "relevance": "appears"},
                                      {"chapter_id": ch2, "chapter_title": "Chapter 2",
                                       "chapter_index": 2, "relevance": "appears"},
                                  ]}]})
    ents = er.get("entities") or []
    if not ents:
        raise RuntimeError(f"glossary extract returned no entity for {name!r}: {er}")
    gid = ents[0]["entity_id"]

    # 2. Seed the death + gone-status in chapter 1. hierarchy_paths.chapter_index=1
    #    → event_order = 1 * 1_000_000. The anchor loader (run inside persist-pass2)
    #    fetches the glossary entity → :Entity{glossary_entity_id=gid}; the writer's
    #    Tier-A.2 resolves the status_effect entity_ref → :EntityStatus{gone}.
    part_id = str(uuid.uuid4())
    _internal("POST", KNOWLEDGE_INTERNAL, "/internal/extraction/persist-pass2", {
        "user_id": user_id,
        "project_id": project,
        "source_type": "chapter",
        "source_id": f"seed:{ch1}",
        "job_id": str(uuid.uuid4()),
        "extraction_model": "eval-a2-seed",
        "entities": [],
        "relations": [],
        "facts": [],
        "events": [{
            "name": f"The death of {name}",
            "kind": "death",
            "participants": [name],
            "participant_ids": [None],
            "location": None,
            "time_cue": None,
            "summary": f"{name} is slain at the end of the battle in chapter one.",
            "confidence": 0.97,
            "event_id": None,
            "status_effects": [{"entity_ref": name, "status": "gone"}],
        }],
        "hierarchy_paths": {
            "book_id": book,
            "book_path": "book",
            "book_title": None,
            "part_id": part_id,
            "part_path": "book/part-1",
            "part_index": 1,
            "part_title": None,
            "chapter_id": ch1,
            "chapter_path": "book/part-1/chapter-1",
            "chapter_index": 1,
            "chapter_title": None,
            "scenes": [],
        },
        "provenance": "human_authored",
    })
    return gid


def run_scenario(token, user_id, drafter, critic, name, synopsis):
    book = _req("POST", "/v1/books", token,
                {"title": f"A2 eval {name} {int(time.time())}",
                 "original_language": "en"})["book_id"]
    ch1 = _req("POST", f"/v1/books/{book}/chapters", token,
               {"original_language": "en", "title": "Chapter 1"})["chapter_id"]
    ch2 = _req("POST", f"/v1/books/{book}/chapters", token,
               {"original_language": "en", "title": "Chapter 2"})["chapter_id"]
    proj = _req("POST", f"/v1/composition/books/{book}/work", token)["project_id"]
    _req("PATCH", f"/v1/composition/works/{proj}", token,
         {"settings": {"critic_model_source": "user_model", "critic_model_ref": critic}})

    gid = seed_gone_entity(token, user_id, book, proj, ch1, ch2, name)

    node = _req("POST", f"/v1/composition/works/{proj}/outline/nodes", token,
                {"kind": "scene", "chapter_id": ch2, "title": name,
                 "synopsis": synopsis, "present_entity_ids": [gid], "story_order": 1})["id"]

    r = _req("POST", f"/v1/composition/works/{proj}/generate", token,
             {"outline_node_id": node, "model_source": "user_model", "model_ref": drafter,
              "operation": "draft_scene", "mode": "auto", "reasoning": "off",
              "max_output_tokens": 400})
    canon = r.get("canon") or {}
    return book, proj, gid, canon


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    n = max(1, min(n, len(SCENARIOS)))
    token = login()
    user_id = jwt_sub(token)
    drafter, critic = models(token)
    print(f"user={user_id} drafter={drafter} critic={critic} n={n}\n")

    rows = []
    books = []
    for name, syn in SCENARIOS[:n]:
        t0 = time.time()
        try:
            book, proj, gid, canon = run_scenario(token, user_id, drafter, critic, name, syn)
            books.append(book)
        except (urllib.error.HTTPError, urllib.error.URLError, RuntimeError) as exc:
            detail = ""
            if isinstance(exc, urllib.error.HTTPError):
                try:
                    detail = exc.read().decode()[:300]
                except Exception:  # noqa
                    pass
            print(f"  {name}: ERROR {exc} {detail}")
            rows.append((name, None))
            continue
        dt = time.time() - t0
        status = canon.get("status")
        iters = canon.get("iterations", 0)
        resolved = canon.get("resolved")
        viol = canon.get("violations") or []
        fired = status == "checked" and iters >= 1
        outcome = ("repaired" if resolved else "flagged-unrepaired") if fired else "—"
        rows.append((name, fired))
        print(f"  {name}: status={status} iters={iters} resolved={resolved} "
              f"violations={len(viol)} → {'FIRED' if fired else 'NO-FIRE'} "
              f"({outcome}, {dt:.0f}s)")
        if viol:
            v = viol[0]
            print(f"       v0: src={v.get('source')} confirmed={v.get('confirmed')} "
                  f"matched={v.get('matched')!r} why={(v.get('why') or '')[:120]!r}")

    fired_n = sum(1 for _, f in rows if f)
    print("\n=== RESULT ===")
    print(f"FIRED {fired_n}/{len(rows)} scenarios "
          f"(status=checked AND iterations>=1 — gone-cast contradiction detected)")
    gate = "PASS — A2 canon arc fires end-to-end" if fired_n == len(rows) and rows \
        else "FAIL — at least one scenario did not detect the seeded contradiction"
    print(f"GATE: {gate}")

    for book in books:
        try:
            _req("DELETE", f"/v1/books/{book}", token)
        except Exception as exc:  # noqa
            print(f"(cleanup failed for {book}, ignore: {exc})")


if __name__ == "__main__":
    main()
