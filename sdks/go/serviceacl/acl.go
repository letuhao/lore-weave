// Package serviceacl — interim S11 Layer-1 ACL for /internal/* routes.
package serviceacl

import (
	"fmt"
	"net/http"
	"os"
	"strings"

	"gopkg.in/yaml.v3"
)

type matrix struct {
	Version int `yaml:"version"`
	Rules   []struct {
		Caller string   `yaml:"caller"`
		Allow  []string `yaml:"allow"`
	} `yaml:"rules"`
}

var defaultRules map[string][]string

func init() {
	_ = LoadFromEnv()
}

// LoadFromEnv reads SERVICE_ACL_MATRIX_PATH or contracts default.
func LoadFromEnv() error {
	path := os.Getenv("SERVICE_ACL_MATRIX_PATH")
	if path == "" {
		path = "contracts/service_acl/matrix.yaml"
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	var m matrix
	if err := yaml.Unmarshal(data, &m); err != nil {
		return err
	}
	rules := make(map[string][]string, len(m.Rules))
	for _, r := range m.Rules {
		rules[r.Caller] = r.Allow
	}
	defaultRules = rules
	return nil
}

// Allowed reports whether caller may invoke method+path on an internal route.
func Allowed(caller, method, path string) bool {
	if caller == "" {
		return false
	}
	prefixes, ok := defaultRules[caller]
	if !ok {
		return false
	}
	key := method + " " + path
	for _, p := range prefixes {
		if strings.HasPrefix(key, p) || strings.HasPrefix(path, strings.TrimPrefix(p, method+" ")) {
			return true
		}
	}
	return false
}

// OptionalMiddleware applies ACL enforcement when SERVICE_ACL_ENFORCE=true.
func OptionalMiddleware(next http.Handler) http.Handler {
	if os.Getenv("SERVICE_ACL_ENFORCE") != "true" {
		return next
	}
	return Middleware(next)
}

// Middleware enforces X-Caller-Service against the ACL matrix.
func Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		caller := r.Header.Get("X-Caller-Service")
		if !Allowed(caller, r.Method, r.URL.Path) {
			http.Error(w, fmt.Sprintf(`{"error":"acl_denied","caller":%q}`, caller), http.StatusForbidden)
			return
		}
		next.ServeHTTP(w, r)
	})
}
