import { AsOfProvider } from '../context/AsOfContext';
import { TimeSlider } from './TimeSlider';
import { CanonicalCard } from './CanonicalCard';
import { ChangeTimelinePanel } from './ChangeTimelinePanel';
import { DiffViewPanel } from './DiffViewPanel';
import { RetrievalPanel } from './RetrievalPanel';
import { EpisodeTranslationPanel } from './EpisodeTranslationPanel';

export interface TemporalTabProps {
  bookId: string;
  entityId: string;
}

/**
 * The "Temporal" tab of the entity detail panel (knowledge-temporal X6c). Composes the six
 * temporal surfaces under one AsOfProvider: the TimeSlider drives the as-of ordinal; the
 * canonical card / change timeline / diff read it. Reads go through the BFF /v1/kal/* (the
 * KAL dual-auths the user JWT + grant-checks the book). Each surface degrades independently —
 * a sparse/failed read shows an inline message, never crashes the panel.
 */
export function TemporalTab({ bookId, entityId }: TemporalTabProps) {
  if (!bookId || !entityId) return null;
  return (
    <AsOfProvider>
      <div className="space-y-5" data-testid="temporal-tab">
        <TimeSlider bookId={bookId} entityId={entityId} />
        <CanonicalCard bookId={bookId} entityId={entityId} />
        <ChangeTimelinePanel bookId={bookId} entityId={entityId} />
        <DiffViewPanel bookId={bookId} entityId={entityId} />
        <RetrievalPanel bookId={bookId} entityId={entityId} />
        <EpisodeTranslationPanel bookId={bookId} entityId={entityId} />
      </div>
    </AsOfProvider>
  );
}
