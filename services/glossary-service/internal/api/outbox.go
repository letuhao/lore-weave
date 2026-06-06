package api

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// C4 (K14) — glossary→KG event pipeline (emit side).
//
// glossary-service writes a `glossary.entity_updated` row into the
// transactional outbox (created by migrate.UpOutbox) on every canonical
// entity write: single create/patch AND the bulk extract-entities path.
// worker-infra's schema-generic outbox-relay (when glossary is listed in
// OUTBOX_SOURCES) ships each row to the Redis Stream
// "loreweave:events:glossary"; knowledge-service's existing consumer then
// triggers glossary_sync → Neo4j. The propagation is therefore automatic
// and platform-wide (resolves H1), going strictly through the glossary
// SSOT → glossary_sync path (Q2) — this service never writes Neo4j.
//
// Backward-compatible / fire-and-forget contract: emitting an event MUST
// NOT change any API response shape. Phase B updated the durability split:
//
//   - CREATE and PATCH are now STRICT transactional outbox — the event row is
//     inserted in the SAME tx as the entity write (PATCH was moved into a tx in
//     Phase B precisely so the before/after correction snapshot is captured
//     consistently with the UPDATE — design §5 / review-impl MED-3). The outbox
//     INSERT is a LOCAL Postgres write, so it only fails when the DB is
//     unhealthy — in which case the entity write would fail anyway; coupling
//     them is therefore safe and atomic. (Adversary subA F-A3: this is a
//     deliberate change from PATCH's prior best-effort emit.)
//   - The BULK extract-entities path stays best-effort fire-and-forget (already
//     committed per-entity above; a hiccup must not fail a 100-entity batch).
//
// In all cases a BROKER/RELAY hiccup never affects the entity write — the relay
// is downstream of the committed outbox row, not in the write path.

// entityUpdatedEvent is the canonical event type string published on the
// glossary stream. Stable wire contract consumed by knowledge-service.
const entityUpdatedEvent = "glossary.entity_updated"

// entityMergedEvent (mui #1c) is emitted when a glossary entity is merged into
// a winner. knowledge-service's consumer runs its existing repo merge_entities
// (rewire KG edges) + entity_alias_map (anti-resurrection). aggregate_id is the
// winner (the surviving canon).
const entityMergedEvent = "glossary.entity_merged"

type entityMergedPayload struct {
	BookID         string `json:"book_id"`
	WinnerEntityID string `json:"winner_glossary_id"`
	LoserEntityID  string `json:"loser_glossary_id"`
	Op             string `json:"op"` // "merged" | "unmerged"
	EmittedAt      string `json:"emitted_at"`
}

// insertMergedOutboxEvent writes a glossary.entity_merged (or unmerged) outbox
// row. Generic over pool/tx via the exec closure. Best-effort at the call site.
func insertMergedOutboxEvent(
	ctx context.Context,
	exec func(ctx context.Context, sql string, args ...any) error,
	winnerID uuid.UUID,
	payload entityMergedPayload,
) error {
	payloadJSON, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("merged outbox marshal: %w", err)
	}
	if err := exec(ctx, `
		INSERT INTO outbox_events (aggregate_type, aggregate_id, event_type, payload)
		VALUES ('glossary', $1, $2, $3)`,
		winnerID, entityMergedEvent, payloadJSON,
	); err != nil {
		return fmt.Errorf("merged outbox insert: %w", err)
	}
	return nil
}

// entityEventPayload is the JSON payload carried by glossary.entity_updated.
//
// It is self-sufficient: it carries everything knowledge-service's
// glossary_sync needs (name, kind, aliases, short_description) so the
// consumer does not have to round-trip back to glossary-service. book_id +
// glossary_entity_id let the consumer resolve user_id/project_id via its
// own knowledge_projects table (mirrors the chapter.saved handler).
type entityEventPayload struct {
	BookID           string   `json:"book_id"`
	GlossaryEntityID string   `json:"glossary_entity_id"`
	Name             string   `json:"name"`
	Kind             string   `json:"kind"`
	Aliases          []string `json:"aliases"`
	ShortDescription string   `json:"short_description,omitempty"`
	Op               string   `json:"op"`          // "created" | "updated"
	SourceType       string   `json:"source_type"` // "glossary" (authored canon)
	EmittedAt        string   `json:"emitted_at"`  // RFC3339
	// Phase B correction-capture enrichment (ADDITIVE — knowledge-service's
	// glossary_sync consumer ignores these). actor_type distinguishes a USER
	// correction ("user") from a pipeline write ("pipeline"); before/after
	// carry the diffable snapshot. learning-service persists ONLY actor_type
	// =="user" events as corrections. See
	// docs/specs/2026-05-31-phase-b-correction-capture.md §4.1.
	ActorType string          `json:"actor_type"`
	ActorID   string          `json:"actor_id,omitempty"`
	Before    *EntitySnapshot `json:"before,omitempty"`
	After     *EntitySnapshot `json:"after,omitempty"`
}

// EntitySnapshot is the diffable before/after view of an entity carried by
// glossary.entity_updated. learning-service splits it into structural (kind)
// + content-hash (name/aliases/short_description) at ingest.
type EntitySnapshot struct {
	Name             string   `json:"name"`
	Kind             string   `json:"kind"`
	Aliases          []string `json:"aliases"`
	ShortDescription string   `json:"short_description,omitempty"`
}

// buildEntityEventPayload assembles the event payload. Pure / DB-free so
// it is unit-testable without a database. `op` is normalised to one of
// "created"/"updated" (anything else falls back to "updated"). source_type
// defaults to "glossary" (authored canon).
//
// Phase B: `actorType` is normalised to "user" or "pipeline" (anything else
// falls back to "pipeline" — fail-safe so a mislabelled caller is never
// mis-persisted as a user correction). `before` is the pre-edit snapshot
// (nil on create). The `after` snapshot is built from the name/kind/aliases/
// shortDescription args (the current/after state). before/after are attached
// ONLY for user ops — pipeline (bulk-extract) events stay lean and are skipped
// by learning-service anyway.
func buildEntityEventPayload(
	bookID, entityID, name, kind string,
	aliases []string,
	shortDescription, op, actorType, actorID string,
	before *EntitySnapshot,
) entityEventPayload {
	if op != "created" && op != "updated" {
		op = "updated"
	}
	if actorType != "user" {
		actorType = "pipeline"
	}
	if aliases == nil {
		aliases = []string{}
	}
	p := entityEventPayload{
		BookID:           bookID,
		GlossaryEntityID: entityID,
		Name:             name,
		Kind:             kind,
		Aliases:          aliases,
		ShortDescription: shortDescription,
		Op:               op,
		SourceType:       "glossary",
		EmittedAt:        time.Now().UTC().Format(time.RFC3339),
		ActorType:        actorType,
	}
	if actorType == "user" {
		p.ActorID = actorID
		p.Before = before
		p.After = &EntitySnapshot{
			Name:             name,
			Kind:             kind,
			Aliases:          aliases,
			ShortDescription: shortDescription,
		}
	}
	return p
}

// loadEntityEventFields reads the snapshot fields needed for the event
// payload (cached_name, cached_aliases, short_description, kind code) from
// the entity. Uses the denormalised cached_* columns (maintained by the
// snapshot trigger) so no EAV join is needed at emit time. Returns the
// fields even if cached_name is empty (a freshly-created draft) — the
// consumer's glossary_sync MERGE is keyed on glossary_entity_id, so an
// early empty-name event is still idempotently corrected by the later
// PATCH-driven event.
func loadEntityEventFields(
	ctx context.Context, q pgxQuerier, entityID uuid.UUID,
) (name, kind string, aliases []string, shortDesc string, ok bool) {
	var (
		cachedName  *string
		cachedAlias []string
		shortDescDB *string
		kindCode    string
	)
	err := q.QueryRow(ctx, `
		SELECT e.cached_name, e.cached_aliases, e.short_description, k.code
		FROM glossary_entities e
		JOIN entity_kinds k ON k.kind_id = e.kind_id
		WHERE e.entity_id = $1`,
		entityID,
	).Scan(&cachedName, &cachedAlias, &shortDescDB, &kindCode)
	if err != nil {
		return "", "", nil, "", false
	}
	if cachedName != nil {
		name = *cachedName
	}
	if shortDescDB != nil {
		shortDesc = *shortDescDB
	}
	if cachedAlias == nil {
		cachedAlias = []string{}
	}
	return name, kindCode, cachedAlias, shortDesc, true
}

// pgxQuerier is the read interface shared by *pgxpool.Pool and pgx.Tx,
// so loadEntityEventFields can read either inside or outside a tx.
type pgxQuerier interface {
	QueryRow(ctx context.Context, sql string, args ...any) pgx.Row
}

// insertEntityOutboxEvent writes a glossary.entity_updated outbox row.
// Generic over pool or tx via the exec closure so the single-create path
// can enlist it in its transaction while patch/bulk use the pool.
func insertEntityOutboxEvent(
	ctx context.Context,
	exec func(ctx context.Context, sql string, args ...any) error,
	entityID uuid.UUID,
	payload entityEventPayload,
) error {
	payloadJSON, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("outbox marshal: %w", err)
	}
	if err := exec(ctx, `
		INSERT INTO outbox_events (aggregate_type, aggregate_id, event_type, payload)
		VALUES ('glossary', $1, $2, $3)`,
		entityID, entityUpdatedEvent, payloadJSON,
	); err != nil {
		return fmt.Errorf("outbox insert: %w", err)
	}
	return nil
}

// emitEntityUpdatedTx emits within an open transaction (atomic with the
// entity write). Used by the single-create path. A marshal/insert error
// is returned so the caller can decide; createEntity treats it as fatal
// to the tx (the whole write rolls back together — strict transactional
// outbox).
func emitEntityUpdatedTx(
	ctx context.Context, tx pgx.Tx, entityID uuid.UUID, payload entityEventPayload,
) error {
	return insertEntityOutboxEvent(ctx, func(ctx context.Context, sql string, args ...any) error {
		_, e := tx.Exec(ctx, sql, args...)
		return e
	}, entityID, payload)
}

// Phase B: the prior best-effort `emitEntityUpdated` used by the PATCH path was
// removed — PATCH now emits transactionally via `emitEntityUpdatedTx` so it can
// capture a consistent before/after snapshot in the SAME tx as the UPDATE (no
// TOCTOU — design §5 / review-impl MED-3).
//
// emitEntityUpdated is re-provided here (lore-enrichment merge, 2026-06-01) for
// the SERVICE/pipeline write paths that have NO user tx in hand and only need to
// drive the C4/K14 glossary_sync → Neo4j anchor: the canon-content endpoint and
// the enrichment-supplement upsert/delete. It is BEST-EFFORT + post-commit
// (failures are logged, never fatal — the entity write already committed), and
// emits actor_type="pipeline" so learning-service IGNORES it (these are not user
// corrections); only the glossary_sync consumer acts on it. USER edits must keep
// using the transactional emitEntityUpdatedTx path (before/after capture).
func (s *Server) emitEntityUpdated(ctx context.Context, entityID uuid.UUID, op string) {
	name, kind, aliases, shortDesc, ok := loadEntityEventFields(ctx, s.pool, entityID)
	if !ok {
		slog.Warn("emitEntityUpdated: entity fields unavailable (non-fatal)",
			"entity_id", entityID.String())
		return
	}
	var bookID uuid.UUID
	if err := s.pool.QueryRow(ctx,
		`SELECT book_id FROM glossary_entities WHERE entity_id = $1`, entityID,
	).Scan(&bookID); err != nil {
		slog.Warn("emitEntityUpdated: book_id lookup failed (non-fatal)",
			"entity_id", entityID.String(), "err", err)
		return
	}
	payload := buildEntityEventPayload(
		bookID.String(), entityID.String(), name, kind, aliases, shortDesc,
		op, "pipeline", "", nil,
	)
	exec := func(ctx context.Context, sql string, args ...any) error {
		_, e := s.pool.Exec(ctx, sql, args...)
		return e
	}
	if err := insertEntityOutboxEvent(ctx, exec, entityID, payload); err != nil {
		slog.Warn("emitEntityUpdated: outbox insert failed (non-fatal)",
			"entity_id", entityID.String(), "err", err)
	}
}
