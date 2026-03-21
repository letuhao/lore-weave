type Props = {
  total: number;
  limit: number;
  offset: number;
  onChange: (nextOffset: number) => void;
};

export function PaginationBar({ total, limit, offset, onChange }: Props) {
  const prevDisabled = offset <= 0;
  const nextDisabled = offset + limit >= total;
  const page = Math.floor(offset / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(total / limit));

  return (
    <div className="flex items-center justify-between gap-2 border-t pt-3 text-sm">
      <p className="text-muted-foreground">
        Page {page}/{totalPages} ({total} items)
      </p>
      <div className="flex items-center gap-2">
        <button
          className="rounded border px-3 py-1 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={prevDisabled}
          onClick={() => onChange(Math.max(0, offset - limit))}
          type="button"
        >
          Prev
        </button>
        <button
          className="rounded border px-3 py-1 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={nextDisabled}
          onClick={() => onChange(offset + limit)}
          type="button"
        >
          Next
        </button>
      </div>
    </div>
  );
}
