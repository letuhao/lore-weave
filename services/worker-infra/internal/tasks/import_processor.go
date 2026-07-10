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

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/minio/minio-go/v7"
	amqp "github.com/rabbitmq/amqp091-go"
	"github.com/redis/go-redis/v9"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"

	"github.com/loreweave/observability"
	"github.com/loreweave/worker-infra/internal/config"
)

// amqpPublisher is the subset of *amqp.Channel that publishWSEvent uses.
// Narrowing the field to this interface lets a test inject a fake publisher
// and assert the Phase 6c traceparent injection without a live broker.
type amqpPublisher interface {
	Publish(exchange, key string, mandatory, immediate bool, msg amqp.Publishing) error
}

type ImportProcessor struct {
	Cfg     *config.Config
	Redis   *redis.Client
	BookDB  *pgxpool.Pool
	Minio   *minio.Client

	amqpCh      amqpPublisher
	parseClient *ParseClient // P1 — initialised lazily in Run()
}

func (t *ImportProcessor) Name() string { return "import-processor" }

const (
	importStream   = "loreweave:events:chapter" // outbox-relay publishes here with event_type=import.requested
	importGroup    = "import-processor"
	importConsumer = "worker-1"
)

func (t *ImportProcessor) Run(ctx context.Context) error {
	slog.Info("import-processor starting")

	// P1 — initialise the structural-decomposer client.
	if t.parseClient == nil {
		t.parseClient = NewParseClient(t.Cfg.KnowledgeServiceURL, t.Cfg.InternalToken)
	}

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
				var payload importRequestedPayload
				if err := json.Unmarshal([]byte(payloadStr), &payload); err != nil {
					slog.Error("import-processor bad payload", "error", err, "msg_id", msg.ID)
					t.Redis.XAck(ctx, importStream, importGroup, msg.ID)
					continue
				}

				slog.Info("import-processor processing", "job_id", payload.JobID, "format", payload.FileFormat)
				t.updateJobStatus(ctx, payload.JobID, "processing", 0, nil)
				t.publishWSEvent(ctx, payload.UserID, payload.JobID, "processing", 0, nil)

				var chaptersCreated int
				var procErr error
				if payload.FileFormat == "pdf" {
					// docs/specs/2026-07-06-pdf-book-import.md — dedicated
					// per-chunk pipeline (L6): skips pandoc, loops chunks
					// against knowledge-service /internal/parse/pdf-chunk
					// instead of one whole-book /internal/parse call.
					chaptersCreated, procErr = t.processPdfImport(ctx, payload)
				} else {
					chaptersCreated, procErr = t.processImport(ctx, payload)
				}
				if procErr != nil {
					slog.Error("import-processor failed", "job_id", payload.JobID, "error", procErr)
					errMsg := procErr.Error()
					t.updateJobStatus(ctx, payload.JobID, "failed", chaptersCreated, &errMsg)
					t.publishWSEvent(ctx, payload.UserID, payload.JobID, "failed", chaptersCreated, &errMsg)
				} else {
					slog.Info("import-processor completed", "job_id", payload.JobID, "chapters", chaptersCreated)
					t.updateJobStatus(ctx, payload.JobID, "completed", chaptersCreated, nil)
					t.publishWSEvent(ctx, payload.UserID, payload.JobID, "completed", chaptersCreated, nil)
				}

				t.Redis.XAck(ctx, importStream, importGroup, msg.ID)
			}
		}
	}
}

// importRequestedPayload mirrors book-service's import.requested outbox
// event payload (import.go's outboxPayload map). The pdf-specific fields
// are only populated when file_format="pdf" (docs/specs/2026-07-06-pdf-book-import.md).
type importRequestedPayload struct {
	JobID            string `json:"job_id"`
	BookID           string `json:"book_id"`
	UserID           string `json:"user_id"`
	FileFormat       string `json:"file_format"`
	FileStorageKey   string `json:"file_storage_key"`
	OriginalLanguage string `json:"original_language"`

	PagesPerChunk     int    `json:"pages_per_chunk"`
	CaptionImages     bool   `json:"caption_images"`
	VisionModelSource string `json:"vision_model_source"`
	VisionModelRef    string `json:"vision_model_ref"`
}

func (t *ImportProcessor) processImport(ctx context.Context, payload importRequestedPayload) (int, error) {
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

	// 3. P1 — structural decomposition via knowledge-service /internal/parse
	// (replaces the naive splitChapters helper that handled <h1>/<h2> only
	// and degraded DOCX to a single chapter).
	lang := payload.OriginalLanguage
	if lang == "" {
		lang = "auto"
	}
	tree, err := t.parseClient.Call(ctx, "html", html, lang, "")
	if err != nil {
		return 0, fmt.Errorf("parse: %w", err)
	}

	// 4. Find current max sort_order ONCE — we apply chapterGlobalSort
	// (book-global counter, R-SELF-3) across parts.
	var maxSort int
	_ = t.BookDB.QueryRow(ctx,
		`SELECT COALESCE(MAX(sort_order),0) FROM chapters WHERE book_id=$1 AND lifecycle_state='active'`,
		payload.BookID).Scan(&maxSort)
	chapterGlobalSort := maxSort + 1

	// L3 fix: multi-part filename pattern when len(parts) > 1.
	multiPart := len(tree.Parts) > 1

	// 5. Write parts + chapters + scenes per spec D7 3-level Tx scoping.
	count := 0
	for partIdx, part := range tree.Parts {
		// (a) Per-part Tx: insert ONE parts row.
		partID, err := t.insertPart(ctx, payload.BookID, partIdx+1, part.Title, part.Path)
		if err != nil {
			return count, fmt.Errorf("insert part: %w", err)
		}

		for chIdxInPart, ch := range part.Chapters {
			tiptapJSON := htmlToTiptapJSON(ch.HTML)

			// Extract embedded images (data: URIs) → upload to MinIO → replace src.
			// Use chapterGlobalSort-1 as the per-job index (preserves existing pattern).
			imgPrefix := fmt.Sprintf(
				"chapters/%s/import-%s-%d",
				payload.BookID,
				payload.JobID,
				chapterGlobalSort-1,
			)
			tiptapJSON, imgCount := extractAndUploadImages(
				ctx, tiptapJSON, t.Minio, t.Cfg.MinioBucket, imgPrefix, "",
			)
			if imgCount > 0 {
				slog.Info("import: extracted images",
					"chapter", chapterGlobalSort, "count", imgCount)
			}

			// L3 — synthesised original_filename pattern. C1 fix: per-part
			// indexing for BOTH filename and storage_key in multi-part mode
			// (consistent debug scheme; uniqueness preserved by the inserted
			// import-job UUID + per-part counter).
			var origFilename, storageKey string
			if multiPart {
				origFilename = fmt.Sprintf("import-pt%02d-ch%03d.epub", partIdx+1, chIdxInPart+1)
				storageKey = fmt.Sprintf(
					"chapters/%s/import-%s-pt%d-ch%d",
					payload.BookID, payload.JobID, partIdx+1, chIdxInPart+1,
				)
			} else {
				origFilename = fmt.Sprintf("import-ch%03d.epub", chapterGlobalSort)
				storageKey = fmt.Sprintf(
					"chapters/%s/import-%s-%d",
					payload.BookID, payload.JobID, chapterGlobalSort-1,
				)
			}

			// (b) Per-chapter Tx: chapter + draft + revision + scenes.
			tx, err := t.BookDB.Begin(ctx)
			if err != nil {
				return count, fmt.Errorf("db begin: %w", err)
			}

			var chapterID string
			chapterTitle := ""
			if ch.Title != nil {
				chapterTitle = *ch.Title
			}
			err = tx.QueryRow(ctx, `
INSERT INTO chapters(book_id, title, original_filename, original_language, content_type, byte_size, sort_order, storage_key, lifecycle_state, draft_updated_at, updated_at, part_id, structural_path)
VALUES($1, $2, $3, $4, 'application/json', $5, $6, $7, 'active', now(), now(), $8, $9)
RETURNING id
`, payload.BookID, nullIfEmpty(chapterTitle), origFilename, lang,
				len(tiptapJSON), chapterGlobalSort, storageKey,
				partID, ch.Path,
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
				chapterID, tiptapJSON, "imported from "+origFilename, payload.UserID)
			_, _ = tx.Exec(ctx, `UPDATE chapters SET draft_revision_count=1 WHERE id=$1`, chapterID)

			// Insert scenes for this chapter.
			for _, sc := range ch.Scenes {
				// 22-A5: set book_id (SC1 direct scope) AND source_scene_id (the SC7
				// `data-scene-id` anchor back-link, when the parser recovered one) at
				// INSERT — the same window-closing write the .txt path (parse.go) makes.
				_, err := tx.Exec(ctx,
					`INSERT INTO scenes(chapter_id, book_id, sort_order, path, leaf_text, content_hash, source_scene_id, parse_version) VALUES($1, $2, $3, $4, $5, $6, $7, 1)`,
					chapterID, payload.BookID, sc.SortOrder, sc.Path, sc.LeafText, sc.ContentHash, sceneSourceSceneIDArg(sc.SourceSceneID))
				if err != nil {
					tx.Rollback(ctx)
					return count, fmt.Errorf("insert scene: %w", err)
				}
			}

			if err := tx.Commit(ctx); err != nil {
				return count, fmt.Errorf("commit chapter: %w", err)
			}
			count++
			chapterGlobalSort++
		}
	}

	// 6. Clean up import file from MinIO.
	_ = t.Minio.RemoveObject(ctx, t.Cfg.MinioBucket, payload.FileStorageKey, minio.RemoveObjectOptions{})

	return count, nil
}

// insertPart writes a single parts row in its own short transaction
// (per spec D7 (a) per-part Tx prelude).
func (t *ImportProcessor) insertPart(
	ctx context.Context,
	bookID string,
	sortOrder int,
	title *string,
	path string,
) (string, error) {
	var titleArg any
	if title != nil && strings.TrimSpace(*title) != "" {
		titleArg = *title
	}
	var partID string
	err := t.BookDB.QueryRow(ctx, `
INSERT INTO parts(book_id, sort_order, title, path)
VALUES($1, $2, $3, $4)
ON CONFLICT (book_id, sort_order) DO UPDATE SET title = EXCLUDED.title, path = EXCLUDED.path, updated_at = now()
RETURNING id
`, bookID, sortOrder, titleArg, path).Scan(&partID)
	if err != nil {
		return "", fmt.Errorf("insert part: %w", err)
	}
	return partID, nil
}

func nullIfEmpty(s string) any {
	if strings.TrimSpace(s) == "" {
		return nil
	}
	return s
}

// sceneSourceSceneIDArg maps the parser's optional `data-scene-id` anchor (22-A5/
// SC7) to the scenes.source_scene_id INSERT bind: a valid UUID → that UUID, absent
// or malformed → NULL. A malformed anchor is deliberately NOT fatal — the scene
// still gets its index row with a NULL back-link ("anchor lost", the F6 re-anchor
// path), never a failed import. Mirrors book-service parse.go's helper.
func sceneSourceSceneIDArg(raw *string) any {
	if raw == nil {
		return nil
	}
	id, err := uuid.Parse(strings.TrimSpace(*raw))
	if err != nil {
		return nil
	}
	return id
}

// callPandoc sends the file to pandoc-server and returns HTML.
func (t *ImportProcessor) callPandoc(ctx context.Context, data []byte, format string) (string, error) {
	pandocFrom := format
	if format == "epub" {
		pandocFrom = "epub"
	}

	reqBody, _ := json.Marshal(map[string]any{
		"from":            pandocFrom,
		"to":              "html",
		"text":            base64.StdEncoding.EncodeToString(data),
		"embed-resources": true,
		"standalone":      true,
	})

	req, err := http.NewRequestWithContext(ctx, "POST", t.Cfg.PandocURL+"/", bytes.NewReader(reqBody))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/json")

	client := &http.Client{Timeout: 5 * time.Minute, Transport: observability.HTTPTransport(nil)}
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
//
// Phase 6c — wraps the publish in a PRODUCER span and injects a W3C
// traceparent into the message headers so a downstream consumer can continue
// the trace. ctx carries no span until D-PHASE6C-REDIS-STREAM instruments the
// import-job consume, so today this span is a fresh root.
func (t *ImportProcessor) publishWSEvent(ctx context.Context, userID, jobID, status string, chaptersCreated int, errMsg *string) {
	if t.amqpCh == nil {
		return
	}
	ctx, span := observability.Tracer("import-processor").Start(ctx, "import.ws-event",
		trace.WithSpanKind(trace.SpanKindProducer),
		trace.WithAttributes(
			attribute.String("messaging.system", "rabbitmq"),
			attribute.String("messaging.destination.name", "loreweave.events"),
			attribute.String("job.id", jobID),
		))
	defer span.End()

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
	headers := amqp.Table{}
	observability.Inject(ctx, observability.AMQPCarrier(headers))
	err := t.amqpCh.Publish("loreweave.events", routingKey, false, false, amqp.Publishing{
		ContentType: "application/json",
		Headers:     headers,
		Body:        body,
	})
	if err != nil {
		span.RecordError(err)
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

	client := &http.Client{Timeout: 10 * time.Second, Transport: observability.HTTPTransport(nil)}
	resp, err := client.Do(req)
	if err != nil {
		slog.Error("import-processor update status", "error", err)
		return
	}
	resp.Body.Close()
}
