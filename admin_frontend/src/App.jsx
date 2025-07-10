import { BrowserRouter as Router, Routes, Route, Link, Navigate } from 'react-router-dom';
import Employees from './pages/Employees';
import Payouts from './pages/Payouts';
import PayoutsControl from './pages/PayoutsControl';
import Incentives from './pages/Incentives';
import Reports from './pages/Reports';
import Broadcast from './pages/Broadcast';
import Analytics from './pages/Analytics';
import Vacations from './pages/Vacations';
import Birthdays from './pages/Birthdays';
import Settings from './pages/Settings';

export default function App() {
  return (
    <Router>
      <div className="container mx-auto p-4 space-y-6">
        <nav className="flex flex-wrap gap-2 mb-4 bg-white p-3 rounded shadow">
          <Link className="px-3 py-2 bg-blue-50 hover:bg-blue-100 rounded" to="/admin/employees">Сотрудники</Link>
          <Link className="px-3 py-2 bg-blue-50 hover:bg-blue-100 rounded" to="/admin/payouts">Выплаты</Link>
          <Link className="px-3 py-2 bg-blue-50 hover:bg-blue-100 rounded" to="/admin/payouts-control">Контроль выплат</Link>
          <Link className="px-3 py-2 bg-blue-50 hover:bg-blue-100 rounded" to="/admin/incentives">Штрафы и премии</Link>
          <Link className="px-3 py-2 bg-blue-50 hover:bg-blue-100 rounded" to="/admin/vacations">Отпуска</Link>
          <Link className="px-3 py-2 bg-blue-50 hover:bg-blue-100 rounded" to="/admin/birthdays">Дни рождения</Link>
          <Link className="px-3 py-2 bg-blue-50 hover:bg-blue-100 rounded" to="/admin/reports">Отчёты</Link>
          <Link className="px-3 py-2 bg-blue-50 hover:bg-blue-100 rounded" to="/admin/broadcast">Рассылка</Link>
          <Link className="px-3 py-2 bg-blue-50 hover:bg-blue-100 rounded" to="/admin/analytics">Аналитика</Link>
          <Link className="px-3 py-2 bg-blue-50 hover:bg-blue-100 rounded" to="/admin/settings">Настройки</Link>
        </nav>
        <Routes>
          <Route path="/admin/employees" element={<Employees />} />
          <Route path="/admin/payouts" element={<Payouts />} />
          <Route path="/admin/payouts-control" element={<PayoutsControl />} />
          <Route path="/admin/incentives" element={<Incentives />} />
          <Route path="/admin/reports" element={<Reports />} />
          <Route path="/admin/broadcast" element={<Broadcast />} />
          <Route path="/admin/vacations" element={<Vacations />} />
          <Route path="/admin/birthdays" element={<Birthdays />} />
          <Route path="/admin/analytics" element={<Analytics />} />
          <Route path="/admin/settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/admin/employees" replace />} />
        </Routes>
      </div>
    </Router>
  );
}
