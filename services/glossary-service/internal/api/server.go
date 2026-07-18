package api

import (
	"crypto/rsa"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"slices"
	"strings"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/contracts/adminjwt"
	"github.com/loreweave/foundation/contracts/platformjwt"
	"github.com/loreweave/grantclient"
	"github.com/loreweave/observability"

	"github.com/loreweave/glossary-service/internal/config"
)

// Server holds shared dependencies for all handlers.
type Server struct {
	pool   *pgxpool.Pool
	cfg    *config.Config
	secret []byte
	// grantClient resolves (user, book) grants against book-service (E0-1).
	// Positive-grant caching lives in the client; nil → guards fail closed.
	grantClient *grantclient.Client
	// adminPub verifies RS256 admin JWTs for the System-tier write endpoints
	// (D-GKA-SYSTEM-TIER-ADMIN). nil when ADMIN_JWT_PUBLIC_KEY_PEM is unset →
	// those endpoints fail closed. adminKID = KeyFingerprint(adminPub).
	adminPub *rsa.PublicKey
	adminKID string
	// emitTenantAudit is the P2·F cross-tenant audit hook. Production wires it to
	// (*Server).asyncTenantAudit; tests override it with a synchronous spy. nil ⇒
	// no-op (struct-literal Server / nil pool).
	emitTenantAudit func(actorID, bookID uuid.UUID, outcome string)
	// auditDedup bounds the P2·F audit WRITE path to first-per-window. nil ⇒ no dedup
	// (still correct — the DB ON CONFLICT dedups the row). Wired in NewServer.
	auditDedup *tenantAuditDedup
}

func NewServer(pool *pgxpool.Pool, cfg *config.Config) *Server {
	s := &Server{
		pool:        pool,
		cfg:         cfg,
		secret:      []byte(cfg.JWTSecret),
		grantClient: buildGrantClient(cfg.BookServiceURL, cfg.InternalServiceToken),
	}
	s.emitTenantAudit = s.asyncTenantAudit
	s.auditDedup = &tenantAuditDedup{}
	if raw := strings.TrimSpace(cfg.AdminJWTPublicKeyPEM); raw != "" {
		pub, err := adminjwt.ParseRSAPublicKeyPEM(pemOrBase64(raw))
		if err != nil {
			// Misconfigured key → leave admin disabled (fail closed) + log loudly.
			slog.Error("glossary: ADMIN_JWT_PUBLIC_KEY_PEM parse failed; System-tier admin endpoints DISABLED", "err", err)
		} else if kid, err := adminjwt.KeyFingerprint(pub); err != nil {
			slog.Error("glossary: admin key fingerprint failed; System-tier admin endpoints DISABLED", "err", err)
		} else {
			s.adminPub = pub
			s.adminKID = kid
			slog.Info("glossary: System-tier admin endpoints ENABLED", "kid", kid)
		}
	}
	return s
}

// GrantClient exposes the process's grant client so main can wire the
// grant-revoke stream consumer to its cache (D-GRANT-INSTANT-REVOKE). May be nil.
func (s *Server) GrantClient() *grantclient.Client { return s.grantClient }

func (s *Server) Router() http.Handler {
	r := chi.NewRouter()
	r.Use(middleware.RequestID)
	r.Use(middleware.RealIP)
	// Phase 6c — OpenTelemetry SERVER span. Before jsonRecovererMiddleware
	// (the custom recoverer) so the span survives a handler panic. Sits
	// alongside the pre-existing traceIDMiddleware, which is a separate
	// header-level request-id mechanism (X-Trace-Id) — retained as-is.
	r.Use(observability.ChiMiddleware())
	// traceIDMiddleware before jsonRecovererMiddleware so a panicking
	// handler's recovery response carries the incoming trace id. We
	// swap chi's built-in Recoverer for our JSON version that embeds
	// the trace id in both the response body and the X-Trace-Id header.
	r.Use(traceIDMiddleware)
	r.Use(jsonRecovererMiddleware)

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
	// T2-polish-2a — Prometheus scrape endpoint. Same convention as
	// provider-registry: no auth, in-cluster scrape only, not exposed
	// via the gateway.
	r.Method(http.MethodGet, "/metrics", metricsHandler())

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

	// ── MCP server (Tier-R read tools, ai-gateway provider #2) ────────────
	// Internal-only; the identity middleware (in mcpHandler) validates the
	// service token and lifts X-User-Id into ctx for the ownership guard.
	r.Handle("/mcp", s.mcpHandler())

	// ── Admin MCP server (System-tier tools, ai-gateway admin surface) ────
	// PHYSICALLY SEPARATE from /mcp (INV-T6): the transport middleware verifies an
	// RS256 admin:write token in X-Admin-Token BEFORE tools/list — a non-admin can't
	// even enumerate these tools. System-tier tools NEVER appear on /mcp.
	r.Handle("/mcp/admin", s.adminMCPHandler())

	// ── Internal service-to-service endpoints ─────────────────────────────
	r.Route("/internal", func(r chi.Router) {
		r.Use(s.requireInternalToken)
		r.Get("/books/{book_id}/translation-glossary", s.internalTranslationGlossary)
		r.Get("/books/{book_id}/extraction-profile", s.internalExtractionProfile)
		r.Post("/books/{book_id}/select-for-context", s.internalSelectForContext)
		r.Get("/books/{book_id}/known-entities", s.getKnownEntities)
		r.Post("/books/{book_id}/extract-entities", s.bulkExtractEntities)
		// WS-4C Half A — chat's post-turn canon auto-capture. UNLIKE its siblings here,
		// this route grant-checks the supplied owner_user_id (Edit) against the book: it
		// is driven by a chat session, so its book_id traces back to user-supplied data
		// and the internal token alone must not authorize a write into it.
		r.Post("/books/{book_id}/capture-canon", s.captureCanon)
		// M7 backfill — deterministic per-chapter mention_count recount (no LLM). The
		// producer computes counts (it holds chapter text + matcher) and POSTs a targeted,
		// idempotent UPDATE batch here.
		r.Post("/books/{book_id}/recount-mention-counts", s.internalRecountMentionCounts)
		r.Get("/books/{book_id}/translation-candidates", s.internalTranslationCandidates)
		r.Post("/books/{book_id}/apply-translations", s.internalApplyTranslations)
		r.Get("/books/{book_id}/entity-count", s.internalEntityCount)
		// Track-C rail driver — the entity-triage rail's completion signal: how many
		// AI-suggested items still await a triage decision (the review pile). Grounds
		// `done_when:"suggestions < 1"` so the driver knows a half-triaged pile from a clean one.
		r.Get("/books/{book_id}/suggestions-count", s.internalSuggestionsCount)
		r.Get("/books/{book_id}/entities", s.internalListEntities)
		// mui #4 — batch fetch by id for the knowledge semantic selector.
		r.Post("/books/{book_id}/entities/by-ids", s.internalEntitiesByIDs)
		// KG-ML M5 (C9) — batch localized entity display names for the knowledge
		// KG graph-view / edge-timeline (resolves name/term attr → language).
		r.Post("/books/{book_id}/entity-display-names", s.internalEntityDisplayNames)
		// C13 — per-entity mention-span + coverage for the build-wizard auto-pin
		// suggestion banner (bounded GROUP-BY over chapter_entity_links).
		r.Get("/books/{book_id}/entities/stats", s.internalEntityStats)
		// mui #1c G-cand — knowledge's coref detector proposes merge clusters here.
		r.Post("/books/{book_id}/merge-candidates", s.internalProposeMergeCandidates)
		// D-GLOSSARY-ST-DEDUP M3b — remediate pre-existing CJK simplified/traditional
		// (+ full-width/case) entity name-variant duplicates: group by the folded key
		// and merge each group into one winner. DRY-RUN unless ?apply=true.
		r.Post("/books/{book_id}/dedup-name-variants", s.internalDedupNameVariants)
		// Set canonical content (short_description) on an existing entity.
		// Used by lore-enrichment promote to write enriched canon THROUGH the
		// glossary SSOT (Q2) — extract-entities can't set this column.
		r.Post("/books/{book_id}/entities/{entity_id}/canon-content", s.internalSetCanonContent)
		// Read the current canonical content. Used by the lore-enrichment
		// re-promote SELF-HEAL (adversary WARN-1): if a prior canon-content
		// write failed transiently, a re-promote reads NULL here and re-writes.
		r.Get("/books/{book_id}/entities/{entity_id}/canon-content", s.internalGetCanonContent)
		// #26/#7 summarize (merge-rewrite) — the end-of-extraction-job LLM pass fetches
		// the dirty summarize attributes here, rewrites their accumulated raw mentions into
		// one canonical value, and writes it back (compare-and-clear on canonical_dirty).
		r.Get("/books/{book_id}/canonical-dirty", s.internalCanonicalDirty)
		r.Post("/books/{book_id}/entities/{entity_id}/canonical", s.internalWriteCanonical)
		// Temporal-knowledge (F4-live) — the append-only bi-temporal fact SSOT surface the
		// KAL (knowledge-gateway) reads/writes through. Reads return bounded results
		// (kal.v1.yaml); writes wrap the fact core (appendFact/retractFacts/ingestEpisode).
		r.Get("/books/{book_id}/entities/{entity_id}/facts", s.internalGetFacts)
		r.Get("/books/{book_id}/entities/{entity_id}/timeline", s.internalFactTimeline)
		r.Get("/books/{book_id}/entities/{entity_id}/attr-values", s.internalListAttrValues)
		r.Post("/books/{book_id}/facts/episode", s.internalIngestEpisode)
		r.Post("/books/{book_id}/facts/append", s.internalAppendFact)
		r.Post("/books/{book_id}/facts/close", s.internalCloseFact)
		r.Post("/books/{book_id}/facts/retract", s.internalRetractFacts)
		r.Post("/books/{book_id}/facts/merge", s.internalFactMerge)
		r.Post("/books/{book_id}/facts/resolve-entity", s.internalResolveEntity)
		r.Post("/books/{book_id}/facts/split", s.internalSplitEntity)
		// F2-app — the canonical fold loop (the LLM fold runs in the translation fold worker).
		r.Get("/books/{book_id}/fold-dirty", s.internalFoldDirty)
		r.Post("/books/{book_id}/entities/{entity_id}/fold-snapshot", s.internalWriteFoldSnapshot)
		// KAL fold_canonical trigger — mark dirty so the next worker pass re-folds (no LLM here).
		r.Post("/books/{book_id}/entities/{entity_id}/fold", s.internalTriggerFold)
		r.Get("/books/{book_id}/entities/{entity_id}/canonical-snapshot", s.internalGetCanonical)
		// Per-episode translation surface (§6B/§7.6) — on-demand, cached translation of the
		// as-of folded canonical into the reader's display language. Read-through + single-flight
		// background fill via translation-service (BYOK MT, provider-registry); no LLM in glossary.
		r.Get("/books/{book_id}/entities/{entity_id}/canonical-translation", s.internalGetCanonicalTranslation)
		// Enrichment SUPPLEMENT layer (F-C13-1 + F-C13-2 / PO ruling B1):
		// lore-enrichment writes/retracts the distinguished enrichment `dị bản`
		// here (its own table, FK→entity) instead of overwriting short_description.
		// DELETE is the F-C13-1 fix — retract un-canonizes via the internal token,
		// no user JWT, leaving the canonical entity + original canon untouched.
		r.Post("/books/{book_id}/entities/{entity_id}/enrichments", s.internalUpsertEnrichments)
		r.Delete("/books/{book_id}/entities/{entity_id}/enrichments", s.internalDeleteEnrichments)
		// Per-entity enrichment coverage for the lore-enrichment gap engine (D1
		// gap-auto-detect): entities + mention_count + promoted-enrichment dims.
		r.Get("/books/{book_id}/enrichment-coverage", s.internalEnrichmentCoverage)
		// wiki-llm M5 — knowledge-service writes an AI-generated article here
		// (clobber-guard: upsert an ai/stub draft, else file a wiki_suggestion).
		r.Post("/books/{book_id}/wiki/articles", s.internalWriteWikiArticle)
		// wiki-llm Phase-2 (§5.2) — on-demand recipe-drift sweep: flag AI articles
		// whose stored prompt/pipeline version lags the current one (the caller
		// supplies the current versions, which live in knowledge's config).
		r.Post("/books/{book_id}/wiki/staleness-sweep", s.sweepWikiStaleness)
		// wiki-llm M8 (D-WIKI-M8-FEWSHOT) — gold AI→human revision pairs (plaintext,
		// truncated) for few-shot generation in knowledge-service.
		r.Get("/books/{book_id}/wiki/gold-pairs", s.listWikiGoldPairs)
		// D-KG-LG-REAL — the KG ontology resolver / adopt-gate node-kind source
		// (knowledge-service glossary_ontology_client). Book tier + the System
		// standards baseline for book-less projects.
		r.Get("/books/{book_id}/ontology", s.internalBookOntology)
		r.Get("/users/{user_id}/glossary-standards", s.internalUserGlossaryStandards)
		// KG adopt auto-seed — knowledge-service's graph-schema adopt calls this to
		// idempotently copy the schema's REQUIRED node-kinds into the book tier
		// (System→book copy-down), so adopting a KG schema no longer 422s
		// KG_ADOPT_NEEDS_GLOSSARY and silently does nothing. Internal-token gated;
		// the caller (knowledge-service) already verified the user's MANAGE grant.
		r.Post("/books/{book_id}/ontology/adopt-kinds", s.internalAdoptBookKinds)
		// WS-1.6 (spec 05 §Q5) — get-or-create the user's is_self identity entity in their
		// diary (the assistant provisioner calls this after adopt-kinds).
		r.Post("/books/{book_id}/self-entity", s.internalSeedSelfEntity)
		// D-R27 — the assistant-erase orchestrator (gateway) HARD-deletes all captured entities of a
		// diary (the flip side of self-entity/adopt-kinds). Internal-token; book-scoped.
		r.Delete("/books/{book_id}/entities", s.internalEraseBookEntities)
	})

	r.Route("/v1/glossary", func(r chi.Router) {
		// System (T1) kinds are READ-ONLY over HTTP (SS-4 Milestone C). The merged
		// kind list (T1 system + the caller's T2 user kinds, then T3 book kinds in
		// SS-5) stays readable; all user-facing kind WRITES moved to the per-user
		// (/user-kinds) and per-book tiers. The old POST/PATCH/DELETE /kinds*,
		// /kinds/reorder, /kind-aliases, and the attribute write routes were removed
		// here — a regular user must not mutate the shared system catalogue.
		r.Get("/kinds", s.listKinds)
		// Generalized class-C confirm machinery (spec §13) — the single token-gated,
		// single-use, human-confirmed write path for every high-impact action
		// (book_delete + schema creates today; adopt/sync/system later). Supersedes
		// the retired /schema/confirm. /preview is non-consuming (current-state card).
		r.Post("/actions/confirm", s.confirmAction)
		r.Post("/actions/preview", s.previewAction)
		// #27/#29/#30 coalesce — ONE human card commits/previews the N child tokens a chat
		// turn minted (the run-loop bundles strays). Reuses the per-descriptor effects above.
		r.Post("/actions/confirm-batch", s.confirmActionBatch)
		r.Post("/actions/preview-batch", s.previewActionBatch)
		// T4 — System-tier admin confirm path, RS256-gated (requireAdminScope inside),
		// SEPARATE from the HS256 user /actions/confirm above. The MCP admin tools
		// propose (authorityAdmin token); a human admin confirms a System write here.
		r.Post("/actions/admin/confirm", s.confirmAdminAction)
		r.Post("/actions/admin/preview", s.previewAdminAction)
		// Kind-resolution epic: alias table READ (alias_code → kind) for the
		// unknown-kind review GUI. The write (createKindAlias + reassign) was removed
		// in SS-4 Milestone C; it returns in SS-7 retargeted at the tiered model.
		r.Get("/kind-aliases", s.listKindAliases)

		// ── T2 per-user kind CRUD (SS-4) — owner-scoped, JWT-only ─────────────
		r.Route("/user-kinds", func(r chi.Router) {
			r.Get("/", s.listUserKinds)
			r.Post("/", s.createUserKind)
			r.Route("/{user_kind_id}", func(r chi.Router) {
				r.Get("/", s.getUserKind)
				r.Patch("/", s.patchUserKind)
				r.Delete("/", s.deleteUserKind)
				r.Route("/attributes", func(r chi.Router) {
					r.Post("/", s.createUserKindAttr)
					r.Route("/{attr_id}", func(r chi.Router) {
						r.Patch("/", s.patchUserKindAttr)
						r.Delete("/", s.deleteUserKindAttr)
					})
				})
				// G2: kind↔genre association links (tiered genre level).
				r.Route("/genres", func(r chi.Router) {
					r.Get("/", s.listUserKindGenres)
					r.Put("/", s.putUserKindGenres)
					r.Put("/{genre_id}", s.addUserKindGenre)
					r.Delete("/{genre_id}", s.deleteUserKindGenre)
				})
			})
		})
		// ── T2 user-kind recycle bin (SS-4) ──────────────────────────────────
		r.Route("/user-kinds-trash", func(r chi.Router) {
			r.Get("/", s.listUserKindTrash)
			r.Post("/{user_kind_id}/restore", s.restoreUserKind)
			r.Delete("/{user_kind_id}", s.purgeUserKind)
		})

		// ── Genre tier (G2, 2026-06-19) ───────────────────────────────────────
		// System genres read-only (merged via /genres); user genres = owner-scoped
		// CRUD + recycle bin, mirroring the user-kinds surface. This is the tiered
		// genre level — distinct from the legacy per-book genre_groups at
		// /books/{book_id}/genres (which retires in G4).
		r.Get("/genres", s.listStandardGenres)
		r.Route("/user-genres", func(r chi.Router) {
			r.Get("/", s.listUserGenres)
			r.Post("/", s.createUserGenre)
			r.Route("/{genre_id}", func(r chi.Router) {
				r.Get("/", s.getUserGenre)
				r.Patch("/", s.patchUserGenre)
				r.Delete("/", s.deleteUserGenre)
			})
		})
		r.Route("/user-genres-trash", func(r chi.Router) {
			r.Get("/", s.listUserGenreTrash)
			r.Post("/{genre_id}/restore", s.restoreUserGenre)
			r.Delete("/{genre_id}", s.purgeUserGenre)
		})

		// ── Attribute tier (G2) ───────────────────────────────────────────────
		// System attributes read-only (admin/seed); user attributes owner-scoped
		// CRUD with attach-by-code. Keyed by (kind × genre × code).
		r.Get("/system-attributes", s.listSystemAttributes)

		// ── System-tier ADMIN writes (D-GKA-SYSTEM-TIER-ADMIN) ────────────────
		// Platform-owned defaults: each handler gates on an RS256 admin JWT with
		// the admin:write scope (requireAdminScope). A regular HS256 user token
		// can never satisfy it. Edits recompute content_hash for G5 Sync.
		r.Route("/system-genres", func(r chi.Router) {
			r.Post("/", s.createSystemGenre)
			r.Patch("/{genre_id}", s.patchSystemGenre)
			r.Delete("/{genre_id}", s.deleteSystemGenre)        // soft-delete (G-C8)
			r.Post("/{genre_id}/restore", s.restoreSystemGenre) // recycle-bin restore (G-C8)
		})
		r.Route("/system-kinds", func(r chi.Router) {
			r.Post("/", s.createSystemKind)
			r.Patch("/{kind_id}", s.patchSystemKind)
			r.Delete("/{kind_id}", s.deleteSystemKind)
			r.Post("/{kind_id}/restore", s.restoreSystemKind)
		})
		r.Route("/system-attributes-admin", func(r chi.Router) {
			r.Post("/", s.createSystemAttribute)
			r.Patch("/{attr_id}", s.patchSystemAttribute)
			r.Delete("/{attr_id}", s.deleteSystemAttribute)
			r.Post("/{attr_id}/restore", s.restoreSystemAttribute)
		})
		// Recycle bin: all soft-deleted System rows (G-C8). admin:write-gated.
		r.Get("/system-trash", s.listSystemTrash)

		r.Route("/user-attributes", func(r chi.Router) {
			r.Get("/", s.listUserAttributes)
			r.Post("/", s.createUserAttribute)
			r.Patch("/{attr_id}", s.patchUserAttribute)
			r.Delete("/{attr_id}", s.deleteUserAttribute)
		})

		// Cross-book wiki contributions for a user's public profile (UI-2a).
		// Optional auth: self sees private/draft; others see public+published only.
		r.Get("/users/{user_id}/wiki-contributions", s.listUserWikiContributions)

		r.Route("/books/{book_id}", func(r chi.Router) {
			r.Get("/extraction-profile", s.getExtractionProfile)
			r.Get("/export", s.exportGlossary)
			// G3: book-tier ontology — adopt (copy-down from System standards,
			// Manage-gated) + book-local single-tier read (View-gated) + book-tier
			// CRUD (G3b, Manage-gated). The legacy per-book genre_groups /genres
			// routes were retired in G4e.
			r.Post("/adopt", s.adoptBookOntology)
			r.Route("/ontology", func(r chi.Router) {
				r.Get("/", s.getBookOntology)
				r.Put("/active-genres", s.setBookActiveGenres)
				r.Route("/genres", func(r chi.Router) {
					r.Post("/", s.createBookGenre)
					r.Route("/{genre_id}", func(r chi.Router) {
						r.Patch("/", s.patchBookGenre)
						r.Delete("/", s.deleteBookGenre)
						r.Post("/revert", s.revertBookGenre) // G-U1 revert to parent tier
					})
				})
				r.Route("/kinds", func(r chi.Router) {
					r.Post("/", s.createBookKind)
					r.Route("/{book_kind_id}", func(r chi.Router) {
						r.Patch("/", s.patchBookKind)
						r.Delete("/", s.deleteBookKind)
						r.Put("/genres", s.setBookKindGenres)
						r.Post("/revert", s.revertBookKind)
					})
				})
				r.Route("/attributes", func(r chi.Router) {
					r.Post("/", s.createBookAttribute)
					r.Route("/{attr_id}", func(r chi.Router) {
						r.Patch("/", s.patchBookAttribute)
						r.Delete("/", s.deleteBookAttribute)
						r.Post("/revert", s.revertBookAttribute)
					})
				})
			})
			// G5: Sync — on-demand diff (View) + per-row apply (Manage) of the book's
			// adopted standards against their upstream source (book_sync_handler.go).
			r.Route("/sync", func(r chi.Router) {
				r.Get("/available", s.getBookSyncAvailable)
				r.Post("/apply", s.applyBookSync)
			})
			// NOTE: the legacy per-book /genres routes (genre_groups) were RETIRED in
			// G4e — genre_groups is dropped, replaced by the tiered *_genres +
			// book_active_genres model. Book-tier genre CRUD lives under
			// /ontology/genres above.
			r.Route("/recycle-bin", func(r chi.Router) {
				r.Get("/", s.listEntityTrash)
				r.Post("/{entity_id}/restore", s.restoreEntity)
				r.Delete("/{entity_id}", s.purgeEntity)
			})
			r.Route("/wiki", func(r chi.Router) {
				r.Get("/", s.listWikiArticles)
				r.Post("/", s.createWikiArticle)
				r.Post("/generate", s.generateWikiStubs)
				// wiki-llm Phase-2b (D-WIKI-P2B-COST-ESTIMATE) — flat per-article cost.
				r.Get("/gen-config", s.getWikiGenConfigStatus)
				// wiki-llm M7b — LLM-gen job lifecycle proxy (status + resume/cancel).
				r.Route("/job", func(r chi.Router) {
					r.Get("/", s.getWikiGenJobStatus)
					r.Post("/{job_id}/resume", s.resumeWikiGenJob)
					r.Post("/{job_id}/cancel", s.cancelWikiGenJob)
				})
				// wiki-llm Phase-2b (§5.3) — the "Knowledge updates" change-feed.
				r.Route("/staleness", func(r chi.Router) {
					r.Get("/", s.listWikiStaleness)
					r.Post("/sweep", s.sweepWikiStalenessPublic)
					r.Post("/dismiss-batch", s.dismissWikiStalenessBatch)
					r.Get("/{staleness_id}/diff", s.getWikiStalenessDiff)
					r.Post("/{staleness_id}/dismiss", s.dismissWikiStaleness)
				})
				r.Get("/suggestions", s.listWikiSuggestions)
				// Submitter-facing read of their OWN suggestions WITH accept/reject status
				// (no grant — `ws.user_id = caller` is the scope). Static 2-seg route wins
				// over `/{article_id}/...` in chi's trie, so "mine" is never an article_id.
				r.Get("/suggestions/mine", s.listMyWikiSuggestions)
				r.Get("/public", s.publicListWikiArticles)
				r.Get("/public/{article_id}", s.publicGetWikiArticle)
				r.Route("/{article_id}", func(r chi.Router) {
					r.Get("/", s.getWikiArticle)
					r.Patch("/", s.patchWikiArticle)
					r.Delete("/", s.deleteWikiArticle)
					r.Post("/suggestions", s.submitWikiSuggestion)
					r.Route("/suggestions/{sug_id}", func(r chi.Router) {
						r.Patch("/", s.reviewWikiSuggestion)
						r.Delete("/", s.withdrawWikiSuggestion)
					})
					r.Route("/revisions", func(r chi.Router) {
						r.Get("/", s.listWikiRevisions)
						r.Route("/{rev_id}", func(r chi.Router) {
							r.Get("/", s.getWikiRevision)
							r.Post("/restore", s.restoreWikiRevision)
						})
					})
				})
			})
			r.Get("/entity-names", s.listEntityNames)
			r.Get("/translation-languages", s.listBookTranslationLanguages)
			// S4 — batch-translate dialog: list candidates (View) + apply drafts (Edit),
			// reusing the internal worker cores behind a grant gate.
			r.Get("/translation-candidates", s.bookTranslationCandidates)
			r.Post("/apply-translations", s.bookApplyTranslations)
			// Kind-resolution epic: the per-book unknown-kind review queue.
			r.Get("/unknown-entities", s.listUnknownEntities)
			// mui #1c: revert a recorded entity merge.
			r.Post("/merge-journal/{journal_id}/revert", s.revertMerge)
			// mui #1c G-cand: the merge-candidate review inbox (list + dismiss).
			// Confirm == the existing entities/{id}/merge endpoint.
			r.Get("/merge-candidates", s.listMergeCandidates)
			r.Post("/merge-candidates/{candidate_id}/dismiss", s.dismissMergeCandidate)
			// D-BATCH-RESEARCH-JOB — async batch entity-research over a kind. create +
			// estimate are kind-scoped (Manage/View); list + status are book-scoped (View).
			// Lifecycle actions (pause/resume/cancel) arrive with the M2 worker.
			r.Post("/kinds/{kind_id}/research-jobs", s.createResearchJob)
			r.Get("/kinds/{kind_id}/research-estimate", s.researchEstimate)
			r.Get("/research-jobs", s.listResearchJobs)
			r.Get("/research-jobs/{job_id}", s.getResearchJob)
			r.Post("/research-jobs/{job_id}/pause", s.pauseResearchJob)
			r.Post("/research-jobs/{job_id}/resume", s.resumeResearchJob)
			r.Post("/research-jobs/{job_id}/cancel", s.cancelResearchJob)
			// M6 — "Canon at chapter N" public read surface (composition inspector).
			// Both View-grant gated, bare-array responses. known-entities is a public
			// mirror of the internal getKnownEntities (+ first/last/coverage); chapter-
			// entities is the new chapter→entities direction (idx_cel_chapter).
			r.Get("/known-entities", s.publicKnownEntities)
			r.Get("/chapter-entities", s.publicChapterEntities)
			r.Route("/entities", func(r chi.Router) {
				r.Get("/", s.listEntities)
				r.Post("/", s.createEntity)
				// Bulk status flip (e.g. activate freshly-extracted drafts so they
				// feed the translation glossary). Static path — registered before
				// /{entity_id} so chi matches it first.
				r.Post("/bulk-status", s.bulkSetEntityStatus)
				// Bulk soft-delete (clean up duplicate/unwanted entities). Static
				// path — registered before /{entity_id} so chi matches it first.
				r.Post("/bulk-delete", s.bulkDeleteEntities)
				r.Route("/{entity_id}", func(r chi.Router) {
					r.Get("/", s.getEntityDetail)
					r.Patch("/", s.patchEntity)
					r.Delete("/", s.deleteEntity)
					r.Post("/apply-edit", s.applyEntityEdit) // EDIT-ATOMIC: multi-field single-tx edit (assistant diff-card Apply); P3 PATCH endpoints stay for the UI
					r.Post("/pin", s.pinEntity)
					r.Delete("/pin", s.unpinEntity)
					// Kind-resolution epic: move a parked entity onto a real kind.
					r.Post("/reassign-kind", s.reassignEntityKind)
					// mui #1c: merge loser entities into this (winner) entity.
					r.Post("/merge", s.mergeEntities)
					// G6/D2: per-entity genre override (entity_genres) — read (View) +
					// replace (Edit). universal is always included (O4). Drives the
					// merged entity form's which-attributes-apply decision.
					r.Route("/genres", func(r chi.Router) {
						r.Get("/", s.getEntityGenres)
						r.Put("/", s.setEntityGenres)
					})
					r.Route("/chapter-links", func(r chi.Router) {
						r.Get("/", s.listChapterLinks)
						r.Post("/", s.createChapterLink)
						r.Route("/{link_id}", func(r chi.Router) {
							r.Patch("/", s.updateChapterLink)
							r.Delete("/", s.deleteChapterLink)
						})
					})
					r.Get("/evidences", s.listEntityEvidences)
					// VG-2: entity version history + restore (mirrors wiki/revisions).
					r.Route("/revisions", func(r chi.Router) {
						r.Get("/", s.listEntityRevisions)
						r.Route("/{rev_id}", func(r chi.Router) {
							r.Get("/", s.getEntityRevision)
							r.Post("/restore", s.restoreEntityRevision)
						})
					})
					// S-06 — add a value for an attr-def added AFTER the entity existed (the
					// add-later path that was MCP-only). Collection-level POST.
					r.Post("/attributes", s.addAttributeValue)
					r.Route("/attributes/{attr_value_id}", func(r chi.Router) {
						r.Patch("/", s.patchAttributeValue)
						// S-06 — remove the value ROW entirely (cascades children), distinct
						// from a PATCH-to-empty which keeps the blank row.
						r.Delete("/", s.deleteAttributeValue)
						// D-GLOSSARY-MULTIROW-ATTR-VALUES slice 3 — per-item verify/tombstone.
						r.Patch("/items/{item_id}", s.patchAttributeValueItem)
						r.Route("/translations", func(r chi.Router) {
							r.Post("/", s.createTranslation)
							r.Route("/{translation_id}", func(r chi.Router) {
								r.Patch("/", s.updateTranslation)
								r.Delete("/", s.deleteTranslation)
							})
						})
						r.Route("/evidences", func(r chi.Router) {
							r.Post("/", s.createEvidence)
							r.Route("/{evidence_id}", func(r chi.Router) {
								r.Patch("/", s.updateEvidence)
								r.Delete("/", s.deleteEvidence)
							})
						})
					})
				})
			})
		})
	})

	return r
}

// ── helpers ──────────────────────────────────────────────────────────────────

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

// ── auth ─────────────────────────────────────────────────────────────────────

// requireUserID extracts and validates the Bearer JWT, returning the user UUID.
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

// requireAdminScope verifies the Bearer admin RS256 JWT and that it carries the
// required scope, writing the error response + returning false on any failure.
// System tier is platform-owned: only an admin principal (never a regular user)
// may mutate it (CLAUDE.md › User Boundaries). Fail closed when the verify key is
// unconfigured. A regular HS256 user token never satisfies adminjwt.Verify (RS256
// only), so this is not bypassable with a normal login.
func (s *Server) requireAdminScope(w http.ResponseWriter, r *http.Request, scope string) (adminjwt.AdminClaims, bool) {
	if s.adminPub == nil {
		writeError(w, http.StatusServiceUnavailable, "GLOSS_ADMIN_UNAVAILABLE", "system-tier administration is not configured")
		return adminjwt.AdminClaims{}, false
	}
	auth := r.Header.Get("Authorization")
	if !strings.HasPrefix(auth, "Bearer ") {
		writeError(w, http.StatusUnauthorized, "GLOSS_ADMIN_UNAUTHORIZED", "valid admin Bearer token required")
		return adminjwt.AdminClaims{}, false
	}
	claims, err := adminjwt.Verify(strings.TrimPrefix(auth, "Bearer "), s.adminPub, s.adminKID)
	if err != nil {
		writeError(w, http.StatusUnauthorized, "GLOSS_ADMIN_UNAUTHORIZED", "invalid admin token")
		return adminjwt.AdminClaims{}, false
	}
	if !slices.Contains(claims.Scopes, scope) {
		writeError(w, http.StatusForbidden, "GLOSS_ADMIN_FORBIDDEN", "missing required admin scope")
		return adminjwt.AdminClaims{}, false
	}
	return claims, true
}

// requireInternalToken validates the X-Internal-Token header for service-to-service calls.
func (s *Server) requireInternalToken(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if s.cfg.InternalServiceToken != "" && r.Header.Get("X-Internal-Token") != s.cfg.InternalServiceToken {
			writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "invalid internal token"})
			return
		}
		next.ServeHTTP(w, r)
	})
}

// ── internal endpoints ────────────────────────────────────────────────────

// internalTranslationGlossary returns a compact glossary for translation prompts.
//
//	GET /internal/books/{book_id}/translation-glossary
//	Query: target_language (required), chapter_id (optional), max_entries (optional, default 50)
//
// Returns array of: {"zh":["name1","alias"],"vi":["translation"],"kind":"character"}
func (s *Server) internalTranslationGlossary(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	targetLang := r.URL.Query().Get("target_language")
	if targetLang == "" {
		writeError(w, http.StatusBadRequest, "GLOSS_BAD_REQUEST", "target_language query param required")
		return
	}
	chapterIDStr := r.URL.Query().Get("chapter_id")
	maxEntries := 50
	if v := r.URL.Query().Get("max_entries"); v != "" {
		if n, err := fmt.Sscanf(v, "%d", &maxEntries); n != 1 || err != nil || maxEntries < 1 {
			maxEntries = 50
		}
		if maxEntries > 200 {
			maxEntries = 200
		}
	}

	ctx := r.Context()

	// Build query: fetch entities with original name + target translation + kind code.
	// If chapter_id given, prioritize chapter-linked entities (Tier 1),
	// then fill remaining budget with most-linked entities across book (Tier 0).
	//
	// Strategy: UNION of chapter-linked + globally-popular, deduped, limited.
	var query string
	var args []any

	if chapterIDStr != "" {
		chapterID, err := uuid.Parse(chapterIDStr)
		if err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_BAD_REQUEST", "invalid chapter_id")
			return
		}
		// Tier 1 (chapter-linked) + Tier 0 (most-linked) + Tier 2 (all active), deduped
		query = `
WITH chapter_entities AS (
    -- Tier 1: entities linked to this chapter
    SELECT e.entity_id, 1 AS tier
    FROM glossary_entities e
    JOIN chapter_entity_links cel ON cel.entity_id = e.entity_id AND cel.chapter_id = $3
    WHERE e.book_id = $1 AND e.status = 'active' AND e.deleted_at IS NULL
),
popular_entities AS (
    -- Tier 0: most-linked entities in the book (pinned)
    SELECT e.entity_id, 0 AS tier
    FROM glossary_entities e
    JOIN chapter_entity_links cel ON cel.entity_id = e.entity_id
    WHERE e.book_id = $1 AND e.status = 'active' AND e.deleted_at IS NULL
    GROUP BY e.entity_id
    ORDER BY COUNT(*) DESC
    LIMIT $4
),
fallback_entities AS (
    -- Tier 2: all active entities (fallback when no chapter links exist)
    SELECT e.entity_id, 2 AS tier
    FROM glossary_entities e
    WHERE e.book_id = $1 AND e.status = 'active' AND e.deleted_at IS NULL
    LIMIT $4
),
all_entities AS (
    SELECT entity_id, MIN(tier) AS best_tier FROM (
        SELECT * FROM chapter_entities
        UNION ALL
        SELECT * FROM popular_entities
        UNION ALL
        SELECT * FROM fallback_entities
    ) combined GROUP BY entity_id
)
SELECT
    e.entity_id AS entity_id,
    eav.original_value AS name_zh,
    COALESCE(at.value, '') AS name_target,
    ek.code AS kind_code,
    COALESCE(at.confidence, '') AS name_confidence,
    ae.best_tier
FROM all_entities ae
JOIN glossary_entities e ON e.entity_id = ae.entity_id
JOIN book_kinds ek ON ek.book_kind_id = e.kind_id
LEFT JOIN entity_attribute_values eav ON eav.entity_id = e.entity_id
    AND eav.attr_def_id = (
        SELECT ba.attr_id FROM book_attributes ba
        JOIN book_genres g ON g.genre_id = ba.genre_id
        WHERE ba.kind_id = e.kind_id AND ba.code = 'name'
        ORDER BY (g.code = 'universal') DESC LIMIT 1
    )
LEFT JOIN attribute_translations at ON at.attr_value_id = eav.attr_value_id
    AND at.language_code = $2
WHERE eav.original_value IS NOT NULL AND eav.original_value != ''
ORDER BY ae.best_tier ASC, length(eav.original_value) DESC
LIMIT $4`
		args = []any{bookID, targetLang, chapterID, maxEntries}
	} else {
		// No chapter scoping — return most-linked entities across the book
		query = `
SELECT
    e.entity_id AS entity_id,
    eav.original_value AS name_zh,
    COALESCE(at.value, '') AS name_target,
    ek.code AS kind_code,
    COALESCE(at.confidence, '') AS name_confidence,
    0 AS best_tier
FROM glossary_entities e
JOIN book_kinds ek ON ek.book_kind_id = e.kind_id
LEFT JOIN entity_attribute_values eav ON eav.entity_id = e.entity_id
    AND eav.attr_def_id = (
        SELECT ba.attr_id FROM book_attributes ba
        JOIN book_genres g ON g.genre_id = ba.genre_id
        WHERE ba.kind_id = e.kind_id AND ba.code = 'name'
        ORDER BY (g.code = 'universal') DESC LIMIT 1
    )
LEFT JOIN attribute_translations at ON at.attr_value_id = eav.attr_value_id
    AND at.language_code = $2
LEFT JOIN chapter_entity_links cel ON cel.entity_id = e.entity_id
WHERE e.book_id = $1 AND e.status = 'active' AND e.deleted_at IS NULL
    AND eav.original_value IS NOT NULL AND eav.original_value != ''
GROUP BY e.entity_id, eav.original_value, at.value, at.confidence, ek.code
ORDER BY COUNT(cel.link_id) DESC, length(eav.original_value) DESC
LIMIT $3`
		args = []any{bookID, targetLang, maxEntries}
	}

	rows, err := s.pool.Query(ctx, query, args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "query failed")
		return
	}
	defer rows.Close()

	type glossaryEntry struct {
		ZH   []string `json:"zh"`
		Tgt  []string `json:"tgt,omitempty"`
		Kind string   `json:"kind"`
	}

	items := make([]map[string]any, 0, maxEntries)
	for rows.Next() {
		var entityID uuid.UUID
		var nameZH, nameTarget, kindCode, nameConfidence string
		var tier int
		if err := rows.Scan(&entityID, &nameZH, &nameTarget, &kindCode, &nameConfidence, &tier); err != nil {
			continue
		}
		entry := map[string]any{
			// M6b: entity_id lets translation-service record per-chapter glossary
			// usage so a later entity change flags only the chapters that used it.
			"entity_id": entityID.String(),
			"zh":        []string{nameZH},
			"kind":      kindCode,
		}
		if nameTarget != "" {
			entry[targetLang] = []string{nameTarget}
			// D-TRANSL-M1D trust ladder: expose the translation's confidence tier
			// (verified|machine|draft) so the V3 verifier hard-enforces only canon.
			entry["confidence"] = nameConfidence
		}
		items = append(items, entry)
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "row iteration failed")
		return
	}

	writeJSON(w, http.StatusOK, items)
}
