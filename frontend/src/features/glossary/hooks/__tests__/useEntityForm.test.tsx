import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import type { BookAttribute, BookGenre, BookKind, BookOntology } from '../../tieringTypes';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

// useEntityForm reads the ontology via useBookOntology; inject a controlled one.
const ontologyState = vi.hoisted(() => ({ value: null as unknown as ReturnType<() => unknown> }));
vi.mock('../useBookOntology', () => ({ useBookOntology: () => ontologyState.value }));

const glossaryMocks = vi.hoisted(() => ({
  createEntity: vi.fn(),
  getEntity: vi.fn(),
  patchAttributeValue: vi.fn(),
}));
vi.mock('../../api', () => ({ glossaryApi: glossaryMocks }));

const tieringMocks = vi.hoisted(() => ({ setEntityGenres: vi.fn() }));
vi.mock('../../tieringApi', () => ({ tieringApi: tieringMocks }));

import { useEntityForm } from '../useEntityForm';

const KIND_ID = 'bk1';
const G_UNIV = 'g-univ';
const G_XIANXIA = 'g-xianxia';
const G_ROMANCE = 'g-romance';

function genre(id: string, code: string, active: boolean): BookGenre {
  return { genre_id: id, code, name: code, icon: '', color: '#000', sort_order: 0, active, source_ref: null };
}
function attr(id: string, genreId: string, code: string): BookAttribute {
  return {
    attr_id: id, kind_id: KIND_ID, genre_id: genreId, code, name: code,
    field_type: 'text', is_required: false, sort_order: 0, options: [], source_ref: null,
  };
}

function makeOntology(): BookOntology {
  return {
    book_id: 'book-1',
    genres: [genre(G_UNIV, 'universal', true), genre(G_XIANXIA, 'xianxia', true), genre(G_ROMANCE, 'romance', false)],
    kinds: [{ book_kind_id: KIND_ID, code: 'character', name: 'Character', icon: '', color: '#000', sort_order: 0, is_hidden: false, source_ref: null } as BookKind],
    kind_genres: [],
    // `rank` is defined in BOTH xianxia and romance → keep-both (namespaced) when both active.
    attributes: [
      attr('a-uni', G_UNIV, 'name'),
      attr('a-xx', G_XIANXIA, 'rank'),
      attr('a-rom', G_ROMANCE, 'rank'),
    ],
  };
}

function setOntology(over: Partial<Record<string, unknown>> = {}) {
  ontologyState.value = {
    ontology: makeOntology(),
    isAdopted: true,
    isLoading: false,
    error: null,
    ...over,
  } as never;
}

beforeEach(() => {
  Object.values(glossaryMocks).forEach((m) => m.mockReset());
  tieringMocks.setEntityGenres.mockReset();
  glossaryMocks.createEntity.mockResolvedValue({ entity_id: 'e-new' });
  glossaryMocks.getEntity.mockResolvedValue({ attribute_values: [] });
  glossaryMocks.patchAttributeValue.mockResolvedValue({});
  tieringMocks.setEntityGenres.mockResolvedValue({});
  setOntology();
});

describe('useEntityForm', () => {
  it('defaults the genre selection to the book active genres', () => {
    const { result } = renderHook(() => useEntityForm('book-1', KIND_ID));
    expect(result.current.selectedGenreIds.sort()).toEqual([G_UNIV, G_XIANXIA].sort());
  });

  it('namespaces a code present in 2+ selected genres (keep-both)', () => {
    const { result } = renderHook(() => useEntityForm('book-1', KIND_ID));
    // Add romance so `rank` spans two active genres.
    act(() => result.current.setSelectedGenreIds([G_UNIV, G_XIANXIA, G_ROMANCE]));
    const labels = result.current.sections.flatMap((s) => s.fields.map((f) => f.labelCode));
    expect(labels).toContain('rank·xianxia');
    expect(labels).toContain('rank·romance');
    expect(labels).toContain('name'); // single-genre code stays bare
  });

  it('creates with NO genre override when the selection equals the book default', async () => {
    const { result } = renderHook(() => useEntityForm('book-1', KIND_ID));
    await act(async () => { await result.current.submit(); });
    // genreIds (4th arg) is undefined → the entity follows the book's active genres.
    expect(glossaryMocks.createEntity).toHaveBeenCalledWith('book-1', KIND_ID, 'tok', undefined);
    expect(tieringMocks.setEntityGenres).not.toHaveBeenCalled();
  });

  it('passes the override genres AT create when the selection diverges', async () => {
    const { result } = renderHook(() => useEntityForm('book-1', KIND_ID));
    act(() => result.current.setSelectedGenreIds([G_UNIV, G_XIANXIA, G_ROMANCE]));
    await act(async () => { await result.current.submit(); });
    expect(glossaryMocks.createEntity).toHaveBeenCalledWith('book-1', KIND_ID, 'tok', [G_UNIV, G_XIANXIA, G_ROMANCE]);
    // No separate setEntityGenres round-trip — it's atomic in createEntity now.
    expect(tieringMocks.setEntityGenres).not.toHaveBeenCalled();
  });

  it('writes filled attribute values mapped through their value rows', async () => {
    glossaryMocks.getEntity.mockResolvedValue({
      attribute_values: [{ attr_def_id: 'a-uni', attr_value_id: 'av-1' }],
    });
    const { result } = renderHook(() => useEntityForm('book-1', KIND_ID));
    act(() => result.current.setValue('a-uni', 'Nezha'));
    await act(async () => { await result.current.submit(); });
    expect(glossaryMocks.patchAttributeValue).toHaveBeenCalledWith(
      'book-1', 'e-new', 'av-1', { original_value: 'Nezha' }, 'tok',
    );
  });
});
