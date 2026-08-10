package api

import (
	"encoding/json"
	"log/slog"
	"net/http"
	"strconv"

	"github.com/google/uuid"

	"github.com/loreweave/grantclient"
)

// ── M6 — "Canon at chapter N" public read surface (composition inspector) ────────
//
// Two PUBLIC, grant-gated (View) reads that let the composition canon-at-chapter
// panel answer "what does canon know as of chapter N" and "what does chapter N
// establish" WITHOUT exposing the /internal extraction routes to the browser. Both
// mirror listChapterLinks' guard order exactly: requireUserID → requireGrant(View).
// Under-grant / missing book → uniform 403 GLOSS_FORBIDDEN (no existence oracle),
// courtesy of requireGrant.

// knownEntityOut is the bare-array element for publicKnownEntities. first/last/
// coverage are folded in from the chapter-link aggregate so the panel can show a
// span + reach per entity (the /entities/stats fields) in one call.
type knownEntityOut struct {
	EntityID          string   `json:"entity_id"`
	Name              string   `json:"name"`
	KindCode          string   `json:"kind_code"`
	Aliases           []string `json:"aliases"`
	Frequency         int      `json:"frequency"`
	FirstChapterIndex *int     `json:"first_chapter_index"`
	LastChapterIndex  *int     `json:"last_chapter_index"`
	CoveragePct       float64  `json:"coverage_pct"`
}

// publicKnownEntities — GET /v1/glossary/books/{book_id}/known-entities
//
//	?before_chapter_index={int}  (optional — only count links strictly before this chapter;
//	                              omit/-1 ⇒ whole book)
//	&min_frequency={int}         (default 2 — min distinct-chapter appearances)
//	&limit={int}                 (default 50, cap 500)
//
// Public mirror of the internal getKnownEntities, with first/last/coverage folded in
// from the chapter-link aggregate. Bare-array response. View-grant gated.
func (s *Server) publicKnownEntities(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantView) {
		return
	}

	ctx := r.Context()
	q := r.URL.Query()
	beforeIdx := queryInt(q.Get("before_chapter_index"), -1)
	minFreq := queryInt(q.Get("min_frequency"), 2)
	limit := queryInt(q.Get("limit"), 50)
	if limit > 500 {
		limit = 500
	}
	if limit < 1 {
		limit = 1
	}

	// Window the chapter-link aggregate to links strictly before `before_chapter_index`
	// (when set). frequency = distinct linked chapters in-window; first/last = MIN/MAX
	// chapter_index in-window. Resolving the window by chapter_index (not id) keeps it
	// consistent with the FE cutoff; an unresolvable id is the caller's concern (it passes
	// the resolved index). Name + aliases mirror the internal handler's attribute_values
	// projection (name code 'name', aliases code 'aliases' as a JSON-array string).
	args := []any{bookID}
	argIdx := 2
	linkWhere := "cl.entity_id = e.entity_id"
	if beforeIdx >= 0 {
		linkWhere += " AND cl.chapter_index < $" + strconv.Itoa(argIdx)
		args = append(args, beforeIdx)
		argIdx++
	}
	minFreqParam := "$" + strconv.Itoa(argIdx)
	args = append(args, minFreq)
	argIdx++
	limitParam := "$" + strconv.Itoa(argIdx)
	args = append(args, limit)
	argIdx++
	// The STORY POSITION this read answers at (plan T52). `before_chapter_index` omitted (or
	// -1) means "the whole book", and a whole-book read has NO single position — asking for a
	// name "as of the whole book" is not a question. Then the position is NULL, the as-of
	// lateral below matches nothing, and the current value is used, which is the CORRECT read
	// rather than a degradation. Same reasoning composition's `_cast_roster` records for its
	// untimed catalogue read.
	asOfParam := "$" + strconv.Itoa(argIdx)
	var asOfArg any
	if beforeIdx >= 0 {
		asOfArg = int64(beforeIdx)
	}
	args = append(args, asOfArg)
	fellBackName, fellBackAlias := 0, 0

	query := `
		SELECT
			e.entity_id,
			k.code AS kind_code,
			-- D-GLOSSARY-KNOWN-ENTITIES-NAME-BLIND (same class): the name attribute
			-- does not exist on every kind (terminology identifies itself with term),
			-- so this rendered an empty name. cached_name is trigger-maintained and
			-- already kind-aware.
			-- T52 — resolve the name AS OF the requested chapter, not as of now. The as-of
			-- fact wins; the current attribute value is the FALLBACK, and the handler warns
			-- when it is used, because a silently-current name in a canon-at-chapter panel is
			-- a spoiler that looks like data.
			COALESCE(NULLIF(name_asof.value, ''), NULLIF(name_av.original_value, ''), e.cached_name, '')  AS entity_name,
			COALESCE(NULLIF(alias_asof.value, ''), alias_av.original_value, '') AS aliases_raw,
			(name_asof.value IS NULL)  AS name_fell_back,
			(alias_asof.value IS NULL) AS alias_fell_back,
			COUNT(DISTINCT cl.chapter_id)         AS frequency,
			MIN(cl.chapter_index)                 AS first_chapter_index,
			MAX(cl.chapter_index)                 AS last_chapter_index,
			COUNT(DISTINCT cl.chapter_id)         AS distinct_chapters
		FROM glossary_entities e
		JOIN book_kinds k ON k.book_kind_id = e.kind_id
		LEFT JOIN entity_attribute_values name_av
			ON name_av.entity_id = e.entity_id
			AND name_av.attr_def_id = (
				SELECT ba.attr_id FROM book_attributes ba
				JOIN book_genres g ON g.genre_id = ba.genre_id
				WHERE ba.kind_id = e.kind_id AND ba.code = 'name'
				ORDER BY (g.code = 'universal') DESC LIMIT 1
			)
		LEFT JOIN entity_attribute_values alias_av
			ON alias_av.entity_id = e.entity_id
			AND alias_av.attr_def_id = (
				SELECT ba.attr_id FROM book_attributes ba
				JOIN book_genres g ON g.genre_id = ba.genre_id
				WHERE ba.kind_id = e.kind_id AND ba.code = 'aliases'
				ORDER BY (g.code = 'universal') DESC LIMIT 1
			)
		-- ── the as-of resolution (T52 / decision D0) ──────────────────────────────────
		-- Same predicate as state@as_of: the half-open story interval
		-- [valid_from_ordinal, valid_to_eff). ORDER BY valid_from DESC so an
		-- overlapping-interval substrate bug degrades to "freshest wins" rather than
		-- "random wins" — the reasoning state_handler.go already records.
		LEFT JOIN LATERAL (
			SELECT f.value
			  FROM entity_facts f
			 WHERE f.entity_id = e.entity_id AND f.book_id = e.book_id
			   AND f.fact_kind = 'name'
			   AND f.invalidated_at IS NULL
			   AND ` + asOfParam + `::bigint IS NOT NULL
			   AND f.valid_from_ordinal <= ` + asOfParam + `::bigint
			   AND ` + asOfParam + `::bigint < f.valid_to_eff
			 ORDER BY f.valid_from_ordinal DESC
			 LIMIT 1
		) name_asof ON TRUE
		LEFT JOIN LATERAL (
			SELECT f.value
			  FROM entity_facts f
			 WHERE f.entity_id = e.entity_id AND f.book_id = e.book_id
			   AND f.fact_kind = 'alias'
			   AND f.invalidated_at IS NULL
			   AND ` + asOfParam + `::bigint IS NOT NULL
			   AND f.valid_from_ordinal <= ` + asOfParam + `::bigint
			   AND ` + asOfParam + `::bigint < f.valid_to_eff
			 ORDER BY f.valid_from_ordinal DESC
			 LIMIT 1
		) alias_asof ON TRUE
		JOIN chapter_entity_links cl ON ` + linkWhere + `
		WHERE e.book_id = $1 AND e.alive = true AND e.deleted_at IS NULL
		GROUP BY e.entity_id, k.code, name_av.original_value, alias_av.original_value,
		         name_asof.value, alias_asof.value
		HAVING COUNT(DISTINCT cl.chapter_id) >= ` + minFreqParam + `
		ORDER BY COUNT(DISTINCT cl.chapter_id) DESC, e.entity_id
		LIMIT ` + limitParam

	rows, err := s.pool.Query(ctx, query, args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to query known entities")
		return
	}
	defer rows.Close()

	type row struct {
		out              knownEntityOut
		distinctChapters int
	}
	var collected []row
	for rows.Next() {
		var rr row
		var aliasesRaw string
		var nameFellBack, aliasFellBack bool
		if err := rows.Scan(
			&rr.out.EntityID, &rr.out.KindCode, &rr.out.Name, &aliasesRaw,
			&nameFellBack, &aliasFellBack,
			&rr.out.Frequency, &rr.out.FirstChapterIndex, &rr.out.LastChapterIndex,
			&rr.distinctChapters,
		); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to scan entity")
			return
		}
		if rr.out.Name == "" {
			continue // skip nameless entities (mirrors the internal handler)
		}
		var aliases []string
		if aliasesRaw != "" {
			_ = json.Unmarshal([]byte(aliasesRaw), &aliases)
		}
		if aliases == nil {
			aliases = []string{}
		}
		rr.out.Aliases = aliases
		if beforeIdx >= 0 {
			if nameFellBack {
				fellBackName++
			}
			if aliasFellBack {
				fellBackAlias++
			}
		}
		collected = append(collected, rr)
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "row error")
		return
	}

	// T52's logging contract. DEBUG the resolved position and the per-field as-of source;
	// WARN when any field fell back to a CURRENT value, because that is the defect this task
	// exists to fix and it is otherwise invisible: a current name in a canon-at-chapter panel
	// is well-formed, plausible, and wrong — a spoiler that looks like data.
	//
	// Liveness is reported as a permanent fallback while D-T32-ALIVE-NO-FACTS is open: there
	// are 0 liveness facts, so `alive` is still the only source. Saying so on every timed read
	// is deliberate — an unmet precondition nobody is reminded of is one that never gets met.
	if beforeIdx >= 0 {
		slog.Debug("known-entities resolved at a story position",
			"book_id", bookID.String(), "as_of", beforeIdx,
			"entities", len(collected),
			"name_source", "entity_facts(fact_kind=name)",
			"alias_source", "entity_facts(fact_kind=alias)",
			"kind_source", "book_kinds (CURRENT - no kind facts exist)",
			"liveness_source", "glossary_entities.alive (CURRENT - no liveness facts exist)")
		if fellBackName > 0 || fellBackAlias > 0 {
			slog.Warn("known-entities fell back to CURRENT values on a timed read",
				"book_id", bookID.String(), "as_of", beforeIdx,
				"entities", len(collected),
				"name_fallbacks", fellBackName, "alias_fallbacks", fellBackAlias,
				"why", "no name/alias fact covers this position; the value shown is today's")
		}
		// Not conditional: these two have NO as-of source at all yet, so every timed read is
		// answering them with a current value.
		slog.Warn("known-entities cannot resolve kind or liveness as-of",
			"book_id", bookID.String(), "as_of", beforeIdx,
			"deferral", "D-T32-ALIVE-NO-FACTS")
	}

	// coverage_pct = distinct linked chapters / total book chapters, in [0,1]. Prefer
	// book-service (authoritative); degrade to a link-derived denominator on outage so
	// the read never 503s just for a coverage number (mirrors internalEntityStats).
	chapterCount := 0
	if chapters, status := s.fetchBookChapters(ctx, bookID); status == http.StatusOK {
		chapterCount = len(chapters)
	} else {
		for _, rr := range collected {
			if rr.out.LastChapterIndex != nil && *rr.out.LastChapterIndex+1 > chapterCount {
				chapterCount = *rr.out.LastChapterIndex + 1
			}
		}
	}

	result := make([]knownEntityOut, 0, len(collected))
	for _, rr := range collected {
		cov := 0.0
		if chapterCount > 0 {
			cov = float64(rr.distinctChapters) / float64(chapterCount)
		}
		rr.out.CoveragePct = cov
		result = append(result, rr.out)
	}
	writeJSON(w, http.StatusOK, result)
}

// chapterEntityOut is the bare-array element for publicChapterEntities.
type chapterEntityOut struct {
	EntityID     string `json:"entity_id"`
	Name         string `json:"name"`
	KindCode     string `json:"kind_code"`
	Relevance    string `json:"relevance"`
	ChapterIndex *int   `json:"chapter_index"`
	MentionCount int    `json:"mention_count"`
}

// publicChapterEntities — GET /v1/glossary/books/{book_id}/chapter-entities?chapter_id={uuid}
//
// The NEW chapter→entities direction (uses idx_cel_chapter): every entity LINKED to
// the given chapter, with its 3-level relevance, the link's chapter_index, and the M7
// per-chapter mention_count. Bare-array response, sorted by relevance (major→appears→
// mentioned) then mention_count desc. View-grant gated.
func (s *Server) publicChapterEntities(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantView) {
		return
	}

	chapterRaw := r.URL.Query().Get("chapter_id")
	chapterID, err := uuid.Parse(chapterRaw)
	if err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "chapter_id query param must be a UUID")
		return
	}

	// Chapter→entities via idx_cel_chapter. Scope to the book (join glossary_entities,
	// filter book_id) so a chapter_id from another tenant's book can't leak rows — the
	// caller is already View-granted on THIS book. Name from cached_name (the maintained
	// display column, as entity_stats uses); relevance ordered major→appears→mentioned.
	rows, err := s.pool.Query(r.Context(), `
		SELECT cel.entity_id,
		       COALESCE(e.cached_name, '') AS name,
		       k.code                      AS kind_code,
		       cel.relevance,
		       cel.chapter_index,
		       cel.mention_count
		FROM chapter_entity_links cel
		JOIN glossary_entities e ON e.entity_id = cel.entity_id
		JOIN book_kinds k        ON k.book_kind_id = e.kind_id
		WHERE cel.chapter_id = $1
		  AND e.book_id = $2
		  AND e.deleted_at IS NULL
		ORDER BY CASE cel.relevance
		           WHEN 'major'     THEN 0
		           WHEN 'appears'   THEN 1
		           WHEN 'mentioned' THEN 2
		           ELSE 3 END,
		         cel.mention_count DESC,
		         cel.entity_id`, chapterID, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to query chapter entities")
		return
	}
	defer rows.Close()

	result := []chapterEntityOut{}
	for rows.Next() {
		var ce chapterEntityOut
		if err := rows.Scan(
			&ce.EntityID, &ce.Name, &ce.KindCode,
			&ce.Relevance, &ce.ChapterIndex, &ce.MentionCount,
		); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to scan chapter entity")
			return
		}
		result = append(result, ce)
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "row error")
		return
	}
	writeJSON(w, http.StatusOK, result)
}
