"""ext-tasks durable-gate WIRE — LIVE in-process MCP-session E2E (T1b).

Stands up a real FastMCP server with a KIND-C-style gate tool + the task endpoints,
connects a REAL MCP client session over in-memory streams, and drives the whole
durable-gate loop through genuine protocol routing:

    call gate tool → task handle (input_required)
      → tasks/get   (routes to our handler) → input_required + inputRequests
      → task_provide_input(accepted) → executor runs the real write → completed
      → tasks/get → completed + result

This is the live proof that the store + the FastMCP wire integration work end to
end over an actual client↔server session (not a mock).
"""
from __future__ import annotations

import json

import mcp.types as t
import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

from loreweave_mcp.tasks import InMemoryTaskStore
from loreweave_mcp.tasks_wire import (
    GATE_RESULT_TYPE,
    enable_task_results,
    open_gate,
    register_task_endpoints,
)


def _build_server(committed: list):
    """A FastMCP server with a gate tool whose executor records the committed write."""
    mcp = FastMCP("tasks-e2e", stateless_http=True)
    store = InMemoryTaskStore()
    register_task_endpoints(mcp, store)

    @mcp.tool(name="publish_book")
    async def publish_book(book_id: str) -> dict:
        async def _commit(inputs):
            committed.append({"book_id": book_id, "inputs": inputs})
            return {"published": True, "book_id": book_id}

        return await open_gate(
            store,
            descriptor="book.publish",
            executor=_commit,
            input_requests={"title": f"Publish book {book_id}?"},
        )

    return mcp


def _content_json(result) -> dict:
    """Pull the JSON object out of a CallToolResult — from structuredContent when
    present (a dict-returning FastMCP tool), else the text block. Robust to the
    kit's `patch_convert_result` global monkeypatch, which alters which form a
    tool result takes and can leak across tests in the full suite."""
    sc = getattr(result, "structuredContent", None)
    if isinstance(sc, dict):
        # FastMCP wraps a non-BaseModel return under a "result" key.
        return sc["result"] if set(sc.keys()) == {"result"} else sc
    return json.loads(result.content[0].text)


async def _get_task(session, task_id: str) -> t.GetTaskResult:
    return await session.send_request(
        t.ClientRequest(
            t.GetTaskRequest(method="tasks/get", params=t.GetTaskRequestParams(taskId=task_id))
        ),
        t.GetTaskResult,
    )


@pytest.mark.asyncio
async def test_durable_gate_full_loop():
    committed: list = []
    server = _build_server(committed)
    async with create_connected_server_and_client_session(server._mcp_server) as session:
        await session.initialize()

        # 1) call the gate tool → a durable task handle carrying the card payload,
        #    input_required, nothing written yet
        r = await session.call_tool("publish_book", {"book_id": "b-42"})
        handle = _content_json(r)
        assert handle["type"] == GATE_RESULT_TYPE
        task_id = handle["taskId"]
        assert handle["status"] == "input_required"
        assert handle["inputRequests"] == {"title": "Publish book b-42?"}  # card payload
        assert committed == []  # the gate is holding — no write

        # 2) tasks/get routes to our handler → input_required (the poll contract)
        got = await _get_task(session, task_id)
        assert got.status == "input_required"

        # 3) provide the human's accept → the real write runs → completed
        upd = _content_json(await session.call_tool(
            "task_provide_input", {"task_id": task_id, "accepted": True}))
        assert upd["status"] == "completed"
        assert upd["result"] == {"published": True, "book_id": "b-42"}
        assert committed == [{"book_id": "b-42", "inputs": {"accepted": True}}]

        # 4) tasks/get now terminal → completed (the result was delivered on the
        #    provide_input response above; a crash-resumed client re-polls to see
        #    this terminal status)
        done = await _get_task(session, task_id)
        assert done.status == "completed"


@pytest.mark.asyncio
async def test_gate_tool_emits_create_task_result():
    """With enable_task_results, a gate tool's tools/call response IS a wire
    CreateTaskResult (resultType:"task") a client auto-detects — no need to read
    the tool content to know it's a durable task."""
    committed: list = []
    mcp = FastMCP("tasks-e2e-ctr", stateless_http=True)
    store = InMemoryTaskStore()
    register_task_endpoints(mcp, store)

    @mcp.tool(name="publish_book")
    async def publish_book(book_id: str) -> dict:
        async def _commit(inputs):
            committed.append(book_id)
            return {"published": True}

        return await open_gate(store, descriptor="book.publish", executor=_commit,
                               input_requests={"title": f"Publish {book_id}?"})

    enable_task_results(mcp, store)  # AFTER the tools are registered

    async with create_connected_server_and_client_session(mcp._mcp_server) as session:
        await session.initialize()
        res = await session.send_request(
            t.ClientRequest(
                t.CallToolRequest(
                    method="tools/call",
                    params=t.CallToolRequestParams(name="publish_book",
                                                   arguments={"book_id": "b-7"}),
                )
            ),
            t.CreateTaskResult,
        )
        assert res.task.status == "input_required"
        assert res.task.taskId.startswith("task_")
        assert committed == []  # the gate holds — nothing written on create


@pytest.mark.asyncio
async def test_decline_does_not_write():
    committed: list = []
    server = _build_server(committed)
    async with create_connected_server_and_client_session(server._mcp_server) as session:
        await session.initialize()
        handle = _content_json(await session.call_tool("publish_book", {"book_id": "b-9"}))
        task_id = handle["taskId"]
        upd = _content_json(await session.call_tool(
            "task_provide_input", {"task_id": task_id, "accepted": False}))
        assert upd["status"] == "cancelled"
        assert committed == []  # declined → no write
        got = await _get_task(session, task_id)
        assert got.status == "cancelled"
