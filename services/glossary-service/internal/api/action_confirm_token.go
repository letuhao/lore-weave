package api

import (
	"crypto/hmac"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"github.com/google/uuid"
)

// Generalized class-C confirm token (spec §13) — the single mint/confirm spine
// behind every high-impact glossary action (book_delete, schema creates today;
// adopt/sync/system writes later). Supersedes the schema-specific token: same
// stateless-HMAC scheme, generalized to carry an action descriptor + authority
// kind + a single-use jti.
//
// The token is a stateless HMAC over the claims, keyed by the service JWT secret
// with a domain separator so it can never be confused with a real JWT. Forging
// one requires the JWT secret — i.e. a full service compromise, out of scope.
//
// Single-use is NOT in the token itself (it is stateless) — it is enforced at
// confirm time by recording the jti in the consumed_tokens ledger (§13.4). The
// token binds intent + authority + identity + expiry; the ledger makes it
// one-shot.

const (
	actionTokenDomain = "gloss-action-confirm:v1|" // domain separator (never a JWT)
	actionTokenTTL    = 10 * time.Minute           // human has time to read + confirm

	// authority kinds — selects the confirm-time re-check branch (§13.5).
	authorityGrant = "grant" // book/user tiers: re-check the proposing user + Manage grant
	authorityAdmin = "admin" // System tier: re-check the RS256 admin token (T4)

	// action descriptors LIVE in Foundation (§13.1). Reserved descriptors
	// (adopt, sync_apply, book_set_*, system_*) are intentionally NOT accepted
	// yet — verify fails closed on them until their phase wires the effect.
	descBookDelete        = "book_delete"
	// descBookDeleteBatch — tool-catalog-simplification spec (glossary_ontology_delete,
	// scope=book): ONE confirm token covers N items, mirroring descSchemaCreateKinds'
	// per-item-independent, idempotent-skip pattern (§8.8).
	descBookDeleteBatch   = "book_delete_batch"
	descSchemaCreateKind  = "schema_create_kind"
	descSchemaCreateKinds = "schema_create_kinds" // BATCH: many kinds (+ their attrs) on ONE confirm
	descSchemaCreateAttr  = "schema_create_attribute"
	descAdopt             = "adopt"       // T1 — scaffold a book by copy-down from standards
	descSyncApply         = "sync_apply"  // T2 — apply a proposed per-row sync choice set
	descBookRevert        = "book_revert" // G-U1 — revert a book override back to its parent tier

	// Pipeline M2 — high-impact / destructive entity-curation writes (authorityGrant,
	// Manage-gated at confirm). Each effect re-validates against current state (§13.5).
	descStatusChange    = "status_change"    // batch set entity status
	descRestoreRevision = "restore_revision" // restore an entity to a prior revision (prune+upsert)
	descReassignKind    = "reassign_kind"    // move an entity to another kind (drops non-matching attrs)
	descMerge           = "merge"            // merge loser entities into a winner (destructive; journaled)

	// glossary_entity_delete — Tier-W propose+confirm soft-delete of ONE glossary
	// entity (real-usage feedback finding: no MCP way to remove a genuinely empty/
	// garbage extraction-draft entity). Its restore counterpart, glossary_entity_restore,
	// is Tier-A/direct (no token) — see entity_delete_tools.go.
	descEntityDelete = "entity_delete"

	// S5 — web-search deep-research (authorityGrant, Manage-gated). Class-C because it is
	// a PAID outward call (S21 cost gate); the effect runs the search + attaches sources as
	// draft evidence. Additive (not destructive).
	descDeepResearch = "deep_research"

	// Plan/Action kit — execute a typed multi-op plan on ONE confirm (loreweave_mcp).
	// The op-set spans additive ops + Phase-2 destructive deletes (gated per-op by
	// enabled_ops at confirm). MUST equal loreweave_mcp.DescriptorExecutePlan.
	descExecutePlan = "execute_plan"

	// #27/#29/#30 coalesce — the chat run-loop bundles the N child confirm_tokens a turn
	// minted into ONE card; the FE confirms/previews the bundle at /actions/(confirm|preview)
	// -batch. descBatch is ONLY a response/card label — no token is ever signed with it (the
	// children keep their own descriptors); it tells the FE to route to the batch endpoints.
	descBatch = "glossary.batch"

	// T4 — System-tier admin writes (authorityAdmin only; confirmed via the
	// RS256-gated /v1/glossary/actions/admin/confirm, never the user path). Verb is
	// the descriptor, entity is the `level` in params (genre|kind|attribute).
	descSystemCreate  = "system_create"
	descSystemPatch   = "system_patch"
	descSystemDelete  = "system_delete"
	descSystemRestore = "system_restore" // G-C8 — restore a soft-deleted System row from the recycle bin
)

var (
	ErrActionTokenInvalid = errors.New("action confirm token is invalid")
	ErrActionTokenExpired = errors.New("action confirm token has expired")
)

// liveDescriptor reports whether a descriptor is wired in this build. An unknown
// or not-yet-implemented descriptor is rejected at verify (fail closed) so a token
// can never carry intent the confirm path doesn't fully validate.
func liveDescriptor(d string) bool {
	switch d {
	case descBookDelete, descBookDeleteBatch, descSchemaCreateKind, descSchemaCreateKinds, descSchemaCreateAttr, descAdopt, descSyncApply, descBookRevert,
		descStatusChange, descRestoreRevision, descReassignKind, descMerge, descDeepResearch, descExecutePlan, descEntityDelete,
		descSystemCreate, descSystemPatch, descSystemDelete, descSystemRestore:
		return true
	default:
		return false
	}
}

// actionClaims is the signed payload. Params is the opaque action-spec captured at
// propose time (resolved ids, validated codes); confirm trusts it because it is
// inside the HMAC, but STILL re-validates the action against current state (§13.5).
type actionClaims struct {
	JTI        string          `json:"jti"`            // single-use id (recorded at confirm)
	Authority  string          `json:"auth"`           // authorityGrant | authorityAdmin
	UserID     uuid.UUID       `json:"u"`              // grant authority: the proposing user
	AdminSub   string          `json:"asub,omitempty"` // admin authority: the RS256 subject (T4)
	BookID     uuid.UUID       `json:"b"`              // book-scoped actions
	Descriptor string          `json:"d"`
	Params     json.RawMessage `json:"p"`
	Exp        int64           `json:"exp"` // unix seconds
}

// mintActionToken signs a confirm token. The caller fills authority/descriptor/
// identity/params + a fresh jti; mint stamps the expiry. An empty secret or jti is
// a misconfiguration and yields an empty token (caller treats that as "cannot mint"
// → fail closed).
func mintActionToken(secret string, c actionClaims, now time.Time) string {
	if secret == "" || strings.TrimSpace(c.JTI) == "" || !liveDescriptor(c.Descriptor) {
		return ""
	}
	c.Exp = now.Add(actionTokenTTL).Unix()
	payload, err := json.Marshal(c)
	if err != nil {
		return ""
	}
	payloadB64 := base64.RawURLEncoding.EncodeToString(payload)
	sig := actionTokenSign(secret, payloadB64)
	return payloadB64 + "." + base64.RawURLEncoding.EncodeToString(sig)
}

// verifyActionToken checks the signature (constant-time), the descriptor (must be
// live), and expiry. Signature/format/unknown-descriptor → ErrActionTokenInvalid;
// a valid-but-stale token → ErrActionTokenExpired (distinct so the UI says "re-propose").
func verifyActionToken(secret, token string, now time.Time) (actionClaims, error) {
	var zero actionClaims
	if secret == "" {
		return zero, ErrActionTokenInvalid
	}
	parts := strings.Split(token, ".")
	if len(parts) != 2 || parts[0] == "" || parts[1] == "" {
		return zero, ErrActionTokenInvalid
	}
	sig, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return zero, ErrActionTokenInvalid
	}
	expected := actionTokenSign(secret, parts[0])
	if subtle.ConstantTimeCompare(sig, expected) != 1 {
		return zero, ErrActionTokenInvalid
	}
	payload, err := base64.RawURLEncoding.DecodeString(parts[0])
	if err != nil {
		return zero, ErrActionTokenInvalid
	}
	var claims actionClaims
	if err := json.Unmarshal(payload, &claims); err != nil {
		return zero, ErrActionTokenInvalid
	}
	if !liveDescriptor(claims.Descriptor) || strings.TrimSpace(claims.JTI) == "" {
		return zero, ErrActionTokenInvalid
	}
	if claims.Authority != authorityGrant && claims.Authority != authorityAdmin {
		return zero, ErrActionTokenInvalid
	}
	if now.Unix() >= claims.Exp {
		return zero, ErrActionTokenExpired
	}
	return claims, nil
}

func actionTokenSign(secret, payloadB64 string) []byte {
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write([]byte(actionTokenDomain))
	mac.Write([]byte(payloadB64))
	return mac.Sum(nil)
}
