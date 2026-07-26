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
 * this is a lookup, not a guaranteed 1:1). Filters SERVER-SIDE via the BE's
 * existing `book_id` query param (/review-impl fix — the original cut filtered
 * client-side over the first cached page of ALL the user's projects, so a
 * user with more than PAGE_LIMIT projects could silently miss a linked one
 * past the first page). Extracted from KnowledgeOntologyTab's inline
 * `projects.find(p => p.book_id === bookId)`.
 */
export function useBookKnowledgeProject(bookId: string): BookKnowledgeProject {
  const { items, isLoading } = useProjects({ includeArchived: false, bookId });
  const project: Project | null = items[0] ?? null;
  return { project, projectId: project?.project_id ?? null, isLoading };
}
