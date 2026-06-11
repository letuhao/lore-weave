package api

// wiki-llm M8 (D-WIKI-M8-FEWSHOT) — gold AI→human pair feed for few-shot generation.
//
// A "gold pair" is an article whose revision history has an 'ai' revision (the draft)
// immediately followed by a later 'owner' revision (the human correction) — exactly the
// wiki.corrected condition. knowledge-service fetches the most-recent N pairs for a book
// and feeds them as few-shot exemplars so the model learns the editorial style humans
// apply. The bodies are TipTap JSON; this endpoint flattens them to plaintext and
// TRUNCATES each server-side so the prompt stays bounded (knowledge never parses TipTap).

import (
	"encoding/json"
	"log/slog"
	"net/http"
	"strconv"
	"strings"
)

const (
	goldPairsMaxLimit   = 5
	goldPairsBodyMaxLen = 1500 // chars per body — enough to convey style, bounds the prompt
)

type wikiGoldPair struct {
	ArticleID string `json:"article_id"`
	EntityID  string `json:"entity_id"`
	AIText    string `json:"ai_text"`
	HumanText string `json:"human_text"`
}

// tiptapPlaintext flattens a TipTap/ProseMirror doc to plain text (depth-first text nodes).
func tiptapPlaintext(raw json.RawMessage) string {
	var node any
	if err := json.Unmarshal(raw, &node); err != nil {
		return ""
	}
	var b strings.Builder
	var walk func(n any)
	walk = func(n any) {
		switch v := n.(type) {
		case map[string]any:
			if v["type"] == "text" {
				if t, ok := v["text"].(string); ok {
					b.WriteString(t)
					b.WriteString(" ")
				}
			}
			if c, ok := v["content"].([]any); ok {
				for _, ch := range c {
					walk(ch)
				}
			}
		case []any:
			for _, ch := range v {
				walk(ch)
			}
		}
	}
	walk(node)
	return strings.TrimSpace(b.String())
}

func truncateRunes(s string, max int) string {
	r := []rune(s)
	if len(r) <= max {
		return s
	}
	return string(r[:max])
}

// listWikiGoldPairs — GET /internal/books/{book_id}/wiki/gold-pairs?limit=N (X-Internal-Token).
func (s *Server) listWikiGoldPairs(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	limit := 3
	if q := r.URL.Query().Get("limit"); q != "" {
		if n, err := strconv.Atoi(q); err == nil && n > 0 {
			limit = n
		}
	}
	if limit > goldPairsMaxLimit {
		// Hard server-side cap (knowledge's wiki_fewshot_max_examples can in
		// principle exceed it) — log the clamp so a caller asking for more
		// isn't silently trimmed without a trace.
		slog.Debug("listWikiGoldPairs limit clamped", "requested", limit, "cap", goldPairsMaxLimit)
		limit = goldPairsMaxLimit
	}

	// For each article in the book: its latest 'owner' (human) revision joined with the
	// latest 'ai' revision that PRECEDES it (the draft it corrected). Newest-corrected first.
	rows, err := s.pool.Query(r.Context(), `
		WITH ranked AS (
		  SELECT wr.article_id, wr.version, wr.author_type, wr.body_json, wr.created_at, wa.entity_id
		    FROM wiki_revisions wr
		    JOIN wiki_articles wa ON wa.article_id = wr.article_id
		   WHERE wa.book_id = $1
		),
		human AS (
		  SELECT DISTINCT ON (article_id) article_id, entity_id, version, body_json, created_at
		    FROM ranked WHERE author_type = 'owner'
		   ORDER BY article_id, version DESC
		),
		ai AS (
		  SELECT DISTINCT ON (r.article_id) r.article_id, r.body_json
		    FROM ranked r JOIN human h ON h.article_id = r.article_id
		   WHERE r.author_type = 'ai' AND r.version < h.version
		   ORDER BY r.article_id, r.version DESC
		)
		SELECT h.article_id::text, h.entity_id::text, ai.body_json, h.body_json
		  FROM human h JOIN ai ON ai.article_id = h.article_id
		 ORDER BY h.created_at DESC
		 LIMIT $2`,
		bookID, limit)
	if err != nil {
		slog.Error("listWikiGoldPairs query", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	defer rows.Close()

	pairs := []wikiGoldPair{}
	for rows.Next() {
		var articleID, entityID string
		var aiBody, humanBody json.RawMessage
		if err := rows.Scan(&articleID, &entityID, &aiBody, &humanBody); err != nil {
			slog.Error("listWikiGoldPairs scan", "error", err)
			writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
			return
		}
		pairs = append(pairs, wikiGoldPair{
			ArticleID: articleID,
			EntityID:  entityID,
			AIText:    truncateRunes(tiptapPlaintext(aiBody), goldPairsBodyMaxLen),
			HumanText: truncateRunes(tiptapPlaintext(humanBody), goldPairsBodyMaxLen),
		})
	}
	if err := rows.Err(); err != nil {
		slog.Error("listWikiGoldPairs rows", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"pairs": pairs})
}
