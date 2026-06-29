// D-MOTIF-FE-PLANNERVIEW-WIRING (Shape A) — ChapterMotifBindings: renders one
// MotifBindingCard per committed scene from the binding map (bound vs free-form),
// wires the per-node useMotifBinding (swap → PATCH …/motif), and routes commit+generate.
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const apiJson = vi.fn();
vi.mock('@/api', () => ({ apiJson: (...a: unknown[]) => apiJson(...a), apiBase: () => '' }));

import { ChapterMotifBindings } from '../components/ChapterMotifBindings';
import type { SceneBoundMotif } from '../types';

const BOUND: SceneBoundMotif = {
  motif_id: 'm1', motif_name: 'Face-Slap Reversal', motif_source: 'authored',
  role_bindings: { protagonist: { entity_id: 'e1', entity_name: 'Lin' } },
  match_reason: { tension: 0.9, cosine: 0.7 }, beat_key: 'reversal',
};

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

const SCENES = [{ id: 'n1', title: 'Scene one' }, { id: 'n2', title: 'Scene two' }];

beforeEach(() => {
  apiJson.mockReset();
  apiJson.mockImplementation((url: string) => {
    if (url.includes('/motif-bindings')) {
      return Promise.resolve({ chapter_id: 'c1', bindings: { n1: BOUND, n2: null } });
    }
    if (url.includes('/motifs')) { // useMotifCandidates — the bind/swap picker options
      return Promise.resolve({ motifs: [{ id: 'm9', name: 'Library Motif', summary: 's' }] });
    }
    return Promise.resolve({ ok: true }); // swap/clear/bind PATCH/DELETE
  });
});

describe('ChapterMotifBindings (Shape A)', () => {
  it('renders a card per committed scene — bound vs free-form — from the map', async () => {
    render(<ChapterMotifBindings projectId="p1" bookId="b1" chapterId="c1" scenes={SCENES} token="tok" />, { wrapper: wrap() });
    // the bound scene shows its motif; the unbound scene is the free-form fallback.
    expect(await screen.findByText('Face-Slap Reversal')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('motif-binding-n1')).toHaveAttribute('data-state', 'bound'));
    expect(screen.getByTestId('motif-binding-n2')).toHaveAttribute('data-state', 'free-form');
    // both scene rows present.
    expect(screen.getByTestId('scene-binding-n1')).toBeInTheDocument();
    expect(screen.getByTestId('scene-binding-n2')).toBeInTheDocument();
  });

  it('the read hits the binding endpoint for the committed chapter', async () => {
    render(<ChapterMotifBindings projectId="p1" bookId="b1" chapterId="c1" scenes={SCENES} token="tok" />, { wrapper: wrap() });
    await screen.findByText('Face-Slap Reversal');
    const readCall = apiJson.mock.calls.find((c) => String(c[0]).includes('/motif-bindings'));
    expect(readCall?.[0]).toContain('/works/p1/outline/motif-bindings?chapter_id=c1');
  });

  it('swap on a bound scene PATCHes that node’s motif', async () => {
    render(<ChapterMotifBindings projectId="p1" bookId="b1" chapterId="c1" scenes={SCENES} token="tok" candidatesByNode={{ n1: [{ motif_id: 'm2', motif_name: 'Other' }] }} />, { wrapper: wrap() });
    await screen.findByText('Face-Slap Reversal');
    fireEvent.click(screen.getByTestId('motif-binding-swap-n1'));
    fireEvent.click(screen.getByTestId('motif-swap-option-m2'));
    await waitFor(() => {
      const patch = apiJson.mock.calls.find((c) => String(c[0]).includes('/outline/n1/motif'));
      expect(patch?.[0]).toContain('/works/p1/outline/n1/motif');
    });
  });

  it('a FREE-FORM scene can BIND a library motif → PATCHes that node (per-scene bind BE)', async () => {
    render(<ChapterMotifBindings projectId="p1" bookId="b1" chapterId="c1" scenes={SCENES} token="tok" />, { wrapper: wrap() });
    // n2 is free-form; once candidates load it offers a "Bind motif" affordance.
    const bindBtn = await screen.findByTestId('motif-binding-bind-n2');
    fireEvent.click(bindBtn);
    fireEvent.click(screen.getByTestId('motif-swap-option-m9'));
    await waitFor(() => {
      const patch = apiJson.mock.calls.find((c) => String(c[0]).includes('/outline/n2/motif'));
      expect(patch?.[0]).toContain('/works/p1/outline/n2/motif');
    });
  });

  it('a succession hint renders ChainIt on the bound scene → POSTs the chain to the next node', async () => {
    apiJson.mockImplementation((url: string) => {
      if (url.includes('/motif-bindings')) {
        return Promise.resolve({
          chapter_id: 'c1',
          bindings: { n1: BOUND, n2: null },
          succession: {
            n1: { from_motif_id: 'm1', to_motif_code: 'revenge.face_slap', to_motif_name: 'Face Slap', for_node_id: 'n2' },
            n2: null,
          },
        });
      }
      if (url.includes('/motifs')) return Promise.resolve({ motifs: [] });
      return Promise.resolve({ ok: true });
    });
    render(<ChapterMotifBindings projectId="p1" bookId="b1" chapterId="c1" scenes={SCENES} token="tok" />, { wrapper: wrap() });
    fireEvent.click(await screen.findByTestId('motif-chain-it-btn'));
    await waitFor(() => {
      const post = apiJson.mock.calls.find((c) => String(c[0]).includes('/outline/n2/motif/chain'));
      expect(post?.[0]).toContain('/works/p1/outline/n2/motif/chain');
      // the legal-successor code rides the chain POST body.
      expect(String((post?.[1] as { body?: string })?.body)).toContain('revenge.face_slap');
    });
  });

  it('commit+generate routes the scene (closes the H-8 dead-end)', async () => {
    const onGenerate = vi.fn();
    render(<ChapterMotifBindings projectId="p1" bookId="b1" chapterId="c1" scenes={SCENES} token="tok" onGenerate={onGenerate} />, { wrapper: wrap() });
    await screen.findByText('Face-Slap Reversal');
    fireEvent.click(screen.getByTestId('motif-binding-generate-n1'));
    expect(onGenerate).toHaveBeenCalledWith({ tab: 'compose', sceneId: 'n1' });
  });

  it('renders nothing without a committed chapter', () => {
    const { container } = render(<ChapterMotifBindings projectId="p1" bookId="b1" chapterId={null} scenes={SCENES} token="tok" />, { wrapper: wrap() });
    expect(container.firstChild).toBeNull();
  });
});
