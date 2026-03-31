interface ChapterReadViewProps {
  body: string;
  title?: string | null;
  chapterNumber?: number;
}

/**
 * Reusable reading-mode content renderer.
 * Used by ReaderPage (live draft) and RevisionHistory (revision preview).
 */
export function ChapterReadView({ body, title, chapterNumber }: ChapterReadViewProps) {
  const paragraphs = body.split(/\n\n+/).filter(Boolean);

  return (
    <article className="w-full max-w-[680px]">
      <header className="mb-10 text-center">
        {chapterNumber !== undefined && (
          <p className="text-xs uppercase tracking-wider text-muted-foreground">
            Chapter {chapterNumber}
          </p>
        )}
        {title && (
          <h1 className="mt-2 font-serif text-2xl font-semibold">{title}</h1>
        )}
        <div className="mx-auto mt-4 h-0.5 w-10 rounded bg-primary/40" />
      </header>

      {paragraphs.length > 0 ? (
        <div className="space-y-[1.4em] font-serif text-[17px] leading-[1.85]">
          {paragraphs.map((p, i) => (
            <p key={i} style={{ whiteSpace: 'pre-wrap' }}>{p}</p>
          ))}
        </div>
      ) : (
        <p className="text-center font-serif text-muted-foreground italic">
          Empty chapter — nothing written yet.
        </p>
      )}
    </article>
  );
}
