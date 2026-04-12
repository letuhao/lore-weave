package migrate

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5/pgxpool"
)

const schemaSQL = `
-- Real-time book stats, updated incrementally from events
CREATE TABLE IF NOT EXISTS book_stats (
  book_id            UUID PRIMARY KEY,
  owner_user_id      UUID NOT NULL,
  title              TEXT NOT NULL DEFAULT '',
  genre_tags         TEXT[] NOT NULL DEFAULT '{}',
  original_language  TEXT,
  total_views        BIGINT NOT NULL DEFAULT 0,
  views_7d           BIGINT NOT NULL DEFAULT 0,
  views_30d          BIGINT NOT NULL DEFAULT 0,
  unique_readers     BIGINT NOT NULL DEFAULT 0,
  avg_time_ms        BIGINT NOT NULL DEFAULT 0,
  avg_scroll_depth   DOUBLE PRECISION NOT NULL DEFAULT 0,
  chapter_count      INT NOT NULL DEFAULT 0,
  book_created_at    TIMESTAMPTZ,
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_bs_views_all ON book_stats(total_views DESC);
CREATE INDEX IF NOT EXISTS idx_bs_views_7d ON book_stats(views_7d DESC);
CREATE INDEX IF NOT EXISTS idx_bs_views_30d ON book_stats(views_30d DESC);
CREATE INDEX IF NOT EXISTS idx_bs_readers ON book_stats(unique_readers DESC);
CREATE INDEX IF NOT EXISTS idx_bs_owner ON book_stats(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_bs_genre ON book_stats USING GIN(genre_tags);

-- Raw view events (for time-windowed recalculation)
CREATE TABLE IF NOT EXISTS view_events (
  id         UUID PRIMARY KEY DEFAULT uuidv7(),
  book_id    UUID NOT NULL,
  user_id    UUID,
  viewed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ve_book_time ON view_events(book_id, viewed_at DESC);
CREATE INDEX IF NOT EXISTS idx_ve_time ON view_events(viewed_at DESC);

-- Raw reading events (for engagement calculation)
CREATE TABLE IF NOT EXISTS reading_events (
  id            UUID PRIMARY KEY DEFAULT uuidv7(),
  book_id       UUID NOT NULL,
  chapter_id    UUID NOT NULL,
  user_id       UUID NOT NULL,
  time_spent_ms BIGINT NOT NULL DEFAULT 0,
  scroll_depth  DOUBLE PRECISION NOT NULL DEFAULT 0,
  recorded_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_re_book ON reading_events(book_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_re_user ON reading_events(user_id, recorded_at DESC);

-- Author aggregates (recalculated from book_stats)
CREATE TABLE IF NOT EXISTS author_stats (
  user_id        UUID PRIMARY KEY,
  total_books    INT NOT NULL DEFAULT 0,
  total_views    BIGINT NOT NULL DEFAULT 0,
  views_7d       BIGINT NOT NULL DEFAULT 0,
  views_30d      BIGINT NOT NULL DEFAULT 0,
  total_readers  BIGINT NOT NULL DEFAULT 0,
  avg_time_ms    BIGINT NOT NULL DEFAULT 0,
  total_chapters INT NOT NULL DEFAULT 0,
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_as_views ON author_stats(total_views DESC);
CREATE INDEX IF NOT EXISTS idx_as_views_7d ON author_stats(views_7d DESC);

-- Social data columns on book_stats (populated by future social service via message bus)
ALTER TABLE book_stats ADD COLUMN IF NOT EXISTS avg_rating DOUBLE PRECISION NOT NULL DEFAULT 0;
ALTER TABLE book_stats ADD COLUMN IF NOT EXISTS rating_count INT NOT NULL DEFAULT 0;
ALTER TABLE book_stats ADD COLUMN IF NOT EXISTS favorites_count INT NOT NULL DEFAULT 0;
ALTER TABLE book_stats ADD COLUMN IF NOT EXISTS rank_change INT NOT NULL DEFAULT 0;
ALTER TABLE book_stats ADD COLUMN IF NOT EXISTS has_cover BOOLEAN NOT NULL DEFAULT false;
CREATE INDEX IF NOT EXISTS idx_bs_rating ON book_stats(avg_rating DESC);
CREATE INDEX IF NOT EXISTS idx_bs_favorites ON book_stats(favorites_count DESC);

-- Social data column on author_stats
ALTER TABLE author_stats ADD COLUMN IF NOT EXISTS avg_rating DOUBLE PRECISION NOT NULL DEFAULT 0;

-- Rank snapshots (for computing trend arrows)
CREATE TABLE IF NOT EXISTS rank_snapshots (
  id         UUID PRIMARY KEY DEFAULT uuidv7(),
  book_id    UUID NOT NULL,
  position   INT NOT NULL,
  period     TEXT NOT NULL,
  snapped_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_rs_book_period ON rank_snapshots(book_id, period, snapped_at DESC);

-- Raw rating events from social service
CREATE TABLE IF NOT EXISTS rating_events (
  id        UUID PRIMARY KEY DEFAULT uuidv7(),
  book_id   UUID NOT NULL,
  user_id   UUID NOT NULL,
  rating    DOUBLE PRECISION NOT NULL,
  rated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_rate_book ON rating_events(book_id);

-- Raw favorite events from social service
CREATE TABLE IF NOT EXISTS favorite_events (
  id        UUID PRIMARY KEY DEFAULT uuidv7(),
  book_id   UUID NOT NULL,
  user_id   UUID NOT NULL,
  action    TEXT NOT NULL,
  acted_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_fav_book ON favorite_events(book_id);

-- Translator stats (populated from translation_events)
CREATE TABLE IF NOT EXISTS translator_stats (
  user_id              UUID PRIMARY KEY,
  total_translations   INT NOT NULL DEFAULT 0,
  total_chapters_done  INT NOT NULL DEFAULT 0,
  translations_7d      INT NOT NULL DEFAULT 0,
  translations_30d     INT NOT NULL DEFAULT 0,
  languages            TEXT[] NOT NULL DEFAULT '{}',
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ts_total ON translator_stats(total_chapters_done DESC);
CREATE INDEX IF NOT EXISTS idx_ts_7d ON translator_stats(translations_7d DESC);

-- Raw translation completion events (from translation-service via outbox relay)
CREATE TABLE IF NOT EXISTS translation_events (
  id               UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id          UUID NOT NULL,
  book_id          UUID NOT NULL,
  chapter_id       UUID NOT NULL,
  target_language  TEXT NOT NULL,
  status           TEXT NOT NULL,
  input_tokens     INT,
  output_tokens    INT,
  translated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_te_user ON translation_events(user_id, translated_at DESC);
CREATE INDEX IF NOT EXISTS idx_te_book ON translation_events(book_id);
CREATE INDEX IF NOT EXISTS idx_te_time ON translation_events(translated_at DESC);

-- Daily rollups for time-series charts (author dashboard)
CREATE TABLE IF NOT EXISTS daily_book_rollups (
  book_id      UUID NOT NULL,
  day          DATE NOT NULL,
  views        BIGINT NOT NULL DEFAULT 0,
  readers      BIGINT NOT NULL DEFAULT 0,
  avg_time_ms  BIGINT NOT NULL DEFAULT 0,
  PRIMARY KEY (book_id, day)
);
CREATE INDEX IF NOT EXISTS idx_dbr_day ON daily_book_rollups(day DESC);

-- Display name denormalization (for leaderboard rendering without N auth calls)
ALTER TABLE book_stats ADD COLUMN IF NOT EXISTS owner_display_name TEXT NOT NULL DEFAULT '';
ALTER TABLE author_stats ADD COLUMN IF NOT EXISTS display_name TEXT NOT NULL DEFAULT '';
ALTER TABLE translator_stats ADD COLUMN IF NOT EXISTS display_name TEXT NOT NULL DEFAULT '';

-- Translation count per book (distinct languages with completed translations)
ALTER TABLE book_stats ADD COLUMN IF NOT EXISTS translation_count INT NOT NULL DEFAULT 0;

-- Voice Pipeline V2: raw voice turn events for analytics
CREATE TABLE IF NOT EXISTS voice_turn_events (
  id                       UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id                  UUID NOT NULL,
  session_id               UUID NOT NULL,
  stt_success              BOOLEAN NOT NULL,
  stt_duration_ms          INT NOT NULL DEFAULT 0,
  speech_duration_ms       INT,
  audio_size_kb            INT,
  llm_first_token_ms       INT,
  tts_sentence_count       INT NOT NULL DEFAULT 0,
  tts_skipped_count        INT NOT NULL DEFAULT 0,
  threshold_silence_frames INT NOT NULL DEFAULT 8,
  threshold_min_duration_ms INT NOT NULL DEFAULT 500,
  recorded_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_vte_user ON voice_turn_events(user_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_vte_time ON voice_turn_events(recorded_at DESC);

-- Voice Pipeline V2: per-user aggregated voice stats (for adaptive thresholds)
CREATE TABLE IF NOT EXISTS voice_user_stats (
  user_id                  UUID PRIMARY KEY,
  total_turns              INT NOT NULL DEFAULT 0,
  successful_turns         INT NOT NULL DEFAULT 0,
  failed_turns             INT NOT NULL DEFAULT 0,
  avg_stt_duration_ms      INT NOT NULL DEFAULT 0,
  avg_speech_duration_ms   INT NOT NULL DEFAULT 0,
  avg_llm_first_token_ms   INT NOT NULL DEFAULT 0,
  misfire_rate             DOUBLE PRECISION NOT NULL DEFAULT 0,
  recommended_silence_frames INT NOT NULL DEFAULT 8,
  recommended_min_duration_ms INT NOT NULL DEFAULT 500,
  updated_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);
`

func Up(ctx context.Context, pool *pgxpool.Pool) error {
	if _, err := pool.Exec(ctx, schemaSQL); err != nil {
		return fmt.Errorf("migrate: %w", err)
	}
	return nil
}
