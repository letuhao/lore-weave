import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { EntityListBrowser } from '../EntityListBrowser';
import { type ServerPagedList } from '@/components/pagination/useServerPagedList';

// i18n returns keys in tests; we assert on structure/callbacks, not copy.

function makePaged(over: Partial<ServerPagedList> = {}): ServerPagedList {
  return {
    page: 0,
    setPage: vi.fn(),
    pageSize: 50,
    setPageSize: vi.fn(),
    offset: 0,
    limit: 50,
    reset: vi.fn(),
    pageInfo: () => ({ pageCount: 1, safePage: 0, start: 1, end: 50 }),
    ...over,
  };
}

const baseProps = {
  searchValue: '',
  onSearchChange: vi.fn(),
  searchMode: 'simple' as const,
  onToggleSearchMode: vi.fn(),
  sort: 'updated_at',
  onSortChange: vi.fn(),
  sortOptions: [
    { value: 'links', label: 'Most appearances' },
    { value: 'updated_at', label: 'Recent' },
  ],
};

describe('EntityListBrowser', () => {
  it('renders the toolbar, sort options, children, and footer', () => {
    render(
      <EntityListBrowser
        {...baseProps}
        total={120}
        paged={makePaged()}
        pageInfo={{ pageCount: 3, safePage: 0, start: 1, end: 50 }}
        filterControl={<button>filter-btn</button>}
      >
        <div data-testid="list-body">rows</div>
      </EntityListBrowser>,
    );
    expect(screen.getByTestId('glossary-search-input')).toBeTruthy();
    expect(screen.getByTestId('glossary-raw-toggle')).toBeTruthy();
    expect(screen.getByText('Most appearances')).toBeTruthy();
    expect(screen.getByText('filter-btn')).toBeTruthy();
    expect(screen.getByTestId('list-body')).toBeTruthy();
    // Footer present (total>0) + Pager shows (pageCount 3).
    expect(screen.getByTestId('glossary-range')).toBeTruthy();
  });

  it('wires search, raw-toggle, and sort callbacks', () => {
    const onSearchChange = vi.fn();
    const onToggleSearchMode = vi.fn();
    const onSortChange = vi.fn();
    render(
      <EntityListBrowser
        {...baseProps}
        onSearchChange={onSearchChange}
        onToggleSearchMode={onToggleSearchMode}
        onSortChange={onSortChange}
        total={10}
        paged={makePaged()}
        pageInfo={{ pageCount: 1, safePage: 0, start: 1, end: 10 }}
      >
        <div />
      </EntityListBrowser>,
    );
    fireEvent.change(screen.getByTestId('glossary-search-input'), { target: { value: 'abc' } });
    expect(onSearchChange).toHaveBeenCalledWith('abc');
    fireEvent.click(screen.getByTestId('glossary-raw-toggle'));
    expect(onToggleSearchMode).toHaveBeenCalled();
    fireEvent.change(screen.getByTestId('glossary-sort'), { target: { value: 'links' } });
    expect(onSortChange).toHaveBeenCalledWith('links');
  });

  it('hides the footer when total is 0', () => {
    render(
      <EntityListBrowser
        {...baseProps}
        total={0}
        paged={makePaged()}
        pageInfo={{ pageCount: 1, safePage: 0, start: 0, end: 0 }}
      >
        <div />
      </EntityListBrowser>,
    );
    expect(screen.queryByTestId('glossary-range')).toBeNull();
  });

  it('renders the filter panel slot when provided', () => {
    render(
      <EntityListBrowser
        {...baseProps}
        total={5}
        paged={makePaged()}
        pageInfo={{ pageCount: 1, safePage: 0, start: 1, end: 5 }}
        filterPanel={<div data-testid="filter-panel">panel</div>}
      >
        <div />
      </EntityListBrowser>,
    );
    expect(screen.getByTestId('filter-panel')).toBeTruthy();
  });
});
