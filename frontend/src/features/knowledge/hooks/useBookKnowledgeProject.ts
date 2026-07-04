import { useMemo } from 'react';
import { useProjects } from './useProjects';
import type { Project } from '../types';

export interface BookKnowledgeProject {
  project: Project | null;
  projectId: string | null;
  isLoading: boolean;
}

/**
 * 14_kg_panels.md A1/K5 — the ONE place a book-scoped KG panel resolves
 * "the book's knowledge project" (a project's `book_id` FK is optional, so
 * this is a lookup, not a guaranteed 1:1). Sourced from the existing
 * useProjects(false) cache — no new fetch. Extracted from
 * KnowledgeOntologyTab's inline `projects.find(p => p.book_id === bookId)`.
 */
export function useBookKnowledgeProject(bookId: string): BookKnowledgeProject {
  const { items, isLoading } = useProjects(false);
  const project = useMemo(
    () => items.find((p) => p.book_id === bookId) ?? null,
    [items, bookId],
  );
  return { project, projectId: project?.project_id ?? null, isLoading };
}
