package war_room

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/loreweave/foundation/contracts/incidents"
)

// fakeProvider records calls and lets tests inject failures + latency.
type fakeProvider struct {
	created    []string
	invited    map[string][]string
	posted     map[string]string
	createErr  error
	inviteErr  error
	postErr    error
	createTook time.Duration
}

func newFake() *fakeProvider {
	return &fakeProvider{invited: map[string][]string{}, posted: map[string]string{}}
}

func (f *fakeProvider) CreateChannel(ctx context.Context, name, topic string) (string, error) {
	if f.createErr != nil {
		return "", f.createErr
	}
	f.created = append(f.created, name)
	return "C-" + name, nil
}

func (f *fakeProvider) Invite(ctx context.Context, channelID string, userIDs []string) error {
	if f.inviteErr != nil {
		return f.inviteErr
	}
	f.invited[channelID] = userIDs
	return nil
}

func (f *fakeProvider) PostMessage(ctx context.Context, channelID, text string) error {
	if f.postErr != nil {
		return f.postErr
	}
	f.posted[channelID] = text
	return nil
}

func declared() incidents.IncidentDeclaredV1 {
	return incidents.NewIncidentDeclaredV1(
		"INC-2026-0531-0001", incidents.SEV0, "DB primary down",
		"Primary database unreachable", "audit_hash_mismatch", true,
		[]string{"gateway"}, time.Now(), "ic-1")
}

func TestNew_NilProvider(t *testing.T) {
	if _, err := New(nil); err == nil {
		t.Error("New(nil) must error")
	}
}

func TestChannelName(t *testing.T) {
	if got := ChannelName("INC-2026-0531-0001"); got != "incident-inc-2026-0531-0001" {
		t.Errorf("ChannelName = %q", got)
	}
	long := ChannelName("INC-" + string(make([]byte, 200)))
	if len(long) > 80 {
		t.Errorf("channel name not truncated: len=%d", len(long))
	}
}

func TestCreate_HappyPath(t *testing.T) {
	f := newFake()
	m, _ := New(f)
	roster := Roster{ICUserID: "ic-1", FixerUserID: "fix-1", TeamUserIDs: []string{"t-1", "t-2", "ic-1"}}
	res, err := m.Create(context.Background(), declared(), roster, time.Now)
	if err != nil {
		t.Fatalf("Create: %v", err)
	}
	if res.ChannelName != "incident-inc-2026-0531-0001" {
		t.Errorf("channel name = %q", res.ChannelName)
	}
	// ic-1 appears twice in roster (IC + team) → must be deduped.
	if len(res.Invited) != 4 { // ic-1, fix-1, t-1, t-2
		t.Errorf("invited = %v (want 4 deduped)", res.Invited)
	}
	if _, ok := f.posted[res.ChannelID]; !ok {
		t.Error("severity card not posted")
	}
}

func TestCreate_InvalidEvent(t *testing.T) {
	f := newFake()
	m, _ := New(f)
	bad := incidents.IncidentDeclaredV1{} // missing everything
	if _, err := m.Create(context.Background(), bad, Roster{}, time.Now); err == nil {
		t.Error("invalid event must fail")
	}
}

func TestCreate_ProviderError(t *testing.T) {
	f := newFake()
	f.createErr = errors.New("slack down")
	m, _ := New(f)
	if _, err := m.Create(context.Background(), declared(), Roster{ICUserID: "ic-1"}, time.Now); err == nil {
		t.Error("provider create error must propagate")
	}
}

func TestCreate_Under30s(t *testing.T) {
	// Acceptance: war-room creation < 30s. Simulate a clock that advances
	// 12s across the operation and assert we report < 30000ms.
	f := newFake()
	m, _ := New(f)
	base := time.Unix(1700000000, 0)
	calls := 0
	clock := func() time.Time {
		// first call = start; subsequent = +12s
		if calls == 0 {
			calls++
			return base
		}
		return base.Add(12 * time.Second)
	}
	res, err := m.Create(context.Background(), declared(), Roster{ICUserID: "ic-1"}, clock)
	if err != nil {
		t.Fatalf("Create: %v", err)
	}
	if res.ElapsedMS >= 30000 {
		t.Errorf("war-room creation took %dms; acceptance < 30s", res.ElapsedMS)
	}
}

func TestLoadSlackConfigFromEnv_FailClosed(t *testing.T) {
	t.Setenv("SLACK_BOT_TOKEN", "")
	if _, err := LoadSlackConfigFromEnv(); err == nil {
		t.Error("missing SLACK_BOT_TOKEN must fail closed")
	}
	t.Setenv("SLACK_BOT_TOKEN", "xoxb-test")
	cfg, err := LoadSlackConfigFromEnv()
	if err != nil || cfg.BotToken != "xoxb-test" {
		t.Errorf("LoadSlackConfigFromEnv = %+v, %v", cfg, err)
	}
}

func TestNewSlackProvider_RequiresToken(t *testing.T) {
	if _, err := NewSlackProvider(SlackConfig{}); err == nil {
		t.Error("NewSlackProvider without token must error")
	}
}
