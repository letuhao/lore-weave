import { EnrichmentProvider } from '@/features/enrichment/context/EnrichmentContext';
import { EnrichmentView } from '@/features/enrichment/components/EnrichmentView';

/** Book-workspace tab entry for enrichment review — mirrors GlossaryTab/WikiTab.
 *  A thin wrapper that scopes the feature to this book and mounts the shell. */
export function EnrichmentTab({ bookId }: { bookId: string }) {
  return (
    <EnrichmentProvider bookId={bookId}>
      <EnrichmentView />
    </EnrichmentProvider>
  );
}
