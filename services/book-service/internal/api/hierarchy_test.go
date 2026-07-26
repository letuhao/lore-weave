package api

import (
	"testing"

	"github.com/google/uuid"
)

func strptr(s string) *string { return &s }
func intptr(i int) *int       { return &i }

// A decomposed chapter (real part_id) passes through untouched — no synthesis.
func TestResolveHierarchyPart_DecomposedPassthrough(t *testing.T) {
	bookID := uuid.MustParse("11111111-1111-1111-1111-111111111111")
	partID := uuid.MustParse("22222222-2222-2222-2222-222222222222")
	chPath := strptr("book/part-2/chapter-3")
	realParts := []hierarchyPart{{ID: partID.String(), Path: "book/part-2", Index: 2}}

	part, bookParts, outPath := resolveHierarchyPart(
		bookID,
		&partID, strptr("book/part-2"), intptr(2), strptr("Part Two"),
		chPath, 3, realParts,
	)

	if part.ID != partID.String() || part.Path != "book/part-2" || part.Index != 2 {
		t.Fatalf("decomposed part mutated: %+v", part)
	}
	if outPath != chPath || *outPath != "book/part-2/chapter-3" {
		t.Fatalf("chapter path mutated: %v", outPath)
	}
	if len(bookParts) != 1 {
		t.Fatalf("book_parts mutated: %+v", bookParts)
	}
}

// An undecomposed chapter (NULL part_id + NULL structural_path) gets a
// synthetic implicit part + synthesized chapter path, and the synthetic part is
// injected into an empty book_parts for the book-summary roll-up.
func TestResolveHierarchyPart_UndecomposedSynthesizes(t *testing.T) {
	bookID := uuid.MustParse("11111111-1111-1111-1111-111111111111")

	part, bookParts, outPath := resolveHierarchyPart(
		bookID,
		nil, nil, nil, nil,
		nil, 7, []hierarchyPart{},
	)

	if part == nil || part.Path != "book/part-1" || part.Index != 1 {
		t.Fatalf("expected synthetic part book/part-1 idx1, got %+v", part)
	}
	if _, err := uuid.Parse(part.ID); err != nil {
		t.Fatalf("synthetic part_id not a valid UUID: %q", part.ID)
	}
	if outPath == nil || *outPath != "book/part-1/chapter-7" {
		t.Fatalf("expected synthesized chapter path book/part-1/chapter-7, got %v", outPath)
	}
	if len(bookParts) != 1 || bookParts[0].Path != "book/part-1" {
		t.Fatalf("synthetic part not injected into book_parts: %+v", bookParts)
	}
}

// The synthetic part_id is DETERMINISTIC per book (uuidv5) — a re-run of
// extraction MERGEs the same :Part node (no graph drift), and differs across
// books.
func TestResolveHierarchyPart_DeterministicPerBook(t *testing.T) {
	bookA := uuid.MustParse("11111111-1111-1111-1111-111111111111")
	bookB := uuid.MustParse("33333333-3333-3333-3333-333333333333")

	p1, _, _ := resolveHierarchyPart(bookA, nil, nil, nil, nil, nil, 1, nil)
	p2, _, _ := resolveHierarchyPart(bookA, nil, nil, nil, nil, nil, 5, nil)
	pB, _, _ := resolveHierarchyPart(bookB, nil, nil, nil, nil, nil, 1, nil)

	if p1.ID != p2.ID {
		t.Fatalf("synthetic part_id not stable within a book: %s vs %s", p1.ID, p2.ID)
	}
	if p1.ID == pB.ID {
		t.Fatalf("synthetic part_id collides across books: %s", p1.ID)
	}
}

// An undecomposed chapter that nonetheless already has a structural_path keeps
// that path (only the part is synthesized).
func TestResolveHierarchyPart_KeepsExistingChapterPath(t *testing.T) {
	bookID := uuid.MustParse("11111111-1111-1111-1111-111111111111")
	existing := strptr("book/legacy-chapter-9")

	_, _, outPath := resolveHierarchyPart(
		bookID, nil, nil, nil, nil, existing, 9, nil,
	)
	if outPath != existing || *outPath != "book/legacy-chapter-9" {
		t.Fatalf("existing chapter path should be preserved, got %v", outPath)
	}
}
