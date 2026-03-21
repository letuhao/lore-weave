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
    <nav className="border-b border-border pb-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <Link to="/" className={linkClass}>
            Home
          </Link>
          {accessToken && (
            <>
              <Link to="/books" className={linkClass}>
                Workspace
              </Link>
              <Link to="/books/trash" className={linkClass}>
                Recycle bin
              </Link>
              <Link to="/m03/models" className={linkClass}>
                AI Models
              </Link>
              <Link to="/m03/platform-models" className={linkClass}>
                Platform models
              </Link>
              <Link to="/m03/usage" className={linkClass}>
                Usage logs
              </Link>
            </>
          )}
          <Link to="/browse" className={linkClass}>
            Browse
          </Link>
        </div>

        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 lg:ml-auto">
          {accessToken && (
            <>
              <Link to="/profile" className={linkClass}>
                Profile
              </Link>
              <Link to="/security" className={linkClass}>
                Security
              </Link>
              <Link to="/verify" className={linkClass}>
                Verify email
              </Link>
            </>
          )}
          {!accessToken && (
            <>
              <Link to="/register" className={linkClass}>
                Register
              </Link>
              <Link to="/login" className={linkClass}>
                Login
              </Link>
              <Link to="/forgot" className={linkClass}>
                Forgot password
              </Link>
              <Link to="/reset" className={linkClass}>
                Reset password
              </Link>
            </>
          )}
          {accessToken && (
            <Button type="button" variant="outline" size="sm" onClick={() => void serverLogout()}>
              Log out
            </Button>
          )}
        </div>
      </div>
      {refreshToken && !accessToken && <p className="mt-2 text-xs text-muted-foreground">Has refresh token only</p>}
    </nav>
  );
}
