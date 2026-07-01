"""Evaluation runner — drive the compose-quality surfaces over a REAL book and collect
the structured outputs as DATA (not a green/red smoke), so we can analyze signal-vs-noise
and build a ranked improvement backlog.

Uses the reusable `quality_harness`: logs in as claude-test, resolves the POC book +
every DRAFTED chapter, and for each chapter drives self-heal/propose + quality-report,
then the book-level promise-coverage once. Writes raw results to a JSON file
(incrementally, so a mid-run failure still preserves partial data) and prints a compact
per-chapter line + an aggregate summary.

Run (stack must be up + the BYOK model reachable):
    OUT=/path/to/eval.json python tests/e2e/eval_compose_quality.py
Defaults the output to the scratchpad if OUT is unset.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

import httpx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quality_harness as qh  # noqa: E402

OUT = os.environ.get("OUT", os.path.join(os.path.dirname(__file__), "eval_out.json"))


def _slim_self_heal(res: dict) -> dict:
    """Drop the bulky source_text; keep the proposals + stats we analyze."""
    if "error" in res:
        return res
    props = res.get("proposals", [])
    return {
        "n_proposals": len(props),
        "proposals": [{k: p.get(k) for k in ("type", "tier", "before", "after", "issue",
                                             "recommended", "rerank_reason")} for p in props],
        "stats": res.get("stats"),
        "draft_version": res.get("draft_version"),
    }


async def run() -> dict:
    async with httpx.AsyncClient(base_url=qh.GATEWAY_URL, timeout=120.0) as c:
        token = await qh.login(c)
        headers = qh.auth_headers(token)
        target = await qh.resolve_target(c, headers=headers)
        print(f"book={target.book_title!r} project={target.project_id} model={target.model_ref[:8]} "
              f"lang={target.source_language}", flush=True)

        r = await c.get(f"/v1/books/{target.book_id}/chapters?limit=200", headers=headers)
        r.raise_for_status()
        chapters = [ch for ch in r.json().get("items", []) if (ch.get("draft_revision_count") or 0) > 0]
        chapters.sort(key=lambda ch: ch.get("sort_order") or 0)
        print(f"drafted chapters: {len(chapters)}", flush=True)

        results: dict = {
            "book": target.book_title, "project_id": target.project_id,
            "model_ref": target.model_ref, "source_language": target.source_language,
            "n_chapters": len(chapters), "chapters": [], "promise_coverage": None,
        }

        for ch in chapters:
            cid = ch["chapter_id"]
            ct = qh.QualityTarget(project_id=target.project_id, book_id=target.book_id,
                                  chapter_id=cid, model_ref=target.model_ref,
                                  source_language=target.source_language)
            try:
                heal = _slim_self_heal(await qh.propose_self_heal(c, ct, headers=headers))
            except Exception as exc:  # noqa: BLE001 — keep the run going, record the failure
                heal = {"error": repr(exc)}
            try:
                rep = await qh.quality_report(c, ct, headers=headers)
            except Exception as exc:  # noqa: BLE001
                rep = {"error": repr(exc)}

            critic = rep.get("critic", {}) if isinstance(rep, dict) else {}
            promises = rep.get("promises", {}) if isinstance(rep, dict) else {}
            results["chapters"].append({
                "sort_order": ch.get("sort_order"), "chapter_id": cid,
                "self_heal": heal, "quality_report": rep,
            })
            with open(OUT, "w", encoding="utf-8") as f:  # incremental save
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"ch{ch.get('sort_order'):>2} | heal={heal.get('n_proposals', 'ERR')} "
                  f"| critic(coh/voice/pace/canon)={critic.get('coherence')}/{critic.get('voice_match')}/"
                  f"{critic.get('pacing')}/{critic.get('canon_consistency')} viol={len(critic.get('violations', []))} "
                  f"| dropped={len(promises.get('dropped', []))}", flush=True)

        try:
            results["promise_coverage"] = await qh.promise_coverage(c, ct, headers=headers)
        except Exception as exc:  # noqa: BLE001
            results["promise_coverage"] = {"error": repr(exc)}
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        pc = results["promise_coverage"] or {}
        print(f"\nBOOK promise-coverage: tracked={pc.get('tracked_count')} "
              f"paid={pc.get('paid_count')} progressing={pc.get('progressing_count')} "
              f"abandoned={pc.get('abandoned_count')} absent={pc.get('absent_count')} "
              f"err={pc.get('error')}", flush=True)
        print(f"raw data -> {OUT}", flush=True)
        return results


if __name__ == "__main__":
    asyncio.run(run())
