// W6 §3.2 — resolves an unresolved motif role → a cast member, wrapping the existing
// glossary roster (useGlossaryRoster). Exposes the option list for the picker. The
// actual rebind is a useMotifBinding.rebindRole mutation (the caller wires them);
// this hook only supplies the candidate cast. No JSX.
import { useMemo } from 'react';
import { useGlossaryRoster, type RosterOption } from '../../hooks/useGlossaryRoster';

export function useRoleResolver(bookId: string | undefined, token: string | null) {
  const roster = useGlossaryRoster(bookId, token);

  const options = useMemo<RosterOption[]>(() => roster.data ?? [], [roster.data]);

  return {
    options,
    isLoading: roster.isLoading,
    isError: roster.isError,
  };
}
