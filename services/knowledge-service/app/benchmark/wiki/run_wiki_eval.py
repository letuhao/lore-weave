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
import base64
import binascii
import json
import sys
import uuid
from typing import Any

import httpx

from app.benchmark.wiki.metrics import (
    aggregate_resolvability,
    citation_resolvability,
    collect_citation_marks,
    verify_flag_rate,
)


def _jwt_sub(token: str) -> str:
    """Read the `sub` claim (the owner user_id) from a JWT WITHOUT verifying — the
    eval account is the book owner, and the judge needs the owner to bill/attribute."""
    try:
        seg = token.split(".")[1]
        seg += "=" * (-len(seg) % 4)  # pad base64url
        return str(json.loads(base64.urlsafe_b64decode(seg)).get("sub", ""))
    except (IndexError, ValueError, binascii.Error, json.JSONDecodeError):
        return ""


def _plaintext(body_json: Any) -> str:
    """Flatten a TipTap doc to plain text (depth-first text nodes)."""
    out: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "text" and node.get("text"):
                out.append(str(node["text"]))
            for child in node.get("content", []) or []:
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(body_json)
    return " ".join(out)


def _judge_articles(
    client: httpx.Client, learning_url: str, internal_token: str, book: str,
    ai: list[dict], details: list[dict], jwt: str, judge_model: str | None,
    *, chunk: int = 8,
) -> dict[str, Any]:
    """POST the AI articles (body text + cited snippets) to the learning groundedness
    judge endpoint in bounded CHUNKS, folding the per-article scores into a mean. Each
    judge is a slow LLM call, so a single all-articles request would blow the client
    timeout on a real book — chunking keeps each call bounded (and gives partial
    progress). Stops early once a chunk reports the judge disabled (no model)."""
    owner = _jwt_sub(jwt)
    payload_articles = []
    for item, d in zip(ai, details):
        marks = collect_citation_marks(d.get("body_json"))
        sources = [m["snippet"] for m in marks.values() if m.get("snippet")]
        payload_articles.append({
            "article_id": item["article_id"],
            "book_id": book,
            "user_id": owner,
            "article_text": _plaintext(d.get("body_json")),
            "sources": sources,
        })
    url = f"{learning_url.rstrip('/')}/internal/learning/wiki/judge"
    # One run_id for the whole audit (across chunks) so the scores group as a single
    # run + a retried chunk is idempotent on (run_id, article_id).
    run_id = uuid.uuid4().hex
    enabled, scored, all_scores = False, 0, []
    for i in range(0, len(payload_articles), chunk):
        body: dict[str, Any] = {"run_id": run_id, "articles": payload_articles[i:i + chunk]}
        if judge_model:
            body["judge_model"] = judge_model
        r = client.post(url, json=body, headers={"X-Internal-Token": internal_token})
        r.raise_for_status()
        res = r.json()
        if not res.get("enabled", False):
            enabled = False
            break  # judge disabled (no model) — no point posting the rest
        enabled = True
        scored += res.get("scored", 0)
        all_scores.extend(s["score"] for s in res.get("scores", []))
    return {
        "enabled": enabled,
        "scored": scored,
        "mean": (sum(all_scores) / len(all_scores)) if all_scores else 0.0,
    }


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


def run(
    base: str, book: str, email: str, password: str, *,
    judge: bool = False, learning_url: str | None = None,
    internal_token: str | None = None, judge_model: str | None = None,
) -> dict[str, Any]:
    with httpx.Client(timeout=60.0) as client:
        token = _login(client, base, email, password)
        hdr = {"Authorization": f"Bearer {token}"}
        articles = _list_articles(client, base, book, hdr)
        flags = verify_flag_rate(articles)
        ai = [a for a in articles if a.get("generation_status")]
        details = [_detail(client, base, book, a["article_id"], hdr) for a in ai]
        per_article = [citation_resolvability(d) for d in details]
        out: dict[str, Any] = {
            "verify_flag_rate": flags,
            "resolvability": aggregate_resolvability(per_article),
        }
        if judge:
            try:
                out["groundedness"] = _judge_articles(
                    client, learning_url or "", internal_token or "", book, ai, details,
                    token, judge_model,
                )
            except Exception as e:  # noqa: BLE001 — the judge is advisory; never nuke the eval
                out["groundedness"] = {"enabled": False, "scored": 0, "mean": 0.0, "error": str(e)[:200]}
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Wiki quality eval (advisory)")
    ap.add_argument("--base", default="http://localhost:3123")
    ap.add_argument("--book", required=True)
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--gate", action="store_true", help="exit non-zero on a threshold breach")
    ap.add_argument("--min-resolvability", type=float, default=0.9)
    ap.add_argument("--max-flagged-rate", type=float, default=0.5)
    # D-WIKI-M8-EVAL-PLUS — optional LLM-judge groundedness (the on-demand audit plan).
    ap.add_argument("--judge", action="store_true", help="also run the LLM groundedness judge")
    ap.add_argument("--learning-url", default="http://localhost:8094",
                    help="learning-service internal base url (for --judge)")
    ap.add_argument("--internal-token", default="", help="X-Internal-Token for the judge call")
    ap.add_argument("--judge-model", default="", help="judge model UUID (BYOK user_model)")
    ap.add_argument("--judge-min", type=float, default=0.7, help="gate: min mean groundedness")
    args = ap.parse_args(argv)

    res = run(
        args.base, args.book, args.email, args.password,
        judge=args.judge, learning_url=args.learning_url,
        internal_token=args.internal_token, judge_model=args.judge_model or None,
    )
    f, r = res["verify_flag_rate"], res["resolvability"]
    print("── wiki quality eval (advisory) ──")
    print(f"AI articles:        {f['total_ai']}  "
          f"(generated={f['generated']} needs_review={f['needs_review']} blocked={f['blocked']})")
    print(f"verify-flag-rate:   {f['flagged_rate']:.2f}  (clean={f['clean_rate']:.2f})")
    print(f"citations:          {r['citations']} over {r['articles']} articles")
    print(f"resolvability:      {r['ratio']:.2f}  "
          f"({r['articles_with_unresolvable']} article(s) with an unresolvable cite)")
    g = res.get("groundedness")
    if g is not None:
        if g["enabled"]:
            print(f"groundedness:       {g['mean']:.2f}  (judged {g['scored']} article(s))")
        elif g.get("error"):
            print(f"groundedness:       failed ({g['error']})")
        else:
            print("groundedness:       skipped (judge disabled / no model)")

    if args.gate:
        breaches = []
        if r["ratio"] < args.min_resolvability:
            breaches.append(f"resolvability {r['ratio']:.2f} < {args.min_resolvability}")
        if f["flagged_rate"] > args.max_flagged_rate:
            breaches.append(f"flagged-rate {f['flagged_rate']:.2f} > {args.max_flagged_rate}")
        if g is not None and g["enabled"] and g["scored"] and g["mean"] < args.judge_min:
            breaches.append(f"groundedness {g['mean']:.2f} < {args.judge_min}")
        if breaches:
            print("GATE FAIL: " + "; ".join(breaches))
            return 1
        print("GATE PASS")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
