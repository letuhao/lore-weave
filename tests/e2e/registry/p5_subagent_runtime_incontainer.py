"""E2E-P5-A (in-container) — prove the subagent RUNTIME runs a REAL nested LLM turn
through the real provider chain (chat-service → provider-registry → lm_studio),
deterministically (no dependence on a top model choosing to delegate).

Run inside the chat-service container:
  docker exec infra-chat-service-1 python /app/p5_incontainer.py <MODEL_REF> <USER_ID>
"""
import asyncio
import sys

from app.services.stream_service import _run_subagent_call
from app.client.knowledge_client import get_knowledge_client

MODEL_REF = sys.argv[1]
USER_ID = sys.argv[2]


async def main() -> int:
    defs = {
        "scout": {
            "name": "scout",
            "system_prompt": "You are a terse lore assistant. Answer in ONE short sentence.",
            "tool_scope": [],          # text-only sub-run (valid)
            "model_ref": "",
            "tier": "user",
        }
    }
    payload, sin, sout = await _run_subagent_call(
        args={"subagent": "scout", "task": "In one sentence, what is a mimic in fantasy fiction?"},
        subagent_defs=defs,
        full_catalog=[],
        model_source="user_model",
        model_ref=MODEL_REF,
        user_id=USER_ID,
        gen_params={"max_tokens": 200},
        knowledge_client=get_knowledge_client(),
        session_id="e2e-p5a",
        project_id=None,
        caller_max_iterations=4,
        decision_check=None,   # Track C WS-3 renamed approval_check -> decision_check
        hooks=None,
        effective_limit=None,
        subagent_depth=0,
    )
    print("SUBAGENT :", payload.get("subagent"))
    print("RESULT   :", repr(payload.get("result"))[:400])
    print("TOOLS    :", payload.get("tools_used"))
    print("TOKENS   : in=%s out=%s" % (sin, sout))

    ok = True
    if payload.get("error"):
        print("XFAIL error:", payload["error"]); ok = False
    if not payload.get("result"):
        print("XFAIL empty synthesized result"); ok = False
    if not (sin > 0 and sout > 0):
        print("XFAIL no real tokens (nested LLM turn didn't run)"); ok = False
    print("PART-A-PASS" if ok else "PART-A-FAIL")
    return 0 if ok else 1


sys.exit(asyncio.run(main()))
