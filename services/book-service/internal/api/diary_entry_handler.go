package api

// WS-1.8 (spec 06 §Q5/§Q6/§Q10) — the journal distiller's WRITE seam.
//
// The map-reduce worker has no user JWT and book-service /internal was read-only, so this is the
// one internal-token, owner-scoped, DRAFT-ONLY chapter write. It turns a distilled day into a
// diary chapter, reusing the existing chapter machinery (Tiptap body + draft/raw/revision rows)
// but with three journal-specific invariants the red team demanded:
//
//   - Idempotent PRIMARY-per-day (§Q6): at most one active primary entry per (book, day). Two
//     devices clicking "End my day" at once COALESCE on a (owner, day) advisory lock instead of
//     minting two entries or racing the partial unique.
//   - REPLACE, never append (§Q5): a re-distill of the same day REPLACES the draft body. Appending
//     would duplicate content on every catch-up sweep. A KEPT entry (post-confirm) is never
//     clobbered — the caller must write a 'supplement' instead.
//   - Diary-only, owner-only (DR-12 discipline): the entry can only land in the caller's own
//     kind='diary' book. Never a shareable novel, never another user's book.
//
// It deliberately does NOT emit chapter.created: that event enrolls a book into the reading /
// statistics aggregates meant for browsable novels, and the diary is deliberately outside them
// (the same principle as the WS-1.2 egress guards that hide it from the library grid).

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

type diaryEntryRequest struct {
	OwnerUserID string `json:"owner_user_id"`
	EntryDate   string `json:"entry_date"` // the LOCAL day (YYYY-MM-DD) the distiller resolved
	EntryZone   string `json:"entry_zone"` // IANA zone in effect (§Q3/T21 auditability)
	Title       string `json:"title"`
	Body        string `json:"body"`        // the distilled prose
	JournalKind string `json:"journal_kind"` // 'primary' (default) | 'supplement'
	Language    string `json:"language"`
}

func (s *Server) upsertDiaryEntry(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	var in diaryEntryRequest
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_BAD_REQUEST", "invalid body")
		return
	}
	owner, err := uuid.Parse(strings.TrimSpace(in.OwnerUserID))
	if err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_BAD_REQUEST", "owner_user_id required")
		return
	}
	entryDate, err := time.Parse("2006-01-02", strings.TrimSpace(in.EntryDate))
	if err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_BAD_REQUEST", "entry_date must be YYYY-MM-DD")
		return
	}
	kind := strings.TrimSpace(in.JournalKind)
	if kind == "" {
		kind = "primary"
	}
	if kind != "primary" && kind != "supplement" {
		writeError(w, http.StatusBadRequest, "BOOK_BAD_REQUEST", "journal_kind must be primary|supplement")
		return
	}
	body := in.Body
	if strings.TrimSpace(body) == "" {
		// A low-signal day ⇒ NO entry (spec §Q11) — the worker decides that and never calls here.
		// An empty body reaching this route is a caller bug, not a blank entry to persist.
		writeError(w, http.StatusBadRequest, "BOOK_BAD_REQUEST", "body required (a low-signal day writes no entry)")
		return
	}
	lang := strings.TrimSpace(in.Language)
	if lang == "" {
		lang = "en"
	}
	zone := strings.TrimSpace(in.EntryZone)
	if zone == "" {
		zone = "UTC"
	}
	title := strings.TrimSpace(in.Title)
	if title == "" {
		title = entryDate.Format("Mon, 02 Jan 2006")
	}

	ctx := r.Context()

	// 1. The target MUST be the caller's own ACTIVE diary (DR-12 discipline).
	var bookOwner uuid.UUID
	var bookKind, lifecycle string
	err = s.pool.QueryRow(ctx,
		`SELECT owner_user_id, kind, lifecycle_state FROM books WHERE id=$1`, bookID).
		Scan(&bookOwner, &bookKind, &lifecycle)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "book not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to read book")
		return
	}
	if bookKind != "diary" {
		writeError(w, http.StatusConflict, "BOOK_NOT_DIARY", "diary entries only write to a kind='diary' book")
		return
	}
	if bookOwner != owner {
		writeError(w, http.StatusForbidden, "BOOK_FORBIDDEN", "owner_user_id does not own this diary")
		return
	}
	if lifecycle != "active" {
		writeError(w, http.StatusConflict, "BOOK_INACTIVE", "diary is not active")
		return
	}

	if err := s.ensureQuotaRow(ctx, owner); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to initialize quota")
		return
	}

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to begin")
		return
	}
	defer tx.Rollback(ctx)

	// 2. Coalesce concurrent same-day writes across devices (§Q6). All primary/supplement writes
	//    for one (owner, day) serialize here, so the get-or-create-then-replace below is race-safe
	//    and two "End my day" clicks converge on one entry. Released at tx end.
	lockKey := owner.String() + "|" + entryDate.Format("2006-01-02")
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock(hashtext($1))`, lockKey); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to acquire day lock")
		return
	}

	jsonBody := plainTextToTiptapJSON(body)
	byteSize := int64(len(body))

	// 3. PRIMARY: get-or-create-then-replace. (Supplement always creates a new chapter.)
	if kind == "primary" {
		var chID uuid.UUID
		var kept *time.Time
		var oldSize int64
		err = tx.QueryRow(ctx,
			`SELECT id, diary_kept_at, byte_size FROM chapters
			   WHERE book_id=$1 AND entry_date=$2 AND journal_kind='primary' AND lifecycle_state='active'`,
			bookID, entryDate).Scan(&chID, &kept, &oldSize)
		if err == nil {
			if kept != nil {
				// The user already reviewed+kept this day (§Q6) — never overwrite it. The caller
				// re-runs as a 'supplement' so a re-distill augments rather than destroys.
				writeError(w, http.StatusConflict, "DIARY_ENTRY_KEPT",
					"the day's entry was already kept; write a supplement instead")
				return
			}
			// REPLACE the draft body in place (§Q5). Quota is only enforced on GROWTH so a
			// re-distill of the user's own day is never blocked from shrinking/rewriting.
			if byteSize > oldSize {
				if ok := s.txQuotaOK(ctx, tx, w, owner, byteSize-oldSize); !ok {
					return
				}
			}
			if _, err := tx.Exec(ctx,
				`UPDATE chapters SET title=$2, original_language=$3, byte_size=$4, entry_zone=$5,
				        draft_revision_count=draft_revision_count+1, draft_updated_at=now(), updated_at=now()
				   WHERE id=$1`,
				chID, nullIfEmpty(title), lang, byteSize, zone); err != nil {
				writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to update entry")
				return
			}
			if _, err := tx.Exec(ctx,
				`UPDATE chapter_drafts SET body=$2, draft_updated_at=now(), draft_version=draft_version+1
				   WHERE chapter_id=$1`, chID, jsonBody); err != nil {
				writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to update draft")
				return
			}
			// chapter_raw_objects may not exist for an older row — upsert it.
			if _, err := tx.Exec(ctx,
				`INSERT INTO chapter_raw_objects(chapter_id, body_text) VALUES($1,$2)
				   ON CONFLICT (chapter_id) DO UPDATE SET body_text=EXCLUDED.body_text`,
				chID, body); err != nil {
				writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to update raw body")
				return
			}
			if _, err := tx.Exec(ctx,
				`INSERT INTO chapter_revisions(chapter_id, body, body_format, message, author_user_id)
				   VALUES($1,$2,'json',$3,$4)`,
				chID, jsonBody, "distiller re-run", owner); err != nil {
				writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to write revision")
				return
			}
			if err := tx.Commit(ctx); err != nil {
				writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to commit")
				return
			}
			_ = s.recalcQuota(ctx, owner)
			writeJSON(w, http.StatusOK, map[string]any{
				"chapter_id": chID.String(), "book_id": bookID.String(),
				"entry_date": in.EntryDate, "journal_kind": "primary",
				"created": false, "replaced": true,
			})
			return
		}
		if !errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to read existing entry")
			return
		}
		// No active primary yet → fall through to create.
	}

	// 4. CREATE a new chapter (primary-new or supplement).
	if ok := s.txQuotaOK(ctx, tx, w, owner, byteSize); !ok {
		return
	}
	var sortOrder int
	_ = tx.QueryRow(ctx, `SELECT COALESCE(MAX(sort_order),0)+1 FROM chapters WHERE book_id=$1`, bookID).Scan(&sortOrder)
	var chID uuid.UUID
	err = tx.QueryRow(ctx, `
INSERT INTO chapters(book_id,title,original_filename,original_language,content_type,byte_size,sort_order,storage_key,lifecycle_state,entry_date,journal_kind,entry_zone,draft_updated_at,updated_at)
VALUES($1,$2,$3,$4,'text/plain',$5,$6,$7,'active',$8,$9,$10,now(),now())
RETURNING id`,
		bookID, nullIfEmpty(title), "journal/"+in.EntryDate+".txt", lang, byteSize, sortOrder,
		"chapters/"+bookID.String()+"/"+uuid.New().String(), entryDate, kind, zone).Scan(&chID)
	if err != nil {
		// A concurrent primary create for the same day would violate uq_chapters_primary_entry_per_day
		// — but the advisory lock above serializes those, so a conflict here is a genuine (rare)
		// sort_order race across different days; the caller's re-run is idempotent.
		writeError(w, http.StatusConflict, "BOOK_CONFLICT", "failed to create entry (retryable)")
		return
	}
	if _, err := tx.Exec(ctx, `INSERT INTO chapter_raw_objects(chapter_id, body_text) VALUES($1,$2)`, chID, body); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to write raw body")
		return
	}
	if _, err := tx.Exec(ctx,
		`INSERT INTO chapter_drafts(chapter_id, body, draft_format, draft_updated_at, draft_version) VALUES($1,$2,'json',now(),1)`,
		chID, jsonBody); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to write draft")
		return
	}
	if _, err := tx.Exec(ctx,
		`INSERT INTO chapter_revisions(chapter_id, body, body_format, message, author_user_id) VALUES($1,$2,'json',$3,$4)`,
		chID, jsonBody, "distilled entry", owner); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to write revision")
		return
	}
	if _, err := tx.Exec(ctx, `UPDATE chapters SET draft_revision_count=1 WHERE id=$1`, chID); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to finalize entry")
		return
	}
	if err := tx.Commit(ctx); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to commit")
		return
	}
	_ = s.recalcQuota(ctx, owner)
	writeJSON(w, http.StatusCreated, map[string]any{
		"chapter_id": chID.String(), "book_id": bookID.String(),
		"entry_date": in.EntryDate, "journal_kind": kind,
		"created": true, "replaced": false,
	})
}

// keepDiaryEntry — B2 (spec 03/06 §Q6) — the user REVIEWS a draft diary entry and KEEPS it. Sets
// `diary_kept_at` (once, idempotent) on the entry. After this, a re-distill of the same day no
// longer clobbers the primary — the write seam 409s DIARY_ENTRY_KEPT and the caller supplements.
// Owner-only (the diary is never shared); diary-only (the `journal_kind IS NOT NULL` guard means a
// novel chapter can never be "kept" through here → 404).
func (s *Server) keepDiaryEntry(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}
	_, _, _, ok = s.authBook(w, r, bookID, GrantOwner)
	if !ok {
		return
	}
	ct, err := s.pool.Exec(r.Context(), `
UPDATE chapters SET diary_kept_at = COALESCE(diary_kept_at, now()), updated_at = now()
WHERE id=$1 AND book_id=$2 AND journal_kind IS NOT NULL AND lifecycle_state='active'`,
		chID, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to keep entry")
		return
	}
	if ct.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "DIARY_ENTRY_NOT_FOUND", "no active diary entry for that id")
		return
	}
	var keptAt time.Time
	_ = s.pool.QueryRow(r.Context(), `SELECT diary_kept_at FROM chapters WHERE id=$1`, chID).Scan(&keptAt)
	writeJSON(w, http.StatusOK, map[string]any{
		"chapter_id": chID.String(), "kept": true, "diary_kept_at": keptAt.Format(time.RFC3339),
	})
}

// diaryStats — D-R18 (human decision, amends D-R16) — the diary surfaces stats to the OWNER ONLY.
// This is an OWNER-SCOPED read over the diary's own chapters (entry count, words, day span), NOT the
// shared statistics-service aggregate — the diary write still emits no chapter.created (D-R16), so a
// private diary never enters any cross-user / trending surface. authBook(GrantOwner) is the leak
// guard: a non-owner (a diary can't be shared anyway) is refused, so no other user ever sees these.
func (s *Server) diaryStats(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	_, _, _, ok = s.authBook(w, r, bookID, GrantOwner)
	if !ok {
		return
	}
	// diary-only: journal_kind IS NOT NULL is what makes a chapter a diary entry (a novel chapter
	// has NULL) — so this never counts non-diary content even if pointed at another book kind.
	var entryCount, distinctDays int
	var totalWords int64
	var firstDate, lastDate *time.Time
	err := s.pool.QueryRow(r.Context(), `
SELECT count(*)                                            AS entry_count,
       count(DISTINCT entry_date)                         AS distinct_days,
       COALESCE(sum(word_count), 0)::bigint               AS total_words,
       min(entry_date)                                    AS first_date,
       max(entry_date)                                    AS last_date
FROM chapters
WHERE book_id=$1 AND journal_kind IS NOT NULL AND lifecycle_state='active'`,
		bookID).Scan(&entryCount, &distinctDays, &totalWords, &firstDate, &lastDate)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to read diary stats")
		return
	}
	out := map[string]any{
		"entry_count": entryCount, "distinct_days": distinctDays, "total_words": totalWords,
	}
	if firstDate != nil {
		out["first_entry_date"] = firstDate.Format("2006-01-02")
	}
	if lastDate != nil {
		out["last_entry_date"] = lastDate.Format("2006-01-02")
	}
	writeJSON(w, http.StatusOK, out)
}

// listDiaryEntries — WS-1.10 (spec 02/03) — the OWNER-ONLY list of the diary's entries for the
// assistant home timeline + the end-of-day review. Owner-scoped + diary-only (journal_kind IS NOT
// NULL) — the same leak posture as diaryStats: a diary is never shared and never enters a
// cross-user surface, so authBook(GrantOwner) is the guard. Newest-first, and it returns the entry
// BODY inline (from chapter_raw_objects) so the review renders + PROVES the entry_date in one call.
// `kept` reflects diary_kept_at (B2 review→keep). Bounded to the most recent 100 entries (a review
// only ever needs the latest few); if a diary ever grows past that, add keyset paging.
func (s *Server) listDiaryEntries(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	_, _, _, ok = s.authBook(w, r, bookID, GrantOwner)
	if !ok {
		return
	}
	rows, err := s.pool.Query(r.Context(), `
SELECT c.id, c.entry_date, COALESCE(c.entry_zone,'UTC'), COALESCE(c.title,''),
       COALESCE(c.word_count,0), c.journal_kind, c.diary_kept_at, c.draft_updated_at,
       COALESCE(ro.body_text,'')
FROM chapters c
LEFT JOIN chapter_raw_objects ro ON ro.chapter_id = c.id
WHERE c.book_id=$1 AND c.journal_kind IS NOT NULL AND c.lifecycle_state='active'
ORDER BY c.entry_date DESC, c.draft_updated_at DESC NULLS LAST
LIMIT 100`, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to list diary entries")
		return
	}
	defer rows.Close()
	entries := make([]map[string]any, 0, 16)
	for rows.Next() {
		var id uuid.UUID
		var entryDate time.Time
		var zone, title, journalKind, body string
		var wordCount int
		var keptAt, draftUpdated *time.Time
		// Scan EVERY column into a real target (never `_ = rows.Scan()` — a discarded scan
		// error zeroes the whole row; pgx-discarded-scan bug class).
		if err := rows.Scan(&id, &entryDate, &zone, &title, &wordCount, &journalKind,
			&keptAt, &draftUpdated, &body); err != nil {
			writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to read diary entry row")
			return
		}
		e := map[string]any{
			"chapter_id":   id.String(),
			"entry_date":   entryDate.Format("2006-01-02"),
			"entry_zone":   zone,
			"title":        title,
			"word_count":   wordCount,
			"journal_kind": journalKind,
			"kept":         keptAt != nil,
			"body":         body,
		}
		if keptAt != nil {
			e["diary_kept_at"] = keptAt.Format(time.RFC3339)
		}
		if draftUpdated != nil {
			e["draft_updated_at"] = draftUpdated.Format(time.RFC3339)
		}
		entries = append(entries, e)
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to iterate diary entries")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"entries": entries, "count": len(entries)})
}

// txQuotaOK checks the owner has room for `delta` more bytes, writing a 507 and returning false
// if not. Uses the tx so the read is consistent with the pending write.
func (s *Server) txQuotaOK(ctx context.Context, tx pgx.Tx, w http.ResponseWriter, owner uuid.UUID, delta int64) bool {
	var used, quota int64
	// ensureQuotaRow (called before the tx) guarantees the row exists, so a read error here is a
	// genuine DB fault — fail CLOSED (500) rather than let a zeroed used/quota skip the cap.
	if err := tx.QueryRow(ctx,
		`SELECT used_bytes, quota_bytes FROM user_storage_quota WHERE owner_user_id=$1`, owner).
		Scan(&used, &quota); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to read quota")
		return false
	}
	if quota > 0 && used+delta > quota {
		writeError(w, http.StatusInsufficientStorage, "STORAGE_QUOTA_EXCEEDED", "quota exceeded")
		return false
	}
	return true
}
