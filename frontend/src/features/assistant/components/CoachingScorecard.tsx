// C8 / SD-C8 (WS-5.21/5.22) — the coaching scorecard view. Renders the N server-authoritative
// dimensions + a QUARANTINE badge. SD-7: a quarantine score is SHOWN but the badge makes clear it is
// NOT trended; the trend line (scorecardTrend.ts) excludes it. Pure view — data comes from props.
import type { Scorecard } from '../types';

export function CoachingScorecard({ card }: { card: Scorecard }) {
  return (
    <div data-testid="coaching-scorecard" className="rounded-lg border border-border bg-card p-4">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold">Coaching scorecard</h3>
        {card.quarantine && (
          // WS-5.22 / SD-7 — the quarantine badge: shown, never trended (an uncertified score).
          <span
            data-testid="quarantine-badge"
            title="This score is not yet calibrated against human ratings, so it is shown for reference but not plotted on a trend."
            className="rounded-full border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-600 dark:text-amber-400"
          >
            Not trended (in review)
          </span>
        )}
      </div>

      {typeof card.overall_score === 'number' && (
        <p data-testid="scorecard-overall" className="mb-3 text-sm text-muted-foreground">
          Overall: <span className="font-medium text-foreground">{card.overall_score}/100</span>
        </p>
      )}

      <ul className="space-y-2">
        {card.dimensions.map((d) => (
          <li key={d.key} data-testid="scorecard-dimension" className="flex items-start gap-3">
            <span className="min-w-32 text-sm font-medium">{d.label}</span>
            <span className="text-sm text-muted-foreground">
              {d.score === null ? (
                <span data-testid="dimension-unscored" className="italic">not scored</span>
              ) : (
                <span data-testid="dimension-score" className="font-medium text-foreground">{d.score}/5</span>
              )}
              {d.note ? <span className="ml-2">— {d.note}</span> : null}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
