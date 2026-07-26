"""Live E2E for Compose Slice 4 (mode B — free-text intent).

Step 1: POST /compose/resolve-intent (one LLM call → proposed target+dims+technique,
NO job). Step 2: confirm the resolved target and POST /compose input_source=intent →
a fabrication/retrieval quarantined proposal. Proves the 2-step (F5) flow live.

Usage:
  python scripts/smoke_compose_intent_e2e.py --base http://127.0.0.1:8221 \
    --project <book> --user <uuid> --jwt-secret <secret> --embed <ref> --gen <ref>
"""

from __future__ import annotations

import argparse
import time

import httpx
import jwt as pyjwt

INTENT = "a wise immortal advisor who helps mortals cultivate the Dao — call them 玄虛真人"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--user", required=True)
    ap.add_argument("--jwt-secret", required=True)
    ap.add_argument("--embed", required=True)
    ap.add_argument("--gen", required=True)
    args = ap.parse_args()
    base = args.base.rstrip("/")
    uh = {"Authorization": f"Bearer {pyjwt.encode({'sub': args.user}, args.jwt_secret, algorithm='HS256')}"}

    with httpx.Client(timeout=120.0) as c:
        print("=== step 1: POST /compose/resolve-intent (LLM → proposed target, NO job) ===")
        r = c.post(
            f"{base}/v1/lore-enrichment/projects/{args.project}/compose/resolve-intent", headers=uh,
            json={"book_id": args.project, "intent_text": INTENT, "generation_model_ref": args.gen},
        )
        print(r.status_code, r.text[:300])
        if r.status_code != 200:
            print("FAIL: resolve-intent did not return a proposal"); return 1
        resolved = r.json()
        target = resolved.get("target") or {}
        name = target.get("canonical_name")
        if not name:
            print("FAIL: resolver returned no canonical_name"); return 1
        technique = resolved.get("technique") or "fabrication"
        print(f"resolved → mode={target.get('mode')} name={name!r} kind={target.get('entity_kind')} "
              f"technique={technique} dims={resolved.get('dimensions')} ✓")

        print("\n=== step 2: confirm + POST /compose input_source=intent ===")
        is_new = target.get("mode") == "new"
        compose_target = {
            "mode": target.get("mode", "new"),
            "canonical_name": name,
            "entity_kind": target.get("entity_kind", "generic"),
            "target_ref": None if is_new else name,
        }
        body = {
            "book_id": args.project, "input_source": "intent", "target": compose_target,
            "intent_text": INTENT, "technique": technique,
            "generation_model_ref": args.gen, "embedding_model_ref": args.embed,
            "max_spend_tokens": 100000, "top_k": 5,
        }
        r = c.post(f"{base}/v1/lore-enrichment/projects/{args.project}/compose", headers=uh, json=body)
        print(r.status_code, r.text[:200])
        if r.status_code != 202:
            print("FAIL: intent compose did not enqueue"); return 1
        job_id = r.json()["job_id"]

        print("\n=== poll job → completed ===")
        status_val = None
        for _ in range(60):
            jr = c.get(f"{base}/v1/lore-enrichment/jobs?book_id={args.project}&limit=50", headers=uh)
            job = next((j for j in jr.json().get("items", []) if j.get("job_id") == job_id), None)
            status_val = (job or {}).get("status")
            print(f"  job status={status_val}")
            if status_val in ("completed", "failed", "error", "done"):
                break
            time.sleep(3)
        if status_val not in ("completed", "done"):
            print(f"FAIL/INCONCLUSIVE: job ended status={status_val}"); return 2

        pr = c.get(f"{base}/v1/lore-enrichment/proposals?book_id={args.project}&limit=50", headers=uh)
        mine = [p for p in pr.json().get("items", []) if name in str(p.get("canonical_name") or p.get("title") or "")]
        if not mine:
            print("FAIL: no proposal for the resolved intent target"); return 1
        p = mine[0]
        assert (p.get("review_status") or p.get("status")) in ("proposed", "pending"), f"not quarantined: {p}"
        conf = p.get("confidence")
        assert conf is None or conf < 1.0, f"canon confidence: {conf}"
        print(f"  proposal {p.get('proposal_id') or p.get('id')} quarantined (conf={conf}) ✓")
        c.post(f"{base}/v1/lore-enrichment/proposals/{p.get('proposal_id') or p.get('id')}/reject"
               f"?project_id={args.project}", headers=uh, json={"reason": "S4 intent smoke cleanup"})

    print("\nSMOKE OK — intent → resolve-intent (proposed target, no job) → confirm → "
          "compose intent → quarantined proposal; cleaned up.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
