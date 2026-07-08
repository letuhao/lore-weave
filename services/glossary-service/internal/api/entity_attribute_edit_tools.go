package api

import (
	"context"
	"errors"
	"log/slog"
	"strings"

	"github.com/google/jsonschema-go/jsonschema"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/loreweave/grantclient"
	lwmcp "github.com/loreweave/loreweave_mcp"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// T-ENTITY-ATTR-EDIT — glossary_entity_set_attributes: the missing write path for an
// ALREADY-EXISTING entity's attribute values (real feedback gap, 2026-07-08,
// D:\Works\novels\mi_de\loreweave-mcp-feedback.md). glossary_propose_new_entity /
// glossary_propose_entities only ever write attribute values at CREATION time and are
// idempotent-skip on re-call (a re-call for an existing name+kind does NOT merge new
// attributes onto it) -- there was no reachable tool to edit or clear a value
// afterward, even though the REST/UI path (applyEntityEdit, patchAttributeValue) has
// always supported exactly this. Tier-A per the user's explicit call (2026-07-08): the
// H5-style optimistic write here + the entity's own revision history are the safety
// net, the same tier as entity creation itself -- a propose/confirm round trip adds no
// real safety since the entity already exists and is fully revertible.

// RegisterEntityAttributeEditTools adds glossary_entity_set_attributes to the
// user/book /mcp server. Registered separately (append-only convention, matches
// RegisterEntityBatchTools/RegisterEntityDeleteTools).
func (s *Server) RegisterEntityAttributeEditTools(srv *mcp.Server) {
	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_entity_set_attributes",
		Description: "Set, edit, or clear attribute values on an ALREADY-EXISTING glossary entity -- " +
			"the counterpart to glossary_propose_entities, which only sets values at CREATION time and " +
			"has no way to touch an entity afterward. Pass attr_code -> new value; a code not yet on " +
			"the entity is added, an existing one is overwritten, and an empty string \"\" clears it. " +
			"Call glossary_get_entity first to see the entity's current attribute codes/values, and " +
			"glossary_book_ontology_read for the kind's valid attribute codes. Writes immediately " +
			"(Tier-A, like entity creation) -- the entity's own revision history covers rollback.",
		InputSchema: entityAttributeSetSchema(),
		Meta: lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeBook, nil, []string{
			"edit an entity's attribute", "update an entity attribute value", "delete or clear an attribute value",
			"change an existing entity's attribute", "fix a wrong attribute value", "add a missing attribute to an entity",
		}),
	}, s.toolSetEntityAttributes)
}

func entityAttributeSetSchema() *jsonschema.Schema {
	return closedSetSchemaFor[entitySetAttributesToolIn](map[string][]any{})
}

type entitySetAttributesToolIn struct {
	BookID     string            `json:"book_id" jsonschema:"the book the entity belongs to (UUID)"`
	EntityID   string            `json:"entity_id" jsonschema:"the entity to edit (UUID)"`
	Attributes map[string]string `json:"attributes" jsonschema:"attr_code -> new value; empty string clears the value; a code not yet on the entity is added"`
}

type entitySetAttributesToolOut struct {
	Updated []string `json:"updated"`
	Skipped []string `json:"skipped,omitempty"` // attr codes not defined on this entity's kind
}

func (s *Server) toolSetEntityAttributes(ctx context.Context, _ *mcp.CallToolRequest, in entitySetAttributesToolIn) (*mcp.CallToolResult, entitySetAttributesToolOut, error) {
	userID, ok := userIDFromCtx(ctx)
	if !ok {
		return nil, entitySetAttributesToolOut{}, errors.New("missing caller identity")
	}
	bookID, err := uuid.Parse(strings.TrimSpace(in.BookID))
	if err != nil {
		return nil, entitySetAttributesToolOut{}, errors.New("book_id must be a UUID")
	}
	entityID, err := uuid.Parse(strings.TrimSpace(in.EntityID))
	if err != nil {
		return nil, entitySetAttributesToolOut{}, errors.New("entity_id must be a UUID")
	}
	if len(in.Attributes) == 0 {
		return nil, entitySetAttributesToolOut{}, errors.New("attributes must have at least one entry")
	}
	if err := s.checkGrant(ctx, bookID, userID, grantclient.GrantEdit); err != nil {
		return nil, entitySetAttributesToolOut{}, uniformOwnershipError(err)
	}
	out, err := s.setEntityAttributes(ctx, bookID, entityID, userID, in.Attributes)
	return nil, out, err
}

// setEntityAttributes is the core DB logic, split from the tool wrapper above so
// tests can exercise it directly without a grant-client/book-service stub (mirrors
// the proposeNewEntity/toolProposeNewEntity split in mcp_server.go). Caller must
// have already verified book access.
func (s *Server) setEntityAttributes(ctx context.Context, bookID, entityID, userID uuid.UUID, attrs map[string]string) (entitySetAttributesToolOut, error) {
	var kindID uuid.UUID
	err := s.pool.QueryRow(ctx,
		`SELECT kind_id FROM glossary_entities WHERE entity_id=$1 AND book_id=$2`,
		entityID, bookID,
	).Scan(&kindID)
	if errors.Is(err, pgx.ErrNoRows) {
		return entitySetAttributesToolOut{}, errors.New("entity not found in this book")
	}
	if err != nil {
		return entitySetAttributesToolOut{}, errors.New("entity lookup failed")
	}

	attrDefMap, err := s.loadAttrDefMap(ctx, bookID)
	if err != nil {
		return entitySetAttributesToolOut{}, errors.New("failed to resolve attribute definitions")
	}

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return entitySetAttributesToolOut{}, errors.New("begin tx failed")
	}
	defer tx.Rollback(ctx)

	// Capture BEFORE (pre-edit) snapshot in-tx for the event, same discipline as
	// applyEntityEdit (EDIT-ATOMIC).
	beforeName, beforeKind, beforeAliases, beforeShortDesc, beforeOK := loadEntityEventFields(ctx, tx, entityID)
	var before *EntitySnapshot
	if beforeOK {
		before = &EntitySnapshot{Name: beforeName, Kind: beforeKind, Aliases: beforeAliases, ShortDescription: beforeShortDesc}
	}

	out := entitySetAttributesToolOut{}
	descriptionChanged := false
	for code, val := range attrs {
		trimmedCode := strings.TrimSpace(code)
		defID, ok := attrDefMap[kindID.String()+":"+trimmedCode]
		if !ok {
			out.Skipped = append(out.Skipped, trimmedCode)
			continue
		}
		// UPSERT (unlike applyEntityEdit's UPDATE-only, which requires the row to
		// already exist): an MCP-created entity (createExtractedEntity) only gets a
		// row for attributes actually supplied at creation, so adding a previously-
		// omitted attribute needs INSERT, not just UPDATE. Marked 'verified' (a
		// human/agent-directed write) so a later machine re-extraction's
		// verified-clobber guard (INV-8) won't silently overwrite it.
		var attrValueID uuid.UUID
		err := tx.QueryRow(ctx, `
			INSERT INTO entity_attribute_values (entity_id, attr_def_id, original_language, original_value, confidence)
			VALUES ($1, $2, 'und', $3, 'verified')
			ON CONFLICT (entity_id, attr_def_id)
			DO UPDATE SET original_value = EXCLUDED.original_value, confidence = 'verified'
			RETURNING attr_value_id
		`, entityID, defID, val).Scan(&attrValueID)
		if err != nil {
			return entitySetAttributesToolOut{}, errors.New("write attribute failed: " + trimmedCode)
		}
		// D-GLOSSARY-MULTIROW slice 2 — sync per-item child rows for a LIST value
		// (scalar ⇒ no-op), matching applyEntityEdit's parity.
		if err := syncListItemsByID(ctx, tx, attrValueID, val, "verified", nil); err != nil {
			return entitySetAttributesToolOut{}, errors.New("item sync failed: " + trimmedCode)
		}
		if trimmedCode == "description" {
			descriptionChanged = true
		}
		out.Updated = append(out.Updated, trimmedCode)
	}

	if len(out.Updated) == 0 {
		return entitySetAttributesToolOut{}, errors.New("no valid attribute codes for this entity's kind")
	}

	// One updated_at bump for the whole edit (parity with applyEntityEdit's single
	// H5 version token).
	if _, err := tx.Exec(ctx, `UPDATE glossary_entities SET updated_at = now() WHERE entity_id = $1`, entityID); err != nil {
		return entitySetAttributesToolOut{}, errors.New("version bump failed")
	}
	if err := refreshEntityDedupKey(ctx, tx, entityID); err != nil {
		if errors.Is(err, errDuplicateName) {
			return entitySetAttributesToolOut{}, errors.New("an entity with this name already exists in this book")
		}
		return entitySetAttributesToolOut{}, errors.New("dedup key refresh failed")
	}

	afterName, afterKind, afterAliases, afterShortDesc, _ := loadEntityEventFields(ctx, tx, entityID)
	payload := buildEntityEventPayload(
		bookID.String(), entityID.String(),
		afterName, afterKind, afterAliases, afterShortDesc, "updated",
		"user", userID.String(), before,
	)
	if err := emitEntityUpdatedTx(ctx, tx, entityID, payload); err != nil {
		return entitySetAttributesToolOut{}, errors.New("outbox emit failed")
	}
	if err := tx.Commit(ctx); err != nil {
		return entitySetAttributesToolOut{}, errors.New("commit failed")
	}

	// K3.3b parity: if the description attr changed and short_description is still
	// auto, regenerate it (best-effort, post-commit, never fails the request).
	if descriptionChanged {
		if err := s.regenerateAutoShortDescription(ctx, s.pool, entityID); err != nil {
			slog.Warn("glossary_entity_set_attributes: regenerate short_description failed",
				"entity_id", entityID.String(), "error", err.Error())
		}
	}

	return out, nil
}
