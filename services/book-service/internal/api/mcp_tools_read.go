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

	lwmcp "github.com/loreweave/loreweave_mcp"
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
	BookID           string  `json:"book_id"`
	Title            string  `json:"title"`
	AccessLevel      string  `json:"access_level"`
	OriginalLanguage *string `json:"original_language"`
	LifecycleState   string  `json:"lifecycle_state"`
	ChapterCount     int     `json:"chapter_count"`
}
type bookListOut struct {
	Books []bookSummary `json:"books"`
	Total int           `json:"total"`
}

// bookListFilter builds the WHERE clause for book_list (the "my library"
// enumeration), parameterized by $1 = caller. ownerOnly=true (OD-8 — a PUBLIC MCP
// key) drops the collaborator clause so a public key cannot ENUMERATE books merely
// SHARED to the caller (it would otherwise leak another tenant's book ids/titles),
// matching the per-book owner gate (mcpRequireGrant). First-party keeps owned+shared.
func bookListFilter(ownerOnly bool) string {
	// WS-1.2 · EGRESS GUARD #7, MCP twin (review-impl P1). The REST library LIST filters
	// out kind='diary', but this MCP book_list tool — the agent-facing enumerator in the
	// SAME service — did not. So the moment WS-1.4 provisions a diary, ANY agent (including
	// a public MCP key) could enumerate it here and then read its plaintext prose. The
	// guard belongs on BOTH list surfaces, not just the browser one.
	if ownerOnly {
		return `b.owner_user_id=$1 AND b.is_bible=false AND b.kind<>'diary' AND b.lifecycle_state='active'`
	}
	return `(b.owner_user_id=$1 OR EXISTS(SELECT 1 FROM book_collaborators bc WHERE bc.book_id=b.id AND bc.user_id=$1)) AND b.is_bible=false AND b.kind<>'diary' AND b.lifecycle_state='active'`
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
	filter := bookListFilter(lwmcp.OwnerOnlyFromCtx(ctx))
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
		var bookID uuid.UUID
		if err := rows.Scan(&bookID, &b.Title, &b.OriginalLanguage, &b.LifecycleState, &b.ChapterCount, &b.AccessLevel); err == nil {
			b.BookID = bookID.String()
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
	BookID           string   `json:"book_id"`
	Title            string   `json:"title"`
	Description      *string  `json:"description"`
	OriginalLanguage *string  `json:"original_language"`
	Summary          *string  `json:"summary"`
	GenreTags        []string `json:"genre_tags"`
	LifecycleState   string   `json:"lifecycle_state"`
	ChapterCount     int      `json:"chapter_count"`
	AccessLevel      string   `json:"access_level"`
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
	var bookIDScan, owner uuid.UUID
	err = s.pool.QueryRow(ctx, `
SELECT b.id,b.owner_user_id,b.title,b.description,b.original_language,b.summary,b.genre_tags,b.lifecycle_state,
  COALESCE((SELECT COUNT(*) FROM chapters c WHERE c.book_id=b.id AND c.lifecycle_state='active'),0),
  CASE WHEN b.owner_user_id=$2 THEN 'owner'
       ELSE COALESCE((SELECT role FROM book_collaborators bc WHERE bc.book_id=b.id AND bc.user_id=$2),'none') END
FROM books b WHERE b.id=$1`, bookID, userID).
		Scan(&bookIDScan, &owner, &d.Title, &d.Description, &d.OriginalLanguage, &d.Summary, &d.GenreTags, &d.LifecycleState, &d.ChapterCount, &d.AccessLevel)
	if errors.Is(err, pgx.ErrNoRows) || d.LifecycleState == "purge_pending" {
		// Grant already passed, so this is a TOCTOU race; still collapse uniformly.
		return nil, bookGetOut{}, errBookNotAccessible
	}
	if err != nil {
		return nil, bookGetOut{}, errors.New("failed to get book")
	}
	d.BookID = bookIDScan.String()
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
	ChapterID        string  `json:"chapter_id"`
	Title            *string `json:"title"`
	OriginalLanguage string  `json:"original_language"`
	SortOrder        int     `json:"sort_order"`
	EditorialStatus  string  `json:"editorial_status"`
	DraftRevisions   int     `json:"draft_revision_count"`
	LifecycleState   string  `json:"lifecycle_state"`
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
		var chID uuid.UUID
		if err := rows.Scan(&chID, &c.Title, &c.OriginalLanguage, &c.SortOrder, &c.EditorialStatus, &c.DraftRevisions, &c.LifecycleState); err == nil {
			c.ChapterID = chID.String()
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
	// IncludeBody opts into returning the chapter's plain-text prose (the `body`
	// field) alongside the metadata. Default false — the body can be thousands of
	// tokens, so a caller that only needs metadata does not pay for it. Use it to
	// READ a chapter after story_search locates it (the grep→read loop).
	IncludeBody bool `json:"include_body,omitempty" jsonschema:"return the chapter's plain-text prose in 'body' (default false; the body can be large)"`
	// D-2-CHAPTER-PAGINATION. include_body used to be an UNBOUNDED string_agg over every block:
	// a long chapter dumped its whole prose into one tool result, which is the context problem in
	// miniature (and, past the MCP result-size ceiling, an outright failure). Now the read is
	// bounded by DEFAULT and always SIGNALS when it stopped early — a truncation the caller cannot
	// see is the silent-truncation bug class this repo treats as a defect.
	Offset int `json:"offset,omitempty" jsonschema:"paging: block index to start the body at (default 0)"`
	Limit  int `json:"limit,omitempty" jsonschema:"paging: how many blocks of prose to return (default 300, max 300). If the chapter has more, the result sets truncated=true and next_offset — call again with offset=next_offset to continue."`
}

// maxChapterBlocks bounds ONE body read. Deliberately not "unlimited": the previous unbounded
// read is exactly how a 10k-word chapter silently ate a turn's context budget. A caller that
// wants the rest gets told to ask for it (truncated + next_offset), never quietly short-changed.
const maxChapterBlocks = 300
type chapterDetail struct {
	ChapterID           string  `json:"chapter_id"`
	BookID              string  `json:"book_id"`
	Title               *string `json:"title"`
	OriginalLanguage    string  `json:"original_language"`
	SortOrder           int     `json:"sort_order"`
	EditorialStatus     string  `json:"editorial_status"`
	PublishedRevisionID *string `json:"published_revision_id"`
	DraftRevisions      int     `json:"draft_revision_count"`
	LifecycleState      string  `json:"lifecycle_state"`
}

// uuidPtrToStr renders an optional UUID as an optional string for an MCP tool
// OUTPUT struct (the go-sdk infers a string-or-null schema from *string, but a
// [16]byte from *uuid.UUID, which then fails its own output validation since
// uuid.UUID marshals as a string).
func uuidPtrToStr(p *uuid.UUID) *string {
	if p == nil {
		return nil
	}
	s := p.String()
	return &s
}
type getChapterOut struct {
	Chapter chapterDetail `json:"chapter"`
	// Body is the chapter's plain-text prose for the requested block window, present only when
	// the caller passed include_body=true. omitempty so a metadata-only fetch stays lean.
	Body *string `json:"body,omitempty"`
	// Truncated is true when this body is only PART of the chapter — i.e. more blocks exist past
	// the window. Paired with NextOffset so the caller can continue. Never silently short.
	Truncated bool `json:"truncated,omitempty"`
	// NextOffset is the block index to pass as `offset` to fetch the next page. Set iff Truncated.
	NextOffset *int `json:"next_offset,omitempty"`
	// TotalBlocks is the chapter's full block count, so a caller knows the size of what it is paging.
	TotalBlocks *int `json:"total_blocks,omitempty"`
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
	var chIDScan, bookIDScan uuid.UUID
	var pubRevID *uuid.UUID
	// chapters.title is NULLABLE (a titleless chapter is valid), so scan straight
	// into the *string field (like toolBookListChapters) — a plain-string target
	// errors "cannot scan NULL into *string" on every titleless chapter.
	err = s.pool.QueryRow(ctx, `
SELECT c.id,c.book_id,c.title,c.original_language,c.sort_order,c.editorial_status,c.published_revision_id,c.draft_revision_count,c.lifecycle_state
FROM chapters c WHERE c.id=$1 AND c.book_id=$2`, chID, bookID).
		Scan(&chIDScan, &bookIDScan, &c.Title, &c.OriginalLanguage, &c.SortOrder, &c.EditorialStatus, &pubRevID, &c.DraftRevisions, &c.LifecycleState)
	if errors.Is(err, pgx.ErrNoRows) || c.LifecycleState == "purge_pending" {
		return nil, getChapterOut{}, errBookNotAccessible
	}
	if err != nil {
		return nil, getChapterOut{}, errors.New("failed to get chapter")
	}
	c.ChapterID = chIDScan.String()
	c.BookID = bookIDScan.String()
	c.PublishedRevisionID = uuidPtrToStr(pubRevID)
	out := getChapterOut{Chapter: c}
	if in.IncludeBody {
		// The chapter's plain-text prose from the extracted, searchable blocks
		// (same source story_search's lexical leg hits — so "find then read" is
		// consistent). COALESCE guards NULL text_content on non-text blocks
		// (D-CHAPTER-BLOCKS null-nontext class); ordered by block_index.
		//
		// D-2-CHAPTER-PAGINATION: bounded window + an explicit truncation signal.
		offset := in.Offset
		if offset < 0 {
			offset = 0
		}
		limit := in.Limit
		if limit <= 0 || limit > maxChapterBlocks {
			limit = maxChapterBlocks
		}

		var total int
		if err := s.pool.QueryRow(ctx,
			`SELECT count(*) FROM chapter_blocks WHERE chapter_id=$1`, chID).Scan(&total); err != nil {
			return nil, getChapterOut{}, errors.New("failed to read chapter body")
		}

		var prose string
		if err := s.pool.QueryRow(ctx, `
SELECT COALESCE(string_agg(text, E'\n\n' ORDER BY block_index), '') FROM (
  SELECT block_index, COALESCE(text_content, '') AS text
  FROM chapter_blocks WHERE chapter_id=$1
  ORDER BY block_index OFFSET $2 LIMIT $3
) w`, chID, offset, limit).Scan(&prose); err != nil {
			return nil, getChapterOut{}, errors.New("failed to read chapter body")
		}
		out.Body = &prose
		out.TotalBlocks = &total
		if end := offset + limit; end < total {
			out.Truncated = true
			next := end
			out.NextOffset = &next
		}
	}
	return nil, out, nil
}

// ── book_list_revisions ──────────────────────────────────────────────────────

type listRevisionsIn struct {
	BookID    string `json:"book_id" jsonschema:"the book the chapter belongs to (UUID)"`
	ChapterID string `json:"chapter_id" jsonschema:"the chapter whose revisions to list (UUID)"`
	Limit     int    `json:"limit,omitempty" jsonschema:"max revisions to return (default 20, max 100)"`
	Offset    int    `json:"offset,omitempty" jsonschema:"pagination offset"`
}
type revisionSummary struct {
	RevisionID     string    `json:"revision_id"`
	CreatedAt      time.Time `json:"created_at"`
	AuthorUserID   *string   `json:"author_user_id"`
	Message        *string   `json:"message"`
	BodyByteLength int       `json:"body_byte_length"`
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
		var revID uuid.UUID
		var authorID *uuid.UUID
		if err := rows.Scan(&revID, &rv.CreatedAt, &authorID, &rv.Message, &rv.BodyByteLength); err == nil {
			rv.RevisionID = revID.String()
			rv.AuthorUserID = uuidPtrToStr(authorID)
			out.Revisions = append(out.Revisions, rv)
		}
	}
	_ = s.pool.QueryRow(ctx, `SELECT COUNT(*) FROM chapter_revisions WHERE chapter_id=$1`, chID).Scan(&out.Total)
	return nil, out, nil
}
