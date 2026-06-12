"""Live E1 verify for the glossary kind-alias + unknown-kind review epic.

Hits the running glossary-service directly: extract-entities with a BOGUS kind_code
(internal token) → the entity is PARKED under 'unknown' (not skipped) remembering its
source_kind_code → the review endpoints (user bearer) list it, create an alias that
reassigns it onto a real kind (re-keying its attrs so the name survives) → cleanup.

Usage:
  python scripts/smoke_kind_aliases_e2e.py --base http://127.0.0.1:8211 \
    --book 019e7850-a8d9-78dd-8b2a-f33ccc2396ad \
    --user 019d5e3c-7cc5-7e6a-8b27-1344e148bf7c \
    --internal-token dev_internal_token \
    --species-kind 019d8749-0faa-7b14-af98-82893e30b36e
"""

from __future__ import annotations

import argparse
import json
import sys
import time

import httpx
import jwt as pyjwt

BOGUS_KIND = "mythical_beast"
NAME = "測試異兽-KINDALIAS-SMOKE"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--book", required=True)
    ap.add_argument("--user", required=True)
    ap.add_argument("--internal-token", required=True)
    ap.add_argument("--species-kind", required=True)
    ap.add_argument("--jwt-secret", required=True, help="glossary JWT_SECRET (HS256)")
    args = ap.parse_args()

    base = args.base.rstrip("/")
    ih = {"X-Internal-Token": args.internal_token}
    claims = {"sub": args.user, "iat": int(time.time()), "exp": int(time.time()) + 3600}
    uh = {"Authorization": f"Bearer {pyjwt.encode(claims, args.jwt_secret, algorithm='HS256')}"}

    with httpx.Client(timeout=30.0) as c:
        # 1. extract-entities with a BOGUS kind → must be PARKED under unknown (not skipped)
        print("=== extract-entities (bogus kind 'mythical_beast') ===")
        r = c.post(
            f"{base}/internal/books/{args.book}/extract-entities", headers=ih,
            json={
                "source_language": "zh",
                "attribute_actions": {BOGUS_KIND: {}},
                "entities": [{"kind_code": BOGUS_KIND, "name": NAME, "attributes": {}, "evidence": ""}],
            },
        )
        print(r.status_code, r.text[:300])
        if r.status_code != 200:
            print("extract FAILED"); return 1
        ents = r.json().get("entities") or []
        if not ents or not ents[0].get("entity_id"):
            print("FAIL: entity was SKIPPED (not parked under unknown)"); return 1
        eid = ents[0]["entity_id"]
        print(f"parked entity_id={eid} (status={ents[0].get('status')}) ✓ not dropped")

        # 2. the review queue lists it with the source code + name preserved
        print("\n=== GET unknown-entities (review queue) ===")
        r = c.get(f"{base}/v1/glossary/books/{args.book}/unknown-entities", headers=uh)
        print(r.status_code)
        if r.status_code != 200:
            print("unknown-entities FAILED", r.text[:200]); return 1
        items = r.json().get("items", [])
        mine = next((i for i in items if i["entity_id"] == eid), None)
        if not mine:
            print("FAIL: parked entity not in the unknown review queue"); return 1
        print(json.dumps(mine, ensure_ascii=False))
        assert mine["source_kind_code"] == BOGUS_KIND, "source_kind_code not recorded"
        assert mine["name"] == NAME, "name not preserved under unknown"
        print("source_kind_code + name preserved ✓")

        # 3. merge: create an alias mythical_beast→species + reassign the parked entity
        print("\n=== POST kind-aliases (merge: mythical_beast→species, reassign) ===")
        r = c.post(
            f"{base}/v1/glossary/kind-aliases", headers=uh,
            json={"alias_code": BOGUS_KIND, "kind_id": args.species_kind,
                  "reassign": True, "book_id": args.book},
        )
        print(r.status_code, r.text[:200])
        if r.status_code != 201:
            print("alias create FAILED"); return 1
        assert r.json().get("reassigned", 0) >= 1, "expected >=1 entity reassigned"
        print(f"alias created + reassigned={r.json()['reassigned']} ✓")

        # 4. it left the unknown queue + landed under species with its name intact (re-key)
        print("\n=== verify it left unknown + name survived the kind change ===")
        r = c.get(f"{base}/v1/glossary/books/{args.book}/unknown-entities", headers=uh)
        still = next((i for i in r.json().get("items", []) if i["entity_id"] == eid), None)
        assert still is None, "entity still in the unknown queue after reassign"
        detail = c.get(f"{base}/v1/glossary/books/{args.book}/entities/{eid}", headers=uh)
        print("entity detail:", detail.status_code, detail.text[:400])
        body = detail.json()
        # name survives the re-key (attr re-pointed to species' 'name' attr_def)
        assert NAME in detail.text, "name LOST after kind reassign (re-key failed)"
        print("entity moved to species + name preserved (re-key OK) ✓")

        # 5. cleanup — delete the test entity + the alias (leave the demo untouched)
        print("\n=== cleanup ===")
        d = c.delete(f"{base}/v1/glossary/books/{args.book}/entities/{eid}", headers=uh)
        print("delete entity:", d.status_code)

    print("\nSMOKE OK — bogus kind PARKED under unknown (not dropped) → reviewed → "
          "alias-merged onto species with attrs re-keyed → cleaned up.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
