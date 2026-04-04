import { type ReactNode } from 'react';
import { Link } from 'react-router-dom';

interface AuthCardProps {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer?: ReactNode;
}

export function AuthCard({ title, subtitle, children, footer }: AuthCardProps) {
  return (
    <div className="w-full max-w-sm space-y-6">
      <div className="space-y-2 text-center">
        <Link to="/" className="mx-auto flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-sm font-bold text-primary-foreground">
          L
        </Link>
        <h1 className="font-serif text-xl font-semibold">{title}</h1>
        <p className="text-sm text-muted-foreground">{subtitle}</p>
      </div>
      {children}
      {footer && <div className="text-center text-xs text-muted-foreground">{footer}</div>}
    </div>
  );
}
