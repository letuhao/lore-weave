package api

// mui #1c — entity-resolution / coreference merge (EXECUTE layer, R5).
//
//	POST /v1/glossary/books/{book_id}/entities/{winner_id}/merge   body {loser_ids}
//	POST /v1/glossary/books/{book_id}/merge-journal/{journal_id}/revert
//
// Reversibility model (spec §3.3): the merge SOFT-deletes each loser and
// repoints only NON-conflicting child rows to the winner; conflicting rows stay
// with the (now hidden) loser. The merge_journal records the exact child-row
// PKs repointed + the winner's `aliases` value before folding, so revert
// replays them back without row snapshots. All mutations for one loser run in a
// single transaction; events emit best-effort post-commit.

import (
	"context"
	"encoding/json"
	"net/http"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/loreweave/grantclient"
)

type mergeRequest struct {
	LoserIDs []string `json:"loser_ids"`
}

type mergeResultItem struct {
	LoserID   string `json:"loser_id"`
	JournalID string `json:"journal_id"`
	Status    string `json:"status"` // "merged" | "skipped"
	Reason    string `json:"reason,omitempty"`
}

// entityNameAndAliases reads an entity's name + aliases (parsed from the JSON
// array stored in the 'aliases' attribute). Missing → "" / nil.
func entityNameAndAliases(ctx context.Context, q pgxQuerier, entityID uuid.UUID) (name string, aliases []string) {
	rows, err := q.(interface {
		Query(context.Context, string, ...any) (pgx.Rows, error)
	}).Query(ctx, `
		SELECT ad.code, eav.original_value
		FROM entity_attribute_values eav
		JOIN system_kind_attributes ad ON ad.attr_def_id = eav.attr_def_id
		WHERE eav.entity_id = $1 AND ad.code IN ('name','aliases')`, entityID)
	if err != nil {
		return "", nil
	}
	defer rows.Close()
	for rows.Next() {
		var code, val string
		if rows.Scan(&code, &val) != nil {
			continue
		}
		switch code {
		case "name":
			name = val
		case "aliases":
			_ = json.Unmarshal([]byte(val), &aliases) // best-effort; bad JSON → nil
		}
	}
	return name, aliases
}

func dedupStrings(in []string) []string {
	seen := map[string]struct{}{}
	out := make([]string, 0, len(in))
	for _, s := range in {
		if s == "" {
			continue
		}
		if _, ok := seen[s]; ok {
			continue
		}
		seen[s] = struct{}{}
		out = append(out, s)
	}
	return out
}

// scanUUIDs runs an UPDATE ... RETURNING <uuid col> and collects the ids.
func scanUUIDs(ctx context.Context, tx pgx.Tx, sql string, args ...any) ([]uuid.UUID, error) {
	rows, err := tx.Query(ctx, sql, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	ids := []uuid.UUID{}
	for rows.Next() {
		var id uuid.UUID
		if err := rows.Scan(&id); err != nil {
			return nil, err
		}
		ids = append(ids, id)
	}
	return ids, rows.Err()
}

// mergeEntities merges one or more loser entities into a winner.
func (s *Server) mergeEntities(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	winnerID, ok := parsePathUUID(w, r, "entity_id")
	if !ok {
		return
	}
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantManage) {
		return
	}

	var req mergeRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON body")
		return
	}
	if len(req.LoserIDs) == 0 {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_NO_LOSERS", "loser_ids required")
		return
	}

	ctx := r.Context()

	// Winner must exist, live, in this book — resolve its kind for the same-kind check.
	var winnerKind uuid.UUID
	var winnerDeleted *time.Time
	var winnerBook uuid.UUID
	if err := s.pool.QueryRow(ctx,
		`SELECT kind_id, deleted_at, book_id FROM glossary_entities WHERE entity_id = $1`, winnerID,
	).Scan(&winnerKind, &winnerDeleted, &winnerBook); err != nil {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "winner entity not found")
		return
	}
	if winnerBook != bookID || winnerDeleted != nil {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_BAD_WINNER", "winner not a live entity in this book")
		return
	}

	results := make([]mergeResultItem, 0, len(req.LoserIDs))
	mergedLosers := make([]uuid.UUID, 0, len(req.LoserIDs))
	for _, raw := range req.LoserIDs {
		loserID, err := uuid.Parse(raw)
		if err != nil {
			results = append(results, mergeResultItem{LoserID: raw, Status: "skipped", Reason: "invalid uuid"})
			continue
		}
		jid, reason, merr := s.mergeOne(ctx, bookID, winnerID, winnerKind, loserID, userID)
		if merr != nil {
			// MED-3b: don't abort the whole request — earlier losers already
			// committed. Record this one as failed and continue so the response
			// reports per-loser outcomes (each merge is independently journaled).
			results = append(results, mergeResultItem{LoserID: raw, Status: "failed", Reason: merr.Error()})
			continue
		}
		if reason != "" {
			results = append(results, mergeResultItem{LoserID: raw, Status: "skipped", Reason: reason})
			continue
		}
		results = append(results, mergeResultItem{LoserID: raw, JournalID: jid.String(), Status: "merged"})
		mergedLosers = append(mergedLosers, loserID)
		// Best-effort events post-commit: winner re-synced (aliases changed) +
		// the merged signal that drives KG merge_entities + alias_map (K-sync).
		s.emitEntityUpdated(ctx, winnerID, "updated")
		_ = insertMergedOutboxEvent(ctx, func(ctx context.Context, sql string, args ...any) error {
			_, e := s.pool.Exec(ctx, sql, args...)
			return e
		}, winnerID, entityMergedPayload{
			BookID: bookID.String(), WinnerEntityID: winnerID.String(),
			LoserEntityID: loserID.String(), Op: "merged",
			EmittedAt: time.Now().UTC().Format(time.RFC3339),
		})
	}

	// G-cand: a confirmed cluster shouldn't keep showing in the inbox. Flip only
	// candidates fully resolved by THIS request (winner present + every member in
	// {winner}∪{merged losers}) — a partial merge of a larger cluster leaves it
	// proposed (review-impl MED-1). Done once after the loop with the full
	// merged-loser set so subset semantics are exact.
	s.markCandidatesMerged(ctx, bookID, winnerID, mergedLosers)

	writeJSON(w, http.StatusOK, map[string]any{"winner_id": winnerID.String(), "results": results})
}

// mergeOne performs the transactional merge of one loser into the winner.
// Returns (journal_id, "", nil) on success or ("", reason, nil) on a validation
// skip; a non-nil error is a real failure (caller 500s, tx rolled back).
func (s *Server) mergeOne(
	ctx context.Context, bookID, winnerID, winnerKind, loserID, actor uuid.UUID,
) (uuid.UUID, string, error) {
	if loserID == winnerID {
		return uuid.Nil, "same entity", nil
	}
	// Validate loser: live + same book + same kind.
	var loserKind, loserBook uuid.UUID
	var loserDeleted *time.Time
	if err := s.pool.QueryRow(ctx,
		`SELECT kind_id, deleted_at, book_id FROM glossary_entities WHERE entity_id = $1`, loserID,
	).Scan(&loserKind, &loserDeleted, &loserBook); err != nil {
		return uuid.Nil, "loser not found", nil
	}
	if loserBook != bookID || loserDeleted != nil {
		return uuid.Nil, "loser not a live entity in this book", nil
	}
	if loserKind != winnerKind {
		return uuid.Nil, "different kind", nil
	}

	// Read names/aliases BEFORE mutating (loser's name/aliases stay with loser
	// since the winner already has those attrs — they conflict — but read now
	// to be order-independent).
	loserName, loserAliases := entityNameAndAliases(ctx, s.pool, loserID)

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return uuid.Nil, "", err
	}
	defer tx.Rollback(ctx)

	// Lock both rows + re-validate liveness INSIDE the tx (MED-2: closes the
	// TOCTOU between the pool-level validation above and the repoint — a
	// concurrent merge/revert/delete of either side can't interleave). The
	// ANY+ORDER BY locks in a deterministic order to avoid deadlock.
	{
		lrows, lerr := tx.Query(ctx,
			`SELECT entity_id, deleted_at FROM glossary_entities
			 WHERE entity_id = ANY($1::uuid[]) ORDER BY entity_id FOR UPDATE`,
			[]uuid.UUID{winnerID, loserID})
		if lerr != nil {
			return uuid.Nil, "", lerr
		}
		live := map[uuid.UUID]bool{}
		for lrows.Next() {
			var id uuid.UUID
			var del *time.Time
			if e := lrows.Scan(&id, &del); e != nil {
				lrows.Close()
				return uuid.Nil, "", e
			}
			live[id] = del == nil
		}
		lrows.Close()
		if e := lrows.Err(); e != nil {
			return uuid.Nil, "", e
		}
		if !live[winnerID] {
			return uuid.Nil, "winner not a live entity in this book", nil
		}
		if !live[loserID] {
			return uuid.Nil, "loser not a live entity in this book", nil
		}
	}

	// Resolve the kind's aliases attr_def up front. The aliases attribute is
	// handled ONLY by the fold below — the generic EAV repoint EXCLUDES it — so
	// the same row can never be both repointed AND folded, which would corrupt
	// the loser's aliases on revert (MED-1).
	var aliasDef uuid.UUID
	var aliasDefPtr *uuid.UUID
	if tx.QueryRow(ctx,
		`SELECT attr_def_id FROM system_kind_attributes WHERE kind_id = $1 AND code = 'aliases' LIMIT 1`,
		winnerKind,
	).Scan(&aliasDef) == nil {
		aliasDefPtr = &aliasDef
	}

	// 1. Repoint NON-conflicting child rows loser→winner, collecting PKs.
	chLinks, err := scanUUIDs(ctx, tx, `
		UPDATE chapter_entity_links SET entity_id = $1
		WHERE entity_id = $2
		  AND chapter_id NOT IN (SELECT chapter_id FROM chapter_entity_links WHERE entity_id = $1)
		RETURNING link_id`, winnerID, loserID)
	if err != nil {
		return uuid.Nil, "", err
	}
	eavs, err := scanUUIDs(ctx, tx, `
		UPDATE entity_attribute_values SET entity_id = $1
		WHERE entity_id = $2
		  AND ($3::uuid IS NULL OR attr_def_id <> $3)
		  AND attr_def_id NOT IN (SELECT attr_def_id FROM entity_attribute_values WHERE entity_id = $1)
		RETURNING attr_value_id`, winnerID, loserID, aliasDefPtr)
	if err != nil {
		return uuid.Nil, "", err
	}
	enrich, err := scanUUIDs(ctx, tx, `
		UPDATE entity_enrichments SET entity_id = $1
		WHERE entity_id = $2
		  AND (dimension, proposal_id) NOT IN
		      (SELECT dimension, proposal_id FROM entity_enrichments WHERE entity_id = $1)
		RETURNING enrichment_id`, winnerID, loserID)
	if err != nil {
		return uuid.Nil, "", err
	}
	audit, err := scanUUIDs(ctx, tx,
		`UPDATE extraction_audit_log SET entity_id = $1 WHERE entity_id = $2 RETURNING id`,
		winnerID, loserID)
	if err != nil {
		return uuid.Nil, "", err
	}
	// wiki (Bug-1 fix, merge-spec AC4): repoint the loser's article to the winner
	// when the winner has NONE. When BOTH have an article, the loser's is ARCHIVED
	// in place (superseded_by_entity_id := winner) — kept, revision-preserved, and
	// resolvable via redirect — never silently abandoned. Bodies are NOT auto-merged
	// (the winner's stays canonical; merge-and-regenerate is later wiki-LLM work).
	var wikiArticle, supersededWiki *uuid.UUID
	wikiRepoint, err := scanUUIDs(ctx, tx, `
		UPDATE wiki_articles SET entity_id = $1, updated_at = now()
		WHERE entity_id = $2 AND NOT EXISTS (SELECT 1 FROM wiki_articles WHERE entity_id = $1)
		RETURNING article_id`, winnerID, loserID)
	if err != nil {
		return uuid.Nil, "", err
	}
	if len(wikiRepoint) == 1 {
		wikiArticle = &wikiRepoint[0]
	} else {
		// repoint was a no-op → either the loser has no article (nothing to do) or
		// BOTH have one → archive the loser's in place, pointing at the winner.
		wikiArchive, aerr := scanUUIDs(ctx, tx, `
			UPDATE wiki_articles SET superseded_by_entity_id = $1, updated_at = now()
			WHERE entity_id = $2 AND superseded_by_entity_id IS NULL
			RETURNING article_id`, winnerID, loserID)
		if aerr != nil {
			return uuid.Nil, "", aerr
		}
		if len(wikiArchive) == 1 {
			supersededWiki = &wikiArchive[0]
		}
	}

	// 2. Fold loser name + aliases into the winner's aliases (anti-resurrection:
	//    a future extract-entities with the loser name resolves to the winner).
	//    Uses the aliasDef resolved up front (excluded from the EAV repoint).
	var aliasesBefore *string
	if aliasDefPtr != nil {
		winnerName, winnerAliases := entityNameAndAliases(ctx, tx, winnerID)
		merged := dedupStrings(append(append(append([]string{}, winnerAliases...), loserAliases...), loserName))
		// drop the winner's own name from its aliases (never alias-to-self)
		final := merged[:0]
		for _, a := range merged {
			if a != winnerName {
				final = append(final, a)
			}
		}
		newJSON, _ := json.Marshal(final)
		var prev string
		err := tx.QueryRow(ctx,
			`SELECT original_value FROM entity_attribute_values WHERE entity_id = $1 AND attr_def_id = $2`,
			winnerID, aliasDef,
		).Scan(&prev)
		if err == nil {
			aliasesBefore = &prev
			if _, e := tx.Exec(ctx,
				`UPDATE entity_attribute_values SET original_value = $1 WHERE entity_id = $2 AND attr_def_id = $3`,
				string(newJSON), winnerID, aliasDef); e != nil {
				return uuid.Nil, "", e
			}
		} else { // winner had no aliases row → insert (aliasesBefore stays nil → revert deletes)
			if _, e := tx.Exec(ctx, `
				INSERT INTO entity_attribute_values (entity_id, attr_def_id, original_language, original_value)
				VALUES ($1, $2, 'zh', $3)`, winnerID, aliasDef, string(newJSON)); e != nil {
				return uuid.Nil, "", e
			}
		}
	}

	// 3. Soft-delete the loser (hidden; conflicting rows stay attached to it).
	if _, err := tx.Exec(ctx,
		`UPDATE glossary_entities SET deleted_at = now(), merged_into_entity_id = $1 WHERE entity_id = $2`,
		winnerID, loserID); err != nil {
		return uuid.Nil, "", err
	}

	// 4. Journal (for revert).
	var journalID uuid.UUID
	if err := tx.QueryRow(ctx, `
		INSERT INTO merge_journal
		  (book_id, winner_entity_id, loser_entity_id, repointed_chapter_link_ids,
		   repointed_eav_ids, repointed_enrichment_ids, repointed_audit_ids,
		   repointed_wiki_article_id, superseded_wiki_article_id, winner_aliases_before, merged_by)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) RETURNING journal_id`,
		bookID, winnerID, loserID, chLinks, eavs, enrich, audit, wikiArticle, supersededWiki, aliasesBefore, actor,
	).Scan(&journalID); err != nil {
		return uuid.Nil, "", err
	}

	if err := tx.Commit(ctx); err != nil {
		return uuid.Nil, "", err
	}
	return journalID, "", nil
}

// revertMerge undoes a merge by replaying its journal.
func (s *Server) revertMerge(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	journalID, ok := parsePathUUID(w, r, "journal_id")
	if !ok {
		return
	}
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantManage) {
		return
	}
	reason, err := s.revertMergeCore(r.Context(), bookID, journalID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "revert failed: "+err.Error())
		return
	}
	switch reason {
	case "":
		writeJSON(w, http.StatusOK, map[string]any{"journal_id": journalID.String(), "status": "reverted"})
	case "not_found":
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "merge journal not found")
	case "wrong_book":
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_BAD_BOOK", "journal not in this book")
	case "already_reverted":
		writeError(w, http.StatusConflict, "GLOSS_ALREADY_REVERTED", "merge already reverted")
	case "winner_since_merged":
		writeError(w, http.StatusConflict, "GLOSS_WINNER_SINCE_MERGED", "winner has since been merged; revert the later merge first")
	default:
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", reason)
	}
}

// revertMergeCore replays a merge journal to undo the merge. Returns ("", nil)
// on success, (businessReason, nil) for a 4xx condition, or (_, err) for a 500.
// Auth/ownership is the caller's concern (so this is unit-testable without
// book-service).
func (s *Server) revertMergeCore(ctx context.Context, bookID, journalID uuid.UUID) (string, error) {
	var (
		winnerID, loserID uuid.UUID
		jBook             uuid.UUID
		chLinks, eavs     []uuid.UUID
		enrich, audit     []uuid.UUID
		wikiArticle       *uuid.UUID
		supersededWiki    *uuid.UUID
		aliasesBefore     *string
		status            string
	)
	if err := s.pool.QueryRow(ctx, `
		SELECT book_id, winner_entity_id, loser_entity_id, repointed_chapter_link_ids,
		       repointed_eav_ids, repointed_enrichment_ids, repointed_audit_ids,
		       repointed_wiki_article_id, superseded_wiki_article_id, winner_aliases_before, status
		FROM merge_journal WHERE journal_id = $1`, journalID,
	).Scan(&jBook, &winnerID, &loserID, &chLinks, &eavs, &enrich, &audit, &wikiArticle, &supersededWiki, &aliasesBefore, &status); err != nil {
		return "not_found", nil
	}
	if jBook != bookID {
		return "wrong_book", nil
	}
	if status != "merged" {
		return "already_reverted", nil
	}
	// Chain-merge guard (MED-3a): if the winner has SINCE been merged away, its
	// rows (incl. ones this journal moved onto it) have moved on to a later
	// winner — reverting now would yank them to the loser incorrectly. Force
	// LIFO: the later merge must be reverted first.
	var winnerMergedInto *uuid.UUID
	if err := s.pool.QueryRow(ctx,
		`SELECT merged_into_entity_id FROM glossary_entities WHERE entity_id = $1`, winnerID,
	).Scan(&winnerMergedInto); err == nil && winnerMergedInto != nil {
		return "winner_since_merged", nil
	}

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return "", err
	}
	defer tx.Rollback(ctx)

	// Repoint the moved rows back to the loser.
	if _, err := tx.Exec(ctx, `UPDATE chapter_entity_links SET entity_id=$1 WHERE link_id = ANY($2::uuid[])`, loserID, chLinks); err != nil {
		return "", err
	}
	if _, err := tx.Exec(ctx, `UPDATE entity_attribute_values SET entity_id=$1 WHERE attr_value_id = ANY($2::uuid[])`, loserID, eavs); err != nil {
		return "", err
	}
	if _, err := tx.Exec(ctx, `UPDATE entity_enrichments SET entity_id=$1 WHERE enrichment_id = ANY($2::uuid[])`, loserID, enrich); err != nil {
		return "", err
	}
	if _, err := tx.Exec(ctx, `UPDATE extraction_audit_log SET entity_id=$1 WHERE id = ANY($2::uuid[])`, loserID, audit); err != nil {
		return "", err
	}
	if wikiArticle != nil {
		if _, err := tx.Exec(ctx, `UPDATE wiki_articles SET entity_id=$1 WHERE article_id=$2`, loserID, *wikiArticle); err != nil {
			return "", err
		}
	}
	// Un-archive a superseded loser article (Bug-1 fix): clear the redirect so the
	// restored loser entity's article is live again.
	if supersededWiki != nil {
		if _, err := tx.Exec(ctx, `UPDATE wiki_articles SET superseded_by_entity_id=NULL, updated_at=now() WHERE article_id=$1`, *supersededWiki); err != nil {
			return "", err
		}
	}
	// Restore the winner's aliases (or delete the row we inserted).
	var aliasDef uuid.UUID
	if e := tx.QueryRow(ctx, `SELECT ad.attr_def_id FROM system_kind_attributes ad JOIN glossary_entities ge ON ge.kind_id=ad.kind_id WHERE ge.entity_id=$1 AND ad.code='aliases' LIMIT 1`, winnerID).Scan(&aliasDef); e == nil {
		if aliasesBefore != nil {
			if _, err := tx.Exec(ctx, `UPDATE entity_attribute_values SET original_value=$1 WHERE entity_id=$2 AND attr_def_id=$3`, *aliasesBefore, winnerID, aliasDef); err != nil {
				return "", err
			}
		} else {
			if _, err := tx.Exec(ctx, `DELETE FROM entity_attribute_values WHERE entity_id=$1 AND attr_def_id=$2`, winnerID, aliasDef); err != nil {
				return "", err
			}
		}
	}
	// Restore the loser (un-soft-delete) + mark journal reverted.
	if _, err := tx.Exec(ctx, `UPDATE glossary_entities SET deleted_at=NULL, merged_into_entity_id=NULL WHERE entity_id=$1`, loserID); err != nil {
		return "", err
	}
	if _, err := tx.Exec(ctx, `UPDATE merge_journal SET status='reverted', reverted_at=now() WHERE journal_id=$1`, journalID); err != nil {
		return "", err
	}
	if err := tx.Commit(ctx); err != nil {
		return "", err
	}

	// Re-sync both sides + emit the compensating merged(op=unmerged) signal.
	s.emitEntityUpdated(ctx, winnerID, "updated")
	s.emitEntityUpdated(ctx, loserID, "updated")
	_ = insertMergedOutboxEvent(ctx, func(ctx context.Context, sql string, args ...any) error {
		_, e := s.pool.Exec(ctx, sql, args...)
		return e
	}, winnerID, entityMergedPayload{
		BookID: bookID.String(), WinnerEntityID: winnerID.String(),
		LoserEntityID: loserID.String(), Op: "unmerged",
		EmittedAt: time.Now().UTC().Format(time.RFC3339),
	})

	return "", nil
}
