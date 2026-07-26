package api

// Unified content-read tools (docs/specs/2026-07-22-book-tools-redesign.md Part C/D).
//
// The "ls / grep / cat" model: the agent navigates a book like a filesystem, never dumps it.
//   book_read   = cat  — the full content of ONE addressed item (book | chapter | scene).
//   book_list   = ls   — REFERENCES only, paged (built in the next slice).
//   book_search = grep — content match (kept).
//
// Both new reads dispatch to the EXISTING typed handlers (reusing their grant-check, queries,
// and the chapter block-paging already shipped) and wrap the result in ONE uniform envelope
// that carries the OUTPUT contract: reference-first, a structured `page` block with an
// is_complete boolean, and a prose `guidance` stop-signal so a weak model never loops.

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// pageEnvelope is the uniform paging block on every set/paged result (OUT-2, OUT-5). The
// structured half of the anti-loop stop-signal is `IsComplete`: true ⇔ the caller has the
// whole set/body and MUST NOT call again.
type pageEnvelope struct {
	Returned   int  `json:"returned"`
	Total      int  `json:"total"`
	Offset     int  `json:"offset"`
	NextOffset *int `json:"next_offset,omitempty"`
	HasMore    bool `json:"has_more"`
	IsComplete bool `json:"is_complete"`
}

// listPage builds the envelope + the prose `guidance` directive (D-3) for a paged SET. `noun`
// is the plural listed ("chapters"); `retryPrefix` is the call to resume with (e.g.
// "book_list kind=chapters") — listPage appends the exact next offset when there's more.
func listPage(noun string, returned, total, offset int, retryPrefix string) (pageEnvelope, string) {
	env := pageEnvelope{Returned: returned, Total: total, Offset: offset}
	env.HasMore = offset+returned < total
	env.IsComplete = !env.HasMore
	switch {
	case total == 0:
		return env, fmt.Sprintf("no %s here. Do NOT retry — there are none to page.", noun)
	case env.IsComplete && offset == 0:
		return env, fmt.Sprintf("complete — all %d %s returned. Do NOT call again for this listing.", total, noun)
	case env.IsComplete:
		return env, fmt.Sprintf("complete — the final %d of %d %s. Do NOT call again.", returned, total, noun)
	default:
		next := offset + returned
		env.NextOffset = &next
		return env, fmt.Sprintf("%d of %d %s so far. Call `%s offset=%d` ONLY if you still need more; otherwise stop.",
			offset+returned, total, noun, retryPrefix, next)
	}
}

// ── book_read (cat) ───────────────────────────────────────────────────────────

type bookReadIn struct {
	BookID    string `json:"book_id" jsonschema:"the book (UUID) — required"`
	ChapterID string `json:"chapter_id,omitempty" jsonschema:"read THIS chapter's metadata + prose (UUID). Omit for the book's own detail."`
	SceneID   string `json:"scene_id,omitempty" jsonschema:"read THIS scene's prose (UUID). Takes precedence over chapter_id."`
	Offset    int    `json:"offset,omitempty" jsonschema:"paging: chapter-body block index to start at (default 0). Only for a chapter read."`
	Limit     int    `json:"limit,omitempty" jsonschema:"paging: chapter-body blocks to return (default 300, max 300). Only for a chapter read."`
}

// bookReadOut — the deepest id present decides which of book/chapter/scene is populated
// (implicit discriminator, CAT-1). `page` is present only when a chapter body was paged.
type bookReadOut struct {
	Read     string         `json:"read"` // "book" | "chapter" | "scene"
	Book     *bookDetail    `json:"book,omitempty"`
	Chapter  *chapterDetail `json:"chapter,omitempty"`
	Scene    *sceneDetail   `json:"scene,omitempty"`
	Body     *string        `json:"body,omitempty"`
	Page     *pageEnvelope  `json:"page,omitempty"`
	Guidance string         `json:"guidance"`
}

func (s *Server) toolBookRead(ctx context.Context, req *mcp.CallToolRequest, in bookReadIn) (*mcp.CallToolResult, bookReadOut, error) {
	switch {
	case in.SceneID != "":
		_, sc, err := s.toolBookSceneGet(ctx, req, sceneGetIn{BookID: in.BookID, SceneID: in.SceneID})
		if err != nil {
			return nil, bookReadOut{}, fmt.Errorf("%w — if the scene id is wrong, call book_list kind=scenes for valid ids; do NOT retry the same id", err)
		}
		return nil, bookReadOut{Read: "scene", Scene: &sc.Scene,
			Guidance: "complete — this scene's full prose. Do NOT call again for this scene."}, nil

	case in.ChapterID != "":
		_, ch, err := s.toolBookGetChapter(ctx, req, getChapterIn{
			BookID: in.BookID, ChapterID: in.ChapterID, IncludeBody: true, Offset: in.Offset, Limit: in.Limit})
		if err != nil {
			return nil, bookReadOut{}, fmt.Errorf("%w — if the chapter id is wrong, call book_list kind=chapters for valid ids; do NOT retry the same id", err)
		}
		out := bookReadOut{Read: "chapter", Chapter: &ch.Chapter, Body: ch.Body}
		total := 0
		if ch.TotalBlocks != nil {
			total = *ch.TotalBlocks
		}
		env := pageEnvelope{Total: total, Offset: in.Offset, HasMore: ch.Truncated, IsComplete: !ch.Truncated, NextOffset: ch.NextOffset}
		if ch.Truncated {
			env.Returned = *ch.NextOffset - in.Offset
			out.Guidance = fmt.Sprintf("chapter body truncated at block %d of %d. Call book_read again with offset=%d to continue, or stop if you have enough.", *ch.NextOffset, total, *ch.NextOffset)
		} else {
			env.Returned = total - in.Offset
			out.Guidance = "complete — the chapter's full body. Do NOT call again for this chapter."
		}
		out.Page = &env
		return nil, out, nil

	default:
		_, bk, err := s.toolBookGet(ctx, req, bookGetIn{BookID: in.BookID})
		if err != nil {
			return nil, bookReadOut{}, err
		}
		return nil, bookReadOut{Read: "book", Book: &bk.Book,
			Guidance: "complete — the book's detail. To read a chapter's prose, call book_read with a chapter_id (use book_list kind=chapters for valid ids)."}, nil
	}
}

// ── book_list (ls) ────────────────────────────────────────────────────────────

type bookListKindIn struct {
	Kind      string `json:"kind,omitempty" jsonschema:"what to list: books | chapters | revisions | scenes (default books)"`
	BookID    string `json:"book_id,omitempty" jsonschema:"required for kind=chapters|revisions|scenes"`
	ChapterID string `json:"chapter_id,omitempty" jsonschema:"required for kind=revisions; optional chapter filter for kind=scenes"`
	Limit     int    `json:"limit,omitempty" jsonschema:"max items to return (default 20, max 100)"`
	Offset    int    `json:"offset,omitempty" jsonschema:"pagination offset"`
}

// bookListOut2 — references only (OUT-1): exactly ONE slice is populated, keyed by `kind`.
// `total` is kept top-level for backward-compat with the prior single-purpose book_list; the
// page envelope is the home for paging + the is_complete stop-signal, with the prose guidance.
type bookListOut2 struct {
	Kind      string            `json:"kind"`
	Books     []bookSummary     `json:"books,omitempty"`
	Chapters  []chapterSummary  `json:"chapters,omitempty"`
	Revisions []revisionSummary `json:"revisions,omitempty"`
	Scenes    []sceneSummary    `json:"scenes,omitempty"`
	Total     int               `json:"total"`
	Page      pageEnvelope      `json:"page"`
	Guidance  string            `json:"guidance"`
}

func (s *Server) toolBookListUnified(ctx context.Context, req *mcp.CallToolRequest, in bookListKindIn) (*mcp.CallToolResult, bookListOut2, error) {
	kind := strings.ToLower(strings.TrimSpace(in.Kind))
	if kind == "" {
		kind = "books"
	}
	switch kind {
	case "books":
		_, r, err := s.toolBookList(ctx, req, bookListIn{Limit: in.Limit, Offset: in.Offset})
		if err != nil {
			return nil, bookListOut2{}, err
		}
		env, g := listPage("books", len(r.Books), r.Total, in.Offset, "book_list kind=books")
		return nil, bookListOut2{Kind: "books", Books: r.Books, Total: r.Total, Page: env, Guidance: g}, nil
	case "chapters":
		if in.BookID == "" {
			return nil, bookListOut2{}, errors.New("kind=chapters needs book_id — pass the book whose chapters to list")
		}
		_, r, err := s.toolBookListChapters(ctx, req, listChaptersIn{BookID: in.BookID, Limit: in.Limit, Offset: in.Offset})
		if err != nil {
			return nil, bookListOut2{}, err
		}
		env, g := listPage("chapters", len(r.Chapters), r.Total, in.Offset, "book_list kind=chapters book_id=<id>")
		return nil, bookListOut2{Kind: "chapters", Chapters: r.Chapters, Total: r.Total, Page: env, Guidance: g}, nil
	case "revisions":
		if in.BookID == "" || in.ChapterID == "" {
			return nil, bookListOut2{}, errors.New("kind=revisions needs book_id + chapter_id — pass the chapter whose revisions to list")
		}
		_, r, err := s.toolBookListRevisions(ctx, req, listRevisionsIn{BookID: in.BookID, ChapterID: in.ChapterID, Limit: in.Limit, Offset: in.Offset})
		if err != nil {
			return nil, bookListOut2{}, err
		}
		env, g := listPage("revisions", len(r.Revisions), r.Total, in.Offset, "book_list kind=revisions")
		return nil, bookListOut2{Kind: "revisions", Revisions: r.Revisions, Total: r.Total, Page: env, Guidance: g}, nil
	case "scenes":
		if in.BookID == "" {
			return nil, bookListOut2{}, errors.New("kind=scenes needs book_id — pass the book whose scenes to list")
		}
		_, r, err := s.toolBookSceneList(ctx, req, sceneListIn{BookID: in.BookID, ChapterID: in.ChapterID, Limit: in.Limit, Offset: in.Offset})
		if err != nil {
			return nil, bookListOut2{}, err
		}
		env, g := listPage("scenes", len(r.Scenes), r.Total, in.Offset, "book_list kind=scenes")
		return nil, bookListOut2{Kind: "scenes", Scenes: r.Scenes, Total: r.Total, Page: env, Guidance: g}, nil
	default:
		return nil, bookListOut2{}, fmt.Errorf("unknown kind %q — use one of: books, chapters, revisions, scenes", in.Kind)
	}
}
