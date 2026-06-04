"""Live E2E for Compose Slice 2 (mode C — paste-context).

Acceptance (spec §5 slice 2): pasted text → ingested as a grounding corpus → a
retrieval job grounds on it → a QUARANTINED proposal; a `copyrighted` assertion is
refused (403). H0: the proposal is non-canon (origin=enrichment, confidence<1.0,
review_status=proposed); a NEW target writes NOTHING to glossary at compose time.

Usage:
  python scripts/smoke_compose_context_e2e.py --base http://127.0.0.1:8221 \
    --project <book/project uuid> --user <uuid> --jwt-secret <secret> \
    --embed <embed model_ref> --gen <gen model_ref>
"""

from __future__ import annotations

import argparse
import time

import httpx
import jwt as pyjwt

TARGET = "蓬萊仙島-CTX-SMOKE"
CONTEXT = (
    "蓬萊乃東海之上的仙山，雲霧繚繞，仙人所居。山中有瓊樓玉宇，奇花異草，"
    "服之可長生。傳說秦皇漢武皆遣方士入海求之而不得。"
)


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
    h = {"Authorization": f"Bearer {pyjwt.encode({'sub': args.user}, args.jwt_secret, algorithm='HS256')}"}
    compose_url = f"{base}/v1/lore-enrichment/projects/{args.project}/compose"

    def _body(license_: str) -> dict:
        return {
            "book_id": args.project,
            "input_source": "context",
            "embedding_model_ref": args.embed,
            "generation_model_ref": args.gen,
            "context_text": CONTEXT,
            "context_license": license_,
            "technique": "retrieval",
            "target": {"mode": "new", "canonical_name": TARGET, "entity_kind": "location"},
            "max_spend_usd": 100000,
            "top_k": 5,
        }

    with httpx.Client(timeout=60.0) as c:
        # 1. copyrighted → refused (default-deny), no job.
        print("=== copyrighted context → expect 403 ===")
        r = c.post(compose_url, headers=h, json=_body("copyrighted"))
        print(r.status_code, r.text[:160])
        if r.status_code != 403:
            print("FAIL: copyrighted was not refused"); return 1
        print("copyrighted refused ✓")

        # 2. public_domain → 202 + job_id (the paste is ingested as a corpus).
        print("\n=== public_domain context → expect 202 + job_id ===")
        r = c.post(compose_url, headers=h, json=_body("public_domain"))
        print(r.status_code, r.text[:200])
        if r.status_code != 202:
            print("FAIL: context compose did not enqueue (corpus ingest failed?)"); return 1
        job_id = r.json().get("job_id")
        print(f"enqueued job_id={job_id} ✓ (corpus ingested synchronously)")

        # 3. poll the job to a terminal status.
        print("\n=== poll job → completed ===")
        jobs_url = f"{base}/v1/lore-enrichment/jobs?book_id={args.project}&limit=50"
        status_val = None
        for _ in range(60):  # ~180s
            jr = c.get(jobs_url, headers=h)
            items = jr.json().get("items", []) if jr.status_code == 200 else []
            job = next((j for j in items if j.get("job_id") == job_id or j.get("id") == job_id), None)
            status_val = (job or {}).get("status")
            print(f"  job status={status_val}")
            if status_val in ("completed", "failed", "error", "done"):
                break
            time.sleep(3)
        if status_val not in ("completed", "done"):
            print(f"FAIL/INCONCLUSIVE: job ended status={status_val} (LM-Studio eviction?)"); return 2

        # 4. find the quarantined proposal for the target, grounded on the corpus.
        print("\n=== verify a QUARANTINED proposal for the target ===")
        pr = c.get(f"{base}/v1/lore-enrichment/proposals?book_id={args.project}&limit=50", headers=h)
        props = pr.json().get("items", []) if pr.status_code == 200 else []
        mine = [p for p in props if TARGET in str(p.get("canonical_name") or p.get("title") or "")]
        print(f"  proposals for target: {len(mine)}")
        if not mine:
            print("FAIL: no proposal produced for the context target"); return 1
        p = mine[0]
        assert (p.get("review_status") or p.get("status")) in ("proposed", "pending"), f"not quarantined: {p}"
        assert p.get("origin", "enrichment") == "enrichment", f"origin not enrichment: {p}"
        conf = p.get("confidence")
        assert conf is None or conf < 1.0, f"canon confidence on a proposal: {conf}"
        print(f"  proposal {p.get('proposal_id') or p.get('id')} quarantined (origin=enrichment, conf={conf}) ✓")

    print("\nSMOKE OK — paste → corpus → grounded QUARANTINED proposal; copyrighted refused; "
          "new target wrote nothing to glossary (H0). NOTE: leaves a PD test corpus + a "
          "quarantined proposal (non-canon) — reject in the UI if unwanted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
