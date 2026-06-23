"""Fresh agent-driven Dracula journey (phases 1-5) THROUGH THE GATEWAY.

Runs inside the docker net (e.g. infra-knowledge-service-1). Drives the journey via
the assistant's MCP surface with the test user's envelope — the same tool-calls the FE
chat agent makes. The Dracula Ch.1 text is FETCHED from Project Gutenberg #345 at
runtime (never embedded), then sliced to a tractable size for local-model steps.

Phases: 1 create book · 2 web-search + suggest+approve ontology · 3 import chapter ·
4 extract glossary · 5 translate glossary+chapter to vi. (KG/wiki/enrich/write = phase 6+.)
State persists to /app/scenario_state.json (resumable).
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
H = {"X-Internal-Token": TOKEN, "X-User-Id": USER, "X-Session-Id": "fresh-journey"}
STATE = "/app/scenario_state.json"
GLOSS_SVC = "http://glossary-service:8088"
XLATE_SVC = "http://translation-service:8087"
BOOK_SVC = "http://book-service:8082"

GUTENBERG = "https://www.gutenberg.org/cache/epub/345/pg345.txt"
_FALLBACK = (
    "3 May. Bistritz.—Left Munich at 8:35 P.M., arriving at Vienna early next "
    "morning. Jonathan Harker travelled east toward the Borgo Pass, into the wild "
    "Carpathian mountains of Transylvania, to meet the mysterious Count Dracula at "
    "his crumbling castle. The local peasants crossed themselves and pressed a "
    "crucifix upon him, whispering of the vampire that haunted the land."
)


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


def _err(res):
    return res.content[0].text if getattr(res, "content", None) else "?"


def fetch_chapter1() -> str:
    """Prefer a host-injected /app/dracula-ch01.txt (real Gutenberg text, fetched on the
    host where there IS egress); else fetch directly; else a short ORIGINAL placeholder."""
    try:
        with open("/app/dracula-ch01.txt", encoding="utf-8") as f:
            t = f.read().strip()
        if len(t) > 500:
            return t[:6000]
    except FileNotFoundError:
        pass
    try:
        r = httpx.get(GUTENBERG, timeout=60, follow_redirects=True)
        r.raise_for_status()
        text = r.text
        start = text.find("Left Munich at")
        if start == -1:
            return _FALLBACK
        s2 = text.rfind("3 May", 0, start)
        if s2 != -1:
            start = s2
        end = text.find("CHAPTER II", start)
        chapter = text[start:end if end != -1 else start + 8000].strip()
        # Cap to keep local-model extraction/translation tractable (still rich in entities).
        return chapter[:6000]
    except Exception as e:  # noqa: BLE001
        print("  gutenberg fetch failed, using fallback:", e)
        return _FALLBACK


async def confirm(domain, token):
    base = {"glossary": GLOSS_SVC, "translation": XLATE_SVC, "book": BOOK_SVC}[domain]
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(f"{base}/v1/{domain}/actions/confirm",
                         headers={"Authorization": f"Bearer {bearer()}"},
                         json={"confirm_token": token})
    ct = r.headers.get("content-type", "")
    return r.status_code, (r.json() if ct.startswith("application/json") else r.text)


async def poll_job(session, job_id, label, tries=90, delay=10):
    for i in range(tries):
        res = await session.call_tool("translation_job_status", {"job_id": job_id})
        if getattr(res, "isError", False):
            print(f"  [{label}] {i}: status-tool error: {_err(res)[:80]}")
            return {"status": "unknown"}
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

            # ── Phase 1 — create the book ─────────────────────────────────────
            if not st.get("book_id"):
                print("== Phase 1: create book ==")
                res = _p(await s.call_tool("book_create", {
                    "title": "Dracula (fresh agent journey)", "original_language": "en",
                    "description": "Agent-driven end-to-end journey", "genre_tags": ["gothic", "horror"],
                }))
                st["book_id"] = res.get("book_id") or res.get("id")
                save(st)
            book = st["book_id"]
            print("book_id:", book)

            # ── Phase 2 — web research + suggest + approve a book-native ontology
            if not st.get("ontology_done"):
                print("== Phase 2: ontology (web search + suggest + approve) ==")
                try:
                    wr = await s.call_tool("glossary_web_search",
                                           {"query": "Bram Stoker Dracula characters and vampire lore"})
                    print("  web_search:", "ok" if not getattr(wr, "isError", False) else _err(wr)[:100])
                except Exception as e:  # noqa: BLE001
                    print("  web_search skipped:", e)
                DEFAULT_KINDS = ["character", "location", "item", "event", "terminology",
                                 "power_system", "organization", "species", "relationship",
                                 "plot_arc", "trope", "social_setting"]
                async with httpx.AsyncClient(timeout=60) as c:
                    ar = await c.post(f"{GLOSS_SVC}/v1/glossary/books/{book}/adopt",
                                      headers={"Authorization": f"Bearer {bearer()}"},
                                      json={"genres": ["universal"], "kinds": DEFAULT_KINDS})
                print("  adopt baseline ontology:", ar.status_code)
                # A kind is proposed without attributes; each attribute is its OWN
                # propose->confirm (glossary_propose_new_attribute, keyed by kind_code).
                kinds = [
                    {"code": "vampire", "name": "Vampire",
                     "description": "An undead being that feeds on blood.",
                     "attributes": [
                         {"code": "powers", "name": "Powers", "field_type": "textarea",
                          "description": "Supernatural abilities."},
                         {"code": "weaknesses", "name": "Weaknesses", "field_type": "textarea",
                          "description": "Vulnerabilities (garlic, sunlight, stake)."}]},
                    {"code": "hunter", "name": "Hunter", "description": "One who hunts vampires.",
                     "attributes": [
                         {"code": "methods", "name": "Methods", "field_type": "textarea",
                          "description": "Techniques used to hunt vampires."},
                         {"code": "allegiance", "name": "Allegiance", "field_type": "text",
                          "description": "Who the hunter serves."}]},
                ]
                approved = []
                for k in kinds:
                    attrs = k["attributes"]
                    pr = _p(await s.call_tool("glossary_propose_new_kind", {
                        "book_id": book, "code": k["code"], "name": k["name"],
                        "description": k["description"]}))
                    tok = pr.get("confirm_token")
                    if not tok:
                        print("  propose kind no token:", json.dumps(pr)[:200]); continue
                    code, _b = await confirm("glossary", tok)
                    print(f"  approve kind '{k['code']}': {code}")
                    for a in attrs:
                        ap = _p(await s.call_tool("glossary_propose_new_attribute", {
                            "book_id": book, "kind_code": k["code"], **a}))
                        atok = ap.get("confirm_token")
                        if atok:
                            ac, _ab = await confirm("glossary", atok)
                            print(f"    approve attr '{k['code']}.{a['code']}': {ac}")
                    approved.append(k["code"])
                st["ontology_done"] = True
                st["kinds"] = approved
                save(st)

            # ── Phase 3 — import a chapter (fetched from Gutenberg) ────────────
            if not st.get("chapter_ids"):
                print("== Phase 3: import chapter (fetch Gutenberg #345) ==")
                text = fetch_chapter1()
                print(f"  chapter text: {len(text)} chars; head: {text[:80]!r}")
                res = _p(await s.call_tool("book_chapter_bulk_create", {
                    "book_id": book, "original_language": "en",
                    "chapters": [{"title": "Chapter I — Jonathan Harker's Journal",
                                  "original_filename": "dracula-ch01.txt", "content": text}],
                }))
                print("  bulk_create:", json.dumps(res)[:200])
                ids = res.get("chapter_ids") or [
                    c.get("chapter_id") or c.get("id")
                    for c in (res.get("chapters") or res.get("created") or [])]
                st["chapter_ids"] = [i for i in ids if i]
                save(st)
            chapters = st["chapter_ids"]
            print("chapter_ids:", chapters)

            if not st.get("published"):
                for cid in chapters:
                    # book_chapter_publish is propose->confirm: confirm the token so the
                    # chapter is GENUINELY published (chapter.published fires → the
                    # embedding-model-set backfill later grounds it; D-KG-PASSAGE-BACKFILL).
                    pr = _p(await s.call_tool("book_chapter_publish",
                                              {"book_id": book, "chapter_id": cid}))
                    code, _b = await confirm("book", pr["confirm_token"])
                    print("  publish+confirm", cid, "->", code)
                st["published"] = True
                save(st)

            # ── Phase 4 — extract glossary (agent) ────────────────────────────
            if not st.get("extract_job"):
                print("== Phase 4: extract glossary ==")
                pr = _p(await s.call_tool("translation_start_extraction", {
                    "book_id": book, "chapter_ids": chapters,
                    "extraction_profile": {}, "model_ref": GEN,
                }))
                print("  extraction propose:", json.dumps(pr)[:200])
                tok = pr.get("confirm_token")
                if tok:
                    code, body = await confirm("translation", tok)
                    print("  extraction confirm:", code, json.dumps(body)[:200])
                    st["extract_job"] = (body or {}).get("job_id") if isinstance(body, dict) else None
                else:
                    st["extract_job"] = pr.get("job_id")
                save(st)
            if st.get("extract_job") and not st.get("extracted_count"):
                print("  polling glossary entity-count...")
                cnt = 0
                for i in range(90):
                    async with httpx.AsyncClient(timeout=30) as c:
                        rr = await c.get(f"{GLOSS_SVC}/internal/books/{book}/entity-count",
                                         headers={"X-Internal-Token": TOKEN})
                    cnt = (rr.json() or {}).get("count", 0) if rr.status_code == 200 else 0
                    print(f"  [extract] {i}: entities={cnt}")
                    if cnt > 0:
                        st["extracted_count"] = cnt; save(st); break
                    await asyncio.sleep(10)

            # ── Phase 5 — translate glossary + chapter to vi ──────────────────
            if not st.get("translate_job"):
                print("== Phase 5: translate to vi ==")
                pr = _p(await s.call_tool("translation_start_job", {
                    "book_id": book, "chapter_ids": chapters, "target_language": "vi",
                }))
                print("  translate start:", json.dumps(pr)[:200])
                tok = pr.get("confirm_token")
                if tok:
                    code, body = await confirm("translation", tok)
                    print("  translate confirm:", code, json.dumps(body)[:200])
                    st["translate_job"] = (body or {}).get("job_id") if isinstance(body, dict) else None
                else:
                    st["translate_job"] = pr.get("job_id")
                save(st)
            if st.get("translate_job") and not st.get("translate_done"):
                res = await poll_job(s, st["translate_job"], "translate")
                if res.get("status") in ("completed", "completed_with_errors", "succeeded"):
                    st["translate_done"] = True; save(st)

    print("PHASES 1-5 STATE:", json.dumps(load()))


asyncio.run(main())
