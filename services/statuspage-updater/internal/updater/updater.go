package updater

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/loreweave/foundation/contracts/incidents"
	"github.com/loreweave/foundation/services/statuspage-updater/internal/config"
)

// Updater consumes incident events and drives the status page.
type Updater struct {
	client     StatusPageClient
	components *config.Components
	banner     *config.BannerConfig

	// in-memory map of incident_id → provider incident id. In production this
	// is persisted; for V1 the live consumer holds it (the unit/integration
	// tests exercise the mapping in-process).
	providerIDs map[string]string
}

// New builds an Updater. Fails closed on nil deps.
func New(client StatusPageClient, components *config.Components, banner *config.BannerConfig) (*Updater, error) {
	if client == nil {
		return nil, fmt.Errorf("updater: nil status-page client")
	}
	if components == nil {
		return nil, fmt.Errorf("updater: nil components config")
	}
	if banner == nil {
		return nil, fmt.Errorf("updater: nil banner config")
	}
	return &Updater{
		client:      client,
		components:  components,
		banner:      banner,
		providerIDs: map[string]string{},
	}, nil
}

// ShouldHandle reports whether a declared incident warrants a public post.
// Mirrors the cross-DPS comms obligation: SEV0/SEV1 user-visible (and SEV2
// user-visible per the banner policy's requires_user_visible). An internal
// (non-user-visible) incident is never posted publicly.
func (u *Updater) ShouldHandle(ev incidents.IncidentDeclaredV1) bool {
	row, ok := u.banner.PolicyFor(string(ev.Severity))
	if !ok {
		return false
	}
	if row.StatuspageImpact == string(ImpactNone) {
		return false // SEV3 → never public
	}
	if row.RequiresUserVisible && !ev.UserVisible {
		return false
	}
	return true
}

// impactFor maps severity → Statuspage.io impact via the banner policy.
func (u *Updater) impactFor(sev incidents.Severity) Impact {
	if row, ok := u.banner.PolicyFor(string(sev)); ok {
		return Impact(row.StatuspageImpact)
	}
	return ImpactNone
}

// bannerFor reports whether a banner fires for an event.
func (u *Updater) bannerFor(ev incidents.IncidentDeclaredV1) bool {
	row, ok := u.banner.PolicyFor(string(ev.Severity))
	if !ok {
		return false
	}
	return row.AutoBanner && (!row.RequiresUserVisible || ev.UserVisible)
}

// mapComponents translates incident component ids → known status-page
// component ids, dropping unknown ones (an alert may reference an internal
// subsystem with no public component).
func (u *Updater) mapComponents(in []string) []string {
	out := make([]string, 0, len(in))
	for _, id := range in {
		if _, ok := u.components.Lookup(id); ok {
			out = append(out, id)
		}
	}
	return out
}

// OnDeclared handles an IncidentDeclaredV1: creates the public incident +
// auto-banner if the comms obligation requires it. Returns whether a post was
// made. A no-op (no obligation) is not an error.
func (u *Updater) OnDeclared(ctx context.Context, ev incidents.IncidentDeclaredV1) (posted bool, err error) {
	if err := ev.Validate(); err != nil {
		return false, fmt.Errorf("updater: invalid declared event: %w", err)
	}
	if !u.ShouldHandle(ev) {
		return false, nil
	}
	body := ev.Summary
	if body == "" {
		body = "We are investigating an issue and will post an update shortly."
	}
	post := IncidentPost{
		IncidentID:   ev.IncidentID,
		Name:         ev.Title,
		Body:         body,
		Impact:       u.impactFor(ev.Severity),
		Status:       "investigating",
		ComponentIDs: u.mapComponents(ev.Components),
		Banner:       u.bannerFor(ev),
	}
	pid, err := u.client.CreateIncident(ctx, post)
	if err != nil {
		return false, fmt.Errorf("updater: create incident: %w", err)
	}
	u.providerIDs[ev.IncidentID] = pid
	return true, nil
}

// OnUpdated appends an update to a tracked incident.
func (u *Updater) OnUpdated(ctx context.Context, ev incidents.IncidentUpdatedV1) error {
	if err := ev.Validate(); err != nil {
		return fmt.Errorf("updater: invalid updated event: %w", err)
	}
	pid, ok := u.providerIDs[ev.IncidentID]
	if !ok {
		// Not tracked publicly (was internal at declare-time) — ignore.
		return nil
	}
	post := IncidentPost{
		IncidentID: ev.IncidentID,
		Body:       ev.Message,
		Impact:     u.impactFor(ev.Severity),
		Status:     ev.Status,
	}
	return u.client.UpdateIncident(ctx, pid, post)
}

// OnClosed resolves a tracked incident + clears its banner.
func (u *Updater) OnClosed(ctx context.Context, ev incidents.IncidentClosedV1) error {
	if err := ev.Validate(); err != nil {
		return fmt.Errorf("updater: invalid closed event: %w", err)
	}
	pid, ok := u.providerIDs[ev.IncidentID]
	if !ok {
		return nil
	}
	dur := ev.ResolvedAt.Sub(ev.DeclaredAt)
	body := fmt.Sprintf("Resolved. Total impact: %s.", durString(dur))
	if ev.ResolutionNote != "" {
		body = ev.ResolutionNote
	}
	if err := u.client.ResolveIncident(ctx, pid, body); err != nil {
		return fmt.Errorf("updater: resolve incident: %w", err)
	}
	delete(u.providerIDs, ev.IncidentID)
	return nil
}

// TrackedCount returns the number of currently-tracked public incidents
// (test helper + readiness signal).
func (u *Updater) TrackedCount() int { return len(u.providerIDs) }

func durString(d time.Duration) string {
	if d <= 0 {
		return "0s"
	}
	return strings.TrimSuffix(d.String(), "0s")
}
