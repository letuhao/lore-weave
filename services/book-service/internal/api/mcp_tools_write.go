package api

// S-BOOK Tier-A (auto-write + Undo) MCP tool handlers. Each resolves identity
// from the envelope (SEC-1), verifies the grant (Edit for content writes,
// owner-implicit for book_create), performs the write reusing book-service's
// own DB logic, and returns a result whose _meta.undo_hint = {tool, args} names
// the verified reverse op (C-ACTIVITY). The consumer renders an Undo affordance
// from that hint; clicking it calls the named reverse tool.

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// undoResult builds a Tier-A CallToolResult carrying the C-ACTIVITY undo_hint in
// _meta. tool is the reverse tool name; args is its argument template. The
// structured Out is returned separately by the handler (the SDK fills
// StructuredContent and leaves this _meta intact).
func undoResult(tool string, args map[string]any) *mcp.CallToolResult {
	return &mcp.CallToolResult{
		Meta: mcp.Meta{
			"undo_hint": map[string]any{"tool": tool, "args": args},
		},
	}
}

// maxBooksPerUser caps the number of ACTIVE (non-bible) books a single user may
// own at once, across BOTH creation surfaces (the MCP book_create tool and the
// HTTP createBook). Without it an agent (or a script) could loop book_create and
// make unbounded empty books — the gap closed by D-MCP-BOOK-CREATE-QUOTA. It is a
// package var (not a const) so DB-gated tests can lower it to seed at the cap
// cheaply. 200 is a generous but real ceiling for a human library.
var maxBooksPerUser = 200

// countActiveBooks returns how many active, non-bible books owner_user_id owns —
// the same predicate listBooks/book_list use to define "my library". This is the
// per-user ceiling input shared by both creation surfaces (book_create + HTTP).
func (s *Server) countActiveBooks(ctx context.Context, ownerID uuid.UUID) (int, error) {
	var n int
	err := s.pool.QueryRow(ctx,
		// Exclude BOTH the hidden system rows the library also hides: is_bible AND kind='diary'
		// (WS-1.4). The diary is a system-provisioned private workspace that never appears in
		// listBooks; counting it would silently steal a novel slot from the user's ceiling —
		// they'd hit BOOK_LIMIT_REACHED one novel early after provisioning an assistant.
		`SELECT COUNT(*) FROM books WHERE owner_user_id=$1 AND is_bible=false AND kind<>'diary' AND lifecycle_state='active'`,
		ownerID).Scan(&n)
	return n, err
}

// errBookLimitReached is the MCP-surface refusal when a caller is at/over the
// per-user active-book ceiling. It is informative (not the uniform
// not-accessible error) because this is a quota condition, not an ownership one.
// Built per-call so it reflects the current maxBooksPerUser (tests lower it).
func errBookLimitReached() error {
	return fmt.Errorf("book limit reached (%d) — delete or purge a book first", maxBooksPerUser)
}

// ── book_create ──────────────────────────────────────────────────────────────

type bookCreateIn struct {
	Title            string   `json:"title" jsonschema:"the book title (required)"`
	Description      string   `json:"description,omitempty"`
	OriginalLanguage string   `json:"original_language,omitempty" jsonschema:"ISO language code of the source text"`
	Summary          string   `json:"summary,omitempty"`
	GenreTags        []string `json:"genre_tags,omitempty"`
}
type bookCreateOut struct {
	BookID string `json:"book_id"`
}

func (s *Server) toolBookCreate(ctx context.Context, _ *mcp.CallToolRequest, in bookCreateIn) (*mcp.CallToolResult, bookCreateOut, error) {
	userID, ok := mcpUserID(ctx)
	if !ok {
		return nil, bookCreateOut{}, errMissingIdentity
	}
	title := strings.TrimSpace(in.Title)
	if title == "" {
		return nil, bookCreateOut{}, errors.New("title is required")
	}
	if in.GenreTags == nil {
		in.GenreTags = []string{}
	}
	if err := s.ensureQuotaRow(ctx, userID); err != nil {
		return nil, bookCreateOut{}, errors.New("failed to initialize quota")
	}
	// Per-user active-book ceiling (parity with HTTP createBook) — refuse before
	// inserting so an agent can't loop book_create into unbounded empty books.
	n, err := s.countActiveBooks(ctx, userID)
	if err != nil {
		return nil, bookCreateOut{}, errors.New("failed to check book quota")
	}
	if n >= maxBooksPerUser {
		return nil, bookCreateOut{}, errBookLimitReached()
	}
	var bookID uuid.UUID
	if err := s.pool.QueryRow(ctx, `
-- WS-1.1: kind EXPLICIT (see server.go createBook). An agent-created book is a novel;
-- only the diary provisioner may write kind='diary'.
INSERT INTO books(owner_user_id,title,description,original_language,summary,genre_tags,kind)
VALUES($1,$2,$3,$4,$5,$6,'novel') RETURNING id`,
		userID, title, in.Description, in.OriginalLanguage, in.Summary, in.GenreTags).Scan(&bookID); err != nil {
		return nil, bookCreateOut{}, errors.New("failed to create book")
	}
	// Reverse op: trash the book (book_delete proposes a confirm; but the natural
	// Undo of a fresh create is the reversible trash → restore. We name book_delete
	// as the reverse; the consumer's Undo issues it as a confirmable delete).
	res := undoResult("book_delete", map[string]any{"book_id": bookID.String()})
	return res, bookCreateOut{BookID: bookID.String()}, nil
}

// ── book_update_meta ─────────────────────────────────────────────────────────

type bookUpdateMetaIn struct {
	BookID           string    `json:"book_id" jsonschema:"the book to update (UUID)"`
	Title            *string   `json:"title,omitempty"`
	Description      *string   `json:"description,omitempty"`
	OriginalLanguage *string   `json:"original_language,omitempty"`
	Summary          *string   `json:"summary,omitempty"`
	GenreTags        *[]string `json:"genre_tags,omitempty"`
}
type bookUpdateMetaOut struct {
	BookID  string   `json:"book_id"`
	Updated []string `json:"updated_fields"`
}

func (s *Server) toolBookUpdateMeta(ctx context.Context, _ *mcp.CallToolRequest, in bookUpdateMetaIn) (*mcp.CallToolResult, bookUpdateMetaOut, error) {
	userID, ok := mcpUserID(ctx)
	if !ok {
		return nil, bookUpdateMetaOut{}, errMissingIdentity
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, bookUpdateMetaOut{}, errors.New("book_id must be a UUID")
	}
	if _, err := s.mcpRequireGrant(ctx, bookID, userID, GrantEdit); err != nil {
		return nil, bookUpdateMetaOut{}, mcpOwnershipError(err)
	}
	// Capture prior values for the undo_hint (verified reverse = same tool, prior
	// values). Only fields the caller is changing are snapshotted.
	var lifecycle string
	prior := map[string]any{}
	var pTitle, pDesc, pLang, pSummary *string
	var pTags []string
	if err := s.pool.QueryRow(ctx, `SELECT lifecycle_state,title,description,original_language,summary,genre_tags FROM books WHERE id=$1`, bookID).
		Scan(&lifecycle, &pTitle, &pDesc, &pLang, &pSummary, &pTags); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, bookUpdateMetaOut{}, errBookNotAccessible
		}
		return nil, bookUpdateMetaOut{}, errors.New("failed to load book")
	}
	if lifecycle != "active" {
		return nil, bookUpdateMetaOut{}, errors.New("book is not in an editable state")
	}

	set := []string{"updated_at=now()"}
	args := []any{bookID}
	idx := 2
	updated := []string{}
	if in.Title != nil {
		set = append(set, fmt.Sprintf("title=$%d", idx))
		args = append(args, *in.Title)
		idx++
		updated = append(updated, "title")
		prior["title"] = derefStr(pTitle)
	}
	if in.Description != nil {
		set = append(set, fmt.Sprintf("description=$%d", idx))
		args = append(args, *in.Description)
		idx++
		updated = append(updated, "description")
		prior["description"] = derefStr(pDesc)
	}
	if in.OriginalLanguage != nil {
		set = append(set, fmt.Sprintf("original_language=$%d", idx))
		args = append(args, *in.OriginalLanguage)
		idx++
		updated = append(updated, "original_language")
		prior["original_language"] = derefStr(pLang)
	}
	if in.Summary != nil {
		set = append(set, fmt.Sprintf("summary=$%d", idx))
		args = append(args, *in.Summary)
		idx++
		updated = append(updated, "summary")
		prior["summary"] = derefStr(pSummary)
	}
	if in.GenreTags != nil {
		set = append(set, fmt.Sprintf("genre_tags=$%d", idx))
		args = append(args, *in.GenreTags)
		idx++
		updated = append(updated, "genre_tags")
		if pTags == nil {
			pTags = []string{}
		}
		prior["genre_tags"] = pTags
	}
	if len(updated) == 0 {
		return nil, bookUpdateMetaOut{}, errors.New("no fields to update")
	}
	if _, err := s.pool.Exec(ctx, fmt.Sprintf("UPDATE books SET %s WHERE id=$1", strings.Join(set, ", ")), args...); err != nil {
		return nil, bookUpdateMetaOut{}, errors.New("failed to update book")
	}
	prior["book_id"] = bookID.String()
	res := undoResult("book_update_meta", prior)
	return res, bookUpdateMetaOut{BookID: bookID.String(), Updated: updated}, nil
}

func derefStr(p *string) any {
	if p == nil {
		return ""
	}
	return *p
}

// ── book_chapter_create ──────────────────────────────────────────────────────

type chapterCreateIn struct {
	BookID           string `json:"book_id" jsonschema:"the book to add the chapter to (UUID)"`
	Title            string `json:"title,omitempty"`
	OriginalLanguage string `json:"original_language" jsonschema:"ISO language code of the chapter text (required)"`
	SortOrder        int    `json:"sort_order,omitempty" jsonschema:"position; 0 = append at the end"`
	Body             string `json:"body,omitempty" jsonschema:"plain-text body (optional)"`
}
type chapterCreateOut struct {
	ChapterID string `json:"chapter_id"`
}

func (s *Server) toolChapterCreate(ctx context.Context, _ *mcp.CallToolRequest, in chapterCreateIn) (*mcp.CallToolResult, chapterCreateOut, error) {
	userID, ok := mcpUserID(ctx)
	if !ok {
		return nil, chapterCreateOut{}, errMissingIdentity
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, chapterCreateOut{}, errors.New("book_id must be a UUID")
	}
	if strings.TrimSpace(in.OriginalLanguage) == "" {
		return nil, chapterCreateOut{}, errors.New("original_language is required")
	}
	owner, err := s.mcpRequireGrant(ctx, bookID, userID, GrantEdit)
	if err != nil {
		return nil, chapterCreateOut{}, mcpOwnershipError(err)
	}
	// Lifecycle gate (parity with createChapter): only an active book accepts new chapters.
	var lifecycle string
	if err := s.pool.QueryRow(ctx, `SELECT lifecycle_state FROM books WHERE id=$1`, bookID).Scan(&lifecycle); err != nil {
		return nil, chapterCreateOut{}, errBookNotAccessible
	}
	if lifecycle != "active" {
		return nil, chapterCreateOut{}, errors.New("book is not in an editable state")
	}
	chID, err := s.mcpCreateChapter(ctx, userID, owner, bookID, strings.TrimSpace(in.Title), in.OriginalLanguage, in.SortOrder, in.Body)
	if err != nil {
		return nil, chapterCreateOut{}, err
	}
	res := undoResult("book_chapter_delete", map[string]any{"book_id": bookID.String(), "chapter_id": chID.String()})
	return res, chapterCreateOut{ChapterID: chID.String()}, nil
}

// mcpCreateChapter inserts one chapter (+ draft + seed revision) in a tx, billing
// the owner's quota. Mirrors createChapterRecord's writes without the HTTP shell.
func (s *Server) mcpCreateChapter(ctx context.Context, caller, owner, bookID uuid.UUID, title, lang string, sortOrder int, body string) (uuid.UUID, error) {
	if sortOrder == 0 {
		_ = s.pool.QueryRow(ctx, `SELECT COALESCE(MAX(sort_order),0)+1 FROM chapters WHERE book_id=$1`, bookID).Scan(&sortOrder)
	}
	_ = s.ensureQuotaRow(ctx, owner)
	_ = s.recalcQuota(ctx, owner)
	var used, quota int64
	_ = s.pool.QueryRow(ctx, `SELECT used_bytes, quota_bytes FROM user_storage_quota WHERE owner_user_id=$1`, owner).Scan(&used, &quota)
	if used+int64(len(body)) > quota {
		return uuid.Nil, errors.New("storage quota exceeded")
	}
	jsonBody := plainTextToTiptapJSON(body)
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return uuid.Nil, errors.New("failed to create chapter")
	}
	defer tx.Rollback(ctx)
	var chapterID uuid.UUID
	if err := tx.QueryRow(ctx, `
INSERT INTO chapters(book_id,title,original_filename,original_language,content_type,byte_size,sort_order,storage_key,lifecycle_state,draft_updated_at,updated_at)
VALUES($1,$2,$3,$4,'text/plain',$5,$6,$7,'active',now(),now()) RETURNING id`,
		bookID, nullIfEmpty(title), fmt.Sprintf("editor-%s.txt", uuid.NewString()), lang, int64(len(body)), sortOrder,
		fmt.Sprintf("chapters/%s/%s", bookID, uuid.New())).Scan(&chapterID); err != nil {
		return uuid.Nil, errors.New("failed to create chapter (duplicate sort/language?)")
	}
	_, _ = tx.Exec(ctx, `INSERT INTO chapter_raw_objects(chapter_id, body_text) VALUES($1,$2)`, chapterID, body)
	_, _ = tx.Exec(ctx, `INSERT INTO chapter_drafts(chapter_id, body, draft_format, draft_updated_at, draft_version) VALUES($1,$2,'json',now(),1)`, chapterID, jsonBody)
	_, _ = tx.Exec(ctx, `INSERT INTO chapter_revisions(chapter_id, body, body_format, message, author_user_id) VALUES($1,$2,'json','seed from assistant',$3)`, chapterID, jsonBody, caller)
	_, _ = tx.Exec(ctx, `UPDATE chapters SET draft_revision_count=1 WHERE id=$1`, chapterID)
	if err := insertOutboxEvent(ctx, tx, "chapter.created", chapterID, map[string]any{"book_id": bookID}); err != nil {
		return uuid.Nil, errors.New("failed to commit chapter")
	}
	if err := tx.Commit(ctx); err != nil {
		return uuid.Nil, errors.New("failed to commit chapter")
	}
	_ = s.recalcQuota(ctx, owner)
	return chapterID, nil
}

// ── book_chapter_bulk_create ─────────────────────────────────────────────────

type chapterBulkItem struct {
	OriginalFilename string `json:"original_filename,omitempty"`
	Title            string `json:"title,omitempty"`
	Content          string `json:"content" jsonschema:"plain-text chapter content"`
}
type chapterBulkCreateIn struct {
	BookID           string            `json:"book_id" jsonschema:"the book to add chapters to (UUID)"`
	OriginalLanguage string            `json:"original_language,omitempty" jsonschema:"ISO language code (default auto)"`
	Chapters         []chapterBulkItem `json:"chapters" jsonschema:"the chapters to create"`
}
type chapterBulkCreateOut struct {
	Created    int      `json:"created"`
	Skipped    int      `json:"skipped"`
	ChapterIDs []string `json:"chapter_ids"`
}

func (s *Server) toolChapterBulkCreate(ctx context.Context, _ *mcp.CallToolRequest, in chapterBulkCreateIn) (*mcp.CallToolResult, chapterBulkCreateOut, error) {
	userID, ok := mcpUserID(ctx)
	if !ok {
		return nil, chapterBulkCreateOut{}, errMissingIdentity
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, chapterBulkCreateOut{}, errors.New("book_id must be a UUID")
	}
	if len(in.Chapters) == 0 {
		return nil, chapterBulkCreateOut{}, errors.New("chapters must not be empty")
	}
	if len(in.Chapters) > maxBulkChapters {
		return nil, chapterBulkCreateOut{}, fmt.Errorf("at most %d chapters per request", maxBulkChapters)
	}
	owner, err := s.mcpRequireGrant(ctx, bookID, userID, GrantEdit)
	if err != nil {
		return nil, chapterBulkCreateOut{}, mcpOwnershipError(err)
	}
	var lifecycle string
	if err := s.pool.QueryRow(ctx, `SELECT lifecycle_state FROM books WHERE id=$1`, bookID).Scan(&lifecycle); err != nil {
		return nil, chapterBulkCreateOut{}, errBookNotAccessible
	}
	if lifecycle != "active" {
		return nil, chapterBulkCreateOut{}, errors.New("book is not in an editable state")
	}
	lang := strings.TrimSpace(in.OriginalLanguage)
	if lang == "" {
		lang = "auto"
	}

	var batchBytes int64
	for _, it := range in.Chapters {
		batchBytes += int64(len(it.Content))
	}
	_ = s.ensureQuotaRow(ctx, owner)
	_ = s.recalcQuota(ctx, owner)
	var used, quota int64
	_ = s.pool.QueryRow(ctx, `SELECT used_bytes, quota_bytes FROM user_storage_quota WHERE owner_user_id=$1`, owner).Scan(&used, &quota)
	if used+batchBytes > quota {
		return nil, chapterBulkCreateOut{}, errors.New("storage quota exceeded")
	}

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, chapterBulkCreateOut{}, errors.New("db begin failed")
	}
	defer tx.Rollback(ctx)
	var maxSort int
	_ = tx.QueryRow(ctx, `SELECT COALESCE(MAX(sort_order),0) FROM chapters WHERE book_id=$1 AND lifecycle_state='active'`, bookID).Scan(&maxSort)
	sortOrder := maxSort + 1
	existing := map[string]struct{}{}
	if rows, qerr := tx.Query(ctx, `SELECT original_filename FROM chapters WHERE book_id=$1 AND lifecycle_state='active'`, bookID); qerr == nil {
		for rows.Next() {
			var fn string
			if rows.Scan(&fn) == nil {
				existing[fn] = struct{}{}
			}
		}
		rows.Close()
	}
	out := chapterBulkCreateOut{ChapterIDs: []string{}}
	for _, it := range in.Chapters {
		title := strings.TrimSpace(it.Title)
		if title == "" {
			title = extractChapterTitle(it.Content)
		}
		filename := strings.TrimSpace(it.OriginalFilename)
		if filename == "" {
			filename = fmt.Sprintf("chapter-%04d.txt", sortOrder)
		}
		if _, dup := existing[filename]; dup {
			out.Skipped++
			continue
		}
		existing[filename] = struct{}{}
		jsonBody := plainTextToTiptapJSON(it.Content)
		var chID uuid.UUID
		if err := tx.QueryRow(ctx, `
INSERT INTO chapters(book_id,title,original_filename,original_language,content_type,byte_size,sort_order,storage_key,lifecycle_state,draft_updated_at,updated_at)
VALUES($1,$2,$3,$4,'text/plain',$5,$6,$7,'active',now(),now()) RETURNING id`,
			bookID, nullIfEmpty(title), filename, lang, int64(len(it.Content)), sortOrder,
			fmt.Sprintf("chapters/%s/%s", bookID, uuid.New())).Scan(&chID); err != nil {
			return nil, chapterBulkCreateOut{}, errors.New("failed to create chapter")
		}
		_, _ = tx.Exec(ctx, `INSERT INTO chapter_raw_objects(chapter_id, body_text) VALUES($1,$2)`, chID, it.Content)
		_, _ = tx.Exec(ctx, `INSERT INTO chapter_drafts(chapter_id, body, draft_format, draft_updated_at, draft_version) VALUES($1,$2,'json',now(),1)`, chID, jsonBody)
		_, _ = tx.Exec(ctx, `INSERT INTO chapter_revisions(chapter_id, body, body_format, message, author_user_id) VALUES($1,$2,'json','bulk seed from assistant',$3)`, chID, jsonBody, userID)
		_, _ = tx.Exec(ctx, `UPDATE chapters SET draft_revision_count=1 WHERE id=$1`, chID)
		if err := insertOutboxEvent(ctx, tx, "chapter.created", chID, map[string]any{"book_id": bookID}); err != nil {
			return nil, chapterBulkCreateOut{}, errors.New("failed to commit chapters")
		}
		out.ChapterIDs = append(out.ChapterIDs, chID.String())
		out.Created++
		sortOrder++
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, chapterBulkCreateOut{}, errors.New("failed to commit chapters")
	}
	_ = s.recalcQuota(ctx, owner)
	// Undo of a bulk create = trash each created chapter. The hint names the
	// per-chapter reverse tool + the id list the consumer iterates. out.ChapterIDs
	// are already string-rendered ids (the MCP output struct uses string UUIDs).
	ids := append([]string(nil), out.ChapterIDs...)
	res := undoResult("book_chapter_delete", map[string]any{"book_id": bookID.String(), "chapter_ids": ids})
	return res, out, nil
}

// ── book_chapter_update_meta ─────────────────────────────────────────────────

type chapterUpdateMetaIn struct {
	BookID           string  `json:"book_id" jsonschema:"the book the chapter belongs to (UUID)"`
	ChapterID        string  `json:"chapter_id" jsonschema:"the chapter to update (UUID)"`
	Title            *string `json:"title,omitempty"`
	SortOrder        *int    `json:"sort_order,omitempty"`
	OriginalLanguage *string `json:"original_language,omitempty"`
}
type chapterUpdateMetaOut struct {
	ChapterID string   `json:"chapter_id"`
	Updated   []string `json:"updated_fields"`
}

func (s *Server) toolChapterUpdateMeta(ctx context.Context, _ *mcp.CallToolRequest, in chapterUpdateMetaIn) (*mcp.CallToolResult, chapterUpdateMetaOut, error) {
	userID, ok := mcpUserID(ctx)
	if !ok {
		return nil, chapterUpdateMetaOut{}, errMissingIdentity
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, chapterUpdateMetaOut{}, errors.New("book_id must be a UUID")
	}
	chID, err := uuid.Parse(in.ChapterID)
	if err != nil {
		return nil, chapterUpdateMetaOut{}, errors.New("chapter_id must be a UUID")
	}
	if _, err := s.mcpRequireGrant(ctx, bookID, userID, GrantEdit); err != nil {
		return nil, chapterUpdateMetaOut{}, mcpOwnershipError(err)
	}
	var bState, cState string
	var pTitle *string
	var pSort int
	var pLang string
	if err := s.pool.QueryRow(ctx, `
SELECT b.lifecycle_state,c.lifecycle_state,c.title,c.sort_order,c.original_language
FROM books b JOIN chapters c ON c.book_id=b.id WHERE b.id=$1 AND c.id=$2`, bookID, chID).
		Scan(&bState, &cState, &pTitle, &pSort, &pLang); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, chapterUpdateMetaOut{}, errBookNotAccessible
		}
		return nil, chapterUpdateMetaOut{}, errors.New("failed to load chapter")
	}
	if bState != "active" || cState != "active" {
		return nil, chapterUpdateMetaOut{}, errors.New("book or chapter is not in an editable state")
	}
	updated := []string{}
	prior := map[string]any{"book_id": bookID.String(), "chapter_id": chID.String()}
	if in.Title != nil {
		updated = append(updated, "title")
		prior["title"] = derefStr(pTitle)
	}
	if in.SortOrder != nil {
		updated = append(updated, "sort_order")
		prior["sort_order"] = pSort
	}
	if in.OriginalLanguage != nil {
		updated = append(updated, "original_language")
		prior["original_language"] = pLang
	}
	if len(updated) == 0 {
		return nil, chapterUpdateMetaOut{}, errors.New("no fields to update")
	}
	if _, err := s.pool.Exec(ctx, `
UPDATE chapters SET title=COALESCE($3,title), sort_order=COALESCE($4,sort_order),
  original_language=COALESCE($5,original_language), updated_at=now()
WHERE id=$1 AND book_id=$2`, chID, bookID, in.Title, in.SortOrder, in.OriginalLanguage); err != nil {
		return nil, chapterUpdateMetaOut{}, errors.New("failed to update chapter")
	}
	res := undoResult("book_chapter_update_meta", prior)
	return res, chapterUpdateMetaOut{ChapterID: chID.String(), Updated: updated}, nil
}

// ── book_chapter_restore_revision ────────────────────────────────────────────

type restoreRevisionIn struct {
	BookID     string `json:"book_id" jsonschema:"the book the chapter belongs to (UUID)"`
	ChapterID  string `json:"chapter_id" jsonschema:"the chapter to restore (UUID)"`
	RevisionID string `json:"revision_id" jsonschema:"the revision to restore the draft to (UUID)"`
}
type restoreRevisionOut struct {
	ChapterID        string `json:"chapter_id"`
	NewDraftVersion  int64  `json:"new_draft_version"`
	SnapshotRevision string `json:"snapshot_revision_id"`
	RestoredRevision string `json:"restored_revision_id"`
}

func (s *Server) toolChapterRestoreRevision(ctx context.Context, _ *mcp.CallToolRequest, in restoreRevisionIn) (*mcp.CallToolResult, restoreRevisionOut, error) {
	userID, ok := mcpUserID(ctx)
	if !ok {
		return nil, restoreRevisionOut{}, errMissingIdentity
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, restoreRevisionOut{}, errors.New("book_id must be a UUID")
	}
	chID, err := uuid.Parse(in.ChapterID)
	if err != nil {
		return nil, restoreRevisionOut{}, errors.New("chapter_id must be a UUID")
	}
	revID, err := uuid.Parse(in.RevisionID)
	if err != nil {
		return nil, restoreRevisionOut{}, errors.New("revision_id must be a UUID")
	}
	if _, err := s.mcpRequireGrant(ctx, bookID, userID, GrantEdit); err != nil {
		return nil, restoreRevisionOut{}, mcpOwnershipError(err)
	}
	snapshotID, restoredVer, err := s.mcpRestoreRevision(ctx, userID, bookID, chID, revID)
	if err != nil {
		return nil, restoreRevisionOut{}, err
	}
	// Reverse op: restore to the snapshot this op just created (the prior draft).
	res := undoResult("book_chapter_restore_revision", map[string]any{
		"book_id": bookID.String(), "chapter_id": chID.String(), "revision_id": snapshotID.String(),
	})
	return res, restoreRevisionOut{
		ChapterID: chID.String(), NewDraftVersion: restoredVer, SnapshotRevision: snapshotID.String(), RestoredRevision: revID.String(),
	}, nil
}

// mcpRestoreRevision snapshots the current draft (so it is reversible), then
// overwrites the draft with the target revision's body, bumping draft_version.
// Returns the snapshot revision id (the undo target) and the new draft_version.
func (s *Server) mcpRestoreRevision(ctx context.Context, caller, bookID, chID, revID uuid.UUID) (snapshotID uuid.UUID, newVersion int64, err error) {
	tx, terr := s.pool.Begin(ctx)
	if terr != nil {
		return uuid.Nil, 0, errors.New("failed to restore revision")
	}
	defer tx.Rollback(ctx)
	var currentBody json.RawMessage
	var currentFormat string
	if err := tx.QueryRow(ctx, `
SELECT d.body,d.draft_format FROM chapter_drafts d JOIN chapters c ON c.id=d.chapter_id
WHERE d.chapter_id=$1 AND c.book_id=$2`, chID, bookID).Scan(&currentBody, &currentFormat); err != nil {
		return uuid.Nil, 0, errBookNotAccessible
	}
	var body json.RawMessage
	var bodyFormat string
	if err := tx.QueryRow(ctx, `
SELECT rv.body,COALESCE(rv.body_format,'plain') FROM chapter_revisions rv JOIN chapters c ON c.id=rv.chapter_id
WHERE rv.id=$1 AND rv.chapter_id=$2 AND c.book_id=$3`, revID, chID, bookID).Scan(&body, &bodyFormat); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return uuid.Nil, 0, errors.New("revision not found")
		}
		return uuid.Nil, 0, errors.New("failed to restore revision")
	}
	if err := tx.QueryRow(ctx, `
INSERT INTO chapter_revisions(chapter_id, body, body_format, message, author_user_id)
VALUES($1,$2,$3,'before restore',$4) RETURNING id`, chID, currentBody, currentFormat, caller).Scan(&snapshotID); err != nil {
		return uuid.Nil, 0, errors.New("failed to snapshot draft")
	}
	if err := tx.QueryRow(ctx, `
UPDATE chapter_drafts SET body=$2,draft_format=$3,draft_updated_at=now(),draft_version=draft_version+1
WHERE chapter_id=$1 RETURNING draft_version`, chID, body, bodyFormat).Scan(&newVersion); err != nil {
		return uuid.Nil, 0, errors.New("failed to restore revision")
	}
	_, _ = tx.Exec(ctx, `UPDATE chapters SET draft_updated_at=now(),draft_revision_count=draft_revision_count+1,updated_at=now() WHERE id=$1`, chID)
	if err := insertOutboxEvent(ctx, tx, "chapter.saved", chID, map[string]any{"book_id": bookID}); err != nil {
		return uuid.Nil, 0, errors.New("failed to restore revision")
	}
	if err := tx.Commit(ctx); err != nil {
		return uuid.Nil, 0, errors.New("failed to restore revision")
	}
	return snapshotID, newVersion, nil
}

// ── book_chapter_save_draft (H8: base_version mandatory) ─────────────────────

// saveDraftIn — `body` is PROSE TEXT, not hand-written editor JSON.
//
// It used to be a `json.RawMessage`, which the Go MCP schema reflector renders as
// `{"type":"array","items":{"type":"integer"}}` (a []byte is an array of bytes!). So the tool
// ADVERTISED "give me a list of integers" for a chapter of prose: no model could ever satisfy it,
// and the schema offered zero structural guidance, so a mid-tier model guessed a Slate-ish
// `[{type,children}]` shape and got rejected on every retry. Measured live (M0a, 2026-07-13): the
// flagship wrote GOOD prose, failed this call 3× in a row, and left a titled chapter row with ZERO
// prose — which a count-based check then read as "a drafted chapter". This tool has never once been
// callable by an agent with real content.
//
// The fix mirrors this file's own working sibling, `book_chapter_create`, which takes plain prose and
// runs it through plainTextToTiptapJSON (whose `_text` snapshots are what the chapter_blocks trigger
// reads). Writing prose is the one thing a mid-tier model is reliably good at; emitting nested editor
// JSON by hand is the one thing it is reliably bad at. `body_format:"json"` remains available for the
// round-trip case (an existing Tiptap doc read back and re-saved).
type saveDraftIn struct {
	BookID      string `json:"book_id" jsonschema:"the book the chapter belongs to (UUID)"`
	ChapterID   string `json:"chapter_id" jsonschema:"the chapter to save (UUID)"`
	BaseVersion int64  `json:"base_version" jsonschema:"REQUIRED — the draft_version you read; a mismatch returns 409 and stops (no overwrite)"`
	Body        string `json:"body" jsonschema:"the chapter's PROSE, as plain text. Separate paragraphs with a blank line. Write the prose itself — do NOT send editor/Tiptap JSON unless you also set body_format:\"json\"."`
	BodyFormat  string `json:"body_format,omitempty" jsonschema:"how to read body: \"plain\" (default — prose text) | \"markdown\" | \"json\" (an existing Tiptap doc being round-tripped)"`

	CommitMessage string `json:"commit_message,omitempty"`
}
type saveDraftOut struct {
	ChapterID        string `json:"chapter_id"`
	NewDraftVersion  int64  `json:"new_draft_version"`
	SnapshotRevision string `json:"snapshot_revision_id"`
}

// saveDraftBody turns the tool's inbound body into a canonical Tiptap doc, reusing the same
// formatters every other ingestion path uses (see tiptap.go). "json" is the round-trip escape
// hatch for an already-Tiptap doc; anything else is prose the model wrote.
func saveDraftBody(body, format string) (json.RawMessage, error) {
	switch format {
	case "json":
		raw := json.RawMessage(body)
		if !json.Valid(raw) {
			return nil, errors.New(`body_format:"json" requires body to be a valid Tiptap JSON document`)
		}
		return raw, nil
	case "markdown":
		return markdownToTiptapJSON(body), nil
	case "", "plain":
		return plainTextToTiptapJSON(body), nil
	default:
		return nil, errors.New(`body_format must be one of "plain", "markdown", "json"`)
	}
}

// ErrStaleDraftVersion — H8: book_chapter_save_draft requires base_version; a
// mismatch is reported as a stale-version conflict (the consumer surfaces a 409
// and stops, never overwriting).
var ErrStaleDraftVersion = errors.New("stale base_version — re-read the draft and retry")

func (s *Server) toolChapterSaveDraft(ctx context.Context, _ *mcp.CallToolRequest, in saveDraftIn) (*mcp.CallToolResult, saveDraftOut, error) {
	userID, ok := mcpUserID(ctx)
	if !ok {
		return nil, saveDraftOut{}, errMissingIdentity
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, saveDraftOut{}, errors.New("book_id must be a UUID")
	}
	chID, err := uuid.Parse(in.ChapterID)
	if err != nil {
		return nil, saveDraftOut{}, errors.New("chapter_id must be a UUID")
	}
	// H8: base_version is MANDATORY at the tool boundary. A missing/zero value is
	// rejected before any write (server-optional concurrency → tool-mandatory).
	if in.BaseVersion <= 0 {
		return nil, saveDraftOut{}, errors.New("base_version is required (the draft_version you read)")
	}
	if strings.TrimSpace(in.Body) == "" {
		return nil, saveDraftOut{}, errors.New("body is required (the chapter's prose)")
	}
	// Normalize prose → a canonical Tiptap doc, exactly as the sibling book_chapter_create does.
	// The `_text` snapshots this produces are what the chapter_blocks trigger reads, so the draft
	// lands as REAL BLOCKS — the difference between a chapter that has prose and an empty shell.
	jsonBody, err := saveDraftBody(in.Body, in.BodyFormat)
	if err != nil {
		return nil, saveDraftOut{}, err
	}
	if _, err := s.mcpRequireGrant(ctx, bookID, userID, GrantEdit); err != nil {
		return nil, saveDraftOut{}, mcpOwnershipError(err)
	}
	tx, terr := s.pool.Begin(ctx)
	if terr != nil {
		return nil, saveDraftOut{}, errors.New("failed to save draft")
	}
	defer tx.Rollback(ctx)
	var curr int64
	if err := tx.QueryRow(ctx, `
SELECT d.draft_version FROM chapter_drafts d JOIN chapters c ON c.id=d.chapter_id
WHERE d.chapter_id=$1 AND c.book_id=$2 AND c.lifecycle_state='active'`, chID, bookID).Scan(&curr); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, saveDraftOut{}, errBookNotAccessible
		}
		return nil, saveDraftOut{}, errors.New("failed to save draft")
	}
	if in.BaseVersion != curr {
		// 409 — version mismatch stops the write.
		return nil, saveDraftOut{}, ErrStaleDraftVersion
	}
	// Snapshot the prior draft as a revision (so save_draft is reversible via
	// restore_revision → undo_hint below).
	var snapshotID uuid.UUID
	if err := tx.QueryRow(ctx, `
INSERT INTO chapter_revisions(chapter_id, body, body_format, message, author_user_id)
SELECT chapter_id, body, draft_format, 'before assistant save', $2 FROM chapter_drafts WHERE chapter_id=$1
RETURNING id`, chID, userID).Scan(&snapshotID); err != nil {
		return nil, saveDraftOut{}, errors.New("failed to snapshot draft")
	}
	var newVer int64
	if err := tx.QueryRow(ctx, `
UPDATE chapter_drafts SET body=$2,draft_format='json',draft_updated_at=now(),draft_version=draft_version+1
WHERE chapter_id=$1 RETURNING draft_version`, chID, jsonBody).Scan(&newVer); err != nil {
		return nil, saveDraftOut{}, errors.New("failed to save draft")
	}
	_, _ = tx.Exec(ctx, `INSERT INTO chapter_revisions(chapter_id, body, body_format, message, author_user_id) VALUES($1,$2,'json',$3,$4)`,
		chID, jsonBody, nullIfEmpty(in.CommitMessage), userID)
	// NOTE (review-impl, M0a): deliberately do NOT touch chapter_raw_objects here.
	// That column is the ORIGINAL IMPORTED SOURCE text (per-chapter joined leaf_text), served by
	// GET /v1/books/{id}/chapters/{id}/raw — parse.go:255-262 is explicit that "chapter_drafts.body
	// remains the canonical edit source". An earlier cut of this fix upserted the assistant's draft
	// into it, which would have DESTROYED the import provenance of every imported chapter on the
	// first assistant save. The draft alone is sufficient: the chapter_blocks trigger projects
	// chapter_drafts.body → chapter_blocks.text_content, which is what prose-state and the rail's
	// book-state probe actually read.
	_, _ = tx.Exec(ctx, `UPDATE chapters SET draft_updated_at=now(),draft_revision_count=draft_revision_count+2,updated_at=now() WHERE id=$1`, chID)
	if err := insertOutboxEvent(ctx, tx, "chapter.saved", chID, map[string]any{"book_id": bookID}); err != nil {
		return nil, saveDraftOut{}, errors.New("failed to save draft")
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, saveDraftOut{}, errors.New("failed to save draft")
	}
	res := undoResult("book_chapter_restore_revision", map[string]any{
		"book_id": bookID.String(), "chapter_id": chID.String(), "revision_id": snapshotID.String(),
	})
	return res, saveDraftOut{ChapterID: chID.String(), NewDraftVersion: newVer, SnapshotRevision: snapshotID.String()}, nil
}
