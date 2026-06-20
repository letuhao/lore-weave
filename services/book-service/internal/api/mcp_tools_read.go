package api

// S-BOOK Tier-R (read) MCP tool handlers. Each resolves the caller identity
// from the envelope (NEVER a tool arg, SEC-1), verifies the book grant via the
// local resolver (mcpRequireGrant; View for reads), and returns structured
// output. Ownership errors collapse to the uniform "not accessible" (H13).

import (
	"context"
	"errors"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

const (
	mcpDefaultLimit = 20
	mcpMaxLimit     = 100
)

func clampLimit(n int) int {
	if n <= 0 {
		return mcpDefaultLimit
	}
	if n > mcpMaxLimit {
		return mcpMaxLimit
	}
	return n
}

// ── book_list ────────────────────────────────────────────────────────────────

type bookListIn struct {
	Limit  int `json:"limit,omitempty" jsonschema:"max books to return (default 20, max 100)"`
	Offset int `json:"offset,omitempty" jsonschema:"pagination offset"`
}
type bookSummary struct {
	BookID           uuid.UUID `json:"book_id"`
	Title            string    `json:"title"`
	AccessLevel      string    `json:"access_level"`
	OriginalLanguage *string   `json:"original_language"`
	LifecycleState   string    `json:"lifecycle_state"`
	ChapterCount     int       `json:"chapter_count"`
}
type bookListOut struct {
	Books []bookSummary `json:"books"`
	Total int           `json:"total"`
}

func (s *Server) toolBookList(ctx context.Context, _ *mcp.CallToolRequest, in bookListIn) (*mcp.CallToolResult, bookListOut, error) {
	userID, ok := mcpUserID(ctx)
	if !ok {
		return nil, bookListOut{}, errMissingIdentity
	}
	limit := clampLimit(in.Limit)
	offset := in.Offset
	if offset < 0 {
		offset = 0
	}
	// "My library": owned + collaborated, mirroring listBooks (excludes hidden
	// world-bible containers). Scoped to the caller by $1 — no cross-tenant leak.
	const filter = `(b.owner_user_id=$1 OR EXISTS(SELECT 1 FROM book_collaborators bc WHERE bc.book_id=b.id AND bc.user_id=$1)) AND b.is_bible=false AND b.lifecycle_state='active'`
	rows, err := s.pool.Query(ctx, `
SELECT b.id,b.title,b.original_language,b.lifecycle_state,
  COALESCE((SELECT COUNT(*) FROM chapters c WHERE c.book_id=b.id AND c.lifecycle_state='active'),0),
  CASE WHEN b.owner_user_id=$1 THEN 'owner'
       ELSE COALESCE((SELECT role FROM book_collaborators bc WHERE bc.book_id=b.id AND bc.user_id=$1),'none') END
FROM books b
WHERE `+filter+`
ORDER BY b.created_at DESC
LIMIT $2 OFFSET $3`, userID, limit, offset)
	if err != nil {
		return nil, bookListOut{}, errors.New("failed to list books")
	}
	defer rows.Close()
	out := bookListOut{Books: []bookSummary{}}
	for rows.Next() {
		var b bookSummary
		if err := rows.Scan(&b.BookID, &b.Title, &b.OriginalLanguage, &b.LifecycleState, &b.ChapterCount, &b.AccessLevel); err == nil {
			out.Books = append(out.Books, b)
		}
	}
	_ = s.pool.QueryRow(ctx, `SELECT COUNT(*) FROM books b WHERE `+filter, userID).Scan(&out.Total)
	return nil, out, nil
}

// ── book_get ─────────────────────────────────────────────────────────────────

type bookGetIn struct {
	BookID string `json:"book_id" jsonschema:"the book to fetch (UUID)"`
}
type bookDetail struct {
	BookID           uuid.UUID `json:"book_id"`
	Title            string    `json:"title"`
	Description      *string   `json:"description"`
	OriginalLanguage *string   `json:"original_language"`
	Summary          *string   `json:"summary"`
	GenreTags        []string  `json:"genre_tags"`
	LifecycleState   string    `json:"lifecycle_state"`
	ChapterCount     int       `json:"chapter_count"`
	AccessLevel      string    `json:"access_level"`
}
type bookGetOut struct {
	Book bookDetail `json:"book"`
}

func (s *Server) toolBookGet(ctx context.Context, _ *mcp.CallToolRequest, in bookGetIn) (*mcp.CallToolResult, bookGetOut, error) {
	userID, ok := mcpUserID(ctx)
	if !ok {
		return nil, bookGetOut{}, errMissingIdentity
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, bookGetOut{}, errors.New("book_id must be a UUID")
	}
	if _, err := s.mcpRequireGrant(ctx, bookID, userID, GrantView); err != nil {
		return nil, bookGetOut{}, mcpOwnershipError(err)
	}
	var d bookDetail
	var owner uuid.UUID
	err = s.pool.QueryRow(ctx, `
SELECT b.id,b.owner_user_id,b.title,b.description,b.original_language,b.summary,b.genre_tags,b.lifecycle_state,
  COALESCE((SELECT COUNT(*) FROM chapters c WHERE c.book_id=b.id AND c.lifecycle_state='active'),0),
  CASE WHEN b.owner_user_id=$2 THEN 'owner'
       ELSE COALESCE((SELECT role FROM book_collaborators bc WHERE bc.book_id=b.id AND bc.user_id=$2),'none') END
FROM books b WHERE b.id=$1`, bookID, userID).
		Scan(&d.BookID, &owner, &d.Title, &d.Description, &d.OriginalLanguage, &d.Summary, &d.GenreTags, &d.LifecycleState, &d.ChapterCount, &d.AccessLevel)
	if errors.Is(err, pgx.ErrNoRows) || d.LifecycleState == "purge_pending" {
		// Grant already passed, so this is a TOCTOU race; still collapse uniformly.
		return nil, bookGetOut{}, errBookNotAccessible
	}
	if err != nil {
		return nil, bookGetOut{}, errors.New("failed to get book")
	}
	if d.GenreTags == nil {
		d.GenreTags = []string{}
	}
	return nil, bookGetOut{Book: d}, nil
}

// ── book_list_chapters ───────────────────────────────────────────────────────

type listChaptersIn struct {
	BookID string `json:"book_id" jsonschema:"the book whose chapters to list (UUID)"`
	Limit  int    `json:"limit,omitempty" jsonschema:"max chapters to return (default 20, max 100)"`
	Offset int    `json:"offset,omitempty" jsonschema:"pagination offset"`
}
type chapterSummary struct {
	ChapterID        uuid.UUID `json:"chapter_id"`
	Title            *string   `json:"title"`
	OriginalLanguage string    `json:"original_language"`
	SortOrder        int       `json:"sort_order"`
	EditorialStatus  string    `json:"editorial_status"`
	DraftRevisions   int       `json:"draft_revision_count"`
	LifecycleState   string    `json:"lifecycle_state"`
}
type listChaptersOut struct {
	Chapters []chapterSummary `json:"chapters"`
	Total    int              `json:"total"`
}

func (s *Server) toolBookListChapters(ctx context.Context, _ *mcp.CallToolRequest, in listChaptersIn) (*mcp.CallToolResult, listChaptersOut, error) {
	userID, ok := mcpUserID(ctx)
	if !ok {
		return nil, listChaptersOut{}, errMissingIdentity
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, listChaptersOut{}, errors.New("book_id must be a UUID")
	}
	if _, err := s.mcpRequireGrant(ctx, bookID, userID, GrantView); err != nil {
		return nil, listChaptersOut{}, mcpOwnershipError(err)
	}
	limit := clampLimit(in.Limit)
	offset := in.Offset
	if offset < 0 {
		offset = 0
	}
	rows, err := s.pool.Query(ctx, `
SELECT id,title,original_language,sort_order,editorial_status,draft_revision_count,lifecycle_state
FROM chapters WHERE book_id=$1 AND lifecycle_state='active'
ORDER BY sort_order, created_at LIMIT $2 OFFSET $3`, bookID, limit, offset)
	if err != nil {
		return nil, listChaptersOut{}, errors.New("failed to list chapters")
	}
	defer rows.Close()
	out := listChaptersOut{Chapters: []chapterSummary{}}
	for rows.Next() {
		var c chapterSummary
		if err := rows.Scan(&c.ChapterID, &c.Title, &c.OriginalLanguage, &c.SortOrder, &c.EditorialStatus, &c.DraftRevisions, &c.LifecycleState); err == nil {
			out.Chapters = append(out.Chapters, c)
		}
	}
	_ = s.pool.QueryRow(ctx, `SELECT COUNT(*) FROM chapters WHERE book_id=$1 AND lifecycle_state='active'`, bookID).Scan(&out.Total)
	return nil, out, nil
}

// ── book_get_chapter ─────────────────────────────────────────────────────────

type getChapterIn struct {
	BookID    string `json:"book_id" jsonschema:"the book the chapter belongs to (UUID)"`
	ChapterID string `json:"chapter_id" jsonschema:"the chapter to fetch (UUID)"`
}
type chapterDetail struct {
	ChapterID           uuid.UUID  `json:"chapter_id"`
	BookID              uuid.UUID  `json:"book_id"`
	Title               *string    `json:"title"`
	OriginalLanguage    string     `json:"original_language"`
	SortOrder           int        `json:"sort_order"`
	EditorialStatus     string     `json:"editorial_status"`
	PublishedRevisionID *uuid.UUID `json:"published_revision_id"`
	DraftRevisions      int        `json:"draft_revision_count"`
	LifecycleState      string     `json:"lifecycle_state"`
}
type getChapterOut struct {
	Chapter chapterDetail `json:"chapter"`
}

func (s *Server) toolBookGetChapter(ctx context.Context, _ *mcp.CallToolRequest, in getChapterIn) (*mcp.CallToolResult, getChapterOut, error) {
	userID, ok := mcpUserID(ctx)
	if !ok {
		return nil, getChapterOut{}, errMissingIdentity
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, getChapterOut{}, errors.New("book_id must be a UUID")
	}
	chID, err := uuid.Parse(in.ChapterID)
	if err != nil {
		return nil, getChapterOut{}, errors.New("chapter_id must be a UUID")
	}
	if _, err := s.mcpRequireGrant(ctx, bookID, userID, GrantView); err != nil {
		return nil, getChapterOut{}, mcpOwnershipError(err)
	}
	var c chapterDetail
	var titleRaw string
	err = s.pool.QueryRow(ctx, `
SELECT c.id,c.book_id,c.title,c.original_language,c.sort_order,c.editorial_status,c.published_revision_id,c.draft_revision_count,c.lifecycle_state
FROM chapters c WHERE c.id=$1 AND c.book_id=$2`, chID, bookID).
		Scan(&c.ChapterID, &c.BookID, &titleRaw, &c.OriginalLanguage, &c.SortOrder, &c.EditorialStatus, &c.PublishedRevisionID, &c.DraftRevisions, &c.LifecycleState)
	if errors.Is(err, pgx.ErrNoRows) || c.LifecycleState == "purge_pending" {
		return nil, getChapterOut{}, errBookNotAccessible
	}
	if err != nil {
		return nil, getChapterOut{}, errors.New("failed to get chapter")
	}
	if titleRaw != "" {
		c.Title = &titleRaw
	}
	return nil, getChapterOut{Chapter: c}, nil
}

// ── book_list_revisions ──────────────────────────────────────────────────────

type listRevisionsIn struct {
	BookID    string `json:"book_id" jsonschema:"the book the chapter belongs to (UUID)"`
	ChapterID string `json:"chapter_id" jsonschema:"the chapter whose revisions to list (UUID)"`
	Limit     int    `json:"limit,omitempty" jsonschema:"max revisions to return (default 20, max 100)"`
	Offset    int    `json:"offset,omitempty" jsonschema:"pagination offset"`
}
type revisionSummary struct {
	RevisionID     uuid.UUID  `json:"revision_id"`
	CreatedAt      time.Time  `json:"created_at"`
	AuthorUserID   *uuid.UUID `json:"author_user_id"`
	Message        *string    `json:"message"`
	BodyByteLength int        `json:"body_byte_length"`
}
type listRevisionsOut struct {
	Revisions []revisionSummary `json:"revisions"`
	Total     int               `json:"total"`
}

func (s *Server) toolBookListRevisions(ctx context.Context, _ *mcp.CallToolRequest, in listRevisionsIn) (*mcp.CallToolResult, listRevisionsOut, error) {
	userID, ok := mcpUserID(ctx)
	if !ok {
		return nil, listRevisionsOut{}, errMissingIdentity
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, listRevisionsOut{}, errors.New("book_id must be a UUID")
	}
	chID, err := uuid.Parse(in.ChapterID)
	if err != nil {
		return nil, listRevisionsOut{}, errors.New("chapter_id must be a UUID")
	}
	if _, err := s.mcpRequireGrant(ctx, bookID, userID, GrantView); err != nil {
		return nil, listRevisionsOut{}, mcpOwnershipError(err)
	}
	limit := clampLimit(in.Limit)
	offset := in.Offset
	if offset < 0 {
		offset = 0
	}
	rows, err := s.pool.Query(ctx, `
SELECT rv.id,rv.created_at,rv.author_user_id,rv.message,octet_length(rv.body::text)
FROM chapter_revisions rv JOIN chapters c ON c.id=rv.chapter_id
WHERE rv.chapter_id=$1 AND c.book_id=$2
ORDER BY rv.created_at DESC LIMIT $3 OFFSET $4`, chID, bookID, limit, offset)
	if err != nil {
		return nil, listRevisionsOut{}, errors.New("failed to list revisions")
	}
	defer rows.Close()
	out := listRevisionsOut{Revisions: []revisionSummary{}}
	for rows.Next() {
		var rv revisionSummary
		if err := rows.Scan(&rv.RevisionID, &rv.CreatedAt, &rv.AuthorUserID, &rv.Message, &rv.BodyByteLength); err == nil {
			out.Revisions = append(out.Revisions, rv)
		}
	}
	_ = s.pool.QueryRow(ctx, `SELECT COUNT(*) FROM chapter_revisions WHERE chapter_id=$1`, chID).Scan(&out.Total)
	return nil, out, nil
}
