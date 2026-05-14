#!/usr/bin/env python3
"""mcp-query.py — REST CLI wrapper for ContextHub MCP.

Sub-agents (Adversary, Scope Guard, Scribe) and `workflow-gate.py` shell
out to this helper for ContextHub interactions instead of relying on
MCP tool inheritance from the host agent's session config.

Stdlib-only (urllib + json + argparse) — zero extra deps.

Environment variables:
  CONTEXTHUB_API_URL    Base URL (default: http://localhost:3001)
  CONTEXTHUB_PROJECT_ID Project slug (default: mmo-rpg-zone-map-design-non-human-in-loop)

Exit codes:
  0  success
  1  bad request / 4xx / user-input error
  2  transport error / server down / 5xx
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_BASE_URL = "http://localhost:3001"
DEFAULT_PROJECT_ID = "mmo-rpg-zone-map-design-non-human-in-loop"
TIMEOUT_SECONDS = 60  # embedding-generating ops (add_lesson) can take 30s+ cold; bumped from 30 after AC-7 timing measurement showed 30.169s on cold path


def _env_base_url() -> str:
    return os.environ.get("CONTEXTHUB_API_URL", DEFAULT_BASE_URL).rstrip("/")


def _env_project_id() -> str:
    return os.environ.get("CONTEXTHUB_PROJECT_ID", DEFAULT_PROJECT_ID)


def _request(method: str, path: str, body: dict | None = None, params: dict | None = None) -> tuple[int, Any]:
    """Issue HTTP request. Returns (status_code, parsed_json_or_text)."""
    url = _env_base_url() + path
    if params:
        clean = {k: v for k, v in params.items() if v is not None}
        if clean:
            url = url + "?" + urllib.parse.urlencode(clean)

    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw
    except urllib.error.URLError as e:
        print(f"ContextHub not reachable at {_env_base_url()} — {e.reason}", file=sys.stderr)
        sys.exit(2)
    except TimeoutError:
        print(f"ContextHub timeout (>{TIMEOUT_SECONDS}s) at {_env_base_url()}", file=sys.stderr)
        sys.exit(2)
    except (ConnectionError, http.client.RemoteDisconnected, http.client.HTTPException) as e:
        print(f"ContextHub connection lost mid-request ({type(e).__name__}: {e}) — server may be restarting or overloaded", file=sys.stderr)
        sys.exit(2)


def _emit(payload: Any, fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    # summary mode — readable formatting
    if isinstance(payload, dict):
        for k, v in payload.items():
            if isinstance(v, list):
                print(f"{k}: ({len(v)} items)")
                for i, item in enumerate(v[:10], 1):
                    if isinstance(item, dict):
                        title = item.get("title") or item.get("note") or item.get("rule") or item.get("path") or json.dumps(item)[:80]
                        print(f"  {i}. {title}")
                    else:
                        print(f"  {i}. {str(item)[:120]}")
                if len(v) > 10:
                    print(f"  ... ({len(v) - 10} more)")
            elif isinstance(v, dict):
                print(f"{k}: {json.dumps(v)[:200]}")
            else:
                print(f"{k}: {v}")
    elif isinstance(payload, list):
        print(f"({len(payload)} items)")
        for i, item in enumerate(payload[:10], 1):
            if isinstance(item, dict):
                title = item.get("title") or item.get("note") or json.dumps(item)[:80]
                print(f"  {i}. {title}")
            else:
                print(f"  {i}. {str(item)[:120]}")
    else:
        print(payload)


# --- verb implementations ---

def cmd_ping(args: argparse.Namespace) -> None:
    status, body = _request("GET", "/api/lessons", params={"project_id": _env_project_id(), "limit": 1})
    if status == 200:
        print("OK")
        sys.exit(0)
    print(f"ContextHub unhealthy (HTTP {status}): {body}", file=sys.stderr)
    sys.exit(2 if status >= 500 else 1)


def cmd_search_lessons(args: argparse.Namespace) -> None:
    body: dict[str, Any] = {
        "project_id": _env_project_id(),
        "query": args.query,
        "limit": args.limit,
    }
    filters: dict[str, Any] = {}
    if args.type:
        filters["lesson_type"] = args.type
    if args.tags:
        filters["tags_any"] = [t.strip() for t in args.tags.split(",") if t.strip()]
    if filters:
        body["filters"] = filters

    status, payload = _request("POST", "/api/lessons/search", body=body)
    if status >= 400:
        print(f"search_lessons failed (HTTP {status}): {payload}", file=sys.stderr)
        sys.exit(1 if status < 500 else 2)
    _emit(payload, args.format)


def cmd_add_lesson(args: argparse.Namespace) -> None:
    body = {
        "project_id": _env_project_id(),
        "lesson_type": args.type,
        "title": args.title,
        "content": args.content,
    }
    if args.tags:
        body["tags"] = [t.strip() for t in args.tags.split(",") if t.strip()]
    if args.source_refs:
        body["source_refs"] = [s.strip() for s in args.source_refs.split(",") if s.strip()]

    status, payload = _request("POST", "/api/lessons", body=body)
    if status >= 400:
        print(f"add_lesson failed (HTTP {status}): {payload}", file=sys.stderr)
        sys.exit(1 if status < 500 else 2)
    if args.format == "json":
        _emit(payload, "json")
    else:
        lesson_id = payload.get("id") or payload.get("lesson_id") if isinstance(payload, dict) else None
        if lesson_id:
            print(lesson_id)
        else:
            _emit(payload, "summary")


def cmd_list_lessons(args: argparse.Namespace) -> None:
    params = {
        "project_id": _env_project_id(),
        "limit": args.limit,
    }
    if args.type:
        params["lesson_type"] = args.type
    status, payload = _request("GET", "/api/lessons", params=params)
    if status >= 400:
        print(f"list_lessons failed (HTTP {status}): {payload}", file=sys.stderr)
        sys.exit(1 if status < 500 else 2)
    _emit(payload, args.format)


def cmd_check_guardrails(args: argparse.Namespace) -> None:
    body = {
        "project_id": _env_project_id(),
        "action_context": {"action": args.action},
    }
    status, payload = _request("POST", "/api/guardrails/check", body=body)
    if status >= 400:
        print(f"check_guardrails failed (HTTP {status}): {payload}", file=sys.stderr)
        sys.exit(1 if status < 500 else 2)
    _emit(payload, args.format)


def cmd_search_code_tiered(args: argparse.Namespace) -> None:
    body: dict[str, Any] = {
        "project_id": _env_project_id(),
        "query": args.query,
    }
    if args.kind:
        body["kind"] = args.kind
    if args.max_files:
        body["max_files"] = args.max_files
    status, payload = _request("POST", "/api/search/code-tiered", body=body)
    if status >= 400:
        print(f"search_code_tiered failed (HTTP {status}): {payload}", file=sys.stderr)
        sys.exit(1 if status < 500 else 2)
    _emit(payload, args.format)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mcp-query.py",
        description="REST CLI wrapper for ContextHub MCP. Set CONTEXTHUB_API_URL + CONTEXTHUB_PROJECT_ID env to override defaults.",
    )
    # --format may appear EITHER before or after the subcommand. Defined on
    # both top-level and each subparser so users can write either form.
    def _add_format(p: argparse.ArgumentParser) -> None:
        p.add_argument("--format", choices=["summary", "json"], default="summary", help="Output format (default: summary)")

    _add_format(parser)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ping = sub.add_parser("ping", help="Check ContextHub reachability (GET /api/lessons?limit=1)")
    _add_format(p_ping)
    p_ping.set_defaults(func=cmd_ping)

    sl = sub.add_parser("search_lessons", help="Semantic search over lessons")
    sl.add_argument("query", help="Natural language query")
    sl.add_argument("--type", help="Filter by lesson_type (decision|preference|guardrail|workaround|general_note)")
    sl.add_argument("--tags", help="Comma-separated tags (any-overlap filter)")
    sl.add_argument("--limit", type=int, default=10)
    _add_format(sl)
    sl.set_defaults(func=cmd_search_lessons)

    al = sub.add_parser("add_lesson", help="Persist a new lesson")
    al.add_argument("--type", required=True, choices=["decision", "preference", "guardrail", "workaround", "general_note"])
    al.add_argument("--title", required=True)
    al.add_argument("--content", required=True)
    al.add_argument("--tags", help="Comma-separated tags")
    al.add_argument("--source-refs", help="Comma-separated source references")
    _add_format(al)
    al.set_defaults(func=cmd_add_lesson)

    ll = sub.add_parser("list_lessons", help="List lessons (cursor-paginated)")
    ll.add_argument("--limit", type=int, default=20)
    ll.add_argument("--type", help="Filter by lesson_type")
    _add_format(ll)
    ll.set_defaults(func=cmd_list_lessons)

    cg = sub.add_parser("check_guardrails", help="Evaluate guardrails for a proposed action")
    cg.add_argument("action", help="Action string (e.g. 'git commit', 'git push to main')")
    _add_format(cg)
    cg.set_defaults(func=cmd_check_guardrails)

    sc = sub.add_parser("search_code_tiered", help="Multi-tier code search (ripgrep + KG + semantic)")
    sc.add_argument("query", help="Identifier, file path, or natural language")
    sc.add_argument("--kind", help="Data kind filter (source|test|doc|config|...)")
    sc.add_argument("--max-files", type=int, default=20)
    _add_format(sc)
    sc.set_defaults(func=cmd_search_code_tiered)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
