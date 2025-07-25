import { Outlet } from 'react-router-dom';

export default function PlainLayout() {
  return (
    <main className="p-6 min-h-screen bg-surface text-gray-900 dark:bg-gray-900 dark:text-white">
      <Outlet />
    </main>
  );
}
