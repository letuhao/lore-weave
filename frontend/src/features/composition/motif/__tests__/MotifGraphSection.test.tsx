// 3a-C — the motif graph section: reads edges, renders neighbors grouped by kind, and
// surfaces the DB guard's 409 INLINE on the add form (not a swallowed toast).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MotifGraphSection } from '../components/MotifGraphSection';
import { motifApi } from '../api';

vi.mock('../api', () => ({
  motifApi: {
    links: vi.fn(),
    createLink: vi.fn(),
    deleteLink: vi.fn(),
    list: vi.fn(),
  },
}));

const MID = 'motif-1';
function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  (motifApi.list as ReturnType<typeof vi.fn>).mockResolvedValue({ motifs: [
    { id: 'n2', code: 'rev.slap', name: 'Face-slap', kind: 'scheme', genre_tags: [] },
  ] });
});

describe('MotifGraphSection', () => {
  it('renders edges grouped by kind after expanding', async () => {
    (motifApi.links as ReturnType<typeof vi.fn>).mockResolvedValue({ motif_id: MID, count: 1, links: [
      { id: 'e1', kind: 'precedes', ord: null, direction: 'out', neighbor_id: 'n2', neighbor_code: 'rev.slap', neighbor_name: 'Face-slap' },
    ] });
    wrap(<MotifGraphSection motifId={MID} token="t" />);
    fireEvent.click(screen.getByTestId('motif-graph-toggle'));
    await waitFor(() => expect(screen.getByTestId('motif-graph-edge')).toBeInTheDocument());
    expect(screen.getByText('Face-slap')).toBeInTheDocument();     // neighbor name (not i18n)
    expect(screen.getByText('rev.slap')).toBeInTheDocument();      // neighbor code
    // the kind group header uses i18n (test env returns the key) — assert the key is present
    expect(screen.getByText('motif.graph.kind.precedes')).toBeInTheDocument();
  });

  it('shows the empty state when there are no edges', async () => {
    (motifApi.links as ReturnType<typeof vi.fn>).mockResolvedValue({ motif_id: MID, count: 0, links: [] });
    wrap(<MotifGraphSection motifId={MID} token="t" />);
    fireEvent.click(screen.getByTestId('motif-graph-toggle'));
    await waitFor(() => expect(screen.getByTestId('motif-graph-empty')).toBeInTheDocument());
  });

  it('surfaces the guard 409 message INLINE on the add form (not swallowed)', async () => {
    (motifApi.links as ReturnType<typeof vi.fn>).mockResolvedValue({ motif_id: MID, count: 0, links: [] });
    (motifApi.createLink as ReturnType<typeof vi.fn>).mockRejectedValue(
      Object.assign(new Error('a motif cannot precede itself, and a cycle would make the succession chain unresolvable'), { status: 409 }),
    );
    wrap(<MotifGraphSection motifId={MID} token="t" />);
    fireEvent.click(screen.getByTestId('motif-graph-toggle'));
    fireEvent.click(await screen.findByTestId('motif-graph-add-toggle'));
    // the neighbor options load async (candidatesQ) — wait for one before selecting it
    await screen.findByRole('option', { name: /Face-slap/ });
    fireEvent.change(screen.getByTestId('motif-graph-neighbor'), { target: { value: 'n2' } });
    fireEvent.click(screen.getByTestId('motif-graph-add-submit'));
    const err = await screen.findByTestId('motif-graph-add-error');
    expect(err.textContent).toMatch(/cannot precede itself/i);
  });

  it('hides write affordances when readOnly (system/foreign motif)', async () => {
    (motifApi.links as ReturnType<typeof vi.fn>).mockResolvedValue({ motif_id: MID, count: 1, links: [
      { id: 'e1', kind: 'variant_of', ord: null, direction: 'out', neighbor_id: 'n2', neighbor_code: 'x', neighbor_name: 'X' },
    ] });
    wrap(<MotifGraphSection motifId={MID} token="t" readOnly />);
    fireEvent.click(screen.getByTestId('motif-graph-toggle'));
    await screen.findByTestId('motif-graph-edge');
    expect(screen.queryByTestId('motif-graph-add-toggle')).not.toBeInTheDocument();
    expect(screen.queryByTestId('motif-graph-edge-delete')).not.toBeInTheDocument();
  });

  it('deletes an edge', async () => {
    (motifApi.links as ReturnType<typeof vi.fn>).mockResolvedValue({ motif_id: MID, count: 1, links: [
      { id: 'e1', kind: 'composed_of', ord: null, direction: 'out', neighbor_id: 'n2', neighbor_code: 'x', neighbor_name: 'X' },
    ] });
    (motifApi.deleteLink as ReturnType<typeof vi.fn>).mockResolvedValue({ deleted: true, link_id: 'e1' });
    wrap(<MotifGraphSection motifId={MID} token="t" />);
    fireEvent.click(screen.getByTestId('motif-graph-toggle'));
    fireEvent.click(await screen.findByTestId('motif-graph-edge-delete'));
    await waitFor(() => expect(motifApi.deleteLink).toHaveBeenCalledWith('e1', 't', null));
  });
});
