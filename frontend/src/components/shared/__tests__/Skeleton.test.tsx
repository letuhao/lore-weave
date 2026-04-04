import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { Skeleton, SkeletonCard, SkeletonTable } from '../Skeleton';

describe('Skeleton', () => {
  it('renders with base classes', () => {
    const { container } = render(<Skeleton />);
    expect(container.firstChild).toHaveClass('animate-pulse');
  });

  it('applies additional className', () => {
    const { container } = render(<Skeleton className="h-4 w-32" />);
    expect(container.firstChild).toHaveClass('h-4', 'w-32');
  });
});

describe('SkeletonCard', () => {
  it('renders skeleton card structure', () => {
    const { container } = render(<SkeletonCard />);
    // Should have multiple skeleton divs
    const skeletons = container.querySelectorAll('.animate-pulse');
    expect(skeletons.length).toBeGreaterThanOrEqual(3);
  });
});

describe('SkeletonTable', () => {
  it('renders default 3 rows', () => {
    const { container } = render(<SkeletonTable />);
    // Each row has 3 skeleton divs
    const skeletons = container.querySelectorAll('.animate-pulse');
    expect(skeletons.length).toBe(9); // 3 rows * 3 skeletons
  });

  it('renders custom number of rows', () => {
    const { container } = render(<SkeletonTable rows={5} />);
    const skeletons = container.querySelectorAll('.animate-pulse');
    expect(skeletons.length).toBe(15); // 5 rows * 3 skeletons
  });
});
