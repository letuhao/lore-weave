package statuspage

import (
	"context"
	"errors"
	"path/filepath"
	"testing"
	"time"

	"github.com/loreweave/foundation/contracts/incidents"
)

type fakeEmitter struct {
	emitted []incidents.IncidentDeclaredV1
	err     error
}

func (f *fakeEmitter) EmitIncidentDeclared(ctx context.Context, ev incidents.IncidentDeclaredV1) error {
	if f.err != nil {
		return f.err
	}
	f.emitted = append(f.emitted, ev)
	return nil
}

func matrix(t *testing.T) *incidents.SeverityMatrix {
	t.Helper()
	p := filepath.Join("..", "..", "..", "..", "contracts", "incidents", "severity_matrix.yaml")
	m, err := incidents.LoadSeverityMatrix(p)
	if err != nil {
		t.Fatalf("load matrix: %v", err)
	}
	return m
}

func ev(sev incidents.Severity, userVisible bool) incidents.IncidentDeclaredV1 {
	return incidents.NewIncidentDeclaredV1("INC-1", sev, "t", "s", "trig", userVisible, nil, time.Now(), "ic")
}

func TestNew_NilDeps(t *testing.T) {
	m := matrix(t)
	if _, err := New(nil, &fakeEmitter{}); err == nil {
		t.Error("nil matrix must error")
	}
	if _, err := New(m, nil); err == nil {
		t.Error("nil emitter must error")
	}
}

func TestDecide(t *testing.T) {
	p, _ := New(matrix(t), &fakeEmitter{})
	cases := []struct {
		sev        incidents.Severity
		uv         bool
		wantPost   bool
		wantBanner bool
	}{
		{incidents.SEV0, true, true, true},
		{incidents.SEV0, false, false, false}, // internal SEV0 → no public post
		{incidents.SEV1, true, true, true},
		{incidents.SEV2, true, true, false},  // conditional post, no banner
		{incidents.SEV3, true, false, false}, // never
	}
	for _, c := range cases {
		d := p.Decide(ev(c.sev, c.uv))
		if d.ShouldPost != c.wantPost || d.AutoBanner != c.wantBanner {
			t.Errorf("Decide(%s,uv=%v) = post:%v banner:%v want post:%v banner:%v",
				c.sev, c.uv, d.ShouldPost, d.AutoBanner, c.wantPost, c.wantBanner)
		}
	}
}

func TestMaybePost_EmitsWhenRequired(t *testing.T) {
	f := &fakeEmitter{}
	p, _ := New(matrix(t), f)
	d, err := p.MaybePost(context.Background(), ev(incidents.SEV0, true))
	if err != nil {
		t.Fatalf("MaybePost: %v", err)
	}
	if !d.ShouldPost || len(f.emitted) != 1 {
		t.Errorf("SEV0 user-visible should emit once; got post=%v emitted=%d", d.ShouldPost, len(f.emitted))
	}
}

func TestMaybePost_NoopWhenNotRequired(t *testing.T) {
	f := &fakeEmitter{}
	p, _ := New(matrix(t), f)
	d, err := p.MaybePost(context.Background(), ev(incidents.SEV3, true))
	if err != nil {
		t.Fatalf("MaybePost: %v", err)
	}
	if d.ShouldPost || len(f.emitted) != 0 {
		t.Errorf("SEV3 must be a no-op; got post=%v emitted=%d", d.ShouldPost, len(f.emitted))
	}
}

func TestMaybePost_EmitError(t *testing.T) {
	f := &fakeEmitter{err: errors.New("broker down")}
	p, _ := New(matrix(t), f)
	if _, err := p.MaybePost(context.Background(), ev(incidents.SEV0, true)); err == nil {
		t.Error("emit error must propagate")
	}
}

func TestMaybePost_InvalidEvent(t *testing.T) {
	f := &fakeEmitter{}
	p, _ := New(matrix(t), f)
	if _, err := p.MaybePost(context.Background(), incidents.IncidentDeclaredV1{}); err == nil {
		t.Error("invalid event must error")
	}
}
