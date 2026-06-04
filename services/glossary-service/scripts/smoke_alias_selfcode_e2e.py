"""Live verify for /review-impl fix #2: alias_code == target-kind code is allowed.

When the author parks an entity under an unknown kind, then creates a NEW kind whose
code equals that parked source code, then "merges all", the FE routes through the alias
endpoint. The BE must NOT 409 (that code now owns the target kind) — it should SKIP the
redundant alias row but STILL reassign the parked entities (unbounded). The genuinely-
dead case (alias_code is a DIFFERENT existing kind) must still 409.

Usage:
  python scripts/smoke_alias_selfcode_e2e.py --base http://127.0.0.1:8211 \
    --book <book> --user <any-uuid> --internal-token dev_internal_token \
    --other-kind <terminology-kind-id> --jwt-secret <glossary JWT_SECRET>
"""

from __future__ import annotations

import argparse
import sys
import time

import httpx
import jwt as pyjwt

SELF_CODE = "selfcode_smoke_beast"
NAME = "自碼測試-SELFCODE-SMOKE"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--book", required=True)
    ap.add_argument("--user", required=True)
    ap.add_argument("--internal-token", required=True)
    ap.add_argument("--other-kind", required=True, help="an existing DIFFERENT kind id (for the 409 case)")
    ap.add_argument("--jwt-secret", required=True)
    args = ap.parse_args()

    base = args.base.rstrip("/")
    ih = {"X-Internal-Token": args.internal_token}
    claims = {"sub": args.user, "iat": int(time.time()), "exp": int(time.time()) + 3600}
    uh = {"Authorization": f"Bearer {pyjwt.encode(claims, args.jwt_secret, algorithm='HS256')}"}

    created_kind = None
    eids: list[str] = []
    eid = None
    with httpx.Client(timeout=30.0) as c:
        try:
            # 1. park a bogus-kind entity under unknown
            print("=== extract-entities (bogus kind == future new-kind code) ===")
            r = c.post(
                f"{base}/internal/books/{args.book}/extract-entities", headers=ih,
                json={"source_language": "zh", "attribute_actions": {SELF_CODE: {}},
                      "entities": [{"kind_code": SELF_CODE, "name": NAME, "attributes": {}, "evidence": ""}]},
            )
            print(r.status_code, r.text[:200])
            if r.status_code != 200:
                print("extract FAILED"); return 1
            eid = (r.json().get("entities") or [{}])[0].get("entity_id")
            if not eid:
                print("FAIL: entity skipped, not parked"); return 1
            eids.append(eid)
            print(f"parked entity_id={eid} ✓")

            # 2. create a NEW kind whose code == the parked source code
            print("\n=== POST /kinds (code == source code) ===")
            r = c.post(f"{base}/v1/glossary/kinds", headers=uh,
                       json={"code": SELF_CODE, "name": "Selfcode Smoke Kind"})
            print(r.status_code, r.text[:200])
            if r.status_code != 201:
                print("kind create FAILED"); return 1
            created_kind = r.json()["kind_id"]
            print(f"new kind_id={created_kind} ✓")

            # 3. merge via alias endpoint — MUST be 201 (skip alias) + reassign, NOT 409
            print("\n=== POST /kind-aliases (alias_code == target kind code) → expect 201 ===")
            r = c.post(f"{base}/v1/glossary/kind-aliases", headers=uh,
                       json={"alias_code": SELF_CODE, "kind_id": created_kind,
                             "reassign": True, "book_id": args.book})
            print(r.status_code, r.text[:200])
            if r.status_code != 201:
                print("FAIL: self-code merge was rejected (regression of fix #2)"); return 1
            body = r.json()
            assert body.get("reassigned", 0) >= 1, "expected >=1 reassigned"
            assert not body.get("alias_id"), "expected NO alias row (skip-alias path)"
            print(f"reassigned={body['reassigned']}, alias_id empty (skipped) ✓")

            # 4. NO alias row was actually persisted for this code
            print("\n=== GET /kind-aliases → confirm no row for SELF_CODE ===")
            r = c.get(f"{base}/v1/glossary/kind-aliases", headers=uh)
            rows = [a for a in r.json().get("items", []) if a["alias_code"] == SELF_CODE]
            assert not rows, f"unexpected alias row persisted: {rows}"
            print("no redundant alias row ✓")

            # 5. entity left the unknown queue + name survived the re-key
            print("\n=== verify entity moved off unknown + name preserved ===")
            r = c.get(f"{base}/v1/glossary/books/{args.book}/unknown-entities", headers=uh)
            assert not any(i["entity_id"] == eid for i in r.json().get("items", [])), "still unknown"
            d = c.get(f"{base}/v1/glossary/books/{args.book}/entities/{eid}", headers=uh)
            assert d.json().get("kind_id") == created_kind, "entity not on the new kind"
            assert NAME in d.text, "name lost in re-key"
            print("entity on new kind + name intact ✓")

            # 6. the genuinely-dead case still 409: alias_code 'character' (a DIFFERENT
            #    existing kind) pointed at the terminology kind — clash kind != target.
            print("\n=== POST /kind-aliases (alias_code='character' → terminology) → expect 409 ===")
            r = c.post(f"{base}/v1/glossary/kind-aliases", headers=uh,
                       json={"alias_code": "character", "kind_id": args.other_kind, "reassign": False})
            print(r.status_code, r.text[:160])
            if r.status_code != 409:
                print("FAIL: dead-alias guard no longer fires (over-relaxed)"); return 1
            print("dead-alias guard still 409 ✓")

            # 7. fix #6 step 1b: merge a parked entity onto the EXISTING terminology kind,
            #    which uses a 'term' display attr (not 'name'). The name must survive via
            #    the name↔term display mapping in rekeyEntityToKind.
            print("\n=== park another + merge onto terminology ('term' kind) → name must survive ===")
            r = c.post(
                f"{base}/internal/books/{args.book}/extract-entities", headers=ih,
                json={"source_language": "zh", "attribute_actions": {"termmap_smoke": {}},
                      "entities": [{"kind_code": "termmap_smoke", "name": "詞條測試-TERMMAP", "attributes": {}, "evidence": ""}]},
            )
            eid2 = (r.json().get("entities") or [{}])[0].get("entity_id")
            if not eid2:
                print("FAIL: second entity not parked"); return 1
            eids.append(eid2)
            r = c.post(f"{base}/v1/glossary/kind-aliases", headers=uh,
                       json={"alias_code": "termmap_smoke", "kind_id": args.other_kind,
                             "reassign": True, "book_id": args.book})
            print("merge→terminology:", r.status_code, r.text[:160])
            if r.status_code != 201 or r.json().get("reassigned", 0) < 1:
                print("FAIL: merge onto terminology failed"); return 1
            d = c.get(f"{base}/v1/glossary/books/{args.book}/entities/{eid2}", headers=uh)
            assert d.json().get("kind_id") == args.other_kind, "entity not on terminology"
            assert "詞條測試-TERMMAP" in d.text, "name LOST moving name→term kind (step 1b broken)"
            assert d.json().get("display_name") == "詞條測試-TERMMAP", "display_name not resolved from 'term'"
            print("name survived name→term mapping + display_name resolves ✓")
        finally:
            print("\n=== cleanup ===")
            for e in eids:
                print(f"delete entity {e[:8]}:", c.delete(f"{base}/v1/glossary/books/{args.book}/entities/{e}", headers=uh).status_code)
            if created_kind:
                print("delete kind:", c.delete(f"{base}/v1/glossary/kinds/{created_kind}", headers=uh).status_code)

    print("\nSMOKE OK — self-code merge allowed (skip alias + reassign), dead-alias still 409.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
