import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Sparkles, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Chat } from './Chat';

// Glossary-assistant P5 — the book-scoped assistant dock. A floating "Ask AI"
// button + a right slide-over panel hosting the embedded <Chat> bound to the
// book. Mounted on book surfaces that aren't the editor (glossary page, reader).
//
// The <Chat> is LAZILY mounted on first open and then KEPT mounted (the panel
// only slides off-screen when closed) so the chat session and any in-progress
// stream survive open/close — CLAUDE.md: never conditionally unmount stateful
// components. Not mounting until first open avoids creating a book-scoped chat
// session on every page visit.

export function BookAssistantDock({ bookId }: { bookId: string }) {
  const { t } = useTranslation('chat');
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);

  function openDock() {
    setMounted(true);
    setOpen(true);
  }

  return (
    <>
      {!open && (
        <button
          type="button"
          data-testid="book-assistant-toggle"
          onClick={openDock}
          className="fixed bottom-5 right-5 z-40 inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2.5 text-xs font-medium text-primary-foreground shadow-lg hover:bg-primary/90"
          title={t('dock.open', { defaultValue: 'Ask the glossary assistant' })}
        >
          <Sparkles className="h-4 w-4" />
          {t('dock.label', { defaultValue: 'Ask AI' })}
        </button>
      )}

      {mounted && (
        <div
          data-testid="book-assistant-panel"
          aria-hidden={!open}
          className={cn(
            'fixed bottom-0 right-0 top-0 z-50 flex w-full max-w-md flex-col border-l bg-background shadow-2xl transition-transform duration-200',
            open ? 'translate-x-0' : 'pointer-events-none translate-x-full',
          )}
        >
          <div className="flex items-center justify-between border-b px-3 py-2">
            <span className="inline-flex items-center gap-1.5 text-xs font-semibold">
              <Sparkles className="h-3.5 w-3.5 text-primary" />
              {t('dock.title', { defaultValue: 'Glossary assistant' })}
            </span>
            <button
              type="button"
              data-testid="book-assistant-close"
              onClick={() => setOpen(false)}
              className="rounded p-1 text-muted-foreground hover:bg-secondary hover:text-foreground"
              title={t('dock.close', { defaultValue: 'Close' })}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <Chat key={bookId} bookId={bookId} className="min-h-0 flex-1" />
        </div>
      )}
    </>
  );
}
