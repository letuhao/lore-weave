package updater

import (
	"context"
	"errors"
	"path/filepath"
	"testing"
	"time"

	"github.com/loreweave/foundation/contracts/incidents"
	"github.com/loreweave/foundation/services/statuspage-updater/internal/config"
)

type fakeClient struct {
	created   []IncidentPost
	updated   []IncidentPost
	resolved  []string
	createErr error
	nextID    int
}

func (f *fakeClient) CreateIncident(ctx context.Context, p IncidentPost) (string, error) {
	if f.createErr != nil {
		return "", f.createErr
	}
	f.created = append(f.created, p)
	f.nextID++
	return "prov-" + p.IncidentID, nil
}
func (f *fakeClient) UpdateIncident(ctx context.Context, pid string, p IncidentPost) error {
	f.updated = append(f.updated, p)
	return nil
}
func (f *fakeClient) ResolveIncident(ctx context.Context, pid, body string) error {
	f.resolved = append(f.resolved, pid)
	return nil
}

func loadCfg(t *testing.T) (*config.Components, *config.BannerConfig) {
	t.Helper()
	base := filepath.Join("..", "..", "..", "..", "infra", "statuspage")
	comp, err := config.LoadComponents(filepath.Join(base, "components.yaml"))
	if err != nil {
		t.Fatalf("load components: %v", err)
	}
	ban, err := config.LoadBannerConfig(filepath.Join(base, "banner-config.yaml"))
	if err != nil {
		t.Fatalf("load banner: %v", err)
	}
	return comp, ban
}

func declared(sev incidents.Severity, uv bool, comps []string) incidents.IncidentDeclaredV1 {
	return incidents.NewIncidentDeclaredV1("INC-1", sev, "Title", "Summary", "trig", uv, comps, time.Now(), "ic")
}

func TestNew_NilDeps(t *testing.T) {
	comp, ban := loadCfg(t)
	if _, err := New(nil, comp, ban); err == nil {
		t.Error("nil client must error")
	}
	if _, err := New(&fakeClient{}, nil, ban); err == nil {
		t.Error("nil components must error")
	}
	if _, err := New(&fakeClient{}, comp, nil); err == nil {
		t.Error("nil banner must error")
	}
}

func TestShouldHandle(t *testing.T) {
	comp, ban := loadCfg(t)
	u, _ := New(&fakeClient{}, comp, ban)
	cases := []struct {
		sev  incidents.Severity
		uv   bool
		want bool
	}{
		{incidents.SEV0, true, true},
		{incidents.SEV0, false, false}, // internal SEV0 → not public
		{incidents.SEV1, true, true},
		{incidents.SEV2, true, true},  // minor impact, still posts
		{incidents.SEV3, true, false}, // impact none → never
	}
	for _, c := range cases {
		if got := u.ShouldHandle(declared(c.sev, c.uv, nil)); got != c.want {
			t.Errorf("ShouldHandle(%s,uv=%v) = %v want %v", c.sev, c.uv, got, c.want)
		}
	}
}

func TestOnDeclared_CreatesWithBanner(t *testing.T) {
	comp, ban := loadCfg(t)
	f := &fakeClient{}
	u, _ := New(f, comp, ban)
	posted, err := u.OnDeclared(context.Background(), declared(incidents.SEV0, true, []string{"gateway", "world"}))
	if err != nil {
		t.Fatalf("OnDeclared: %v", err)
	}
	if !posted || len(f.created) != 1 {
		t.Fatalf("SEV0 user-visible should create one incident; posted=%v created=%d", posted, len(f.created))
	}
	p := f.created[0]
	if p.Impact != ImpactCritical {
		t.Errorf("SEV0 impact = %s want critical", p.Impact)
	}
	if !p.Banner {
		t.Error("SEV0 user-visible must banner")
	}
	if len(p.ComponentIDs) != 2 {
		t.Errorf("component ids = %v want [gateway world]", p.ComponentIDs)
	}
	if u.TrackedCount() != 1 {
		t.Errorf("tracked = %d want 1", u.TrackedCount())
	}
}

func TestOnDeclared_DropsUnknownComponents(t *testing.T) {
	comp, ban := loadCfg(t)
	f := &fakeClient{}
	u, _ := New(f, comp, ban)
	_, err := u.OnDeclared(context.Background(), declared(incidents.SEV1, true, []string{"gateway", "internal-secret-subsystem"}))
	if err != nil {
		t.Fatalf("OnDeclared: %v", err)
	}
	if got := f.created[0].ComponentIDs; len(got) != 1 || got[0] != "gateway" {
		t.Errorf("unknown component not dropped: %v", got)
	}
}

func TestOnDeclared_NoopInternal(t *testing.T) {
	comp, ban := loadCfg(t)
	f := &fakeClient{}
	u, _ := New(f, comp, ban)
	posted, err := u.OnDeclared(context.Background(), declared(incidents.SEV0, false, nil))
	if err != nil {
		t.Fatalf("OnDeclared: %v", err)
	}
	if posted || len(f.created) != 0 {
		t.Error("internal SEV0 must be a no-op")
	}
}

func TestOnDeclared_CreateError(t *testing.T) {
	comp, ban := loadCfg(t)
	f := &fakeClient{createErr: errors.New("statuspage 500")}
	u, _ := New(f, comp, ban)
	if _, err := u.OnDeclared(context.Background(), declared(incidents.SEV0, true, nil)); err == nil {
		t.Error("create error must propagate")
	}
}

func TestOnUpdated_AppendsToTracked(t *testing.T) {
	comp, ban := loadCfg(t)
	f := &fakeClient{}
	u, _ := New(f, comp, ban)
	_, _ = u.OnDeclared(context.Background(), declared(incidents.SEV0, true, nil))
	upd := incidents.IncidentUpdatedV1{
		Type: incidents.TypeIncidentUpdatedV1, IncidentID: "INC-1",
		Severity: incidents.SEV0, Status: "identified", Message: "fix in progress", UpdatedAt: time.Now(),
	}
	if err := u.OnUpdated(context.Background(), upd); err != nil {
		t.Fatalf("OnUpdated: %v", err)
	}
	if len(f.updated) != 1 || f.updated[0].Status != "identified" {
		t.Errorf("update not appended: %+v", f.updated)
	}
}

func TestOnUpdated_IgnoresUntracked(t *testing.T) {
	comp, ban := loadCfg(t)
	f := &fakeClient{}
	u, _ := New(f, comp, ban)
	upd := incidents.IncidentUpdatedV1{
		Type: incidents.TypeIncidentUpdatedV1, IncidentID: "INC-UNKNOWN",
		Severity: incidents.SEV1, Status: "monitoring", UpdatedAt: time.Now(),
	}
	if err := u.OnUpdated(context.Background(), upd); err != nil {
		t.Fatalf("OnUpdated should ignore untracked: %v", err)
	}
	if len(f.updated) != 0 {
		t.Error("untracked update must not call provider")
	}
}

func TestOnClosed_ResolvesAndUntracks(t *testing.T) {
	comp, ban := loadCfg(t)
	f := &fakeClient{}
	u, _ := New(f, comp, ban)
	now := time.Now()
	dev := declared(incidents.SEV0, true, nil)
	dev.DeclaredAt = now
	_, _ = u.OnDeclared(context.Background(), dev)
	closed := incidents.IncidentClosedV1{
		Type: incidents.TypeIncidentClosedV1, IncidentID: "INC-1",
		Severity: incidents.SEV0, DeclaredAt: now, ResolvedAt: now.Add(time.Hour),
	}
	if err := u.OnClosed(context.Background(), closed); err != nil {
		t.Fatalf("OnClosed: %v", err)
	}
	if len(f.resolved) != 1 {
		t.Errorf("resolve calls = %d want 1", len(f.resolved))
	}
	if u.TrackedCount() != 0 {
		t.Errorf("incident not untracked after close: %d", u.TrackedCount())
	}
}

func TestLoadProviderConfig_FailClosed(t *testing.T) {
	t.Setenv("STATUSPAGE_API_KEY", "")
	t.Setenv("STATUSPAGE_PAGE_ID", "")
	if _, err := LoadProviderConfigFromEnv(); err == nil {
		t.Error("missing creds must fail closed")
	}
	t.Setenv("STATUSPAGE_API_KEY", "k")
	t.Setenv("STATUSPAGE_PAGE_ID", "p")
	if _, err := LoadProviderConfigFromEnv(); err != nil {
		t.Errorf("valid creds: %v", err)
	}
}

func TestNewStatuspageIOClient_RequiresCreds(t *testing.T) {
	if _, err := NewStatuspageIOClient(ProviderConfig{}); err == nil {
		t.Error("client without creds must error")
	}
}
