import { createContext, useContext, useState, type ReactNode } from 'react';

export type EnrichmentPanel = 'proposals' | 'gaps' | 'sources' | 'jobs' | 'settings';

/** Stable per-book UI state shared across the enrichment panels (book scope +
 *  which panel + which proposal is selected + the client-side project filter).
 *  Changes rarely — kept separate from the react-query data the hooks own. */
interface EnrichmentContextValue {
  bookId: string;
  activePanel: EnrichmentPanel;
  setActivePanel: (p: EnrichmentPanel) => void;
  selectedProposalId: string | null;
  setSelectedProposalId: (id: string | null) => void;
  /** Client-side filter over the book's proposals by general project_id (null = all). */
  projectFilter: string | null;
  setProjectFilter: (p: string | null) => void;
  /** Detected-gap count for the Gaps tab badge (null until the user runs Detect). */
  gapCount: number | null;
  setGapCount: (n: number | null) => void;
}

const EnrichmentCtx = createContext<EnrichmentContextValue | null>(null);

export function EnrichmentProvider({ bookId, children }: { bookId: string; children: ReactNode }) {
  const [activePanel, setActivePanel] = useState<EnrichmentPanel>('proposals');
  const [selectedProposalId, setSelectedProposalId] = useState<string | null>(null);
  const [projectFilter, setProjectFilter] = useState<string | null>(null);
  const [gapCount, setGapCount] = useState<number | null>(null);

  return (
    <EnrichmentCtx.Provider
      value={{
        bookId,
        activePanel,
        setActivePanel,
        selectedProposalId,
        setSelectedProposalId,
        projectFilter,
        setProjectFilter,
        gapCount,
        setGapCount,
      }}
    >
      {children}
    </EnrichmentCtx.Provider>
  );
}

export function useEnrichmentContext(): EnrichmentContextValue {
  const v = useContext(EnrichmentCtx);
  if (!v) throw new Error('useEnrichmentContext must be used within EnrichmentProvider');
  return v;
}
