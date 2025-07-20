import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Employees from './pages/Employees';
import Payouts from './pages/Payouts';
import PayoutsControl from './pages/PayoutsControl';
import Incentives from './pages/Incentives';
import Reports from './pages/Reports';
import Broadcast from './pages/Broadcast';
import Analytics from './pages/Analytics';
import AnalyticsDetails from './pages/AnalyticsDetails';
import Vacations from './pages/Vacations';
import Birthdays from './pages/Birthdays';
import Settings from './pages/Settings';
import Assets from './pages/Assets';
import Dictionary from './pages/Dictionary';
import Navigation from './components/Navigation.jsx';

export default function App() {
  return (
    <Router>
      <div className="container mx-auto p-4 space-y-6">
        <Navigation />
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
          <Route path="/admin/analytics-details" element={<AnalyticsDetails />} />
          <Route path="/admin/assets" element={<Assets />} />
          <Route path="/admin/dictionary" element={<Dictionary />} />
          <Route path="/admin/settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/admin/employees" replace />} />
        </Routes>
      </div>
    </Router>
  );
}
