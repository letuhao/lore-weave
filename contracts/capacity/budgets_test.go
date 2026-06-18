package capacity

import (
	"errors"
	"path/filepath"
	"runtime"
	"testing"
)

// TestLoadAndValidate_RealBudgetsYAML pins that the shipped budgets.yaml
// (cycle 7) parses + validates.
func TestLoadAndValidate_RealBudgetsYAML(t *testing.T) {
	_, thisFile, _, _ := runtime.Caller(0)
	path := filepath.Join(filepath.Dir(thisFile), "budgets.yaml")
	b, err := LoadAndValidate(path, ModeLax)
	if err != nil {
		t.Fatalf("LoadAndValidate(%s, lax): %v", path, err)
	}
	if b.Version != 1 {
		t.Errorf("Version = %d, want 1", b.Version)
	}
	// Spot-check critical services exist.
	must := []string{"auth-service", "world-service", "publisher", "api-gateway-bff", "translation-service"}
	for _, n := range must {
		if _, ok := b.Find(n); !ok {
			t.Errorf("budgets missing service %q", n)
		}
	}
	if len(b.Services) < 20 {
		t.Errorf("expected at least 20 services in shipped budgets; got %d", len(b.Services))
	}
}

func TestParseAndValidate_RejectsUnsupportedVersion(t *testing.T) {
	bad := []byte("version: 99\nservices: []\n")
	_, err := ParseAndValidate(bad, ModeStrict)
	if !errors.Is(err, ErrUnsupportedVersion) {
		t.Errorf("err = %v, want ErrUnsupportedVersion", err)
	}
}

func TestParseAndValidate_RejectsDuplicateService(t *testing.T) {
	bad := []byte(`
version: 1
services:
  - name: a
    class: web
    v1: {min_replicas: 1, max_replicas: 2, cpu_per_replica: 0.5, memory_per_replica: 512Mi, scale_trigger: "rps>10"}
    v3: {min_replicas: 1, max_replicas: 2}
  - name: a
    class: web
    v1: {min_replicas: 1, max_replicas: 2, cpu_per_replica: 0.5, memory_per_replica: 512Mi, scale_trigger: "rps>10"}
    v3: {min_replicas: 1, max_replicas: 2}
`)
	_, err := ParseAndValidate(bad, ModeStrict)
	if !errors.Is(err, ErrDuplicateService) {
		t.Errorf("err = %v, want ErrDuplicateService", err)
	}
}

func TestParseAndValidate_StrictRejectsUnknownKey(t *testing.T) {
	bad := []byte(`
version: 1
services:
  - name: a
    class: web
    yolo: oops
    v1: {min_replicas: 1, max_replicas: 2, cpu_per_replica: 0.5, memory_per_replica: 512Mi, scale_trigger: "rps>10"}
    v3: {min_replicas: 1, max_replicas: 2}
`)
	_, err := ParseAndValidate(bad, ModeStrict)
	if !errors.Is(err, ErrUnknownYAMLKey) {
		t.Errorf("err = %v, want ErrUnknownYAMLKey", err)
	}
	if _, err := ParseAndValidate(bad, ModeLax); err != nil {
		t.Errorf("lax err = %v, want nil", err)
	}
}

func TestService_Validate_RejectsBadFields(t *testing.T) {
	cpu := 0.5
	base := Service{
		Name:  "svc-a",
		Class: ClassWeb,
		V1:    Tier{MinReplicas: 1, MaxReplicas: 2, CPUPerReplica: &cpu, MemoryPerReplica: "512Mi", ScaleTrigger: "rps>10"},
		V3:    Tier{MinReplicas: 1, MaxReplicas: 4},
	}
	zero := 0.0
	cases := []struct {
		name   string
		mutate func(*Service)
	}{
		{"empty name", func(s *Service) { s.Name = "" }},
		{"uppercase name", func(s *Service) { s.Name = "SvcA" }},
		{"bad class", func(s *Service) { s.Class = "weird" }},
		{"v1 max < min", func(s *Service) { s.V1.MaxReplicas = 0 }},
		{"v1 min negative", func(s *Service) { s.V1.MinReplicas = -1 }},
		{"v1 cpu zero", func(s *Service) { s.V1.CPUPerReplica = &zero }},
		{"v1 cpu nil", func(s *Service) { s.V1.CPUPerReplica = nil }},
		{"v1 bad memory", func(s *Service) { s.V1.MemoryPerReplica = "lots" }},
		{"v1 empty scale_trigger", func(s *Service) { s.V1.ScaleTrigger = "" }},
		{"v3 max 0", func(s *Service) { s.V3.MaxReplicas = 0 }},
		{"v3 max < min", func(s *Service) { s.V3.MinReplicas = 5; s.V3.MaxReplicas = 2 }},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			s := base
			c.mutate(&s)
			if err := s.Validate(); !errors.Is(err, ErrInvalidService) {
				t.Errorf("err = %v, want ErrInvalidService", err)
			}
		})
	}
}

func TestService_Validate_LibrarySkipsTiers(t *testing.T) {
	s := Service{Name: "lib", Class: ClassLibrary}
	if err := s.Validate(); err != nil {
		t.Errorf("library Validate() = %v, want nil", err)
	}
}

func TestAdmission_RegisterService_AcceptsKnown(t *testing.T) {
	cpu := 0.5
	b := Budgets{Version: 1, Services: []Service{{
		Name: "ok-svc", Class: ClassWeb,
		V1: Tier{MinReplicas: 1, MaxReplicas: 4, CPUPerReplica: &cpu, MemoryPerReplica: "512Mi", ScaleTrigger: "rps>10"},
		V3: Tier{MinReplicas: 2, MaxReplicas: 8},
	}}}
	a := NewAdmission(b)
	got, err := a.RegisterService("ok-svc")
	if err != nil {
		t.Fatalf("err = %v, want nil", err)
	}
	if got.Name != "ok-svc" {
		t.Errorf("got %q, want ok-svc", got.Name)
	}
	if !a.IsRegistered("ok-svc") {
		t.Errorf("IsRegistered = false, want true")
	}
}

func TestAdmission_RegisterService_RejectsUnknown(t *testing.T) {
	b := Budgets{Version: 1, Services: []Service{}}
	a := NewAdmission(b)
	_, err := a.RegisterService("missing")
	if !errors.Is(err, ErrUnregisteredService) {
		t.Errorf("err = %v, want ErrUnregisteredService", err)
	}
	c, r := a.Stats()
	if c != 1 || r != 1 {
		t.Errorf("stats = (%d,%d), want (1,1)", c, r)
	}
}

func TestAdmission_RemainingBudget(t *testing.T) {
	cpu := 0.5
	b := Budgets{Version: 1, Services: []Service{{
		Name: "svc", Class: ClassWeb,
		V1: Tier{MinReplicas: 1, MaxReplicas: 4, CPUPerReplica: &cpu, MemoryPerReplica: "512Mi", ScaleTrigger: "rps>10"},
		V3: Tier{MinReplicas: 2, MaxReplicas: 12},
	}}}
	a := NewAdmission(b)
	if h, err := a.RemainingBudget("svc", "v1", 2); err != nil || h != 2 {
		t.Errorf("v1@2 → (%d, %v), want (2, nil)", h, err)
	}
	if h, err := a.RemainingBudget("svc", "v3", 10); err != nil || h != 2 {
		t.Errorf("v3@10 → (%d, %v), want (2, nil)", h, err)
	}
	if h, err := a.RemainingBudget("svc", "v1", 99); err != nil || h != 0 {
		t.Errorf("over-capacity → (%d, %v), want (0, nil)", h, err)
	}
	if _, err := a.RemainingBudget("missing", "v1", 0); !errors.Is(err, ErrUnregisteredService) {
		t.Errorf("err = %v, want ErrUnregisteredService", err)
	}
	if _, err := a.RemainingBudget("svc", "v99", 0); !errors.Is(err, ErrInvalidService) {
		t.Errorf("bad tier err = %v, want ErrInvalidService", err)
	}
}
