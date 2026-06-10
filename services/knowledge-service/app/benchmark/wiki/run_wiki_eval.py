"""wiki-llm M8 — wiki quality eval runner (thin advisory).

Reads AI-generated wiki articles for a book via the GLOSSARY API (PO decision A —
the list/detail endpoints expose ``generation_status`` + ``generation_provenance``
since M7b-1), computes verify-flag-rate + citation-resolvability (``metrics.py``),
prints a table, and (with ``--gate``) exits non-zero when a threshold is breached
so it can run advisory in CI.

Usage (against a running stack, e.g. the dev gateway):

    python -m app.benchmark.wiki.run_wiki_eval \\
        --base http://localhost:3123 --book <BOOK_ID> \\
        --email claude-test@loreweave.dev --password '...' \\
        [--gate --min-resolvability 0.9 --max-flagged-rate 0.5]

Network I/O lives here; the scored logic is pure in ``metrics.py`` (unit-tested).
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

import httpx

from app.benchmark.wiki.metrics import (
    aggregate_resolvability,
    citation_resolvability,
    verify_flag_rate,
)


def _login(client: httpx.Client, base: str, email: str, password: str) -> str:
    r = client.post(f"{base}/v1/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    body = r.json()
    token = body.get("access_token") or body.get("accessToken")
    if not token:
        raise SystemExit("login: no access_token in response")
    return token


def _list_articles(client: httpx.Client, base: str, book: str, hdr: dict) -> list[dict[str, Any]]:
    r = client.get(f"{base}/v1/glossary/books/{book}/wiki", params={"limit": 500}, headers=hdr)
    r.raise_for_status()
    return r.json().get("items", [])


def _detail(client: httpx.Client, base: str, book: str, article_id: str, hdr: dict) -> dict[str, Any]:
    r = client.get(f"{base}/v1/glossary/books/{book}/wiki/{article_id}", headers=hdr)
    r.raise_for_status()
    return r.json()


def run(base: str, book: str, email: str, password: str) -> dict[str, Any]:
    with httpx.Client(timeout=30.0) as client:
        token = _login(client, base, email, password)
        hdr = {"Authorization": f"Bearer {token}"}
        articles = _list_articles(client, base, book, hdr)
        flags = verify_flag_rate(articles)
        ai = [a for a in articles if a.get("generation_status")]
        per_article = [
            citation_resolvability(_detail(client, base, book, a["article_id"], hdr)) for a in ai
        ]
    return {"verify_flag_rate": flags, "resolvability": aggregate_resolvability(per_article)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Wiki quality eval (advisory)")
    ap.add_argument("--base", default="http://localhost:3123")
    ap.add_argument("--book", required=True)
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--gate", action="store_true", help="exit non-zero on a threshold breach")
    ap.add_argument("--min-resolvability", type=float, default=0.9)
    ap.add_argument("--max-flagged-rate", type=float, default=0.5)
    args = ap.parse_args(argv)

    res = run(args.base, args.book, args.email, args.password)
    f, r = res["verify_flag_rate"], res["resolvability"]
    print("── wiki quality eval (advisory) ──")
    print(f"AI articles:        {f['total_ai']}  "
          f"(generated={f['generated']} needs_review={f['needs_review']} blocked={f['blocked']})")
    print(f"verify-flag-rate:   {f['flagged_rate']:.2f}  (clean={f['clean_rate']:.2f})")
    print(f"citations:          {r['citations']} over {r['articles']} articles")
    print(f"resolvability:      {r['ratio']:.2f}  "
          f"({r['articles_with_unresolvable']} article(s) with an unresolvable cite)")

    if args.gate:
        breaches = []
        if r["ratio"] < args.min_resolvability:
            breaches.append(f"resolvability {r['ratio']:.2f} < {args.min_resolvability}")
        if f["flagged_rate"] > args.max_flagged_rate:
            breaches.append(f"flagged-rate {f['flagged_rate']:.2f} > {args.max_flagged_rate}")
        if breaches:
            print("GATE FAIL: " + "; ".join(breaches))
            return 1
        print("GATE PASS")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
