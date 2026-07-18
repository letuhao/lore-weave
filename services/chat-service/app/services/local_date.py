"""DBT-11 / D-R14 (spec 01) — resolve the LOCAL calendar day a chat message belongs to.

The distiller ("End my day", and in Phase 3 the *scheduled* end-of-day) buckets a day's
assistant messages by ``chat_messages.local_date``. That day must be the user's LOCAL day,
not the server's UTC day, or a late-night message for a non-UTC user lands in the wrong
diary entry — a mistake the user is not present to catch once distillation is unattended.

Server-authoritative by design: the timezone is resolved from the user's stored preference,
never taken from a client-supplied date (which a caller could forge to mis-bucket history).
Degrades safely to UTC when the timezone is unset/blank/invalid (D-R14) — the same day the
DB DEFAULT would have stamped, so an un-set-timezone user is no worse off than before.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def compute_local_date(tz_name: str | None, now_utc: datetime | None = None) -> date:
    """The user's local calendar day for a message written at ``now_utc``.

    ``now_utc`` defaults to the current instant; a naive datetime is assumed UTC.
    Falls back to the UTC day when ``tz_name`` is None/blank/invalid.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    elif now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)

    if tz_name:
        try:
            return now_utc.astimezone(ZoneInfo(tz_name)).date()
        except (ZoneInfoNotFoundError, ValueError, KeyError):
            # An unknown/garbage tz must NOT raise into the message-write path —
            # degrade to UTC (no-silent-success is satisfied by the caller logging
            # the fallback if it cares; here correctness-over-crash wins).
            pass
    return now_utc.astimezone(timezone.utc).date()
