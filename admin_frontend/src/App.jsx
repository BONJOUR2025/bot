import "./styles/tokens.css";
import "./styles/globals.css";
import ThemeProvider from "./providers/ThemeProvider.jsx";
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Employees from './pages/Employees';
import Payouts from './pages/Payouts';
import PayoutsControl from './pages/PayoutsControl';
import Incentives from './pages/Incentives';
import Reports from './pages/Reports';
import Broadcast from './pages/Broadcast';
import MessageHistory from './pages/MessageHistory';
import Vacations from './pages/Vacations';
import Birthdays from './pages/Birthdays';
import Settings from './pages/Settings';
import Assets from './pages/Assets';
import Dictionary from './pages/Dictionary';
import AccessControl from './pages/AccessControl';
import MainLayout from './layouts/MainLayout.jsx';
import PlainLayout from './layouts/PlainLayout.jsx';
import { AuthProvider } from './providers/AuthProvider.jsx';
import RequireAuth from './components/RequireAuth.jsx';
import Login from './pages/Login.jsx';

export default function App() {
  return (
    <ThemeProvider>
      {() => (
        <AuthProvider>
          <Router>
            <Routes>
              <Route path="/login" element={<PlainLayout />}>
                <Route index element={<Login />} />
              </Route>
              <Route path="/" element={<Navigate to="/login" replace />} />
              <Route
                path="/admin"
                element={(
                  <RequireAuth>
                    <MainLayout />
                  </RequireAuth>
                )}
              >
                <Route index element={<Dashboard />} />
                <Route path="employees" element={<Employees />} />
                <Route path="payouts" element={<Payouts />} />
                <Route path="payouts-control" element={<PayoutsControl />} />
                <Route path="incentives" element={<Incentives />} />
                <Route path="reports" element={<Reports />} />
                <Route path="broadcast" element={<Broadcast />} />
                <Route path="messages" element={<MessageHistory />} />
                <Route path="vacations" element={<Vacations />} />
                <Route path="birthdays" element={<Birthdays />} />
                <Route path="assets" element={<Assets />} />
                <Route path="dictionary" element={<Dictionary />} />
                <Route path="settings" element={<Settings />} />
                <Route path="access" element={<AccessControl />} />
              </Route>
              <Route path="*" element={<Navigate to="/login" replace />} />
            </Routes>
          </Router>
        </AuthProvider>
      )}
    </ThemeProvider>
  );
}




