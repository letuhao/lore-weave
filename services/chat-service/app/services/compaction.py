"""chat-service compaction — MOVED to the shared Context Budget kernel (T3.3b).

The implementation now lives in `loreweave_context.compaction` (provider-agnostic tiered
clear→summarize→truncate + the T6/D6 breadcrumb/recovery-hint). This module re-exports the
public API so every existing chat-service importer — stream_service, the sessions router,
compact_service, and the tests — is unchanged. New code should import from
`loreweave_context` directly. The summarizer (compact_service FACTS/SYNOPSIS) is still
INJECTED by the caller, so no chat dependency leaks into the kernel.
"""
from loreweave_context.compaction import (  # noqa: F401  (re-export shim)
    COMPACT_TRIGGER_RATIO,
    DEFAULT_EXCLUDE_TOOLS,
    CompactionReport,
    CompactionStrategy,
    Summarizer,
    compact_messages,
    extract_breadcrumb,
    inject_recovery_hint,
    recovery_hint_message,
    summary_message,
    _PLACEHOLDER,
    _DUP_PLACEHOLDER,
)

__all__ = [
    "COMPACT_TRIGGER_RATIO",
    "DEFAULT_EXCLUDE_TOOLS",
    "CompactionReport",
    "CompactionStrategy",
    "Summarizer",
    "compact_messages",
    "extract_breadcrumb",
    "inject_recovery_hint",
    "recovery_hint_message",
    "summary_message",
    "_PLACEHOLDER",
    "_DUP_PLACEHOLDER",
]
