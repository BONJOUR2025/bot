import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
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
import MainLayout from './layouts/MainLayout.jsx';
import PlainLayout from './layouts/PlainLayout.jsx';

export default function App() {
  return (
    <Router>
      <Routes>
        <Route path="/admin" element={<MainLayout />}> 
          <Route index element={<Dashboard />} />
          <Route path="employees" element={<Employees />} />
          <Route path="payouts" element={<Payouts />} />
          <Route path="payouts-control" element={<PayoutsControl />} />
          <Route path="incentives" element={<Incentives />} />
          <Route path="reports" element={<Reports />} />
          <Route path="broadcast" element={<Broadcast />} />
          <Route path="vacations" element={<Vacations />} />
          <Route path="birthdays" element={<Birthdays />} />
          <Route path="analytics" element={<Analytics />} />
          <Route path="analytics-details" element={<AnalyticsDetails />} />
          <Route path="assets" element={<Assets />} />
          <Route path="dictionary" element={<Dictionary />} />
          <Route path="settings" element={<Settings />} />
        </Route>
        <Route path="*" element={<PlainLayout />}> 
          <Route index element={<Navigate to="/admin" replace />} />
        </Route>
      </Routes>
    </Router>
  );
}
