package api

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/statistics-service/internal/config"
)

type Server struct {
	pool *pgxpool.Pool
	cfg  *config.Config
}

func NewServer(pool *pgxpool.Pool, cfg *config.Config) *Server {
	return &Server{
		pool: pool,
		cfg:  cfg,
	}
}

func (s *Server) Router() http.Handler {
	r := chi.NewRouter()
	r.Use(middleware.RequestID)
	r.Use(middleware.RealIP)
	r.Use(middleware.Recoverer)

	r.Get("/health", func(w http.ResponseWriter, r *http.Request) {
		if s.pool != nil {
			if err := s.pool.Ping(r.Context()); err != nil {
				w.WriteHeader(http.StatusServiceUnavailable)
				_, _ = w.Write([]byte("db ping failed"))
				return
			}
		}
		_, _ = w.Write([]byte("ok"))
	})
	r.Get("/health/ready", func(w http.ResponseWriter, r *http.Request) {
		if s.pool == nil {
			writeJSON(w, http.StatusServiceUnavailable, map[string]string{"status": "not ready", "error": "no db pool"})
			return
		}
		var n int
		if err := s.pool.QueryRow(r.Context(), "SELECT 1").Scan(&n); err != nil {
			writeJSON(w, http.StatusServiceUnavailable, map[string]string{"status": "not ready", "error": err.Error()})
			return
		}
		writeJSON(w, http.StatusOK, map[string]string{"status": "ready"})
	})

	r.Route("/v1/leaderboard", func(r chi.Router) {
		r.Get("/books", s.leaderboardBooks)
		r.Get("/authors", s.leaderboardAuthors)
		r.Get("/translators", s.leaderboardTranslators)
	})

	r.Route("/v1/stats", func(r chi.Router) {
		r.Get("/books/{book_id}", s.statsBook)
		r.Get("/authors/{user_id}", s.statsAuthor)
		r.Get("/translators/{user_id}", s.statsTranslator)
		r.Get("/overview", s.statsOverview)
	})

	// Internal API for cross-service queries
	r.Route("/internal", func(r chi.Router) {
		r.Use(s.internalAuth)
		r.Get("/voice-stats/{user_id}", s.voiceStats)
	})

	return r
}

// ── Leaderboard ─────────────────────────────────────────────────────────────

func (s *Server) leaderboardBooks(w http.ResponseWriter, r *http.Request) {
	period := r.URL.Query().Get("period")
	genre := r.URL.Query().Get("genre")
	language := r.URL.Query().Get("language")
	sortBy := r.URL.Query().Get("sort")
	limit := queryInt(r, "limit", 20)
	offset := queryInt(r, "offset", 0)
	if limit > 100 {
		limit = 100
	}

	orderCol := bookOrderCol(period, sortBy)

	query := fmt.Sprintf(`SELECT book_id, owner_user_id, owner_display_name, title, genre_tags, original_language,
		total_views, views_7d, views_30d, unique_readers,
		avg_time_ms, avg_scroll_depth, chapter_count, translation_count,
		avg_rating, rating_count, favorites_count, rank_change, has_cover
		FROM book_stats WHERE total_views > 0`)
	args := []any{}
	argIdx := 1

	if genre != "" {
		query += fmt.Sprintf(` AND genre_tags @> ARRAY[$%d]::text[]`, argIdx)
		args = append(args, genre)
		argIdx++
	}
	if language != "" {
		query += fmt.Sprintf(` AND original_language = $%d`, argIdx)
		args = append(args, language)
		argIdx++
	}

	query += fmt.Sprintf(` ORDER BY %s DESC LIMIT $%d OFFSET $%d`, orderCol, argIdx, argIdx+1)
	args = append(args, limit, offset)

	rows, err := s.pool.Query(r.Context(), query, args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "STATS_ERROR", "query failed")
		return
	}
	defer rows.Close()

	items := make([]map[string]any, 0)
	rank := offset + 1
	for rows.Next() {
		var bookID, ownerID uuid.UUID
		var ownerDisplayName, title string
		var genreTags []string
		var lang *string
		var totalViews, views7d, views30d, uniqueReaders, avgTimeMs int64
		var avgScrollDepth, avgRating float64
		var chapterCount, translationCount, ratingCount, favoritesCount, rankChange int
		var hasCover bool
		if err := rows.Scan(&bookID, &ownerID, &ownerDisplayName, &title, &genreTags, &lang,
			&totalViews, &views7d, &views30d, &uniqueReaders,
			&avgTimeMs, &avgScrollDepth, &chapterCount, &translationCount,
			&avgRating, &ratingCount, &favoritesCount, &rankChange, &hasCover); err != nil {
			continue
		}
		if genreTags == nil {
			genreTags = []string{}
		}
		items = append(items, map[string]any{
			"rank":               rank,
			"book_id":            bookID,
			"owner_user_id":      ownerID,
			"owner_display_name": ownerDisplayName,
			"title":              title,
			"genre_tags":         genreTags,
			"original_language":  lang,
			"views":              totalViews,
			"views_7d":           views7d,
			"views_30d":          views30d,
			"unique_readers":     uniqueReaders,
			"avg_time_ms":        avgTimeMs,
			"avg_scroll_depth":   avgScrollDepth,
			"chapter_count":      chapterCount,
			"translation_count":  translationCount,
			"avg_rating":         avgRating,
			"rating_count":       ratingCount,
			"favorites_count":    favoritesCount,
			"rank_change":        rankChange,
			"has_cover":          hasCover,
		})
		rank++
	}

	// Count total with same filters
	countQuery := `SELECT COUNT(*) FROM book_stats WHERE total_views > 0`
	countArgs := []any{}
	countIdx := 1
	if genre != "" {
		countQuery += fmt.Sprintf(` AND genre_tags @> ARRAY[$%d]::text[]`, countIdx)
		countArgs = append(countArgs, genre)
		countIdx++
	}
	if language != "" {
		countQuery += fmt.Sprintf(` AND original_language = $%d`, countIdx)
		countArgs = append(countArgs, language)
	}
	var total int64
	_ = s.pool.QueryRow(r.Context(), countQuery, countArgs...).Scan(&total)

	writeJSON(w, http.StatusOK, map[string]any{
		"items":  items,
		"total":  total,
		"period": periodOrDefault(period),
	})
}

func (s *Server) leaderboardAuthors(w http.ResponseWriter, r *http.Request) {
	period := r.URL.Query().Get("period")
	limit := queryInt(r, "limit", 20)
	offset := queryInt(r, "offset", 0)
	if limit > 100 {
		limit = 100
	}

	orderCol := "total_views"
	switch period {
	case "7d":
		orderCol = "views_7d"
	case "30d":
		orderCol = "views_30d"
	}

	rows, err := s.pool.Query(r.Context(), fmt.Sprintf(`
		SELECT user_id, display_name, total_books, total_views, views_7d, views_30d,
			total_readers, avg_time_ms, total_chapters, avg_rating
		FROM author_stats WHERE total_views > 0
		ORDER BY %s DESC LIMIT $1 OFFSET $2
	`, orderCol), limit, offset)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "STATS_ERROR", "query failed")
		return
	}
	defer rows.Close()

	items := make([]map[string]any, 0)
	rank := offset + 1
	for rows.Next() {
		var userID uuid.UUID
		var displayName string
		var totalBooks, totalChapters int
		var totalViews, views7d, views30d, totalReaders, avgTimeMs int64
		var avgRating float64
		if err := rows.Scan(&userID, &displayName, &totalBooks, &totalViews, &views7d, &views30d,
			&totalReaders, &avgTimeMs, &totalChapters, &avgRating); err != nil {
			continue
		}
		items = append(items, map[string]any{
			"rank":           rank,
			"user_id":        userID,
			"display_name":   displayName,
			"total_books":    totalBooks,
			"views":          totalViews,
			"views_7d":       views7d,
			"views_30d":      views30d,
			"readers":        totalReaders,
			"avg_time_ms":    avgTimeMs,
			"total_chapters": totalChapters,
			"avg_rating":     avgRating,
		})
		rank++
	}

	var total int64
	_ = s.pool.QueryRow(r.Context(), `SELECT COUNT(*) FROM author_stats WHERE total_views > 0`).Scan(&total)

	writeJSON(w, http.StatusOK, map[string]any{
		"items":  items,
		"total":  total,
		"period": periodOrDefault(period),
	})
}

func (s *Server) leaderboardTranslators(w http.ResponseWriter, r *http.Request) {
	period := r.URL.Query().Get("period")
	limit := queryInt(r, "limit", 20)
	offset := queryInt(r, "offset", 0)
	if limit > 100 {
		limit = 100
	}

	orderCol := "total_chapters_done"
	switch period {
	case "7d":
		orderCol = "translations_7d"
	case "30d":
		orderCol = "translations_30d"
	}

	rows, err := s.pool.Query(r.Context(), fmt.Sprintf(`
		SELECT user_id, display_name, total_translations, total_chapters_done,
			translations_7d, translations_30d, languages
		FROM translator_stats WHERE total_chapters_done > 0
		ORDER BY %s DESC LIMIT $1 OFFSET $2
	`, orderCol), limit, offset)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "STATS_ERROR", "query failed")
		return
	}
	defer rows.Close()

	items := make([]map[string]any, 0)
	rank := offset + 1
	for rows.Next() {
		var userID uuid.UUID
		var displayName string
		var totalTranslations, totalChaptersDone, translations7d, translations30d int
		var languages []string
		if err := rows.Scan(&userID, &displayName, &totalTranslations, &totalChaptersDone,
			&translations7d, &translations30d, &languages); err != nil {
			continue
		}
		if languages == nil {
			languages = []string{}
		}
		items = append(items, map[string]any{
			"rank":                rank,
			"user_id":             userID,
			"display_name":        displayName,
			"total_translations":  totalTranslations,
			"total_chapters_done": totalChaptersDone,
			"translations_7d":     translations7d,
			"translations_30d":    translations30d,
			"languages":           languages,
		})
		rank++
	}

	var total int64
	_ = s.pool.QueryRow(r.Context(), `SELECT COUNT(*) FROM translator_stats WHERE total_chapters_done > 0`).Scan(&total)

	writeJSON(w, http.StatusOK, map[string]any{
		"items":  items,
		"total":  total,
		"period": periodOrDefault(period),
	})
}

// ── Single Stats ────────────────────────────────────────────────────────────

func (s *Server) statsBook(w http.ResponseWriter, r *http.Request) {
	bookID, err := uuid.Parse(chi.URLParam(r, "book_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "STATS_VALIDATION_ERROR", "invalid book_id")
		return
	}

	var ownerID uuid.UUID
	var ownerDisplayName, title string
	var genreTags []string
	var lang *string
	var totalViews, views7d, views30d, uniqueReaders, avgTimeMs int64
	var avgScrollDepth, avgRating float64
	var chapterCount, translationCount, ratingCount, favoritesCount, rankChange int
	var hasCover bool

	err = s.pool.QueryRow(r.Context(), `
		SELECT owner_user_id, owner_display_name, title, genre_tags, original_language,
			total_views, views_7d, views_30d, unique_readers,
			avg_time_ms, avg_scroll_depth, chapter_count, translation_count,
			avg_rating, rating_count, favorites_count, rank_change, has_cover
		FROM book_stats WHERE book_id=$1
	`, bookID).Scan(&ownerID, &ownerDisplayName, &title, &genreTags, &lang,
		&totalViews, &views7d, &views30d, &uniqueReaders,
		&avgTimeMs, &avgScrollDepth, &chapterCount, &translationCount,
		&avgRating, &ratingCount, &favoritesCount, &rankChange, &hasCover)
	if err != nil {
		writeJSON(w, http.StatusOK, map[string]any{
			"book_id":              bookID,
			"owner_display_name":   "",
			"total_views":          0,
			"views_7d":             0,
			"views_30d":            0,
			"unique_readers":       0,
			"avg_time_ms":          0,
			"avg_scroll_depth":     0,
			"chapter_count":        0,
			"translation_count":    0,
			"avg_rating":           0,
			"rating_count":         0,
			"favorites_count":      0,
			"rank_change":          0,
			"has_cover":            false,
			"daily_views":          []map[string]any{},
		})
		return
	}
	if genreTags == nil {
		genreTags = []string{}
	}

	// Fetch daily rollups (last 30 days)
	dailyViews := make([]map[string]any, 0)
	dvRows, err := s.pool.Query(r.Context(), `
		SELECT day, views, readers, avg_time_ms
		FROM daily_book_rollups
		WHERE book_id = $1 AND day >= CURRENT_DATE - interval '30 days'
		ORDER BY day
	`, bookID)
	if err == nil {
		defer dvRows.Close()
		for dvRows.Next() {
			var day time.Time
			var views, readers, avgTime int64
			if err := dvRows.Scan(&day, &views, &readers, &avgTime); err != nil {
				continue
			}
			dailyViews = append(dailyViews, map[string]any{
				"day":         day.Format("2006-01-02"),
				"views":       views,
				"readers":     readers,
				"avg_time_ms": avgTime,
			})
		}
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"book_id":            bookID,
		"owner_user_id":      ownerID,
		"owner_display_name": ownerDisplayName,
		"title":              title,
		"genre_tags":         genreTags,
		"original_language":  lang,
		"total_views":        totalViews,
		"views_7d":           views7d,
		"views_30d":          views30d,
		"unique_readers":     uniqueReaders,
		"avg_time_ms":        avgTimeMs,
		"avg_scroll_depth":   avgScrollDepth,
		"chapter_count":      chapterCount,
		"translation_count":  translationCount,
		"avg_rating":         avgRating,
		"rating_count":       ratingCount,
		"favorites_count":    favoritesCount,
		"rank_change":        rankChange,
		"has_cover":          hasCover,
		"daily_views":        dailyViews,
	})
}

func (s *Server) statsAuthor(w http.ResponseWriter, r *http.Request) {
	userID, err := uuid.Parse(chi.URLParam(r, "user_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "STATS_VALIDATION_ERROR", "invalid user_id")
		return
	}

	var totalBooks, totalChapters int
	var totalViews, views7d, views30d, totalReaders, avgTimeMs int64
	var avgRating float64

	err = s.pool.QueryRow(r.Context(), `
		SELECT total_books, total_views, views_7d, views_30d,
			total_readers, avg_time_ms, total_chapters, avg_rating
		FROM author_stats WHERE user_id=$1
	`, userID).Scan(&totalBooks, &totalViews, &views7d, &views30d,
		&totalReaders, &avgTimeMs, &totalChapters, &avgRating)
	if err != nil {
		writeJSON(w, http.StatusOK, map[string]any{
			"user_id":        userID,
			"total_books":    0,
			"total_views":    0,
			"views_7d":       0,
			"views_30d":      0,
			"total_readers":  0,
			"avg_time_ms":    0,
			"total_chapters": 0,
			"avg_rating":     0,
		})
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"user_id":        userID,
		"total_books":    totalBooks,
		"total_views":    totalViews,
		"views_7d":       views7d,
		"views_30d":      views30d,
		"total_readers":  totalReaders,
		"avg_time_ms":    avgTimeMs,
		"total_chapters": totalChapters,
		"avg_rating":     avgRating,
	})
}

func (s *Server) statsTranslator(w http.ResponseWriter, r *http.Request) {
	userID, err := uuid.Parse(chi.URLParam(r, "user_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "STATS_VALIDATION_ERROR", "invalid user_id")
		return
	}

	var totalTranslations, totalChaptersDone, translations7d, translations30d int
	var languages []string
	var displayName string

	err = s.pool.QueryRow(r.Context(), `
		SELECT display_name, total_translations, total_chapters_done,
			translations_7d, translations_30d, languages
		FROM translator_stats WHERE user_id=$1
	`, userID).Scan(&displayName, &totalTranslations, &totalChaptersDone,
		&translations7d, &translations30d, &languages)
	if err != nil {
		writeJSON(w, http.StatusOK, map[string]any{
			"user_id":             userID,
			"display_name":        "",
			"total_translations":  0,
			"total_chapters_done": 0,
			"translations_7d":     0,
			"translations_30d":    0,
			"languages":           []string{},
		})
		return
	}
	if languages == nil {
		languages = []string{}
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"user_id":             userID,
		"display_name":        displayName,
		"total_translations":  totalTranslations,
		"total_chapters_done": totalChaptersDone,
		"translations_7d":     translations7d,
		"translations_30d":    translations30d,
		"languages":           languages,
	})
}

func (s *Server) statsOverview(w http.ResponseWriter, r *http.Request) {
	var totalBooks, totalAuthors int64
	var totalViews7d, totalViews30d, totalViewsAll int64

	_ = s.pool.QueryRow(r.Context(), `SELECT COUNT(*), COALESCE(SUM(total_views),0), COALESCE(SUM(views_7d),0), COALESCE(SUM(views_30d),0) FROM book_stats`).
		Scan(&totalBooks, &totalViewsAll, &totalViews7d, &totalViews30d)
	_ = s.pool.QueryRow(r.Context(), `SELECT COUNT(*) FROM author_stats`).Scan(&totalAuthors)

	var totalTranslators int64
	var totalTranslations int64
	_ = s.pool.QueryRow(r.Context(), `SELECT COUNT(*), COALESCE(SUM(total_chapters_done),0) FROM translator_stats`).Scan(&totalTranslators, &totalTranslations)

	// Top genre by total views
	var topGenre *string
	_ = s.pool.QueryRow(r.Context(), `
		SELECT g FROM book_stats, unnest(genre_tags) AS g
		GROUP BY g ORDER BY SUM(total_views) DESC LIMIT 1
	`).Scan(&topGenre)

	writeJSON(w, http.StatusOK, map[string]any{
		"total_books":        totalBooks,
		"total_authors":      totalAuthors,
		"total_translators":  totalTranslators,
		"total_translations": totalTranslations,
		"total_views":        totalViewsAll,
		"total_views_7d":     totalViews7d,
		"total_views_30d":    totalViews30d,
		"top_genre":          topGenre,
	})
}

// ── Helpers ─────────────────────────────────────────────────────────────────

type errorBody struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, code, message string) {
	writeJSON(w, status, errorBody{Code: code, Message: message})
}

func queryInt(r *http.Request, key string, def int) int {
	v := r.URL.Query().Get(key)
	if v == "" {
		return def
	}
	n, err := strconv.Atoi(v)
	if err != nil || n < 0 {
		return def
	}
	return n
}

func periodOrDefault(p string) string {
	switch p {
	case "7d", "30d":
		return p
	default:
		return "all"
	}
}

// bookOrderCol returns a safe column name for ORDER BY based on period and sort params.
// Only returns known column names — never user input directly.
func bookOrderCol(period, sortBy string) string {
	switch sortBy {
	case "readers":
		return "unique_readers"
	case "rating":
		return "avg_rating"
	case "favorites":
		return "favorites_count"
	case "trending":
		return "rank_change"
	}
	switch period {
	case "7d":
		return "views_7d"
	case "30d":
		return "views_30d"
	default:
		return "total_views"
	}
}

// ── Internal auth middleware ────────────────────────────────────────────────

func (s *Server) internalAuth(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		token := r.Header.Get("X-Internal-Token")
		if token == "" || token != s.cfg.InternalServiceToken {
			writeJSON(w, http.StatusForbidden, map[string]string{"error": "invalid internal token"})
			return
		}
		next.ServeHTTP(w, r)
	})
}

// ── Voice stats ────────────────────────────────────────────────────────────

func (s *Server) voiceStats(w http.ResponseWriter, r *http.Request) {
	userIDStr := chi.URLParam(r, "user_id")
	userID, err := uuid.Parse(userIDStr)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid user_id"})
		return
	}

	// Direct query on raw events — no pre-aggregated table needed
	var stats struct {
		TotalTurns       int     `json:"total_turns"`
		FailedTurns      int     `json:"failed_turns"`
		MisfireRate      float64 `json:"misfire_rate"`
		AvgSpeechMs      int     `json:"avg_speech_duration_ms"`
		// Correlation: misfire rate at different threshold levels
		MisfireAtNormal  float64 `json:"misfire_at_normal"`
		MisfireAtPatient float64 `json:"misfire_at_patient"`
		// Recommendation
		RecommendedSilenceFrames int `json:"recommended_silence_frames"`
		RecommendedMinDurationMs int `json:"recommended_min_duration_ms"`
	}

	err = s.pool.QueryRow(r.Context(), `
		WITH recent AS (
			SELECT * FROM voice_turn_events
			WHERE user_id = $1 AND recorded_at > now() - interval '30 days'
			ORDER BY recorded_at DESC LIMIT 100
		)
		SELECT
			COUNT(*),
			COUNT(*) FILTER (WHERE NOT stt_success),
			CASE WHEN COUNT(*) > 0
				THEN COUNT(*) FILTER (WHERE NOT stt_success)::float / COUNT(*)
				ELSE 0 END,
			COALESCE(AVG(speech_duration_ms) FILTER (WHERE stt_success AND speech_duration_ms IS NOT NULL), 0)::int,
			CASE WHEN COUNT(*) FILTER (WHERE threshold_silence_frames <= 8) > 0
				THEN COUNT(*) FILTER (WHERE NOT stt_success AND threshold_silence_frames <= 8)::float
					/ COUNT(*) FILTER (WHERE threshold_silence_frames <= 8)
				ELSE 0 END,
			CASE WHEN COUNT(*) FILTER (WHERE threshold_silence_frames > 8) > 0
				THEN COUNT(*) FILTER (WHERE NOT stt_success AND threshold_silence_frames > 8)::float
					/ COUNT(*) FILTER (WHERE threshold_silence_frames > 8)
				ELSE 0 END
		FROM recent
	`, userID).Scan(
		&stats.TotalTurns, &stats.FailedTurns, &stats.MisfireRate,
		&stats.AvgSpeechMs, &stats.MisfireAtNormal, &stats.MisfireAtPatient,
	)
	if err != nil {
		stats.RecommendedSilenceFrames = 8
		stats.RecommendedMinDurationMs = 500
		writeJSON(w, http.StatusOK, stats)
		return
	}

	// Recommend based on correlation data
	stats.RecommendedSilenceFrames = 8
	stats.RecommendedMinDurationMs = 500
	if stats.MisfireRate > 0.3 {
		stats.RecommendedSilenceFrames = 16
		stats.RecommendedMinDurationMs = 1000
	} else if stats.MisfireRate > 0.15 {
		stats.RecommendedSilenceFrames = 12
		stats.RecommendedMinDurationMs = 700
	} else if stats.MisfireRate < 0.05 && stats.AvgSpeechMs > 3000 {
		stats.RecommendedSilenceFrames = 5
		stats.RecommendedMinDurationMs = 300
	}

	writeJSON(w, http.StatusOK, stats)
}
