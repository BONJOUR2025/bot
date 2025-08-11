import { Outlet } from 'react-router-dom';
import Navigation from '../components/Navigation.jsx';

export default function MainLayout() {
  return (
    <div className="flex min-h-screen bg-surface text-gray-900 dark:bg-gray-900 dark:text-white">
      <aside className="w-64 shrink-0 p-4 border-r border-muted/20">
        <Navigation />
      </aside>
      <main className="flex-1 p-6">
        <Outlet />
      </main>
    </div>
  );
}




