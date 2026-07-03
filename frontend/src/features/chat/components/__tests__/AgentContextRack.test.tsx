import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

// W6 — the rack's per-server grouping, status dots, and the summary chip.

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
// The add modal fetches the catalog on open — keep it inert for these tests.
vi.mock('../ToolSkillAddModal', () => ({
  ToolSkillAddModal: () => null,
}));

import { AgentContextRack, summarizeRack } from '../AgentContextRack';
import type { AgentSurfaceState } from '../../types';

const baseSurface: AgentSurfaceState = {
  phase: 'Curated',
  pinned_count: 2,
  hot_seed_count: 0,
  activated_count: 2,
  injected_skills: ['universal'],
  running_tool: null,
  last_find_tools_query: null,
  find_tools_call_count: 0,
  advertised: {
    core: ['find_tools', 'ui_navigate'],
    frontend: ['propose_edit'],
    activated: ['memory_search', 'glossary_search'],
  },
  servers: {
    knowledge: { tools: 1 },
    glossary: { tools: 1 },
    ui: { tools: 2 },
    chat: { tools: 1 },
  },
  schema_tokens: { frontend: 120, mcp: 380 },
};

// A turn-OPENING frame (Curated) — the tracker defaults: all-empty advertised,
// empty servers, zero-zero schema_tokens. NOT-measured, never "0 tools · 0 tok".
const curatedEmptySurface: AgentSurfaceState = {
  phase: 'Curated',
  pinned_count: 2,
  hot_seed_count: 0,
  activated_count: 0,
  injected_skills: [],
  running_tool: null,
  last_find_tools_query: null,
  find_tools_call_count: 0,
  advertised: { core: [], frontend: [], activated: [] },
  servers: {},
  schema_tokens: { frontend: 0, mcp: 0 },
};

const noop = () => {};
const rackProps = {
  enabledSkills: [],
  token: null,
  onAddTool: noop,
  onAddSkill: noop,
  onRemoveTool: noop,
  onRemoveSkill: noop,
  onClearDiscovered: noop,
};

describe('summarizeRack', () => {
  it('prefers the advertised surface and sums the schema-token split', () => {
    const s = summarizeRack(baseSurface, ['glossary_search'], ['memory_search'], []);
    expect(s.tools).toBe(5); // 2 core + 1 frontend + 2 activated
    expect(s.skills).toBe(1); // injected_skills from the frame
    expect(s.tokens).toBe(500); // 120 frontend + 380 mcp
  });

  it('degrades to pins + discovered (deduped) without a frame', () => {
    const s = summarizeRack(null, ['glossary_search', 'book_create'], ['glossary_search'], ['universal']);
    expect(s.tools).toBe(2);
    expect(s.skills).toBe(1);
    expect(s.tokens).toBeNull();
  });

  it('treats a turn-opening frame (all-empty advertised, 0/0 schema_tokens) as NOT-measured', () => {
    const s = summarizeRack(curatedEmptySurface, ['glossary_search', 'book_create'], ['memory_search'], []);
    expect(s.tools).toBe(3); // pins + discovered fallback — never 0
    expect(s.tokens).toBeNull(); // never "0 tok"
  });

  it('0 injected skills is a real measurement — it must NOT fall back to the pins', () => {
    const s = summarizeRack({ ...baseSurface, injected_skills: [] }, [], [], ['universal', 'other']);
    expect(s.skills).toBe(0);
  });
});

describe('AgentContextRack grouping', () => {
  it('groups pinned + discovered chips by server with counts', () => {
    render(
      <AgentContextRack
        {...rackProps}
        enabledTools={['glossary_search', 'book_create']}
        activatedTools={['memory_search', 'kg_query_paths']}
        surface={baseSurface}
      />,
    );
    // knowledge group carries both discovered knowledge tools.
    const knowledge = screen.getByTestId('agent-rack-server-knowledge');
    expect(knowledge.textContent).toContain('rack.server.knowledge');
    expect(knowledge.textContent).toContain('· 2');
    expect(screen.getByTestId('agent-rack-server-glossary')).toBeInTheDocument();
    expect(screen.getByTestId('agent-rack-server-book')).toBeInTheDocument();
    // every chip renders inside its group.
    expect(screen.getByTestId('agent-rack-chip-tool-glossary_search')).toBeInTheDocument();
    expect(screen.getByTestId('agent-rack-chip-tool-memory_search')).toBeInTheDocument();
    expect(screen.getByTestId('agent-rack-chip-tool-kg_query_paths')).toBeInTheDocument();
  });

  it('status dot is live for servers in the frame, muted for pins-only', () => {
    render(
      <AgentContextRack
        {...rackProps}
        enabledTools={['glossary_search', 'translation_start_job']}
        activatedTools={[]}
        surface={baseSurface} // servers has glossary but NOT translation
      />,
    );
    expect(screen.getByTestId('agent-rack-server-dot-glossary').dataset.live).toBe('1');
    expect(screen.getByTestId('agent-rack-server-dot-translation').dataset.live).toBe('0');
  });

  it('pinned chips keep the remove button; discovered chips are read-only', () => {
    const onRemoveTool = vi.fn();
    render(
      <AgentContextRack
        {...rackProps}
        onRemoveTool={onRemoveTool}
        enabledTools={['glossary_search']}
        activatedTools={['memory_search']}
        surface={null}
      />,
    );
    const pinned = screen.getByTestId('agent-rack-chip-tool-glossary_search');
    fireEvent.click(pinned.querySelector('button')!);
    expect(onRemoveTool).toHaveBeenCalledWith('glossary_search');
    const discovered = screen.getByTestId('agent-rack-chip-tool-memory_search');
    expect(discovered.querySelector('button')).toBeNull();
  });
});

describe('AgentContextRack summary chip', () => {
  it('renders "N tools · M skills · X tok" from the frame and opens the breakdown', () => {
    const onOpenBreakdown = vi.fn();
    render(
      <AgentContextRack
        {...rackProps}
        enabledTools={[]}
        activatedTools={[]}
        surface={baseSurface}
        onOpenBreakdown={onOpenBreakdown}
      />,
    );
    const chip = screen.getByTestId('agent-rack-summary');
    // mocked t: "rack.summary {tools} {skills} {tokens}"
    expect(chip.textContent).toContain('rack.summary');
    expect(chip.textContent).toContain('5');
    expect(chip.textContent).toContain('1');
    expect(chip.textContent).toContain('500');
    fireEvent.click(chip);
    expect(onOpenBreakdown).toHaveBeenCalledTimes(1);
  });

  it('frame sequence Curated(empty) → advertised pass: fallback first, then real numbers', () => {
    const props = {
      ...rackProps,
      enabledTools: ['glossary_search', 'book_create'],
      activatedTools: [],
    };
    const { rerender } = render(<AgentContextRack {...props} surface={curatedEmptySurface} />);
    const chip = screen.getByTestId('agent-rack-summary');
    // turn-opening frame → pins fallback + no token count (no "0 tools · 0 tok" flash)
    expect(chip.textContent).toContain('rack.summary_no_tokens');
    expect(chip.textContent).toContain('2');
    rerender(<AgentContextRack {...props} surface={baseSurface} />);
    // the advertised pass → real measured numbers
    expect(chip.textContent).toContain('rack.summary');
    expect(chip.textContent).toContain('5');
    expect(chip.textContent).toContain('500');
  });

  it('a later unmeasured frame keeps the PREVIOUS measured tokens and live dots', () => {
    const props = { ...rackProps, enabledTools: ['glossary_search'], activatedTools: [] };
    const { rerender } = render(<AgentContextRack {...props} surface={baseSurface} />);
    expect(screen.getByTestId('agent-rack-server-dot-glossary').dataset.live).toBe('1');
    rerender(<AgentContextRack {...props} surface={curatedEmptySurface} />);
    // token count + live dot held from the last measured frame — no flash
    expect(screen.getByTestId('agent-rack-summary').textContent).toContain('500');
    expect(screen.getByTestId('agent-rack-server-dot-glossary').dataset.live).toBe('1');
  });

  it('without a seam the chip is a tooltip no-op; without tokens it hides the tok part', () => {
    render(
      <AgentContextRack
        {...rackProps}
        enabledTools={['glossary_search']}
        activatedTools={[]}
        surface={null}
      />,
    );
    const chip = screen.getByTestId('agent-rack-summary');
    expect(chip.textContent).toContain('rack.summary_no_tokens');
    expect(chip.title).toContain('rack.summary_tooltip');
    fireEvent.click(chip); // must not throw
  });
});
