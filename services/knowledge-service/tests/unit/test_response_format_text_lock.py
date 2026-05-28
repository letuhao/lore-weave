"""Regression-lock — every LLM extractor + judge sends response_format=text.

Background: newer LM Studio (post-2026-05-25) rejects
`response_format: {"type": "json_object"}` with HTTP 400
(`'response_format.type' must be 'json_schema' or 'text'`). Knowledge-service
extractors migrated from the gateway proxy path (which normalized json_object
→ text via `normalizeResponseFormatForKind` in server.go, commit db065152)
to the async jobs path (`/internal/llm/jobs` → adapters.go), where no
equivalent normalization exists. Every extractor + the LLM-judge therefore
needs to send `text` natively so LM Studio doesn't 400 on the request.

The fix is mechanical (string swap), but easy to revert by accident on a
future "let's tighten output enforcement" PR — and the next time we'd notice
is when a live smoke against LM Studio fails. This grep-lock prevents that
silent revert by failing at unit-suite time (which runs in the Dockerfile
test stage — see services/knowledge-service/Dockerfile line 33-37).

Implementation notes:
- SDK extractor sources are located via module-import + `__file__`, so the
  test works both in-monorepo and inside the knowledge-service test
  container (where the SDK is pip-installed under site-packages from the
  same source tree).
- The regex tolerates formatting variation (whitespace, line breaks within
  the dict literal) — only the field name + type value are locked.

If you intentionally re-introduce `json_object` (e.g. because gateway-side
normalization gets ported back to the async path — see
docs/plans/2026-05-26-response-format-text-for-lm-studio.md follow-up
D-LM-STUDIO-RESPONSE-FORMAT-ASYNC-PATH), delete this test in the same
commit and reference the gateway PR that re-enables proxy-side fix.
See `feedback_audit_all_callsites_when_adding_optional_kwarg` for the audit
pattern this test implements.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Pattern: `"response_format": {"type": "text"}` with whitespace tolerance.
# Locks (a) the field is present and (b) its type is `text`. Will reject
# both `json_object` and the bare-field-removed case.
_RESPONSE_FORMAT_TEXT_RE = re.compile(
    r'"response_format"\s*:\s*\{\s*"type"\s*:\s*"text"\s*\}'
)
# Negative pattern — the LM-Studio-breaking value must not appear.
_RESPONSE_FORMAT_JSON_OBJECT_RE = re.compile(
    r'"response_format"\s*:\s*\{\s*"type"\s*:\s*"json_object"\s*\}'
)


def _sdk_source(module_path: str) -> tuple[str, Path]:
    """Import a module and return (source_text, source_path).

    Locates the source via `__file__` rather than repo-relative paths so
    the test passes both in-monorepo (running pytest from repo root) and
    in the knowledge-service Docker test container (where the SDK is
    pip-installed under site-packages).
    """
    import importlib
    module = importlib.import_module(module_path)
    path = Path(module.__file__).resolve()
    return path.read_text(encoding="utf-8"), path


def _judge_source() -> tuple[str, Path]:
    """Locate llm_judge.py relative to this test file.

    Layout assumption: this file at services/knowledge-service/tests/unit/
    and llm_judge.py at services/knowledge-service/tests/quality/. Inside
    the Docker test container the same relative structure holds because
    the Dockerfile COPYs the full tests/ tree.
    """
    here = Path(__file__).resolve().parent
    judge_path = here.parent / "quality" / "llm_judge.py"
    return judge_path.read_text(encoding="utf-8"), judge_path


_SITES = (
    ("entity extractor", lambda: _sdk_source("loreweave_extraction.extractors.entity")),
    ("relation extractor", lambda: _sdk_source("loreweave_extraction.extractors.relation")),
    ("event extractor", lambda: _sdk_source("loreweave_extraction.extractors.event")),
    ("fact extractor", lambda: _sdk_source("loreweave_extraction.extractors.fact")),
    ("summarize extractor", lambda: _sdk_source("loreweave_extraction.extractors.summarize")),
    ("llm judge", _judge_source),
)


@pytest.mark.parametrize("label, loader", _SITES, ids=[s[0] for s in _SITES])
def test_response_format_is_text_not_json_object(
    label: str, loader: callable
) -> None:
    """Every extractor + judge must send `response_format: {"type": "text"}`,
    NOT json_object. LM Studio rejects json_object; OpenAI accepts text
    (default); Anthropic doesn't receive `response_format` at all
    (`anthropicAdapter.Stream` in adapters.go builds its own body without
    forwarding `response_format`). The prompts + the gateway aggregator's
    extractJSONObject helper (aggregator.go) handle JSON parsing including
    markdown ```json fences.
    """
    source, path = loader()
    assert not _RESPONSE_FORMAT_JSON_OBJECT_RE.search(source), (
        f"{label} at {path} still posts response_format=json_object, "
        f"which LM Studio rejects with HTTP 400 since ~2026-05-25. "
        f"Switch to {{'type': 'text'}} per "
        f"docs/plans/2026-05-26-response-format-text-for-lm-studio.md."
    )
    assert _RESPONSE_FORMAT_TEXT_RE.search(source), (
        f"{label} at {path} is missing the expected "
        f'`"response_format": {{"type": "text"}}` field. Either it was '
        f"deleted (unsafe — cloud providers no longer get a JSON output "
        f"hint via the field) or it was changed to a non-text value "
        f"(re-check against LM Studio's accepted set: json_schema, text)."
    )
