import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok-test' }),
}));

const mockConfigQuality = vi.fn();
const mockModelMatrix = vi.fn();
const mockDefaultDrift = vi.fn();
const mockOutcomeRecompute = vi.fn();

vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    knowledgeApi: {
      ...(actual.knowledgeApi as Record<string, unknown>),
      miningConfigQuality: (...args: unknown[]) => mockConfigQuality(...args),
      miningModelMatrix: (...args: unknown[]) => mockModelMatrix(...args),
      miningDefaultDrift: (...args: unknown[]) => mockDefaultDrift(...args),
      miningOutcomeRecompute: (...args: unknown[]) => mockOutcomeRecompute(...args),
    },
  };
});

const COLD_START = {
  configQuality: { items: [], exploration: [] },
  modelMatrix: { items: [] },
  defaultDrift: { items: [] },
  outcomeRecompute: { items: [], total: 0 },
};

function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

import { MiningInsightsTab } from '../MiningInsightsTab';

function Wrapped() {
  return (
    <QueryClientProvider client={makeClient()}>
      <MiningInsightsTab />
    </QueryClientProvider>
  );
}

describe('MiningInsightsTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockConfigQuality.mockResolvedValue(COLD_START.configQuality);
    mockModelMatrix.mockResolvedValue(COLD_START.modelMatrix);
    mockDefaultDrift.mockResolvedValue(COLD_START.defaultDrift);
    mockOutcomeRecompute.mockResolvedValue(COLD_START.outcomeRecompute);
  });

  it('renders all 4 section titles', async () => {
    render(<Wrapped />);
    await waitFor(() => {
      expect(screen.getByText('mining.sections.configQuality.title')).toBeInTheDocument();
      expect(screen.getByText('mining.sections.modelMatrix.title')).toBeInTheDocument();
      expect(screen.getByText('mining.sections.defaultDrift.title')).toBeInTheDocument();
      expect(screen.getByText('mining.sections.outcomeRecompute.title')).toBeInTheDocument();
    });
  });

  it('shows empty state messages at cold-start', async () => {
    render(<Wrapped />);
    await waitFor(() => {
      expect(
        screen.getByText('mining.sections.configQuality.empty'),
      ).toBeInTheDocument();
      // model-matrix section is collapsed by default (open={false})
      // but the content is still in the DOM (details element hides visually)
      expect(
        screen.getByText('mining.sections.modelMatrix.empty'),
      ).toBeInTheDocument();
      expect(
        screen.getByText('mining.sections.defaultDrift.empty'),
      ).toBeInTheDocument();
      expect(
        screen.getByText('mining.sections.outcomeRecompute.empty'),
      ).toBeInTheDocument();
    });
  });

  it('renders config-quality rows when data is present', async () => {
    mockConfigQuality.mockResolvedValue({
      items: [
        {
          genre: 'Tiên hiệp',
          config_hash: 'abcdef1234567890',
          run_count: 5,
          succeeded: 4,
          avg_entities_on_success: 22.5,
          success_rate: 0.8,
        },
      ],
      exploration: [],
    });

    render(<Wrapped />);
    await waitFor(() => {
      expect(screen.getByTestId('config-quality-table')).toBeInTheDocument();
    });
    expect(screen.getByText('Tiên hiệp')).toBeInTheDocument();
    expect(screen.getByText('abcdef12')).toBeInTheDocument();
    expect(screen.getByText('80.0%')).toBeInTheDocument();
    expect(screen.getByText('22.5')).toBeInTheDocument();
  });

  it('renders model-matrix rows when data is present', async () => {
    mockModelMatrix.mockResolvedValue({
      items: [
        {
          model_ref: 'claude-haiku-4-5',
          scope: 'all',
          has_filter: true,
          run_count: 3,
          succeeded: 3,
          weighted_outcome: 1.0,
        },
      ],
    });

    render(<Wrapped />);
    await waitFor(() => {
      expect(screen.getByTestId('model-matrix-table')).toBeInTheDocument();
    });
    expect(screen.getByText('claude-haiku-4-5')).toBeInTheDocument();
    expect(screen.getByText('100.0%')).toBeInTheDocument();
  });

  it('renders drift rows with convergent/divergent labels', async () => {
    mockDefaultDrift.mockResolvedValue({
      items: [
        {
          target: 'precision_filter.enabled',
          base_default_version: '1.0',
          affected_projects: 3,
          distinct_after_values: 1,
          drift_pattern: 'convergent',
          runs_with_outcome: 8,
        },
      ],
    });

    render(<Wrapped />);
    await waitFor(() => {
      expect(screen.getByTestId('default-drift-table')).toBeInTheDocument();
    });
    expect(screen.getByText('precision_filter.enabled')).toBeInTheDocument();
    expect(screen.getByText('mining.driftPattern.convergent')).toBeInTheDocument();
  });

  it('renders outcome-recompute rows with truncated run_id', async () => {
    mockOutcomeRecompute.mockResolvedValue({
      items: [
        {
          run_id: 'aaaabbbb-cccc-dddd-eeee-ffffffffffff',
          project_id: '00000000-0000-0000-0000-000000000001',
          pipeline_outcome: 'succeeded',
          created_at: '2026-05-01T00:00:00Z',
          post_run_corrections: 2,
          recomputed_outcome: 'minor_corrected',
        },
      ],
      total: 1,
    });

    render(<Wrapped />);
    await waitFor(() => {
      expect(screen.getByTestId('outcome-recompute-table')).toBeInTheDocument();
    });
    expect(screen.getByText('aaaabbbb')).toBeInTheDocument();
    expect(screen.getByText('minor_corrected')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('calls each API with the auth token', async () => {
    render(<Wrapped />);
    await waitFor(() => {
      expect(mockConfigQuality).toHaveBeenCalledWith('tok-test');
      expect(mockModelMatrix).toHaveBeenCalledWith('tok-test');
      expect(mockDefaultDrift).toHaveBeenCalledWith('tok-test');
      expect(mockOutcomeRecompute).toHaveBeenCalledWith('tok-test');
    });
  });
});
