package breach

import (
	"context"
	"time"

	"github.com/loreweave/foundation/contracts/incidents"
)

// emitNotifier implements gdpr_breach_flow.DPONotifier by EMITTING the DPO
// notice OBLIGATION event (GDPRDPONoticeRequiredV1) — it does NOT deliver the
// notice (Q-L7-1: a downstream consumer fulfills the obligation; tracked
// D-BREACH-DELIVERY-CONSUMER). It is bound to one breach's incident_id +
// deadline (both known before Flow.Open) so the emitted event is complete.
//
// Honest-failure contract: if the emit fails, NotifyDPO returns the error.
// gdpr_breach_flow.Open then does NOT set BreachRecord.DPONotifiedAt — so a
// failed obligation-emit is never mistaken for a queued notice.
type emitNotifier struct {
	emitter    EventEmitter
	incidentID string
	deadline   time.Time
}

// NotifyDPO emits the obligation event. subject+body are composed by the Flow.
func (n *emitNotifier) NotifyDPO(ctx context.Context, subject, body string) error {
	ev := incidents.NewGDPRDPONoticeRequiredV1(n.incidentID, subject, body, n.deadline)
	return n.emitter.EmitDPONoticeRequired(ctx, ev)
}
