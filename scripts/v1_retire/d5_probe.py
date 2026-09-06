"""D5 probe — run inside services/chat-service. Prints OK / FAIL:<reason>.

Behavioural: ACTUALLY CALLS tool_load_result with a legacy name absent from the turn catalogue
(the state drop_superseded_tools leaves) and requires a refusal that NAMES the successor. Reading
the source for the string "deprecated" would pass on a comment.
"""
import os
import sys

# sys.path[0] is THIS script's directory, not the cwd it was launched from.
sys.path.insert(0, os.getcwd())

from app.services.tool_discovery import tool_load_result

payload, _ = tool_load_result(
    [{"function": {"name": "book_read", "description": "read", "parameters": {}}}],
    names=["book_get"],
    legacy_index={"book_get": "book_read"},
)
problems = []
if "book_get" in (payload.get("not_found") or []):
    problems.append("a deprecated tool was reported as not_found (the 'no such tool' lie)")
dep = payload.get("deprecated") or []
if not any(d.get("name") == "book_get" for d in dep):
    problems.append("no `deprecated` entry naming the tool")
if not any(d.get("superseded_by") == "book_read" for d in dep):
    problems.append("the refusal does not name the successor")
note = payload.get("deprecated_note") or ""
if "book_read" not in note:
    problems.append("deprecated_note does not name the successor")
print("OK" if not problems else "FAIL:" + "; ".join(problems))
