package deploy

import (
	"context"
	"errors"
	"testing"
	"time"
)

type recordingWriter struct {
	got OverrideRecord
	err error
}

func (w *recordingWriter) WriteFreezeOverride(_ context.Context, rec OverrideRecord) error {
	w.got = rec
	return w.err
}

func fixedClock(t time.Time) ClockFn { return func() time.Time { return t } }

func validReq() BreakGlassRequest {
	return BreakGlassRequest{
		DeployID:         "d-2026-0530-001",
		PRLabels:         []string{"emergency", "break-glass-deploy"},
		FreezeType:       FreezeSLOBurn,
		TechLeadApprover: "tl-1",
		IncidentID:       "INC-2026-0530-0007",
		Actor:            "dev-1",
		Reason:           "auth-service 5xx spike; security hotfix must ship despite burn freeze",
	}
}

func TestBreakGlass_Apply_HappyPath(t *testing.T) {
	w := &recordingWriter{}
	now := time.Date(2026, 5, 30, 14, 0, 0, 0, time.UTC)
	rec, err := Apply(context.Background(), validReq(), w, fixedClock(now))
	if err != nil {
		t.Fatalf("Apply err = %v", err)
	}
	if rec.PostReviewDueNanos != now.Add(24*time.Hour).UnixNano() {
		t.Errorf("post-review due mismatch: %d", rec.PostReviewDueNanos)
	}
	if rec.IncidentRef != "INC-2026-0530-0007" {
		t.Errorf("incident ref = %q", rec.IncidentRef)
	}
	if w.got.DeployID != "d-2026-0530-001" {
		t.Errorf("writer saw wrong deploy: %+v", w.got)
	}
}

func TestBreakGlass_Apply_FallsBackToSecurityFindingRef(t *testing.T) {
	req := validReq()
	req.IncidentID = ""
	req.SecurityFindingID = "SEC-2026-0001"
	w := &recordingWriter{}
	rec, err := Apply(context.Background(), req, w, time.Now)
	if err != nil {
		t.Fatalf("Apply err = %v", err)
	}
	if rec.IncidentRef != "SEC-2026-0001" {
		t.Errorf("ref = %q want SEC-2026-0001", rec.IncidentRef)
	}
}

func TestBreakGlass_RejectsMissingLabel(t *testing.T) {
	req := validReq()
	req.PRLabels = []string{"emergency"} // missing break-glass-deploy
	_, err := Apply(context.Background(), req, &recordingWriter{}, time.Now)
	if !errors.Is(err, ErrBreakGlass) {
		t.Errorf("err = %v want ErrBreakGlass", err)
	}
}

func TestBreakGlass_RejectsInvalidFreezeType(t *testing.T) {
	req := validReq()
	req.FreezeType = "bogus"
	_, err := Apply(context.Background(), req, &recordingWriter{}, time.Now)
	if !errors.Is(err, ErrBreakGlass) {
		t.Errorf("err = %v want ErrBreakGlass", err)
	}
}

func TestBreakGlass_RejectsMissingTechLead(t *testing.T) {
	req := validReq()
	req.TechLeadApprover = ""
	_, err := Apply(context.Background(), req, &recordingWriter{}, time.Now)
	if !errors.Is(err, ErrBreakGlass) {
		t.Errorf("err = %v want ErrBreakGlass", err)
	}
}

func TestBreakGlass_RejectsSelfApproval(t *testing.T) {
	req := validReq()
	req.TechLeadApprover = "dev-1" // same as Actor
	_, err := Apply(context.Background(), req, &recordingWriter{}, time.Now)
	if !errors.Is(err, ErrBreakGlass) {
		t.Errorf("err = %v want ErrBreakGlass (no self-approval)", err)
	}
}

func TestBreakGlass_RejectsNoIncidentOrSecurityRef(t *testing.T) {
	req := validReq()
	req.IncidentID = ""
	req.SecurityFindingID = ""
	_, err := Apply(context.Background(), req, &recordingWriter{}, time.Now)
	if !errors.Is(err, ErrBreakGlass) {
		t.Errorf("err = %v want ErrBreakGlass", err)
	}
}

func TestBreakGlass_RejectsEmptyReason(t *testing.T) {
	req := validReq()
	req.Reason = ""
	_, err := Apply(context.Background(), req, &recordingWriter{}, time.Now)
	if !errors.Is(err, ErrBreakGlass) {
		t.Errorf("err = %v want ErrBreakGlass", err)
	}
}

func TestBreakGlass_AllFourFreezeTypesValid(t *testing.T) {
	for _, ft := range []FreezeType{FreezeSLOBurn, FreezeScheduled, FreezeIncident, FreezeSecurity} {
		if !ValidFreezeType(ft) {
			t.Errorf("%q should be valid", ft)
		}
		req := validReq()
		req.FreezeType = ft
		if err := req.Validate(); err != nil {
			t.Errorf("freeze type %q: Validate err = %v", ft, err)
		}
	}
}

func TestBreakGlass_WriterErrorPropagates(t *testing.T) {
	w := &recordingWriter{err: errors.New("meta write timeout")}
	_, err := Apply(context.Background(), validReq(), w, time.Now)
	if err == nil || !contains(err.Error(), "meta write timeout") {
		t.Errorf("err should wrap writer error: %v", err)
	}
}

func TestBreakGlass_LabelMatchCaseInsensitive(t *testing.T) {
	req := validReq()
	req.PRLabels = []string{"Break-Glass-Deploy"}
	if err := req.Validate(); err != nil {
		t.Errorf("case-insensitive label match should pass: %v", err)
	}
}

func contains(s, sub string) bool {
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return true
		}
	}
	return false
}
