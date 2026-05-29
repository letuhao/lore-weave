//go:build integration

package integration

import (
	"context"
	"path/filepath"
	"testing"
	"time"

	"github.com/loreweave/foundation/contracts/incidents"
	"github.com/loreweave/foundation/services/incident-bot/pkg/incidentflow"
	"github.com/loreweave/foundation/services/postmortem-bot/pkg/postmortem"
)

// fakeChannelProvider for the war-room leg (no live Slack).
type fakeChannelProvider struct {
	created []string
	posted  map[string]string
}

func (f *fakeChannelProvider) CreateChannel(ctx context.Context, name, topic string) (string, error) {
	f.created = append(f.created, name)
	return "C-" + name, nil
}
func (f *fakeChannelProvider) Invite(ctx context.Context, channelID string, userIDs []string) error {
	return nil
}
func (f *fakeChannelProvider) PostMessage(ctx context.Context, channelID, text string) error {
	if f.posted == nil {
		f.posted = map[string]string{}
	}
	f.posted[channelID] = text
	return nil
}

// fakeStatusEmitter captures the status-page event the engine emits — this is
// the SAME IncidentDeclaredV1 shape statuspage-updater (DPS 2) consumes.
type fakeStatusEmitter struct {
	emitted []incidents.IncidentDeclaredV1
}

func (f *fakeStatusEmitter) EmitIncidentDeclared(ctx context.Context, ev incidents.IncidentDeclaredV1) error {
	f.emitted = append(f.emitted, ev)
	return nil
}

// TestIncidentFlow_AutoSEV0_FullChain wires the L7.D pipeline end to end:
// fire an auto-SEV0 alert → classify → declare → war room created → status
// page event emitted → IC assigned (separate from fixer) → postmortem stub
// created on close. Mirrors the L7.D.13 acceptance.
func TestIncidentFlow_AutoSEV0_FullChain(t *testing.T) {
	ctx := context.Background()
	repoRoot := filepath.Join("..", "..")
	matrixPath := filepath.Join(repoRoot, "contracts", "incidents", "severity_matrix.yaml")

	matrix, err := incidents.LoadSeverityMatrix(matrixPath)
	if err != nil {
		t.Fatalf("load matrix: %v", err)
	}

	fp := &fakeChannelProvider{}
	emitter := &fakeStatusEmitter{}
	engine, err := incidentflow.New(matrix, fp, emitter)
	if err != nil {
		t.Fatalf("incidentflow.New: %v", err)
	}

	now := time.Unix(1700000000, 0).UTC()
	res, err := engine.Declare(ctx, "INC-2026-0531-0001",
		incidentflow.Signal{AlertName: "AuditHashMismatch", UserVisible: true},
		"Audit hash mismatch detected", "Integrity check failed on canon store",
		[]string{"world", "canon"},
		incidentflow.Roster{ICUserID: "ic-1", FixerUserID: "fix-1", TeamUserIDs: []string{"sec-1"}},
		func() time.Time { return now })
	if err != nil {
		t.Fatalf("Declare: %v", err)
	}

	// 1. Auto-classified SEV0.
	if res.Event.Severity != incidents.SEV0 {
		t.Fatalf("auto-classify = %s want SEV0 (%s)", res.Event.Severity, res.ClassReason)
	}

	// 2. War room created < 30s.
	if res.WarRoom.ChannelName != "incident-inc-2026-0531-0001" {
		t.Errorf("war-room channel = %q", res.WarRoom.ChannelName)
	}
	if res.WarRoom.ElapsedMS >= 30000 {
		t.Errorf("war-room creation %dms exceeds 30s acceptance", res.WarRoom.ElapsedMS)
	}

	// 3. Status-page obligation: SEV0 user-visible → post + banner, event emitted.
	if !res.StatusPage.ShouldPost || !res.StatusPage.AutoBanner {
		t.Errorf("SEV0 user-visible should post + banner; got %+v", res.StatusPage)
	}
	if len(emitter.emitted) != 1 || emitter.emitted[0].IncidentID != "INC-2026-0531-0001" {
		t.Fatalf("status-page emit = %d events (want 1)", len(emitter.emitted))
	}

	// 4. IC assigned, distinct from fixer.
	if res.Assignment.ICUserID == res.Assignment.FixerUserID {
		t.Error("IC must differ from fixer")
	}

	// 5. Close → postmortem stub created.
	closed := incidents.IncidentClosedV1{
		Type: incidents.TypeIncidentClosedV1, IncidentID: res.Event.IncidentID,
		Severity: res.Event.Severity, Title: res.Event.Title, DeclaredAt: now,
		ResolvedAt: now.Add(90 * time.Minute), UserVisible: true, PostmortemDue: true,
	}
	tmplPath := filepath.Join(repoRoot, "docs", "sre", "postmortems", "TEMPLATE.md")
	outDir := t.TempDir()
	pmPath, err := postmortem.WriteStub(tmplPath, outDir, closed)
	if err != nil {
		t.Fatalf("postmortem stub: %v", err)
	}
	if pmPath == "" {
		t.Error("postmortem stub path empty")
	}
}

// TestIncidentFlow_InternalSEV0_NoPublicPost — an internal SEV0 (not
// user-visible) wakes on-call but does NOT raise a public status-page banner.
func TestIncidentFlow_InternalSEV0_NoPublicPost(t *testing.T) {
	matrixPath := filepath.Join("..", "..", "contracts", "incidents", "severity_matrix.yaml")
	matrix, err := incidents.LoadSeverityMatrix(matrixPath)
	if err != nil {
		t.Fatalf("load matrix: %v", err)
	}
	fp := &fakeChannelProvider{}
	emitter := &fakeStatusEmitter{}
	engine, _ := incidentflow.New(matrix, fp, emitter)

	now := time.Unix(1700000000, 0).UTC()
	res, err := engine.Declare(context.Background(), "INC-2",
		incidentflow.Signal{AlertName: "AuditHashMismatch", UserVisible: false},
		"internal hash drift", "", nil,
		incidentflow.Roster{ICUserID: "ic-1", FixerUserID: "fix-1"},
		func() time.Time { return now })
	if err != nil {
		t.Fatalf("Declare: %v", err)
	}
	if res.Event.Severity != incidents.SEV0 {
		t.Fatalf("want SEV0, got %s", res.Event.Severity)
	}
	if res.StatusPage.ShouldPost || len(emitter.emitted) != 0 {
		t.Errorf("internal SEV0 must not post publicly; got %+v emitted=%d", res.StatusPage, len(emitter.emitted))
	}
}

// TestIncidentFlow_RootCauseEnum_Available — the postmortem root-cause enum
// loads with the full SR4 12-class taxonomy (cross-checks the contract).
func TestIncidentFlow_RootCauseEnum_Available(t *testing.T) {
	enumPath := filepath.Join("..", "..", "contracts", "postmortems", "root_cause_enum.yaml")
	enum, err := postmortem.LoadRootCauseEnum(enumPath)
	if err != nil {
		t.Fatalf("LoadRootCauseEnum: %v", err)
	}
	if enum.Count() != 12 {
		t.Errorf("root cause enum = %d classes want 12", enum.Count())
	}
}
