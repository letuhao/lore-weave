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
// NOT change any API response shape and MUST NOT break the primary entity
// write. The single-create path inserts the outbox row inside the SAME tx
// as the entity insert (true transactional outbox — atomic). Paths that
// have already committed (patch, bulk) emit best-effort with the shared
// pool and only log on failure, mirroring the bulk path's existing
// fire-and-forget side effects (chapter links, evidence). A broker/relay
// hiccup never rolls back or fails the entity write.

// entityUpdatedEvent is the canonical event type string published on the
// glossary stream. Stable wire contract consumed by knowledge-service.
const entityUpdatedEvent = "glossary.entity_updated"

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
}

// buildEntityEventPayload assembles the event payload. Pure / DB-free so
// it is unit-testable without a database. `op` is normalised to one of
// "created"/"updated" (anything else falls back to "updated"). source_type
// defaults to "glossary" (authored canon) — the C4 cycle never emits
// enriched content (that is C11/C13, gated by H0).
func buildEntityEventPayload(
	bookID, entityID, name, kind string,
	aliases []string,
	shortDescription, op string,
) entityEventPayload {
	if op != "created" && op != "updated" {
		op = "updated"
	}
	if aliases == nil {
		aliases = []string{}
	}
	return entityEventPayload{
		BookID:           bookID,
		GlossaryEntityID: entityID,
		Name:             name,
		Kind:             kind,
		Aliases:          aliases,
		ShortDescription: shortDescription,
		Op:               op,
		SourceType:       "glossary",
		EmittedAt:        time.Now().UTC().Format(time.RFC3339),
	}
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

// emitEntityUpdated emits best-effort using the server pool, after the
// entity write has already committed (patch / bulk paths). Never returns
// an error: a failure is logged and swallowed so a broker/DB hiccup on the
// secondary event cannot surface as a 500 on a write that already
// succeeded. The outbox row is the source of truth — if the insert itself
// fails, the relay simply has nothing to ship for this write; the next
// write (or a manual glossary_sync) re-converges Neo4j.
func (s *Server) emitEntityUpdated(ctx context.Context, entityID uuid.UUID, op string) {
	name, kind, aliases, shortDesc, ok := loadEntityEventFields(ctx, s.pool, entityID)
	if !ok {
		slog.Warn("outbox: failed to load entity fields for event (skipping emit)",
			"entity_id", entityID, "op", op)
		return
	}
	payload := buildEntityEventPayload(
		s.bookIDForEntity(ctx, entityID), entityID.String(),
		name, kind, aliases, shortDesc, op,
	)
	err := insertEntityOutboxEvent(ctx, func(ctx context.Context, sql string, args ...any) error {
		_, e := s.pool.Exec(ctx, sql, args...)
		return e
	}, entityID, payload)
	if err != nil {
		slog.Warn("outbox: failed to emit glossary.entity_updated (non-fatal)",
			"entity_id", entityID, "op", op, "error", err)
	}
}

// bookIDForEntity resolves the owning book_id for an entity. Returns ""
// on lookup failure (the event still publishes; the consumer skips a
// payload with an empty book_id rather than crashing).
func (s *Server) bookIDForEntity(ctx context.Context, entityID uuid.UUID) string {
	var bookID string
	if err := s.pool.QueryRow(ctx,
		`SELECT book_id::text FROM glossary_entities WHERE entity_id = $1`, entityID,
	).Scan(&bookID); err != nil {
		return ""
	}
	return bookID
}
