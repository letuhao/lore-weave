package tasks

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/minio/minio-go/v7"
	amqp "github.com/rabbitmq/amqp091-go"
	"github.com/redis/go-redis/v9"

	"github.com/loreweave/worker-infra/internal/config"
)

type ImportProcessor struct {
	Cfg     *config.Config
	Redis   *redis.Client
	BookDB  *pgxpool.Pool
	Minio   *minio.Client

	amqpCh *amqp.Channel
}

func (t *ImportProcessor) Name() string { return "import-processor" }

const (
	importStream   = "loreweave:events:chapter" // outbox-relay publishes here with event_type=import.requested
	importGroup    = "import-processor"
	importConsumer = "worker-1"
)

func (t *ImportProcessor) Run(ctx context.Context) error {
	slog.Info("import-processor starting")

	// Connect to RabbitMQ for WebSocket push events
	if t.Cfg.RabbitMQURL != "" {
		conn, err := amqp.Dial(t.Cfg.RabbitMQURL)
		if err != nil {
			slog.Warn("import-processor: AMQP connect failed (WS push disabled)", "error", err)
		} else {
			ch, err := conn.Channel()
			if err != nil {
				slog.Warn("import-processor: AMQP channel failed", "error", err)
			} else {
				_ = ch.ExchangeDeclare("loreweave.events", "topic", true, false, false, false, nil)
				t.amqpCh = ch
				slog.Info("import-processor: AMQP connected for WS push")
			}
		}
	}

	// Create consumer group (ignore error if already exists)
	t.Redis.XGroupCreateMkStream(ctx, importStream, importGroup, "0").Err()

	for {
		select {
		case <-ctx.Done():
			slog.Info("import-processor shutting down")
			return nil
		default:
		}

		results, err := t.Redis.XReadGroup(ctx, &redis.XReadGroupArgs{
			Group:    importGroup,
			Consumer: importConsumer,
			Streams:  []string{importStream, ">"},
			Count:    1,
			Block:    5 * time.Second,
		}).Result()
		if err != nil {
			if err == redis.Nil || strings.Contains(err.Error(), "context") {
				continue
			}
			slog.Error("import-processor XREADGROUP", "error", err)
			time.Sleep(2 * time.Second)
			continue
		}

		for _, stream := range results {
			for _, msg := range stream.Messages {
				eventType, _ := msg.Values["event_type"].(string)
				if eventType != "import.requested" {
					t.Redis.XAck(ctx, importStream, importGroup, msg.ID)
					continue
				}

				payloadStr, _ := msg.Values["payload"].(string)
				var payload struct {
					JobID            string `json:"job_id"`
					BookID           string `json:"book_id"`
					UserID           string `json:"user_id"`
					FileFormat       string `json:"file_format"`
					FileStorageKey   string `json:"file_storage_key"`
					OriginalLanguage string `json:"original_language"`
				}
				if err := json.Unmarshal([]byte(payloadStr), &payload); err != nil {
					slog.Error("import-processor bad payload", "error", err, "msg_id", msg.ID)
					t.Redis.XAck(ctx, importStream, importGroup, msg.ID)
					continue
				}

				slog.Info("import-processor processing", "job_id", payload.JobID, "format", payload.FileFormat)
				t.updateJobStatus(ctx, payload.JobID, "processing", 0, nil)
				t.publishWSEvent(payload.UserID, payload.JobID, "processing", 0, nil)

				chaptersCreated, procErr := t.processImport(ctx, payload)
				if procErr != nil {
					slog.Error("import-processor failed", "job_id", payload.JobID, "error", procErr)
					errMsg := procErr.Error()
					t.updateJobStatus(ctx, payload.JobID, "failed", chaptersCreated, &errMsg)
					t.publishWSEvent(payload.UserID, payload.JobID, "failed", chaptersCreated, &errMsg)
				} else {
					slog.Info("import-processor completed", "job_id", payload.JobID, "chapters", chaptersCreated)
					t.updateJobStatus(ctx, payload.JobID, "completed", chaptersCreated, nil)
					t.publishWSEvent(payload.UserID, payload.JobID, "completed", chaptersCreated, nil)
				}

				t.Redis.XAck(ctx, importStream, importGroup, msg.ID)
			}
		}
	}
}

func (t *ImportProcessor) processImport(ctx context.Context, payload struct {
	JobID            string `json:"job_id"`
	BookID           string `json:"book_id"`
	UserID           string `json:"user_id"`
	FileFormat       string `json:"file_format"`
	FileStorageKey   string `json:"file_storage_key"`
	OriginalLanguage string `json:"original_language"`
}) (int, error) {
	// 1. Download file from MinIO
	obj, err := t.Minio.GetObject(ctx, t.Cfg.MinioBucket, payload.FileStorageKey, minio.GetObjectOptions{})
	if err != nil {
		return 0, fmt.Errorf("minio get: %w", err)
	}
	defer obj.Close()
	fileData, err := io.ReadAll(obj)
	if err != nil {
		return 0, fmt.Errorf("minio read: %w", err)
	}

	// 2. Convert via pandoc-server
	html, err := t.callPandoc(ctx, fileData, payload.FileFormat)
	if err != nil {
		return 0, fmt.Errorf("pandoc: %w", err)
	}

	// 3. Split into chapters and convert HTML→Tiptap JSON
	chapters := splitChapters(html, payload.FileFormat)

	lang := payload.OriginalLanguage
	if lang == "" {
		lang = "auto"
	}

	// 4. Create chapters in book DB
	count := 0
	for i, ch := range chapters {
		tiptapJSON := htmlToTiptapJSON(ch.Content)

		// Extract embedded images (data: URIs) → upload to MinIO → replace src
		imgPrefix := fmt.Sprintf("chapters/%s/import-%s-%d", payload.BookID, payload.JobID, i)
		tiptapJSON, imgCount := extractAndUploadImages(ctx, tiptapJSON, t.Minio, t.Cfg.MinioBucket, imgPrefix, "")
		if imgCount > 0 {
			slog.Info("import: extracted images", "chapter", i, "count", imgCount)
		}

		sortOrder := i + 1
		// Auto-assign sort_order after existing chapters
		var maxSort int
		t.BookDB.QueryRow(ctx,
			`SELECT COALESCE(MAX(sort_order),0) FROM chapters WHERE book_id=$1 AND lifecycle_state='active'`,
			payload.BookID).Scan(&maxSort)
		sortOrder = maxSort + 1

		tx, err := t.BookDB.Begin(ctx)
		if err != nil {
			return count, fmt.Errorf("db begin: %w", err)
		}

		var chapterID string
		err = tx.QueryRow(ctx, `
INSERT INTO chapters(book_id, title, original_filename, original_language, content_type, byte_size, sort_order, storage_key, lifecycle_state, draft_updated_at, updated_at)
VALUES($1, $2, $3, $4, 'application/json', $5, $6, $7, 'active', now(), now())
RETURNING id
`, payload.BookID, nullIfEmpty(ch.Title), ch.Filename, lang,
			len(tiptapJSON), sortOrder,
			fmt.Sprintf("chapters/%s/import-%s-%d", payload.BookID, payload.JobID, i),
		).Scan(&chapterID)
		if err != nil {
			tx.Rollback(ctx)
			return count, fmt.Errorf("insert chapter: %w", err)
		}

		_, _ = tx.Exec(ctx,
			`INSERT INTO chapter_drafts(chapter_id, body, draft_format, draft_updated_at, draft_version) VALUES($1, $2, 'json', now(), 1)`,
			chapterID, tiptapJSON)
		_, _ = tx.Exec(ctx,
			`INSERT INTO chapter_revisions(chapter_id, body, body_format, message, author_user_id) VALUES($1, $2, 'json', $3, $4)`,
			chapterID, tiptapJSON, "imported from "+ch.Filename, payload.UserID)
		_, _ = tx.Exec(ctx, `UPDATE chapters SET draft_revision_count=1 WHERE id=$1`, chapterID)

		if err := tx.Commit(ctx); err != nil {
			return count, fmt.Errorf("commit chapter: %w", err)
		}
		count++
	}

	// 5. Clean up import file from MinIO
	_ = t.Minio.RemoveObject(ctx, t.Cfg.MinioBucket, payload.FileStorageKey, minio.RemoveObjectOptions{})

	return count, nil
}

func nullIfEmpty(s string) any {
	if strings.TrimSpace(s) == "" {
		return nil
	}
	return s
}

// callPandoc sends the file to pandoc-server and returns HTML.
func (t *ImportProcessor) callPandoc(ctx context.Context, data []byte, format string) (string, error) {
	pandocFrom := format
	if format == "epub" {
		pandocFrom = "epub"
	}

	reqBody, _ := json.Marshal(map[string]any{
		"from": pandocFrom,
		"to":   "html",
		"text": base64.StdEncoding.EncodeToString(data),
	})

	req, err := http.NewRequestWithContext(ctx, "POST", t.Cfg.PandocURL+"/", bytes.NewReader(reqBody))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/json")

	client := &http.Client{Timeout: 5 * time.Minute}
	resp, err := client.Do(req)
	if err != nil {
		return "", fmt.Errorf("pandoc request: %w", err)
	}
	defer resp.Body.Close()

	respData, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", fmt.Errorf("pandoc read response: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("pandoc status %d: %s", resp.StatusCode, string(respData))
	}

	// pandoc-server returns JSON with "output" field
	var result struct {
		Output   string `json:"output"`
		Messages []any  `json:"messages"`
	}
	if err := json.Unmarshal(respData, &result); err != nil {
		// Might be plain text response
		return string(respData), nil
	}

	return result.Output, nil
}

// publishWSEvent publishes an import status event to RabbitMQ for WebSocket push.
func (t *ImportProcessor) publishWSEvent(userID, jobID, status string, chaptersCreated int, errMsg *string) {
	if t.amqpCh == nil {
		return
	}
	event := map[string]any{
		"type":             "import.status",
		"user_id":          userID,
		"job_id":           jobID,
		"status":           status,
		"chapters_created": chaptersCreated,
	}
	if errMsg != nil {
		event["error"] = *errMsg
	}
	body, _ := json.Marshal(event)
	routingKey := "user." + userID
	err := t.amqpCh.Publish("loreweave.events", routingKey, false, false, amqp.Publishing{
		ContentType: "application/json",
		Body:        body,
	})
	if err != nil {
		slog.Warn("import-processor: AMQP publish failed", "error", err)
	}
}

// updateJobStatus calls book-service internal API to update import job status.
func (t *ImportProcessor) updateJobStatus(ctx context.Context, jobID string, status string, chaptersCreated int, errMsg *string) {
	body, _ := json.Marshal(map[string]any{
		"status":           status,
		"chapters_created": chaptersCreated,
		"error":            errMsg,
	})

	url := fmt.Sprintf("%s/internal/imports/%s", t.Cfg.BookServiceURL, jobID)
	req, err := http.NewRequestWithContext(ctx, "PATCH", url, bytes.NewReader(body))
	if err != nil {
		slog.Error("import-processor update status request", "error", err)
		return
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Internal-Token", t.Cfg.InternalToken)

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		slog.Error("import-processor update status", "error", err)
		return
	}
	resp.Body.Close()
}
