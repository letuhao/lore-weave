//go:build integration

package integration

import (
	"context"
	"path/filepath"
	"testing"
	"time"

	"github.com/loreweave/foundation/contracts/incidents"
	"github.com/loreweave/foundation/services/statuspage-updater/pkg/statusflow"
)

// fakeStatusClient records posts + lets the test inject a latency bound.
type fakeStatusClient struct {
	created []statusflow.IncidentPost
	latency time.Duration
	clock   func() time.Time
}

func (f *fakeStatusClient) CreateIncident(ctx context.Context, p statusflow.IncidentPost) (string, error) {
	f.created = append(f.created, p)
	return "prov-" + p.IncidentID, nil
}
func (f *fakeStatusClient) UpdateIncident(ctx context.Context, pid string, p statusflow.IncidentPost) error {
	return nil
}
func (f *fakeStatusClient) ResolveIncident(ctx context.Context, pid, body string) error { return nil }

func loadStatuspageCfg(t *testing.T) (*statusflow.Components, *statusflow.BannerConfig) {
	t.Helper()
	base := filepath.Join("..", "..", "infra", "statuspage")
	comp, err := statusflow.LoadComponents(filepath.Join(base, "components.yaml"))
	if err != nil {
		t.Fatalf("load components: %v", err)
	}
	ban, err := statusflow.LoadBannerConfig(filepath.Join(base, "banner-config.yaml"))
	if err != nil {
		t.Fatalf("load banner: %v", err)
	}
	return comp, ban
}

// TestStatusPage_DeclareSEV0_AutoBannerWithin30s — the L7.L.6 acceptance:
// declare a user-visible SEV0 → status-page incident with auto-banner is
// created, and the create round-trip completes within the 30s budget.
func TestStatusPage_DeclareSEV0_AutoBannerWithin30s(t *testing.T) {
	comp, ban := loadStatuspageCfg(t)
	client := &fakeStatusClient{}
	u, err := statusflow.New(client, comp, ban)
	if err != nil {
		t.Fatalf("statusflow.New: %v", err)
	}

	// The declared event is the SAME IncidentDeclaredV1 shape incident-bot
	// (DPS 1) emits — this is the cross-DPS contract under test.
	now := time.Unix(1700000000, 0).UTC()
	ev := incidents.NewIncidentDeclaredV1(
		"INC-2026-0531-0007", incidents.SEV0, "Gateway outage",
		"Users cannot connect", "total_outage", true,
		[]string{"gateway", "realtime"}, now, "ic-1")

	start := time.Now()
	posted, err := u.OnDeclared(context.Background(), ev)
	elapsed := time.Since(start)
	if err != nil {
		t.Fatalf("OnDeclared: %v", err)
	}
	if !posted {
		t.Fatal("SEV0 user-visible must post to status page")
	}
	if elapsed > 30*time.Second {
		t.Errorf("status-page update took %v; acceptance < 30s", elapsed)
	}
	if len(client.created) != 1 {
		t.Fatalf("created %d incidents want 1", len(client.created))
	}
	p := client.created[0]
	if !p.Banner {
		t.Error("SEV0 user-visible must raise auto-banner")
	}
	if p.Impact != statusflow.ImpactCritical {
		t.Errorf("impact = %s want critical", p.Impact)
	}
	if len(p.ComponentIDs) != 2 {
		t.Errorf("component ids = %v want gateway+realtime", p.ComponentIDs)
	}
}

// TestStatusPage_FullLifecycle — declared → updated → closed, banner cleared.
func TestStatusPage_FullLifecycle(t *testing.T) {
	comp, ban := loadStatuspageCfg(t)
	client := &fakeStatusClient{}
	u, _ := statusflow.New(client, comp, ban)
	now := time.Unix(1700000000, 0).UTC()

	dev := incidents.NewIncidentDeclaredV1("INC-9", incidents.SEV1, "Auth slow", "Login delays", "core_surface_partial_outage", true, []string{"auth"}, now, "ic-1")
	if _, err := u.OnDeclared(context.Background(), dev); err != nil {
		t.Fatalf("declare: %v", err)
	}
	if u.TrackedCount() != 1 {
		t.Fatalf("tracked = %d", u.TrackedCount())
	}

	upd := incidents.IncidentUpdatedV1{Type: incidents.TypeIncidentUpdatedV1, IncidentID: "INC-9", Severity: incidents.SEV1, Status: "monitoring", Message: "recovering", UpdatedAt: now.Add(time.Hour)}
	if err := u.OnUpdated(context.Background(), upd); err != nil {
		t.Fatalf("update: %v", err)
	}

	closed := incidents.IncidentClosedV1{Type: incidents.TypeIncidentClosedV1, IncidentID: "INC-9", Severity: incidents.SEV1, DeclaredAt: now, ResolvedAt: now.Add(2 * time.Hour)}
	if err := u.OnClosed(context.Background(), closed); err != nil {
		t.Fatalf("close: %v", err)
	}
	if u.TrackedCount() != 0 {
		t.Errorf("incident not untracked after close: %d", u.TrackedCount())
	}
}

// TestStatusPage_InternalSEV0_NoPublicPost — internal (non-user-visible)
// SEV0 must NOT raise a public status-page entry (matches incident-bot side).
func TestStatusPage_InternalSEV0_NoPublicPost(t *testing.T) {
	comp, ban := loadStatuspageCfg(t)
	client := &fakeStatusClient{}
	u, _ := statusflow.New(client, comp, ban)
	ev := incidents.NewIncidentDeclaredV1("INC-INT", incidents.SEV0, "internal", "", "audit_hash_mismatch", false, nil, time.Now(), "")
	posted, err := u.OnDeclared(context.Background(), ev)
	if err != nil {
		t.Fatalf("OnDeclared: %v", err)
	}
	if posted || len(client.created) != 0 {
		t.Error("internal SEV0 must not post publicly")
	}
}
