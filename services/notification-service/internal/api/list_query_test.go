package api

import (
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
)

// MB3 — the notifications feed query builder. Keyset paging (before+before_id) must add the
// row-value predicate, keep the total-ordered DESC sort, and OMIT offset; the legacy path keeps
// OFFSET. Pure function → deterministic unit test without a DB.

func TestListNotificationsQuery_OffsetPathByDefault(t *testing.T) {
	uid := uuid.New()
	q, args, keyset := listNotificationsQuery(uid, "", false, nil, nil, 20, 40)
	if keyset {
		t.Fatalf("expected offset path (keyset=false)")
	}
	if !strings.Contains(q, "ORDER BY created_at DESC, id DESC") {
		t.Errorf("missing total-ordered sort: %s", q)
	}
	if !strings.Contains(q, "OFFSET") {
		t.Errorf("offset path must include OFFSET: %s", q)
	}
	if strings.Contains(q, "(created_at, id) <") {
		t.Errorf("offset path must NOT include the keyset predicate: %s", q)
	}
	// args: userID, limit, offset
	if len(args) != 3 || args[0] != uid || args[1] != 20 || args[2] != 40 {
		t.Errorf("unexpected args: %v", args)
	}
}

func TestListNotificationsQuery_KeysetOmitsOffsetAndAddsPredicate(t *testing.T) {
	uid := uuid.New()
	cursorTime := time.Date(2026, 7, 14, 10, 0, 0, 0, time.UTC)
	cursorID := uuid.New()
	q, args, keyset := listNotificationsQuery(uid, "", false, &cursorTime, &cursorID, 20, 40)
	if !keyset {
		t.Fatalf("expected keyset path")
	}
	if !strings.Contains(q, "(created_at, id) < ($2, $3)") {
		t.Errorf("keyset predicate missing/misplaced: %s", q)
	}
	if strings.Contains(q, "OFFSET") {
		t.Errorf("keyset path must NOT use OFFSET (that's the drift bug it fixes): %s", q)
	}
	if !strings.Contains(q, "ORDER BY created_at DESC, id DESC") {
		t.Errorf("missing total-ordered sort: %s", q)
	}
	// args: userID, before, beforeID, limit  (no offset)
	if len(args) != 4 {
		t.Fatalf("expected 4 args (uid, before, beforeID, limit), got %d: %v", len(args), args)
	}
	if args[0] != uid || args[1] != cursorTime || args[2] != cursorID || args[3] != 20 {
		t.Errorf("unexpected keyset args: %v", args)
	}
}

func TestListNotificationsQuery_KeysetNeedsBothCursorParts(t *testing.T) {
	uid := uuid.New()
	cursorTime := time.Now().UTC()
	// only `before`, no `before_id` → must fall back to the offset path (never a half-keyset).
	_, _, keyset := listNotificationsQuery(uid, "", false, &cursorTime, nil, 20, 0)
	if keyset {
		t.Errorf("keyset must require BOTH before and before_id")
	}
}

func TestListNotificationsQuery_CategoryAndUnreadShiftPlaceholders(t *testing.T) {
	uid := uuid.New()
	cursorTime := time.Now().UTC()
	cursorID := uuid.New()
	q, args, _ := listNotificationsQuery(uid, "assistant", true, &cursorTime, &cursorID, 10, 0)
	if !strings.Contains(q, "category = $2") {
		t.Errorf("category filter should bind $2: %s", q)
	}
	if !strings.Contains(q, "read_at IS NULL") {
		t.Errorf("unread filter missing: %s", q)
	}
	// With category consuming $2, the keyset tuple shifts to $3,$4.
	if !strings.Contains(q, "(created_at, id) < ($3, $4)") {
		t.Errorf("keyset predicate should shift past the category placeholder: %s", q)
	}
	// args: uid, "assistant", before, beforeID, limit
	if len(args) != 5 || args[1] != "assistant" {
		t.Errorf("unexpected args: %v", args)
	}
}
