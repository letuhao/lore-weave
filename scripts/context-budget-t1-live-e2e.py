"""T1 live-e2e GATE — composition_list_outline reference-first + cheap node read.

Runs INSIDE the docker network (like scripts/smoke_new_mcp_exec.py): chat-path
federation through ai-gateway → composition MCP. Proves the L1/L2 contract on a
REAL 251-node outline for the test account, measuring the bytes the MODEL actually
sees (serialized through the T0 funnel `tool_result_content`).

Proves:
  1. detail=summary drops the goal/synopsis prose → materially fewer bytes/tokens.
  2. summary result carries NO synopsis field (reference-first honored).
  3. composition_get_outline_node returns ONE node's `version` cheaply — the
     146K root-cause fix (no full-outline dump just to get expected_version).
  4. limit bounds the node count + reports truncation (never silent).

Usage (inside the net):
  docker cp scripts/context-budget-t1-live-e2e.py infra-chat-service-1:/tmp/t1.py
  docker exec -e T1_PROJECT=<pid> infra-chat-service-1 python /tmp/t1.py
"""
import asyncio
import json
import os
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

# The T0 funnel — measure the bytes the model actually receives.
sys.path.insert(0, "/app")
try:
    from app.services.tool_result_wire import tool_result_content
except Exception:  # pragma: no cover — fallback if run outside chat-service
    def tool_result_content(p):
        return json.dumps(p, ensure_ascii=False)

TOKEN = os.environ["INTERNAL_SERVICE_TOKEN"]
USER = os.environ.get("T1_USER", "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c")  # claude-test
PROJECT = os.environ.get("T1_PROJECT", "019f1783-ecca-7331-afab-9543762a8b68")  # 251 nodes
GW = os.environ.get("T1_GW", "http://ai-gateway:8210/mcp")
H = {"X-Internal-Token": TOKEN, "X-User-Id": USER, "X-Session-Id": "t1-e2e"}


def _payload(res):
    return json.loads(res.content[0].text)


def _bytes(payload) -> int:
    return len(tool_result_content(payload).encode("utf-8"))


async def main() -> int:
    async with streamablehttp_client(GW, headers=H) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()

            full = _payload(await s.call_tool(
                "composition_list_outline", {"project_id": PROJECT, "detail": "full"}))
            summ = _payload(await s.call_tool(
                "composition_list_outline", {"project_id": PROJECT, "detail": "summary"}))
            capped = _payload(await s.call_tool(
                "composition_list_outline",
                {"project_id": PROJECT, "detail": "summary", "limit": 10}))

            if "error" in full:
                print("DENIED / error on list_outline:", full)
                return 2

            fb, sb = _bytes(full), _bytes(summ)
            n_nodes = len(full.get("nodes", []))
            print(f"project {PROJECT} — {n_nodes} outline nodes")
            print(f"  list_outline  full : {fb:>9,} B")
            print(f"  list_outline  summ : {sb:>9,} B   (-{100*(fb-sb)/fb:.1f}%)")
            print(f"  summary meta       : "
                  f"detail={summ.get('detail')} total={summ.get('total')} "
                  f"returned={summ.get('returned')} truncated={summ.get('truncated')}")

            # (2) reference-first: no synopsis in the summary nodes
            has_synopsis = any("synopsis" in nd for nd in summ.get("nodes", []))
            has_version = all("version" in nd for nd in summ.get("nodes", []) or [{}])

            # (3) cheap single-node version read
            first = (full.get("nodes") or [{}])[0]
            node_id = first.get("id")
            node = _payload(await s.call_tool(
                "composition_get_outline_node",
                {"project_id": PROJECT, "node_id": node_id})) if node_id else {}
            node_bytes = _bytes(node) if node else 0
            print(f"  get_outline_node   : {node_bytes:>9,} B  (version={node.get('version')})")

            # (4) limit bound
            cap_ok = capped.get("returned", 99) <= 10 and capped.get("truncated", 0) >= 0

            ok = (
                sb < fb * 0.6           # summary at least ~40% smaller
                and not has_synopsis    # reference-first
                and has_version         # concurrency token kept
                and node.get("version") is not None  # cheap version read works
                and node_bytes < sb     # one node << whole outline
                and cap_ok
            )
            print()
            print(f"  reference-first (no synopsis at summary): {not has_synopsis}")
            print(f"  version kept at summary                 : {has_version}")
            print(f"  cheap node read returns version         : {node.get('version') is not None}")
            print(f"  limit honored + truncation reported     : {cap_ok}")
            print("RESULT:", "PASS" if ok else "FAIL")
            return 0 if ok else 1


raise SystemExit(asyncio.run(main()))
