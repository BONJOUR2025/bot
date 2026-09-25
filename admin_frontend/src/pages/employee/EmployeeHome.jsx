import { Navigate } from 'react-router-dom';
import { useAuth } from '../../providers/AuthProvider.jsx';

/** Стартовый раздел кабинета: у мастера — заработок по сканам, у остальных —
 *  зарплата из расчёта. Приложение «BONJOUR Мастер» открывается сюда же. */
export default function EmployeeHome() {
  const { user } = useAuth();
  return <Navigate to={user?.is_master ? '/employee/earnings' : user?.is_manager ? '/employee/kpi' : '/employee/salary'} replace />;
}
