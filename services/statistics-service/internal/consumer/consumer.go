package consumer

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"

	"github.com/loreweave/statistics-service/internal/config"
)

const (
	eventStream      = "loreweave:events:chapter"
	voiceEventStream = "loreweave:events:voice"
	consumerGroup    = "statistics-service"
	consumerName     = "worker-1"
)

type Consumer struct {
	Pool           *pgxpool.Pool
	Redis          *redis.Client
	Cfg            *config.Config
	client         *http.Client
	lastSnapshotAt time.Time
}

// Run starts the Redis Streams consumer and periodic refresh loops.
func (c *Consumer) Run(ctx context.Context) {
	c.client = &http.Client{Timeout: 10 * time.Second}

	// Create consumer groups (ignore error if already exists)
	c.Redis.XGroupCreateMkStream(ctx, eventStream, consumerGroup, "0").Err()
	c.Redis.XGroupCreateMkStream(ctx, voiceEventStream, consumerGroup, "0").Err()

	// Start periodic windowed stats refresh
	go c.refreshLoop(ctx)
	// Start voice event consumer
	go c.runVoiceConsumer(ctx)

	slog.Info("statistics-consumer started", "stream", eventStream, "group", consumerGroup)

	for {
		select {
		case <-ctx.Done():
			slog.Info("statistics-consumer shutting down")
			return
		default:
		}

		results, err := c.Redis.XReadGroup(ctx, &redis.XReadGroupArgs{
			Group:    consumerGroup,
			Consumer: consumerName,
			Streams:  []string{eventStream, ">"},
			Count:    10,
			Block:    5 * time.Second,
		}).Result()
		if err != nil {
			if err == redis.Nil || strings.Contains(err.Error(), "context") {
				continue
			}
			slog.Error("statistics-consumer XREADGROUP", "error", err)
			time.Sleep(2 * time.Second)
			continue
		}

		for _, stream := range results {
			for _, msg := range stream.Messages {
				eventType, _ := msg.Values["event_type"].(string)
				payloadStr, _ := msg.Values["payload"].(string)

				switch eventType {
				case "book.viewed":
					c.handleBookViewed(ctx, payloadStr)
				case "reading.progress":
					c.handleReadingProgress(ctx, payloadStr)
				case "chapter.created":
					c.handleChapterCreated(ctx, payloadStr)
				case "chapter.trashed", "chapter.deleted":
					c.handleChapterRemoved(ctx, payloadStr)
				case "chapter.translated":
					c.handleChapterTranslated(ctx, payloadStr)
				case "book.rated":
					c.handleBookRated(ctx, payloadStr)
				case "book.favorited":
					c.handleBookFavorited(ctx, payloadStr)
				}

				c.Redis.XAck(ctx, eventStream, consumerGroup, msg.ID)
			}
		}
	}
}

func (c *Consumer) handleBookViewed(ctx context.Context, payloadStr string) {
	var p struct {
		BookID    string `json:"book_id"`
		UserID    string `json:"user_id"`
		SessionID string `json:"session_id"`
	}
	if err := json.Unmarshal([]byte(payloadStr), &p); err != nil {
		slog.Error("statistics: bad book.viewed payload", "error", err)
		return
	}

	bookID, err := uuid.Parse(p.BookID)
	if err != nil {
		return
	}

	var userID *uuid.UUID
	if p.UserID != "" {
		uid, err := uuid.Parse(p.UserID)
		if err == nil {
			userID = &uid
		}
	}

	// Insert raw view event
	_, _ = c.Pool.Exec(ctx, `INSERT INTO view_events (book_id, user_id) VALUES ($1, $2)`, bookID, userID)

	// Ensure book_stats row exists, increment total_views
	c.ensureBookStats(ctx, bookID)
	_, _ = c.Pool.Exec(ctx, `UPDATE book_stats SET total_views = total_views + 1, updated_at = now() WHERE book_id = $1`, bookID)
}

func (c *Consumer) handleReadingProgress(ctx context.Context, payloadStr string) {
	var p struct {
		BookID      string  `json:"book_id"`
		ChapterID   string  `json:"chapter_id"`
		UserID      string  `json:"user_id"`
		TimeSpentMs int64   `json:"time_spent_ms"`
		ScrollDepth float64 `json:"scroll_depth"`
	}
	if err := json.Unmarshal([]byte(payloadStr), &p); err != nil {
		slog.Error("statistics: bad reading.progress payload", "error", err)
		return
	}

	bookID, err := uuid.Parse(p.BookID)
	if err != nil {
		return
	}
	chapterID, err := uuid.Parse(p.ChapterID)
	if err != nil {
		return
	}
	userID, err := uuid.Parse(p.UserID)
	if err != nil {
		return
	}

	// Insert raw reading event (aggregates recalculated in refresh loop)
	_, _ = c.Pool.Exec(ctx, `INSERT INTO reading_events (book_id, chapter_id, user_id, time_spent_ms, scroll_depth) VALUES ($1, $2, $3, $4, $5)`,
		bookID, chapterID, userID, p.TimeSpentMs, p.ScrollDepth)

	// Ensure book_stats row exists
	c.ensureBookStats(ctx, bookID)
}

func (c *Consumer) handleChapterCreated(ctx context.Context, payloadStr string) {
	var p struct {
		BookID string `json:"book_id"`
	}
	if err := json.Unmarshal([]byte(payloadStr), &p); err != nil {
		return
	}
	bookID, err := uuid.Parse(p.BookID)
	if err != nil {
		return
	}
	c.ensureBookStats(ctx, bookID)
	// Refresh chapter count from book-service metadata
	c.refreshBookMetadata(ctx, bookID)
}

func (c *Consumer) handleChapterRemoved(ctx context.Context, payloadStr string) {
	var p struct {
		BookID string `json:"book_id"`
	}
	if err := json.Unmarshal([]byte(payloadStr), &p); err != nil {
		return
	}
	bookID, err := uuid.Parse(p.BookID)
	if err != nil {
		return
	}
	c.refreshBookMetadata(ctx, bookID)
}

func (c *Consumer) handleBookRated(ctx context.Context, payloadStr string) {
	var p struct {
		BookID string  `json:"book_id"`
		UserID string  `json:"user_id"`
		Rating float64 `json:"rating"`
	}
	if err := json.Unmarshal([]byte(payloadStr), &p); err != nil {
		slog.Error("statistics: bad book.rated payload", "error", err)
		return
	}

	bookID, err := uuid.Parse(p.BookID)
	if err != nil {
		return
	}
	userID, err := uuid.Parse(p.UserID)
	if err != nil {
		return
	}

	// Insert raw rating event
	_, _ = c.Pool.Exec(ctx, `INSERT INTO rating_events (book_id, user_id, rating) VALUES ($1, $2, $3)`,
		bookID, userID, p.Rating)

	// Recalc avg_rating and rating_count for this book
	c.ensureBookStats(ctx, bookID)
	_, _ = c.Pool.Exec(ctx, `
		UPDATE book_stats SET
			avg_rating = COALESCE(r.avg, 0),
			rating_count = COALESCE(r.cnt, 0),
			updated_at = now()
		FROM (
			SELECT AVG(rating) AS avg, COUNT(*) AS cnt
			FROM rating_events WHERE book_id = $1
		) r WHERE book_stats.book_id = $1
	`, bookID)
}

func (c *Consumer) handleBookFavorited(ctx context.Context, payloadStr string) {
	var p struct {
		BookID string `json:"book_id"`
		UserID string `json:"user_id"`
		Action string `json:"action"` // "add" or "remove"
	}
	if err := json.Unmarshal([]byte(payloadStr), &p); err != nil {
		slog.Error("statistics: bad book.favorited payload", "error", err)
		return
	}

	bookID, err := uuid.Parse(p.BookID)
	if err != nil {
		return
	}
	userID, err := uuid.Parse(p.UserID)
	if err != nil {
		return
	}

	_, _ = c.Pool.Exec(ctx, `INSERT INTO favorite_events (book_id, user_id, action) VALUES ($1, $2, $3)`,
		bookID, userID, p.Action)

	c.ensureBookStats(ctx, bookID)

	delta := 1
	if p.Action == "remove" {
		delta = -1
	}
	_, _ = c.Pool.Exec(ctx, `
		UPDATE book_stats SET
			favorites_count = GREATEST(favorites_count + $2, 0),
			updated_at = now()
		WHERE book_id = $1
	`, bookID, delta)
}

func (c *Consumer) handleChapterTranslated(ctx context.Context, payloadStr string) {
	var p struct {
		UserID         string `json:"user_id"`
		BookID         string `json:"book_id"`
		ChapterID      string `json:"chapter_id"`
		TargetLanguage string `json:"target_language"`
		Status         string `json:"status"`
		InputTokens    *int   `json:"input_tokens"`
		OutputTokens   *int   `json:"output_tokens"`
	}
	if err := json.Unmarshal([]byte(payloadStr), &p); err != nil {
		slog.Error("statistics: bad chapter.translated payload", "error", err)
		return
	}

	userID, err := uuid.Parse(p.UserID)
	if err != nil {
		return
	}
	bookID, err := uuid.Parse(p.BookID)
	if err != nil {
		return
	}
	chapterID, err := uuid.Parse(p.ChapterID)
	if err != nil {
		return
	}

	_, _ = c.Pool.Exec(ctx, `
		INSERT INTO translation_events (user_id, book_id, chapter_id, target_language, status, input_tokens, output_tokens)
		VALUES ($1, $2, $3, $4, $5, $6, $7)
	`, userID, bookID, chapterID, p.TargetLanguage, p.Status, p.InputTokens, p.OutputTokens)
}

// ensureBookStats creates a book_stats row if it doesn't exist, fetching metadata from book-service.
func (c *Consumer) ensureBookStats(ctx context.Context, bookID uuid.UUID) {
	var exists bool
	_ = c.Pool.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM book_stats WHERE book_id=$1)`, bookID).Scan(&exists)
	if exists {
		return
	}
	c.refreshBookMetadata(ctx, bookID)
}

// refreshBookMetadata fetches book projection from book-service and upserts into book_stats.
func (c *Consumer) refreshBookMetadata(ctx context.Context, bookID uuid.UUID) {
	url := fmt.Sprintf("%s/internal/books/%s/projection", strings.TrimRight(c.Cfg.BookServiceInternalURL, "/"), bookID)
	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		slog.Error("statistics: build request", "error", err)
		return
	}
	if c.Cfg.InternalServiceToken != "" {
		req.Header.Set("X-Internal-Token", c.Cfg.InternalServiceToken)
	}

	resp, err := c.client.Do(req)
	if err != nil {
		slog.Error("statistics: fetch book projection", "error", err, "book_id", bookID)
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		slog.Warn("statistics: book projection non-200", "status", resp.StatusCode, "body", string(body), "book_id", bookID)
		return
	}

	var proj struct {
		BookID       uuid.UUID `json:"book_id"`
		OwnerUserID  uuid.UUID `json:"owner_user_id"`
		Title        string    `json:"title"`
		GenreTags    []string  `json:"genre_tags"`
		Language     *string   `json:"original_language"`
		ChapterCount int       `json:"chapter_count"`
		HasCover     bool      `json:"has_cover"`
		CreatedAt    time.Time `json:"created_at"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&proj); err != nil {
		slog.Error("statistics: decode projection", "error", err)
		return
	}
	if proj.GenreTags == nil {
		proj.GenreTags = []string{}
	}

	// Fetch owner display name from auth-service
	ownerDisplayName := c.fetchUserDisplayName(ctx, proj.OwnerUserID)

	_, _ = c.Pool.Exec(ctx, `
		INSERT INTO book_stats (book_id, owner_user_id, title, genre_tags, original_language, chapter_count, has_cover, book_created_at, owner_display_name)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
		ON CONFLICT (book_id) DO UPDATE SET
			owner_user_id = EXCLUDED.owner_user_id,
			title = EXCLUDED.title,
			genre_tags = EXCLUDED.genre_tags,
			original_language = EXCLUDED.original_language,
			chapter_count = EXCLUDED.chapter_count,
			has_cover = EXCLUDED.has_cover,
			owner_display_name = EXCLUDED.owner_display_name,
			updated_at = now()
	`, proj.BookID, proj.OwnerUserID, proj.Title, proj.GenreTags, proj.Language, proj.ChapterCount, proj.HasCover, proj.CreatedAt, ownerDisplayName)
}

// refreshLoop periodically recalculates windowed stats and author aggregates.
func (c *Consumer) refreshLoop(ctx context.Context) {
	interval := time.Duration(c.Cfg.RefreshIntervalSeconds) * time.Second
	if interval < 30*time.Second {
		interval = 30 * time.Second
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			c.recalculateWindowedStats(ctx)
			c.recalculateEngagement(ctx)
			c.recalculateTranslationCounts(ctx)
			c.rollupDailyBookStats(ctx)
			c.snapshotRanks(ctx)
			c.recalculateAuthorStats(ctx)
			c.recalculateTranslatorStats(ctx)
			c.refreshTranslatorDisplayNames(ctx)
			c.cleanupOldEvents(ctx)
		}
	}
}

func (c *Consumer) recalculateWindowedStats(ctx context.Context) {
	slog.Info("statistics: recalculating windowed stats")

	// views_7d
	_, err := c.Pool.Exec(ctx, `
		UPDATE book_stats bs SET views_7d = COALESCE(v.cnt, 0), updated_at = now()
		FROM (
			SELECT book_id, COUNT(*) AS cnt
			FROM view_events WHERE viewed_at > now() - interval '7 days'
			GROUP BY book_id
		) v WHERE bs.book_id = v.book_id
	`)
	if err != nil {
		slog.Error("statistics: recalc views_7d", "error", err)
	}
	// Reset books with no recent views
	_, _ = c.Pool.Exec(ctx, `
		UPDATE book_stats bs SET views_7d = 0
		FROM book_stats bs2
		LEFT JOIN (
			SELECT DISTINCT book_id FROM view_events WHERE viewed_at > now() - interval '7 days'
		) v ON v.book_id = bs2.book_id
		WHERE bs.book_id = bs2.book_id AND v.book_id IS NULL AND bs.views_7d > 0
	`)

	// views_30d
	_, err = c.Pool.Exec(ctx, `
		UPDATE book_stats bs SET views_30d = COALESCE(v.cnt, 0)
		FROM (
			SELECT book_id, COUNT(*) AS cnt
			FROM view_events WHERE viewed_at > now() - interval '30 days'
			GROUP BY book_id
		) v WHERE bs.book_id = v.book_id
	`)
	if err != nil {
		slog.Error("statistics: recalc views_30d", "error", err)
	}
	_, _ = c.Pool.Exec(ctx, `
		UPDATE book_stats bs SET views_30d = 0
		FROM book_stats bs2
		LEFT JOIN (
			SELECT DISTINCT book_id FROM view_events WHERE viewed_at > now() - interval '30 days'
		) v ON v.book_id = bs2.book_id
		WHERE bs.book_id = bs2.book_id AND v.book_id IS NULL AND bs.views_30d > 0
	`)

	slog.Info("statistics: windowed stats recalculated")
}

func (c *Consumer) recalculateEngagement(ctx context.Context) {
	slog.Info("statistics: recalculating engagement metrics")

	// Update unique_readers + avg engagement from reading_events
	_, err := c.Pool.Exec(ctx, `
		UPDATE book_stats bs SET
			unique_readers = COALESCE(r.cnt, 0),
			avg_time_ms = COALESCE(r.avg_time, 0),
			avg_scroll_depth = COALESCE(r.avg_scroll, 0),
			updated_at = now()
		FROM (
			SELECT book_id,
				COUNT(DISTINCT user_id) AS cnt,
				AVG(time_spent_ms) AS avg_time,
				AVG(scroll_depth) AS avg_scroll
			FROM reading_events
			GROUP BY book_id
		) r WHERE bs.book_id = r.book_id
	`)
	if err != nil {
		slog.Error("statistics: recalc engagement", "error", err)
	}
}

func (c *Consumer) rollupDailyBookStats(ctx context.Context) {
	// Upsert today + yesterday only (yesterday for final counts after midnight)
	_, err := c.Pool.Exec(ctx, `
		INSERT INTO daily_book_rollups (book_id, day, views, readers, avg_time_ms)
		SELECT
			ve.book_id,
			ve.viewed_at::date AS day,
			COUNT(*) AS views,
			COUNT(DISTINCT ve.user_id) AS readers,
			0
		FROM view_events ve
		WHERE ve.viewed_at::date >= CURRENT_DATE - 1
		GROUP BY ve.book_id, ve.viewed_at::date
		ON CONFLICT (book_id, day) DO UPDATE SET
			views = EXCLUDED.views,
			readers = EXCLUDED.readers
	`)
	if err != nil {
		slog.Error("statistics: rollup daily views", "error", err)
	}

	// Merge reading engagement into daily rollups for today + yesterday
	_, err = c.Pool.Exec(ctx, `
		UPDATE daily_book_rollups dbr SET avg_time_ms = COALESCE(r.avg_time, 0)
		FROM (
			SELECT book_id, recorded_at::date AS day, AVG(time_spent_ms) AS avg_time
			FROM reading_events
			WHERE recorded_at::date >= CURRENT_DATE - 1
			GROUP BY book_id, recorded_at::date
		) r
		WHERE dbr.book_id = r.book_id AND dbr.day = r.day
	`)
	if err != nil {
		slog.Error("statistics: rollup daily engagement", "error", err)
	}

	// Prune rollups older than 90 days
	_, _ = c.Pool.Exec(ctx, `DELETE FROM daily_book_rollups WHERE day < CURRENT_DATE - interval '90 days'`)
}

func (c *Consumer) recalculateTranslatorStats(ctx context.Context) {
	slog.Info("statistics: recalculating translator stats")

	_, err := c.Pool.Exec(ctx, `
		INSERT INTO translator_stats (user_id, total_translations, total_chapters_done, translations_7d, translations_30d, languages, updated_at)
		SELECT
			user_id,
			COUNT(*) AS total_translations,
			COUNT(*) FILTER (WHERE status = 'completed') AS total_chapters_done,
			COUNT(*) FILTER (WHERE translated_at > now() - interval '7 days') AS translations_7d,
			COUNT(*) FILTER (WHERE translated_at > now() - interval '30 days') AS translations_30d,
			COALESCE(ARRAY_AGG(DISTINCT target_language) FILTER (WHERE target_language IS NOT NULL), '{}'),
			now()
		FROM translation_events
		GROUP BY user_id
		ON CONFLICT (user_id) DO UPDATE SET
			total_translations = EXCLUDED.total_translations,
			total_chapters_done = EXCLUDED.total_chapters_done,
			translations_7d = EXCLUDED.translations_7d,
			translations_30d = EXCLUDED.translations_30d,
			languages = EXCLUDED.languages,
			updated_at = now()
	`)
	if err != nil {
		slog.Error("statistics: recalc translator stats", "error", err)
	}
}

func (c *Consumer) cleanupOldEvents(ctx context.Context) {
	// Keep only 90 days of raw events to prevent unbounded growth
	tag, _ := c.Pool.Exec(ctx, `DELETE FROM view_events WHERE viewed_at < now() - interval '90 days'`)
	if tag.RowsAffected() > 0 {
		slog.Info("statistics: cleaned view_events", "deleted", tag.RowsAffected())
	}
	tag, _ = c.Pool.Exec(ctx, `DELETE FROM reading_events WHERE recorded_at < now() - interval '90 days'`)
	if tag.RowsAffected() > 0 {
		slog.Info("statistics: cleaned reading_events", "deleted", tag.RowsAffected())
	}
	tag, _ = c.Pool.Exec(ctx, `DELETE FROM translation_events WHERE translated_at < now() - interval '90 days'`)
	if tag.RowsAffected() > 0 {
		slog.Info("statistics: cleaned translation_events", "deleted", tag.RowsAffected())
	}
}

func (c *Consumer) snapshotRanks(ctx context.Context) {
	// Only snapshot once per hour to avoid unbounded row growth
	if time.Since(c.lastSnapshotAt) < time.Hour {
		return
	}
	c.lastSnapshotAt = time.Now()

	// Snapshot current ranks for each period, then compute rank_change
	for _, period := range []string{"all", "7d", "30d"} {
		orderCol := "total_views"
		switch period {
		case "7d":
			orderCol = "views_7d"
		case "30d":
			orderCol = "views_30d"
		}

		// Insert current ranks
		_, _ = c.Pool.Exec(ctx, fmt.Sprintf(`
			INSERT INTO rank_snapshots (book_id, position, period)
			SELECT book_id, ROW_NUMBER() OVER (ORDER BY %s DESC), $1
			FROM book_stats WHERE total_views > 0
		`, orderCol), period)
	}

	// Compute rank_change for "all" period (most commonly displayed)
	// Compare latest snapshot to the previous one
	_, _ = c.Pool.Exec(ctx, `
		UPDATE book_stats bs SET rank_change = COALESCE(prev.position - curr.position, 0)
		FROM (
			SELECT DISTINCT ON (book_id) book_id, position
			FROM rank_snapshots WHERE period = 'all'
			ORDER BY book_id, snapped_at DESC
		) curr
		LEFT JOIN (
			SELECT DISTINCT ON (book_id) book_id, position
			FROM rank_snapshots WHERE period = 'all'
			AND snapped_at < (SELECT MAX(snapped_at) FROM rank_snapshots WHERE period = 'all')
			ORDER BY book_id, snapped_at DESC
		) prev ON prev.book_id = curr.book_id
		WHERE bs.book_id = curr.book_id
	`)

	// Cleanup old snapshots (keep 30 days)
	_, _ = c.Pool.Exec(ctx, `DELETE FROM rank_snapshots WHERE snapped_at < now() - interval '30 days'`)
}

func (c *Consumer) recalculateAuthorStats(ctx context.Context) {
	slog.Info("statistics: recalculating author stats")

	// Aggregate from book_stats — carry owner_display_name as display_name
	_, err := c.Pool.Exec(ctx, `
		INSERT INTO author_stats (user_id, display_name, total_books, total_views, views_7d, views_30d, total_readers, avg_time_ms, total_chapters, avg_rating, updated_at)
		SELECT
			owner_user_id,
			MAX(owner_display_name),
			COUNT(*),
			COALESCE(SUM(total_views), 0),
			COALESCE(SUM(views_7d), 0),
			COALESCE(SUM(views_30d), 0),
			COALESCE(SUM(unique_readers), 0),
			COALESCE(AVG(avg_time_ms), 0),
			COALESCE(SUM(chapter_count), 0),
			COALESCE(AVG(NULLIF(avg_rating, 0)), 0),
			now()
		FROM book_stats
		GROUP BY owner_user_id
		ON CONFLICT (user_id) DO UPDATE SET
			display_name = EXCLUDED.display_name,
			total_books = EXCLUDED.total_books,
			total_views = EXCLUDED.total_views,
			views_7d = EXCLUDED.views_7d,
			views_30d = EXCLUDED.views_30d,
			total_readers = EXCLUDED.total_readers,
			avg_time_ms = EXCLUDED.avg_time_ms,
			total_chapters = EXCLUDED.total_chapters,
			avg_rating = EXCLUDED.avg_rating,
			updated_at = now()
	`)
	if err != nil {
		slog.Error("statistics: recalc author stats", "error", err)
	}

	slog.Info("statistics: author stats recalculated")
}

func (c *Consumer) recalculateTranslationCounts(ctx context.Context) {
	// Count distinct target languages with completed translations per book
	_, err := c.Pool.Exec(ctx, `
		UPDATE book_stats bs SET translation_count = COALESCE(t.cnt, 0)
		FROM (
			SELECT book_id, COUNT(DISTINCT target_language) AS cnt
			FROM translation_events WHERE status = 'completed'
			GROUP BY book_id
		) t WHERE bs.book_id = t.book_id
	`)
	if err != nil {
		slog.Error("statistics: recalc translation counts", "error", err)
	}

	// Reset books that no longer have any completed translations
	_, _ = c.Pool.Exec(ctx, `
		UPDATE book_stats bs SET translation_count = 0
		WHERE bs.translation_count > 0
		AND NOT EXISTS (
			SELECT 1 FROM translation_events te
			WHERE te.book_id = bs.book_id AND te.status = 'completed'
		)
	`)
}

// fetchUserDisplayName calls auth-service to resolve a user_id to a display name.
// Returns empty string on any error (best-effort).
func (c *Consumer) fetchUserDisplayName(ctx context.Context, userID uuid.UUID) string {
	url := fmt.Sprintf("%s/internal/users/%s/profile", strings.TrimRight(c.Cfg.AuthServiceInternalURL, "/"), userID)
	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return ""
	}
	resp, err := c.client.Do(req)
	if err != nil {
		return ""
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return ""
	}
	var profile struct {
		DisplayName string `json:"display_name"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&profile); err != nil {
		return ""
	}
	return profile.DisplayName
}

// refreshTranslatorDisplayNames fetches display names for all translators.
// Refreshes all rows (not just empty) so name changes propagate.
func (c *Consumer) refreshTranslatorDisplayNames(ctx context.Context) {
	rows, err := c.Pool.Query(ctx, `SELECT user_id FROM translator_stats`)
	if err != nil {
		return
	}
	defer rows.Close()

	for rows.Next() {
		var userID uuid.UUID
		if err := rows.Scan(&userID); err != nil {
			continue
		}
		name := c.fetchUserDisplayName(ctx, userID)
		if name != "" {
			_, _ = c.Pool.Exec(ctx, `UPDATE translator_stats SET display_name = $1 WHERE user_id = $2`, name, userID)
		}
	}
}

// ── Voice analytics consumer ────────────────────────────────────────────────

func (c *Consumer) runVoiceConsumer(ctx context.Context) {
	slog.Info("voice-consumer started", "stream", voiceEventStream)
	for {
		select {
		case <-ctx.Done():
			return
		default:
		}

		results, err := c.Redis.XReadGroup(ctx, &redis.XReadGroupArgs{
			Group:    consumerGroup,
			Consumer: consumerName,
			Streams:  []string{voiceEventStream, ">"},
			Count:    10,
			Block:    5 * time.Second,
		}).Result()
		if err != nil {
			if err == redis.Nil || strings.Contains(err.Error(), "context") {
				continue
			}
			slog.Error("voice-consumer XREADGROUP", "error", err)
			time.Sleep(2 * time.Second)
			continue
		}

		for _, stream := range results {
			for _, msg := range stream.Messages {
				eventType, _ := msg.Values["event_type"].(string)
				payloadStr, _ := msg.Values["payload"].(string)

				if eventType == "voice.turn" {
					c.handleVoiceTurn(ctx, payloadStr)
				}

				c.Redis.XAck(ctx, voiceEventStream, consumerGroup, msg.ID)
			}
		}
	}
}

func (c *Consumer) handleVoiceTurn(ctx context.Context, payloadStr string) {
	var p struct {
		UserID                 string `json:"user_id"`
		SessionID              string `json:"session_id"`
		STTSuccess             bool   `json:"stt_success"`
		STTDurationMs          int    `json:"stt_duration_ms"`
		SpeechDurationMs       *int   `json:"speech_duration_ms"`
		AudioSizeKB            *int   `json:"audio_size_kb"`
		LLMFirstTokenMs        *int   `json:"llm_first_token_ms"`
		TTSSentenceCount       int    `json:"tts_sentence_count"`
		TTSSkippedCount        int    `json:"tts_skipped_count"`
		ThresholdSilenceFrames int    `json:"threshold_silence_frames"`
		ThresholdMinDurationMs int    `json:"threshold_min_duration_ms"`
	}
	if err := json.Unmarshal([]byte(payloadStr), &p); err != nil {
		slog.Error("voice: bad payload", "error", err)
		return
	}

	userID, err := uuid.Parse(p.UserID)
	if err != nil {
		slog.Error("voice: bad user_id", "error", err)
		return
	}

	// Insert raw event
	_, err = c.Pool.Exec(ctx, `
		INSERT INTO voice_turn_events
		  (user_id, session_id, stt_success, stt_duration_ms, speech_duration_ms,
		   audio_size_kb, llm_first_token_ms, tts_sentence_count, tts_skipped_count,
		   threshold_silence_frames, threshold_min_duration_ms)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)`,
		userID, p.SessionID, p.STTSuccess, p.STTDurationMs, p.SpeechDurationMs,
		p.AudioSizeKB, p.LLMFirstTokenMs, p.TTSSentenceCount, p.TTSSkippedCount,
		p.ThresholdSilenceFrames, p.ThresholdMinDurationMs,
	)
	if err != nil {
		slog.Error("voice: insert event failed", "error", err)
		return
	}

	// Update aggregated user stats
	c.recalcVoiceUserStats(ctx, userID)
}

func (c *Consumer) recalcVoiceUserStats(ctx context.Context, userID uuid.UUID) {
	// Aggregate from recent events (last 100 turns)
	var totalTurns, successTurns, failedTurns int
	var avgSTTMs, avgSpeechMs, avgLLMMs int
	var misfireRate float64

	err := c.Pool.QueryRow(ctx, `
		WITH recent AS (
			SELECT * FROM voice_turn_events
			WHERE user_id = $1
			ORDER BY recorded_at DESC LIMIT 100
		)
		SELECT
			COUNT(*),
			COUNT(*) FILTER (WHERE stt_success),
			COUNT(*) FILTER (WHERE NOT stt_success),
			COALESCE(AVG(stt_duration_ms) FILTER (WHERE stt_success), 0)::int,
			COALESCE(AVG(speech_duration_ms) FILTER (WHERE stt_success AND speech_duration_ms IS NOT NULL), 0)::int,
			COALESCE(AVG(llm_first_token_ms) FILTER (WHERE stt_success AND llm_first_token_ms IS NOT NULL), 0)::int,
			CASE WHEN COUNT(*) > 0
				THEN COUNT(*) FILTER (WHERE NOT stt_success)::float / COUNT(*)
				ELSE 0 END
		FROM recent
	`, userID).Scan(&totalTurns, &successTurns, &failedTurns, &avgSTTMs, &avgSpeechMs, &avgLLMMs, &misfireRate)
	if err != nil {
		slog.Error("voice: recalc stats failed", "error", err)
		return
	}

	// Calculate recommended thresholds based on misfire rate
	recommendedSilence := 8 // Normal default
	recommendedMinDuration := 500
	if misfireRate > 0.3 {
		recommendedSilence = 16  // Learner mode — lots of misfires
		recommendedMinDuration = 1000
	} else if misfireRate > 0.15 {
		recommendedSilence = 12 // Patient mode
		recommendedMinDuration = 700
	} else if misfireRate < 0.05 && avgSpeechMs > 3000 {
		recommendedSilence = 5 // Fast mode — reliable speaker
		recommendedMinDuration = 300
	}

	_, err = c.Pool.Exec(ctx, `
		INSERT INTO voice_user_stats
			(user_id, total_turns, successful_turns, failed_turns,
			 avg_stt_duration_ms, avg_speech_duration_ms, avg_llm_first_token_ms,
			 misfire_rate, recommended_silence_frames, recommended_min_duration_ms, updated_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, now())
		ON CONFLICT (user_id) DO UPDATE SET
			total_turns = EXCLUDED.total_turns,
			successful_turns = EXCLUDED.successful_turns,
			failed_turns = EXCLUDED.failed_turns,
			avg_stt_duration_ms = EXCLUDED.avg_stt_duration_ms,
			avg_speech_duration_ms = EXCLUDED.avg_speech_duration_ms,
			avg_llm_first_token_ms = EXCLUDED.avg_llm_first_token_ms,
			misfire_rate = EXCLUDED.misfire_rate,
			recommended_silence_frames = EXCLUDED.recommended_silence_frames,
			recommended_min_duration_ms = EXCLUDED.recommended_min_duration_ms,
			updated_at = now()
	`, userID, totalTurns, successTurns, failedTurns, avgSTTMs, avgSpeechMs, avgLLMMs,
		misfireRate, recommendedSilence, recommendedMinDuration,
	)
	if err != nil {
		slog.Error("voice: upsert user stats failed", "error", err)
	}
}
