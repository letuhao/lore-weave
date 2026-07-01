"""Live-smoke the self-heal/propose ENDPOINT's cross-service resolve path against the
running stack: mint bearer → book-service get_draft (confirm `body` key) → Tiptap→text →
KAL roster → render_canon. (The propose ENGINE is already live-validated separately.)"""
import asyncio, sys
sys.path.insert(0, "/app")
from uuid import UUID
from app.config import settings
from app.mcp.service_bearer import mint_service_bearer
from app.clients.book_client import get_book_client
from app.clients.kal_client import get_kal_client
from app.engine.prose_doc import tiptap_doc_to_text
from app.engine.heal_canon import render_canon, convention_for

USER = UUID("019d5e3c-7cc5-7e6a-8b27-1344e148bf7c")
BOOK = UUID("019f1783-ebb4-78de-ac9d-0dfba6539b7c")
CH = UUID("019f1783-eca0-7bc9-ae29-d2cefc452a37")

async def main():
    bearer = mint_service_bearer(USER, settings.jwt_secret)
    book = get_book_client()
    draft = await book.get_draft(BOOK, CH, bearer)
    print("draft keys:", sorted(draft.keys()))
    print("draft_version:", draft.get("draft_version"))
    body = draft.get("body") or draft.get("doc") or draft.get("content")
    text = tiptap_doc_to_text(body)
    print("text len:", len(text), "| head:", repr(text[:90]))
    kal = get_kal_client()
    roster = await kal.roster(BOOK, user_id=USER)
    print("roster count:", len(roster), "| sample:", roster[:2])
    canon = render_canon(roster, convention=convention_for(["tiên hiệp"], "vi"))
    print("canon len:", len(canon))
    print("canon head:\n", canon[:240])
    print("\nRESOLVE PATH OK" if text.strip() and canon.strip() else "\nRESOLVE INCOMPLETE")

asyncio.run(main())
