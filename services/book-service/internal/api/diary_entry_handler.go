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
	"regexp"
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
	Body        string `json:"body"`         // the distilled prose
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
	// 'weekly' (WS-3.7) is a get-or-REPLACE kind like primary (review M2): re-running a week's rollup
	// must REPLACE the prior weekly review for that week, not pile up duplicates on redelivery/double-fire.
	if kind != "primary" && kind != "supplement" && kind != "weekly" {
		writeError(w, http.StatusBadRequest, "BOOK_BAD_REQUEST", "journal_kind must be primary|supplement|weekly")
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

	// 3. PRIMARY / WEEKLY: get-or-create-then-replace (keyed by book+entry_date+kind, so a re-run
	//    REPLACES). Supplement always creates a new chapter. (M2 — 'weekly' is idempotent per week.)
	if kind == "primary" || kind == "weekly" {
		var chID uuid.UUID
		var kept *time.Time
		var oldSize int64
		err = tx.QueryRow(ctx,
			`SELECT id, diary_kept_at, byte_size FROM chapters
			   WHERE book_id=$1 AND entry_date=$2 AND journal_kind=$3 AND lifecycle_state='active'`,
			bookID, entryDate, kind).Scan(&chID, &kept, &oldSize)
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

// diaryDayKept — WS-3.3 review M1 — a CHEAP pre-LLM gate so the catch-up sweep doesn't re-run the
// distiller's map-reduce on a day whose primary entry is already KEPT (the write seam only discovers
// "kept" AFTER the LLM, so a daily catch-up burned redundant spend on each kept day). Internal-token;
// returns {kept} for (book, entry_date) — owner+diary scoped so it can't probe another user's diary.
func (s *Server) diaryDayKept(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	owner, err := uuid.Parse(strings.TrimSpace(r.URL.Query().Get("owner_user_id")))
	if err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_BAD_REQUEST", "owner_user_id required")
		return
	}
	entryDate, err := time.Parse("2006-01-02", strings.TrimSpace(r.URL.Query().Get("entry_date")))
	if err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_BAD_REQUEST", "entry_date must be YYYY-MM-DD")
		return
	}
	var kept *time.Time
	err = s.pool.QueryRow(r.Context(), `
SELECT c.diary_kept_at FROM chapters c JOIN books b ON b.id = c.book_id
WHERE c.book_id=$1 AND b.owner_user_id=$2 AND b.kind='diary'
  AND c.entry_date=$3 AND c.journal_kind='primary' AND c.lifecycle_state='active'`,
		bookID, owner, entryDate).Scan(&kept)
	if errors.Is(err, pgx.ErrNoRows) {
		writeJSON(w, http.StatusOK, map[string]any{"exists": false, "kept": false})
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to read entry")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"exists": true, "kept": kept != nil})
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
	_, owner, _, ok := s.authBook(w, r, bookID, GrantOwner)
	if !ok {
		return
	}
	ctx := r.Context()

	// The keep MUST take the SAME (owner, day) advisory lock the distiller's write seam
	// (`upsertDiaryEntry`) uses. Without it there is a TOCTOU: a concurrent re-distill acquires the
	// lock, reads `diary_kept_at`=NULL, and REPLACEs the body — while a keep commits in the gap between
	// that read and the REPLACE — clobbering an entry the user just kept (multi-device: device A keeps
	// while device B clicks "End my day"). Serializing keep vs re-distill on the lock closes it: once
	// the keep holds the lock and sets `diary_kept_at`, the next re-distill sees it and 409s instead of
	// overwriting. (audit MED — "a KEPT entry must NOT be clobbered".)
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to keep entry")
		return
	}
	defer tx.Rollback(ctx)

	// The entry's day is needed to compute the lock key; the read also validates it's an active diary
	// entry of THIS book (→ 404 otherwise). entry_date is immutable per entry, so reading it before the
	// lock is safe; the UPDATE below re-checks the row under the lock.
	var entryDate time.Time
	err = tx.QueryRow(ctx, `
SELECT entry_date FROM chapters
WHERE id=$1 AND book_id=$2 AND journal_kind IS NOT NULL AND lifecycle_state='active'`,
		chID, bookID).Scan(&entryDate)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "DIARY_ENTRY_NOT_FOUND", "no active diary entry for that id")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to read entry")
		return
	}

	// Same lock key + acquisition as upsertDiaryEntry (owner|YYYY-MM-DD). Same lock-order (lock →
	// write) as the upsert, so no deadlock.
	lockKey := owner.String() + "|" + entryDate.Format("2006-01-02")
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock(hashtext($1))`, lockKey); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to acquire day lock")
		return
	}

	ct, err := tx.Exec(ctx, `
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
	if err := tx.QueryRow(ctx, `SELECT diary_kept_at FROM chapters WHERE id=$1`, chID).Scan(&keptAt); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to read kept time")
		return
	}
	if err := tx.Commit(ctx); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to keep entry")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"chapter_id": chID.String(), "kept": true, "diary_kept_at": keptAt.Format(time.RFC3339),
	})
}

// amendDiaryEntry — WS-2.6a / D17 leg 1 (the missing leg). The user CORRECTS a kept diary entry
// ("Alice said that, not Minh"). This is the piece D17 says nobody built: `memory_forget` invalidates
// one Neo4j fact but never touches the PG SSOT, so the diary text stays wrong and a KG rebuild
// resurrects the fact. An amendment writes a NEW chapter revision with the corrected body and — unlike
// the distiller write-seam (`upsertDiaryEntry`, which 409s a kept entry) — PRESERVES `diary_kept_at`
// (a correction is an explicit human edit, not a re-distill clobber). Owner-only, diary-only. Takes the
// same (owner, day) advisory lock as keep/upsert so a concurrent re-distill can't interleave. Legs 2+3
// (re-distill the corrected entry → reconcile the graph, D-R30) are driven by the correction flow; this
// endpoint is leg 1 and returns the correction's `entry_date` so the caller can re-distill that day.
func (s *Server) amendDiaryEntry(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}
	_, owner, _, ok := s.authBook(w, r, bookID, GrantOwner)
	if !ok {
		return
	}
	var in struct {
		Body  string `json:"body"`
		Title string `json:"title"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_BAD_REQUEST", "invalid body")
		return
	}
	body := strings.TrimSpace(in.Body)
	if body == "" {
		writeError(w, http.StatusBadRequest, "BOOK_BAD_REQUEST", "body required (a correction must have text)")
		return
	}
	title := strings.TrimSpace(in.Title)
	jsonBody := plainTextToTiptapJSON(body)
	byteSize := int64(len(body))
	ctx := r.Context()

	if err := s.ensureQuotaRow(ctx, owner); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to initialize quota")
		return
	}

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to amend entry")
		return
	}
	defer tx.Rollback(ctx)

	// Read the entry's day (validates it's an active diary entry of THIS book → 404 otherwise) BEFORE
	// the lock; entry_date is immutable per entry. Same lock key + lock-order (lock → write) as
	// keep/upsert, so amend serializes against a concurrent re-distill instead of interleaving.
	var entryDate time.Time
	var keptAt *time.Time
	err = tx.QueryRow(ctx, `
SELECT entry_date, diary_kept_at FROM chapters
WHERE id=$1 AND book_id=$2 AND journal_kind IS NOT NULL AND lifecycle_state='active'`,
		chID, bookID).Scan(&entryDate, &keptAt)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "DIARY_ENTRY_NOT_FOUND", "no active diary entry for that id")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to read entry")
		return
	}
	lockKey := owner.String() + "|" + entryDate.Format("2006-01-02")
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock(hashtext($1))`, lockKey); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to acquire day lock")
		return
	}

	// Quota is enforced only on GROWTH (a correction may shrink or rewrite; never block that).
	var oldSize int64
	_ = tx.QueryRow(ctx, `SELECT byte_size FROM chapters WHERE id=$1`, chID).Scan(&oldSize)
	if byteSize > oldSize {
		if ok := s.txQuotaOK(ctx, tx, w, owner, byteSize-oldSize); !ok {
			return
		}
	}

	// Write the corrected body as a NEW revision. `diary_kept_at` is DELIBERATELY untouched — a
	// correction to a kept entry keeps it kept (the write-seam refuses a kept entry; amend is the
	// sanctioned edit path). draft_revision_count/version bump so the audit trail shows the correction.
	if _, err := tx.Exec(ctx,
		`UPDATE chapters SET title=COALESCE(NULLIF($2,''), title), byte_size=$3,
		        draft_revision_count=draft_revision_count+1, draft_updated_at=now(), updated_at=now()
		   WHERE id=$1`, chID, title, byteSize); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to update entry")
		return
	}
	if _, err := tx.Exec(ctx,
		`UPDATE chapter_drafts SET body=$2, draft_updated_at=now(), draft_version=draft_version+1
		   WHERE chapter_id=$1`, chID, jsonBody); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to update draft")
		return
	}
	if _, err := tx.Exec(ctx,
		`INSERT INTO chapter_raw_objects(chapter_id, body_text) VALUES($1,$2)
		   ON CONFLICT (chapter_id) DO UPDATE SET body_text=EXCLUDED.body_text`,
		chID, body); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to update raw body")
		return
	}
	if _, err := tx.Exec(ctx,
		`INSERT INTO chapter_revisions(chapter_id, body, body_format, message, author_user_id)
		   VALUES($1,$2,'json',$3,$4)`, chID, jsonBody, "user amendment (D17)", owner); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to write revision")
		return
	}
	if err := tx.Commit(ctx); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to commit amendment")
		return
	}
	_ = s.recalcQuota(ctx, owner)
	writeJSON(w, http.StatusOK, map[string]any{
		"chapter_id":     chID.String(),
		"book_id":        bookID.String(),
		"entry_date":     entryDate.Format("2006-01-02"),
		"amended":        true,
		"kept_preserved": keptAt != nil,
	})
}

// redactDiaryName — WS-2.6c (D17 forget-a-person, source-text leg). Redacts a person's NAME from the
// user's diary entry bodies so a re-index can't resurface it (the knowledge leg deleted the structured
// :Entity/:Facts; this deletes the name from the SOURCE prose). Owner-only, diary-only. For every active
// diary entry whose body mentions the name (whole-word, case-insensitive), replace it with the redaction
// placeholder and write a NEW revision (audit trail), preserving diary_kept_at (like amend — a redaction
// is a sanctioned edit, not a re-distill clobber). Idempotent: a second run finds no occurrences → 0.
//
// LIMITATION (noted): whole-word matching uses a regex word boundary, which covers Latin/Vietnamese names
// (the dominant diary case). A CJK name (no word boundary) falls back to substring replacement. Passages
// already in the KG are refreshed on the next re-index of the redacted entry; this leg fixes the SOURCE.
const diaryRedactionPlaceholder = "[removed]"

func (s *Server) redactDiaryName(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	_, owner, _, ok := s.authBook(w, r, bookID, GrantOwner)
	if !ok {
		return
	}
	var in struct {
		Name string `json:"name"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_BAD_REQUEST", "invalid body")
		return
	}
	name := strings.TrimSpace(in.Name)
	if name == "" {
		writeError(w, http.StatusBadRequest, "BOOK_BAD_REQUEST", "name required")
		return
	}
	// Whole-word, case-insensitive matcher for Latin/VI names; if the name has no word-boundary-able
	// edge (e.g. a CJK name), \b won't fire — fall back to a plain case-insensitive substring matcher so
	// the redaction still removes it. QuoteMeta neutralizes any regex metacharacters in the name.
	quoted := regexp.QuoteMeta(name)
	re := regexp.MustCompile(`(?i)\b` + quoted + `\b`)
	if !hasWordBoundaryEdge(name) {
		re = regexp.MustCompile(`(?i)` + quoted)
	}

	ctx := r.Context()
	rows, err := s.pool.Query(ctx, `
SELECT c.id, COALESCE(ro.body_text,'')
FROM chapters c LEFT JOIN chapter_raw_objects ro ON ro.chapter_id = c.id
WHERE c.book_id=$1 AND c.journal_kind IS NOT NULL AND c.lifecycle_state='active'`, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to scan diary")
		return
	}
	type target struct {
		id      uuid.UUID
		newBody string
	}
	var targets []target
	for rows.Next() {
		var id uuid.UUID
		var body string
		if err := rows.Scan(&id, &body); err != nil {
			rows.Close()
			writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to read diary row")
			return
		}
		if re.MatchString(body) {
			targets = append(targets, target{id: id, newBody: re.ReplaceAllString(body, diaryRedactionPlaceholder)})
		}
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to iterate diary")
		return
	}

	if len(targets) == 0 {
		writeJSON(w, http.StatusOK, map[string]any{"redacted_entries": 0, "name": name})
		return
	}

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to begin")
		return
	}
	defer tx.Rollback(ctx)
	for _, t := range targets {
		jsonBody := plainTextToTiptapJSON(t.newBody)
		byteSize := int64(len(t.newBody))
		// Redaction only SHRINKS or rewrites — never a growth path, so no quota check is needed.
		if _, err := tx.Exec(ctx,
			`UPDATE chapters SET byte_size=$2, draft_revision_count=draft_revision_count+1,
			        draft_updated_at=now(), updated_at=now() WHERE id=$1`, t.id, byteSize); err != nil {
			writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to update entry")
			return
		}
		if _, err := tx.Exec(ctx,
			`UPDATE chapter_drafts SET body=$2, draft_updated_at=now(), draft_version=draft_version+1
			   WHERE chapter_id=$1`, t.id, jsonBody); err != nil {
			writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to update draft")
			return
		}
		if _, err := tx.Exec(ctx,
			`INSERT INTO chapter_raw_objects(chapter_id, body_text) VALUES($1,$2)
			   ON CONFLICT (chapter_id) DO UPDATE SET body_text=EXCLUDED.body_text`,
			t.id, t.newBody); err != nil {
			writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to update raw body")
			return
		}
		if _, err := tx.Exec(ctx,
			`INSERT INTO chapter_revisions(chapter_id, body, body_format, message, author_user_id)
			   VALUES($1,$2,'json',$3,$4)`, t.id, jsonBody, "forget-person redaction (D17)", owner); err != nil {
			writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to write revision")
			return
		}
	}
	if err := tx.Commit(ctx); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to commit redaction")
		return
	}
	_ = s.recalcQuota(ctx, owner)
	writeJSON(w, http.StatusOK, map[string]any{"redacted_entries": len(targets), "name": name})
}

// hasWordBoundaryEdge reports whether the name starts AND ends with a character that participates in a
// regex `\b` boundary (a word char: letter/digit/underscore). A CJK name is word-char per Go's regexp
// (\w is ASCII-only by default), so `\b` around it won't match reliably — the caller falls back to a
// plain substring match for such names.
func hasWordBoundaryEdge(name string) bool {
	isWord := func(b byte) bool {
		return b == '_' || (b >= '0' && b <= '9') || (b >= 'a' && b <= 'z') || (b >= 'A' && b <= 'Z')
	}
	return len(name) > 0 && isWord(name[0]) && isWord(name[len(name)-1])
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

// getInternalDiaryBook — D-R27 (erase review MED-1) — resolve a user's diary book_id for ANY
// lifecycle (active / trashed / purge_pending) WITHOUT creating one. The erase orchestrator needs
// this: the get-or-create diary endpoint 409s on a TRASHED diary, which made erasing a trashed diary
// a silent no-op (the derived data survived). This read never creates, so it also fixes the
// "erase spuriously creates then deletes an empty diary" smell. Internal-token; owner-scoped by
// ?user_id; 404 when the user has no diary at all.
func (s *Server) getInternalDiaryBook(w http.ResponseWriter, r *http.Request) {
	owner, err := uuid.Parse(strings.TrimSpace(r.URL.Query().Get("user_id")))
	if err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_BAD_REQUEST", "user_id required")
		return
	}
	var bookID uuid.UUID
	var lifecycle string
	// Prefer the ACTIVE diary; fall back to a trashed/purge_pending one so erasure still reaches it.
	err = s.pool.QueryRow(r.Context(), `
SELECT id, lifecycle_state FROM books
WHERE owner_user_id=$1 AND kind='diary'
ORDER BY (lifecycle_state='active') DESC, created_at DESC
LIMIT 1`, owner).Scan(&bookID, &lifecycle)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "no diary for user")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to resolve diary")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"book_id": bookID.String(), "lifecycle": lifecycle})
}

// eraseDiaryBook — D-R27 (human-authorized 2026-07-12) — the IMMEDIATE ROW-DELETE erasure of a
// user's diary. HARD-deletes the diary `books` row, which ON DELETE CASCADE removes ALL its content:
// chapters → chapter_drafts / chapter_revisions / chapter_raw_objects / chapter_blocks / scenes, plus
// book_collaborators / book_cover_assets / etc. After this the diary content is genuinely ROW-GONE
// (not soft-trashed), and a re-provision mints a FRESH empty diary — nothing to resurrect from the
// book side. Internal-token + owner-scoped by ?user_id; `kind='diary'` guard so this route can NEVER
// hard-delete a novel or another user's book (a non-diary/foreign id → 0 rows → erased:false).
// (Backup-resistant crypto-shred stays P-12 — this is the immediate-absence half only.)
func (s *Server) eraseDiaryBook(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	owner, err := uuid.Parse(strings.TrimSpace(r.URL.Query().Get("user_id")))
	if err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_BAD_REQUEST", "user_id required")
		return
	}
	// Owner + diary guarded IN the DELETE predicate: a foreign or non-diary book matches 0 rows and
	// is left untouched (never a cross-tenant or novel delete). Idempotent — re-erase → erased:false.
	ct, err := s.pool.Exec(r.Context(),
		`DELETE FROM books WHERE id=$1 AND owner_user_id=$2 AND kind='diary'`, bookID, owner)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to erase diary")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"book_id": bookID.String(), "erased": ct.RowsAffected() > 0, "deleted_books": ct.RowsAffected(),
	})
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
