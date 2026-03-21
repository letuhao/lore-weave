import { Outlet } from 'react-router-dom';
import { AppNav } from '@/components/layout/AppNav';
import { Card, CardContent } from '@/components/ui/card';

export function AppLayout() {
  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto w-full max-w-screen-2xl px-4 py-6 sm:px-6 lg:px-8 xl:px-10">
        <AppNav />
        <Card className="mt-4 shadow-sm lg:mt-6">
          <CardContent className="pt-5 lg:pt-6">
            <Outlet />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
