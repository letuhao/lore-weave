import { useEffect, useState } from 'react';

// Debounce a rapidly-changing value (e.g. a search input) so downstream work
// (a BE query per keystroke) only runs after the user pauses. This is the
// legitimate "timer synchronization" use of useEffect (CLAUDE.md FE rules
// permit subscriptions/timers in effects).
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(id);
  }, [value, delayMs]);
  return debounced;
}
