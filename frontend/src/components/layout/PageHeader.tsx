import { type ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';

type Crumb = { label: string; to?: string };

interface PageHeaderProps {
  title: string;
  subtitle?: React.ReactNode;
  breadcrumbs?: Crumb[];
  actions?: ReactNode;
  tabs?: ReactNode;
}

export function PageHeader({ title, subtitle, breadcrumbs, actions, tabs }: PageHeaderProps) {
  return (
    <div className="space-y-4">
      {/* Breadcrumbs */}
      {breadcrumbs && breadcrumbs.length > 0 && (
        <nav className="flex items-center gap-1.5 text-sm text-muted-foreground">
          {breadcrumbs.map((crumb, i) => (
            <span key={i} className="flex items-center gap-1.5">
              {i > 0 && <ChevronRight className="h-3.5 w-3.5" />}
              {crumb.to ? (
                <Link to={crumb.to} className="transition-colors hover:text-foreground">
                  {crumb.label}
                </Link>
              ) : (
                <span className="font-medium text-foreground">{crumb.label}</span>
              )}
            </span>
          ))}
        </nav>
      )}

      {/* Title + Actions */}
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <h1 data-testid="page-header-title" className="font-serif text-xl font-semibold">{title}</h1>
          {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
        </div>
        {actions && <div className="flex items-center gap-2">{actions}</div>}
      </div>

      {/* Tabs */}
      {tabs}
    </div>
  );
}

/**
 * Auto-generate breadcrumbs from the current route path.
 * Usage: <Breadcrumb />
 */
export function Breadcrumb() {
  const location = useLocation();
  const segments = location.pathname.split('/').filter(Boolean);

  if (segments.length <= 1) return null;

  const crumbs: Crumb[] = segments.map((seg, i) => {
    const path = '/' + segments.slice(0, i + 1).join('/');
    const label = seg.charAt(0).toUpperCase() + seg.slice(1).replace(/-/g, ' ');
    const isLast = i === segments.length - 1;
    return { label, to: isLast ? undefined : path };
  });

  return (
    <nav className="flex items-center gap-1.5 text-sm text-muted-foreground">
      {crumbs.map((crumb, i) => (
        <span key={i} className="flex items-center gap-1.5">
          {i > 0 && <ChevronRight className="h-3.5 w-3.5" />}
          {crumb.to ? (
            <Link to={crumb.to} className="transition-colors hover:text-foreground">
              {crumb.label}
            </Link>
          ) : (
            <span className="font-medium text-foreground">{crumb.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}
