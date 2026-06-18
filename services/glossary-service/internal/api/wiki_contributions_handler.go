package api

// Cross-book "wiki contributions by user" for the public profile page
// (LW-PLAN-MVP-RELEASE UI-2a). Lists the distinct wiki articles a user has authored a
// revision on. Visibility: the user sees all their own contributions; everyone else
// (incl. anonymous) sees only PUBLISHED articles in books whose wiki is public.

import (
	"net/http"
	"time"

	"github.com/google/uuid"
)

type wikiContributionItem struct {
	ArticleID         string      `json:"article_id"`
	EntityID          string      `json:"entity_id"`
	BookID            string      `json:"book_id"`
	DisplayName       string      `json:"display_name"`
	Kind              kindSummary `json:"kind"`
	Status            string      `json:"status"`
	LastContributedAt time.Time   `json:"last_contributed_at"`
}

// wikiContributionVisible decides whether one of a user's contributions is shown to a
// given viewer. Pure — unit-testable without a DB or book-service. Self sees all;
// others see only published articles whose book wiki visibility is "public".
func wikiContributionVisible(isSelf bool, articleStatus, wikiVisibility string) bool {
	if isSelf {
		return true
	}
	return articleStatus == "published" && wikiVisibility == "public"
}

func (s *Server) listUserWikiContributions(w http.ResponseWriter, r *http.Request) {
	targetUser, ok := parsePathUUID(w, r, "user_id")
	if !ok {
		return
	}
	// Optional auth: a present+valid token identifies the caller (for self-view);
	// no token = anonymous (public-only).
	caller, authed := s.requireUserID(r)
	isSelf := authed && caller == targetUser

	q := r.URL.Query()
	limit := min(queryInt(q.Get("limit"), 50), 100)
	offset := queryInt(q.Get("offset"), 0)

	rows, err := s.pool.Query(r.Context(), `
		SELECT wa.article_id, wa.entity_id, wa.book_id, wa.status,
		       COALESCE(dn.original_value, '') AS display_name,
		       ek.kind_id, ek.code, ek.name, ek.icon, ek.color,
		       MAX(wr.created_at) AS last_contributed_at
		FROM wiki_revisions wr
		JOIN wiki_articles wa ON wa.article_id = wr.article_id
		JOIN glossary_entities ge ON ge.entity_id = wa.entity_id
		JOIN system_kinds ek ON ek.kind_id = ge.kind_id
		LEFT JOIN entity_attribute_values dn ON dn.entity_id = ge.entity_id
			AND dn.attr_def_id = (
				SELECT ad.attr_def_id FROM system_kind_attributes ad
				WHERE ad.kind_id = ge.kind_id AND ad.code IN ('name','term')
				ORDER BY ad.sort_order LIMIT 1
			)
		WHERE wr.author_id = $1
		GROUP BY wa.article_id, wa.entity_id, wa.book_id, wa.status,
		         dn.original_value, ek.kind_id, ek.code, ek.name, ek.icon, ek.color
		ORDER BY last_contributed_at DESC
		LIMIT $2 OFFSET $3`, targetUser, limit, offset)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	defer rows.Close()

	var raw []wikiContributionItem
	for rows.Next() {
		var it wikiContributionItem
		if err := rows.Scan(
			&it.ArticleID, &it.EntityID, &it.BookID, &it.Status,
			&it.DisplayName,
			&it.Kind.KindID, &it.Kind.Code, &it.Kind.Name, &it.Kind.Icon, &it.Kind.Color,
			&it.LastContributedAt,
		); err != nil {
			continue
		}
		raw = append(raw, it)
	}

	// Apply visibility. For non-self viewers, resolve each book's wiki visibility once
	// (cached) via the book-service projection.
	visCache := map[string]string{}
	items := []wikiContributionItem{}
	for _, it := range raw {
		vis := ""
		if !isSelf {
			v, cached := visCache[it.BookID]
			if !cached {
				if bid, perr := uuid.Parse(it.BookID); perr == nil {
					if proj, status := s.fetchBookProjection(r.Context(), bid); status == http.StatusOK && proj.WikiSettings != nil {
						v = proj.WikiSettings.Visibility
					}
				}
				visCache[it.BookID] = v
			}
			vis = v
		}
		if wikiContributionVisible(isSelf, it.Status, vis) {
			items = append(items, it)
		}
	}

	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}
