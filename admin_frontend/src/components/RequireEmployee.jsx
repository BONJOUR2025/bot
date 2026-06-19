import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../providers/AuthProvider.jsx';

export default function RequireEmployee({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center text-sm text-[color:var(--muted-foreground)]">
        Загрузка…
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // Admin/owner accounts (no employee_id) belong in the admin panel, not the employee portal
  if (!user.employee_id) {
    return <Navigate to="/admin" replace />;
  }

  return children;
}
