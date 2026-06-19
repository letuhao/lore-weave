import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { tieringApi } from '../tieringApi';
import type {
  AdoptRequest,
  BookAttributeCreate,
  BookGenreCreate,
  BookKindCreate,
  BookOntology,
} from '../tieringTypes';

/**
 * Controller for a book's tiered ontology (G6) — the shared source for the Manage
 * workspace, attribute matrix, and entity form. Reads the book-local, single-tier
 * ontology (`GET /ontology`) and owns the book-tier mutations (adopt copy-down +
 * genre/kind/attribute CRUD + active-genres + kind↔genre links). Every mutation
 * invalidates the ontology query so all three screens stay consistent.
 *
 * Writes are Manage-gated server-side; a 403 surfaces as a thrown error the caller
 * turns into a toast (mirrors useUnknownReview's error handling).
 */
export function useBookOntology(bookId: string) {
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  const key = ['glossary-ontology', bookId];

  const { data, isLoading, error, refetch } = useQuery<BookOntology>({
    queryKey: key,
    queryFn: () => tieringApi.getOntology(bookId, accessToken!),
    enabled: !!accessToken,
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: key });

  // adopt returns the fresh ontology — seed the cache directly + invalidate.
  const adopt = async (req: AdoptRequest): Promise<BookOntology> => {
    const ont = await tieringApi.adoptOntology(bookId, req, accessToken!);
    qc.setQueryData(key, ont);
    void invalidate();
    return ont;
  };

  // ── genre CRUD ──
  const createGenre = async (p: BookGenreCreate) => {
    const r = await tieringApi.createBookGenre(bookId, p, accessToken!);
    void invalidate();
    return r;
  };
  const patchGenre = async (genreId: string, changes: Record<string, unknown>) => {
    const r = await tieringApi.patchBookGenre(bookId, genreId, changes, accessToken!);
    void invalidate();
    return r;
  };
  const deleteGenre = async (genreId: string) => {
    await tieringApi.deleteBookGenre(bookId, genreId, accessToken!);
    void invalidate();
  };

  // ── kind CRUD ──
  const createKind = async (p: BookKindCreate) => {
    const r = await tieringApi.createBookKind(bookId, p, accessToken!);
    void invalidate();
    return r;
  };
  const patchKind = async (kindId: string, changes: Record<string, unknown>) => {
    const r = await tieringApi.patchBookKind(bookId, kindId, changes, accessToken!);
    void invalidate();
    return r;
  };
  const deleteKind = async (kindId: string) => {
    await tieringApi.deleteBookKind(bookId, kindId, accessToken!);
    void invalidate();
  };
  const setKindGenres = async (kindId: string, genreIds: string[]) => {
    const r = await tieringApi.setBookKindGenres(bookId, kindId, genreIds, accessToken!);
    void invalidate();
    return r;
  };

  // ── attribute CRUD ──
  const createAttribute = async (p: BookAttributeCreate) => {
    const r = await tieringApi.createBookAttribute(bookId, p, accessToken!);
    void invalidate();
    return r;
  };
  const patchAttribute = async (attrId: string, changes: Record<string, unknown>) => {
    const r = await tieringApi.patchBookAttribute(bookId, attrId, changes, accessToken!);
    void invalidate();
    return r;
  };
  const deleteAttribute = async (attrId: string) => {
    await tieringApi.deleteBookAttribute(bookId, attrId, accessToken!);
    void invalidate();
  };

  const setActiveGenres = async (genreIds: string[]) => {
    const r = await tieringApi.setActiveGenres(bookId, genreIds, accessToken!);
    void invalidate();
    return r;
  };

  const ontology: BookOntology =
    data ?? { book_id: bookId, genres: [], kinds: [], kind_genres: [], attributes: [] };
  // A book with zero adopted kinds hasn't been scaffolded yet (pre-adopt pick-list).
  const isAdopted = (data?.kinds.length ?? 0) > 0;

  return {
    ontology,
    isAdopted,
    isLoading,
    error,
    refetch,
    adopt,
    createGenre,
    patchGenre,
    deleteGenre,
    createKind,
    patchKind,
    deleteKind,
    setKindGenres,
    createAttribute,
    patchAttribute,
    deleteAttribute,
    setActiveGenres,
  };
}
