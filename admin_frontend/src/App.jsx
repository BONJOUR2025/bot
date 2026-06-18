import "./styles/tokens.css";
import "./styles/globals.css";

import ThemeProvider from "./providers/ThemeProvider.jsx";
import { ViewportProvider } from "./providers/ViewportProvider.jsx";
import { ToastProvider } from "./providers/ToastProvider.jsx";
import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom";

import MainLayout from "./layouts/MainLayout.jsx";
import PlainLayout from "./layouts/PlainLayout.jsx";
import EmployeeLayout from "./layouts/EmployeeLayout.jsx";

import { AuthProvider } from "./providers/AuthProvider.jsx";
import RequireAuth from "./components/RequireAuth.jsx";
import RequireEmployee from "./components/RequireEmployee.jsx";

import EmployeeSalary from "./pages/employee/EmployeeSalary.jsx";
import EmployeePayouts from "./pages/employee/EmployeePayouts.jsx";
import EmployeeSchedule from "./pages/employee/EmployeeSchedule.jsx";
import EmployeeProfile from "./pages/employee/EmployeeProfile.jsx";
import EmployeeHistory from "./pages/employee/EmployeeHistory.jsx";
import EmployeeLeaveRequests from "./pages/employee/EmployeeLeaveRequests.jsx";
import EmployeeFeedback from "./pages/employee/EmployeeFeedback.jsx";

import Login from "./pages/Login.jsx";
import Dashboard from "./pages/Dashboard";
import Employees from "./pages/Employees";
import ArchivedEmployees from "./pages/ArchivedEmployees";
import Payouts from "./pages/Payouts";
import PayoutsControl from "./pages/PayoutsControl";
import Incentives from "./pages/Incentives";
import Reports from "./pages/Reports";
import Broadcast from "./pages/Broadcast";
import KnowledgeBase from "./pages/KnowledgeBase";
import MessageHistory from "./pages/MessageHistory";
import Vacations from "./pages/Vacations";
import LeaveRequests from "./pages/LeaveRequests";
import EmployeeMessages from "./pages/EmployeeMessages";
import Birthdays from "./pages/Birthdays";
import Settings from "./pages/Settings";
import Assets from "./pages/Assets";
import Payroll from "./pages/Payroll";
import Schedule from "./pages/Schedule";
import Tasks from "./pages/Tasks";
import Passwords from "./pages/Passwords";
import Masters from "./pages/Masters";
import SalesAnalytics from "./pages/SalesAnalytics";
import AdminEmployeeProfile from "./pages/AdminEmployeeProfile";
import Salons from "./pages/Salons";
import ShiftCheckins from "./pages/ShiftCheckins";
import LocationPlans from "./pages/LocationPlans";
import SaleTransfers from "./pages/SaleTransfers";
import CashMovements from "./pages/CashMovements";
import PaymentCalendar from "./pages/PaymentCalendar";
import Smses from "./pages/Smses";
import Recruitment from "./pages/Recruitment";

export default function App() {
  return (
    <ViewportProvider>
      <ThemeProvider>
        {() => (
          <ToastProvider>
            <AuthProvider>
              <Router>
              <Routes>
              {/* Единая страница логина */}
              <Route path="/login" element={<PlainLayout />}>
                <Route index element={<Login />} />
              </Route>
              {/* Редиректы со старых адресов */}
              <Route path="/admin/login" element={<Navigate to="/login" replace />} />
              <Route path="/employee/login" element={<Navigate to="/login" replace />} />

              {/* Приватная зона: всё под /admin защищено RequireAuth */}
              <Route
                path="/admin"
                element={
                  <RequireAuth>
                    <MainLayout />
                  </RequireAuth>
                }
              >
                <Route index element={<Dashboard />} />
                <Route path="employees" element={<Employees />} />
                <Route path="employees/:id" element={<AdminEmployeeProfile />} />
                <Route path="archive" element={<ArchivedEmployees />} />
                <Route path="payouts" element={<Payouts />} />
                <Route path="payouts-control" element={<PayoutsControl />} />
                <Route path="incentives" element={<Incentives />} />
                <Route path="reports" element={<Reports />} />
                <Route path="broadcast" element={<Broadcast />} />
                <Route path="messages" element={<MessageHistory />} />
                <Route path="vacations" element={<Vacations />} />
                <Route path="leave-requests" element={<LeaveRequests />} />
                <Route path="employee-messages" element={<EmployeeMessages />} />
                <Route path="birthdays" element={<Birthdays />} />
                <Route path="assets" element={<Assets />} />
                <Route path="dictionary" element={<Navigate to="/admin/settings/dictionary" replace />} />
                <Route path="access" element={<Navigate to="/admin/settings/access" replace />} />
                <Route path="settings/*" element={<Settings />} />
                <Route path="payroll" element={<Payroll />} />
                <Route path="schedule" element={<Schedule />} />
                <Route path="tasks" element={<Tasks />} />
                <Route path="passwords" element={<Passwords />} />
                <Route path="masters" element={<Masters />} />
                <Route path="sales" element={<SalesAnalytics />} />
                <Route path="salons" element={<Salons />} />
                <Route path="shift-checkins" element={<ShiftCheckins />} />
                <Route path="location-plans" element={<LocationPlans />} />
                <Route path="sale-transfers" element={<SaleTransfers />} />
                <Route path="cash-moves" element={<CashMovements />} />
                <Route path="payment-calendar" element={<PaymentCalendar />} />
                <Route path="smses" element={<Smses />} />
                <Route path="recruitment" element={<Recruitment />} />
                <Route path="knowledge-base" element={<KnowledgeBase />} />
              </Route>

              {/* Личный кабинет сотрудника */}
              <Route
                path="/employee"
                element={
                  <RequireEmployee>
                    <EmployeeLayout />
                  </RequireEmployee>
                }
              >
                <Route index element={<Navigate to="/employee/salary" replace />} />
                <Route path="salary" element={<EmployeeSalary />} />
                <Route path="payouts" element={<EmployeePayouts />} />
                <Route path="schedule" element={<EmployeeSchedule />} />
                <Route path="profile" element={<EmployeeProfile />} />
                <Route path="history" element={<EmployeeHistory />} />
                <Route path="leave-requests" element={<EmployeeLeaveRequests />} />
                <Route path="feedback" element={<EmployeeFeedback />} />
              </Route>

              {/* Фолбэк */}
              <Route path="*" element={<Navigate to="/login" replace />} />
              </Routes>
              </Router>
            </AuthProvider>
          </ToastProvider>
        )}
      </ThemeProvider>
    </ViewportProvider>
  );
}
