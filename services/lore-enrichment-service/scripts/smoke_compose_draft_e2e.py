"""Live cross-service e2e for Compose Slice 1 mode D (draft expansion).

Hits the running lore-enrichment-service directly (unverified-JWT decode) on the
demo book: POST /compose (draft, NEW generic entity, NO embed model — exercises
D-COMPOSE-S1-EMBED-REF) → 202 + job_id → poll Proposals for the quarantined
compose_draft proposal (the worker re-drives via the gen LLM) → approve+promote
the NEW entity (mints the glossary anchor, H0 retained) → retract to leave the
demo untouched.

Usage:
  python scripts/smoke_compose_draft_e2e.py --base http://127.0.0.1:8221 \
    --book 019e7850-a8d9-78dd-8b2a-f33ccc2396ad \
    --user 019d5e3c-7cc5-7e6a-8b27-1344e148bf7c \
    --gen-model 019dc738-a6b7-7bff-b953-b47868ae7db0
"""

from __future__ import annotations

import argparse
import json
import sys
import time

import httpx
import jwt as pyjwt

NEW_NAME = "测试天宫-COMPOSE-SMOKE"  # an obviously-test NEW entity (retracted at the end)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--book", required=True)
    ap.add_argument("--user", required=True)
    ap.add_argument("--gen-model", required=True)
    ap.add_argument("--poll-seconds", type=int, default=180)
    args = ap.parse_args()

    token = pyjwt.encode({"sub": args.user}, "x", algorithm="HS256")
    h = {"Authorization": f"Bearer {token}"}
    base = args.base.rstrip("/")
    proj = args.book  # project_id := bookId (the demo + FE convention)

    with httpx.Client(timeout=60.0) as c:
        # ── 1. POST /compose (draft, NEW entity, NO embed model) ──────────────────
        print("=== POST /compose (draft · new · generic · NO embed model) ===")
        body = {
            "book_id": args.book,
            "input_source": "draft",
            "generation_model_ref": args.gen_model,  # no embedding_model_ref (EMBED-REF)
            "target": {"mode": "new", "canonical_name": NEW_NAME, "entity_kind": "generic"},
            "draft_text": (
                f"{NEW_NAME}乃三十三天之外新辟之仙阙，由一位无名上仙以先天灵气凝成，"
                "悬于星河之畔，往来皆为修真练气之士。此宫不录于旧典，乃后人补述之地。"
            ),
            "expand_mode": "rewrite",
            "max_spend_tokens": 200000,  # cost-cap is denominated in TOKENS (C1)
            "top_k": 5,
        }
        r = c.post(f"{base}/v1/lore-enrichment/projects/{proj}/compose", headers=h, json=body)
        print(r.status_code, r.text)
        if r.status_code != 202:
            print("COMPOSE FAILED (expected 202)")
            return 1
        job_id = r.json()["job_id"]
        assert r.json()["technique"] == "compose_draft", "expected technique=compose_draft"
        print(f"job_id={job_id} technique=compose_draft enqueued={r.json().get('enqueued')}")

        # ── 2. poll Proposals for the quarantined compose_draft proposal ──────────
        print(f"\n=== poll Proposals (≤{args.poll_seconds}s; worker re-drives via the gen LLM) ===")
        deadline = args.poll_seconds
        found = None
        while deadline > 0:
            time.sleep(10)
            deadline -= 10
            pr = c.get(
                f"{base}/v1/lore-enrichment/proposals",
                headers=h, params={"book_id": args.book, "limit": 100},
            )
            if pr.status_code != 200:
                print("  proposals list error", pr.status_code, pr.text[:200])
                continue
            for p in pr.json().get("items", []):
                if p.get("canonical_name") == NEW_NAME and p.get("technique") == "compose_draft":
                    found = p
                    break
            jb = c.get(f"{base}/v1/lore-enrichment/jobs/{job_id}", headers=h, params={"project_id": proj})
            jst = jb.json().get("status") if jb.status_code == 200 else "?"
            print(f"  …job={jst} proposal_found={bool(found)} ({deadline}s left)")
            if found:
                break

        if not found:
            print(
                "\nPARTIAL: /compose 202 + compose_draft job created (API+DB+migration "
                "live-proven), but no proposal yet — the worker's gen LLM (LM Studio) "
                "may be unavailable/evicting. The generation path is unit-proven; re-run "
                "when the gen model is loaded."
            )
            return 2

        print("\n=== quarantined compose_draft proposal ===")
        print(json.dumps({k: found[k] for k in (
            "proposal_id", "canonical_name", "entity_kind", "origin", "technique",
            "confidence", "review_status", "target_ref",
        )}, ensure_ascii=False))
        pid = found["proposal_id"]
        assert found["origin"] == "enrichment" and found["confidence"] < 1.0, "H0 violated"
        assert found["target_ref"] in (None, ""), "new target should have no target_ref"

        # ── 3. approve (auto-walks) + promote → mints the glossary anchor ─────────
        print("\n=== approve + promote (mints the NEW glossary anchor) ===")
        ar = c.post(f"{base}/v1/lore-enrichment/proposals/{pid}/approve", headers=h, params={"project_id": proj})
        print("approve:", ar.status_code, ar.text[:200])
        pm = c.post(
            f"{base}/v1/lore-enrichment/proposals/{pid}/promote",
            headers=h, params={"project_id": proj}, json={"book_id": args.book},
        )
        print("promote:", pm.status_code, pm.text[:400])
        if pm.status_code != 200:
            print("PROMOTE FAILED")
            return 1
        promoted = pm.json()
        assert promoted["origin"] == "enrichment", "origin must survive promotion (H0)"
        ent = promoted.get("promoted_entity_id")
        print(f"promoted_entity_id={ent} facts_promoted={promoted.get('facts_promoted')}")
        assert ent, "promote should mint/resolve a glossary entity for the NEW target"

        # ── 4. retract → leave the demo untouched ─────────────────────────────────
        rt = c.post(f"{base}/v1/lore-enrichment/proposals/{pid}/retract", headers=h,
                    params={"project_id": proj}, json={"book_id": args.book})
        print("\nretract (cleanup):", rt.status_code)

    print("\nSMOKE OK — draft → 202 → compose_draft proposal → promote minted the new "
          "entity (H0 retained) → retracted (demo restored).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
