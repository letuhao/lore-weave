"""A1 eval-gate (validate-first): does diverge->converge (auto K) beat the V0
single-draft (cowrite) on COHERENCE on our local models?

For N scenes: generate `mode=auto` (winner) and `mode=cowrite` (single draft),
critique BOTH with the Work's DISTINCT critic model, compare the coherence dim.
Directional (small N) — the rigorous median is the KS harness; this is the gate
signal. Run from the host against the gateway.

Usage: python eval_a1_diverge.py [n_scenes]
"""
import json
import statistics
import sys
import time
import urllib.request

GW = "http://localhost:3123"


def _req(method, path, token=None, body=None, stream=False, timeout=300):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(GW + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    resp = urllib.request.urlopen(req, timeout=timeout)
    if stream:
        return resp
    raw = resp.read().decode().strip()
    return json.loads(raw) if raw else {}


def login():
    r = _req("POST", "/v1/auth/login", body={"email": "claude-test@loreweave.dev",
                                             "password": "Claude@Test2026"})
    return r["access_token"]


def models(token):
    chat = _req("GET", "/v1/model-registry/user-models?capability=chat", token)["items"]
    chat = [m for m in chat if m["is_active"]]
    allm = _req("GET", "/v1/model-registry/user-models?include_inactive=true", token)["items"]
    allm = [m for m in allm if m["is_active"]]
    drafter = next((m for m in chat if "qwen3.6-35b" in m["provider_model_name"]), chat[0])
    critic = next(m for m in allm if m["user_model_id"] != drafter["user_model_id"])
    return drafter["user_model_id"], critic["user_model_id"]


def cowrite_job(token, proj, sid, drafter):
    """POST cowrite (SSE), drain the stream, return the job_id."""
    body = {"outline_node_id": sid, "model_source": "user_model", "model_ref": drafter,
            "operation": "draft_scene", "mode": "cowrite", "reasoning": "off",
            "max_output_tokens": 400}
    resp = _req("POST", f"/v1/composition/works/{proj}/generate", token, body, stream=True)
    job_id = None
    for raw in resp:
        line = raw.decode().strip()
        if line.startswith("data:"):
            ev = json.loads(line[5:])
            if ev.get("type") == "job":
                job_id = ev["job_id"]
            if ev.get("type") == "done":
                break
    return job_id


def critique_coherence(token, job_id):
    r = _req("POST", f"/v1/composition/jobs/{job_id}/critique", token, {})
    crit = r.get("critic") or {}
    return crit.get("coherence")


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    token = login()
    drafter, critic = models(token)
    book = _req("POST", "/v1/books", token, {"title": f"A1 eval {int(time.time())}",
                                            "original_language": "en"})["book_id"]
    chap = _req("POST", f"/v1/books/{book}/chapters", token,
                {"original_language": "en", "title": "C1"})["chapter_id"]
    proj = _req("POST", f"/v1/composition/books/{book}/work", token)["project_id"]
    _req("PATCH", f"/v1/composition/works/{proj}", token,
         {"settings": {"critic_model_source": "user_model", "critic_model_ref": critic}})

    synopses = [
        "A knight rides into a storm-lit town seeking shelter at a crowded inn.",
        "A thief slips through a moonlit market, hunting the merchant who betrayed her.",
        "Two estranged brothers meet at their father's grave as winter sets in.",
        "A scholar opens a forbidden book and the candle flames bend toward the page.",
        "A captain orders the ship turned into the storm to outrun the pursuing fleet.",
    ][:n]

    auto_c, cow_c = [], []
    print(f"drafter={drafter} critic={critic} n={n}\n")
    for i, syn in enumerate(synopses):
        sid = _req("POST", f"/v1/composition/works/{proj}/outline/nodes", token,
                   {"kind": "scene", "chapter_id": chap, "title": f"S{i}", "synopsis": syn})["id"]
        t0 = time.time()
        a = _req("POST", f"/v1/composition/works/{proj}/generate", token,
                 {"outline_node_id": sid, "model_source": "user_model", "model_ref": drafter,
                  "operation": "draft_scene", "mode": "auto", "reasoning": "off",
                  "max_output_tokens": 400})
        ta = time.time() - t0
        ca = critique_coherence(token, a["job_id"])
        t1 = time.time()
        cw_job = cowrite_job(token, proj, sid, drafter)
        tc = time.time() - t1
        ccw = critique_coherence(token, cw_job)
        auto_c.append(ca); cow_c.append(ccw)
        print(f"  S{i}: AUTO coherence={ca} (k={a.get('k')}, rerank={a.get('rerank_measured')}, {ta:.0f}s) "
              f"| COWRITE coherence={ccw} ({tc:.0f}s)")

    av = [c for c in auto_c if c is not None]
    cv = [c for c in cow_c if c is not None]
    print("\n=== RESULT ===")
    print(f"AUTO    coherence: {av}  median={statistics.median(av) if av else 'n/a'}")
    print(f"COWRITE coherence: {cv}  median={statistics.median(cv) if cv else 'n/a'}")
    if av and cv:
        verdict = "AUTO >= COWRITE -> diverge->converge holds" if statistics.median(av) >= statistics.median(cv) \
            else "AUTO < COWRITE -> rethink before A2"
        print(f"GATE: {verdict}")
    try:
        _req("DELETE", f"/v1/books/{book}", token)
    except Exception as exc:  # noqa
        print(f"(cleanup failed, ignore: {exc})")


if __name__ == "__main__":
    main()
