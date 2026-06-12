#!/usr/bin/env python3
"""P3-EVAL E0a — seed the raw-search eval corpus into the RUNNING stack.

Imports the first N chapters of 万古神帝 (crawled .txt on disk) as a book
in book-service for the test account, creates a knowledge_project wired to
the local bge-m3 embedding model, then drives the in-container ingest
(``app.benchmark.ingest_rawsearch_corpus``) to embed each chapter into
``:Passage`` nodes. The result is a book that is searchable on BOTH raw-
search surfaces — lexical (chapter_blocks) and semantic (passages) — so
``scripts/run_rawsearch_eval.py`` can measure retrieval quality live.

Idempotent: find-or-create at every step (book by title, chapter by title,
project by (user,book)). Embeddings run on the LOCAL LM Studio bge-m3 model
the test account owns → free. ADDITIVE only — never deletes existing data.

Run:  python scripts/seed_rawsearch_eval.py
Env overrides (working defaults for the current infra stack):
  AUTH_URL=http://localhost:8204  BOOK_URL=http://localhost:8205
  INTERNAL_SERVICE_TOKEN=dev_internal_token
  TEST_EMAIL=claude-test@loreweave.dev  TEST_PASSWORD=Claude@Test2026
  PG_CONTAINER=infra-postgres-1  PG_USER=loreweave
  KNOWLEDGE_CONTAINER=infra-knowledge-service-1
  SRC_DIR=<path to 万古神帝 chapters>  N_CHAPTERS=40
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import requests

# ── Config ──────────────────────────────────────────────────────────────────
AUTH_URL = os.environ.get("AUTH_URL", "http://localhost:8204").rstrip("/")
BOOK_URL = os.environ.get("BOOK_URL", "http://localhost:8205").rstrip("/")

TEST_EMAIL = os.environ.get("TEST_EMAIL", "claude-test@loreweave.dev")
TEST_PASSWORD = os.environ.get("TEST_PASSWORD", "Claude@Test2026")

PG_CONTAINER = os.environ.get("PG_CONTAINER", "infra-postgres-1")
PG_USER = os.environ.get("PG_USER", "loreweave")
KNOWLEDGE_DB = os.environ.get("KNOWLEDGE_DB", "loreweave_knowledge")
BOOK_DB = os.environ.get("BOOK_DB", "loreweave_book")
KNOWLEDGE_CONTAINER = os.environ.get("KNOWLEDGE_CONTAINER", "infra-knowledge-service-1")

SRC_DIR = Path(os.environ.get(
    "SRC_DIR",
    r"D:\Works\source\web-crawling\output\万古神帝-51254\chapters",
))
N_CHAPTERS = int(os.environ.get("N_CHAPTERS", "40"))

BOOK_TITLE = "万古神帝 — Raw-Search Eval (40ch)"
PROJECT_NAME = "万古神帝 Raw-Search Eval"
ORIG_LANG = "zh"
# bge-m3 (local) user_model owned by claude-test; dim 1024.
BGE_MODEL_ID = os.environ.get(
    "BGE_MODEL_ID", "019e7f71-0271-722f-9c9c-3f049c0b26f4")
EMB_DIM = int(os.environ.get("EMB_DIM", "1024"))

_DATE_AUTHOR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\s")
_PSQL_STATUS_RE = re.compile(
    r"^(INSERT|UPDATE|DELETE|SELECT|MERGE|COPY|BEGIN|COMMIT|ROLLBACK)\b.*$")


# ── helpers ─────────────────────────────────────────────────────────────────
def log(msg: str) -> None:
    print(f"[seed] {msg}", file=sys.stderr, flush=True)


def fail(reason: str, what_landed: str = "") -> None:
    print(json.dumps({"result": "FAILED", "reason": reason,
                      "what_landed": what_landed}, ensure_ascii=False))
    sys.exit(1)


def psql(db: str, sql: str) -> str:
    cp = subprocess.run(
        ["docker", "exec", PG_CONTAINER, "psql", "-U", PG_USER, "-d", db,
         "-tAc", sql],
        capture_output=True, text=True, encoding="utf-8",
    )
    if cp.returncode != 0:
        raise RuntimeError(f"psql failed ({db}): {cp.stderr.strip()}")
    lines = [ln for ln in cp.stdout.strip().splitlines()
             if not _PSQL_STATUS_RE.match(ln.strip())]
    return "\n".join(lines).strip()


def parse_chapter(path: Path) -> tuple[str, str]:
    """Return (title, body) for a crawled chapter .txt.

    Crawl format: the chapter title appears ~3x at the top plus a
    ``YYYY-MM-DD 作者：…`` line, then the body — paragraphs each indented
    a couple spaces. We take the first non-empty line as the title, drop
    every line equal to that title and the date/author line, and join the
    remaining non-empty paragraphs with a blank line so book-service splits
    them into chapter_blocks.
    """
    raw = path.read_text(encoding="utf-8", errors="replace")
    lines = [ln.strip() for ln in raw.splitlines()]
    non_empty = [ln for ln in lines if ln]
    if not non_empty:
        return (path.stem, "")
    title = non_empty[0]
    body_paras = [
        ln for ln in non_empty[1:]
        if ln != title and not _DATE_AUTHOR_RE.match(ln)
    ]
    return (title, "\n\n".join(body_paras))


def login() -> tuple[str, str]:
    r = requests.post(f"{AUTH_URL}/v1/auth/login",
                      json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
                      timeout=15)
    r.raise_for_status()
    body = r.json()
    return body["access_token"], body["user_profile"]["user_id"]


def find_or_create_book(jwt: str) -> str:
    h = {"Authorization": f"Bearer {jwt}"}
    r = requests.get(f"{BOOK_URL}/v1/books?limit=200", headers=h, timeout=15)
    r.raise_for_status()
    payload = r.json()
    items = payload.get("books") or payload.get("items") or payload
    if isinstance(items, dict):
        items = items.get("books", [])
    for b in items:
        if b.get("title") == BOOK_TITLE:
            bid = b.get("book_id") or b.get("id")
            log(f"book exists: {bid}")
            return bid
    r = requests.post(f"{BOOK_URL}/v1/books", headers=h, timeout=15, json={
        "title": BOOK_TITLE,
        "description": "万古神帝 first 40 chapters — raw-search retrieval eval corpus.",
        "original_language": ORIG_LANG,
        "summary": "Eval-only import; lexical + semantic raw-search benchmark.",
        "genre_tags": ["fantasy"],
    })
    r.raise_for_status()
    bid = r.json().get("book_id") or r.json().get("id")
    log(f"book created: {bid}")
    return bid


def find_or_create_chapters(jwt: str, book_id: str) -> list[dict]:
    """Create N chapters from the corpus; return [{chapter_id, chapter_index}]."""
    h = {"Authorization": f"Bearer {jwt}"}
    existing: dict[str, str] = {}
    r = requests.get(f"{BOOK_URL}/v1/books/{book_id}/chapters?limit=500",
                     headers=h, timeout=20)
    if r.status_code == 200:
        payload = r.json()
        for c in (payload.get("chapters") or payload.get("items") or []):
            t = c.get("title")
            cid = c.get("chapter_id") or c.get("id")
            if t and cid:
                existing[t] = cid

    files = sorted(SRC_DIR.glob("*.txt"))[:N_CHAPTERS]
    if not files:
        fail(f"no .txt chapters under {SRC_DIR}")
    out: list[dict] = []
    for i, path in enumerate(files, start=1):
        title, body = parse_chapter(path)
        if not body:
            log(f"WARN: empty body for {path.name}; skipping")
            continue
        if title in existing:
            out.append({"chapter_id": existing[title], "chapter_index": i})
            continue
        rr = requests.post(
            f"{BOOK_URL}/v1/books/{book_id}/chapters",
            headers={**h, "Content-Type": "application/json"}, timeout=30,
            json={"title": title, "original_language": ORIG_LANG,
                  "sort_order": i, "body": body},
        )
        if rr.status_code not in (200, 201):
            log(f"WARN: chapter {i} ({title}) create -> {rr.status_code} {rr.text[:160]}")
            continue
        cid = rr.json().get("chapter_id") or rr.json().get("id")
        if cid:
            out.append({"chapter_id": cid, "chapter_index": i})
    log(f"chapters ready: {len(out)}/{len(files)}")
    return out


def ensure_knowledge_project(user_id: str, book_id: str) -> str:
    pid = psql(KNOWLEDGE_DB,
               f"SELECT project_id FROM knowledge_projects "
               f"WHERE book_id='{book_id}' AND user_id='{user_id}' LIMIT 1;")
    if pid:
        # Make sure the embedding config is wired (idempotent update).
        psql(KNOWLEDGE_DB,
             f"UPDATE knowledge_projects SET embedding_model='{BGE_MODEL_ID}', "
             f"embedding_dimension={EMB_DIM} WHERE project_id='{pid}';")
        log(f"knowledge project exists: {pid} (embedding wired)")
        return pid
    name = PROJECT_NAME.replace("'", "''")
    pid = psql(KNOWLEDGE_DB,
               "INSERT INTO knowledge_projects "
               "(user_id, name, description, project_type, book_id, "
               " extraction_enabled, extraction_status, embedding_model, "
               " embedding_dimension) "
               f"VALUES ('{user_id}', '{name}', 'raw-search eval', 'book', "
               f"'{book_id}', false, 'disabled', '{BGE_MODEL_ID}', {EMB_DIM}) "
               "RETURNING project_id;")
    log(f"knowledge project created: {pid}")
    return pid


def drive_ingest(book_id: str, project_id: str, user_id: str,
                 chapters: list[dict]) -> dict:
    """Run the in-container ingest module, feeding the chapter list on stdin."""
    payload = json.dumps(chapters, ensure_ascii=False)
    cp = subprocess.run(
        ["docker", "exec", "-i", KNOWLEDGE_CONTAINER,
         "python", "-m", "app.benchmark.ingest_rawsearch_corpus",
         "--book-id", book_id, "--project-id", project_id, "--user-id", user_id,
         "--embedding-model", BGE_MODEL_ID, "--embedding-dim", str(EMB_DIM)],
        input=payload, capture_output=True, text=True, encoding="utf-8",
    )
    if cp.stderr.strip():
        log("ingest stderr (tail): " + cp.stderr.strip().splitlines()[-1][:200])
    out = cp.stdout.strip().splitlines()
    for ln in reversed(out):  # last JSON line is the summary
        ln = ln.strip()
        if ln.startswith("{"):
            try:
                return json.loads(ln)
            except json.JSONDecodeError:
                continue
    return {"error": "no ingest summary", "rc": cp.returncode,
            "stdout_tail": out[-3:] if out else []}


def book_block_count(book_id: str) -> int:
    return int(psql(BOOK_DB,
                    "SELECT count(cb.id) FROM chapter_blocks cb "
                    "JOIN chapters c ON c.id=cb.chapter_id "
                    f"WHERE c.book_id='{book_id}';") or "0")


# ── main ────────────────────────────────────────────────────────────────────
def main() -> None:
    try:
        jwt, user_id = login()
    except Exception as e:  # noqa: BLE001
        fail(f"login failed: {e}")
    log(f"user_id={user_id}")

    try:
        book_id = find_or_create_book(jwt)
        chapters = find_or_create_chapters(jwt, book_id)
    except Exception as e:  # noqa: BLE001
        fail(f"book/chapter seeding failed: {e}")
    if not chapters:
        fail("no chapters created", what_landed=f"book {book_id}")

    try:
        project_id = ensure_knowledge_project(user_id, book_id)
    except Exception as e:  # noqa: BLE001
        fail(f"knowledge project ensure failed: {e}",
             what_landed=f"book {book_id}, {len(chapters)} chapters")

    blocks = book_block_count(book_id)
    log(f"lexical surface: {blocks} chapter_blocks")

    ingest = drive_ingest(book_id, project_id, user_id, chapters)
    log(f"ingest: {ingest}")

    passages = int(ingest.get("passages_total", 0) or 0)
    result = "DONE" if (blocks > 0 and passages > 0) else "PARTIAL"
    print(json.dumps({
        "result": result,
        "book_id": book_id,
        "project_id": project_id,
        "user_id": user_id,
        "chapters": len(chapters),
        "blocks": blocks,
        "passages": passages,
        "ingest_errors": ingest.get("errors", [])[:5],
        "seed_script": "scripts/seed_rawsearch_eval.py",
    }, ensure_ascii=False))
    if result != "DONE":
        sys.exit(1)


if __name__ == "__main__":
    main()
