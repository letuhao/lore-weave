import { Outlet } from 'react-router-dom';
import { AppNav } from '@/components/layout/AppNav';
import { Card, CardContent } from '@/components/ui/card';

export function AppLayout() {
  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto w-full max-w-lg px-4 py-8">
        <AppNav />
        <Card className="mt-6 shadow-sm">
          <CardContent className="pt-6">
            <Outlet />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
