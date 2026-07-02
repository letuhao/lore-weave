import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

// W6 — the runtime inspector's advertised-set sizes + phase trail rows.

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (k: string, opts?: Record<string, unknown>) => {
      if (!opts) return k;
      const vals = Object.entries(opts)
        .filter(([key]) => key !== 'defaultValue')
        .map(([, v]) => String(v));
      return vals.length ? `${k} ${vals.join(' ')}` : k;
    },
  }),
}));

import { AgentRuntimeInspector } from '../AgentRuntimeInspector';
import type { AgentSurfaceState } from '../../types';

const state: AgentSurfaceState = {
  phase: 'Discovering',
  pinned_count: 1,
  hot_seed_count: 3,
  activated_count: 2,
  injected_skills: ['glossary'],
  running_tool: null,
  last_find_tools_query: 'translate a book',
  find_tools_call_count: 1,
  advertised: {
    core: ['find_tools', 'ui_navigate', 'confirm_action'],
    frontend: ['propose_edit'],
    activated: ['glossary_search', 'memory_search'],
  },
  servers: { knowledge: { tools: 1 }, glossary: { tools: 1 }, ui: { tools: 2 }, chat: { tools: 1 } },
  schema_tokens: { frontend: 100, mcp: 200 },
};

describe('AgentRuntimeInspector (W6)', () => {
  it('shows the translated live phase in the header row', () => {
    render(
      <AgentRuntimeInspector state={state} expanded={false} onToggle={() => {}} isStreaming />,
    );
    expect(screen.getByTestId('agent-inspector-phase').textContent).toBe(
      'inspector.phase.discovering',
    );
  });

  it('expanded: renders the advertised-set sizes from the new payload', () => {
    render(
      <AgentRuntimeInspector state={state} expanded onToggle={() => {}} isStreaming={false} />,
    );
    const row = screen.getByTestId('agent-inspector-advertised');
    // mocked t: "inspector.advertised_sizes {core} {frontend} {activated}"
    expect(row.textContent).toContain('inspector.advertised_sizes 3 1 2');
  });

  it('expanded: renders the phase trail when it has transitions', () => {
    render(
      <AgentRuntimeInspector
        state={state}
        expanded
        onToggle={() => {}}
        isStreaming={false}
        trail={['Curated', 'SkillInjected', 'Discovering']}
      />,
    );
    expect(screen.getByTestId('agent-inspector-trail').textContent).toContain(
      'inspector.phase.curated → inspector.phase.skills → inspector.phase.discovering',
    );
  });

  it('no advertised payload (older backend) → the row is absent', () => {
    const legacy: AgentSurfaceState = { ...state, advertised: undefined, servers: undefined };
    render(
      <AgentRuntimeInspector state={legacy} expanded onToggle={() => {}} isStreaming={false} />,
    );
    expect(screen.queryByTestId('agent-inspector-advertised')).toBeNull();
    expect(screen.queryByTestId('agent-inspector-trail')).toBeNull();
  });
});
