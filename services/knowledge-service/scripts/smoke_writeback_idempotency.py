"""Live verify for the enriched-writeback idempotency fix.

Reproduces the D-KNOWLEDGE-ENRICHED-WRITEBACK-IDEMPOTENCY collision: two write-backs
for the SAME canonical entity (same user/project/name/kind → same canonical `id`) but
DIFFERENT glossary_entity_ids — e.g. a glossary entity deleted+recreated with the same
name, or a rename. Before the fix the anchor MERGEd on (user_id, glossary_entity_id),
so the second call missed the existing node and ON CREATE set a duplicate `id` →
ConstraintValidationFailed (500). After the fix it MERGEs on the canonical `id`
(matching the glossary→KG canonical sync), so the second call ADOPTS the existing node.

Usage:
  python scripts/smoke_writeback_idempotency.py --base http://127.0.0.1:8216 \
    --internal-token dev_internal_token
"""

from __future__ import annotations

import argparse
import uuid

import httpx

USER = "00000000-0000-0000-0bbb-000000000001"
NAME = "SMOKE_DUP_ENTITY_史密斯"
KIND = "character"


def _wb(user, gid, proposal):
    return {
        "user_id": user,
        "project_id": None,
        "proposal_id": proposal,
        "glossary_entity_id": gid,
        "canonical_name": NAME,
        "entity_kind": KIND,
        "technique": "fabrication",
        "facts": [{"dimension": "历史", "content": "測試補充內容", "confidence": 0.3}],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--internal-token", required=True)
    args = ap.parse_args()
    base = args.base.rstrip("/")
    h = {"X-Internal-Token": args.internal_token}
    g1, g2 = str(uuid.uuid4()), str(uuid.uuid4())
    p1, p2, p3 = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())

    with httpx.Client(timeout=30.0) as c:
        print("=== write-back #1 (glossary_entity_id G1) ===")
        r1 = c.post(f"{base}/internal/knowledge/enriched-writeback", headers=h, json=_wb(USER, g1, p1))
        print(r1.status_code, r1.text[:160])
        if r1.status_code != 200:
            print("FAIL: first write-back failed"); return 1

        print("\n=== write-back #2 (DIFFERENT glossary_entity_id G2, same canonical entity) ===")
        r2 = c.post(f"{base}/internal/knowledge/enriched-writeback", headers=h, json=_wb(USER, g2, p2))
        print(r2.status_code, r2.text[:160])
        if r2.status_code != 200:
            print("FAIL: second write-back 500'd — id collision regression (the bug)"); return 1
        print("second write-back adopted the existing canonical node (no duplicate id) ✓")

        print("\n=== write-back #3 (re-promote with the ORIGINAL G1 again — idempotent) ===")
        r3 = c.post(f"{base}/internal/knowledge/enriched-writeback", headers=h, json=_wb(USER, g1, p3))
        print(r3.status_code, r3.text[:120])
        if r3.status_code != 200:
            print("FAIL: re-promote with original anchor failed"); return 1
        print("re-promote idempotent ✓")

    print("\nSMOKE OK — write-back is idempotent across glossary_entity_id churn "
          "(no duplicate :Entity(id)). Verify single node via cypher; then clean test nodes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
