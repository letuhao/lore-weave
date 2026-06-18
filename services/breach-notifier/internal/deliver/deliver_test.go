package deliver

import (
	"context"
	"testing"
	"time"
)

func TestLogNotifier_Delivers(t *testing.T) {
	ch, err := NewLogNotifier(nil).Deliver(context.Background(),
		DPONotice{IncidentID: "i", Subject: "s", Body: "b", Deadline: time.Now()})
	if err != nil {
		t.Fatalf("log deliver: %v", err)
	}
	if ch != "log" {
		t.Errorf("channel: want log, got %q", ch)
	}
}

func TestSlackNotifier_FailClosedWithoutToken(t *testing.T) {
	if _, err := NewSlackNotifier("", "#c"); err == nil {
		t.Errorf("expected fail-closed without SLACK_BOT_TOKEN")
	}
}

func TestSlackNotifier_ScaffoldErrorsNeverFalseConfirms(t *testing.T) {
	n, err := NewSlackNotifier("xoxb-test", "")
	if err != nil {
		t.Fatalf("ctor: %v", err)
	}
	ch, derr := n.Deliver(context.Background(), DPONotice{IncidentID: "i", Subject: "s", Body: "b"})
	if derr == nil {
		t.Errorf("scaffold must return a not-wired error (never false-confirm delivery)")
	}
	if ch != "" {
		t.Errorf("failed delivery must report no channel, got %q", ch)
	}
}
