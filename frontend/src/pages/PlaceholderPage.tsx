import { Link } from 'react-router-dom';
import { BookOpen, MessageCircle, Search, BarChart3, Settings, Trophy, Trash2, Bell } from 'lucide-react';

const icons: Record<string, React.ElementType> = {
  Workspace: BookOpen,
  Chat: MessageCircle,
  Browse: Search,
  Usage: BarChart3,
  Settings: Settings,
  Leaderboard: Trophy,
  Trash: Trash2,
  Notifications: Bell,
};

export function PlaceholderPage({ title, description }: { title: string; description?: string }) {
  const Icon = icons[title] ?? BookOpen;
  const is404 = title === '404';
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-secondary">
        <Icon className="h-6 w-6 text-muted-foreground" />
      </div>
      <h1 className="font-serif text-xl font-semibold">{title}</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        {description ?? `${title} page — coming in Phase 2.`}
      </p>
      {is404 && (
        <Link to="/books" className="mt-4 text-sm text-primary hover:underline">
          &larr; Back to Workspace
        </Link>
      )}
    </div>
  );
}
