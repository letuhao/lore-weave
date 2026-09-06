#!/usr/bin/env python3
"""CP-0.5 — freeze the old runtime's tool catalog into a committed snapshot.

Spec: ``docs/specs/2026-08-03-agent-runtime-unification/`` · run:
``docs/plans/2026-08-04-agent-runtime-RUNSTATE.md``.

**The problem this closes.** The POC arms A-E were run against the LIVE federated catalog. That
catalog has changed since — tools added, renamed, deprecated — so the published arm results
**cannot be reproduced today**, and a baseline that cannot be re-run is not a control group. It is
a memory of a measurement.

The whole claim of this run is *"the new runtime beats the old one"*. That sentence needs an *old
one* that still exists in a fixed form after the new one ships. This script produces it: one JSON
file, content-hashed, committed, from which the arms can be replayed without any service running.

**What is deliberately NOT done here.** No filtering, no normalisation, no "cleanup" of the catalog.
The baseline must be the surface as it actually was, including its deprecated entries and its
duplicate capabilities — those are not noise, they are the thing being compared against. A tidied
baseline would flatter the new runtime by comparing it against a version of the old one that never
served a request.

Usage::

    python scripts/freeze-tool-catalog.py                 # write the snapshot
    python scripts/freeze-tool-catalog.py --verify        # re-hash, do not overwrite
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "contracts" / "agent-runtime-baseline"
SNAPSHOT = OUT_DIR / "tools-list.snapshot.json"

DEFAULT_GATEWAY = os.environ.get("AI_GATEWAY_URL", "http://localhost:8787")
INTERNAL_TOKEN = os.environ.get("INTERNAL_SERVICE_TOKEN", "dev-internal-token")


def canonical_hash(payload: object) -> str:
    """Content hash over the catalog, order-independent at the top level.

    ``sort_keys`` plus a pre-sorted tool list, because the live surface is assembled from a ``set``
    and its order changes between restarts. Hashing the wire order would make every snapshot differ
    from every other one and the hash would certify nothing.
    """
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


async def fetch_catalog(gateway: str, user_id: str | None) -> list[dict]:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    headers = {"X-Internal-Token": INTERNAL_TOKEN}
    if user_id:
        # The per-user external-MCP overlay is keyed on this header. Captured deliberately: the
        # baseline must include what a REAL turn saw, and a real turn carries a user.
        headers["X-User-Id"] = user_id
    async with streamablehttp_client(f"{gateway}/mcp", headers=headers,
                                     timeout=60, sse_read_timeout=60) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
    out: list[dict] = []
    for t in listed.tools:
        entry = {
            "name": t.name,
            "description": t.description or "",
            "inputSchema": t.inputSchema,
        }
        meta = getattr(t, "meta", None) or getattr(t, "_meta", None)
        if meta:
            entry["_meta"] = meta
        out.append(entry)
    out.sort(key=lambda e: e["name"])
    return out


def summarise(tools: list[dict]) -> dict:
    """Facts about the baseline that a reader should not have to recompute.

    Reported, not enforced. If the deprecated count is high, that is a true statement about the
    surface being compared against, and hiding it would be the same error as tidying the catalog.
    """
    # Structural marks AND prose. Measured on this very catalog: `superseded_by` is the ONLY
    # retirement key present in `_meta` anywhere — there is no `deprecated_at` field in the whole
    # 315-tool surface — so most retirements are announced only in the description text. A
    # structural-only count reports 54; the real number is materially higher, and the gap is not a
    # reporting nicety: it is the reason a machine cannot currently tell a live tool from a dead one.
    def _retired(t: dict) -> bool:
        m = t.get("_meta")
        if isinstance(m, dict) and (
            m.get("deprecated") or m.get("deprecated_at") or m.get("superseded_by")
        ):
            return True
        return "deprecat" in (t.get("description") or "").lower()

    deprecated = [t["name"] for t in tools if _retired(t)]
    structural = [
        t["name"] for t in tools
        if isinstance(t.get("_meta"), dict) and (
            t["_meta"].get("deprecated") or t["_meta"].get("deprecated_at")
            or t["_meta"].get("superseded_by")
        )
    ]
    schema_bytes = sum(len(json.dumps(t, ensure_ascii=False)) for t in tools)
    return {
        "tool_count": len(tools),
        "deprecated_count": len(deprecated),
        "deprecated_structural_count": len(structural),
        "deprecated_prose_only_count": len(deprecated) - len(structural),
        "deprecated": sorted(deprecated),
        "total_schema_bytes": schema_bytes,
        "estimated_schema_tokens": schema_bytes // 4,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gateway", default=DEFAULT_GATEWAY)
    ap.add_argument("--user-id", default=os.environ.get("BASELINE_USER_ID"))
    ap.add_argument("--verify", action="store_true",
                    help="re-hash the committed snapshot and report drift; never writes")
    args = ap.parse_args()

    if args.verify:
        if not SNAPSHOT.exists():
            print(f"FAIL: no snapshot at {SNAPSHOT}", file=sys.stderr)
            return 2
        doc = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        recomputed = canonical_hash(doc["tools"])
        ok = recomputed == doc["catalog_sha256"]
        print(f"{'OK' if ok else 'FAIL'}: recorded={doc['catalog_sha256'][:16]} "
              f"recomputed={recomputed[:16]} tools={len(doc['tools'])}")
        return 0 if ok else 1

    tools = asyncio.run(fetch_catalog(args.gateway, args.user_id))
    if not tools:
        # Refuse to write an empty baseline. A zero-tool snapshot would silently become a control
        # group that the new runtime beats trivially — the most flattering possible bug.
        print("FAIL: gateway returned zero tools; refusing to freeze an empty baseline",
              file=sys.stderr)
        return 2

    doc = {
        "_comment": (
            "CP-0.5 — the FROZEN baseline catalog of the OLD runtime. The arms replay from this "
            "file, never from a live gateway: the arms' original catalog no longer exists, which "
            "is the defect this closes. Do not edit, tidy, or de-duplicate. Regenerating it is a "
            "new baseline, not a correction — a claim measured against a different control group "
            "is a different claim."
        ),
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "gateway": args.gateway,
        "user_overlay": bool(args.user_id),
        "catalog_sha256": canonical_hash(tools),
        "summary": summarise(tools),
        "tools": tools,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    s = doc["summary"]
    print(f"froze {s['tool_count']} tools ({s['deprecated_count']} deprecated, "
          f"~{s['estimated_schema_tokens']} schema tokens) -> {SNAPSHOT.relative_to(REPO)}")
    print(f"catalog_sha256 = {doc['catalog_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
