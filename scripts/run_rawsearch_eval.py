#!/usr/bin/env python3
"""P3-EVAL E3/E4 — raw-search retrieval eval runner (host).

Drives the LIVE knowledge orchestrator endpoint over the golden set for
all three modes (lexical / semantic / hybrid) at controllable K, computes
standard IR metrics per mode, and adds two brute-force baselines:

  - lexical oracle recall : endpoint top-K vs an EXACT substring scan over
    chapter_blocks (does the ILIKE/trigram ranking miss any true match?).
  - semantic ANN recall   : Neo4j vector index vs flat-kNN (shells the
    in-container `app.benchmark.flat_knn_rawsearch`).

Metrics are imported from the shipped, pure `app.benchmark.metrics`.

Run:  python scripts/run_rawsearch_eval.py [--k 5 10] [--golden <path>]
Env:  AUTH_URL, KNOWLEDGE_URL (default :8216), PG_CONTAINER, KNOWLEDGE_CONTAINER,
      TEST_EMAIL/TEST_PASSWORD.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import requests

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "services" / "knowledge-service"))
from app.benchmark.metrics import (  # noqa: E402
    hit_at_k, mean, ndcg_at_k, reciprocal_rank, recall_at_k,
)

AUTH_URL = os.environ.get("AUTH_URL", "http://localhost:8204").rstrip("/")
KNOWLEDGE_URL = os.environ.get("KNOWLEDGE_URL", "http://localhost:8216").rstrip("/")
GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:3123").rstrip("/")
TEST_EMAIL = os.environ.get("TEST_EMAIL", "claude-test@loreweave.dev")
TEST_PASSWORD = os.environ.get("TEST_PASSWORD", "Claude@Test2026")
PG_CONTAINER = os.environ.get("PG_CONTAINER", "infra-postgres-1")
PG_USER = os.environ.get("PG_USER", "loreweave")
BOOK_DB = os.environ.get("BOOK_DB", "loreweave_book")
KNOWLEDGE_CONTAINER = os.environ.get("KNOWLEDGE_CONTAINER", "infra-knowledge-service-1")
BGE_MODEL_ID = os.environ.get("BGE_MODEL_ID", "019e7f71-0271-722f-9c9c-3f049c0b26f4")
EMB_DIM = int(os.environ.get("EMB_DIM", "1024"))

MODES = ["lexical", "semantic", "hybrid"]


def log(m: str) -> None:
    print(f"[eval] {m}", file=sys.stderr, flush=True)


def login() -> tuple[str, str]:
    r = requests.post(f"{AUTH_URL}/v1/auth/login",
                      json={"email": TEST_EMAIL, "password": TEST_PASSWORD}, timeout=15)
    r.raise_for_status()
    b = r.json()
    return b["access_token"], b["user_profile"]["user_id"]


def _esc_sql(s: str) -> str:
    return s.replace("'", "''")


def search(base: str, jwt: str, book_id: str, q: str, mode: str, k: int,
           granularity: str = "chapter", min_relevance: float | None = None) -> dict | None:
    """GET the orchestrator endpoint. Returns parsed JSON or None on transport error."""
    url = f"{base}/v1/knowledge/books/{book_id}/search"
    params: dict = {"query": q, "mode": mode, "limit": k, "granularity": granularity}
    if min_relevance is not None:
        params["min_relevance"] = min_relevance
    try:
        r = requests.get(url, headers={"Authorization": f"Bearer {jwt}"},
                         params=params, timeout=30)
    except requests.RequestException as e:
        log(f"transport error {mode} '{q}': {e}")
        return None
    if r.status_code != 200:
        return {"_status": r.status_code, "_body": r.text[:160]}
    return r.json()


def ranked_chapter_ids(resp: dict) -> list[str]:
    """Dedup chapterIds preserving rank order (chapter-granular metrics)."""
    seen: set[str] = set()
    out: list[str] = []
    for hit in resp.get("results", []):
        cid = str(hit.get("chapterId"))
        if cid and cid not in seen:
            seen.add(cid)
            out.append(cid)
    return out


def oracle_chapters(book_id: str, term: str) -> set[str]:
    """Exact substring ground truth: chapters whose blocks contain `term`."""
    sql = (
        "SELECT DISTINCT c.id FROM chapter_blocks cb "
        "JOIN chapters c ON c.id=cb.chapter_id "
        f"WHERE c.book_id='{book_id}' AND cb.text_content ILIKE '%{_esc_sql(term)}%';"
    )
    cp = subprocess.run(
        ["docker", "exec", PG_CONTAINER, "psql", "-U", PG_USER, "-d", BOOK_DB, "-tAc", sql],
        capture_output=True, text=True, encoding="utf-8",
    )
    if cp.returncode != 0:
        return set()
    status = re.compile(r"^(SELECT|INSERT|UPDATE)\b")
    return {ln.strip() for ln in cp.stdout.strip().splitlines()
            if ln.strip() and not status.match(ln.strip())}


def semantic_ann_recall(project_id: str, user_id: str, queries: list[str], k: int) -> dict:
    payload = json.dumps(queries, ensure_ascii=False)
    cp = subprocess.run(
        ["docker", "exec", "-i", KNOWLEDGE_CONTAINER, "python", "-m",
         "app.benchmark.flat_knn_rawsearch", "--project-id", project_id,
         "--user-id", user_id, "--embedding-model", BGE_MODEL_ID,
         "--embedding-dim", str(EMB_DIM), "--k", str(k)],
        input=payload, capture_output=True, text=True, encoding="utf-8",
    )
    for ln in reversed(cp.stdout.strip().splitlines()):
        if ln.strip().startswith("{"):
            try:
                return json.loads(ln)
            except json.JSONDecodeError:
                continue
    return {"error": "no flat-knn summary", "stderr_tail": cp.stderr.strip()[-200:]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", default=str(
        _REPO / "services" / "knowledge-service" / "app" / "benchmark" / "rawsearch_golden.json"))
    ap.add_argument("--k", type=int, nargs="+", default=[5, 10])
    ap.add_argument("--base", choices=["knowledge", "gateway"], default="knowledge")
    ap.add_argument("--granularity", choices=["chapter", "block"], default="chapter")
    ap.add_argument("--min-relevance", type=float, default=None,
                    help="override the server score-floor (default: server's)")
    args = ap.parse_args()
    gran, mr = args.granularity, args.min_relevance

    golden = json.loads(Path(args.golden).read_text(encoding="utf-8"))
    book_id = golden["book_id"]
    project_id = golden["project_id"]
    queries = golden["queries"]
    pos = [q for q in queries if q.get("band") != "negative"]
    negs = [q for q in queries if q.get("band") == "negative"]

    jwt, user_id = login()
    base = KNOWLEDGE_URL if args.base == "knowledge" else GATEWAY_URL
    log(f"book={book_id} project={project_id} queries={len(queries)} (pos={len(pos)} neg={len(negs)})")

    report: dict = {"book_id": book_id, "modes": {}, "baselines": {}, "negatives": {}}
    maxk = max(args.k)
    degraded_seen: dict[str, str] = {}

    # ── per-mode IR metrics (over positive-band queries) ────────────────
    for mode in MODES:
        per_k = {k: {"hit": [], "recall": [], "ndcg": []} for k in args.k}
        mrr_vals = []
        for qd in pos:
            resp = search(base, jwt, book_id, qd["q"], mode, maxk, gran, mr)
            if not resp or "_status" in (resp or {}):
                continue
            for kk, vv in (resp.get("degraded") or {}).items():
                degraded_seen[kk] = vv
            ranked = ranked_chapter_ids(resp)
            expected = [str(x) for x in qd.get("expected", [])]
            graded = {str(k): float(v) for k, v in (qd.get("graded") or {}).items()}
            mrr_vals.append(reciprocal_rank(expected, ranked))
            for k in args.k:
                per_k[k]["hit"].append(hit_at_k(expected, ranked, k))
                per_k[k]["recall"].append(recall_at_k(expected, ranked, k))
                per_k[k]["ndcg"].append(ndcg_at_k(graded, ranked, k))
        report["modes"][mode] = {
            "MRR": round(mean(mrr_vals), 4),
            **{f"hit@{k}": round(mean(per_k[k]["hit"]), 4) for k in args.k},
            **{f"recall@{k}": round(mean(per_k[k]["recall"]), 4) for k in args.k},
            **{f"ndcg@{k}": round(mean(per_k[k]["ndcg"]), 4) for k in args.k},
        }
    report["degraded_seen"] = degraded_seen

    # ── baseline 1: lexical oracle recall (endpoint vs exact substring) ──
    ora = []
    for qd in pos:
        if qd.get("band") not in ("exact", "phrase"):
            continue  # oracle recall only meaningful for substring-present terms
        truth = oracle_chapters(book_id, qd["q"])
        if not truth:
            continue
        resp = search(base, jwt, book_id, qd["q"], "lexical", maxk, gran, mr)
        ranked = set(ranked_chapter_ids(resp)) if resp and "_status" not in resp else set()
        ora.append(len(truth & ranked) / len(truth))
    report["baselines"]["lexical_oracle_recall@maxk"] = {
        "k": maxk, "value": round(mean(ora), 4), "n": len(ora),
    }

    # ── baseline 2: semantic ANN recall (Neo4j index vs flat-kNN) ────────
    sem_qs = [qd["q"] for qd in pos]
    report["baselines"]["semantic_ann_recall"] = semantic_ann_recall(
        project_id, user_id, sem_qs, maxk)

    # ── negative controls (per mode: leakage) ───────────────────────────
    for mode in MODES:
        leaks = []
        for qd in negs:
            resp = search(base, jwt, book_id, qd["q"], mode, maxk, gran, mr)
            n = len(resp.get("results", [])) if resp and "_status" not in resp else 0
            top = resp["results"][0].get("score") if (resp and resp.get("results")) else None
            leaks.append({"q": qd["q"], "returned": n, "top_score": top})
        report["negatives"][mode] = leaks

    # ── print ───────────────────────────────────────────────────────────
    print("\n=== RAW-SEARCH RETRIEVAL EVAL ===")
    cols = (["MRR"] + [f"hit@{k}" for k in args.k]
            + [f"recall@{k}" for k in args.k] + [f"ndcg@{k}" for k in args.k])
    hdr = "mode".ljust(10) + "".join(c.rjust(11) for c in cols)
    print(hdr)
    print("-" * len(hdr))
    for mode in MODES:
        m = report["modes"][mode]
        print(mode.ljust(10) + "".join(f"{m[c]:.4f}".rjust(11) for c in cols))
    bl = report["baselines"]
    print(f"\nlexical oracle recall@{maxk}: {bl['lexical_oracle_recall@maxk']['value']} "
          f"(n={bl['lexical_oracle_recall@maxk']['n']})  — endpoint vs exact substring")
    sar = bl["semantic_ann_recall"]
    print(f"semantic ANN recall@{maxk}:   {sar.get('mean_ann_recall_at_k', 'n/a')} "
          f"— Neo4j index vs flat-kNN")
    if degraded_seen:
        print(f"degraded legs seen: {degraded_seen}")
    print("\n--- JSON ---")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
