import type { ReactNode } from 'react';

/** A single column definition for DataTable / DataGrid. */
export type ColumnDef<T> = {
  /** Unique key — used for sort field and column identification. */
  key: string;
  /** Display header label. */
  header: string;
  /** Render cell content. Falls back to `row[key]` if omitted. */
  render?: (row: T) => ReactNode;
  /** Whether this column is sortable. */
  sortable?: boolean;
  /** Optional fixed width class (e.g. 'w-32'). */
  widthClass?: string;
  /** Hide on smaller screens. */
  hideBelow?: 'sm' | 'md' | 'lg' | 'xl';
};

export type SortState = {
  field: string;
  direction: 'asc' | 'desc';
};

export type PaginationState = {
  page: number;
  pageSize: number;
  total: number;
};

export type ViewMode = 'table' | 'grid';
