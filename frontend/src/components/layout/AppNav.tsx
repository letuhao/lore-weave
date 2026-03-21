import { Link } from 'react-router-dom';
import { apiJson } from '@/api';
import { useAuth } from '@/auth';
import { Button, buttonVariants } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export function AppNav() {
  const { accessToken, refreshToken, logoutLocal } = useAuth();

  const serverLogout = async () => {
    if (!accessToken) return;
    try {
      await apiJson('/v1/auth/logout', { method: 'POST', token: accessToken });
    } catch {
      /* still clear local */
    }
    logoutLocal();
  };

  const linkClass = cn(buttonVariants({ variant: 'link' }), 'h-auto p-0 text-foreground');

  return (
    <nav className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-border pb-4">
      <Link to="/" className={linkClass}>
        Home
      </Link>
      {!accessToken && (
        <Link to="/register" className={linkClass}>
          Register
        </Link>
      )}
      {!accessToken && (
        <Link to="/login" className={linkClass}>
          Login
        </Link>
      )}
      {accessToken && (
        <Link to="/profile" className={linkClass}>
          Profile
        </Link>
      )}
      {accessToken && (
        <Link to="/security" className={linkClass}>
          Security
        </Link>
      )}
      {accessToken && (
        <Link to="/verify" className={linkClass}>
          Verify email
        </Link>
      )}
      {!accessToken && (
        <Link to="/forgot" className={linkClass}>
          Forgot password
        </Link>
      )}
      {!accessToken && (
        <Link to="/reset" className={linkClass}>
          Reset password
        </Link>
      )}
      {accessToken && (
        <Button type="button" variant="outline" size="sm" className="ml-auto" onClick={() => void serverLogout()}>
          Log out
        </Button>
      )}
      {refreshToken && !accessToken && (
        <span className="w-full text-xs text-muted-foreground md:w-auto md:ml-auto">Has refresh token only</span>
      )}
    </nav>
  );
}
