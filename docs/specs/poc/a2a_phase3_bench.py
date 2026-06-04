"""A2A phase-3 design benchmark — does the proposed adapter actually work?

Run (needs fastapi + httpx, both already in chat-service):
    docker run --rm -v "$PWD/docs/specs/poc/a2a_phase3_bench.py:/bench.py" \
        infra-chat-service:latest python /bench.py
Companion analysis: ../2026-06-03-a2a-phase3-protocol-analysis.md (§11).
Result on 2026-06-03: 7/7 scenarios passed.

Implements the A2A wire spec (Agent Card + JSON-RPC message/send, message/stream
SSE, tasks/get + task lifecycle + artifacts) as the adapter the design proposes,
then runs scenarios in-process via httpx ASGITransport (deterministic). Agent
logic is deterministic on purpose — the benchmark validates the A2A PLUMBING /
DESIGN MAPPINGS (chat-turn↔Task, C6 suspend↔input-required, AG-UI↔status/artifact
events, multi-agent delegation, auth scoping), not model quality (the model call
plugs into the executor and was validated separately).
"""
import asyncio, json, time, uuid
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
import httpx
from httpx import ASGITransport

TOKEN = "dev_internal_token"

# ---------- A2A wire helpers ----------
def tpart(t): return {"text": t, "mediaType": "text/plain"}
def artifact(parts, name): return {"artifactId": str(uuid.uuid4()), "name": name, "parts": parts}
def jrpc_ok(rid, result): return {"jsonrpc": "2.0", "id": rid, "result": result}
def jrpc_err(rid, code, msg): return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": msg}}

# ---------- generic A2A server (the adapter) ----------
def build_a2a_agent(*, name, description, skills, executor, base_url):
    app = FastAPI()
    tasks: dict[str, dict] = {}

    card = {
        "name": name, "description": description, "version": "1.0.0",
        "preferredTransport": "JSONRPC",
        "interfaces": [{"type": "json-rpc", "url": f"{base_url}/a2a"}],
        "capabilities": {"streaming": True, "pushNotifications": False},
        "skills": skills,
        "securitySchemes": {"internal": {"type": "apiKey", "in": "header", "name": "X-Internal-Token"}},
        "security": [{"internal": []}],
        "defaultInputModes": ["text/plain"], "defaultOutputModes": ["text/plain"],
    }

    @app.get("/.well-known/agent-card.json")
    async def agent_card():
        return JSONResponse(card)

    def _auth(req: Request) -> bool:
        return req.headers.get("x-internal-token") == TOKEN

    def _new_or_get_task(params):
        m = params["message"]
        tid = m.get("taskId") or params.get("taskId")
        if tid and tid in tasks:
            return tasks[tid], False
        tid = str(uuid.uuid4())
        cid = m.get("contextId") or str(uuid.uuid4())
        t = {"id": tid, "contextId": cid, "status": {"state": "submitted"},
             "artifacts": [], "history": [], "ownerToken": None}
        tasks[tid] = t
        return t, True

    @app.post("/a2a")
    async def rpc(req: Request):
        if not _auth(req):
            return JSONResponse(jrpc_err(None, -32001, "unauthorized"), status_code=401)
        body = await req.json()
        method, params, rid = body.get("method"), body.get("params", {}), body.get("id")
        owner = req.headers.get("x-user-id")

        if method == "tasks/get":
            t = tasks.get(params.get("id"))
            if not t: return JSONResponse(jrpc_err(rid, -32004, "TaskNotFound"), status_code=404)
            if t.get("ownerToken") not in (None, owner):  # auth scoping
                return JSONResponse(jrpc_err(rid, -32001, "forbidden"), status_code=403)
            return JSONResponse(jrpc_ok(rid, t))

        if method in ("message/send", "message/stream"):
            task, is_new = _new_or_get_task(params)
            if is_new: task["ownerToken"] = owner
            user_text = " ".join(p.get("text", "") for p in params["message"]["parts"])
            task["history"].append({"role": "ROLE_USER", "parts": params["message"]["parts"]})
            agen = executor(user_text, task, deps={"owner": owner})

            if method == "message/send":
                async for ev in agen:  # drain to terminal/interrupt
                    _apply(task, ev)
                return JSONResponse(jrpc_ok(rid, task))

            async def sse():
                # initial Task snapshot, then ordered events (A2A streaming)
                yield f"data: {json.dumps({'kind':'task','task':_summ(task)})}\n\n"
                async for ev in agen:
                    _apply(task, ev)
                    yield f"data: {json.dumps(ev)}\n\n"
            return StreamingResponse(sse(), media_type="text/event-stream")

        return JSONResponse(jrpc_err(rid, -32601, "method not found"), status_code=404)

    return app, tasks


def _apply(task, ev):
    if ev["kind"] == "status":
        task["status"] = {"state": ev["state"], "ts": ev.get("ts")}
    elif ev["kind"] == "artifact":
        task["artifacts"].append(ev["artifact"])

def _summ(task):
    return {"id": task["id"], "contextId": task["contextId"], "state": task["status"]["state"]}


# ---------- LoreWeave-shaped agent executors (deterministic) ----------
async def composer_exec(user_text, task, deps):
    """compose_prose / a chat turn → Task with one prose Artifact."""
    yield {"kind": "status", "state": "working"}
    await asyncio.sleep(0)  # where a real model.stream() would run
    prose = f"[prose for: {user_text!r}]"
    yield {"kind": "artifact", "artifact": artifact([tpart(prose)], "draft")}
    yield {"kind": "status", "state": "completed"}

async def approval_exec(user_text, task, deps):
    """C6 human-in-loop: working → input-required (pause); resume → completed."""
    if task["status"]["state"] == "input-required":
        # resume: the new message is the human's apply/dismiss decision
        decision = user_text
        yield {"kind": "status", "state": "working"}
        yield {"kind": "artifact", "artifact": artifact([tpart(f"applied: {decision}")], "result")}
        yield {"kind": "status", "state": "completed"}
        return
    yield {"kind": "status", "state": "working"}
    yield {"kind": "artifact", "artifact": artifact([tpart(f"PROPOSAL: edit for {user_text!r}")], "proposal")}
    yield {"kind": "status", "state": "input-required"}  # pause for human

def make_director_exec(composer_client):
    async def director_exec(user_text, task, deps):
        """Multi-agent: Director delegates to the Composer agent via A2A."""
        yield {"kind": "status", "state": "working"}
        # A2A client call to the composer (peer agent)
        r = await composer_client.post("/a2a", json={
            "jsonrpc": "2.0", "id": "d1", "method": "message/send",
            "params": {"message": {"messageId": str(uuid.uuid4()), "role": "ROLE_USER",
                                   "parts": [tpart(user_text)]}},
        }, headers={"X-Internal-Token": TOKEN, "X-User-Id": deps["owner"] or ""})
        sub = r.json()["result"]
        prose = sub["artifacts"][0]["parts"][0]["text"]
        yield {"kind": "artifact", "artifact": artifact(
            [tpart(f"director wrapped → {prose}")], "final",
        )}
        yield {"kind": "status", "state": "completed"}
    return director_exec


# ---------- scenarios ----------
async def main():
    results = []
    def rec(name, ok, note=""):
        results.append((name, ok, note))

    # composer server
    comp_app, comp_tasks = build_a2a_agent(
        name="composer", description="writes prose",
        skills=[{"id": "compose", "name": "Compose prose", "description": "draft/rewrite"}],
        executor=composer_exec, base_url="http://composer")
    comp_client = httpx.AsyncClient(transport=ASGITransport(app=comp_app), base_url="http://composer")

    # approval server (C6)
    appr_app, _ = build_a2a_agent(
        name="approver", description="human-in-loop edits",
        skills=[{"id": "propose", "name": "Propose edit", "description": "needs approval"}],
        executor=approval_exec, base_url="http://approver")
    appr_client = httpx.AsyncClient(transport=ASGITransport(app=appr_app), base_url="http://approver")

    # director server (delegates to composer)
    dir_app, _ = build_a2a_agent(
        name="director", description="orchestrates agents",
        skills=[{"id": "orchestrate", "name": "Orchestrate", "description": "delegate"}],
        executor=make_director_exec(comp_client), base_url="http://director")
    dir_client = httpx.AsyncClient(transport=ASGITransport(app=dir_app), base_url="http://director")

    H = {"X-Internal-Token": TOKEN, "X-User-Id": "user-1"}
    def send(client, text, **extra):
        return client.post("/a2a", json={"jsonrpc": "2.0", "id": "1", "method": "message/send",
            "params": {"message": {"messageId": str(uuid.uuid4()), "role": "ROLE_USER",
                       "parts": [tpart(text)], **extra}}}, headers=H)

    # 1) Discovery
    t0 = time.perf_counter()
    c = (await comp_client.get("/.well-known/agent-card.json")).json()
    ok = (c["name"] == "composer" and c["capabilities"]["streaming"] is True
          and c["skills"][0]["id"] == "compose" and "internal" in c["securitySchemes"])
    rec("1. Discovery (Agent Card)", ok, f"skills={[s['id'] for s in c['skills']]} transport={c['interfaces'][0]['type']}")

    # 2) Simple task (message/send) → completed + artifact  [maps a chat turn]
    r = (await send(comp_client, "rain over the city")).json()["result"]
    ok = r["status"]["state"] == "completed" and r["artifacts"][0]["parts"][0]["text"].startswith("[prose")
    rec("2. Simple task → Task+Artifact", ok, f"state={r['status']['state']} artifact={r['artifacts'][0]['name']}")

    # 3) Streaming (message/stream) → ordered SSE status/artifact events  [maps AG-UI deltas]
    events = []
    async with comp_client.stream("POST", "/a2a", json={"jsonrpc":"2.0","id":"1","method":"message/stream",
        "params":{"message":{"messageId":str(uuid.uuid4()),"role":"ROLE_USER","parts":[tpart("storm")]}}},
        headers=H) as resp:
        async for line in resp.aiter_lines():
            if line.startswith("data: "): events.append(json.loads(line[6:]))
    kinds = [e.get("kind") for e in events]
    states = [e.get("state") for e in events if e.get("kind") == "status"]
    ok = kinds[0] == "task" and "artifact" in kinds and states[-1] == "completed" and "working" in states
    rec("3. Streaming SSE (status→artifact→completed)", ok, f"events={kinds}")

    # 4) input-required round-trip  [maps C6 suspend → resume]
    r1 = (await send(appr_client, "make it vivid")).json()["result"]
    paused = r1["status"]["state"] == "input-required" and r1["artifacts"][0]["name"] == "proposal"
    tid = r1["id"]
    # resume: send the human decision to the SAME task
    r2 = (await send(appr_client, "applied", taskId=tid)).json()["result"]
    resumed = r2["id"] == tid and r2["status"]["state"] == "completed" and "applied" in r2["artifacts"][-1]["parts"][0]["text"]
    rec("4. Human-in-loop (input-required→resume)", paused and resumed,
        f"pause={r1['status']['state']} resume={r2['status']['state']} sameTask={r2['id']==tid}")

    # 5) Multi-agent delegation: Director → Composer  [maps game mesh]
    n_before = len(comp_tasks)
    r = (await send(dir_client, "open the chapter")).json()["result"]
    delegated = len(comp_tasks) == n_before + 1  # composer got a task
    ok = r["status"]["state"] == "completed" and r["artifacts"][0]["parts"][0]["text"].startswith("director wrapped") and delegated
    rec("5. Multi-agent delegation (A2A→A2A)", ok, f"composerTasks+={len(comp_tasks)-n_before} final={r['artifacts'][0]['name']}")

    # 6) Auth scoping
    r_noauth = await comp_client.post("/a2a", json={"jsonrpc":"2.0","id":"1","method":"tasks/get","params":{"id":"x"}},
                                      headers={"X-User-Id":"user-1"})
    r_crosstenant = await comp_client.get("/.well-known/agent-card.json")  # card is public (ok)
    # cross-tenant task read: task owned by user-1, read as user-2
    own = (await send(comp_client, "mine")).json()["result"]["id"]
    cross = await comp_client.post("/a2a", json={"jsonrpc":"2.0","id":"1","method":"tasks/get","params":{"id":own}},
                                   headers={"X-Internal-Token":TOKEN,"X-User-Id":"user-2"})
    ok = r_noauth.status_code == 401 and cross.status_code == 403
    rec("6. Auth (401 no-token, 403 cross-tenant)", ok, f"noToken={r_noauth.status_code} crossTenant={cross.status_code}")

    # 7) tasks/get round-trip
    own2 = (await send(comp_client, "fetch me")).json()["result"]["id"]
    g = (await comp_client.post("/a2a", json={"jsonrpc":"2.0","id":"1","method":"tasks/get","params":{"id":own2}}, headers=H)).json()["result"]
    rec("7. tasks/get retrieval", g["id"] == own2 and g["status"]["state"] == "completed", f"state={g['status']['state']}")

    for cl in (comp_client, appr_client, dir_client): await cl.aclose()

    # ---------- report ----------
    print("\n================ A2A PHASE-3 DESIGN BENCHMARK ================")
    passed = sum(1 for _, ok, _ in results if ok)
    for name, ok, note in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:<46} {note}")
    print(f"  ----------------------------------------------------------")
    print(f"  {passed}/{len(results)} scenarios passed")
    print("=============================================================")

asyncio.run(main())
