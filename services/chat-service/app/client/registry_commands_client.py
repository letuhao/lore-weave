"""HTTP client + pure expander for agent-registry-service's /internal/commands (P4).

A user-authored slash command (`/name args`) at the start of a chat message expands
its template BEFORE the turn (server-side default). Graceful degradation is the
contract (mirrors user_skills_client): any failure returns NO commands and the
message passes through unchanged — a command is an enrichment, never load-bearing.

Response shape from /internal/commands:
  { "catalog_version": <int>,
    "commands": [{name, description, arg_schema, template_md, expand_side, tier}, ...] }
"""

from __future__ import annotations

import logging
import re

import httpx

from app.config import settings
from app.middleware.trace_id import current_trace_id

logger = logging.getLogger(__name__)

__all__ = [
    "CommandsClient",
    "expand_command",
    "looks_like_command",
    "RESERVED_COMMANDS",
    "init_commands_client",
    "close_commands_client",
    "get_commands_client",
]

# The fixed inline parses (parse_inline_effort + manual routes) — a user command can
# never shadow these (agent-registry rejects them at create, mirrored here so we never
# even fetch for a built-in-looking message).
RESERVED_COMMANDS = frozenset(
    {"think", "no_think", "no_thinking", "effort", "compact", "clear", "model", "help"}
)

_CMD_RE = re.compile(r"^/([a-z0-9][a-z0-9-]{0,31})(?:\s+(.*))?$", re.DOTALL)
_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def looks_like_command(text: str) -> bool:
    """Cheap gate: a leading /<name> that is NOT a reserved built-in. Lets a normal
    turn skip the registry fetch entirely."""
    if not text:
        return False
    m = _CMD_RE.match(text.lstrip())
    if not m:
        return False
    return m.group(1) not in RESERVED_COMMANDS


def _substitute(template: str, args: str, arg_schema: dict) -> str:
    """Fill {{args}}, positional {{1}}/{{2}}, and named {{key}} (from arg_schema
    property order, last key soaks the remainder). Unknown placeholders → ''."""
    tokens = args.split()
    mapping: dict[str, str] = {"args": args}
    for i, tok in enumerate(tokens, 1):
        mapping[str(i)] = tok
    props = list((arg_schema.get("properties") or {}).keys()) if isinstance(arg_schema, dict) else []
    for i, key in enumerate(props):
        if i < len(props) - 1:
            mapping[key] = tokens[i] if i < len(tokens) else ""
        else:  # last named arg takes the rest
            mapping[key] = " ".join(tokens[i:]) if i < len(tokens) else ""
    return _PLACEHOLDER_RE.sub(lambda m: mapping.get(m.group(1).strip(), ""), template)


def expand_command(text: str, commands: list[dict]) -> tuple[str, str | None]:
    """If `text` starts with a known `/name`, return (expanded_template, name).
    Otherwise (text, None). Pure — the caller supplies the resolved command list."""
    if not text:
        return text, None
    m = _CMD_RE.match(text.lstrip())
    if not m:
        return text, None
    name, args = m.group(1), (m.group(2) or "").strip()
    if name in RESERVED_COMMANDS:
        return text, None
    cmd = next((c for c in commands if isinstance(c, dict) and c.get("name") == name), None)
    if not cmd or not cmd.get("template_md"):
        return text, None
    schema = cmd.get("arg_schema") or {}
    return _substitute(str(cmd["template_md"]), args, schema), name


class CommandsClient:
    def __init__(self, base_url: str, internal_token: str, timeout_s: float = 2.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s),
            headers={"X-Internal-Token": internal_token},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get_commands(self, user_id: str, *, book_id: str = "") -> list[dict]:
        """GET /internal/commands — returns the command list, [] on ANY failure."""
        if not user_id:
            return []
        params = {"user_id": user_id}
        if book_id:
            params["book_id"] = book_id
        tid = current_trace_id()
        headers = {"X-Trace-Id": tid} if tid else None
        try:
            resp = await self._http.get(f"{self._base_url}/internal/commands", params=params, headers=headers)
        except Exception as exc:  # noqa: BLE001 — degrade, don't raise into the turn
            logger.warning("commands unavailable (pass-through): %s", type(exc).__name__)
            return []
        if resp.status_code != 200:
            return []
        try:
            data = resp.json()
        except Exception:  # noqa: BLE001
            return []
        cmds = data.get("commands") if isinstance(data, dict) else None
        return [c for c in cmds if isinstance(c, dict) and isinstance(c.get("name"), str)] if isinstance(cmds, list) else []


_client: CommandsClient | None = None


def init_commands_client() -> CommandsClient:
    global _client
    if _client is None:
        _client = CommandsClient(
            base_url=settings.agent_registry_url,
            internal_token=settings.internal_service_token,
            timeout_s=settings.agent_registry_timeout_s,
        )
    return _client


async def close_commands_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def get_commands_client() -> CommandsClient:
    return _client or init_commands_client()
