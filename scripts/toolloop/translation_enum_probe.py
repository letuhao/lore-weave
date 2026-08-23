#!/usr/bin/env python3
"""translation_job_control's COSTLY half — resume and retry — exercised without spending anything.

    python scripts/toolloop/translation_enum_probe.py

🔴 WHY A PROBE AND NOT A SCENARIO. P11-DISTRIBUTION's finding is that every run which chose this
tool chose it for the CANCEL the author asked for; `resume` and `retry` have never been exercised.
No prompt reliably makes a stochastic model pick the expensive branch, and one written to try would
measure the model's obedience rather than the handler — the same reason ship_probe.py drives
boundary cases directly.

🔴 AND IT COSTS NOTHING, BY THE TOOL'S OWN DESIGN. Its description: "'resume' and 'retry' RE-SPEND
money so they return a cost estimate + confirm token (confirm via confirm_action — they do NOT run
until confirmed)." So calling them exercises the dispatch, the ownership check and the cost gate,
and the money is spent only by a redemption this probe deliberately does NOT perform. That is
stated in the result rather than left implied: the costly branch is exercised UP TO the gate.

SAFETY: one throwaway book of this module's own making, and a translation job INSERTed against it
that references only that book's chapter. Torn down in a finally. Nothing pre-existing is touched,
and no confirm token is redeemed.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.eval.tool_liveness.mcp_direct import MCPDirect, MCPToolError  # noqa: E402
from scripts.toolloop.provision import Throwaway  # noqa: E402

USER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
MODEL = "019ebb72-27a2-72f3-a42d-d2d0e0ded179"

_INSERT = """INSERT INTO translation_jobs
  (job_id, book_id, owner_user_id, status, target_language, model_source, model_ref,
   system_prompt, user_prompt_tpl, chapter_ids, total_chapters)
VALUES ('{job}', '{book}', '{user}', 'paused', 'vi', 'user_model', '{model}',
        'sys', 'tpl', ARRAY['{chapter}']::uuid[], 1)"""


def _psql(sql: str) -> str:
    out = subprocess.run(
        ["docker", "exec", "infra-postgres-1", "psql", "-U", "loreweave",
         "-d", "loreweave_translation", "-tAc", sql],
        capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise RuntimeError(f"psql failed: {out.stderr.strip()[:300]}")
    return out.stdout.strip()


def _call(mcp: MCPDirect, job: str, action: str) -> dict:
    try:
        res = mcp.call("translation_job_control", {"job_id": job, "action": action})
    except MCPToolError as exc:
        return {"verdict": "refused", "detail": str(exc)[:260]}
    blob = json.dumps(res, ensure_ascii=False)
    return {
        "verdict": "MINTED a confirm token" if "confirm_token" in blob else "returned without a token",
        "has_cost_estimate": any(k in blob for k in ("cost", "estimate", "usd")),
        "detail": blob[:300],
    }


def main() -> int:
    mcp = MCPDirect()
    fx = Throwaway("tjc-enum", mcp=mcp).build()
    job = str(uuid.uuid4())
    out: dict[str, dict] = {}
    try:
        _psql(_INSERT.format(job=job, book=fx.book_id, user=USER, model=MODEL,
                             chapter=fx.chapter_id))
        status = _psql(f"SELECT status FROM translation_jobs WHERE job_id='{job}'")
        out["_fixture"] = {"job_id": job, "book_id": fx.book_id, "seeded_status": status}

        for action in ("resume", "retry"):
            out[action] = _call(mcp, job, action)
            out[action]["asked"] = (
                f"the COSTLY half of the enum: action={action}, which the tool's own description "
                "says re-spends money and must return an estimate + confirm token")

        # The cheap half, for contrast - it applies IMMEDIATELY, so it is the one that can change
        # the store without a gate. Run last so it cannot disturb the two above.
        out["pause"] = _call(mcp, job, "pause")
        out["pause"]["asked"] = "the cheap half: action=pause, which the description says applies now"
        out["_after"] = {"status": _psql(f"SELECT status FROM translation_jobs WHERE job_id='{job}'")}
        out["_not_done"] = {
            "redeemed_any_token": False,
            "why": ("Redemption is what spends. The tool is designed not to run until confirmed, so "
                    "the branch is exercised UP TO the gate and no further - stated here rather "
                    "than left for a reader to assume."),
        }
    finally:
        try:
            _psql(f"DELETE FROM translation_jobs WHERE job_id='{job}'")
        except Exception as exc:  # noqa: BLE001
            print(f"job cleanup failed for {job}: {exc}", file=sys.stderr)
        try:
            fx.teardown()
        except Exception as exc:  # noqa: BLE001
            print(f"teardown failed for {fx.book_id}: {exc}", file=sys.stderr)

    for k, v in out.items():
        if k.startswith("_"):
            print(f"  {k:9s} {json.dumps(v, ensure_ascii=False)[:150]}")
            continue
        print(f"  {k:9s} {v['verdict']:24s} cost_estimate={v.get('has_cost_estimate')}  "
              f"{v['detail'][:110]}")
    dest = ROOT / "docs" / "eval" / "toolloop" / "2026-08-14" / "translation-enum-probe.json"
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
