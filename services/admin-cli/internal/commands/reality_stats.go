package commands

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/google/uuid"
)

// ErrRealityNotFound is returned when no reality_registry row matches.
var ErrRealityNotFound = errors.New("reality stats: reality not found")

// RealityStats is the read-only summary the `reality stats` command reports.
type RealityStats struct {
	RealityID          uuid.UUID
	Status             string
	StatusTransitionAt time.Time
	Locale             string
	DeployCohort       int
	SessionMaxPCs      int
	SessionMaxNPCs     int
	SessionMaxTotal    int
	LastStatsUpdatedAt *time.Time
	CloseInitiatedAt   *time.Time
	CloseReason        string
	ArchiveVerifiedAt  *time.Time
	DropScheduledAt    *time.Time
}

// RealityStatsReader reads a reality's summary row (read-only). The prod impl is
// PgRealityStatsReader; tests use a fake.
type RealityStatsReader interface {
	ReadRealityStats(ctx context.Context, realityID uuid.UUID) (*RealityStats, error)
}

// RunRealityStats reads + formats a reality's stats (tier-3 informational,
// read-only — no mutation). Returns ErrRealityNotFound (unwrapped) when absent.
func RunRealityStats(ctx context.Context, realityID uuid.UUID, reader RealityStatsReader) (string, error) {
	if reader == nil {
		return "", fmt.Errorf("reality stats: reader not wired")
	}
	s, err := reader.ReadRealityStats(ctx, realityID)
	if err != nil {
		return "", err
	}
	var b strings.Builder
	fmt.Fprintf(&b, "reality %s — stats (read-only)\n", s.RealityID)
	fmt.Fprintf(&b, "  status:        %s (since %s)\n", s.Status, s.StatusTransitionAt.UTC().Format(time.RFC3339))
	fmt.Fprintf(&b, "  locale:        %s\n", s.Locale)
	fmt.Fprintf(&b, "  deploy_cohort: %d\n", s.DeployCohort)
	fmt.Fprintf(&b, "  session caps:  pcs=%d npcs=%d total=%d\n", s.SessionMaxPCs, s.SessionMaxNPCs, s.SessionMaxTotal)
	if s.LastStatsUpdatedAt != nil {
		fmt.Fprintf(&b, "  last_stats:    %s\n", s.LastStatsUpdatedAt.UTC().Format(time.RFC3339))
	}
	// Lifecycle markers — only shown when set (a healthy live reality has none).
	if s.CloseInitiatedAt != nil {
		fmt.Fprintf(&b, "  close:         initiated %s (%s)\n", s.CloseInitiatedAt.UTC().Format(time.RFC3339), s.CloseReason)
	}
	if s.ArchiveVerifiedAt != nil {
		fmt.Fprintf(&b, "  archive:       verified %s\n", s.ArchiveVerifiedAt.UTC().Format(time.RFC3339))
	}
	if s.DropScheduledAt != nil {
		fmt.Fprintf(&b, "  drop:          scheduled %s\n", s.DropScheduledAt.UTC().Format(time.RFC3339))
	}
	return b.String(), nil
}
