import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ToolSkillAddModal } from '../ToolSkillAddModal';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string, opts?: { defaultValue?: string; count?: number }) => opts?.defaultValue ?? key }),
}));

const listToolsCatalog = vi.fn();
const listSkillsCatalog = vi.fn();
vi.mock('../../api', () => ({
  chatApi: {
    listToolsCatalog: (...args: unknown[]) => listToolsCatalog(...args),
    listSkillsCatalog: (...args: unknown[]) => listSkillsCatalog(...args),
  },
}));

function tool(name: string, domain: string, description = 'desc') {
  return { name, domain, tier: 'R', description };
}

const TOOLS = [
  tool('kg_get_entity', 'kg'),
  tool('kg_list_entities', 'kg'),
  tool('glossary_search', 'glossary'),
  tool('book_create', 'book'),
];
// 25 tools in one category — big enough to cross the 20-per-page boundary
// and prove the Pagination footer + page-2 slice, not just page 1.
const MANY_KG_TOOLS = Array.from({ length: 25 }, (_, i) => tool(`kg_tool_${String(i).padStart(2, '0')}`, 'kg'));
const SKILLS = [
  { id: 'universal', label: 'Universal', surfaces: ['chat'] },
  { id: 'glossary', label: 'Glossary', surfaces: ['book'] },
];

const LEGACY_TOOLS = [
  tool('glossary_book_create', 'glossary', 'old create'),
  tool('glossary_user_create', 'glossary', 'old create (user)'),
];

function setup(props: Partial<React.ComponentProps<typeof ToolSkillAddModal>> = {}) {
  const onClose = vi.fn();
  const onAddTool = vi.fn();
  const onAddSkill = vi.fn();
  render(
    <ToolSkillAddModal
      open
      onClose={onClose}
      token="tok"
      onAddTool={onAddTool}
      onAddSkill={onAddSkill}
      existingTools={[]}
      existingSkills={[]}
      {...props}
    />,
  );
  return { onClose, onAddTool, onAddSkill };
}

describe('ToolSkillAddModal', () => {
  beforeEach(() => {
    listToolsCatalog.mockResolvedValue({ items: TOOLS });
    listSkillsCatalog.mockResolvedValue({ items: SKILLS });
  });

  it('renders inside a FormDialog and shows tools grouped by category by default', async () => {
    setup();
    await waitFor(() => expect(screen.getByTestId('tool-skill-modal')).toBeInTheDocument());
    await waitFor(() => expect(screen.getByTestId('tool-skill-grouped-view')).toBeInTheDocument());
    expect(screen.getByTestId('tool-skill-item-kg_get_entity')).toBeInTheDocument();
    expect(screen.getByTestId('tool-skill-item-book_create')).toBeInTheDocument();
  });

  it('shows a category chip per domain plus an All chip, with counts', async () => {
    setup();
    await waitFor(() => expect(screen.getByTestId('tool-skill-category-chips')).toBeInTheDocument());
    expect(screen.getByTestId('tool-skill-category-chip-all')).toHaveTextContent('4');
    expect(screen.getByTestId('tool-skill-category-chip-kg')).toHaveTextContent('2');
    expect(screen.getByTestId('tool-skill-category-chip-glossary')).toHaveTextContent('1');
  });

  it('clicking a category chip narrows to a flat, paginated list of just that category', async () => {
    setup();
    await waitFor(() => expect(screen.getByTestId('tool-skill-category-chip-kg')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('tool-skill-category-chip-kg'));
    expect(screen.queryByTestId('tool-skill-grouped-view')).not.toBeInTheDocument();
    expect(screen.getByTestId('tool-skill-item-kg_get_entity')).toBeInTheDocument();
    expect(screen.getByTestId('tool-skill-item-kg_list_entities')).toBeInTheDocument();
    expect(screen.queryByTestId('tool-skill-item-book_create')).not.toBeInTheDocument();
  });

  it('paginates a >20-item category: page 1 shows the first 20, page 2 shows the rest', async () => {
    listToolsCatalog.mockResolvedValueOnce({ items: [...TOOLS, ...MANY_KG_TOOLS] });
    setup();
    await waitFor(() => expect(screen.getByTestId('tool-skill-category-chip-kg')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('tool-skill-category-chip-kg'));

    // 27 kg tools total (2 original + 25 more) → page 1 = first 20.
    expect(screen.getByTestId('tool-skill-item-kg_get_entity')).toBeInTheDocument();
    expect(screen.getByTestId('tool-skill-item-kg_tool_00')).toBeInTheDocument();
    expect(screen.queryByTestId('tool-skill-item-kg_tool_24')).not.toBeInTheDocument();
    expect(screen.getByText('2', { selector: 'button' })).toBeInTheDocument();

    fireEvent.click(screen.getByText('2', { selector: 'button' }));
    expect(screen.queryByTestId('tool-skill-item-kg_get_entity')).not.toBeInTheDocument();
    expect(screen.getByTestId('tool-skill-item-kg_tool_24')).toBeInTheDocument();
  });

  it('search narrows across all categories and flattens the grouped view', async () => {
    setup();
    await waitFor(() => expect(screen.getByTestId('tool-skill-search')).toBeInTheDocument());
    fireEvent.change(screen.getByTestId('tool-skill-search'), { target: { value: 'glossary' } });
    expect(screen.queryByTestId('tool-skill-grouped-view')).not.toBeInTheDocument();
    expect(screen.getByTestId('tool-skill-item-glossary_search')).toBeInTheDocument();
    expect(screen.queryByTestId('tool-skill-item-book_create')).not.toBeInTheDocument();
  });

  it('shows EmptyState when a search matches nothing', async () => {
    setup();
    await waitFor(() => expect(screen.getByTestId('tool-skill-search')).toBeInTheDocument());
    fireEvent.change(screen.getByTestId('tool-skill-search'), { target: { value: 'zzz-no-match' } });
    expect(screen.getByText('No matching tools')).toBeInTheDocument();
  });

  it('excludes already-added tools/skills from both the list and the tab counts', async () => {
    setup({ existingTools: ['kg_get_entity'], existingSkills: ['universal'] });
    await waitFor(() => expect(screen.getByTestId('tool-skill-tab-tools')).toHaveTextContent('3'));
    expect(screen.queryByTestId('tool-skill-item-kg_get_entity')).not.toBeInTheDocument();
    expect(screen.getByTestId('tool-skill-tab-skills')).toHaveTextContent('1');
  });

  it('switching to the Skills tab lists skills and calls onAddSkill + closes on pick', async () => {
    const { onAddSkill, onClose } = setup();
    await waitFor(() => expect(screen.getByTestId('tool-skill-tab-skills')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('tool-skill-tab-skills'));
    const row = await screen.findByTestId('tool-skill-item-universal');
    fireEvent.click(row);
    expect(onAddSkill).toHaveBeenCalledWith('universal');
    expect(onClose).toHaveBeenCalled();
  });

  it('picking a tool calls onAddTool with the tool name and closes the modal', async () => {
    const { onAddTool, onClose } = setup();
    const row = await screen.findByTestId('tool-skill-item-book_create');
    fireEvent.click(row);
    expect(onAddTool).toHaveBeenCalledWith('book_create');
    expect(onClose).toHaveBeenCalled();
  });

  it('resets search/category/tab back to defaults each time it is reopened', async () => {
    const { rerender } = render(
      <ToolSkillAddModal
        open
        onClose={vi.fn()}
        token="tok"
        onAddTool={vi.fn()}
        onAddSkill={vi.fn()}
        existingTools={[]}
        existingSkills={[]}
      />,
    );
    await waitFor(() => expect(screen.getByTestId('tool-skill-search')).toBeInTheDocument());
    fireEvent.change(screen.getByTestId('tool-skill-search'), { target: { value: 'glossary' } });
    fireEvent.click(screen.getByTestId('tool-skill-tab-skills'));

    rerender(
      <ToolSkillAddModal
        open={false}
        onClose={vi.fn()}
        token="tok"
        onAddTool={vi.fn()}
        onAddSkill={vi.fn()}
        existingTools={[]}
        existingSkills={[]}
      />,
    );
    rerender(
      <ToolSkillAddModal
        open
        onClose={vi.fn()}
        token="tok"
        onAddTool={vi.fn()}
        onAddSkill={vi.fn()}
        existingTools={[]}
        existingSkills={[]}
      />,
    );
    await waitFor(() => expect(screen.getByTestId('tool-skill-tab-tools')).toHaveAttribute('aria-selected', 'true'));
    expect(screen.getByTestId('tool-skill-search')).toHaveValue('');
  });

  describe('Advanced tools (CAT-4 Part D)', () => {
    function setupWithLegacy(props: Partial<React.ComponentProps<typeof ToolSkillAddModal>> = {}) {
      listToolsCatalog.mockImplementation((_token: string, visibility?: string) =>
        Promise.resolve({ items: visibility === 'legacy' ? LEGACY_TOOLS : TOOLS }));
      const onClose = vi.fn();
      const onAddTool = vi.fn();
      const onAddSkill = vi.fn();
      const onAddLegacyTool = vi.fn();
      render(
        <ToolSkillAddModal
          open
          onClose={onClose}
          token="tok"
          onAddTool={onAddTool}
          onAddSkill={onAddSkill}
          existingTools={[]}
          existingSkills={[]}
          onAddLegacyTool={onAddLegacyTool}
          existingLegacyTools={[]}
          {...props}
        />,
      );
      return { onClose, onAddTool, onAddSkill, onAddLegacyTool };
    }

    it('is hidden entirely when onAddLegacyTool is not supplied', async () => {
      setup(); // no onAddLegacyTool
      await waitFor(() => expect(screen.getByTestId('tool-skill-modal')).toBeInTheDocument());
      expect(screen.queryByTestId('tool-skill-advanced-section')).not.toBeInTheDocument();
    });

    it('renders collapsed by default; toggling reveals legacy items with a legacy badge', async () => {
      setupWithLegacy();
      await waitFor(() => expect(screen.getByTestId('tool-skill-advanced-section')).toBeInTheDocument());
      expect(screen.queryByTestId('tool-skill-item-glossary_book_create')).not.toBeInTheDocument();

      fireEvent.click(screen.getByTestId('tool-skill-advanced-toggle'));
      expect(await screen.findByTestId('tool-skill-item-glossary_book_create')).toBeInTheDocument();
      expect(screen.getByTestId('tool-skill-item-glossary_book_create-legacy-badge')).toBeInTheDocument();
      // The regular (discoverable) tools list is untouched by the legacy fetch.
      expect(screen.getByTestId('tool-skill-item-book_create')).toBeInTheDocument();
      expect(screen.queryByTestId('tool-skill-item-book_create-legacy-badge')).not.toBeInTheDocument();
    });

    it('picking a legacy tool calls onAddLegacyTool (not onAddTool) and closes', async () => {
      const { onAddTool, onAddLegacyTool, onClose } = setupWithLegacy();
      fireEvent.click(await screen.findByTestId('tool-skill-advanced-toggle'));
      fireEvent.click(await screen.findByTestId('tool-skill-item-glossary_book_create'));
      expect(onAddLegacyTool).toHaveBeenCalledWith('glossary_book_create');
      expect(onAddTool).not.toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });

    it('excludes an already-pinned legacy tool from the list', async () => {
      setupWithLegacy({ existingLegacyTools: ['glossary_book_create'] });
      fireEvent.click(await screen.findByTestId('tool-skill-advanced-toggle'));
      await waitFor(() => expect(screen.getByTestId('tool-skill-item-glossary_user_create')).toBeInTheDocument());
      expect(screen.queryByTestId('tool-skill-item-glossary_book_create')).not.toBeInTheDocument();
    });
  });
});
