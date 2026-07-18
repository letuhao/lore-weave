package api

// C-merge — after the parts subsystem was retired from book-service (C4), the .txt import re-creates
// the source document's part grouping in COMPOSITION (structure_node kind='part') by forwarding the
// importing user's bearer to composition's public POST /parts, then stamping chapters.structure_node_id.
//
// BEST-EFFORT by design: any failure (config unset, composition unreachable, a non-2xx) leaves the
// chapters FLAT — the import itself already committed. Grouping is a nicety, never a reason to fail an
// import. Single-part imports skip this entirely (nothing to group).

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"strings"

	"github.com/google/uuid"
)

// groupImportedChaptersIntoParts creates one composition part per source part (in order) and homes its
// chapters via chapters.structure_node_id. titles[i] is part i's title; partChapters[i] its chapter ids.
func (s *Server) groupImportedChaptersIntoParts(ctx context.Context, bearer, bookID string, titles []string, partChapters map[int][]uuid.UUID) {
	base := strings.TrimRight(s.cfg.CompositionServiceURL, "/")
	if base == "" || bearer == "" {
		return
	}
	// Deterministic order (map iteration is random) so parts get sort_order 1..N matching the source.
	for idx := 0; idx < len(titles); idx++ {
		chapterIDs := partChapters[idx]
		if len(chapterIDs) == 0 {
			continue
		}
		partID, err := s.createCompositionPart(ctx, base, bearer, bookID, titles[idx])
		if err != nil {
			slog.Warn("import: composition part create failed; chapters stay flat", "book_id", bookID, "err", err)
			continue
		}
		if _, err := s.pool.Exec(ctx,
			`UPDATE chapters SET structure_node_id=$1, updated_at=now() WHERE book_id=$2 AND id = ANY($3)`,
			partID, bookID, chapterIDs); err != nil {
			slog.Warn("import: home imported chapters into part failed", "book_id", bookID, "err", err)
		}
	}
}

func (s *Server) createCompositionPart(ctx context.Context, base, bearer, bookID, title string) (uuid.UUID, error) {
	body, _ := json.Marshal(map[string]any{"title": title})
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, base+"/v1/composition/books/"+bookID+"/parts", bytes.NewReader(body))
	if err != nil {
		return uuid.Nil, err
	}
	req.Header.Set("Authorization", bearer)
	req.Header.Set("Content-Type", "application/json")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return uuid.Nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusCreated {
		return uuid.Nil, fmt.Errorf("composition POST /parts → %d", resp.StatusCode)
	}
	var out struct {
		PartID uuid.UUID `json:"part_id"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return uuid.Nil, err
	}
	return out.PartID, nil
}
