"""Agent-driven Dracula MCP scenario on a FRESH book (run inside the docker net).

Drives the journey through the gateway MCP surface (the ASSISTANT), confirming the
propose->confirm steps via each domain's confirm route with a minted user JWT. State
persists to /app/scenario_state.json so the run is resumable phase-by-phase.

Phases here: 1 create book · 2 suggest+approve ontology · 3 import chapter ·
4 extract glossary · 5 translate glossary+chapter to vi. KG/wiki/enrich/write are
driven by the companion script (phase 6+).
"""
import asyncio
import json
import os
import time

import httpx
import jwt
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

TOKEN = os.environ["INTERNAL_SERVICE_TOKEN"]
SECRET = os.environ["JWT_SECRET"]
USER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
GEN = "51ea9fd7-4a25-4801-af67-d88c2d161dac"   # gemma (chat/extract/gen)
GW = "http://ai-gateway:8210/mcp"
H = {"X-Internal-Token": TOKEN, "X-User-Id": USER, "X-Session-Id": "scenario"}
STATE = "/app/scenario_state.json"
BOOK_SVC = "http://book-service:8082"
GLOSS_SVC = "http://glossary-service:8088"
XLATE_SVC = "http://translation-service:8087"


def bearer():
    now = int(time.time())
    return jwt.encode({"sub": USER, "iat": now, "exp": now + 3600}, SECRET, algorithm="HS256")


def load():
    try:
        with open(STATE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save(st):
    with open(STATE, "w") as f:
        json.dump(st, f, indent=1)


def _p(res):
    if getattr(res, "isError", False):
        raise RuntimeError(f"tool error: {res.content[0].text if res.content else '?'}")
    return json.loads(res.content[0].text)


async def confirm(domain, token):
    """Redeem a confirm token via <domain>/actions/confirm (Bearer JWT + body)."""
    base = {"glossary": GLOSS_SVC, "translation": XLATE_SVC}[domain]
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(f"{base}/v1/{domain}/actions/confirm",
                         headers={"Authorization": f"Bearer {bearer()}"},
                         json={"confirm_token": token})
    return r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text)


async def poll_job(session, job_id, label, tries=60, delay=10):
    for i in range(tries):
        res = await session.call_tool("translation_job_status", {"job_id": job_id})
        if getattr(res, "isError", False):
            print(f"  [{label}] {i}: status-tool error: {res.content[0].text[:80]}")
            return {"status": "unknown", "error": res.content[0].text}
        st = json.loads(res.content[0].text)
        status = st.get("status") or st.get("state")
        print(f"  [{label}] {i}: {status}")
        if status in ("completed", "succeeded", "failed", "cancelled", "completed_with_errors", "error"):
            return st
        await asyncio.sleep(delay)
    return {"status": "timeout"}


async def main():
    st = load()
    async with streamablehttp_client(GW, headers=H) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()

            # ── Phase 1 — create the book ────────────────────────────────────
            if not st.get("book_id"):
                print("== Phase 1: create book ==")
                res = _p(await s.call_tool("book_create", {
                    "title": "Dracula (MCP scenario)", "original_language": "en",
                    "description": "Agent-driven journey test", "genre_tags": ["gothic", "horror"],
                }))
                st["book_id"] = res.get("book_id") or res.get("id")
                save(st)
            book = st["book_id"]
            print("book_id:", book)

            # ── Phase 2 — agent suggests + approves a book-native ontology ────
            if not st.get("ontology_done"):
                print("== Phase 2: ontology ==")
                # web research (best-effort; may be unconfigured locally)
                try:
                    wr = await s.call_tool("glossary_web_search", {"query": "Bram Stoker Dracula main characters and vampire lore"})
                    print("  web_search:", ("ok" if not getattr(wr, "isError", False) else _p_err(wr)))
                except Exception as e:
                    print("  web_search skipped:", e)
                # Adopt the baseline ontology (the user's "approve the 12 defaults" step;
                # custom kinds below require an adopted book ontology). REST (no MCP
                # adopt tool for the glossary defaults; Manage-tier book setup).
                DEFAULT_KINDS = ["character", "location", "item", "event", "terminology",
                                 "power_system", "organization", "species", "relationship",
                                 "plot_arc", "trope", "social_setting"]
                async with httpx.AsyncClient(timeout=60) as c:
                    ar = await c.post(f"{GLOSS_SVC}/v1/glossary/books/{book}/adopt",
                                      headers={"Authorization": f"Bearer {bearer()}"},
                                      json={"genres": ["universal"], "kinds": DEFAULT_KINDS})
                print("  adopt baseline ontology:", ar.status_code)
                kinds = [
                    {"code": "vampire", "name": "Vampire", "description": "An undead being that feeds on blood.",
                     "attributes": [
                         {"code": "powers", "name": "Powers", "description": "Supernatural abilities (shapeshifting, hypnosis, strength)."},
                         {"code": "weaknesses", "name": "Weaknesses", "description": "Vulnerabilities (garlic, crucifix, sunlight, stake)."}]},
                    {"code": "hunter", "name": "Hunter", "description": "One who hunts vampires.",
                     "attributes": [
                         {"code": "methods", "name": "Methods", "description": "Techniques and tools used to hunt vampires."},
                         {"code": "allegiance", "name": "Allegiance", "description": "Who the hunter serves or allies with."}]},
                ]
                approved = []
                for k in kinds:
                    pr = _p(await s.call_tool("glossary_propose_new_kind", {"book_id": book, **k}))
                    tok = pr.get("confirm_token")
                    if not tok:
                        print("  propose returned no token:", pr); continue
                    code, body = await confirm("glossary", tok)
                    print(f"  approve {k['code']}: {code}")
                    approved.append(k["code"])
                st["ontology_done"] = True
                st["kinds"] = approved
                save(st)

            # ── Phase 3 — import a chapter ───────────────────────────────────
            if not st.get("chapter_ids"):
                print("== Phase 3: import chapter ==")
                with open("/app/dracula-ch01.txt", encoding="utf-8") as f:
                    text = f.read()
                res = _p(await s.call_tool("book_chapter_bulk_create", {
                    "book_id": book, "original_language": "en",
                    "chapters": [{"title": "Chapter I — Jonathan Harker's Journal",
                                  "original_filename": "dracula-ch01.txt", "content": text}],
                }))
                print("  bulk_create:", json.dumps(res)[:300])
                # extract chapter ids from the response shape
                ids = res.get("chapter_ids") or [c.get("chapter_id") or c.get("id") for c in (res.get("chapters") or res.get("created") or [])]
                ids = [i for i in ids if i]
                st["chapter_ids"] = ids
                save(st)
            chapters = st["chapter_ids"]
            print("chapter_ids:", chapters)

            # publish the chapters (extraction reads published content)
            if not st.get("published"):
                for cid in chapters:
                    pr = await s.call_tool("book_chapter_publish", {"book_id": book, "chapter_id": cid})
                    print("  publish", cid, "->", "ok" if not getattr(pr, "isError", False) else _p_err(pr))
                st["published"] = True
                save(st)

            # ── Phase 4 — extract glossary (agent) ───────────────────────────
            if not st.get("extract_job"):
                print("== Phase 4: extract glossary ==")
                pr = _p(await s.call_tool("translation_start_extraction", {
                    "book_id": book, "chapter_ids": chapters,
                    "extraction_profile": {}, "model_ref": GEN,
                }))
                print("  extraction propose:", json.dumps(pr)[:240])
                tok = pr.get("confirm_token")
                if tok:
                    code, body = await confirm("translation", tok)
                    print("  extraction confirm:", code, json.dumps(body)[:240])
                    st["extract_job"] = (body or {}).get("job_id") if isinstance(body, dict) else None
                else:
                    st["extract_job"] = pr.get("job_id")
                save(st)
            if st.get("extract_job") and not st.get("extracted_count"):
                print("  polling glossary entity-count for", book)
                cnt = 0
                for i in range(60):
                    async with httpx.AsyncClient(timeout=30) as c:
                        rr = await c.get(f"{GLOSS_SVC}/internal/books/{book}/entity-count",
                                         headers={"X-Internal-Token": TOKEN})
                    cnt = (rr.json() or {}).get("count", 0) if rr.status_code == 200 else 0
                    print(f"  [extract] {i}: entities={cnt}")
                    if cnt > 0:
                        st["extracted_count"] = cnt; save(st); break
                    await asyncio.sleep(10)
                print("  extraction entities:", cnt)

            # ── Phase 5 — translate glossary + chapter to vi ─────────────────
            if not st.get("translate_job"):
                print("== Phase 5: translate to vi ==")
                pr = _p(await s.call_tool("translation_start_job", {
                    "book_id": book, "chapter_ids": chapters, "target_language": "vi",
                }))
                print("  translate start:", json.dumps(pr)[:240])
                tok = pr.get("confirm_token")
                if tok:
                    code, body = await confirm("translation", tok)
                    print("  translate confirm:", code, json.dumps(body)[:200])
                    st["translate_job"] = (body or {}).get("job_id") if isinstance(body, dict) else None
                else:
                    st["translate_job"] = pr.get("job_id")
                save(st)
            if st.get("translate_job"):
                res = await poll_job(s, st["translate_job"], "translate")
                print("  translate:", res.get("status"))

    print("PHASES 1-5 DONE. state:", json.dumps(load()))


def _p_err(res):
    return res.content[0].text if getattr(res, "content", None) else "?"


asyncio.run(main())
