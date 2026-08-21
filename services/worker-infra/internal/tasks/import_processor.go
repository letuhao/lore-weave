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
	"os"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/minio/minio-go/v7"
	amqp "github.com/rabbitmq/amqp091-go"
	"github.com/redis/go-redis/v9"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"

	"github.com/loreweave/epubimport"
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
	Cfg    *config.Config
	Redis  *redis.Client
	BookDB *pgxpool.Pool
	Minio  *minio.Client

	amqpCh            amqpPublisher
	parseClient       *ParseClient       // P1 — initialised lazily in Run()
	materializeClient *MaterializeClient // 26 IX-12 — initialised lazily in Run()
}

func (t *ImportProcessor) Name() string { return "import-processor" }

const (
	importStream   = "loreweave:events:chapter" // outbox-relay publishes here with event_type=import.requested
	importGroup    = "import-processor"
	importConsumer = "worker-1"

	// A claimed message represents a whole import job, so it is deliberately
	// longer than the reference 500-chapter import target. A restarted worker
	// reclaims only genuinely stale deliveries; concurrent healthy workers do
	// not steal one another's in-flight job.
	importPendingClaimIdle  = 15 * time.Minute
	importPendingClaimCount = 4
)

func (t *ImportProcessor) Run(ctx context.Context) error {
	slog.Info("import-processor starting")

	// P1 — initialise the structural-decomposer client.
	if t.parseClient == nil {
		t.parseClient = NewParseClient(t.Cfg.KnowledgeServiceURL, t.Cfg.InternalToken)
	}
	// 26 IX-12 — the scene-decompile / back-link-write client.
	if t.materializeClient == nil {
		t.materializeClient = NewMaterializeClient(t.Cfg.CompositionServiceURL, t.Cfg.InternalToken)
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

	// Create consumer group (ignore BUSYGROUP when another replica got there
	// first). Each process gets its own consumer name so Redis can identify
	// stale PENDING ownership after a restart.
	if err := t.Redis.XGroupCreateMkStream(ctx, importStream, importGroup, "0").Err(); err != nil && !strings.Contains(err.Error(), "BUSYGROUP") {
		return fmt.Errorf("create import consumer group: %w", err)
	}
	consumer := importConsumerID()
	pendingClaimStart := "0-0"

	for {
		select {
		case <-ctx.Done():
			slog.Info("import-processor shutting down")
			return nil
		default:
		}

		messages, nextStart, claimErr := t.Redis.XAutoClaim(ctx, &redis.XAutoClaimArgs{
			Stream: importStream, Group: importGroup, Consumer: consumer,
			MinIdle: importPendingClaimIdle, Start: pendingClaimStart, Count: importPendingClaimCount,
		}).Result()
		if claimErr != nil && claimErr != redis.Nil {
			slog.Warn("import-processor XAUTOCLAIM", "error", claimErr)
			messages = nil
		} else if nextStart != "" {
			pendingClaimStart = nextStart
		}
		if len(messages) == 0 {
			results, err := t.Redis.XReadGroup(ctx, &redis.XReadGroupArgs{
				Group: importGroup, Consumer: consumer, Streams: []string{importStream, ">"},
				Count: 1, Block: 5 * time.Second,
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
				messages = append(messages, stream.Messages...)
			}
		}

		for _, msg := range messages {
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
			if payload.PipelineVersion == epubImportPipelineVersion {
				if err := t.processEPUBV2(ctx, payload); err != nil {
					slog.Error("epub v2 staging failed", "job_id", payload.JobID, "error", err)
					// The item status is owned by Book Service. Do not overwrite it
					// through the legacy job endpoint or acknowledge a retryable
					// transport failure as if it had completed.
					continue
				}
				t.Redis.XAck(ctx, importStream, importGroup, msg.ID)
				continue
			}
			// Serialize redeliveries for one job and skip already completed jobs.
			jobLock, locked, lockErr := t.acquireImportJobLock(ctx, payload.JobID)
			if lockErr != nil {
				continue
			}
			if !locked {
				t.Redis.XAck(ctx, importStream, importGroup, msg.ID)
				continue
			}
			if t.importJobCompleted(ctx, payload.JobID) {
				t.releaseImportJobLock(ctx, jobLock, payload.JobID)
				t.Redis.XAck(ctx, importStream, importGroup, msg.ID)
				continue
			}
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

			t.releaseImportJobLock(ctx, jobLock, payload.JobID)
			t.Redis.XAck(ctx, importStream, importGroup, msg.ID)
		}
	}
}

func importConsumerID() string {
	hostname, err := os.Hostname()
	if err != nil {
		hostname = ""
	}
	return importConsumerIDForHostname(hostname)
}

func importConsumerIDForHostname(hostname string) string {
	if strings.TrimSpace(hostname) == "" {
		return importConsumer
	}
	return importConsumer + "-" + strings.ReplaceAll(strings.TrimSpace(hostname), " ", "-")
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

	PagesPerChunk          int      `json:"pages_per_chunk"`
	CaptionImages          bool     `json:"caption_images"`
	VisionModelSource      string   `json:"vision_model_source"`
	VisionModelRef         string   `json:"vision_model_ref"`
	CreateBookFromMetadata bool     `json:"create_book_from_metadata"`
	SourceID               string   `json:"source_id"`
	PipelineVersion        string   `json:"pipeline_version"`
	TargetMode             string   `json:"target_mode"`
	LoreGenres             []string `json:"lore_genres"`
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

	// 2. Convert to HTML. EPUB navigation nodes are parsed independently: their
	// boundaries are authoritative and must never be reconstructed from headings.
	var html string
	var tree *StructuralTree
	var fb2 *fb2Document
	if payload.FileFormat == "epub" {
		epubChapters, epubErr := extractEPUBChapters(fileData)
		if epubErr != nil {
			return 0, fmt.Errorf("epub structure: %w", epubErr)
		}
		lang := payload.OriginalLanguage
		if lang == "" {
			lang = "auto"
		}
		tree = &StructuralTree{SourceFormat: "html", WalkerPath: "epub-navigation"}
		for i, ch := range epubChapters {
			sanitized, _, sanitizeErr := epubimport.SanitizeHTML(ch.HTML)
			if sanitizeErr != nil {
				return 0, fmt.Errorf("sanitize EPUB chapter %q: %w", ch.SourceKey, sanitizeErr)
			}
			chapterTree, parseErr := t.parseClient.CallChapter(ctx, sanitized, lang, ch.Title, ch.SourceKey)
			if parseErr != nil {
				return 0, fmt.Errorf("parse EPUB chapter %q: %w", ch.SourceKey, parseErr)
			}
			if len(chapterTree.Parts) != 1 || len(chapterTree.Parts[0].Chapters) != 1 {
				return 0, fmt.Errorf("parse EPUB chapter %q: parser returned invalid chapter count", ch.SourceKey)
			}
			parsed := chapterTree.Parts[0].Chapters[0]
			parsed.Path = fmt.Sprintf("book/epub-chapter-%d", i+1)
			tree.Parts = append(tree.Parts, Part{
				SortOrder: i + 1,
				Path:      fmt.Sprintf("book/epub-part-%d", i+1),
				Chapters:  []ParsedChapter{parsed},
			})
		}
	} else if payload.FileFormat == "fb2" {
		fb2, err = extractFB2Document(fileData)
		if err != nil {
			return 0, err
		}
		html = fb2.HTML
	} else {
		html, err = t.callPandoc(ctx, fileData, payload.FileFormat)
		if err != nil {
			return 0, fmt.Errorf("pandoc: %w", err)
		}
	}

	// 3. P1 — structural decomposition via knowledge-service /internal/parse
	// (replaces the naive splitChapters helper that handled <h1>/<h2> only
	// and degraded DOCX to a single chapter).
	lang := payload.OriginalLanguage
	if lang == "" {
		lang = "auto"
	}
	if tree == nil {
		tree, err = t.parseClient.Call(ctx, "html", html, lang, "")
		if err != nil {
			return 0, fmt.Errorf("parse: %w", err)
		}
	}
	// Metadata is durable source provenance, not a post-processing decoration.
	// Persist it before the independently committed chapter loop so a later
	// partial chapter failure does not discard the title, annotation, or cover
	// that identifies the newly created book.
	if fb2 != nil {
		if err := t.persistFB2Metadata(ctx, payload, fb2); err != nil {
			return 0, err
		}
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

	// 5. Write chapters + scenes. Manuscript parts were moved from book-service
	// into composition (C-merge/C4); imported chapters start flat and can be
	// grouped later by the composition structure tools.
	count := 0
	for partIdx, part := range tree.Parts {
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
				origFilename = fmt.Sprintf("import-pt%02d-ch%03d.%s", partIdx+1, chIdxInPart+1, importSourceExtension(payload.FileFormat))
				storageKey = fmt.Sprintf(
					"chapters/%s/import-%s-pt%d-ch%d",
					payload.BookID, payload.JobID, partIdx+1, chIdxInPart+1,
				)
			} else {
				origFilename = fmt.Sprintf("import-ch%03d.%s", chapterGlobalSort, importSourceExtension(payload.FileFormat))
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
INSERT INTO chapters(book_id, title, original_filename, original_language, content_type, byte_size, sort_order, storage_key, lifecycle_state, draft_updated_at, updated_at, structural_path)
VALUES($1, $2, $3, $4, 'application/json', $5, $6, $7, 'active', now(), now(), $8)
RETURNING id
`, payload.BookID, nullIfEmpty(chapterTitle), origFilename, lang,
				len(tiptapJSON), chapterGlobalSort, storageKey,
				ch.Path,
			).Scan(&chapterID)
			if err != nil {
				tx.Rollback(ctx)
				return count, fmt.Errorf("insert chapter: %w", err)
			}

			_, _ = tx.Exec(ctx,
				`INSERT INTO chapter_drafts(chapter_id, body, draft_format, draft_updated_at, draft_version) VALUES($1, $2, 'json', now(), 1)`,
				chapterID, tiptapJSON)
			// 26 IX-1 corollary: the epub/docx worker importer gains the sync .txt
			// path's auto-publish so every import path births index rows that parse
			// the pinned PUBLISHED revision (F1: this importer used to leave chapters
			// at 'draft'). Capture the import revision id (error-checked — it is what
			// we pin) and mark the index fresh (last_parsed_revision_id=importRevID),
			// since the scenes inserted below ARE that revision's parse. Born
			// published+fresh ⇒ never needlessly re-swept.
			var importRevID string
			if err := tx.QueryRow(ctx,
				`INSERT INTO chapter_revisions(chapter_id, body, body_format, message, author_user_id) VALUES($1, $2, 'json', $3, $4) RETURNING id`,
				chapterID, tiptapJSON, "imported from "+origFilename, payload.UserID).Scan(&importRevID); err != nil {
				tx.Rollback(ctx)
				return count, fmt.Errorf("insert revision: %w", err)
			}
			if _, err := tx.Exec(ctx,
				// WS-0.3 (spec §3.2): worker-infra writes book-service's `chapters` table
				// DIRECTLY — a second service in the blast radius. It must set the KG pointer
				// too, or every book imported through the async worker becomes invisible to
				// the re-keyed reparse sweeper and never enters the knowledge graph.
				// A freshly-imported chapter is never kg_exclude'd (column defaults false).
				`UPDATE chapters SET draft_revision_count=1, editorial_status='published', published_revision_id=$2, kg_indexed_revision_id=$2, last_parsed_revision_id=$2 WHERE id=$1`,
				chapterID, importRevID); err != nil {
				tx.Rollback(ctx)
				return count, fmt.Errorf("publish imported chapter: %w", err)
			}

			// Insert scenes for this chapter.
			anyLinked := false
			for _, sc := range ch.Scenes {
				// 22-A5: set book_id (SC1 direct scope) AND source_scene_id (the SC7
				// `data-scene-id` anchor back-link, when the parser recovered one) at
				// INSERT — the same window-closing write the .txt path (parse.go) makes.
				ssid := sceneSourceSceneIDArg(sc.SourceSceneID)
				_, err := tx.Exec(ctx,
					`INSERT INTO scenes(chapter_id, book_id, sort_order, path, leaf_text, content_hash, source_scene_id, parse_version) VALUES($1, $2, $3, $4, $5, $6, $7, 1)`,
					chapterID, payload.BookID, sc.SortOrder, sc.Path, sc.LeafText, sc.ContentHash, ssid)
				if err != nil {
					tx.Rollback(ctx)
					return count, fmt.Errorf("insert scene: %w", err)
				}
				if ssid != nil {
					anyLinked = true
				}
			}

			// SC11-amendment Phase 0 — WRITER #3. A RE-IMPORT of an exported book arrives with its
			// anchors intact, so these scenes are born linked — and the IX-12 write-back below will
			// never see them (it only fills NULLs). If this stayed silent, the round-trip case would
			// render as an entirely unwritten book. Same tx as the INSERTs (INV-O12).
			if anyLinked {
				if err := emitScenesLinkedTx(ctx, tx, payload.BookID, chapterID); err != nil {
					tx.Rollback(ctx)
					return count, fmt.Errorf("emit scenes_linked: %w", err)
				}
			}

			if err := tx.Commit(ctx); err != nil {
				return count, fmt.Errorf("commit chapter: %w", err)
			}
			count++
			chapterGlobalSort++
		}
	}

	// 5.5 — 26 IX-12 decompile write-back. The book's prose is imported+published; ask
	// composition to decompile it into spec scenes and write the returned back-link map
	// onto scenes.source_scene_id. BEST-EFFORT: the import's primary output (chapters +
	// scenes + prose) is already committed, so a decompile/write-back failure must NOT
	// fail the import — the leaves simply stay "unplanned" (a recoverable state) until the
	// Hub's decompile CTA re-runs. A Work-less book is a graceful no-op (work_resolved=false).
	t.writeBackSceneLinks(ctx, payload.BookID, payload.UserID)

	// 6. Clean up import file from MinIO.
	_ = t.Minio.RemoveObject(ctx, t.Cfg.MinioBucket, payload.FileStorageKey, minio.RemoveObjectOptions{})

	return count, nil
}

func importSourceExtension(format string) string {
	switch format {
	case "markdown":
		return "md"
	case "docx", "epub", "fb2":
		return format
	default:
		return "import"
	}
}

// persistFB2Metadata retains the structured source data for every FB2 job.
// Only create-mode jobs project it onto books and cover assets: an editor who
// imports chapters into an existing book must never have their own metadata
// silently overwritten by an unrelated source file.
func (t *ImportProcessor) persistFB2Metadata(ctx context.Context, payload importRequestedPayload, doc *fb2Document) error {
	metadata, err := json.Marshal(doc.Metadata)
	if err != nil {
		return fmt.Errorf("fb2: marshal metadata: %w", err)
	}
	tx, err := t.BookDB.Begin(ctx)
	if err != nil {
		return fmt.Errorf("fb2: begin metadata transaction: %w", err)
	}
	defer tx.Rollback(ctx)
	if _, err := tx.Exec(ctx, `
INSERT INTO book_import_metadata(import_job_id,book_id,source_format,metadata,applied_to_book)
VALUES($1,$2,'fb2',$3,$4)
ON CONFLICT(import_job_id) DO UPDATE SET metadata=EXCLUDED.metadata, applied_to_book=EXCLUDED.applied_to_book
`, payload.JobID, payload.BookID, metadata, payload.CreateBookFromMetadata); err != nil {
		return fmt.Errorf("fb2: store metadata: %w", err)
	}
	if !payload.CreateBookFromMetadata {
		if err := tx.Commit(ctx); err != nil {
			return fmt.Errorf("fb2: commit metadata: %w", err)
		}
		slog.Info("fb2: retained metadata for existing book", "job_id", payload.JobID, "book_id", payload.BookID)
		return nil
	}
	language := payload.OriginalLanguage
	if language == "" {
		language = doc.Language
	}
	if _, err := tx.Exec(ctx, `UPDATE books SET title=$2,description=$3,original_language=$4,genre_tags=$5,updated_at=now() WHERE id=$1`, payload.BookID, doc.Title, nullIfEmpty(doc.Summary), nullIfEmpty(language), doc.Genres); err != nil {
		return fmt.Errorf("fb2: apply book metadata: %w", err)
	}
	if doc.Cover != nil {
		contentType := http.DetectContentType(doc.Cover.Data)
		if strings.HasPrefix(contentType, "image/") {
			if _, err := tx.Exec(ctx, `
INSERT INTO book_cover_assets(book_id,content_type,byte_size,storage_key,data,updated_at)
VALUES($1,$2,$3,$4,$5,now())
ON CONFLICT(book_id) DO UPDATE SET content_type=EXCLUDED.content_type,byte_size=EXCLUDED.byte_size,storage_key=EXCLUDED.storage_key,data=EXCLUDED.data,updated_at=now()
`, payload.BookID, contentType, len(doc.Cover.Data), fmt.Sprintf("covers/%s", payload.BookID), doc.Cover.Data); err != nil {
				return fmt.Errorf("fb2: store cover: %w", err)
			}
		} else {
			slog.Warn("fb2: skipped cover with non-image signature", "job_id", payload.JobID, "declared_content_type", doc.Cover.ContentType, "detected_content_type", contentType)
		}
	}
	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("fb2: commit metadata: %w", err)
	}
	slog.Info("fb2: applied metadata to created book", "job_id", payload.JobID, "book_id", payload.BookID, "genres", len(doc.Genres), "cover_present", doc.Cover != nil)
	return nil
}

// writeBackSceneLinks runs the 26 IX-12 loop: decompile via composition, then write the
// returned mappings onto scenes.source_scene_id. book-service (this worker's book DB) is
// the sole writer of source_scene_id (SCOPE-2 / DA-8 index-owner role). Only fills a leaf
// whose back-link is still NULL — IX-5 rule 1 (a recovered anchor) WINS over the decompile
// map, so an anchor-derived id set at INSERT is never clobbered. Idempotent: a re-run finds
// the same decompile_key nodes and re-writes the same ids.
func (t *ImportProcessor) writeBackSceneLinks(ctx context.Context, bookID, ownerUserID string) {
	// Self-contained: lazily build the client so a caller that bypassed Run() (or a test)
	// never nil-derefs. No-ops silently if the URL is unset (defense-in-depth).
	if t.materializeClient == nil {
		if t.Cfg == nil || t.Cfg.CompositionServiceURL == "" {
			return
		}
		t.materializeClient = NewMaterializeClient(t.Cfg.CompositionServiceURL, t.Cfg.InternalToken)
	}
	res, err := t.materializeClient.Materialize(ctx, bookID, ownerUserID)
	if err != nil {
		slog.Warn("import: IX-12 decompile failed (leaves stay unplanned; recoverable via Hub)",
			"book", bookID, "err", err)
		return
	}
	if !res.WorkResolved || len(res.Mappings) == 0 {
		slog.Info("import: IX-12 decompile no-op",
			"book", bookID, "work_resolved", res.WorkResolved, "mappings", len(res.Mappings))
		return
	}
	// SC11-amendment Phase 0 — WRITER #3, and the one that emitted NOTHING.
	//
	// This is the write that CREATES the spec back-link for a plain (non-round-tripped) import:
	// the parser recovers no anchor, so `parse.go` inserts every scene with a NULL
	// source_scene_id, and it is this decompile write-back that fills them. Before Phase 0 it
	// fired no event at all — so composition's mirror would never learn the links exist, and a
	// decompiled book would render as ENTIRELY UNWRITTEN. A confident, wrong, whole-book answer.
	//
	// Grouped PER CHAPTER and wrapped in a tx so the UPDATEs and the outbox row commit together
	// (INV-O12). The best-effort, continue-on-error posture is preserved at the CHAPTER level: a
	// chapter that fails is logged and skipped, the rest still land — the write-back has always
	// been recoverable-by-retry, and one bad chapter must not strand the book.
	byChapter := make(map[string][]SceneMapping, len(res.Mappings))
	order := make([]string, 0, len(res.Mappings))
	for _, m := range res.Mappings {
		if _, seen := byChapter[m.ChapterID]; !seen {
			order = append(order, m.ChapterID)
		}
		byChapter[m.ChapterID] = append(byChapter[m.ChapterID], m)
	}

	written, chaptersLinked := 0, 0
	for _, chID := range order {
		n, err := t.linkChapterScenes(ctx, bookID, chID, byChapter[chID])
		if err != nil {
			slog.Warn("import: IX-12 back-link write failed for chapter (partial; recoverable)",
				"book", bookID, "chapter", chID, "err", err)
			continue
		}
		written += n
		if n > 0 {
			chaptersLinked++
		}
	}
	slog.Info("import: IX-12 decompile write-back done",
		"book", bookID, "created", res.Created, "matched", res.Matched,
		"mappings", len(res.Mappings), "linked", written, "chapters_linked", chaptersLinked)
}

// emitScenesLinkedTx writes `chapter.scenes_linked` into book-service's transactional outbox,
// inside the caller's tx (INV-O12: an emit that cannot be written must roll the mutation back).
//
// THE CENSUS THAT WAS WRONG TWICE. `scenes.source_scene_id` is written in FIVE places, not three:
//  1. book-service parse.go        — the .txt import INSERT
//  2. book-service reparse.go      — via FOUR emit sites (publish, kg-index, mcp-publish, sweeper)
//  3. worker-infra import (here)   — the HTML/txt import INSERT      <- emitted NOTHING
//  4. worker-infra import_pdf      — the PDF import INSERT           <- emitted NOTHING
//  5. worker-infra IX-12 write-back— the decompile back-link fill    <- emitted NOTHING
//
// (3) and (4) matter because they set the link from a parser-recovered anchor, and the IX-12
// write-back at (5) only fills NULLs — so a scene that arrives ALREADY ANCHORED is never touched
// by it and, before this, never announced. That is the ROUND-TRIP case: a user exports their book
// and re-imports it, every scene arrives linked, and composition's mirror renders the whole book
// as UNWRITTEN. A confident, wrong, whole-book answer.
func emitScenesLinkedTx(ctx context.Context, tx pgx.Tx, bookID, chapterID string) error {
	payload, err := json.Marshal(map[string]any{"book_id": bookID, "chapter_id": chapterID})
	if err != nil {
		return fmt.Errorf("scenes_linked marshal: %w", err)
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO outbox_events (aggregate_type, aggregate_id, event_type, payload)
		VALUES ('chapter', $1, 'chapter.scenes_linked', $2)
	`, chapterID, payload); err != nil {
		return fmt.Errorf("scenes_linked outbox insert: %w", err)
	}
	return nil
}

// linkChapterScenes writes one chapter's IX-12 back-links and emits `chapter.scenes_linked` in
// the SAME transaction. Returns the number of scenes actually linked (0 ⇒ nothing changed ⇒ NO
// event: a re-run of an already-linked book is a no-op, and a no-op must not fire).
//
// The event carries only {book_id, chapter_id} — composition re-reads and reconciles. Shipping the
// mappings in the payload would let a stale redelivery overwrite newer state; a re-read cannot.
func (t *ImportProcessor) linkChapterScenes(
	ctx context.Context, bookID, chapterID string, ms []SceneMapping,
) (int, error) {
	tx, err := t.BookDB.Begin(ctx)
	if err != nil {
		return 0, fmt.Errorf("begin: %w", err)
	}
	defer tx.Rollback(ctx) // no-op after a successful Commit

	linked := 0
	for _, m := range ms {
		tag, err := tx.Exec(ctx,
			`UPDATE scenes SET source_scene_id=$1
			   WHERE book_id=$2 AND chapter_id=$3 AND sort_order=$4 AND source_scene_id IS NULL`,
			m.OutlineNodeID, bookID, m.ChapterID, m.SortOrder)
		if err != nil {
			return 0, fmt.Errorf("link scene (sort_order=%d): %w", m.SortOrder, err)
		}
		linked += int(tag.RowsAffected())
	}
	if linked == 0 {
		return 0, tx.Commit(ctx) // nothing changed — commit the (empty) tx, emit nothing
	}

	// The emit MUST be able to fail the tx (INV-O12). Swallowing it would leave links that no
	// consumer ever hears about — the projection silently diverges from the truth it mirrors.
	if err := emitScenesLinkedTx(ctx, tx, bookID, chapterID); err != nil {
		return 0, err
	}
	if err := tx.Commit(ctx); err != nil {
		return 0, fmt.Errorf("commit: %w", err)
	}
	return linked, nil
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

// acquireImportJobLock serializes delivery redeliveries for one import job while retaining
// the same pooled connection. PostgreSQL advisory locks are session-scoped, so releasing
// through a different pool connection would leak the lock.
func (t *ImportProcessor) acquireImportJobLock(ctx context.Context, jobID string) (*pgxpool.Conn, bool, error) {
	if t.BookDB == nil {
		return nil, true, nil
	}
	conn, err := t.BookDB.Acquire(ctx)
	if err != nil {
		return nil, false, err
	}
	var acquired bool
	if err := conn.QueryRow(ctx, `SELECT pg_try_advisory_lock(hashtext($1))`, jobID).Scan(&acquired); err != nil {
		conn.Release()
		return nil, false, err
	}
	if !acquired {
		conn.Release()
		return nil, false, nil
	}
	return conn, true, nil
}
func (t *ImportProcessor) releaseImportJobLock(ctx context.Context, conn *pgxpool.Conn, jobID string) {
	if conn == nil {
		return
	}
	_, _ = conn.Exec(ctx, `SELECT pg_advisory_unlock(hashtext($1))`, jobID)
	conn.Release()
}

func (t *ImportProcessor) importJobCompleted(ctx context.Context, jobID string) bool {
	if t.BookDB == nil {
		return false
	}
	var status string
	if err := t.BookDB.QueryRow(ctx, `SELECT status FROM import_jobs WHERE id=$1`, jobID).Scan(&status); err != nil {
		return false
	}
	return status == "completed" || status == "completed_with_warnings"
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
