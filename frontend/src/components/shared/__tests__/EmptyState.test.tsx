import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { EmptyState } from '../EmptyState';
import { BookOpen } from 'lucide-react';

describe('EmptyState', () => {
  it('renders title', () => {
    render(<EmptyState icon={BookOpen} title="No books yet" />);
    expect(screen.getByText('No books yet')).toBeInTheDocument();
  });

  it('renders description when provided', () => {
    render(<EmptyState icon={BookOpen} title="Empty" description="Create your first book" />);
    expect(screen.getByText('Create your first book')).toBeInTheDocument();
  });

  it('does not render description when not provided', () => {
    const { container } = render(<EmptyState icon={BookOpen} title="Empty" />);
    // Only one <p> for title
    const paragraphs = container.querySelectorAll('p');
    expect(paragraphs).toHaveLength(1);
  });

  it('renders action when provided', () => {
    render(
      <EmptyState icon={BookOpen} title="Empty" action={<button>Create</button>} />,
    );
    expect(screen.getByText('Create')).toBeInTheDocument();
  });
});
