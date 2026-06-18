package api

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/json"
	"log/slog"
	"net/http"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/contracts/adminjwt"

	"github.com/loreweave/auth-service/internal/adminprincipal"
	"github.com/loreweave/auth-service/internal/authjwt"
	"github.com/loreweave/auth-service/internal/ratelimit"
)

// AdminStore is the narrow DB surface the admin-issuance endpoints need. It is
// an interface so the handlers are unit-testable with a fake (no live PG);
// production injects *adminprincipal.Store.
type AdminStore interface {
	Lookup(ctx context.Context, userID uuid.UUID) (adminprincipal.Principal, bool, error)
	InsertAudit(ctx context.Context, row adminprincipal.IssuanceAuditRow) error
}

// adminDeps bundles the admin-issuance dependencies. nil on Server => feature
// disabled (routes not mounted).
type adminDeps struct {
	signer       authjwt.DigestSigner
	store        AdminStore
	issuerSecret []byte
	auditHMACKey []byte
	tokenTTL     time.Duration
	rl           *ratelimit.Limiter
}

// EnableAdminIssuance turns on the 074/075 admin-JWT endpoints. Called by main
// when cfg.AdminIssuanceEnabled, and by tests with an in-process signer + fake
// store. Rate-limit is conservative: admin minting is low-volume.
func (s *Server) EnableAdminIssuance(signer authjwt.DigestSigner, store AdminStore, issuerSecret, auditHMACKey string, tokenTTL time.Duration) {
	s.admin = &adminDeps{
		signer:       signer,
		store:        store,
		issuerSecret: []byte(issuerSecret),
		auditHMACKey: []byte(auditHMACKey),
		tokenTTL:     tokenTTL,
		rl:           ratelimit.New(time.Minute, 10),
	}
}

// requireAdminIssuerToken gates the mint endpoints on the DEDICATED issuer
// secret (distinct from InternalServiceToken, which only guards the benign
// profile read). Constant-time compare. A bad/missing token => 401 with NO
// audit row, so anonymous traffic cannot inflate the append-only audit table.
func (s *Server) requireAdminIssuerToken(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if s.admin == nil {
			writeErr(w, http.StatusNotFound, "AUTH_NOT_FOUND", "admin issuance disabled")
			return
		}
		got := []byte(r.Header.Get("X-Internal-Token"))
		if subtle.ConstantTimeCompare(got, s.admin.issuerSecret) != 1 {
			writeErr(w, http.StatusUnauthorized, "AUTH_UNAUTHORIZED", "invalid internal token")
			return
		}
		next.ServeHTTP(w, r)
	})
}

type adminTokenReq struct {
	UserID string `json:"user_id"`
}

type adminTokenResp struct {
	Token     string `json:"token"`
	JTI       string `json:"jti"`
	ExpiresAt int64  `json:"expires_at"`
}

// adminToken mints a normal admin token for an active admin principal.
func (s *Server) adminToken(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	var req adminTokenReq
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "invalid json")
		return
	}
	uid, err := uuid.Parse(req.UserID)
	if err != nil {
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "invalid user_id")
		return
	}

	p, found, err := s.admin.store.Lookup(ctx, uid)
	if err != nil {
		s.auditBestEffort(ctx, issuanceAudit{actorID: uid, actorHandle: uid.String(), kind: "admin", outcome: "error", denyReason: ptr("lookup failed")})
		writeErr(w, http.StatusInternalServerError, "AUTH_VALIDATION_ERROR", "lookup failed")
		return
	}
	if !found || !p.Active {
		s.auditBestEffort(ctx, issuanceAudit{actorID: uid, actorHandle: uid.String(), kind: "admin", outcome: "deny", denyReason: ptr("not an active admin principal")})
		writeErr(w, http.StatusForbidden, "AUTH_FORBIDDEN", "not an active admin principal")
		return
	}

	issued, err := authjwt.SignAdmin(ctx, s.admin.signer, uid, p.Role, p.Scopes, s.admin.tokenTTL)
	if err != nil {
		s.auditBestEffort(ctx, issuanceAudit{actorID: uid, actorHandle: p.Handle, kind: "admin", outcome: "error", role: &p.Role, scopes: p.Scopes, denyReason: ptr("sign failed")})
		writeErr(w, http.StatusInternalServerError, "AUTH_VALIDATION_ERROR", "sign failed")
		return
	}

	if err := s.auditIssuance(ctx, issuanceAudit{
		actorID: uid, actorHandle: p.Handle, kind: "admin", outcome: "success",
		role: &p.Role, scopes: p.Scopes, jti: &issued.JTI,
		issuedAt: &issued.IssuedAt, expiresAt: &issued.ExpiresAt,
	}); err != nil {
		// Append-only audit is mandatory for an issued credential. No durable
		// record => do not hand out the token.
		writeErr(w, http.StatusInternalServerError, "AUTH_INTERNAL", "audit write failed")
		return
	}
	writeJSON(w, http.StatusOK, adminTokenResp{Token: issued.Token, JTI: issued.JTI.String(), ExpiresAt: issued.ExpiresAt.Unix()})
}

type breakGlassReq struct {
	PrimaryActorToken   string `json:"primary_actor_token"`
	SecondaryActorToken string `json:"secondary_actor_token"`
	Reason              string `json:"reason"`
	IncidentTicket      string `json:"incident_ticket"`
	RequestedTTLSeconds int    `json:"requested_ttl_seconds"`
}

// breakGlassToken mints a break-glass (break_glass=true) token. Threat model
// (PO-locked): elevated authority for catastrophic ops, dual-actor gated —
// assumes normal admin auth WORKS (auth-is-down recovery is out-of-band). Both
// actors present their OWN freshly-issued admin token; body actor IDs are not
// trusted.
func (s *Server) breakGlassToken(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	var req breakGlassReq
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "invalid json")
		return
	}

	pub := s.admin.signer.PublicKey()
	kid := s.admin.signer.KID()

	primary, perr := adminjwt.Verify(req.PrimaryActorToken, pub, kid)
	secondary, serr := adminjwt.Verify(req.SecondaryActorToken, pub, kid)
	if perr != nil || serr != nil {
		s.auditBestEffort(ctx, issuanceAudit{actorID: uuid.Nil, actorHandle: "unknown", kind: "break_glass", outcome: "deny", breakGlass: true, denyReason: ptr("actor token(s) invalid")})
		writeErr(w, http.StatusUnauthorized, "AUTH_UNAUTHORIZED", "actor token(s) invalid")
		return
	}
	// Approver credentials must be NORMAL admin tokens — a break-glass token
	// cannot be re-used to authorize another break-glass mint (would let one 24h
	// token act as a reusable approver). The actor tokens already passed Verify,
	// so attribute this high-signal abuse attempt to the known subjects.
	if primary.BreakGlass || secondary.BreakGlass {
		actorID, _ := uuid.Parse(primary.Subject)
		secondID, _ := uuid.Parse(secondary.Subject)
		s.auditBestEffort(ctx, issuanceAudit{
			actorID: actorID, actorHandle: primary.Subject,
			secondActorID: &secondID, secondActorHandle: ptr(secondary.Subject),
			kind: "break_glass", outcome: "deny", breakGlass: true,
			denyReason: ptr("actor presented a break-glass token; a normal admin token is required"),
		})
		writeErr(w, http.StatusUnauthorized, "AUTH_UNAUTHORIZED", "actor must present a normal admin token, not a break-glass token")
		return
	}

	primaryID, err1 := uuid.Parse(primary.Subject)
	secondaryID, err2 := uuid.Parse(secondary.Subject)
	if err1 != nil || err2 != nil {
		writeErr(w, http.StatusUnauthorized, "AUTH_UNAUTHORIZED", "actor token subject invalid")
		return
	}

	// Both must be distinct active admin principals.
	pp, pfound, perr := s.admin.store.Lookup(ctx, primaryID)
	sp, sfound, serr2 := s.admin.store.Lookup(ctx, secondaryID)
	if perr != nil || serr2 != nil {
		s.auditBestEffort(ctx, issuanceAudit{actorID: primaryID, actorHandle: primaryID.String(), secondActorID: &secondaryID, kind: "break_glass", outcome: "error", breakGlass: true, denyReason: ptr("principal lookup failed")})
		writeErr(w, http.StatusInternalServerError, "AUTH_VALIDATION_ERROR", "principal lookup failed")
		return
	}
	if !pfound || !pp.Active || !sfound || !sp.Active {
		s.auditBestEffort(ctx, issuanceAudit{actorID: primaryID, actorHandle: pp.Handle, secondActorID: &secondaryID, secondActorHandle: &sp.Handle, kind: "break_glass", outcome: "deny", breakGlass: true, denyReason: ptr("an actor is not an active admin principal")})
		writeErr(w, http.StatusForbidden, "AUTH_FORBIDDEN", "an actor is not an active admin principal")
		return
	}

	ttl := time.Duration(req.RequestedTTLSeconds) * time.Second
	bgReq := adminjwt.BreakGlassRequest{
		PrimaryActor:   primaryID.String(),
		SecondaryActor: secondaryID.String(),
		Reason:         req.Reason,
		IncidentTicket: req.IncidentTicket,
		RequestedTTL:   ttl,
	}
	if err := adminjwt.ValidateBreakGlass(bgReq); err != nil {
		s.auditBestEffort(ctx, issuanceAudit{actorID: primaryID, actorHandle: pp.Handle, secondActorID: &secondaryID, secondActorHandle: &sp.Handle, kind: "break_glass", outcome: "deny", breakGlass: true, incidentTicket: &req.IncidentTicket, denyReason: ptr(err.Error())})
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "break-glass policy violation")
		return
	}

	issued, err := authjwt.SignBreakGlass(ctx, s.admin.signer, primaryID, pp.Role, pp.Scopes, ttl)
	if err != nil {
		s.auditBestEffort(ctx, issuanceAudit{actorID: primaryID, actorHandle: pp.Handle, secondActorID: &secondaryID, secondActorHandle: &sp.Handle, kind: "break_glass", outcome: "error", breakGlass: true, denyReason: ptr("sign failed")})
		writeErr(w, http.StatusInternalServerError, "AUTH_VALIDATION_ERROR", "sign failed")
		return
	}

	reasonLen := len(req.Reason)
	mac := hmac.New(sha256.New, s.admin.auditHMACKey)
	mac.Write([]byte(req.Reason))
	if err := s.auditIssuance(ctx, issuanceAudit{
		actorID: primaryID, actorHandle: pp.Handle,
		secondActorID: &secondaryID, secondActorHandle: &sp.Handle,
		kind: "break_glass", outcome: "success", breakGlass: true,
		role: &pp.Role, scopes: pp.Scopes,
		incidentTicket: &req.IncidentTicket, reasonLen: &reasonLen, reasonHMAC: mac.Sum(nil),
		jti: &issued.JTI, issuedAt: &issued.IssuedAt, expiresAt: &issued.ExpiresAt,
	}); err != nil {
		// Break-glass is the highest-authority credential — never issue it
		// without a durable dual-actor audit record.
		writeErr(w, http.StatusInternalServerError, "AUTH_INTERNAL", "audit write failed")
		return
	}
	writeJSON(w, http.StatusOK, adminTokenResp{Token: issued.Token, JTI: issued.JTI.String(), ExpiresAt: issued.ExpiresAt.Unix()})
}

// issuanceAudit is the handler-facing shape; auditIssuance maps it to a row.
type issuanceAudit struct {
	actorID           uuid.UUID
	actorHandle       string
	secondActorID     *uuid.UUID
	secondActorHandle *string
	kind              string
	outcome           string
	denyReason        *string
	role              *string
	scopes            []string
	breakGlass        bool
	incidentTicket    *string
	reasonLen         *int
	reasonHMAC        []byte
	jti               *uuid.UUID
	issuedAt          *time.Time
	expiresAt         *time.Time
}

// auditIssuance writes one append-only issuance row and returns the write
// error. SUCCESS callers MUST treat a non-nil error as fatal (do not return the
// minted token without a durable audit record — this is the highest-authority
// credential in the system). DENY/ERROR callers may best-effort ignore it (the
// response is already a rejection).
func (s *Server) auditIssuance(ctx context.Context, a issuanceAudit) error {
	row := adminprincipal.IssuanceAuditRow{
		AuditID:           uuid.New(),
		ActorID:           a.actorID,
		ActorHandle:       a.actorHandle,
		SecondActorID:     a.secondActorID,
		SecondActorHandle: a.secondActorHandle,
		TokenKind:         a.kind,
		Outcome:           a.outcome,
		DenyReason:        a.denyReason,
		Role:              a.role,
		Scopes:            a.scopes,
		BreakGlass:        a.breakGlass,
		IncidentTicket:    a.incidentTicket,
		ReasonLen:         a.reasonLen,
		ReasonHMAC:        a.reasonHMAC,
		JTI:               a.jti,
		CreatedAtNanos:    time.Now().UnixNano(),
	}
	if a.issuedAt != nil {
		n := a.issuedAt.UnixNano()
		row.IssuedAtNanos = &n
	}
	if a.expiresAt != nil {
		n := a.expiresAt.UnixNano()
		row.ExpiresAtNanos = &n
	}
	return s.admin.store.InsertAudit(ctx, row)
}

// auditBestEffort records a deny/error attempt and, if the append-only write
// itself fails, emits a high-signal ERROR log (the response is already a
// rejection so we do not fail the request, but a dropped abuse-probe record
// must not vanish silently). Full durability of deny rows under DB pressure is
// tracked as D-ADMIN-ISSUANCE-DENY-AUDIT-DURABILITY.
func (s *Server) auditBestEffort(ctx context.Context, a issuanceAudit) {
	if err := s.auditIssuance(ctx, a); err != nil {
		slog.Error("admin issuance audit write failed (deny/error path)",
			"outcome", a.outcome, "token_kind", a.kind, "actor_id", a.actorID, "error", err)
	}
}

func ptr[T any](v T) *T { return &v }
