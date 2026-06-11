import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: Record<string, unknown>) => (o ? `${k}:${JSON.stringify(o)}` : k) }),
}));

import { WikiGenJobDetail } from '../WikiGenJobDetail';
import type { WikiGenJobStatus, WikiEntityResult } from '../../types';

const base: WikiGenJobStatus = {
  job_id: 'j1', status: 'running', model_source: 'user_model', model_ref: 'm1',
  items_total: 4, items_processed: 2, items_done_count: 2, entity_count: 4,
  cost_spent_usd: '0.10', max_spend_usd: '1.00', error_message: null,
};

const RESULTS: Record<string, WikiEntityResult> = {
  e1: { outcome: 'written', citations: 3, flags: 0, name: 'Mina' },
  e2: { outcome: 'skipped', citations: 0, flags: 0, name: 'Renfield' },
  e3: { outcome: 'processing', citations: 0, flags: 0, name: 'Count' },
};

function job(over: Partial<WikiGenJobStatus>): WikiGenJobStatus {
  return { ...base, ...over };
}

describe('WikiGenJobDetail', () => {
  it('renders nothing when there is no job or no results', () => {
    const { container, rerender } = render(<WikiGenJobDetail job={null} />);
    expect(container.firstChild).toBeNull();
    rerender(<WikiGenJobDetail job={job({ results: {} })} />);
    expect(screen.queryByTestId('wiki-gen-detail')).toBeNull();
  });

  it('expands while active and lists a row per entity with its outcome', () => {
    render(<WikiGenJobDetail job={job({ results: RESULTS, current_entity_id: 'e3', current_pass: 'verify' })} />);
    // running ⇒ auto-expanded ⇒ rows visible
    expect(screen.getAllByTestId('wiki-gen-detail-row')).toHaveLength(3);
    expect(screen.getByText('Mina')).toBeTruthy();
    expect(screen.getByText('Renfield')).toBeTruthy();
  });

  it('shows the live pass label + counter on the processing entity', () => {
    render(<WikiGenJobDetail job={job({ results: RESULTS, current_entity_id: 'e3', current_pass: 'verify' })} />);
    // verify is pass 3 of 5
    expect(screen.getByTestId('wiki-gen-detail-pass').textContent).toContain('gen.pass.verify');
    expect(screen.getByTestId('wiki-gen-detail-pass').textContent).toContain('(3/5)');
  });

  it('shows the queued remainder (entity_count − rows)', () => {
    render(<WikiGenJobDetail job={job({ results: RESULTS, entity_count: 5 })} />);
    // 5 entities, 3 have results ⇒ 2 queued
    expect(screen.getByText('gen.results.queued:{"count":2}')).toBeTruthy();
  });

  it('a completed job is collapsed by default but expandable', () => {
    render(<WikiGenJobDetail job={job({ status: 'complete', results: RESULTS })} />);
    // complete ⇒ collapsed ⇒ rows hidden, header still shown
    expect(screen.getByTestId('wiki-gen-detail')).toBeTruthy();
    expect(screen.queryByTestId('wiki-gen-detail-row')).toBeNull();
    fireEvent.click(screen.getByTestId('wiki-gen-detail-toggle'));
    expect(screen.getAllByTestId('wiki-gen-detail-row').length).toBeGreaterThan(0);
  });

  it('dismiss hides the panel', () => {
    render(<WikiGenJobDetail job={job({ results: RESULTS })} />);
    expect(screen.getByTestId('wiki-gen-detail')).toBeTruthy();
    fireEvent.click(screen.getByTestId('wiki-gen-detail-dismiss'));
    expect(screen.queryByTestId('wiki-gen-detail')).toBeNull();
  });

  it('sorts the processing row first', () => {
    render(<WikiGenJobDetail job={job({ results: RESULTS, current_entity_id: 'e3', current_pass: 'context' })} />);
    const rows = screen.getAllByTestId('wiki-gen-detail-row');
    expect(rows[0].textContent).toContain('Count'); // e3 processing → top
  });
});
