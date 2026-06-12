"""DIAG (Round 2) — does a POPULATED KG timeline carry cross-chapter plot into
the composition pack? (zero LLM calls — pure packer inspection via /grounding.)

Round-1 found chapter-boundary RE-ESTABLISHMENT is a real residual. The claim is
"production publish-as-you-write fills the KG → the timeline lens carries ch1's
plot into ch2." This probe TESTS that wiring directly, before building anything:

  seed ch1 events in the KG (persist-pass2, chapter_index=1 → event_order≈1e6) →
  GET /grounding for a ch1 scene AND a ch2 scene → print the `memory` (timeline)
  block each sees.

SUSPECTED MISMATCH (from code): gather_timeline filters `before_chronological =
scene.story_order` (≈1000/2000 from decompose), but KG `event_order` = chapter_index
×1e6 and `chronological_order` is sparse (date-derived, NULL→excluded). If the
ch2 scene's `memory` block is EMPTY despite seeded ch1 events, the timeline lens
is mis-wired (wrong axis/scale) — KG plot won't carry regardless of population,
and the fix is a packer change (use event_order with cutoff = chapter_sort×stride),
not a new cross-chapter mechanism.

Usage: python diag_kg_timeline_carry.py
"""
import base64
import json
import time
import urllib.request
import uuid

GW = "http://localhost:3123"
KNOWLEDGE_INTERNAL = "http://localhost:8216"
GLOSSARY_INTERNAL = "http://localhost:8211"
INTERNAL_TOKEN = "dev_internal_token"


def _req(method, path, token=None, body=None, timeout=120):
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
    p = token.split(".")[1]; p += "=" * (-len(p) % 4)
    return json.loads(base64.urlsafe_b64decode(p))["sub"]


def main():
    token = login()
    user_id = jwt_sub(token)
    book = _req("POST", "/v1/books", token, {"title": f"KGCARRY {int(time.time())}",
                                             "original_language": "en"})["book_id"]
    ch1 = _req("POST", f"/v1/books/{book}/chapters", token,
               {"original_language": "en", "title": "Chapter 1"})["chapter_id"]
    ch2 = _req("POST", f"/v1/books/{book}/chapters", token,
               {"original_language": "en", "title": "Chapter 2"})["chapter_id"]
    proj = _req("POST", f"/v1/composition/books/{book}/work", token)["project_id"]
    print(f"book={book}\nproj={proj}\nch1={ch1} (sort_order 1)  ch2={ch2} (sort_order 2)\n")

    # Cast entity (present lens + event participant), linked to both chapters.
    er = _internal("POST", GLOSSARY_INTERNAL, f"/internal/books/{book}/extract-entities",
                   {"source_language": "en", "entities": [{
                       "kind_code": "character", "name": "Kael", "attributes": {},
                       "evidence": "Kael the knight.",
                       "chapter_links": [
                           {"chapter_id": ch1, "chapter_title": "Chapter 1", "chapter_index": 1, "relevance": "appears"},
                           {"chapter_id": ch2, "chapter_title": "Chapter 2", "chapter_index": 2, "relevance": "appears"}]}]})
    gid = (er.get("entities") or [{}])[0].get("entity_id")
    print(f"kael glossary id={gid}")

    # Seed TWO ch1 events (chapter_index=1 → event_order≈1_000_000+idx): one WITH
    # an event_date (gets a chronological_order), one WITHOUT (chronological NULL).
    for i, (name, date) in enumerate([("The fall of Blackwater Keep", "0001-01-05"),
                                      ("Kael is cast into exile", None)]):
        _internal("POST", KNOWLEDGE_INTERNAL, "/internal/extraction/persist-pass2", {
            "user_id": user_id, "project_id": proj, "source_type": "chapter",
            "source_id": f"seed:{ch1}:{i}", "job_id": str(uuid.uuid4()),
            "extraction_model": "kgcarry-seed", "entities": [], "relations": [], "facts": [],
            "events": [{"name": name, "kind": "battle" if i == 0 else "exile",
                        "participants": ["Kael"], "participant_ids": [None],
                        "location": None, "time_cue": None,
                        "summary": f"{name}: a major chapter-1 event.",
                        "confidence": 0.95, "event_id": None, "event_date": date,
                        "status_effects": []}],
            "hierarchy_paths": {"book_id": book, "book_path": "book", "book_title": None,
                                "part_id": str(uuid.uuid4()), "part_path": "book/p1", "part_index": 1,
                                "part_title": None, "chapter_id": ch1,
                                "chapter_path": "book/p1/c1", "chapter_index": 1,
                                "chapter_title": None, "scenes": []},
            "provenance": "human_authored"})
    print("seeded 2 ch1 events (chapter_index=1)\n")

    # Two scene nodes: one in ch1 (story_order 1000), one in ch2 (story_order 2000).
    n1 = _req("POST", f"/v1/composition/works/{proj}/outline/nodes", token,
              {"kind": "scene", "chapter_id": ch1, "title": "ch1 scene",
               "synopsis": "Kael in the village.", "present_entity_ids": [gid], "story_order": 1000})["id"]
    n2 = _req("POST", f"/v1/composition/works/{proj}/outline/nodes", token,
              {"kind": "scene", "chapter_id": ch2, "title": "ch2 scene",
               "synopsis": "Kael marches to the keep.", "present_entity_ids": [gid], "story_order": 2000})["id"]

    for label, nid in [("CH1 scene (story_order 1000)", n1), ("CH2 scene (story_order 2000)", n2)]:
        g = _req("GET", f"/v1/composition/works/{proj}/scenes/{nid}/grounding", token)
        blocks = g.get("blocks") or {}
        print(f"===== {label} =====")
        print(f"  grounding_available={g.get('grounding_available')}  warnings={g.get('warnings')}")
        print(f"  memory (timeline) block: {blocks.get('memory') or '(EMPTY)'}")
        print(f"  present block: {(blocks.get('present') or '(empty)')[:160]}")
        print()

    print("VERDICT: if the CH2 memory block is EMPTY despite 2 seeded ch1 events,")
    print("the timeline lens is mis-wired (before_chronological=story_order vs event_order×1e6)")
    print("→ KG plot does NOT carry cross-chapter regardless of population.")

    _req("DELETE", f"/v1/books/{book}", token)


if __name__ == "__main__":
    main()
