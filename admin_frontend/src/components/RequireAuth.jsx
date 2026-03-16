import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../providers/AuthProvider.jsx';
import { getHomeForUser } from '../pages/Login.jsx';

export default function RequireAuth({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center text-sm text-[color:var(--muted-foreground)]">
        Загрузка панели…
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // Employee without admin permissions ended up in /admin — redirect to their home
  if (!user.permissions?.length) {
    return <Navigate to={getHomeForUser(user)} replace />;
  }

  return children;
}
