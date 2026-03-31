import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DataTable, type Column } from '../DataTable';

type TestRow = { id: string; name: string; status: string };

const columns: Column<TestRow>[] = [
  { key: 'name', header: 'Name', render: (r) => r.name },
  { key: 'status', header: 'Status', render: (r) => r.status },
];

const data: TestRow[] = [
  { id: '1', name: 'Alpha', status: 'active' },
  { id: '2', name: 'Beta', status: 'trashed' },
  { id: '3', name: 'Gamma', status: 'active' },
];

describe('DataTable', () => {
  it('renders column headers', () => {
    render(<DataTable columns={columns} data={data} rowKey={(r) => r.id} />);
    expect(screen.getByText('Name')).toBeInTheDocument();
    expect(screen.getByText('Status')).toBeInTheDocument();
  });

  it('renders all rows', () => {
    render(<DataTable columns={columns} data={data} rowKey={(r) => r.id} />);
    expect(screen.getByText('Alpha')).toBeInTheDocument();
    expect(screen.getByText('Beta')).toBeInTheDocument();
    expect(screen.getByText('Gamma')).toBeInTheDocument();
  });

  it('calls onRowClick when row is clicked', async () => {
    const onClick = vi.fn();
    render(<DataTable columns={columns} data={data} rowKey={(r) => r.id} onRowClick={onClick} />);
    await userEvent.click(screen.getByText('Alpha'));
    expect(onClick).toHaveBeenCalledWith(data[0]);
  });

  it('renders empty table with headers when data is empty', () => {
    const { container } = render(<DataTable columns={columns} data={[]} rowKey={(r: TestRow) => r.id} />);
    const headerCells = container.querySelectorAll('th');
    expect(headerCells).toHaveLength(2);
    expect(headerCells[0].textContent).toBe('Name');
    const bodyRows = container.querySelectorAll('tbody tr');
    expect(bodyRows).toHaveLength(0);
  });

  it('uses rowKey for unique keys', () => {
    const { container } = render(
      <DataTable columns={columns} data={data} rowKey={(r) => r.id} />,
    );
    const tbody = container.querySelector('tbody');
    expect(tbody?.children).toHaveLength(3);
  });
});
