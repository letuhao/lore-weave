// D-REG-BOOK-TIER-FE — the Extensions "book context". When a book is selected, the
// list hooks fetch that book's book-tier rows (grant-gated backend) and the create
// forms create book-tier resources; null = the user's own (default). Shared via
// context so every capability hook reads ONE source of truth.
import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';

interface ExtensionScope {
  bookId: string | null;
  setBookId: (id: string | null) => void;
}

const Ctx = createContext<ExtensionScope>({ bookId: null, setBookId: () => {} });

export function ExtensionScopeProvider({ children }: { children: ReactNode }) {
  const [bookId, setBookId] = useState<string | null>(null);
  const value = useMemo(() => ({ bookId, setBookId }), [bookId]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useExtensionScope(): ExtensionScope {
  return useContext(Ctx);
}
