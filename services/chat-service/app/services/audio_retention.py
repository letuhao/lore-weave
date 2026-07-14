"""WS-4.3 — per-user voice-audio retention.

Audio retention was a single global `AUDIO_TTL_HOURS` env applied to every user's
segments. Retention is a privacy choice two users legitimately differ on, so it is a
per-user setting (`user_chat_ai_prefs.voice.audio_retention_hours`) — NOT an env flag
(Settings & Configuration Boundary). The env stays as the deploy CEILING: a user may
narrow retention (keep audio for LESS time = more private) but never exceed the
platform max. Effective TTL per segment = LEAST(ceiling, user_choice ?? ceiling); a
user choice of 0 means "don't retain" (deleted on the next sweep).

Both the periodic sweeper (`main._audio_cleanup_loop`) and the on-demand
`POST /voice/cleanup` route call `delete_expired_audio`, so the resolution lives in
ONE place (a second, subtly-different copy is how the two would drift).
"""
from __future__ import annotations

import asyncpg

# The per-user retention setting's home key inside the voice blob.
AUDIO_RETENTION_KEY = "audio_retention_hours"

# A single DELETE that resolves each segment's TTL against its owner's setting
# (LEFT JOIN so a user with no prefs row falls back to the ceiling), deletes the
# expired rows, and RETURNs their object keys so the caller can delete the MinIO
# objects. `make_interval(hours => 0)` = delete-on-next-sweep ("don't retain").
_DELETE_EXPIRED_SQL = """
DELETE FROM message_audio_segments mas
USING (
  SELECT s.id,
         LEAST(
           $1::int,
           -- SAFE cast (cold-review L3): a single non-numeric stored value would otherwise
           -- raise and abort the WHOLE sweep platform-wide. Guard with a digit regex so one
           -- bad/out-of-band row can't poison every user's retention.
           COALESCE(
             CASE WHEN p.voice ->> 'audio_retention_hours' ~ '^[0-9]+$'
                  THEN (p.voice ->> 'audio_retention_hours')::int END,
             $1::int)
         ) AS ttl
  FROM message_audio_segments s
  LEFT JOIN user_chat_ai_prefs p ON p.owner_user_id = s.user_id
) eff
WHERE mas.id = eff.id
  AND mas.created_at < now() - make_interval(hours => eff.ttl)
RETURNING mas.object_key
"""


async def delete_expired_audio(pool: asyncpg.Pool, ceiling_hours: int) -> list[str]:
    """Delete every audio segment older than its owner's effective TTL and return
    the deleted object_keys (for MinIO cleanup). `ceiling_hours` is the deploy max."""
    rows = await pool.fetch(_DELETE_EXPIRED_SQL, ceiling_hours)
    return [r["object_key"] for r in rows]
