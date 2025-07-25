import { Outlet } from 'react-router-dom';
import Navigation from '../components/Navigation.jsx';

export default function MainLayout() {
  return (
    <div className="min-h-screen flex flex-col bg-surface text-gray-900 dark:bg-gray-900 dark:text-white">
      <header className="bg-white shadow p-4">
        <Navigation />
      </header>
      <main className="flex-1 p-6">
        <Outlet />
      </main>
    </div>
  );
}
