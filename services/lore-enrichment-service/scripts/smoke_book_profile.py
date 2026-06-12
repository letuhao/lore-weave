"""Live cross-service smoke for de-bias C3 slice 0d (book-profile authoring).

Hits the running lore-enrichment-service directly (unverified-JWT decode) on the
demo Fengshen book: GET (seeded profile) → PUT round-trip → GET. Optionally runs
suggest when a --model-ref is given (needs LM Studio). Cross-service: the owner
check reads book-service; suggest reads knowledge + provider-registry.

Usage:
  python scripts/smoke_book_profile.py --base http://127.0.0.1:8221 \
      --book 019e7850-a8d9-78dd-8b2a-f33ccc2396ad \
      --user 019d5e3c-7cc5-7e6a-8b27-1344e148bf7c [--project <pid> --model-ref <ref>]
"""

from __future__ import annotations

import argparse
import json
import sys

import httpx
import jwt as pyjwt


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--book", required=True)
    ap.add_argument("--user", required=True)
    ap.add_argument("--project", default=None)
    ap.add_argument("--model-ref", default=None)
    args = ap.parse_args()

    token = pyjwt.encode({"sub": args.user}, "x", algorithm="HS256")
    h = {"Authorization": f"Bearer {token}"}
    url = f"{args.base}/v1/lore-enrichment/books/{args.book}/profile"

    with httpx.Client(timeout=200.0) as c:
        print("=== GET profile (seeded Fengshen expected) ===")
        r = c.get(url, headers=h)
        print(r.status_code, json.dumps(r.json(), ensure_ascii=False))
        if r.status_code != 200:
            return 1
        original = r.json()

        print("\n=== PUT profile (round-trip: tweak voice, keep the rest) ===")
        body = {
            "worldview": original["worldview"],
            "language": original["language"],
            "era_policy": original["era_policy"],
            "voice": "原著文言-白话 (smoke-edited)",
            "anachronism_markers": original["anachronism_markers"],
            "dimension_overrides": original["dimension_overrides"],
        }
        r = c.put(url, headers=h, json=body)
        print(r.status_code, json.dumps(r.json(), ensure_ascii=False))
        if r.status_code != 200 or r.json()["voice"] != body["voice"]:
            print("PUT round-trip FAILED")
            return 1
        if r.json()["profile_source"] != "manual":
            print("expected profile_source=manual after author PUT")
            return 1

        print("\n=== GET profile (confirm persisted) ===")
        r = c.get(url, headers=h)
        print(r.status_code, json.dumps(r.json(), ensure_ascii=False))
        persisted = r.json()
        assert persisted["voice"] == body["voice"], "persisted voice mismatch"

        # restore original voice/source so the demo is untouched
        restore = dict(body)
        restore["voice"] = original["voice"]
        c.put(url, headers=h, json=restore)
        print("\n(restored original voice)")

        if args.project and args.model_ref:
            print("\n=== POST suggest (needs LM Studio) ===")
            r = c.post(
                f"{url}/suggest", headers=h,
                json={"project_id": args.project, "suggest_model_ref": args.model_ref},
            )
            print(r.status_code, json.dumps(r.json(), ensure_ascii=False)[:1200])

    print("\nSMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
