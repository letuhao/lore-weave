package api

import (
	"archive/zip"
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"

	"github.com/loreweave/foundation/contracts/platformjwt"
	"github.com/loreweave/observability"

	"github.com/loreweave/book-service/internal/config"
	"github.com/loreweave/book-service/internal/textdiff"
	"github.com/loreweave/llmgw"
)

// imageGenerator is book-service's consumer-defined interface against
// the unified gateway SDK. Tests inject a mock; production wires the
// concrete *llmgw.Client (which satisfies this implicitly).
type imageGenerator interface {
	GenerateImage(ctx context.Context, req llmgw.GenerateImageRequest) (*llmgw.ImageGenResult, error)
}

// audioGenerator — Phase 5e-β.2. Consumer-defined interface for batch
// TTS through the unified gateway. Separate from imageGenerator so
// audio.go's tests can mock without stubbing image_gen, and vice versa.
// Production wires the SAME concrete *llmgw.Client to both fields
// (Go's structural-typing satisfies both implicitly).
type audioGenerator interface {
	GenerateAudio(ctx context.Context, req llmgw.GenerateAudioRequest) (*llmgw.AudioGenResult, error)
}

type Server struct {
	pool           *pgxpool.Pool
	cfg            *config.Config
	secret         []byte
	minio          *minio.Client
	llmgw          imageGenerator // Phase 5e-β.1; nil if config missing — handler checks
	audioGenClient audioGenerator // Phase 5e-β.2; satisfied by same *llmgw.Client
	// resolveBook is the E0-2 local grant resolver. Production wires it to
	// (*Server).resolveBookAuth in NewServer; tests override it to exercise the
	// route→need mapping (the grant chokepoint) without a real DB.
	resolveBook func(ctx context.Context, bookID, userID uuid.UUID) (GrantLevel, uuid.UUID, string, error)
	// emitTenantAudit is the P2·F cross-tenant audit hook. Production wires it to
	// (*Server).asyncTenantAudit (fire-and-forget insert); tests override it with a
	// synchronous spy to assert authBook emits on a cross-tenant crossing and stays
	// silent on own-book / missing-book. nil ⇒ no-op (struct-literal Server).
	emitTenantAudit func(actorID, bookID, ownerID uuid.UUID, outcome string)
	// auditDedup bounds the P2·F audit WRITE path to first-per-window (skips the
	// goroutine+insert on a repeat this window). nil ⇒ no dedup (still correct — the
	// DB ON CONFLICT dedups the row). Wired in NewServer.
	auditDedup *tenantAuditDedup
	// C5 / SD-C5 — diary encryption-at-rest. Non-nil after NewServer; .Enabled() is false when
	// DIARY_ENCRYPTION_KEY is unset (writes stay plaintext). Tests can inject a disabled one.
	diaryCrypto *diaryCrypto
}

func NewServer(pool *pgxpool.Pool, cfg *config.Config) *Server {
	s := &Server{pool: pool, cfg: cfg, secret: []byte(cfg.JWTSecret)}
	s.resolveBook = s.resolveBookAuth
	s.emitTenantAudit = s.asyncTenantAudit
	s.auditDedup = &tenantAuditDedup{}
	// C5 — diary encryption-at-rest (off with a loud warning when DIARY_ENCRYPTION_KEY is unset).
	s.diaryCrypto = newDiaryCrypto(cfg.AuthServiceInternalURL, cfg.InternalServiceToken,
		cfg.DiaryEncryptionKey, cfg.DiaryEncryptionKeysRetired)
	if cfg.MinioEndpoint != "" && cfg.MinioSecretKey != "" {
		mc, err := minio.New(cfg.MinioEndpoint, &minio.Options{
			Creds:  credentials.NewStaticV4(cfg.MinioAccessKey, cfg.MinioSecretKey, ""),
			Secure: cfg.MinioUseSSL,
		})
		if err == nil {
			s.minio = mc
		}
	}
	// Phase 5e-β.1 — wire unified gateway SDK. nil-on-misconfig matches
	// the s.minio pattern above; handler checks `if s.llmgw == nil`.
	// config.Load() already enforces both env vars are non-empty, so the
	// outer guard is dead-defensive — but the NewClient error path is
	// real (future SDK validation may add checks). Log loudly on failure
	// so a silent 503-forever loop is debuggable. (/review-impl(BUILD)
	// HIGH#3.)
	if cfg.LLMGatewayInternalURL != "" && cfg.InternalServiceToken != "" {
		lc, err := llmgw.NewClient(llmgw.Options{
			BaseURL:       cfg.LLMGatewayInternalURL,
			AuthMode:      llmgw.AuthInternal,
			InternalToken: cfg.InternalServiceToken,
			// UserID empty at ctor — book-service is multi-tenant; the
			// per-call UserID override (set to the owner_id in the route
			// handler) is the actual identity per request.
		})
		if err != nil {
			slog.Error("book-service: llmgw.NewClient failed; /media-generate + /audio will return 503 until fixed",
				"err", err,
				"base_url", cfg.LLMGatewayInternalURL)
		} else {
			s.llmgw = lc
			// Phase 5e-β.2 — same *llmgw.Client also satisfies audioGenerator.
			s.audioGenClient = lc
		}
	}
	return s
}

// Phase 6c — traced transport so outbound calls carry a W3C traceparent + emit a CLIENT span.
var internalClient = &http.Client{Timeout: 10 * time.Second, Transport: observability.HTTPTransport(nil)}

func (s *Server) requireInternalToken(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if s.cfg.InternalServiceToken != "" && r.Header.Get("X-Internal-Token") != s.cfg.InternalServiceToken {
			writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "invalid internal token"})
			return
		}
		next.ServeHTTP(w, r)
	})
}

func (s *Server) Router() http.Handler {
	r := chi.NewRouter()
	r.Use(middleware.RequestID)
	r.Use(middleware.RealIP)
	// Phase 6c — OpenTelemetry SERVER span. Before Recoverer so the span
	// survives (and is marked 500) when a handler panics.
	r.Use(observability.ChiMiddleware())
	r.Use(middleware.Recoverer)
	r.Get("/health", func(w http.ResponseWriter, r *http.Request) {
		if s.pool != nil {
			if err := s.pool.Ping(r.Context()); err != nil {
				w.WriteHeader(http.StatusServiceUnavailable)
				_, _ = w.Write([]byte("db ping failed"))
				return
			}
		}
		_, _ = w.Write([]byte("ok"))
	})
	// T2-polish-2b — Prometheus scrape endpoint. No auth; scrape is
	// in-cluster only. Mounted outside /internal so scrapers don't
	// need X-Internal-Token.
	r.Method(http.MethodGet, "/metrics", metricsHandler())

	// S-BOOK (MCP fan-out) — the book MCP server. The kit's NewStatelessHandler
	// wraps it in the identity middleware (X-Internal-Token gate + envelope to
	// ctx), so it is mounted WITHOUT the /internal requireInternalToken wrapper
	// (the kit does the gate). The federation gateway connects here per call.
	//
	// BOTH "/mcp" and "/mcp/*" are mounted: the go-sdk StreamableHTTP handler
	// routes follow-up message traffic under the path subtree, so without the
	// wildcard the initialize POST succeeds once but subsequent list-tools POSTs
	// hit chi's 404 — which the federation gateway reports as the provider going
	// unavailable after the first refresh. Mirrors provider-registry's mount.
	// (Found at COMPOSE B live-smoke; unit tests used a single fresh handshake.)
	r.Handle("/mcp", s.mcpHandler())
	r.Handle("/mcp/*", s.mcpHandler())

	// S-BOOK Tier-W — the NET-NEW class-C action routes. JWT-gated inside the
	// handlers (requireUserID); confirm is the only token-gated write path.
	s.registerActionRoutes(func(method, pattern string, h http.HandlerFunc) {
		r.Method(method, pattern, h)
	})

	r.Get("/health/ready", func(w http.ResponseWriter, r *http.Request) {
		if s.pool == nil {
			writeJSON(w, http.StatusServiceUnavailable, map[string]string{"status": "not ready", "error": "no db pool"})
			return
		}
		var n int
		if err := s.pool.QueryRow(r.Context(), "SELECT 1").Scan(&n); err != nil {
			w.WriteHeader(http.StatusServiceUnavailable)
			writeJSON(w, http.StatusServiceUnavailable, map[string]string{"status": "not ready", "error": err.Error()})
			return
		}
		writeJSON(w, http.StatusOK, map[string]string{"status": "ready"})
	})

	r.Route("/internal", func(r chi.Router) {
		r.Use(s.requireInternalToken)
		r.Get("/books/{book_id}/projection", s.getBookProjection)
		// E0 — the single grant-resolution authority every service calls.
		// Always 200 {grant_level}; `none` for missing/forbidden (no oracle, R4).
		r.Get("/books/{book_id}/access", s.getBookAccess)
		// KG-ML M3 (DD3) — cross-service reader-language resolver (M4/M7).
		r.Get("/books/{book_id}/reader-language", s.getInternalReaderLanguage)
		// RAID C1 (DR-C1) — chat-service fetches the ENABLED steering entries
		// to render the <steering> system part on book-scoped turns.
		r.Get("/books/{book_id}/steering", s.getInternalBookSteering)
		// G4 (W2) — world membership for the knowledge-service world-rollup
		// subgraph. Owner-scoped by the ?user_id param (404 if not owned).
		r.Get("/worlds/{world_id}/books", s.internalListWorldBooks)
		r.Get("/worlds/{world_id}/bible", s.getInternalWorldBible)               // W10-M1 world→bible resolution (world-native lore authoring)
		r.Post("/worlds/maps/{map_id}/image", s.uploadWorldMapImage)             // W10-M2 map base-image upload (owner-scoped by ?user_id)
		r.Get("/books/{book_id}/reading-position", s.getInternalReadingPosition) // W11 reader spoiler cutoff (§4.1)
		r.Get("/book/jobs", s.reconcileImportJobs)                               // Unified Job Control Plane reconcile source (book-import, D-JOBS-BOOK-IMPORT-UNWIRED)
		r.Get("/books/{book_id}/lexical-search", s.searchChapterTextInternal)    // raw-search Phase 2 (lexical leg for the knowledge orchestrator)
		r.Get("/books/{book_id}/chapters", s.getInternalBookChapters)
		// chat-service calls this ONCE PER TURN: "how many chapters, and how many
		// actually hold prose?" — one query, no paging. Deliberately NOT served by
		// /chapters above: that route clamps limit to 100 (a >100-chapter book would
		// have to be paged just to count) and its word_count_estimate only reads
		// chapter_drafts, so an IMPORTED book (prose in chapter_raw_objects) reports
		// 0 words per chapter and would look empty. See prose_state.go.
		r.Get("/books/{book_id}/prose-state", s.getInternalBookProseState)
		r.Get("/books/{book_id}/chapters/{chapter_id}", s.getInternalBookChapter)
		r.Get("/books/{book_id}/chapters/{chapter_id}/blocks", s.getInternalChapterBlocks) // T2 translation segmentation — per-block rows
		// P2 (hierarchical extraction T3) — knowledge-service consumes these
		// for per-leaf orchestration. Spec D8 + scenes.go.
		r.Get("/books/{book_id}/chapters/{chapter_id}/scenes", s.getInternalScenesByChapter)
		r.Get("/books/{book_id}/chapters/{chapter_id}/draft-text", s.getInternalChapterDraftText)
		// Canon Model CM3a — worker-ai (CM3b) fetches the PINNED published
		// revision's text to extract canon at the published snapshot (not the
		// live draft). Internal-token; IDOR-guarded (revision ∈ chapter ∈ book).
		r.Get("/books/{book_id}/chapters/{chapter_id}/revisions/{revision_id}/text", s.getInternalChapterRevisionText)
		// P3 D-P3-EXTRACTION-CALLER-WIRE-UP — worker-ai consumes this to
		// build the HierarchyPathsPayload it forwards to knowledge-service's
		// /persist-pass2 (so the receiving side can enqueue summaries).
		r.Get("/books/{book_id}/chapters/{chapter_id}/hierarchy", s.getInternalChapterHierarchy)
		// C6 (D-K19b.3-01 + D-K19e-β-01) — batch chapter-title resolver.
		// Cross-book query (caller passes a set of chapter_ids from any
		// books they own); sits under /internal/chapters rather than
		// /internal/books/... because it's not scoped to a single book.
		r.Post("/chapters/titles", s.postInternalChapterTitles)
		r.Post("/chapters/sort-orders", s.postInternalChapterSortOrders)
		// 26 IX-9 — canon-markers batch resolver consumed by composition's
		// conformance-status read (the dirty predicate). Mirrors sort-orders'
		// contract (200-id cap, partial responses) but is book-scoped by the path.
		r.Post("/books/{book_id}/chapters/canon-markers", s.postInternalChapterCanonMarkers)
		r.Patch("/imports/{import_id}", s.updateImportJobStatus)
		// WS-1.8 (spec 06 §Q10) — the journal distiller's ONLY write seam: draft-only,
		// owner-scoped, idempotent primary-per-day diary entry. Internal-token (the worker
		// has no user JWT); the (book, owner) pair is verified to be the caller's own diary.
		r.Post("/books/{book_id}/diary/entry", s.upsertDiaryEntry)
		// WS-3.3 M1 — cheap pre-LLM kept check so the catch-up doesn't re-distill a kept day.
		r.Get("/books/{book_id}/diary/day-kept", s.diaryDayKept)
		// D-R27 — the assistant-erase orchestrator (gateway) resolves the diary (any lifecycle, no
		// create) then HARD-deletes it + all its content (ON DELETE CASCADE). Internal-token;
		// owner+diary guarded.
		r.Get("/books/diary", s.getInternalDiaryBook)
		r.Delete("/books/{book_id}/diary/erase", s.eraseDiaryBook)
	})

	r.Route("/v1/books", func(r chi.Router) {
		r.Get("/storage-usage", s.getStorageUsage)
		r.Get("/reading-history", s.getReadingHistory)
		r.Post("/", s.createBook)
		r.Get("/", s.listBooks)
		// WS-1.4 — the diary provisioner (the only kind='diary' write path). Static segment,
		// registered before the /{book_id} sub-route so it is not captured as a book id.
		r.Post("/diary", s.provisionDiaryBook)
		r.Get("/trash", s.listTrashedBooks)

		// Favorites
		r.Get("/favorites", s.listFavorites)

		r.Route("/{book_id}", func(r chi.Router) {
			r.Get("/", s.getBook)
			r.Get("/search", s.searchChapterText) // raw-search Phase 1 (lexical leg)
			r.Patch("/", s.patchBook)
			r.Delete("/", s.trashBook)
			r.Post("/restore", s.restoreBook)
			r.Delete("/purge", s.purgeBook)
			r.Post("/favorite", s.addFavorite)
			r.Delete("/favorite", s.removeFavorite)
			r.Get("/favorite", s.checkFavorite)

			// KG-ML M3 (DD3) — per-(user,book) reader-language preference
			// (server SSOT, cross-device). View-gated (per-user data on a
			// readable book), so NOT in the mutating-routes grant table.
			r.Get("/reader-language", s.getReaderLanguage)
			r.Put("/reader-language", s.setReaderLanguage)

			// RAID C1 (DR-C1) — per-book steering store. List is VIEW-gated
			// (steering renders into any collaborator's chat on this book);
			// writes are EDIT-gated (same tier as editing chapters).
			r.Get("/steering", s.listSteering)
			r.Post("/steering", s.createSteering)
			r.Put("/steering/{steering_id}", s.updateSteering)
			r.Delete("/steering/{steering_id}", s.deleteSteering)

			r.Get("/cover", s.getCover)
			r.Post("/cover", s.uploadCover)
			r.Delete("/cover", s.deleteCover)

			// E0 — owner-only collaborator management (grant/revoke share-access).
			r.Get("/collaborators", s.listCollaborators)
			r.Post("/collaborators", s.inviteCollaborator) // E0-5 email-invite
			r.Put("/collaborators/{user_id}", s.putCollaborator)
			r.Delete("/collaborators/{user_id}", s.deleteCollaborator)

			r.Get("/chapters", s.listChapters)
			r.Post("/chapters", s.createChapter)
			// Bulk plain-text create (folder/large import). Static path — chi matches
			// it before /chapters/{chapter_id} so "bulk" isn't taken as a chapter_id.
			r.Post("/chapters/bulk", s.bulkCreateChapters)
			// Keyset/cursor-paged chapter list for the manuscript navigator (10k+ chapters).
			// Static path (before /chapters/{chapter_id}) — same reason as bulk.
			r.Get("/chapters/page", s.listChaptersKeyset)
			// Chapter Browser A3/A4 — bulk lifecycle change + bulk zip export. Static
			// paths (before /chapters/{chapter_id}) — same reason as bulk/page above.
			r.Patch("/chapters/bulk-status", s.bulkUpdateChapterStatus)
			r.Post("/chapters/export-zip", s.bulkExportChapters)
			// 24 PH20 Row-3 — transactional reading-order reorder. Static path (before
			// /chapters/{chapter_id}) — same reason as bulk/page above.
			r.Post("/chapters/reorder", s.reorderChapters)

			// S-02 — manuscript parts (acts / volumes) editor CRUD. The `parts` layer was
			// write-only from the import decomposer; these routes let a user create/rename/
			// reorder/trash an act and move a chapter between acts (VIEW to list, EDIT to write).
			r.Get("/parts", s.listParts)
			r.Post("/parts", s.createPart)
			r.Post("/parts/reorder", s.reorderParts) // static — before /parts/{part_id}
			r.Patch("/parts/{part_id}", s.renamePart)
			r.Delete("/parts/{part_id}", s.archivePart)
			r.Post("/parts/{part_id}/restore", s.restorePart)

			// 22-A2/A3 — scene browser (read-only, VIEW-gated; SC5 inverted authoring
			// to composition). Book-wide keyset-paged list + single-scene get. Static
			// "/scenes" registers before "/scenes/{scene_id}" so chi matches it first.
			r.Get("/scenes", s.getBookScenes)
			r.Get("/scenes/{scene_id}", s.getBookScene)

			// B2 (spec 03/06 §Q6) — REVIEW→KEEP a draft diary entry (owner-only, diary-only).
			// Sets diary_kept_at so a re-distill of the day no longer clobbers the kept primary.
			r.Post("/diary/entries/{chapter_id}/keep", s.keepDiaryEntry)
			// WS-2.6a / D17 leg 1 — AMEND (correct) a diary entry. The missing leg: unlike the
			// distiller write-seam (refuses a kept entry), an amendment is an explicit human
			// correction that writes a new revision AND PRESERVES diary_kept_at. Owner-only, diary-only.
			r.Post("/diary/entries/{chapter_id}/amend", s.amendDiaryEntry)
			// WS-2.6c / D17 forget-a-person (source-text leg) — redact a NAME from the diary bodies so a
			// re-index can't resurface it (the knowledge leg deletes the structured :Entity/:Facts).
			r.Post("/diary/redact", s.redactDiaryName)
			// D-R18 — OWNER-ONLY diary stats (entry count / words / day span). NOT the shared
			// statistics aggregate (the diary stays out of every cross-user surface, D-R16).
			r.Get("/diary/stats", s.diaryStats)
			// WS-1.10 — OWNER-ONLY diary entries list (newest-first, body inline) for the
			// assistant home timeline + the end-of-day review. Diary-only; never a shared surface.
			r.Get("/diary/entries", s.listDiaryEntries)

			r.Route("/chapters/{chapter_id}", func(r chi.Router) {
				r.Get("/", s.getChapter)
				r.Patch("/", s.patchChapter)
				// S-02 — move a chapter into/out of/between acts. Separate from patchChapter
				// so the move is explicit/auditable and patchChapter's OCC contract is untouched.
				r.Patch("/part", s.setChapterPart)
				r.Delete("/", s.trashChapter)
				r.Post("/restore", s.restoreChapter)
				r.Delete("/purge", s.purgeChapter)
				r.Get("/content", s.getChapterContent)
				// 22-A2 — chapter-scoped scene rail (read-only, VIEW-gated). Distinct from
				// the internal P2 orchestrator route; this is the public browser surface.
				r.Get("/scenes", s.getChapterScenes)
				r.Get("/export", s.exportChapter)
				r.Get("/draft", s.getDraft)
				r.Patch("/draft", s.patchDraft)
				r.Get("/revisions", s.listRevisions)
				r.Get("/revisions/compare", s.compareRevisions) // static; chi matches before /{revision_id}
				r.Get("/revisions/{revision_id}", s.getRevision)
				r.Post("/revisions/{revision_id}/restore", s.restoreRevision)
				r.Post("/publish", s.publishChapter)     // Canon Model CM1: draft → published (canon)
				r.Post("/unpublish", s.unpublishChapter) // Canon Model CM1: published → draft
				// WS-0.4: indexing is INDEPENDENT of publishing. "publish" now means only
				// "this is the canonical version"; "index" means "add this to my knowledge
				// graph" and works on any chapter of any book kind, draft or published.
				r.Post("/index", s.postChapterIndex)        // → chapter.kg_indexed
				r.Put("/kg-exclude", s.putChapterKGExclude) // true ⇒ retract from the KG
				r.Post("/media", s.uploadChapterMedia)
				r.Post("/media-generate", s.generateChapterMedia)
				r.Get("/media-versions", s.listMediaVersions)
				r.Post("/media-versions", s.createMediaVersion)
				r.Delete("/media-versions/{version_id}", s.deleteMediaVersion)
				r.Get("/audio", s.listAudioSegments)
				r.Post("/audio/generate", s.generateAudio)
				r.Get("/audio/{segment_id}", s.getAudioSegment)
				r.Delete("/audio", s.deleteAudioSegments)
				r.Post("/block-audio", s.uploadBlockAudio)
				r.Post("/progress", s.upsertReadingProgress)
			})

			// Import (.docx/.epub/.pdf)
			r.Post("/import", s.startImport)
			r.Post("/import/pdf-peek", s.pdfPeek)
			r.Get("/imports", s.listImportJobs)
			r.Get("/imports/{import_id}", s.getImportJob)

			// Analytics — at book level
			r.Post("/view", s.recordBookView)
			r.Get("/progress", s.listReadingProgress)
			r.Get("/stats", s.getBookStats)
		})
	})

	// C20 — world container. Owner-scoped grouping of books (no collaborators
	// on worlds; per-book grants are unchanged). World creation auto-provisions
	// a hidden sort_order-0 bible chapter (ARCH-REVIEW LOCK).
	r.Route("/v1/worlds", func(r chi.Router) {
		r.Post("/", s.createWorld)
		r.Get("/", s.listWorlds)
		r.Route("/{world_id}", func(r chi.Router) {
			r.Get("/", s.getWorld)
			r.Patch("/", s.patchWorld)
			r.Delete("/", s.deleteWorld)
			r.Get("/books", s.listWorldBooks)
			r.Post("/books", s.moveBookIntoWorld)
			r.Delete("/books/{book_id}", s.removeBookFromWorld)
			// W10-M8 — the maps FE canvas's read surface (list + detail with markers/regions).
			r.Get("/maps", s.listWorldMaps)
			r.Get("/maps/{map_id}", s.getWorldMapREST)
			// S7·2 — the world-map EDITOR's public write surface (~10 routes). All owner-scoped via
			// requireWorldOwner + the map-owner JOIN; map rename is If-Match/version OCC (428/412),
			// marker/region writes are last-write-wins (spec §4.4). See worlds_maps_write_rest.go.
			r.Post("/maps", s.createMapREST)                                     // R1
			r.Patch("/maps/{map_id}", s.patchMapREST)                            // R2 (If-Match)
			r.Delete("/maps/{map_id}", s.deleteMapREST)                          // R3
			r.Post("/maps/{map_id}/image", s.uploadWorldMapImagePublic)          // R4 (public JWT wrapper)
			r.Post("/maps/{map_id}/markers", s.addMarkerREST)                    // R5
			r.Patch("/maps/{map_id}/markers/{marker_id}", s.patchMarkerREST)     // R6 (drag)
			r.Delete("/maps/{map_id}/markers/{marker_id}", s.deleteMarkerREST)   // R7
			r.Post("/maps/{map_id}/regions", s.addRegionREST)                    // R8
			r.Patch("/maps/{map_id}/regions/{region_id}", s.patchRegionREST)     // R9 (reshape)
			r.Delete("/maps/{map_id}/regions/{region_id}", s.deleteRegionREST)   // R10
		})
	})
	return r
}

type errorBody struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, code, message string) {
	writeJSON(w, status, errorBody{Code: code, Message: message})
}

type accessClaims struct {
	jwt.RegisteredClaims
}

func (s *Server) requireUserID(r *http.Request) (uuid.UUID, bool) {
	auth := r.Header.Get("Authorization")
	if !strings.HasPrefix(auth, "Bearer ") {
		return uuid.Nil, false
	}
	tokenStr := strings.TrimPrefix(auth, "Bearer ")
	claims, err := platformjwt.Verify(tokenStr, s.secret)
	if err != nil {
		return uuid.Nil, false
	}
	id, err := claims.UserID()
	if err != nil {
		return uuid.Nil, false
	}
	return id, true
}

func parseUUIDParam(w http.ResponseWriter, r *http.Request, name string) (uuid.UUID, bool) {
	id, err := uuid.Parse(chi.URLParam(r, name))
	if err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid "+name)
		return uuid.Nil, false
	}
	return id, true
}

func (s *Server) fetchSharingVisibility(ctx context.Context, bookID uuid.UUID) string {
	if strings.TrimSpace(s.cfg.SharingInternalURL) == "" {
		return "private"
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, fmt.Sprintf("%s/internal/sharing/books/%s/visibility", strings.TrimRight(s.cfg.SharingInternalURL, "/"), bookID), nil)
	if err != nil {
		return "private"
	}
	if s.cfg.InternalServiceToken != "" {
		req.Header.Set("X-Internal-Token", s.cfg.InternalServiceToken)
	}
	resp, err := internalClient.Do(req)
	if err != nil {
		return "private"
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return "private"
	}
	var out struct {
		Visibility string `json:"visibility"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return "private"
	}
	switch out.Visibility {
	case "private", "unlisted", "public":
		return out.Visibility
	default:
		return "private"
	}
}

func parseLimitOffset(r *http.Request) (limit, offset int) {
	limit = 20
	offset = 0
	if v := r.URL.Query().Get("limit"); v != "" {
		// Clamp to the 100 max instead of falling back to the default 20: a
		// consumer asking for >100 (e.g. the translate wizard) wants "as many as
		// allowed", not a silent drop to 20. (chapter-list-limit100-fallback-20-bug)
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			if n > 100 {
				n = 100
			}
			limit = n
		}
	}
	if v := r.URL.Query().Get("offset"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n >= 0 {
			offset = n
		}
	}
	return
}

// parseSortRange reads the optional ?from_sort= and ?to_sort= query
// params that the internal chapters endpoint uses to scope extraction
// jobs to a chapter range (D-K16.2-02). Returns `(from, to, ok)` —
// ok=false means the caller passed a malformed value we should reject
// with 400. `*int` lets the SQL builder distinguish "not set" from
// "set to 0" so from_sort=0 (chapter zero, if the user uses 0-indexed
// sort orders) behaves correctly.
func parseSortRange(r *http.Request) (from, to *int, ok bool) {
	parse := func(key string) (*int, bool) {
		raw := r.URL.Query().Get(key)
		if raw == "" {
			return nil, true
		}
		n, err := strconv.Atoi(raw)
		if err != nil || n < 0 {
			return nil, false
		}
		return &n, true
	}
	f, okF := parse("from_sort")
	t, okT := parse("to_sort")
	if !okF || !okT {
		return nil, nil, false
	}
	return f, t, true
}

// buildSortRangeFilter is the pure SQL-builder used by
// getInternalBookChapters for its chapter list + count queries. It
// exists as its own function so unit tests can assert on the exact
// WHERE fragments and placeholder positions without a real pgx pool
// (review-impl LOW #4). `baseSel` is the table-qualified WHERE (for
// the SELECT), `baseCount` is the unqualified one (for COUNT). The
// caller owns the starting args slice so the function works for both
// the count and list queries without duplicating placeholder math.
func buildSortRangeFilter(
	baseSel string,
	baseCount string,
	args []any,
	fromSort *int,
	toSort *int,
) (selWhere string, countWhere string, outArgs []any) {
	selWhere = baseSel
	countWhere = baseCount
	outArgs = args
	if fromSort != nil {
		outArgs = append(outArgs, *fromSort)
		selWhere += fmt.Sprintf(" AND c.sort_order >= $%d", len(outArgs))
		countWhere += fmt.Sprintf(" AND sort_order >= $%d", len(outArgs))
	}
	if toSort != nil {
		outArgs = append(outArgs, *toSort)
		selWhere += fmt.Sprintf(" AND c.sort_order <= $%d", len(outArgs))
		countWhere += fmt.Sprintf(" AND sort_order <= $%d", len(outArgs))
	}
	return selWhere, countWhere, outArgs
}

// appendEditorialStatusFilter is the pure SQL-builder for CM3c's optional
// `?editorial_status=` canon-gate. It mirrors buildSortRangeFilter so a unit
// test can assert the placeholder arithmetic (the R2-BLOCK#2 silent-blackout
// risk) without a real pgx pool. `es` MUST already be validated by the caller
// (one of "draft"/"published"); an empty `es` is a no-op pass-through. For
// "published" it also requires a non-NULL published_revision_id — the only
// canon-pinnable published state — so the COUNT matches the worker enumeration
// (which skips purged-pointer chapters). Appends the status value to `args`
// and emits its placeholder from the POST-append len, so the caller's
// limit/offset positions (computed from the returned outArgs) stay correct.
func appendEditorialStatusFilter(
	selWhere string,
	countWhere string,
	args []any,
	es string,
) (string, string, []any) {
	if es == "" {
		return selWhere, countWhere, args
	}
	outArgs := append(args, es)
	selWhere += fmt.Sprintf(" AND c.editorial_status=$%d", len(outArgs))
	countWhere += fmt.Sprintf(" AND editorial_status=$%d", len(outArgs))
	if es == "published" {
		selWhere += " AND c.published_revision_id IS NOT NULL"
		countWhere += " AND published_revision_id IS NOT NULL"
	}
	return selWhere, countWhere, outArgs
}

// appendKGIndexedFilter — WS-0.6. The "is this chapter in the knowledge graph?" gate.
//
// Spec: docs/specs/2026-07-11-publish-independent-kg-indexing.md §3.5 (red-team P0-2).
//
// This is a SIBLING of appendEditorialStatusFilter, deliberately NOT a replacement.
// `editorial_status` keeps meaning editorial status — it has legitimate non-KG users
// (translation-service word counts, lore-enrichment, the chapter browser, knowledge's
// draft lexical search). Re-defining it would break them. Extraction callers ask the
// NEW question instead: "which chapters has the user put in their knowledge graph?"
//
// The predicate is the SAME ONE the reparse sweeper uses (WS-0.5) — deliberately, so
// enumerate and heal can never disagree about the graph's membership. It is served by
// idx_chapters_kg_indexed (migrate.go).
//
// Takes no bound argument: the predicate is a constant, so it cannot disturb the
// caller's $N positions for limit/offset.
func appendKGIndexedFilter(selWhere, countWhere string, kgIndexed bool) (string, string) {
	if !kgIndexed {
		return selWhere, countWhere
	}
	selWhere += " AND c.kg_indexed_revision_id IS NOT NULL AND c.kg_exclude = false"
	countWhere += " AND kg_indexed_revision_id IS NOT NULL AND kg_exclude = false"
	return selWhere, countWhere
}

func (s *Server) ensureQuotaRow(ctx context.Context, ownerID uuid.UUID) error {
	_, err := s.pool.Exec(ctx, `
INSERT INTO user_storage_quota(owner_user_id, used_bytes, quota_bytes)
VALUES($1, 0, $2)
ON CONFLICT(owner_user_id) DO NOTHING
`, ownerID, s.cfg.QuotaBytesDefault)
	return err
}

func (s *Server) recalcQuota(ctx context.Context, ownerID uuid.UUID) error {
	_, err := s.pool.Exec(ctx, `
WITH bytes AS (
  SELECT COALESCE(SUM(c.byte_size),0)::bigint AS chapter_bytes
  FROM books b
  JOIN chapters c ON c.book_id=b.id
  WHERE b.owner_user_id=$1 AND c.lifecycle_state!='purge_pending'
), cover AS (
  SELECT COALESCE(SUM(a.byte_size),0)::bigint AS cover_bytes
  FROM books b
  JOIN book_cover_assets a ON a.book_id=b.id
  WHERE b.owner_user_id=$1
)
UPDATE user_storage_quota q
SET used_bytes = bytes.chapter_bytes + cover.cover_bytes
FROM bytes, cover
WHERE q.owner_user_id=$1
`, ownerID)
	return err
}

func (s *Server) getStorageUsage(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	ctx := r.Context()
	if err := s.ensureQuotaRow(ctx, ownerID); err != nil || s.recalcQuota(ctx, ownerID) != nil {
		writeError(w, http.StatusInternalServerError, "STORAGE_BACKEND_ERROR", "failed to load storage usage")
		return
	}
	var used, quota int64
	if err := s.pool.QueryRow(ctx, `SELECT used_bytes, quota_bytes FROM user_storage_quota WHERE owner_user_id=$1`, ownerID).Scan(&used, &quota); err != nil {
		writeError(w, http.StatusInternalServerError, "STORAGE_BACKEND_ERROR", "failed to load storage usage")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"used_bytes": used, "quota_bytes": quota})
}

func (s *Server) createBook(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	var in struct {
		Title            string   `json:"title"`
		Description      string   `json:"description"`
		OriginalLanguage string   `json:"original_language"`
		Summary          string   `json:"summary"`
		GenreTags        []string `json:"genre_tags"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil || strings.TrimSpace(in.Title) == "" {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "title is required")
		return
	}
	if in.GenreTags == nil {
		in.GenreTags = []string{}
	}
	ctx := r.Context()
	if err := s.ensureQuotaRow(ctx, ownerID); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to initialize quota")
		return
	}
	// Per-user active-book ceiling (parity with the MCP book_create tool) — refuse
	// before inserting so a script can't loop createBook into unbounded empty books.
	n, err := s.countActiveBooks(ctx, ownerID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to check book quota")
		return
	}
	if n >= maxBooksPerUser {
		writeError(w, http.StatusConflict, "BOOK_LIMIT_REACHED",
			fmt.Sprintf("book limit reached (%d) — delete or purge a book first", maxBooksPerUser))
		return
	}
	var bookID uuid.UUID
	if err := s.pool.QueryRow(ctx, `
-- WS-1.1: kind EXPLICIT, never leaning on the column default. kind is the privacy lock,
-- and a create path that silently inherits a default is exactly how a new path (a diary!)
-- ends up mis-kinded and shareable. The hygiene test asserts every INSERT names it.
INSERT INTO books(owner_user_id,title,description,original_language,summary,genre_tags,kind)
VALUES($1,$2,$3,$4,$5,$6,'novel')
RETURNING id
`, ownerID, in.Title, in.Description, in.OriginalLanguage, in.Summary, in.GenreTags).Scan(&bookID); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to create book")
		return
	}
	s.getBookByID(w, ctx, bookID, ownerID, http.StatusCreated)
}

// provisionDiaryBook — POST /v1/books/diary — the diary get-or-create (WS-1.4 step 1, spec 02 §Q2.1).
//
// The ONLY path allowed to write kind='diary'. Idempotent + race-safe get-or-create keyed on
// uq_books_one_active_diary_per_user: a user has exactly ONE active diary, and two concurrent
// provisions (two devices open /assistant, a retried BFF call) converge on it instead of
// splitting the assistant's memory into two unreadable halves.
//
// Owner is the JWT principal, NEVER a body field (the caller is a chat/BFF request; a
// body-supplied owner would be a cross-user write).
//
// The per-user active-book CEILING is deliberately NOT applied here (unlike createBook): the
// diary is a system-provisioned private workspace, not a user-authored novel, and it is hidden
// from the library grid — a user at their novel limit must still be able to get an assistant.
//
// E14: if the user's only diary is TRASHED, this refuses (409 BOOK_DIARY_TRASHED) with the
// trashed id rather than silently forking a fresh diary (which strands the old KG anchors) or
// silently resurrecting the trashed one — the caller offers restore-vs-start-fresh.
func (s *Server) provisionDiaryBook(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	var in struct {
		Title string `json:"title"`
	}
	_ = json.NewDecoder(r.Body).Decode(&in) // body is optional
	title := strings.TrimSpace(in.Title)
	if title == "" {
		title = "My Work Journal"
	}
	ctx := r.Context()

	// 1. Already have an active diary? Return it — this is the common case on every re-open,
	//    and it must be a cheap idempotent read, not a create attempt.
	var existing uuid.UUID
	err := s.pool.QueryRow(ctx,
		`SELECT id FROM books WHERE owner_user_id=$1 AND kind='diary' AND lifecycle_state='active' LIMIT 1`,
		ownerID).Scan(&existing)
	if err == nil {
		s.getBookByID(w, ctx, existing, ownerID, http.StatusOK)
		return
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to read diary")
		return
	}

	// 2. No ACTIVE diary — but a TRASHED one must not be silently forked or resurrected (E14).
	// Only 'trashed' (restorable) is surfaced: a 'purge_pending' diary is on its way to
	// deletion and CANNOT be restored (restoreBook refuses it), so telling the user to
	// "restore or start fresh" would be a dead end — instead we fall through and provision a
	// fresh diary (the purge_pending row is not 'active', so the partial unique allows it).
	var trashed uuid.UUID
	err = s.pool.QueryRow(ctx,
		`SELECT id FROM books WHERE owner_user_id=$1 AND kind='diary'
		   AND lifecycle_state='trashed' ORDER BY updated_at DESC LIMIT 1`,
		ownerID).Scan(&trashed)
	if err == nil {
		writeError(w, http.StatusConflict, "BOOK_DIARY_TRASHED",
			"your diary is in the trash ("+trashed.String()+"); restore it or choose to start fresh")
		return
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to read trashed diary")
		return
	}

	if err := s.ensureQuotaRow(ctx, ownerID); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to initialize quota")
		return
	}

	// 3. Create it. ON CONFLICT repeats the partial-index predicate EXACTLY (the
	//    partial-index/ON-CONFLICT-predicate lesson), so a concurrent provision that already
	//    inserted the diary makes this a no-op; then re-read the row that WON the race.
	var bookID uuid.UUID
	err = s.pool.QueryRow(ctx, `
INSERT INTO books(owner_user_id,title,kind) VALUES($1,$2,'diary')
ON CONFLICT (owner_user_id) WHERE kind='diary' AND lifecycle_state='active'
DO NOTHING
RETURNING id`, ownerID, title).Scan(&bookID)
	if errors.Is(err, pgx.ErrNoRows) {
		// A concurrent provision won (DO NOTHING → no RETURNING row). Return the winner.
		if err = s.pool.QueryRow(ctx,
			`SELECT id FROM books WHERE owner_user_id=$1 AND kind='diary' AND lifecycle_state='active' LIMIT 1`,
			ownerID).Scan(&bookID); err != nil {
			writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to read diary after conflict")
			return
		}
		s.getBookByID(w, ctx, bookID, ownerID, http.StatusOK)
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to create diary")
		return
	}
	s.getBookByID(w, ctx, bookID, ownerID, http.StatusCreated)
}

// listBooks — "my library": owned AND collaborated (E0-2/R2). UNION resolved
// locally (book-service owns both tables → no N+1 /access calls).
func (s *Server) listBooks(w http.ResponseWriter, r *http.Request) {
	s.listBooksByLifecycle(w, r, "active", true)
}

// listTrashedBooks stays OWNER-ONLY — a collaborator never sees the owner's
// trash. (Book-level lifecycle is owner-only across E0-2.)
func (s *Server) listTrashedBooks(w http.ResponseWriter, r *http.Request) {
	s.listBooksByLifecycle(w, r, "trashed", false)
}

func (s *Server) listBooksByLifecycle(w http.ResponseWriter, r *http.Request, lifecycle string, includeShared bool) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	limit, offset := parseLimitOffset(r)
	ctx := r.Context()
	// accessFilter selects owned rows, plus collaborated rows when includeShared.
	// access_level is computed per row so the FE can distinguish owned vs shared.
	// is_bible=false excludes the auto-created hidden world-bible container books
	// (C20) — they anchor lore but must never appear in the user's library.
	// ── WS-1.2 · EGRESS GUARD #7: the library/catalog listing (spec 09) ──
	//
	// The diary is hidden from the default library grid, reusing the SAME is_bible hiding
	// precedent immediately above. It has its own surface (the Assistant); it is not a
	// book you browse to among your novels, and a diary tile sitting in a shared-screen
	// library is a real-world disclosure (a demo, a colleague looking over your shoulder).
	//
	// This is a LIST-level guard on purpose. The repo's paged-join lesson is that
	// per-resource checks pass while the LIST leaks — filtering here is what actually
	// keeps it out of the grid.
	//
	// NOTE for the shared branch: a diary can never be shared (see the collaborator and
	// sharing guards), so the kind filter also makes the includeShared branch honest —
	// a diary must not appear via someone else's grant either, however that grant arose.
	accessFilter := "b.owner_user_id=$1 AND b.is_bible=false AND b.kind<>'diary'"
	if includeShared {
		accessFilter = "(b.owner_user_id=$1 OR EXISTS(SELECT 1 FROM book_collaborators bc WHERE bc.book_id=b.id AND bc.user_id=$1)) AND b.is_bible=false AND b.kind<>'diary'"
	}
	rows, err := s.pool.Query(ctx, `
SELECT b.id,b.owner_user_id,b.title,b.description,b.original_language,b.summary,b.lifecycle_state,b.trashed_at,b.purge_eligible_at,b.created_at,b.updated_at,
  COALESCE((SELECT COUNT(*) FROM chapters c WHERE c.book_id=b.id AND c.lifecycle_state='active'),0) AS chapter_count,
  EXISTS(SELECT 1 FROM book_cover_assets a WHERE a.book_id=b.id) AS has_cover,
  b.genre_tags,
  CASE WHEN b.owner_user_id=$1 THEN 'owner'
       ELSE COALESCE((SELECT role FROM book_collaborators bc WHERE bc.book_id=b.id AND bc.user_id=$1),'none') END AS access_level
FROM books b
WHERE `+accessFilter+` AND b.lifecycle_state=$2
ORDER BY b.created_at DESC
LIMIT $3 OFFSET $4
`, ownerID, lifecycle, limit, offset)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to list books")
		return
	}
	defer rows.Close()
	items := make([]map[string]any, 0)
	for rows.Next() {
		var id, owner uuid.UUID
		var title, state, accessLevel string
		var desc, lang, summary *string
		var trashedAt, purgeAt, createdAt, updatedAt *time.Time
		var chapterCount int
		var hasCover bool
		var genreTags []string
		if err := rows.Scan(&id, &owner, &title, &desc, &lang, &summary, &state, &trashedAt, &purgeAt, &createdAt, &updatedAt, &chapterCount, &hasCover, &genreTags, &accessLevel); err == nil {
			if genreTags == nil {
				genreTags = []string{}
			}
			visibility := s.fetchSharingVisibility(ctx, id)
			items = append(items, map[string]any{
				"book_id":           id,
				"owner_user_id":     owner,
				"access_level":      accessLevel,
				"title":             title,
				"description":       desc,
				"original_language": lang,
				"summary":           summary,
				"lifecycle_state":   state,
				"trashed_at":        trashedAt,
				"purge_eligible_at": purgeAt,
				"chapter_count":     chapterCount,
				"has_cover":         hasCover,
				"visibility":        visibility,
				"genre_tags":        genreTags,
				"created_at":        createdAt,
				"updated_at":        updatedAt,
			})
		}
	}
	var total int
	_ = s.pool.QueryRow(ctx, `SELECT COUNT(*) FROM books b WHERE `+accessFilter+` AND b.lifecycle_state=$2`, ownerID, lifecycle).Scan(&total)
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "total": total})
}

func nullableString(s string) any {
	if s == "" {
		return nil
	}
	return s
}

// nullableStringPtr renders an optional (nullable) TEXT column for a JSON
// response: a NULL (nil pointer) or empty string collapses to null, any other
// value passes through. The null-safe form of nullableString for a *string scan
// target — required for nullable columns like chapters.title, where scanning a
// SQL NULL into a plain string errors "cannot scan NULL into *string".
func nullableStringPtr(p *string) any {
	if p == nil {
		return nil
	}
	return nullableString(*p)
}

func (s *Server) getBook(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	caller, _, _, ok := s.authBook(w, r, bookID, GrantView)
	if !ok {
		return
	}
	s.getBookByID(w, r.Context(), bookID, caller, http.StatusOK)
}

// getBookByID is a response-builder; it does NOT authorize — every caller MUST
// pre-check the grant (authBook) first. E0-2 dropped the owner filter (the
// query is keyed by id) so a collaborator's GET returns the book; access_level
// is computed for `caller` (owner|manage|edit|view|none) for the FE.
func (s *Server) getBookByID(w http.ResponseWriter, ctx context.Context, bookID, caller uuid.UUID, status int) {
	var id, owner uuid.UUID
	var title, state, accessLevel string
	var desc, lang, summary *string
	var worldID *uuid.UUID
	var trashedAt, purgeAt, createdAt, updatedAt *time.Time
	var chapterCount int
	var genreTags []string
	var wikiSettings json.RawMessage
	var extractionProfile json.RawMessage
	err := s.pool.QueryRow(ctx, `
SELECT b.id,b.owner_user_id,b.title,b.description,b.original_language,b.summary,b.lifecycle_state,b.trashed_at,b.purge_eligible_at,b.created_at,b.updated_at,
  COALESCE((SELECT COUNT(*) FROM chapters c WHERE c.book_id=b.id AND c.lifecycle_state='active'),0) AS chapter_count,
  b.genre_tags, b.wiki_settings, b.extraction_profile, b.world_id,
  CASE WHEN b.owner_user_id=$2 THEN 'owner'
       ELSE COALESCE((SELECT role FROM book_collaborators bc WHERE bc.book_id=b.id AND bc.user_id=$2),'none') END AS access_level
FROM books b
WHERE b.id=$1
`, bookID, caller).Scan(&id, &owner, &title, &desc, &lang, &summary, &state, &trashedAt, &purgeAt, &createdAt, &updatedAt, &chapterCount, &genreTags, &wikiSettings, &extractionProfile, &worldID, &accessLevel)
	if errors.Is(err, pgx.ErrNoRows) || state == "purge_pending" {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "book not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to get book")
		return
	}

	var cover any
	var ctype, skey string
	var csize int64
	var cupdated *time.Time
	if err := s.pool.QueryRow(ctx, `SELECT content_type, byte_size, storage_key, updated_at FROM book_cover_assets WHERE book_id=$1`, bookID).Scan(&ctype, &csize, &skey, &cupdated); err == nil {
		cover = map[string]any{
			"content_type": ctype,
			"byte_size":    csize,
			"download_url": fmt.Sprintf("/v1/books/%s/cover?key=%s", bookID, skey),
		}
	}
	if genreTags == nil {
		genreTags = []string{}
	}
	writeJSON(w, status, map[string]any{
		"book_id":            id,
		"owner_user_id":      owner,
		"access_level":       accessLevel,
		"title":              title,
		"description":        desc,
		"original_language":  lang,
		"summary":            summary,
		"cover":              cover,
		"chapter_count":      chapterCount,
		"visibility":         s.fetchSharingVisibility(ctx, id),
		"lifecycle_state":    state,
		"genre_tags":         genreTags,
		"wiki_settings":      json.RawMessage(wikiSettings),
		"extraction_profile": json.RawMessage(extractionProfile),
		// W6 (G3) — the world this book is grouped into (NULL = standalone), so the
		// book workspace can surface an "open in world" backlink.
		"world_id":          worldID,
		"trashed_at":        trashedAt,
		"purge_eligible_at": purgeAt,
		"created_at":        createdAt,
		"updated_at":        updatedAt,
	})
}

func (s *Server) patchBook(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	caller, _, lifecycle, ok := s.authBook(w, r, bookID, GrantEdit)
	if !ok {
		return
	}
	if lifecycle != "active" {
		writeError(w, http.StatusConflict, "BOOK_INVALID_LIFECYCLE", "book is not active")
		return
	}
	var in map[string]any
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid payload")
		return
	}
	// Build dynamic UPDATE — only set fields that were explicitly provided in the payload.
	// This allows sending null to clear a field (vs omitting to keep it unchanged).
	// Authorization is the authBook(edit) pre-check above; the query is keyed by id.
	setClauses := []string{"updated_at=now()"}
	args := []any{bookID}
	paramIdx := 2
	if _, ok := in["title"]; ok {
		setClauses = append(setClauses, fmt.Sprintf("title=COALESCE($%d,title)", paramIdx))
		args = append(args, stringFromAny(in["title"]))
		paramIdx++
	}
	if _, ok := in["description"]; ok {
		setClauses = append(setClauses, fmt.Sprintf("description=$%d", paramIdx))
		args = append(args, stringFromAny(in["description"]))
		paramIdx++
	}
	if _, ok := in["original_language"]; ok {
		setClauses = append(setClauses, fmt.Sprintf("original_language=$%d", paramIdx))
		args = append(args, stringFromAny(in["original_language"]))
		paramIdx++
	}
	if _, ok := in["summary"]; ok {
		setClauses = append(setClauses, fmt.Sprintf("summary=$%d", paramIdx))
		args = append(args, stringFromAny(in["summary"]))
		paramIdx++
	}
	if v, ok := in["genre_tags"]; ok {
		tags := make([]string, 0)
		if arr, ok := v.([]any); ok {
			for _, item := range arr {
				if s, ok := item.(string); ok {
					tags = append(tags, s)
				}
			}
		}
		setClauses = append(setClauses, fmt.Sprintf("genre_tags=$%d", paramIdx))
		args = append(args, tags)
		paramIdx++
	}
	if v, ok := in["wiki_settings"]; ok {
		// ── WS-1.2 · EGRESS GUARD #3: the wiki (spec 09 §Q3) ──
		//
		// This was the widest hole in the design. The public wiki gate reads
		// books.wiki_settings.visibility == "public" — a JSONB blob PATCHable right here,
		// keyed on NOTHING about the book's kind. Sharing-service's guard never runs on
		// this path.
		//
		// So the attack is two clicks: let the assistant build a wiki article about every
		// colleague named in your diary, then flip wiki_settings.visibility='public'. The
		// platform would then serve AI-written biographies of real people — your coworkers,
		// your manager — to the open internet, with no share step and no warning.
		//
		// A diary has no wiki. Not "a private wiki" — NO wiki. Refuse the mutation.
		var kind string
		if err := s.pool.QueryRow(r.Context(),
			`SELECT kind FROM books WHERE id=$1`, bookID).Scan(&kind); err != nil {
			writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to read book")
			return
		}
		if kind == "diary" {
			writeError(w, http.StatusForbidden, "BOOK_DIARY_NO_WIKI",
				"a diary has no wiki — it is private and cannot be published")
			return
		}
		raw, err := json.Marshal(v)
		if err != nil {
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid wiki_settings")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("wiki_settings=$%d", paramIdx))
		args = append(args, raw)
		paramIdx++
	}
	if v, ok := in["extraction_profile"]; ok {
		if v == nil {
			setClauses = append(setClauses, fmt.Sprintf("extraction_profile=$%d", paramIdx))
			args = append(args, nil)
		} else {
			raw, err := json.Marshal(v)
			if err != nil {
				writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid extraction_profile")
				return
			}
			setClauses = append(setClauses, fmt.Sprintf("extraction_profile=$%d", paramIdx))
			args = append(args, raw)
		}
		paramIdx++
	}
	query := fmt.Sprintf("UPDATE books SET %s WHERE id=$1", strings.Join(setClauses, ", "))
	_, err := s.pool.Exec(r.Context(), query, args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to patch book")
		return
	}
	s.getBookByID(w, r.Context(), bookID, caller, http.StatusOK)
}

func stringFromAny(v any) *string {
	if v == nil {
		return nil
	}
	s, ok := v.(string)
	if !ok {
		return nil
	}
	return &s
}

func (s *Server) trashBook(w http.ResponseWriter, r *http.Request) {
	s.transitionBookLifecycle(w, r, "trashed")
}
func (s *Server) restoreBook(w http.ResponseWriter, r *http.Request) {
	s.transitionBookLifecycle(w, r, "active")
}
func (s *Server) purgeBook(w http.ResponseWriter, r *http.Request) {
	s.transitionBookLifecycle(w, r, "purge_pending")
}

func (s *Server) transitionBookLifecycle(w http.ResponseWriter, r *http.Request, target string) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	ctx := r.Context()
	// Book-level lifecycle (trash/restore/purge the whole book) stays OWNER-ONLY
	// — a manage collaborator can delete content WITHIN the book but not the book
	// itself (E0-2 / R-book-destructive). authBook(owner) returns the lifecycle.
	ownerID, _, lifecycle, ok := s.authBook(w, r, bookID, GrantOwner)
	if !ok {
		return
	}
	switch target {
	case "trashed":
		if lifecycle != "active" {
			writeError(w, http.StatusConflict, "BOOK_INVALID_LIFECYCLE", "only active book can be trashed")
			return
		}
		_, _ = s.pool.Exec(ctx, `UPDATE books SET lifecycle_state='trashed', trashed_at=now(), updated_at=now() WHERE id=$1`, bookID)
		_, _ = s.pool.Exec(ctx, `UPDATE chapters SET lifecycle_state='trashed', trashed_at=now(), updated_at=now() WHERE book_id=$1 AND lifecycle_state='active'`, bookID)
		w.WriteHeader(http.StatusNoContent)
	case "active":
		if lifecycle != "trashed" {
			writeError(w, http.StatusConflict, "BOOK_INVALID_LIFECYCLE", "book must be trashed before restore")
			return
		}
		_, _ = s.pool.Exec(ctx, `UPDATE books SET lifecycle_state='active', trashed_at=NULL, purge_eligible_at=NULL, updated_at=now() WHERE id=$1`, bookID)
		_, _ = s.pool.Exec(ctx, `UPDATE chapters SET lifecycle_state='active', trashed_at=NULL, purge_eligible_at=NULL, updated_at=now() WHERE book_id=$1`, bookID)
		s.getBookByID(w, ctx, bookID, ownerID, http.StatusOK)
	case "purge_pending":
		if lifecycle != "trashed" {
			writeError(w, http.StatusConflict, "BOOK_INVALID_LIFECYCLE", "book must be trashed before purge")
			return
		}
		_, _ = s.pool.Exec(ctx, `UPDATE books SET lifecycle_state='purge_pending', purge_eligible_at=now(), updated_at=now() WHERE id=$1`, bookID)
		_, _ = s.pool.Exec(ctx, `UPDATE chapters SET lifecycle_state='purge_pending', purge_eligible_at=now(), updated_at=now() WHERE book_id=$1`, bookID)
		w.WriteHeader(http.StatusNoContent)
	default:
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "unsupported transition")
	}
}

func (s *Server) uploadCover(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	caller, ownerID, lifecycle, ok := s.authBook(w, r, bookID, GrantEdit)
	if !ok {
		return
	}
	if lifecycle != "active" {
		writeError(w, http.StatusConflict, "BOOK_INVALID_LIFECYCLE", "book not active")
		return
	}
	if err := r.ParseMultipartForm(10 << 20); err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid multipart")
		return
	}
	f, fh, err := r.FormFile("file")
	if err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "file is required")
		return
	}
	defer f.Close()
	data, _ := io.ReadAll(f)
	contentType := fh.Header.Get("Content-Type")
	if !strings.HasPrefix(contentType, "image/") {
		writeError(w, http.StatusUnsupportedMediaType, "UNSUPPORTED_MEDIA_TYPE", "cover must be image/*")
		return
	}
	ctx := r.Context()
	if err := s.ensureQuotaRow(ctx, ownerID); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "quota init failed")
		return
	}
	_, err = s.pool.Exec(ctx, `
INSERT INTO book_cover_assets(book_id, content_type, byte_size, storage_key, data, updated_at)
VALUES($1,$2,$3,$4,$5,now())
ON CONFLICT(book_id) DO UPDATE SET content_type=EXCLUDED.content_type, byte_size=EXCLUDED.byte_size, storage_key=EXCLUDED.storage_key, data=EXCLUDED.data, updated_at=now()
`, bookID, contentType, int64(len(data)), fmt.Sprintf("covers/%s", bookID), data)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to save cover")
		return
	}
	_ = s.recalcQuota(ctx, ownerID)
	s.getBookByID(w, ctx, bookID, caller, http.StatusOK)
}

func (s *Server) deleteCover(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	caller, ownerID, _, ok := s.authBook(w, r, bookID, GrantEdit)
	if !ok {
		return
	}
	// authBook(edit) authorized; the delete is keyed by id (owner-EXISTS guard dropped).
	_, err := s.pool.Exec(r.Context(), `DELETE FROM book_cover_assets WHERE book_id=$1`, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to delete cover")
		return
	}
	_ = s.recalcQuota(r.Context(), ownerID) // quota bills the book owner, not the editor
	s.getBookByID(w, r.Context(), bookID, caller, http.StatusOK)
}

func (s *Server) getCover(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	if _, _, _, ok := s.authBook(w, r, bookID, GrantView); !ok {
		return
	}
	var contentType string
	var data []byte
	err := s.pool.QueryRow(r.Context(), `
SELECT a.content_type, a.data
FROM book_cover_assets a
WHERE a.book_id=$1
`, bookID).Scan(&contentType, &data)
	if err != nil {
		writeError(w, http.StatusNotFound, "COVER_NOT_FOUND", "cover not found")
		return
	}
	w.Header().Set("Content-Type", contentType)
	w.Header().Set("Cache-Control", "private, max-age=3600")
	_, _ = w.Write(data)
}

func (s *Server) listChapters(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	_, _, state, ok := s.authBook(w, r, bookID, GrantView)
	if !ok {
		return
	}
	lifecycle := r.URL.Query().Get("lifecycle_state")
	if lifecycle == "" {
		if state == "trashed" {
			lifecycle = "trashed"
		} else {
			lifecycle = "active"
		}
	}
	limit, offset := parseLimitOffset(r)
	args := []any{bookID, lifecycle}
	where := `book_id=$1 AND lifecycle_state=$2`
	if v := r.URL.Query().Get("original_language"); v != "" {
		args = append(args, v)
		where += fmt.Sprintf(" AND original_language=$%d", len(args))
	}
	if v := r.URL.Query().Get("sort_order"); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			args = append(args, n)
			where += fmt.Sprintf(" AND sort_order=$%d", len(args))
		}
	}
	// editorial_status filter (B1 ChapterListBrowser / campaign published-only). Mirrors
	// getInternalBookChapters: "published" additionally requires a pinned revision.
	switch es := r.URL.Query().Get("editorial_status"); es {
	case "", "all":
		// no filter
	case "draft", "published":
		args = append(args, es)
		where += fmt.Sprintf(" AND editorial_status=$%d", len(args))
		if es == "published" {
			where += " AND published_revision_id IS NOT NULL"
		}
	default:
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid editorial_status")
		return
	}
	// q — case-insensitive substring over title + original_filename (B1 browser search).
	// Bounded by the 256-rune cap; a small per-book table makes the seq ILIKE cheap.
	if q := strings.TrimSpace(r.URL.Query().Get("q")); q != "" {
		if len([]rune(q)) > maxSearchQueryRunes {
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "query too long")
			return
		}
		args = append(args, escapeLikePattern(q))
		where += fmt.Sprintf(" AND (title ILIKE $%d OR original_filename ILIKE $%d)", len(args), len(args))
	}
	orderBy, sortErrMsg := chapterOffsetSortClause(r.URL.Query().Get("sort"))
	if sortErrMsg != "" {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", sortErrMsg)
		return
	}
	countArgs := append([]any{}, args...)
	var total int
	_ = s.pool.QueryRow(r.Context(), `SELECT COUNT(*) FROM chapters WHERE `+where, countArgs...).Scan(&total)
	args = append(args, limit, offset)
	rows, err := s.pool.Query(r.Context(), `SELECT id,book_id,title,original_filename,original_language,content_type,byte_size,sort_order,draft_updated_at,draft_revision_count,lifecycle_state,trashed_at,purge_eligible_at,created_at,updated_at,word_count,editorial_status,published_revision_id,part_id FROM chapters WHERE `+where+` ORDER BY `+orderBy+` LIMIT $`+strconv.Itoa(len(args)-1)+` OFFSET $`+strconv.Itoa(len(args)), args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "CHAPTER_NOT_FOUND", "failed to list chapters")
		return
	}
	defer rows.Close()
	items := make([]map[string]any, 0)
	for rows.Next() {
		var id, bid uuid.UUID
		var title *string // chapters.title is NULLABLE — a plain string errors the Scan on a titleless chapter, and the discarded-error path then zeroes every column AFTER it (part_id, sort_order, …). See getChapterByID.
		var fn, lang, ctype, lstate, editorialStatus string
		var size int64
		var order, wordCount int
		var draftUpdated, trashedAt, purgeAt, createdAt, updatedAt *time.Time
		var revCount int
		var publishedRevisionID *uuid.UUID
		var partID *uuid.UUID // S-02: the act this chapter is homed in (NULL = flat manuscript). The FE navigator groups on it.
		_ = rows.Scan(&id, &bid, &title, &fn, &lang, &ctype, &size, &order, &draftUpdated, &revCount, &lstate, &trashedAt, &purgeAt, &createdAt, &updatedAt, &wordCount, &editorialStatus, &publishedRevisionID, &partID)
		items = append(items, map[string]any{
			"chapter_id":            id,
			"book_id":               bid,
			"title":                 nullableStringPtr(title),
			"original_filename":     fn,
			"original_language":     lang,
			"content_type":          ctype,
			"byte_size":             size,
			"sort_order":            order,
			"draft_updated_at":      draftUpdated,
			"draft_revision_count":  revCount,
			"lifecycle_state":       lstate,
			"trashed_at":            trashedAt,
			"purge_eligible_at":     purgeAt,
			"created_at":            createdAt,
			"updated_at":            updatedAt,
			"word_count":            wordCount,
			"editorial_status":      editorialStatus,
			"published_revision_id": publishedRevisionID,
			"part_id":               partID,
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"items":  items,
		"total":  total,
		"limit":  limit,
		"offset": offset,
	})
}

// chapterOffsetSortClause maps the chapter-browser's ?sort= param (CB7) to an
// ORDER BY clause for the offset-paginated listChapters. Unset/"sort_order"
// preserves the pre-existing default ordering exactly. Every branch carries a
// stable tiebreak (sort_order) so ties (e.g. two chapters with the same
// word_count) still order deterministically across pages. An unrecognised
// value is a 400 (BOOK_VALIDATION_ERROR) — never a silent fallback to default,
// which would look like the sort was applied but wasn't.
func chapterOffsetSortClause(sort string) (orderBy, errMsg string) {
	switch sort {
	case "", "sort_order":
		return "sort_order, created_at", ""
	case "updated_at":
		return "updated_at DESC, sort_order", ""
	case "word_count":
		return "word_count DESC, sort_order", ""
	case "lifecycle_state":
		return "lifecycle_state, sort_order", ""
	default:
		return "", "invalid sort (must be sort_order, updated_at, word_count, or lifecycle_state)"
	}
}

// ── keyset cursor pagination (manuscript navigator, 10k+ chapters) ───────────

// encodeChapterCursor packs the keyset tuple (sort_order, chapter_id) into an opaque,
// URL-safe token. The client treats it as a blob; only this service decodes it.
func encodeChapterCursor(sortOrder int, id uuid.UUID) string {
	return base64.RawURLEncoding.EncodeToString(fmt.Appendf(nil, "%d|%s", sortOrder, id.String()))
}

// parseChapterCursor decodes a token from encodeChapterCursor. A malformed token → ok=false
// (caller returns 400); never a silent reset to page 1, which would loop the client.
func parseChapterCursor(s string) (sortOrder int, id uuid.UUID, ok bool) {
	raw, err := base64.RawURLEncoding.DecodeString(s)
	if err != nil {
		return 0, uuid.Nil, false
	}
	parts := strings.SplitN(string(raw), "|", 2)
	if len(parts) != 2 {
		return 0, uuid.Nil, false
	}
	n, err := strconv.Atoi(parts[0])
	if err != nil {
		return 0, uuid.Nil, false
	}
	pid, err := uuid.Parse(parts[1])
	if err != nil {
		return 0, uuid.Nil, false
	}
	return n, pid, true
}

// encodeChapterCursorUpdatedAt / parseChapterCursorUpdatedAt — CB7's ?sort=updated_at
// keyset cursor variant. A DISTINCT token shape from encodeChapterCursor's (sort_order,id)
// tuple (tagged "u|") so the two are never cross-decodable — a stale sort_order cursor
// reused after switching ?sort= would otherwise silently misdecode instead of cleanly
// failing. updated_at ties are broken by id DESC (see listChaptersKeyset's ORDER BY).
func encodeChapterCursorUpdatedAt(t time.Time, id uuid.UUID) string {
	return base64.RawURLEncoding.EncodeToString(fmt.Appendf(nil, "u|%s|%s", t.UTC().Format(time.RFC3339Nano), id.String()))
}

func parseChapterCursorUpdatedAt(s string) (t time.Time, id uuid.UUID, ok bool) {
	raw, err := base64.RawURLEncoding.DecodeString(s)
	if err != nil {
		return time.Time{}, uuid.Nil, false
	}
	parts := strings.SplitN(string(raw), "|", 3)
	if len(parts) != 3 || parts[0] != "u" {
		return time.Time{}, uuid.Nil, false
	}
	pt, err := time.Parse(time.RFC3339Nano, parts[1])
	if err != nil {
		return time.Time{}, uuid.Nil, false
	}
	pid, err := uuid.Parse(parts[2])
	if err != nil {
		return time.Time{}, uuid.Nil, false
	}
	return pt, pid, true
}

// listChaptersKeyset is the cursor-paged chapter list for the manuscript navigator, ordered by
// a strict keyset. id is a UUIDv7 (time-ordered) so pairing it with the primary sort key gives a
// total order with a stable, unique tiebreak — no offset drift as chapters are added/removed
// mid-scroll. Response: {items, next_cursor, total}. next_cursor is null on the last page;
// total is emitted only on the first page (no cursor) so the virtual scrollbar can size itself
// without a COUNT on every page.
//
// CB7: ?sort= is restricted to sort_order (default) and updated_at — the two keys with a
// genuinely stable total order to cursor over. word_count/lifecycle_state are NOT accepted
// here (400) — true cursor-stable paging over those needs a monotonic tiebreak scheme this
// v1 doesn't build; callers wanting those sorts use the offset-paginated listChapters instead
// (CB7 — an honest, documented restriction, not a silently-dropped feature).
func (s *Server) listChaptersKeyset(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	_, _, state, ok := s.authBook(w, r, bookID, GrantView)
	if !ok {
		return
	}
	sortParam := r.URL.Query().Get("sort")
	switch sortParam {
	case "", "sort_order", "updated_at":
		// ok
	default:
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "keyset pagination only supports sort=sort_order or sort=updated_at (word_count/lifecycle_state need offset pagination — see GET .../chapters)")
		return
	}
	byUpdatedAt := sortParam == "updated_at"
	lifecycle := r.URL.Query().Get("lifecycle_state")
	if lifecycle == "" {
		if state == "trashed" {
			lifecycle = "trashed"
		} else {
			lifecycle = "active"
		}
	}
	limit, _ := parseLimitOffset(r) // reuse the 1..100 clamp; offset is ignored in keyset mode
	if r.URL.Query().Get("limit") == "" {
		limit = 100 // a keyset page defaults to a full page, not the list default of 20
	}

	// Base filters (shared by the COUNT and the page query).
	args := []any{bookID, lifecycle}
	where := `book_id=$1 AND lifecycle_state=$2`
	if v := r.URL.Query().Get("original_language"); v != "" {
		args = append(args, v)
		where += fmt.Sprintf(" AND original_language=$%d", len(args))
	}
	if q := strings.TrimSpace(r.URL.Query().Get("q")); q != "" {
		if len([]rune(q)) > maxSearchQueryRunes {
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "query too long")
			return
		}
		args = append(args, escapeLikePattern(q))
		where += fmt.Sprintf(" AND (title ILIKE $%d OR original_filename ILIKE $%d)", len(args), len(args))
	}

	cursor := r.URL.Query().Get("cursor")
	// total only on the first page (cursor absent) — a single COUNT, cached by the client.
	var total any
	if cursor == "" {
		var n int
		_ = s.pool.QueryRow(r.Context(), `SELECT COUNT(*) FROM chapters WHERE `+where, append([]any{}, args...)...).Scan(&n)
		total = n
	} else if byUpdatedAt {
		cursorUpdated, cursorID, valid := parseChapterCursorUpdatedAt(cursor)
		if !valid {
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid cursor")
			return
		}
		// ORDER BY updated_at DESC, id DESC ⇒ "comes after" means a strictly
		// SMALLER (updated_at, id) tuple (both descending) — see doc comment.
		args = append(args, cursorUpdated, cursorID)
		where += fmt.Sprintf(" AND (updated_at, id) < ($%d, $%d)", len(args)-1, len(args))
	} else {
		cursorSort, cursorID, valid := parseChapterCursor(cursor)
		if !valid {
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid cursor")
			return
		}
		// Strictly after (cursorSort, cursorID) — row-value comparison, matching the ORDER BY.
		args = append(args, cursorSort, cursorID)
		where += fmt.Sprintf(" AND (sort_order, id) > ($%d, $%d)", len(args)-1, len(args))
	}

	orderBy := "sort_order, id"
	if byUpdatedAt {
		orderBy = "updated_at DESC, id DESC"
	}

	// Fetch limit+1 to detect a further page without a second COUNT.
	args = append(args, limit+1)
	rows, err := s.pool.Query(r.Context(), `SELECT id,book_id,title,original_filename,original_language,content_type,byte_size,sort_order,draft_updated_at,draft_revision_count,lifecycle_state,trashed_at,purge_eligible_at,created_at,updated_at,word_count,editorial_status,published_revision_id,part_id FROM chapters WHERE `+where+` ORDER BY `+orderBy+` LIMIT $`+strconv.Itoa(len(args)), args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "CHAPTER_NOT_FOUND", "failed to list chapters")
		return
	}
	defer rows.Close()
	items := make([]map[string]any, 0, limit)
	for rows.Next() {
		var id, bid uuid.UUID
		var title *string // NULLABLE — scan into a pointer, else a titleless chapter errors the Scan and zeroes every later column (part_id included). See listChapters / getChapterByID.
		var fn, lang, ctype, lstate, editorialStatus string
		var size int64
		var order, wordCount int
		var draftUpdated, trashedAt, purgeAt, createdAt, updatedAt *time.Time
		var revCount int
		var publishedRevisionID *uuid.UUID
		var partID *uuid.UUID // S-02: the act this chapter is homed in (NULL = flat). The navigator (useManuscriptTree) groups on it.
		_ = rows.Scan(&id, &bid, &title, &fn, &lang, &ctype, &size, &order, &draftUpdated, &revCount, &lstate, &trashedAt, &purgeAt, &createdAt, &updatedAt, &wordCount, &editorialStatus, &publishedRevisionID, &partID)
		items = append(items, map[string]any{
			"chapter_id":            id,
			"book_id":               bid,
			"title":                 nullableStringPtr(title),
			"original_filename":     fn,
			"original_language":     lang,
			"content_type":          ctype,
			"byte_size":             size,
			"sort_order":            order,
			"draft_updated_at":      draftUpdated,
			"draft_revision_count":  revCount,
			"lifecycle_state":       lstate,
			"trashed_at":            trashedAt,
			"purge_eligible_at":     purgeAt,
			"created_at":            createdAt,
			"updated_at":            updatedAt,
			"word_count":            wordCount,
			"editorial_status":      editorialStatus,
			"published_revision_id": publishedRevisionID,
			"part_id":               partID,
		})
	}

	// The extra (limit+1)th row means there IS a next page → drop it, emit the cursor of the
	// last KEPT item so the next request starts strictly after it.
	var nextCursor any
	if len(items) > limit {
		items = items[:limit]
		last := items[limit-1]
		if byUpdatedAt {
			nextCursor = encodeChapterCursorUpdatedAt(*last["updated_at"].(*time.Time), last["chapter_id"].(uuid.UUID))
		} else {
			nextCursor = encodeChapterCursor(last["sort_order"].(int), last["chapter_id"].(uuid.UUID))
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"items":       items,
		"next_cursor": nextCursor,
		"total":       total,
	})
}

func (s *Server) createChapter(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	caller, owner, lifecycle, ok := s.authBook(w, r, bookID, GrantEdit)
	if !ok {
		return
	}
	if lifecycle != "active" {
		writeError(w, http.StatusConflict, "CHAPTER_INVALID_LIFECYCLE", "parent book is not active")
		return
	}
	contentType := strings.ToLower(r.Header.Get("Content-Type"))
	switch {
	case strings.HasPrefix(contentType, "application/json"):
		var in struct {
			Title            string `json:"title"`
			OriginalLanguage string `json:"original_language"`
			SortOrder        int    `json:"sort_order"`
			Body             string `json:"body"`
		}
		if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid payload")
			return
		}
		if strings.TrimSpace(in.OriginalLanguage) == "" {
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "original_language is required")
			return
		}
		filename := fmt.Sprintf("editor-%s.txt", uuid.NewString())
		s.createChapterRecord(w, r.Context(), caller, owner, bookID, in.Title, filename, in.OriginalLanguage, in.SortOrder, in.Body, "seed from editor", true)
		return
	default:
		if err := r.ParseMultipartForm(50 << 20); err != nil {
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid multipart")
			return
		}
		lang := r.FormValue("original_language")
		if lang == "" {
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "original_language is required")
			return
		}
		f, fh, err := r.FormFile("file")
		if err != nil {
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "file is required")
			return
		}
		defer f.Close()
		if ct := fh.Header.Get("Content-Type"); !strings.Contains(ct, "text/plain") {
			writeError(w, http.StatusUnsupportedMediaType, "UNSUPPORTED_MEDIA_TYPE", "chapter must be text/plain")
			return
		}
		data, _ := io.ReadAll(f)
		title := r.FormValue("title")
		sortOrder := 0
		if v := r.FormValue("sort_order"); v != "" {
			sortOrder, _ = strconv.Atoi(v)
		}
		s.createChapterRecord(w, r.Context(), caller, owner, bookID, title, fh.Filename, lang, sortOrder, string(data), "seed from upload", true)
	}
}

// createChapterRecord — E0-2: `caller` is the author (revision attribution);
// `owner` is the book owner whose storage quota the content bills (an editing
// collaborator must NOT be charged, and the owner's quota is the real ceiling).
func (s *Server) createChapterRecord(
	w http.ResponseWriter,
	ctx context.Context,
	caller uuid.UUID,
	owner uuid.UUID,
	bookID uuid.UUID,
	title string,
	originalFilename string,
	lang string,
	sortOrder int,
	body string,
	revisionMessage string,
	includeRaw bool,
) {
	if sortOrder == 0 {
		_ = s.pool.QueryRow(ctx, `SELECT COALESCE(MAX(sort_order),0)+1 FROM chapters WHERE book_id=$1`, bookID).Scan(&sortOrder)
	}
	_ = s.ensureQuotaRow(ctx, owner)
	var used, quota int64
	_ = s.recalcQuota(ctx, owner)
	_ = s.pool.QueryRow(ctx, `SELECT used_bytes, quota_bytes FROM user_storage_quota WHERE owner_user_id=$1`, owner).Scan(&used, &quota)
	if used+int64(len(body)) > quota {
		writeError(w, http.StatusInsufficientStorage, "STORAGE_QUOTA_EXCEEDED", "quota exceeded")
		return
	}
	// Convert plain text → Tiptap JSON with _text snapshots
	jsonBody := plainTextToTiptapJSON(body)
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to create chapter")
		return
	}
	defer tx.Rollback(ctx)
	var chapterID uuid.UUID
	err = tx.QueryRow(ctx, `
INSERT INTO chapters(book_id,title,original_filename,original_language,content_type,byte_size,sort_order,storage_key,lifecycle_state,draft_updated_at,updated_at)
VALUES($1,$2,$3,$4,'text/plain',$5,$6,$7,'active',now(),now())
RETURNING id
`, bookID, nullIfEmpty(title), originalFilename, lang, int64(len(body)), sortOrder, fmt.Sprintf("chapters/%s/%s", bookID, uuid.New())).Scan(&chapterID)
	if err != nil {
		writeError(w, http.StatusConflict, "BOOK_CONFLICT", "duplicate sort/language or invalid chapter")
		return
	}
	if includeRaw {
		_, _ = tx.Exec(ctx, `INSERT INTO chapter_raw_objects(chapter_id, body_text) VALUES($1,$2)`, chapterID, body)
	}
	_, _ = tx.Exec(ctx, `INSERT INTO chapter_drafts(chapter_id, body, draft_format, draft_updated_at, draft_version) VALUES($1,$2,'json',now(),1)`, chapterID, jsonBody)
	_, _ = tx.Exec(ctx, `INSERT INTO chapter_revisions(chapter_id, body, body_format, message, author_user_id) VALUES($1,$2,$3,$4,$5)`, chapterID, jsonBody, "json", revisionMessage, caller)
	_, _ = tx.Exec(ctx, `UPDATE chapters SET draft_revision_count=1 WHERE id=$1`, chapterID)
	if err := insertOutboxEvent(ctx, tx, "chapter.created", chapterID, map[string]any{"book_id": bookID}); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to commit chapter")
		return
	}
	if err := tx.Commit(ctx); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to commit chapter")
		return
	}
	_ = s.recalcQuota(ctx, owner)
	s.getChapterByID(w, ctx, bookID, chapterID, caller, http.StatusCreated)
}

func nullIfEmpty(v string) any {
	if strings.TrimSpace(v) == "" {
		return nil
	}
	return v
}

func (s *Server) getChapter(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}
	caller, _, _, ok := s.authBook(w, r, bookID, GrantView)
	if !ok {
		return
	}
	s.getChapterByID(w, r.Context(), bookID, chID, caller, http.StatusOK)
}

// getChapterByID is a response-builder; callers MUST pre-check the grant
// (authBook). E0-2 dropped the owner filter — the query is keyed by chapter+book
// id, which still scopes to the authorized book. `caller` is unused in the query
// now but kept in the signature for call-site symmetry / future per-caller fields.
// getChapterByID writes the canonical chapter JSON. `extra` (variadic, at most
// one map) is merged into the response envelope — the publish path uses it to
// carry the 26 IX-4 `reparse` delta counts as an additive field without forking
// this shared reader. Existing callers pass no extra and are unaffected.
func (s *Server) getChapterByID(w http.ResponseWriter, ctx context.Context, bookID, chapterID, caller uuid.UUID, status int, extra ...map[string]any) {
	_ = caller
	var id, bid uuid.UUID
	var title *string // chapters.title is NULLABLE — a plain string errors on a titleless chapter
	var fn, lang, ctype, state, editorialStatus string
	var size int64
	var order, revCount, wordCount int
	var draftUpdated, trashedAt, purgeAt, createdAt, updatedAt *time.Time
	var publishedRevID *uuid.UUID
	// WS-0.9: the KG markers ride the public chapter read. Without them the editor
	// cannot render the "in your knowledge" state at all — an invisible knowledge graph
	// is one the user can neither trust nor correct.
	var kgIndexedRevID *uuid.UUID
	var kgExclude bool
	var partID *uuid.UUID // S-02: which act (parts row) this chapter is homed in; NULL = flat manuscript
	err := s.pool.QueryRow(ctx, `
SELECT c.id,c.book_id,c.title,c.original_filename,c.original_language,c.content_type,c.byte_size,c.sort_order,c.draft_updated_at,c.draft_revision_count,c.lifecycle_state,c.trashed_at,c.purge_eligible_at,c.created_at,c.updated_at,c.editorial_status,c.published_revision_id,c.kg_indexed_revision_id,c.kg_exclude,c.word_count,c.part_id
FROM chapters c
WHERE c.id=$1 AND c.book_id=$2
`, chapterID, bookID).Scan(&id, &bid, &title, &fn, &lang, &ctype, &size, &order, &draftUpdated, &revCount, &state, &trashedAt, &purgeAt, &createdAt, &updatedAt, &editorialStatus, &publishedRevID, &kgIndexedRevID, &kgExclude, &wordCount, &partID)
	if errors.Is(err, pgx.ErrNoRows) || state == "purge_pending" {
		writeError(w, http.StatusNotFound, "CHAPTER_NOT_FOUND", "chapter not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "CHAPTER_NOT_FOUND", "failed to get chapter")
		return
	}
	resp := map[string]any{
		"chapter_id":            id,
		"book_id":               bid,
		"title":                 nullableStringPtr(title),
		"original_filename":     fn,
		"original_language":     lang,
		"content_type":          ctype,
		"byte_size":             size,
		"sort_order":            order,
		"draft_updated_at":      draftUpdated,
		"draft_revision_count":  revCount,
		"lifecycle_state":       state,
		"trashed_at":            trashedAt,
		"purge_eligible_at":     purgeAt,
		"created_at":            createdAt,
		"updated_at":            updatedAt,
		"editorial_status":      editorialStatus,
		"published_revision_id": publishedRevID,
		// WS-0.9 — "is this chapter in my knowledge graph?" is now a DIFFERENT question
		// from "is it published", so the editor needs both markers.
		"kg_indexed_revision_id": kgIndexedRevID,
		"kg_exclude":             kgExclude,
		"word_count":             wordCount,
		"part_id":                partID,
	}
	if len(extra) > 0 {
		for k, v := range extra[0] {
			resp[k] = v
		}
	}
	writeJSON(w, status, resp)
}

func (s *Server) patchChapter(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}
	caller, _, _, ok := s.authBook(w, r, bookID, GrantEdit)
	if !ok {
		return
	}
	var in map[string]any
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid payload")
		return
	}
	var bState, cState string
	err := s.pool.QueryRow(r.Context(), `
SELECT b.lifecycle_state,c.lifecycle_state
FROM books b JOIN chapters c ON c.book_id=b.id
WHERE b.id=$1 AND c.id=$2
`, bookID, chID).Scan(&bState, &cState)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "CHAPTER_NOT_FOUND", "chapter not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "CHAPTER_NOT_FOUND", "failed to patch chapter")
		return
	}
	if bState != "active" || cState != "active" {
		writeError(w, http.StatusConflict, "CHAPTER_INVALID_LIFECYCLE", "parent book not active or chapter not patchable")
		return
	}
	_, err = s.pool.Exec(r.Context(), `
UPDATE chapters
SET title=COALESCE($3,title),
    sort_order=COALESCE($4,sort_order),
    original_language=COALESCE($5,original_language),
    updated_at=now()
WHERE id=$1 AND book_id=$2
`, chID, bookID, stringFromAny(in["title"]), intFromAny(in["sort_order"]), stringFromAny(in["original_language"]))
	if err != nil {
		writeError(w, http.StatusConflict, "BOOK_CONFLICT", "failed to patch chapter")
		return
	}
	s.getChapterByID(w, r.Context(), bookID, chID, caller, http.StatusOK)
}

func intFromAny(v any) any {
	switch x := v.(type) {
	case float64:
		return int(x)
	case int:
		return x
	default:
		return nil
	}
}

func (s *Server) trashChapter(w http.ResponseWriter, r *http.Request) {
	s.transitionChapterLifecycle(w, r, "trashed")
}
func (s *Server) restoreChapter(w http.ResponseWriter, r *http.Request) {
	s.transitionChapterLifecycle(w, r, "active")
}
func (s *Server) purgeChapter(w http.ResponseWriter, r *http.Request) {
	s.transitionChapterLifecycle(w, r, "purge_pending")
}

// errChapterNotFound / errInvalidLifecycle — sentinel errors from
// transitionOneChapterLifecycle so callers (the single-chapter HTTP handler
// AND the A3 bulk-status handler) can map them to their own response shape
// (a single HTTP status for one chapter; a per-id outcome for a batch)
// without the shared helper knowing about either caller's response format.
var (
	errChapterNotFound  = errors.New("chapter not found")
	errInvalidLifecycle = errors.New("invalid lifecycle transition")
)

// chapterLifecycleNeed returns the grant level a lifecycle transition needs.
// Trash/restore are reversible content edits → edit; purge is irreversible
// whole-chapter removal → manage (PO-locked CLARIFY 2026-06-11). Shared by the
// single-chapter route and the A3 bulk-status endpoint so the two can't drift.
func chapterLifecycleNeed(target string) GrantLevel {
	if target == "purge_pending" {
		return GrantManage
	}
	return GrantEdit
}

// transitionOneChapterLifecycle applies ONE chapter's lifecycle transition
// (trashed/active/purge_pending) — state validation, the UPDATE, and outbox
// event emission where applicable. Extracted from transitionChapterLifecycle
// (B-A3) so the per-chapter route and the bulk status-change endpoint
// (bulkUpdateChapterStatus) share one implementation and can never diverge on
// what counts as a valid transition. Callers MUST have already authorized the
// caller (authBook) at chapterLifecycleNeed(target) — this function does not
// re-check the grant, only the book/chapter's current lifecycle state.
func (s *Server) transitionOneChapterLifecycle(ctx context.Context, bookID, chID uuid.UUID, target string) error {
	var bState, cState string
	err := s.pool.QueryRow(ctx, `
SELECT b.lifecycle_state,c.lifecycle_state FROM books b JOIN chapters c ON c.book_id=b.id
WHERE b.id=$1 AND c.id=$2
`, bookID, chID).Scan(&bState, &cState)
	if errors.Is(err, pgx.ErrNoRows) {
		return errChapterNotFound
	}
	if err != nil {
		return fmt.Errorf("failed to transition chapter: %w", err)
	}
	switch target {
	case "trashed":
		if bState != "active" || cState != "active" {
			return errInvalidLifecycle
		}
		tx, txErr := s.pool.Begin(ctx)
		if txErr != nil {
			return fmt.Errorf("failed to trash chapter: %w", txErr)
		}
		defer tx.Rollback(ctx) //nolint:errcheck
		if _, err := tx.Exec(ctx, `UPDATE chapters SET lifecycle_state='trashed', trashed_at=now(), updated_at=now() WHERE id=$1`, chID); err != nil {
			return fmt.Errorf("failed to trash chapter: %w", err)
		}
		if err := insertOutboxEvent(ctx, tx, "chapter.trashed", chID, map[string]any{"book_id": bookID}); err != nil {
			return fmt.Errorf("failed to trash chapter: %w", err)
		}
		if err := tx.Commit(ctx); err != nil {
			return fmt.Errorf("failed to trash chapter: %w", err)
		}
		return nil
	case "active":
		if bState != "active" || cState != "trashed" {
			return errInvalidLifecycle
		}
		if _, err := s.pool.Exec(ctx, `UPDATE chapters SET lifecycle_state='active', trashed_at=NULL, purge_eligible_at=NULL, updated_at=now() WHERE id=$1`, chID); err != nil {
			return fmt.Errorf("failed to restore chapter: %w", err)
		}
		return nil
	case "purge_pending":
		if cState != "trashed" {
			return errInvalidLifecycle
		}
		tx, txErr := s.pool.Begin(ctx)
		if txErr != nil {
			return fmt.Errorf("failed to purge chapter: %w", txErr)
		}
		defer tx.Rollback(ctx) //nolint:errcheck
		if _, err := tx.Exec(ctx, `UPDATE chapters SET lifecycle_state='purge_pending', purge_eligible_at=now(), updated_at=now() WHERE id=$1`, chID); err != nil {
			return fmt.Errorf("failed to purge chapter: %w", err)
		}
		if err := insertOutboxEvent(ctx, tx, "chapter.deleted", chID, map[string]any{"book_id": bookID}); err != nil {
			return fmt.Errorf("failed to purge chapter: %w", err)
		}
		if err := tx.Commit(ctx); err != nil {
			return fmt.Errorf("failed to purge chapter: %w", err)
		}
		return nil
	default:
		return fmt.Errorf("unsupported lifecycle_state %q", target)
	}
}

func (s *Server) transitionChapterLifecycle(w http.ResponseWriter, r *http.Request, target string) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}
	caller, _, _, ok := s.authBook(w, r, bookID, chapterLifecycleNeed(target))
	if !ok {
		return
	}
	err := s.transitionOneChapterLifecycle(r.Context(), bookID, chID, target)
	switch {
	case errors.Is(err, errChapterNotFound):
		writeError(w, http.StatusNotFound, "CHAPTER_NOT_FOUND", "chapter not found")
		return
	case errors.Is(err, errInvalidLifecycle):
		msg := "invalid lifecycle for transition"
		switch target {
		case "trashed":
			msg = "invalid lifecycle for trash"
		case "active":
			msg = "chapter not trashed or book inactive"
		case "purge_pending":
			msg = "chapter must be trashed before purge"
		}
		writeError(w, http.StatusConflict, "CHAPTER_INVALID_LIFECYCLE", msg)
		return
	case err != nil:
		// Any other failure (the lifecycle-state lookup, or a downstream
		// write/outbox/commit) — a generic 500. transitionOneChapterLifecycle's
		// wrapped error message already names the specific step for logs.
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to transition chapter")
		return
	}
	switch target {
	case "trashed", "purge_pending":
		w.WriteHeader(http.StatusNoContent)
	case "active":
		s.getChapterByID(w, r.Context(), bookID, chID, caller, http.StatusOK)
	}
}

// maxBulkChapterIDs caps a single bulk request's chapter_ids — both A3
// (bulk-status) and A4 (bulk zip export). 500 matches the existing offset
// pagination cap (parseLimitOffset's max=100 page ×5, comfortably above any
// realistic multi-select in the chapter-browser UI) while bounding one
// request's blast radius/latency.
const maxBulkChapterIDs = 500

// bulkChapterStatusOutcome — one requested chapter_id's result. CB5: the bulk
// endpoint NEVER reports a single all-or-nothing success/fail for the whole
// batch — a partial failure across N chapters must be visible per-id, never
// silently swallowed.
type bulkChapterStatusOutcome struct {
	ChapterID string `json:"chapter_id"`
	OK        bool   `json:"ok"`
	Error     string `json:"error,omitempty"`
}

// bulkUpdateChapterStatus — PATCH /v1/books/{book_id}/chapters/bulk-status
// (A3). Body: {"chapter_ids": string[], "lifecycle_state": "trashed"|"active"|"purge_pending"}.
// Response: {"results": [{"chapter_id","ok","error?"}, ...]} — always 200 with
// a per-id outcome array (CB5); the endpoint itself only 4xx/5xxs on a
// request-level problem (bad payload, no grant, cap exceeded), never because
// one of N chapter_ids failed.
//
// Tenancy (judgment call — see final report): the grant check is done ONCE
// against the book (same authBook chokepoint every single-chapter lifecycle
// route already uses, at the SAME grant level chapterLifecycleNeed(target)
// requires), not loosened "because it's bulk". Each chapter_id is still
// existence-scoped to THIS book_id inside transitionOneChapterLifecycle's own
// query (`WHERE b.id=$1 AND c.id=$2`), so a chapter_id from a different book
// can't be smuggled into the batch — it just comes back as a per-id
// "chapter not found" outcome, identical to the single-chapter route's 404.
func (s *Server) bulkUpdateChapterStatus(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	var in struct {
		ChapterIDs     []string `json:"chapter_ids"`
		LifecycleState string   `json:"lifecycle_state"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid payload")
		return
	}
	if len(in.ChapterIDs) == 0 {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "chapter_ids is required")
		return
	}
	if len(in.ChapterIDs) > maxBulkChapterIDs {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", fmt.Sprintf("too many chapter_ids (max %d)", maxBulkChapterIDs))
		return
	}
	switch in.LifecycleState {
	case "trashed", "active", "purge_pending":
		// ok
	default:
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "lifecycle_state must be trashed, active, or purge_pending")
		return
	}
	target := in.LifecycleState
	if _, _, _, ok := s.authBook(w, r, bookID, chapterLifecycleNeed(target)); !ok {
		return
	}

	results := make([]bulkChapterStatusOutcome, 0, len(in.ChapterIDs))
	for _, raw := range in.ChapterIDs {
		chID, perr := uuid.Parse(raw)
		if perr != nil {
			results = append(results, bulkChapterStatusOutcome{ChapterID: raw, OK: false, Error: "invalid chapter_id"})
			continue
		}
		switch err := s.transitionOneChapterLifecycle(r.Context(), bookID, chID, target); {
		case err == nil:
			results = append(results, bulkChapterStatusOutcome{ChapterID: raw, OK: true})
		case errors.Is(err, errChapterNotFound):
			results = append(results, bulkChapterStatusOutcome{ChapterID: raw, OK: false, Error: "chapter not found"})
		case errors.Is(err, errInvalidLifecycle):
			results = append(results, bulkChapterStatusOutcome{ChapterID: raw, OK: false, Error: "invalid lifecycle for this transition"})
		default:
			results = append(results, bulkChapterStatusOutcome{ChapterID: raw, OK: false, Error: "failed to update chapter"})
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{"results": results})
}

func (s *Server) getChapterContent(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}
	caller, owner, _, ok := s.authBook(w, r, bookID, GrantView)
	if !ok {
		return
	}
	var body string
	var encrypted bool
	err := s.pool.QueryRow(r.Context(), `
SELECT ro.body_text, c.body_encrypted
FROM chapter_raw_objects ro
JOIN chapters c ON c.id=ro.chapter_id
WHERE c.id=$1 AND c.book_id=$2
`, chID, bookID).Scan(&body, &encrypted)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "CHAPTER_NOT_FOUND", "chapter not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "CHAPTER_NOT_FOUND", "failed to fetch content")
		return
	}
	// D-DIARY-GENERIC-READERS-DECRYPT — a diary chapter is stored as ciphertext in chapter_raw_objects;
	// this generic reader would otherwise return base64 NOISE. Decrypt it owner-gated. A diary is
	// un-shareable, so any encrypted-chapter read by a non-owner is an anomaly — refuse defensively
	// (never decrypt the owner's diary for a collaborator). decryptBody fails CLOSED if crypto is
	// disabled while the row is marked encrypted (never returns the raw ciphertext).
	if encrypted {
		if caller != owner {
			writeError(w, http.StatusForbidden, "DIARY_OWNER_ONLY", "diary content is readable only by its owner")
			return
		}
		dec, derr := s.diaryCrypto.decryptBody(r.Context(), owner, chID, body, true)
		if derr != nil {
			writeError(w, http.StatusInternalServerError, "DECRYPT_FAILED", "failed to decrypt diary content")
			return
		}
		body = dec
	}
	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(body))
}

func (s *Server) exportChapter(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}
	if _, _, _, ok := s.authBook(w, r, bookID, GrantView); !ok {
		return
	}
	var originalFilename string
	var title *string
	err := s.pool.QueryRow(r.Context(), `
SELECT c.title, c.original_filename
FROM chapters c
WHERE c.id=$1 AND c.book_id=$2
`, chID, bookID).Scan(&title, &originalFilename)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "CHAPTER_NOT_FOUND", "chapter not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "CHAPTER_EXPORT_FAILED", "failed to fetch chapter")
		return
	}
	textContent, err := s.fetchChapterExportText(r.Context(), chID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "CHAPTER_EXPORT_FAILED", "failed to fetch draft")
		return
	}
	filename := "chapter.txt"
	if title != nil && *title != "" {
		filename = *title + ".txt"
	} else if originalFilename != "" {
		filename = originalFilename
	}
	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	w.Header().Set("Content-Disposition", `attachment; filename="`+filename+`"`)
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(textContent))
}

// fetchChapterExportText returns the export-ready plain text for ONE chapter:
// the aggregated chapter_blocks.text_content (trigger-extracted), falling
// back to the raw chapter_drafts.body when no blocks exist yet (legacy data
// pre-dating the extraction trigger). Extracted verbatim from exportChapter's
// prior inline logic (A4 — do not duplicate this read for the bulk zip
// export; both call this ONE helper so the two paths can't drift on what
// "chapter text" means).
func (s *Server) fetchChapterExportText(ctx context.Context, chID uuid.UUID) (string, error) {
	var textContent string
	err := s.pool.QueryRow(ctx, `
SELECT string_agg(text_content, E'\n\n' ORDER BY block_index)
FROM chapter_blocks WHERE chapter_id=$1
`, chID).Scan(&textContent)
	// TrimSpace, not ==: blocks can exist with every text_content empty/NULL
	// (stale extraction — see D-CHAPTER-BLOCKS-STALE-EXTRACTION), in which case
	// string_agg still returns a non-empty string of bare "\n\n" separators.
	// A raw == "" check never falls back for that case and silently exports
	// whitespace garbage instead of the real chapter_drafts.body text.
	if err != nil || strings.TrimSpace(textContent) == "" {
		// Fallback: no blocks yet (legacy data), read raw draft body as text.
		var rawBody []byte
		if ferr := s.pool.QueryRow(ctx, `SELECT d.body FROM chapter_drafts d WHERE d.chapter_id=$1`, chID).Scan(&rawBody); ferr != nil {
			return "", ferr
		}
		textContent = string(rawBody)
	}
	return textContent, nil
}

// bulkExportChapters — POST /v1/books/{book_id}/chapters/export-zip (A4). Body:
// {"chapter_ids": string[]}. Streams a real application/zip (Go stdlib
// archive/zip, no new dependency) with one "<sort_order>-<name>.txt" entry per
// FOUND, accessible chapter — reusing fetchChapterExportText, the SAME source
// exportChapter reads (chapter_blocks, fallback chapter_drafts.body).
//
// POST-with-body (not GET+query) — spec's own call: a large multi-select could
// carry hundreds of UUIDs (500 ids × 36 chars ≈ 18KB), well past many
// browsers'/proxies' default URL-length limits; POST has no such ceiling and
// matches A3's bulk-status body shape for FE consistency.
//
// Partial-failure discipline (CB5's spirit, adapted to a binary response): a
// zip stream can't carry a JSON per-id outcome alongside its bytes, so any
// requested chapter_id that doesn't resolve (bad UUID caught before headers
// are written → 400; not found/not in this book/export failure discovered
// mid-stream) is never silently dropped — it's listed in a "_errors.txt" entry
// baked into the archive itself, so the failure is visible in the downloaded
// artifact rather than swallowed.
func (s *Server) bulkExportChapters(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	var in struct {
		ChapterIDs []string `json:"chapter_ids"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid payload")
		return
	}
	if len(in.ChapterIDs) == 0 {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "chapter_ids is required")
		return
	}
	if len(in.ChapterIDs) > maxBulkChapterIDs {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", fmt.Sprintf("too many chapter_ids (max %d)", maxBulkChapterIDs))
		return
	}
	ids := make([]uuid.UUID, 0, len(in.ChapterIDs))
	for _, raw := range in.ChapterIDs {
		id, perr := uuid.Parse(raw)
		if perr != nil {
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid chapter_id: "+raw)
			return
		}
		ids = append(ids, id)
	}

	// Export is a read — GrantView matches the single-chapter exportChapter's
	// own requirement (no tighter/looser check "because it's bulk").
	if _, _, _, ok := s.authBook(w, r, bookID, GrantView); !ok {
		return
	}

	type chapterMeta struct {
		title     *string
		filename  string
		sortOrder int
	}
	metas := make(map[uuid.UUID]chapterMeta, len(ids))
	rows, err := s.pool.Query(r.Context(), `
SELECT id, title, original_filename, sort_order
FROM chapters WHERE book_id=$1 AND id = ANY($2)
`, bookID, ids)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "CHAPTER_EXPORT_FAILED", "failed to fetch chapters")
		return
	}
	for rows.Next() {
		var id uuid.UUID
		var m chapterMeta
		if err := rows.Scan(&id, &m.title, &m.filename, &m.sortOrder); err != nil {
			rows.Close()
			writeError(w, http.StatusInternalServerError, "CHAPTER_EXPORT_FAILED", "failed to read chapter")
			return
		}
		metas[id] = m
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "CHAPTER_EXPORT_FAILED", "failed to read chapters")
		return
	}

	w.Header().Set("Content-Type", "application/zip")
	w.Header().Set("Content-Disposition", `attachment; filename="chapters-export.zip"`)
	w.WriteHeader(http.StatusOK)

	zw := zip.NewWriter(w)
	defer zw.Close()

	var missing []string
	usedNames := make(map[string]int, len(ids))
	for i, id := range ids {
		m, found := metas[id]
		if !found {
			missing = append(missing, in.ChapterIDs[i]+" (not found or not in this book)")
			continue
		}
		text, terr := s.fetchChapterExportText(r.Context(), id)
		if terr != nil {
			missing = append(missing, in.ChapterIDs[i]+" (export failed)")
			continue
		}
		name := zipEntryName(m.sortOrder, m.title, m.filename)
		if n := usedNames[name]; n > 0 {
			usedNames[name] = n + 1
			name = strings.TrimSuffix(name, ".txt") + fmt.Sprintf("-%d.txt", n)
		} else {
			usedNames[name] = 1
		}
		fw, ferr := zw.Create(name)
		if ferr != nil {
			continue
		}
		_, _ = fw.Write([]byte(text))
	}
	if len(missing) > 0 {
		if fw, ferr := zw.Create("_errors.txt"); ferr == nil {
			_, _ = fw.Write([]byte("The following requested chapter_ids could not be exported:\n" + strings.Join(missing, "\n") + "\n"))
		}
	}
}

// zipUnsafeChars replaces filesystem-unsafe characters in a chapter title/
// filename before it becomes a zip entry name.
var zipUnsafeChars = strings.NewReplacer(
	"/", "-", "\\", "-", ":", "-", "*", "-", "?", "-", `"`, "'", "<", "-", ">", "-", "|", "-",
)

// zipEntryName builds a unique-enough, human-readable zip entry name:
// "<sort_order zero-padded>-<sanitized title-or-filename>.txt". The sort_order
// prefix (a) guarantees natural reading order when the archive is extracted
// and listed alphabetically, and (b) is the FIRST de-dupe line of defense
// (chapters in one book have distinct sort_order); bulkExportChapters' caller
// still de-dupes exact-name collisions on top (two chapters CAN share both
// sort_order-formatting and a sanitized title in edge cases).
func zipEntryName(sortOrder int, title *string, filename string) string {
	base := filename
	if title != nil && strings.TrimSpace(*title) != "" {
		base = *title
	}
	base = strings.TrimSpace(zipUnsafeChars.Replace(base))
	if base == "" {
		base = "chapter"
	}
	if !strings.HasSuffix(strings.ToLower(base), ".txt") {
		base += ".txt"
	}
	return fmt.Sprintf("%04d-%s", sortOrder, base)
}

func (s *Server) getDraft(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}
	if _, _, _, ok := s.authBook(w, r, bookID, GrantView); !ok {
		return
	}
	var chapterID uuid.UUID
	var body json.RawMessage
	var format string
	var updated time.Time
	var version int64
	err := s.pool.QueryRow(r.Context(), `
SELECT d.chapter_id,d.body,d.draft_format,d.draft_updated_at,d.draft_version
FROM chapter_drafts d
JOIN chapters c ON c.id=d.chapter_id
WHERE d.chapter_id=$1 AND c.book_id=$2
`, chID, bookID).Scan(&chapterID, &body, &format, &updated, &version)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "CHAPTER_NOT_FOUND", "draft not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to get draft")
		return
	}
	var textContent *string
	_ = s.pool.QueryRow(r.Context(), `
SELECT string_agg(text_content, E'\n\n' ORDER BY block_index)
FROM chapter_blocks WHERE chapter_id=$1
`, chID).Scan(&textContent)
	writeJSON(w, http.StatusOK, map[string]any{
		"chapter_id":       chapterID,
		"body":             body,
		"draft_format":     format,
		"draft_updated_at": updated,
		"draft_version":    version,
		"text_content":     textContent,
	})
}

func (s *Server) patchDraft(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}
	caller, _, _, ok := s.authBook(w, r, bookID, GrantEdit)
	if !ok {
		return
	}
	var in struct {
		Body                 json.RawMessage `json:"body"`
		BodyFormat           string          `json:"body_format"`
		CommitMessage        string          `json:"commit_message"`
		ExpectedDraftVersion *int64          `json:"expected_draft_version"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil || len(in.Body) == 0 {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "body is required")
		return
	}
	if !json.Valid(in.Body) {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "body must be valid JSON")
		return
	}
	if in.BodyFormat == "" {
		in.BodyFormat = "json"
	}
	// Universal formatter: normalize a plain/markdown body into canonical Tiptap
	// blocks (read mode + the chapter_blocks trigger + glossary extraction all read
	// the doc via JSON_TABLE). A 'json' body is passed through. Without this, a
	// markdown/plain string is stored verbatim and renders blank / crashes extraction.
	in.Body, in.BodyFormat = normalizeBodyToTiptap(in.Body, in.BodyFormat)
	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to patch draft")
		return
	}
	defer tx.Rollback(r.Context())
	var curr int64
	err = tx.QueryRow(r.Context(), `
SELECT d.draft_version
FROM chapter_drafts d
JOIN chapters c ON c.id=d.chapter_id
WHERE d.chapter_id=$1 AND c.book_id=$2
`, chID, bookID).Scan(&curr)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "CHAPTER_NOT_FOUND", "draft not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to patch draft")
		return
	}
	if in.ExpectedDraftVersion != nil && *in.ExpectedDraftVersion != curr {
		writeError(w, http.StatusConflict, "CHAPTER_DRAFT_CONFLICT", "stale draft version")
		return
	}
	_, _ = tx.Exec(r.Context(), `UPDATE chapter_drafts SET body=$2,draft_format=$3,draft_updated_at=now(),draft_version=draft_version+1 WHERE chapter_id=$1`, chID, in.Body, in.BodyFormat)
	_, _ = tx.Exec(r.Context(), `INSERT INTO chapter_revisions(chapter_id, body, body_format, message, author_user_id) VALUES($1,$2,$3,$4,$5)`, chID, in.Body, in.BodyFormat, nullIfEmpty(in.CommitMessage), caller)
	_, _ = tx.Exec(r.Context(), `UPDATE chapters SET draft_updated_at=now(), draft_revision_count=draft_revision_count+1, updated_at=now() WHERE id=$1`, chID)
	if err := insertOutboxEvent(r.Context(), tx, "chapter.saved", chID, map[string]any{"book_id": bookID}); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to patch draft")
		return
	}
	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to patch draft")
		return
	}
	s.getDraft(w, r)
}

// publishChapter — Canon Model CM1. Snapshots the current draft as an immutable
// revision, pins it as published_revision_id, flips editorial_status to
// 'published', and emits chapter.published{book_id,chapter_id,revision_id}. This
// is the canonization gate: only published content is extracted into the KG
// (CM3). Owner-only; optimistic-concurrency via expected_draft_version → 409.
func (s *Server) publishChapter(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}
	caller, _, _, ok := s.authBook(w, r, bookID, GrantEdit)
	if !ok {
		return
	}
	var in struct {
		ExpectedDraftVersion *int64 `json:"expected_draft_version"`
	}
	// Body is optional; ignore decode errors (no/empty body → unconditional publish).
	_ = json.NewDecoder(r.Body).Decode(&in)

	// 26 IX-2: parse the to-be-pinned body BEFORE the Tx (stateless /internal/parse,
	// never a cross-service call inside the transaction). We compare prep.draftVersion
	// against the FOR-UPDATE draft_version inside the Tx: if a concurrent save
	// slipped in, the parsed tree describes a stale body → skip the upsert and let
	// the sweeper heal (the same OQ-1 degrade as a parse failure). A parse failure
	// itself never blocks publish.
	prep := s.prepareReparse(r.Context(), bookID, chID)

	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to publish")
		return
	}
	defer tx.Rollback(r.Context())

	var curr int64
	var body json.RawMessage
	var format string
	err = tx.QueryRow(r.Context(), `
SELECT d.draft_version, d.body, d.draft_format
FROM chapter_drafts d
JOIN chapters c ON c.id=d.chapter_id
WHERE d.chapter_id=$1 AND c.book_id=$2 AND c.lifecycle_state='active'
FOR UPDATE OF d
`, chID, bookID).Scan(&curr, &body, &format)
	if errors.Is(err, pgx.ErrNoRows) {
		// No draft (or not owner / not active) → nothing to publish.
		writeError(w, http.StatusNotFound, "CHAPTER_NOT_FOUND", "draft not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to publish")
		return
	}
	if in.ExpectedDraftVersion != nil && *in.ExpectedDraftVersion != curr {
		writeError(w, http.StatusConflict, "CHAPTER_DRAFT_CONFLICT", "stale draft version")
		return
	}

	// Empty-prose guard (B1.1) — canon must carry real text. Publishing a chapter
	// with no extractable prose would canonize nothing and run KG extraction on an
	// empty body. A chapter with no text (or whitespace-only) → 422, not a silent
	// no-op publish. Bodies come in TWO legitimate shapes: the editor save path
	// writes a top-level `_text` projection per node, while other writers (compose
	// POC import, plain tiptap PATCH) store standard tiptap with nested
	// `{"type":"text","text":…}` leaves and NO `_text` — the old `_text`-only
	// selector false-rejected those with CHAPTER_EMPTY_PUBLISH, blocking canon/KG
	// for every chapter not written through the editor. Union both extractions:
	// `_text` projections + any-depth `text` leaves ($.**.text).
	var prose string
	_ = tx.QueryRow(r.Context(), `
SELECT COALESCE((
  SELECT string_agg(t #>> '{}', '') FROM jsonb_path_query(($1)::jsonb, '$.content[*]._text') AS x(t)
), '') || COALESCE((
  SELECT string_agg(t #>> '{}', '') FROM jsonb_path_query(($1)::jsonb, '$.**.text') AS y(t)
), '')
`, body).Scan(&prose)
	if strings.TrimSpace(prose) == "" {
		writeError(w, http.StatusUnprocessableEntity, "CHAPTER_EMPTY_PUBLISH", "cannot publish a chapter with no content")
		return
	}

	// Always snapshot the current draft as an immutable revision and capture its
	// id — the canon spine depends on a REAL revision_id (no fire-and-forget).
	var revID uuid.UUID
	err = tx.QueryRow(r.Context(), `
INSERT INTO chapter_revisions(chapter_id, body, body_format, message, author_user_id)
VALUES($1,$2,$3,'publish',$4) RETURNING id
`, chID, body, format, caller).Scan(&revID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to snapshot revision")
		return
	}
	// WS-0.3: publish also advances the KG pointer (see mcp_actions.go for the full
	// rationale). kg_exclude is producer-side authoritative — publishing a chapter the
	// user excluded from their knowledge graph must not silently re-index it.
	// RETURNING kg_exclude — see the emit below (review-impl P0): the event, not the
	// pointer, is what drives the graph write, so the exclusion must ride the payload.
	var kgExcluded bool
	if err := tx.QueryRow(r.Context(), `
UPDATE chapters SET editorial_status='published', published_revision_id=$2,
       kg_indexed_revision_id=CASE WHEN kg_exclude THEN kg_indexed_revision_id ELSE $2 END,
       draft_revision_count=draft_revision_count+1, updated_at=now()
WHERE id=$1
RETURNING kg_exclude`, chID, revID).Scan(&kgExcluded); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to publish")
		return
	}
	// 26 IX-2 step 3(b–d): same-Tx re-parse. Only when the parse succeeded AND it
	// described the body we are actually pinning (draftVersion match). Otherwise
	// the marker stays behind → the chapter is stale by the IX-3 predicate and the
	// sweeper heals it. A parse/upsert issue must NOT hold user prose hostage
	// (OQ-1), so a skipped re-parse is a warning, never a publish failure.
	var counts reparseCounts
	if prep.ok && prep.draftVersion == curr {
		var uerr error
		counts, uerr = s.upsertChapterScenes(r.Context(), tx, bookID, chID, prep.structuralPath, prep.tree)
		if uerr != nil {
			writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to reindex scenes")
			return
		}
		if _, err := tx.Exec(r.Context(), `UPDATE chapters SET last_parsed_revision_id=$2 WHERE id=$1`, chID, revID); err != nil {
			writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to publish")
			return
		}
		// RB5-1: only emit when the INDEX actually changed. A no-op re-parse (identical
		// prose → all scenes Unchanged) must not fire chapter.scenes_reparsed, whose
		// knowledge consumer wipes the WHOLE book's extraction cache (a costly re-extract
		// for zero index change). chapter.published still fires for the publish itself.
		if counts.changed() {
			if err := emitScenesReparsed(r.Context(), tx, bookID, chID, revID, counts.ParseVersion); err != nil {
				writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to publish")
				return
			}
			// SC11-amendment Phase 0 — writer #2, and THE call site the census missed. Publish
			// is the most common re-parse of all, and a re-parse re-resolves every scene's
			// anchor, so the spec back-links may have moved. Same tx, same counts.changed() guard.
			if err := emitScenesLinked(r.Context(), tx, bookID, chID); err != nil {
				writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to publish")
				return
			}
		}
	} else {
		slog.WarnContext(r.Context(), "publish: re-parse skipped; index left stale for the sweeper",
			"chapter_id", chID, "parse_ok", prep.ok, "draft_version_match", prep.draftVersion == curr)
	}
	// review-impl P0: carry kg_exclude. Not setting the pointer above does NOT keep an
	// excluded chapter out of the knowledge graph — handle_chapter_published enqueues the
	// extraction and ingests canon passages, and it cannot see the column. Without this,
	// publishing a chapter the user asked us to forget silently re-indexes it.
	if err := insertOutboxEvent(r.Context(), tx, "chapter.published", chID,
		map[string]any{
			"book_id": bookID, "chapter_id": chID, "revision_id": revID, "kg_exclude": kgExcluded,
		}); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to publish")
		return
	}
	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to publish")
		return
	}
	s.getChapterByID(w, r.Context(), bookID, chID, caller, http.StatusOK, map[string]any{"reparse": counts})
}

// unpublishChapter — Canon Model CM1. Reverts a chapter to 'draft' and clears
// published_revision_id. NOTE: KG retraction of already-extracted canon is NOT
// wired here (deferred D-CM1-UNPUBLISH-RETRACT → CM3b wires
// remove_evidence_for_source on chapter.unpublished); until then stale KG facts
// linger. Owner-only.
func (s *Server) unpublishChapter(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}
	caller, _, _, ok := s.authBook(w, r, bookID, GrantEdit)
	if !ok {
		return
	}
	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to unpublish")
		return
	}
	defer tx.Rollback(r.Context())

	// authBook(edit) authorized; the update is keyed by id (owner subquery dropped).
	ct, err := tx.Exec(r.Context(), `
UPDATE chapters SET editorial_status='draft', published_revision_id=NULL, updated_at=now()
WHERE id=$1 AND book_id=$2 AND lifecycle_state='active'
`, chID, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to unpublish")
		return
	}
	if ct.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "CHAPTER_NOT_FOUND", "chapter not found")
		return
	}
	if err := insertOutboxEvent(r.Context(), tx, "chapter.unpublished", chID,
		map[string]any{"book_id": bookID, "chapter_id": chID}); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to unpublish")
		return
	}
	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to unpublish")
		return
	}
	s.getChapterByID(w, r.Context(), bookID, chID, caller, http.StatusOK)
}

func (s *Server) listRevisions(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}
	if _, _, _, ok := s.authBook(w, r, bookID, GrantView); !ok {
		return
	}
	limit, offset := parseLimitOffset(r)
	rows, err := s.pool.Query(r.Context(), `
SELECT rv.id,rv.chapter_id,rv.created_at,rv.author_user_id,rv.message,octet_length(rv.body::text)
FROM chapter_revisions rv
JOIN chapters c ON c.id=rv.chapter_id
WHERE rv.chapter_id=$1 AND c.book_id=$2
ORDER BY rv.created_at DESC
LIMIT $3 OFFSET $4
`, chID, bookID, limit, offset)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "REVISION_NOT_FOUND", "failed to list revisions")
		return
	}
	defer rows.Close()
	items := make([]map[string]any, 0)
	for rows.Next() {
		var rid, cid uuid.UUID
		var at time.Time
		var uid *uuid.UUID
		var msg *string
		var n int
		_ = rows.Scan(&rid, &cid, &at, &uid, &msg, &n)
		items = append(items, map[string]any{
			"revision_id":      rid,
			"chapter_id":       cid,
			"created_at":       at,
			"author_user_id":   uid,
			"message":          msg,
			"body_byte_length": n,
		})
	}
	var total int
	_ = s.pool.QueryRow(r.Context(), `SELECT COUNT(*) FROM chapter_revisions WHERE chapter_id=$1`, chID).Scan(&total)
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "total": total})
}

func (s *Server) getRevision(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}
	revID, ok := parseUUIDParam(w, r, "revision_id")
	if !ok {
		return
	}
	if _, _, _, ok := s.authBook(w, r, bookID, GrantView); !ok {
		return
	}
	var rid, cid uuid.UUID
	var at time.Time
	var uid *uuid.UUID
	var msg *string
	var body json.RawMessage
	var bodyFormat string
	err := s.pool.QueryRow(r.Context(), `
SELECT rv.id,rv.chapter_id,rv.created_at,rv.author_user_id,rv.message,rv.body,COALESCE(rv.body_format,'plain')
FROM chapter_revisions rv
JOIN chapters c ON c.id=rv.chapter_id
WHERE rv.id=$1 AND rv.chapter_id=$2 AND c.book_id=$3
`, revID, chID, bookID).Scan(&rid, &cid, &at, &uid, &msg, &body, &bodyFormat)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "REVISION_NOT_FOUND", "revision not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "REVISION_NOT_FOUND", "failed to get revision")
		return
	}
	// Extract text_content from the revision body — `_text` projection when
	// present, else nested standard-tiptap text leaves (same union as the publish
	// guard / revision-text endpoint). Also drops the old `t::text` quirk that
	// kept JSON quotes around each segment (compare already extracted unquoted).
	// `strict` (not the default lax) mode on the jsonpath — lax mode's automatic
	// array-unwrap double-visits a single-text-node block (heading/paragraph,
	// the overwhelmingly common case) via `**`, silently DUPLICATING every such
	// block's text (D-CHAPTER-BLOCKS-STALE-EXTRACTION follow-up).
	var textContent *string
	_ = s.pool.QueryRow(r.Context(), `
SELECT string_agg(node_text, E'\n\n' ORDER BY ord)
FROM (
  SELECT x.ord, COALESCE(
    x.elem->>'_text',
    NULLIF((SELECT string_agg(t #>> '{}', '') FROM jsonb_path_query(x.elem, 'strict $.**.text') AS y(t)), '')
  ) AS node_text
  FROM jsonb_array_elements(($1)::jsonb -> 'content') WITH ORDINALITY AS x(elem, ord)
) n
WHERE node_text IS NOT NULL
`, body).Scan(&textContent)
	writeJSON(w, http.StatusOK, map[string]any{
		"revision_id":    rid,
		"chapter_id":     cid,
		"created_at":     at,
		"author_user_id": uid,
		"message":        msg,
		"body":           body,
		"body_format":    bodyFormat,
		"text_content":   textContent,
	})
}

// revisionForCompare fetches one revision (ownership-checked) plus its text
// projection, shaped for the compare response. ok=false means not found / not
// the caller's (→ 404). A DB error returns dbErr set (→ 500).
type compareSide struct {
	RevisionID   uuid.UUID       `json:"revision_id"`
	ChapterID    uuid.UUID       `json:"chapter_id"`
	CreatedAt    time.Time       `json:"created_at"`
	AuthorUserID *uuid.UUID      `json:"author_user_id"`
	Message      *string         `json:"message"`
	Body         json.RawMessage `json:"body"`
	BodyFormat   string          `json:"body_format"`
	TextContent  *string         `json:"text_content"`
}

// revisionForCompare fetches one revision keyed by (rev, chapter, book). The
// caller (compareRevisions) authorizes the book via authBook(view) first, so no
// owner predicate is needed here (E0-2).
func (s *Server) revisionForCompare(
	r *http.Request, revID, chID, bookID uuid.UUID,
) (side compareSide, ok bool, dbErr error) {
	err := s.pool.QueryRow(r.Context(), `
SELECT rv.id,rv.chapter_id,rv.created_at,rv.author_user_id,rv.message,rv.body,COALESCE(rv.body_format,'plain')
FROM chapter_revisions rv
JOIN chapters c ON c.id=rv.chapter_id
WHERE rv.id=$1 AND rv.chapter_id=$2 AND c.book_id=$3
`, revID, chID, bookID).Scan(
		&side.RevisionID, &side.ChapterID, &side.CreatedAt, &side.AuthorUserID,
		&side.Message, &side.Body, &side.BodyFormat,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return compareSide{}, false, nil
	}
	if err != nil {
		return compareSide{}, false, err
	}
	// text_content projection (unquoted — the compare diffs this text). Union of
	// the `_text` projection and nested standard-tiptap text leaves, same as the
	// publish guard / revision-text / getRevision extraction. `strict` jsonpath
	// mode — see getRevision's comment on the lax-mode double-visit bug.
	_ = s.pool.QueryRow(r.Context(), `
SELECT string_agg(node_text, E'\n\n' ORDER BY ord)
FROM (
  SELECT x.ord, COALESCE(
    x.elem->>'_text',
    NULLIF((SELECT string_agg(t #>> '{}', '') FROM jsonb_path_query(x.elem, 'strict $.**.text') AS y(t)), '')
  ) AS node_text
  FROM jsonb_array_elements(($1)::jsonb -> 'content') WITH ORDINALITY AS x(elem, ord)
) n
WHERE node_text IS NOT NULL
`, side.Body).Scan(&side.TextContent)
	return side, true, nil
}

// compareRevisions diffs two revisions of the same chapter (1-vs-1). It returns
// both revisions' bodies + a server-computed line diff of their text_content.
// JWT + ownership enforced; the diff lives server-side so the algorithm is
// tested once and the FE only renders (word-level highlight is an FE concern).
func (s *Server) compareRevisions(w http.ResponseWriter, r *http.Request) {
	// Auth (401) before param validation (400) before the grant/DB check — the
	// established order for this read. authBook below re-resolves the grant.
	if _, ok := s.requireUserID(r); !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}
	leftID, err := uuid.Parse(r.URL.Query().Get("left"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "COMPARE_BAD_PARAM", "left must be a revision id")
		return
	}
	rightID, err := uuid.Parse(r.URL.Query().Get("right"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "COMPARE_BAD_PARAM", "right must be a revision id")
		return
	}
	if _, _, _, ok := s.authBook(w, r, bookID, GrantView); !ok {
		return
	}
	left, ok, dbErr := s.revisionForCompare(r, leftID, chID, bookID)
	if dbErr != nil {
		writeError(w, http.StatusInternalServerError, "REVISION_NOT_FOUND", "failed to load left revision")
		return
	}
	if !ok {
		writeError(w, http.StatusNotFound, "REVISION_NOT_FOUND", "left revision not found")
		return
	}
	right, ok, dbErr := s.revisionForCompare(r, rightID, chID, bookID)
	if dbErr != nil {
		writeError(w, http.StatusInternalServerError, "REVISION_NOT_FOUND", "failed to load right revision")
		return
	}
	if !ok {
		writeError(w, http.StatusNotFound, "REVISION_NOT_FOUND", "right revision not found")
		return
	}
	diff, truncated := textdiff.Lines(deref(left.TextContent), deref(right.TextContent))
	writeJSON(w, http.StatusOK, map[string]any{
		"left":      left,
		"right":     right,
		"diff":      diff,
		"truncated": truncated,
	})
}

func deref(s *string) string {
	if s == nil {
		return ""
	}
	return *s
}

func (s *Server) restoreRevision(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}
	revID, ok := parseUUIDParam(w, r, "revision_id")
	if !ok {
		return
	}
	caller, _, _, ok := s.authBook(w, r, bookID, GrantEdit)
	if !ok {
		return
	}
	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to restore revision")
		return
	}
	defer tx.Rollback(r.Context())
	var currentBody json.RawMessage
	var currentFormat string
	if err := tx.QueryRow(r.Context(), `SELECT body,draft_format FROM chapter_drafts WHERE chapter_id=$1`, chID).Scan(&currentBody, &currentFormat); err != nil {
		writeError(w, http.StatusNotFound, "CHAPTER_NOT_FOUND", "draft not found")
		return
	}
	var body json.RawMessage
	var bodyFormat string
	err = tx.QueryRow(r.Context(), `
SELECT rv.body,COALESCE(rv.body_format,'plain')
FROM chapter_revisions rv
JOIN chapters c ON c.id=rv.chapter_id
WHERE rv.id=$1 AND rv.chapter_id=$2 AND c.book_id=$3
`, revID, chID, bookID).Scan(&body, &bodyFormat)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "REVISION_NOT_FOUND", "revision not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "REVISION_NOT_FOUND", "failed to restore revision")
		return
	}
	_, _ = tx.Exec(r.Context(), `INSERT INTO chapter_revisions(chapter_id, body, body_format, message, author_user_id) VALUES($1,$2,$3,$4,$5)`, chID, currentBody, currentFormat, "before restore", caller)
	_, _ = tx.Exec(r.Context(), `UPDATE chapter_drafts SET body=$2,draft_format=$3,draft_updated_at=now(),draft_version=draft_version+1 WHERE chapter_id=$1`, chID, body, bodyFormat)
	_, _ = tx.Exec(r.Context(), `UPDATE chapters SET draft_updated_at=now(),draft_revision_count=draft_revision_count+1,updated_at=now() WHERE id=$1`, chID)
	if err := insertOutboxEvent(r.Context(), tx, "chapter.saved", chID, map[string]any{"book_id": bookID}); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to restore revision")
		return
	}
	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to restore revision")
		return
	}
	s.getDraft(w, r)
}

func (s *Server) getBookProjection(w http.ResponseWriter, r *http.Request) {
	bookID, err := uuid.Parse(chi.URLParam(r, "book_id"))
	if err != nil {
		ProjectionTotal.WithLabelValues(OutcomeValidationError).Inc()
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid book id")
		return
	}
	var id, owner uuid.UUID
	var title, desc, lang, summary, state string
	var chapterCount int
	var createdAt time.Time
	var genreTags []string
	var wikiSettings json.RawMessage
	var extractionProfile json.RawMessage
	// WS-1.2 (D16): `kind` rides the projection. Every downstream consumer of this
	// contract (wiki, notifications, statistics, catalog, public-MCP) needs it to enforce
	// the diary taint — without it they cannot even ASK whether the book is private.
	var kind string
	// COALESCE the nullable text columns. They were scanned into plain `string`, so ANY
	// book with a NULL description/summary/original_language 500s this endpoint. Existing
	// books happened to carry '' (the create paths always pass a value), which is why it
	// never fired — but the diary provisioner inserts (owner, title, kind) only, so the
	// very first diary would have made its own projection unreadable.
	err = s.pool.QueryRow(r.Context(), `
SELECT b.id,b.owner_user_id,b.title,
  COALESCE(b.description,''), COALESCE(b.original_language,''), COALESCE(b.summary,''),
  b.lifecycle_state,b.created_at,
  COALESCE((SELECT COUNT(*) FROM chapters c WHERE c.book_id=b.id AND c.lifecycle_state='active'),0),
  b.genre_tags, b.wiki_settings, b.extraction_profile, b.kind
FROM books b WHERE b.id=$1
`, bookID).Scan(&id, &owner, &title, &desc, &lang, &summary, &state, &createdAt, &chapterCount, &genreTags, &wikiSettings, &extractionProfile, &kind)
	if errors.Is(err, pgx.ErrNoRows) {
		ProjectionTotal.WithLabelValues(OutcomeNotFound).Inc()
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "book not found")
		return
	}
	if err != nil {
		ProjectionTotal.WithLabelValues(OutcomeQueryFailed).Inc()
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to load projection")
		return
	}
	if genreTags == nil {
		genreTags = []string{}
	}
	var hasCover bool
	var coverURL *string
	var ctype, skey string
	var csize int64
	if err := s.pool.QueryRow(r.Context(), `SELECT content_type, byte_size, storage_key FROM book_cover_assets WHERE book_id=$1`, bookID).Scan(&ctype, &csize, &skey); err == nil {
		hasCover = true
		u := fmt.Sprintf("/v1/books/%s/cover", bookID)
		coverURL = &u
	}
	ProjectionTotal.WithLabelValues(OutcomeOK).Inc()
	writeJSON(w, http.StatusOK, map[string]any{
		"book_id":            id,
		"kind":               kind, // WS-1.2 (D16) — the diary taint; consumers guard on it
		"owner_user_id":      owner,
		"title":              title,
		"description":        nullableString(desc),
		"original_language":  nullableString(lang),
		"summary_excerpt":    excerpt(summary, 180),
		"has_cover":          hasCover,
		"cover_url":          coverURL,
		"chapter_count":      chapterCount,
		"lifecycle_state":    state,
		"genre_tags":         genreTags,
		"wiki_settings":      json.RawMessage(wikiSettings),
		"extraction_profile": json.RawMessage(extractionProfile),
		"created_at":         createdAt,
	})
}

func (s *Server) getInternalBookChapters(w http.ResponseWriter, r *http.Request) {
	bookID, err := uuid.Parse(chi.URLParam(r, "book_id"))
	if err != nil {
		ChaptersListTotal.WithLabelValues(OutcomeValidationError).Inc()
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid book id")
		return
	}
	var lifecycle string
	if err := s.pool.QueryRow(r.Context(), `SELECT lifecycle_state FROM books WHERE id=$1`, bookID).Scan(&lifecycle); errors.Is(err, pgx.ErrNoRows) || lifecycle != "active" {
		ChaptersListTotal.WithLabelValues(OutcomeNotFound).Inc()
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "book not found")
		return
	}
	fromSort, toSort, rangeOK := parseSortRange(r)
	if !rangeOK {
		ChaptersListTotal.WithLabelValues(OutcomeValidationError).Inc()
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid from_sort/to_sort")
		return
	}
	// Swap if caller passed inverted range — the semantic is "inclusive
	// range" and the from>to form is a caller typo, not a zero-match
	// signal. Matches the knowledge-service estimate endpoint which also
	// tolerates either ordering.
	if fromSort != nil && toSort != nil && *fromSort > *toSort {
		fromSort, toSort = toSort, fromSort
	}
	limit, offset := parseLimitOffset(r)

	where, countWhere, countArgs := buildSortRangeFilter(
		"c.book_id=$1 AND c.lifecycle_state='active'",
		"book_id=$1 AND lifecycle_state='active'",
		[]any{bookID},
		fromSort, toSort,
	)
	// CM3c — optional canon=published gate. When the extraction caller
	// (worker-ai enumeration / knowledge cost-estimate) passes
	// `?editorial_status=published`, filter BOTH the COUNT and the LIST so
	// `total` matches the returned items (no estimate/enumeration drift).
	// Default unset → all chapters (chapter browser etc. unaffected). The
	// placeholder-safe append lives in appendEditorialStatusFilter (unit-tested
	// for the $N arithmetic); validation stays here (needs the ResponseWriter).
	es := r.URL.Query().Get("editorial_status")
	if es != "" && es != "draft" && es != "published" {
		ChaptersListTotal.WithLabelValues(OutcomeValidationError).Inc()
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid editorial_status")
		return
	}
	where, countWhere, countArgs = appendEditorialStatusFilter(where, countWhere, countArgs, es)

	// WS-0.6 — the kg_indexed gate (spec §3.5, red-team P0-2). ADDITIVE: it does not
	// change what editorial_status means (see appendKGIndexedFilter).
	//
	// Extraction callers (worker-ai's whole-book rebuild, the passage backfill/ingester,
	// the cost estimate, campaign chapter selection) must ask "what is in the knowledge
	// graph?", NOT "what is published". Without this filter they can only ask the old
	// question, so a user who indexes 50 draft chapters and then hits "Rebuild knowledge
	// graph" gets ZERO of them enumerated — the job reports success having extracted
	// nothing, and the cost estimate says "0 chapters". Their explicit act is silently
	// undone by an unrelated button (the repo's own silent-success-is-a-bug class).
	//
	// Closed set: a typo'd value must 400, never silently fall through to "all chapters"
	// (which would over-extract kg_exclude'd prose the user asked us to forget).
	kgIndexedParam := r.URL.Query().Get("kg_indexed")
	if kgIndexedParam != "" && kgIndexedParam != "true" && kgIndexedParam != "false" {
		ChaptersListTotal.WithLabelValues(OutcomeValidationError).Inc()
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR",
			"invalid kg_indexed (expected true|false)")
		return
	}
	// Filter BOTH the COUNT and the LIST, so `total` matches the returned items — an
	// estimate/enumeration drift here is what makes a cost preview lie.
	where, countWhere = appendKGIndexedFilter(where, countWhere, kgIndexedParam == "true")

	var total int
	// CM3c review WARN#2: the published-gate rides on `total`; a swallowed
	// COUNT error would yield total=0 (HTTP 200) — a silent published-gate
	// blackout. Surface it as 500 instead, mirroring the LIST branch below.
	if err := s.pool.QueryRow(r.Context(), `SELECT COUNT(*) FROM chapters WHERE `+countWhere, countArgs...).Scan(&total); err != nil {
		ChaptersListTotal.WithLabelValues(OutcomeQueryFailed).Inc()
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to count chapters")
		return
	}

	listArgs := append([]any{}, countArgs...)
	listArgs = append(listArgs, limit, offset)
	limitPos := len(countArgs) + 1
	offsetPos := len(countArgs) + 2
	// WS-0.6: kg_indexed_revision_id + kg_exclude join the projection. Without them a
	// re-keyed reader could FILTER on the KG gate but could not PIN the right revision —
	// and worker-ai's extractor falls back to the LIVE DRAFT text when it gets no
	// revision_id, which would silently extract unreviewed prose.
	rows, err := s.pool.Query(r.Context(), fmt.Sprintf(`
SELECT c.id, c.title, c.sort_order, c.original_language, c.draft_updated_at,
  c.editorial_status, c.published_revision_id, c.kg_indexed_revision_id, c.kg_exclude,
  COALESCE((SELECT octet_length(d.body::text) / 5 FROM chapter_drafts d WHERE d.chapter_id = c.id LIMIT 1), 0) AS word_count_estimate
FROM chapters c
WHERE %s
ORDER BY c.sort_order, c.created_at
LIMIT $%d OFFSET $%d
`, where, limitPos, offsetPos), listArgs...)
	if err != nil {
		ChaptersListTotal.WithLabelValues(OutcomeQueryFailed).Inc()
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to list chapters")
		return
	}
	defer rows.Close()
	items := make([]map[string]any, 0)
	for rows.Next() {
		var chapterID uuid.UUID
		var title *string // chapters.title is NULLABLE — a plain string errors on a titleless chapter (silently dropping the row)
		var lang, editorialStatus string
		var sortOrder int
		var draftUpdated *time.Time
		var publishedRevID, kgIndexedRevID *uuid.UUID
		var kgExclude bool
		var wordCount int
		// Every column scans into a real target. A discarded scan zeroes the WHOLE pgx
		// row, so kg_exclude would read false — i.e. fail OPEN on the user's opt-out.
		if err := rows.Scan(&chapterID, &title, &sortOrder, &lang, &draftUpdated, &editorialStatus,
			&publishedRevID, &kgIndexedRevID, &kgExclude, &wordCount); err == nil {
			items = append(items, map[string]any{
				"chapter_id":             chapterID,
				"title":                  nullableStringPtr(title),
				"sort_order":             sortOrder,
				"original_language":      lang,
				"draft_updated_at":       draftUpdated,
				"editorial_status":       editorialStatus,
				"published_revision_id":  publishedRevID,
				"kg_indexed_revision_id": kgIndexedRevID,
				"kg_exclude":             kgExclude,
				"word_count_estimate":    wordCount,
			})
		}
	}
	ChaptersListTotal.WithLabelValues(OutcomeOK).Inc()
	writeJSON(w, http.StatusOK, map[string]any{
		"items":  items,
		"total":  total,
		"limit":  limit,
		"offset": offset,
	})
}

func (s *Server) getInternalBookChapter(w http.ResponseWriter, r *http.Request) {
	bookID, err := uuid.Parse(chi.URLParam(r, "book_id"))
	if err != nil {
		ChapterFetchTotal.WithLabelValues(OutcomeValidationError).Inc()
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid book id")
		return
	}
	chapterID, err := uuid.Parse(chi.URLParam(r, "chapter_id"))
	if err != nil {
		ChapterFetchTotal.WithLabelValues(OutcomeValidationError).Inc()
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid chapter id")
		return
	}
	var lifecycle string
	if err := s.pool.QueryRow(r.Context(), `SELECT lifecycle_state FROM books WHERE id=$1`, bookID).Scan(&lifecycle); errors.Is(err, pgx.ErrNoRows) || lifecycle != "active" {
		ChapterFetchTotal.WithLabelValues(OutcomeNotFound).Inc()
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "book not found")
		return
	}
	var title *string // chapters.title is NULLABLE — a plain string errors on a titleless chapter
	var lang, editorialStatus string
	var body json.RawMessage
	var sortOrder int
	var draftUpdated *time.Time
	var publishedRevID *uuid.UUID
	err = s.pool.QueryRow(r.Context(), `
SELECT c.title,c.sort_order,c.original_language,c.draft_updated_at,d.body,c.editorial_status,c.published_revision_id
FROM chapters c
JOIN chapter_drafts d ON d.chapter_id=c.id
WHERE c.id=$1 AND c.book_id=$2 AND c.lifecycle_state='active'
`, chapterID, bookID).Scan(&title, &sortOrder, &lang, &draftUpdated, &body, &editorialStatus, &publishedRevID)
	if errors.Is(err, pgx.ErrNoRows) {
		ChapterFetchTotal.WithLabelValues(OutcomeNotFound).Inc()
		writeError(w, http.StatusNotFound, "CHAPTER_NOT_FOUND", "chapter not found")
		return
	}
	if err != nil {
		ChapterFetchTotal.WithLabelValues(OutcomeQueryFailed).Inc()
		writeError(w, http.StatusInternalServerError, "CHAPTER_NOT_FOUND", "failed to load chapter")
		return
	}
	// Aggregate plain text from chapter_blocks for translation-service consumption.
	// `block_indices` is the ORDERED list of block_index values text_content was
	// joined from (same ORDER BY): raw-search P3-C maps a passage's paragraph
	// position in text_content → its real block_index for precise jump-to-source.
	var textContent *string
	var blockIndices []int32
	_ = s.pool.QueryRow(r.Context(), `
SELECT string_agg(text_content, E'\n\n' ORDER BY block_index),
       array_agg(block_index ORDER BY block_index)
FROM chapter_blocks WHERE chapter_id=$1
`, chapterID).Scan(&textContent, &blockIndices)
	ChapterFetchTotal.WithLabelValues(OutcomeOK).Inc()
	writeJSON(w, http.StatusOK, map[string]any{
		"chapter_id":            chapterID,
		"title":                 nullableStringPtr(title),
		"sort_order":            sortOrder,
		"original_language":     lang,
		"draft_updated_at":      draftUpdated,
		"body":                  body,
		"body_format":           "json",
		"text_content":          textContent,
		"block_indices":         blockIndices,
		"editorial_status":      editorialStatus,
		"published_revision_id": publishedRevID,
	})
}

// getInternalChapterBlocks — T2 translation segmentation. Returns the chapter's
// extracted blocks (one row per Tiptap block, trigger-maintained from the draft)
// ordered by block_index, each with content_hash for the segmenter's dirty-detection.
// Internal-token only; IDOR + lifecycle guarded (chapter ∈ book ∈ active).
func (s *Server) getInternalChapterBlocks(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chapterID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}
	var exists bool
	if err := s.pool.QueryRow(r.Context(),
		`SELECT EXISTS(SELECT 1 FROM chapters WHERE id=$1 AND book_id=$2 AND lifecycle_state='active')`,
		chapterID, bookID).Scan(&exists); err != nil {
		writeError(w, http.StatusInternalServerError, "CHAPTER_NOT_FOUND", "failed to load chapter")
		return
	}
	if !exists {
		writeError(w, http.StatusNotFound, "CHAPTER_NOT_FOUND", "chapter not found")
		return
	}
	// COALESCE text_content/content_hash: non-text blocks (image/hr/codeBlock) have no
	// `_text` → the extraction trigger leaves them NULL; scanning NULL into a Go string
	// would 500 the whole chapter. Empty string is the right segmenter input for them.
	rows, err := s.pool.Query(r.Context(),
		`SELECT block_index, COALESCE(block_type,''), COALESCE(text_content,''),
		        COALESCE(content_hash,''), heading_context
		 FROM chapter_blocks WHERE chapter_id=$1 ORDER BY block_index`, chapterID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "CHAPTER_NOT_FOUND", "failed to load blocks")
		return
	}
	defer rows.Close()
	type blk struct {
		BlockIndex     int32   `json:"block_index"`
		BlockType      string  `json:"block_type"`
		TextContent    string  `json:"text_content"`
		ContentHash    string  `json:"content_hash"`
		HeadingContext *string `json:"heading_context"`
	}
	out := []blk{}
	for rows.Next() {
		var b blk
		if err := rows.Scan(&b.BlockIndex, &b.BlockType, &b.TextContent, &b.ContentHash, &b.HeadingContext); err != nil {
			writeError(w, http.StatusInternalServerError, "CHAPTER_NOT_FOUND", "failed to scan block")
			return
		}
		out = append(out, b)
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "CHAPTER_NOT_FOUND", "failed to read blocks")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"chapter_id": chapterID, "blocks": out})
}

// getInternalChapterRevisionText — Canon Model CM3a. Returns a SPECIFIC
// revision's plain text for the canonization worker (CM3b), which extracts the
// PINNED published revision rather than the live draft (avoids the draft-drift
// race). Internal-token only (book-scoped; caller validates ownership per
// SEC2). IDOR-guarded: the join revision→chapter→book means a revision_id from
// another chapter/book 404s. text_content is projected plain-and-unquoted from
// the revision's TipTap JSONB (`->>'_text'`), unlike getRevision's quoted
// jsonb_path_query form — extraction wants clean text.
func (s *Server) getInternalChapterRevisionText(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chapterID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}
	revID, ok := parseUUIDParam(w, r, "revision_id")
	if !ok {
		return
	}
	// CONTRACT (review-impl MED-2): serves ANY revision of the chapter, NOT only
	// the published one — it does not gate on chapters.published_revision_id.
	// canon=published depends on the CALLER (CM3b worker) passing
	// chapters.published_revision_id, never an arbitrary/draft-era revision id.
	// Generic-by-id is intentional; the published-gate is the caller's (SEC2).
	var body json.RawMessage
	var bodyFormat string
	err := s.pool.QueryRow(r.Context(), `
SELECT rv.body, COALESCE(rv.body_format,'json')
FROM chapter_revisions rv
JOIN chapters c ON c.id=rv.chapter_id
WHERE rv.id=$1 AND rv.chapter_id=$2 AND c.book_id=$3 AND c.lifecycle_state='active'
`, revID, chapterID, bookID).Scan(&body, &bodyFormat)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "REVISION_NOT_FOUND", "revision not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "REVISION_NOT_FOUND", "failed to load revision")
		return
	}
	// Per-node text: prefer the editor's `_text` projection, else join the node's
	// nested standard-tiptap text leaves ($.**.text). The `_text`-only extraction
	// returned NULL for standard tiptap bodies → the CM3b extraction runner skipped
	// every such chapter as "text unavailable" (same class as the publish guard fix).
	// `strict` jsonpath mode — see getRevision's comment on the lax-mode double-visit bug.
	var textContent *string
	_ = s.pool.QueryRow(r.Context(), `
SELECT string_agg(node_text, E'\n\n' ORDER BY ord)
FROM (
  SELECT x.ord, COALESCE(
    x.elem->>'_text',
    NULLIF((SELECT string_agg(t #>> '{}', '') FROM jsonb_path_query(x.elem, 'strict $.**.text') AS y(t)), '')
  ) AS node_text
  FROM jsonb_array_elements(($1)::jsonb -> 'content') WITH ORDINALITY AS x(elem, ord)
) n
WHERE node_text IS NOT NULL
`, body).Scan(&textContent)
	// body JSONB intentionally NOT returned (review-impl LOW-2): the extraction
	// consumer (CM3b) needs only text_content; the full doc would be dead weight.
	writeJSON(w, http.StatusOK, map[string]any{
		"revision_id":  revID,
		"chapter_id":   chapterID,
		"book_id":      bookID,
		"body_format":  bodyFormat,
		"text_content": textContent,
	})
}

// postInternalChapterTitles — C6 (D-K19b.3-01 + D-K19e-β-01).
//
// Batch resolver used by knowledge-service to denormalize chapter
// titles into Timeline events + ExtractionJob current-cursor rows
// before serving them to the FE. One HTTP round-trip per knowledge-
// service response instead of per-row.
//
// /review-impl M2 test gap: the Go tests for this handler (in
// “server_test.go“) exercise only the pre-DB paths (empty list /
// oversized / invalid JSON) via “s := &Server{}“ with a nil pool.
// The happy-path SQL (column names, “ANY($1::uuid[])“ array codec,
// “lifecycle_state='active'“ filter) follows the conventions from
// “getInternalBookChapters“ / “getInternalBookChapter“ which ARE
// exercised by knowledge-service integration tests hitting
// “/internal/books/{book_id}/chapters“ live. A manual-curl smoke
// in docker before prod promotion is the current safety net for this
// specific handler — if the pattern proves fragile across cycles,
// add a testcontainer-backed Go integration test.
//
// Request:  { "chapter_ids": [uuid, uuid, ...] }
// Response: { "titles": { "<uuid>": "Chapter N — Title" } }
//
// Contract notes:
//   - Empty list → 200 with empty titles map.
//   - Cap at 200 ids per call; oversized → 422.
//   - chapter_ids not in DB OR with lifecycle_state != 'active' are
//     silently dropped from the response map. The caller renders a
//     UUID-suffix fallback for any key it asked for but didn't get.
//   - Whitespace-only titles fall back to "Chapter N" (sort_order
//     only) so the FE never shows a dash with empty text.
//   - No book-scope filter: a caller can ask for any chapter ids
//     across any books. Authorization is "you have the internal
//     token"; knowledge-service only passes ids derived from its own
//     Neo4j rows (which already carry the caller's user_id).
func (s *Server) postInternalChapterTitles(w http.ResponseWriter, r *http.Request) {
	const maxIDs = 200
	var body struct {
		ChapterIDs []uuid.UUID `json:"chapter_ids"`
		// KG-TL M1 — optional reader-language. When set, each requested
		// chapter resolves to its SIBLING-language heading (the chapter at
		// the same (book_id, sort_order) whose original_language folds to
		// this primary subtag); absent a sibling, the requested chapter's
		// own (source-language) heading is returned. Malformed/blank is
		// treated as absent (source heading) — never an error, so the mix
		// is removed even when no translated chapter exists.
		Language string `json:"language"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid JSON body")
		return
	}
	if len(body.ChapterIDs) == 0 {
		writeJSON(w, http.StatusOK, map[string]any{"titles": map[string]string{}})
		return
	}
	if len(body.ChapterIDs) > maxIDs {
		writeError(
			w, http.StatusUnprocessableEntity, "BOOK_VALIDATION_ERROR",
			fmt.Sprintf("too many chapter_ids (max %d)", maxIDs),
		)
		return
	}
	// KG-TL M1 — primary subtag fold ("vi-VN" → "vi"); blank/malformed → "".
	readerLang := primaryLangSubtag(body.Language)
	var rows pgx.Rows
	var err error
	if readerLang != "" {
		// Resolve the sibling-language heading: for each requested chapter,
		// find the chapter at the SAME (book_id, sort_order) whose
		// original_language folds to the reader subtag. LEFT JOIN so a
		// chapter WITHOUT a sibling translation falls back to its own
		// (source-language) heading — never drops a row. The key returned
		// is the REQUESTED chapter id so the caller maps it back 1:1. A tie
		// (two active siblings in the same subtag) is broken by id so the
		// result is deterministic.
		rows, err = s.pool.Query(r.Context(), `
SELECT DISTINCT ON (req.id)
       req.id,
       COALESCE(sib.sort_order, req.sort_order) AS sort_order,
       COALESCE(sib.title, req.title)           AS title
FROM chapters req
LEFT JOIN chapters sib
  ON sib.book_id = req.book_id
 AND sib.sort_order = req.sort_order
 AND sib.lifecycle_state = 'active'
 AND lower(split_part(sib.original_language, '-', 1)) = $2
WHERE req.id = ANY($1::uuid[]) AND req.lifecycle_state = 'active'
ORDER BY req.id, sib.id
`, body.ChapterIDs, readerLang)
	} else {
		rows, err = s.pool.Query(r.Context(), `
SELECT id, sort_order, title
FROM chapters
WHERE id = ANY($1::uuid[]) AND lifecycle_state = 'active'
`, body.ChapterIDs)
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to query chapter titles")
		return
	}
	defer rows.Close()
	titles := make(map[string]string)
	var scanErrors int
	for rows.Next() {
		var id uuid.UUID
		var sortOrder int
		var title *string // chapters.title is NULLABLE — a plain string errors on a titleless chapter (the common case here) and drops the row before the "Chapter N" fallback
		if err := rows.Scan(&id, &sortOrder, &title); err != nil {
			// /review-impl L5 — surface scan errors rather than silent
			// drop. A schema drift (title column type change) would
			// otherwise produce an empty map forever with no signal.
			// Log via stdlib so the ops dashboard sees a spike + keep
			// serving whatever rows DID parse cleanly.
			scanErrors++
			continue
		}
		if title == nil || strings.TrimSpace(*title) == "" {
			titles[id.String()] = fmt.Sprintf("Chapter %d", sortOrder)
		} else {
			titles[id.String()] = fmt.Sprintf("Chapter %d — %s", sortOrder, *title)
		}
	}
	// /review-impl L5 — rows.Err() catches iterator-level errors
	// (connection loss mid-stream, late server-side error) that
	// rows.Next()'s final `false` would otherwise obscure as "end of
	// result set". Fail the request so the caller retries — partial
	// results here are worse than no results because the FE would
	// cache the partial map.
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "chapter titles iterator errored")
		return
	}
	if scanErrors > 0 {
		// Best-effort log — don't want this path to fail the request
		// since SOME rows may have parsed. The count gives ops enough
		// to correlate with a schema drift.
		writeJSON(
			w, http.StatusOK,
			map[string]any{
				"titles":           titles,
				"scan_error_count": scanErrors,
			},
		)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"titles": titles})
}

// postInternalChapterSortOrders — C12a (D-K16.2-02b).
//
// Batch resolver used by knowledge-service's chapter.saved handler
// to honour running jobs' scope_range.chapter_range filters. Mirrors
// postInternalChapterTitles in shape + caps + error envelopes — but
// returns only the raw sort_order int so the handler-gate path
// doesn't have to parse "Chapter N — Title" strings.
//
// Request:  { "chapter_ids": [uuid, uuid, ...] }
// Response: { "sort_orders": { "<uuid>": <int> } }
//
// Contract (same as postInternalChapterTitles):
//   - Empty list → 200 with empty sort_orders map.
//   - Cap at 200 ids per call; oversized → 422.
//   - chapter_ids not in DB OR with lifecycle_state != 'active' are
//     silently dropped from the response. The caller treats missing
//     keys as "unknown sort_order" and over-ingests defensively.
//   - Scan errors surface via scan_error_count (best-effort partial
//     response); iterator-level errors (connection loss) return 500.
//   - No book-scope filter: authorization is the internal token. The
//     knowledge-service handler only passes ids from events it owns.
//
// Same /review-impl M2 test gap as postInternalChapterTitles: the Go
// unit tests exercise only the pre-DB paths. Happy-path SQL follows
// the already-exercised postInternalChapterTitles pattern byte-for-
// byte; testcontainer integration would lock both.
func (s *Server) postInternalChapterSortOrders(w http.ResponseWriter, r *http.Request) {
	const maxIDs = 200
	var body struct {
		ChapterIDs []uuid.UUID `json:"chapter_ids"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid JSON body")
		return
	}
	if len(body.ChapterIDs) == 0 {
		writeJSON(w, http.StatusOK, map[string]any{"sort_orders": map[string]int{}})
		return
	}
	if len(body.ChapterIDs) > maxIDs {
		writeError(
			w, http.StatusUnprocessableEntity, "BOOK_VALIDATION_ERROR",
			fmt.Sprintf("too many chapter_ids (max %d)", maxIDs),
		)
		return
	}
	rows, err := s.pool.Query(r.Context(), `
SELECT id, sort_order
FROM chapters
WHERE id = ANY($1::uuid[]) AND lifecycle_state = 'active'
`, body.ChapterIDs)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to query chapter sort orders")
		return
	}
	defer rows.Close()
	sortOrders := make(map[string]int)
	var scanErrors int
	for rows.Next() {
		var id uuid.UUID
		var sortOrder int
		if err := rows.Scan(&id, &sortOrder); err != nil {
			scanErrors++
			continue
		}
		sortOrders[id.String()] = sortOrder
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "chapter sort orders iterator errored")
		return
	}
	if scanErrors > 0 {
		writeJSON(
			w, http.StatusOK,
			map[string]any{
				"sort_orders":      sortOrders,
				"scan_error_count": scanErrors,
			},
		)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"sort_orders": sortOrders})
}

// postInternalChapterCanonMarkers — 26 IX-9. The batch resolver composition's
// conformance-status read polls to compute dirtiness (prose_drift / index_stale)
// without a stored dirty bit. Mirrors postInternalChapterSortOrders' contract:
//
//	Request:  { "chapter_ids": [uuid, ...] }
//	Response: { "markers": { "<uuid>": { "published_revision_id": uuid|null,
//	                                     "kg_indexed_revision_id": uuid|null,
//	                                     "kg_exclude": bool,
//	                                     "last_parsed_revision_id": uuid|null,
//	                                     "parse_version": int,
//	                                     "editorial_status": "draft"|"published" } } }
//
// WS-0.7 (spec 2026-07-11-publish-independent-kg-indexing §3.6, red-team P0-3):
// kg_indexed_revision_id + kg_exclude are ADDITIVE fields, and they are what make the
// new staleness predicate expressible AT ALL on the consumer side. composition-service
// hand-copies the sweeper's WHERE clause in Python to compute its `index_stale` badge;
// without these two fields it literally cannot compute the post-WS-0.5 predicate, so it
// would keep evaluating the OLD one and produce a PERMANENTLY-STUCK badge:
// publish@A → index a draft@B → composition sees `published AND last_parsed(B) !=
// published_revision_id(A)` ⇒ stale, while the sweeper sees `last_parsed(B) ==
// kg_indexed(B)` ⇒ nothing to heal. The badge never clears.
//
//   - Empty list → 200 with an empty markers map.
//   - Cap at 200 ids per call; oversized → 422.
//   - BOOK-SCOPED by the path {book_id}: ids not in that book (or not active) are
//     silently dropped — the query filters on book_id, so a caller passing a
//     wrong book_id gets no cross-book leak (the token authenticates the caller
//     service; the book_id scope is the tenancy defense at this layer, with the
//     E0 grant enforced upstream at composition's VIEW-gated status route).
//   - parse_version is the IX-4 CHAPTER SCALAR: MAX(parse_version) over the
//     chapter's ACTIVE scenes rows (0 when a chapter has none yet).
//   - Scan errors surface via scan_error_count (best-effort partial response);
//     iterator-level errors return 500.
func (s *Server) postInternalChapterCanonMarkers(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	const maxIDs = 200
	var body struct {
		ChapterIDs []uuid.UUID `json:"chapter_ids"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid JSON body")
		return
	}
	if len(body.ChapterIDs) == 0 {
		writeJSON(w, http.StatusOK, map[string]any{"markers": map[string]any{}})
		return
	}
	if len(body.ChapterIDs) > maxIDs {
		writeError(w, http.StatusUnprocessableEntity, "BOOK_VALIDATION_ERROR",
			fmt.Sprintf("too many chapter_ids (max %d)", maxIDs))
		return
	}
	rows, err := s.pool.Query(r.Context(), `
SELECT c.id, c.published_revision_id, c.kg_indexed_revision_id, c.kg_exclude,
       c.last_parsed_revision_id, c.editorial_status,
       COALESCE((SELECT MAX(parse_version) FROM scenes
                 WHERE chapter_id = c.id AND lifecycle_state = 'active'), 0) AS parse_version
FROM chapters c
WHERE c.book_id = $1 AND c.id = ANY($2::uuid[]) AND c.lifecycle_state = 'active'
`, bookID, body.ChapterIDs)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to query canon markers")
		return
	}
	defer rows.Close()
	markers := make(map[string]any)
	var scanErrors int
	for rows.Next() {
		var id uuid.UUID
		var publishedRev, kgIndexedRev, lastParsedRev *uuid.UUID
		var kgExclude bool
		var editorialStatus string
		var parseVersion int
		// NB: every column is scanned into a real target. A discarded scan error would
		// zero the WHOLE row (pgx), so kg_exclude would read false on any scan hiccup —
		// i.e. fail OPEN on a privacy flag. scanErrors++ + continue keeps that honest.
		if err := rows.Scan(&id, &publishedRev, &kgIndexedRev, &kgExclude,
			&lastParsedRev, &editorialStatus, &parseVersion); err != nil {
			scanErrors++
			continue
		}
		markers[id.String()] = map[string]any{
			"published_revision_id":   publishedRev,
			"kg_indexed_revision_id":  kgIndexedRev,
			"kg_exclude":              kgExclude,
			"last_parsed_revision_id": lastParsedRev,
			"parse_version":           parseVersion,
			"editorial_status":        editorialStatus,
		}
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "canon markers iterator errored")
		return
	}
	if scanErrors > 0 {
		writeJSON(w, http.StatusOK, map[string]any{"markers": markers, "scan_error_count": scanErrors})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"markers": markers})
}

func excerpt(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n]
}
