package api

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// structureActivityAction is the small, explicit contract shared by the book
// mutation paths and the activity feed.  These are deliberately notification
// events, not chapter-content events: changing a title or lifecycle must not
// trigger extraction, indexing, or a prose revision.
type structureActivityAction string

const (
	structureActivityRenamed  structureActivityAction = "chapter.renamed"
	structureActivityTrashed  structureActivityAction = "chapter.trashed"
	structureActivityRestored structureActivityAction = "chapter.restored"
	structureActivityDeleted  structureActivityAction = "chapter.deleted"
)

// insertStructureActivityOutbox writes the activity-feed notification in the
// same transaction as the structural mutation.  worker-infra's durable
// notification outbox relay delivers this payload to notification-service and
// deduplicates it by the generated event id.
func insertStructureActivityOutbox(ctx context.Context, tx pgx.Tx, actorID, bookID, chapterID uuid.UUID, action structureActivityAction, previousTitle, title string) error {
	eventID := uuid.New()
	messageKey := "notif.structure." + string(action)[len("chapter."):]
	activityTitle, body := structureActivityCopy(action, previousTitle, title)
	payload := map[string]any{
		"user_id":     actorID.String(),
		"category":    "system",
		"title":       activityTitle,
		"body":        body,
		"message_key": messageKey,
		"message_params": map[string]any{
			"book_id":        bookID.String(),
			"chapter_id":     chapterID.String(),
			"action":         string(action),
			"previous_title": previousTitle,
			"title":          title,
		},
		"metadata": map[string]any{
			"book_id":        bookID.String(),
			"chapter_id":     chapterID.String(),
			"action":         string(action),
			"previous_title": previousTitle,
			"title":          title,
			"event_id":       eventID.String(),
		},
		"dedup_key": "chapter_structure:" + eventID.String(),
	}
	payloadJSON, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("structure activity marshal: %w", err)
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO outbox_events (event_type, aggregate_type, aggregate_id, payload)
		VALUES ($1, 'notification', $2, $3)
	`, "notification.requested", eventID, payloadJSON); err != nil {
		return fmt.Errorf("structure activity outbox: %w", err)
	}
	return nil
}

func structureActivityCopy(action structureActivityAction, previousTitle, title string) (string, string) {
	switch action {
	case structureActivityRenamed:
		if previousTitle == "" {
			return "Chapter renamed", fmt.Sprintf("Chapter renamed to %q", title)
		}
		return "Chapter renamed", fmt.Sprintf("Chapter %q renamed to %q", previousTitle, title)
	case structureActivityTrashed:
		return "Chapter moved to trash", fmt.Sprintf("Chapter %q moved to trash", title)
	case structureActivityRestored:
		return "Chapter restored", fmt.Sprintf("Chapter %q restored", title)
	case structureActivityDeleted:
		return "Chapter deleted", fmt.Sprintf("Chapter %q permanently deleted", title)
	default:
		return "Book structure changed", "A chapter in your book changed."
	}
}
