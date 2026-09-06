"""T94 — the SAME workload on BOTH engines, and the answers compared.

T90 proved the read surface passes on `age` and on `neo4j`. T93 proved the extraction workload
lands on `age`. Neither proves the thing the port exists for: that the two engines give the
SAME answer to the same question. Two adapters passing their own probes is exactly T43's stated
risk — "two adapters can agree by sharing a bug" — and passing separately is weaker still.

So: write byte-identical extraction candidates through `persist-pass2` on each backend, read
back through the same HTTP surface, and compare the NORMALISED result. Ids and timestamps
differ by construction (different projects, different runs); names, kinds, predicates, titles
and ordinals must not.

Run one arm per backend, flipping the stack between them, then diff the two JSON snapshots:

    python scripts/knowledge-engine-differential.py <base_url> <token> <secret> age   > age.json
    (flip KNOWLEDGE_GRAPH_BACKEND, recreate knowledge-service)
    python scripts/knowledge-engine-differential.py <base_url> <token> <secret> neo4j > neo4j.json

⚠️ Diff the NORMALISED fields, not the raw JSON: ids and timestamps differ by construction
(different projects, different runs). Comparing those would report a divergence on every run
and the check would be ignored within a week.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
import uuid


def _req(url, *, headers, body=None, method=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"))
    for k, v in headers.items():
        r.add_header(k, v)
    if data:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8", "replace") or "{}")
        except ValueError:
            return e.code, {}
    except Exception as e:                                        # noqa: BLE001
        return 0, {"detail": str(e)}


def _jwt(secret, uid):
    import jwt
    now = int(time.time())
    return jwt.encode({"sub": uid, "user_id": uid, "iat": now, "exp": now + 1800},
                      secret, algorithm="HS256")


def run_workload(base, tok, secret, tag):
    """Write the SAME candidates and read back a normalised snapshot."""
    uid = str(uuid.uuid4())
    bearer = {"Authorization": f"Bearer {_jwt(secret, uid)}"}
    internal = {"X-Internal-Token": tok}

    st, proj = _req(f"{base}/v1/knowledge/projects", headers=bearer,
                    body={"name": f"differential {tag}", "project_type": "book"})
    if st not in (200, 201):
        raise SystemExit(f"[{tag}] project create failed: {st} {proj}")
    pid = proj["project_id"]

    def cid(n):
        return hashlib.sha256(f"{uid}:{n}".encode()).hexdigest()[:32]

    # IDENTICAL candidate content on both engines — only the tenant differs.
    a, b, c = "Corvin Ash", "Lyra Fenn", "Mordent Vex"
    ents = [{"name": n, "kind": k, "aliases": [], "confidence": 0.9,
             "canonical_name": n.lower(), "canonical_id": cid(n)}
            for n, k in ((a, "character"), (b, "character"), (c, "faction"))]
    rels = [{"subject": a, "predicate": "ally_of", "object": b, "polarity": "positive",
             "modality": "asserted", "confidence": 0.88, "subject_id": cid(a),
             "object_id": cid(b), "relation_id": None},
            {"subject": c, "predicate": "opposes", "object": a, "polarity": "negative",
             "modality": "asserted", "confidence": 0.71, "subject_id": cid(c),
             "object_id": cid(a), "relation_id": None}]
    evs = [{"name": "The oath at Emberfall", "kind": "scene", "participants": [a, b],
            "participant_ids": [cid(a), cid(b)], "location": "Emberfall", "time_cue": "dusk",
            "summary": "Two allies swore an oath.", "confidence": 0.8, "event_id": None},
           {"name": "The siege breaks", "kind": "scene", "participants": [c],
            "participant_ids": [cid(c)], "location": None, "time_cue": None,
            "summary": "The siege ended.", "confidence": 0.6, "event_id": None}]

    st, p2 = _req(f"{base}/internal/extraction/persist-pass2", headers=internal, body={
        "user_id": uid, "project_id": pid, "source_type": "chapter",
        "source_id": str(uuid.uuid4()), "job_id": str(uuid.uuid4()),
        "extraction_model": "differential", "entities": ents, "relations": rels,
        "events": evs, "facts": [], "chapter_index": 4, "provenance": "human_authored",
        "writer_autocreate": True})
    if st != 200:
        raise SystemExit(f"[{tag}] persist-pass2 failed: {st} {p2}")

    st, listing = _req(f"{base}/v1/knowledge/entities?project_id={pid}&limit=50",
                       headers=bearer)
    st2, sub = _req(f"{base}/v1/knowledge/projects/{pid}/subgraph", headers=bearer)
    st3, tl = _req(f"{base}/v1/knowledge/timeline?project_id={pid}", headers=bearer)

    return {
        "write_counts": {k: p2.get(k) for k in
                         ("entities_merged", "relations_created", "events_merged",
                          "facts_merged", "evidence_edges")},
        "entities": sorted((e["name"], e["kind"]) for e in listing.get("entities", [])),
        "subgraph_nodes": sorted(n.get("name") for n in sub.get("nodes", [])),
        "subgraph_edges": sorted(
            (e.get("predicate"), e.get("subject_name"), e.get("object_name"))
            for e in sub.get("edges", [])),
        "events": sorted((e.get("title"), e.get("event_order"))
                         for e in tl.get("events", [])),
        "http": [st, st2, st3],
    }


def main():
    base, tok, secret = sys.argv[1], sys.argv[2], sys.argv[3]
    which = sys.argv[4]
    snap = run_workload(base, tok, secret, which)
    print(json.dumps(snap, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
