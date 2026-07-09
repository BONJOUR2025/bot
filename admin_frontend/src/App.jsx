import "./styles/tokens.css";
import "./styles/globals.css";

import { lazy, Suspense } from "react";
import ThemeProvider from "./providers/ThemeProvider.jsx";
import { ViewportProvider } from "./providers/ViewportProvider.jsx";
import { ToastProvider } from "./providers/ToastProvider.jsx";
import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom";

import MainLayout from "./layouts/MainLayout.jsx";
import PlainLayout from "./layouts/PlainLayout.jsx";
import EmployeeLayout from "./layouts/EmployeeLayout.jsx";
import ErrorBoundary from "./components/ErrorBoundary.jsx";

import { AuthProvider } from "./providers/AuthProvider.jsx";
import RequireAuth from "./components/RequireAuth.jsx";
import RequireEmployee from "./components/RequireEmployee.jsx";
import NativeShell from "./components/NativeShell.jsx";

// Login loads eagerly — it's the one page an unauthenticated visitor always
// needs immediately. Everything below is lazy: previously every route's code
// (Sales, Payroll, Dashboard, ...) shipped in one ~1.7 MB bundle, so even the
// login page had to download and parse the entire admin app first.
import Login from "./pages/Login.jsx";

const EmployeeSalary = lazy(() => import("./pages/employee/EmployeeSalary.jsx"));
const EmployeePayouts = lazy(() => import("./pages/employee/EmployeePayouts.jsx"));
const EmployeeSchedule = lazy(() => import("./pages/employee/EmployeeSchedule.jsx"));
const EmployeeProfile = lazy(() => import("./pages/employee/EmployeeProfile.jsx"));
const EmployeeHistory = lazy(() => import("./pages/employee/EmployeeHistory.jsx"));
const EmployeeLeaveRequests = lazy(() => import("./pages/employee/EmployeeLeaveRequests.jsx"));
const EmployeeFeedback = lazy(() => import("./pages/employee/EmployeeFeedback.jsx"));

const Dashboard = lazy(() => import("./pages/Dashboard"));
const Employees = lazy(() => import("./pages/Employees"));
const ArchivedEmployees = lazy(() => import("./pages/ArchivedEmployees"));
const Payouts = lazy(() => import("./pages/Payouts"));
const PayoutsControl = lazy(() => import("./pages/PayoutsControl"));
const Incentives = lazy(() => import("./pages/Incentives"));
const Broadcast = lazy(() => import("./pages/Broadcast"));
const KnowledgeBase = lazy(() => import("./pages/KnowledgeBase"));
const MessageHistory = lazy(() => import("./pages/MessageHistory"));
const Vacations = lazy(() => import("./pages/Vacations"));
const LeaveRequests = lazy(() => import("./pages/LeaveRequests"));
const EmployeeMessages = lazy(() => import("./pages/EmployeeMessages"));
const Birthdays = lazy(() => import("./pages/Birthdays"));
const Settings = lazy(() => import("./pages/Settings"));
const Assets = lazy(() => import("./pages/Assets"));
const Payroll = lazy(() => import("./pages/Payroll"));
const PayrollSummary = lazy(() => import("./pages/PayrollSummary"));
const PayrollBySalon = lazy(() => import("./pages/PayrollBySalon"));
const ManagerSalary = lazy(() => import("./pages/ManagerSalary"));
const CourierSalary = lazy(() => import("./pages/CourierSalary"));
const Schedule = lazy(() => import("./pages/Schedule"));
const Tasks = lazy(() => import("./pages/Tasks"));
const Passwords = lazy(() => import("./pages/Passwords"));
const Masters = lazy(() => import("./pages/Masters"));
const AgbisUsers = lazy(() => import("./pages/AgbisUsers"));
const SalesAnalytics = lazy(() => import("./pages/SalesAnalytics"));
const AdminEmployeeProfile = lazy(() => import("./pages/AdminEmployeeProfile"));
const Salons = lazy(() => import("./pages/Salons"));
const ShiftCheckins = lazy(() => import("./pages/ShiftCheckins"));
const LocationPlans = lazy(() => import("./pages/LocationPlans"));
const SaleTransfers = lazy(() => import("./pages/SaleTransfers"));
const CashMovements = lazy(() => import("./pages/CashMovements"));
const CashSummary = lazy(() => import("./pages/CashSummary"));
const PaymentCalendar = lazy(() => import("./pages/PaymentCalendar"));
const Smses = lazy(() => import("./pages/Smses"));
const Receivables = lazy(() => import("./pages/Receivables"));
const Clients = lazy(() => import("./pages/Clients"));
const Recruitment = lazy(() => import("./pages/Recruitment"));
const VisitorCounters = lazy(() => import("./pages/VisitorCounters"));

function RouteFallback() {
  return (
    <div className="flex items-center justify-center py-24 text-[color:var(--color-muted-foreground)] text-sm">
      Загрузка…
    </div>
  );
}

export default function App() {
  return (
    <ViewportProvider>
      <ThemeProvider>
        {() => (
          <ToastProvider>
            <AuthProvider>
              <NativeShell />
              <Router>
              <ErrorBoundary>
              <Suspense fallback={<RouteFallback />}>
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
                <Route path="payroll-summary" element={<PayrollSummary />} />
                <Route path="payroll-by-salon" element={<PayrollBySalon />} />
                <Route path="manager-salary" element={<ManagerSalary />} />
                <Route path="courier-salary" element={<CourierSalary />} />
                <Route path="schedule" element={<Schedule />} />
                <Route path="tasks" element={<Tasks />} />
                <Route path="passwords" element={<Passwords />} />
                <Route path="masters" element={<Masters />} />
                <Route path="agbis-users" element={<AgbisUsers />} />
                <Route path="sales" element={<SalesAnalytics />} />
                <Route path="salons" element={<Salons />} />
                <Route path="shift-checkins" element={<ShiftCheckins />} />
                <Route path="visitor-counters" element={<VisitorCounters />} />
                <Route path="location-plans" element={<LocationPlans />} />
                <Route path="sale-transfers" element={<SaleTransfers />} />
                <Route path="cash-moves" element={<CashMovements />} />
                <Route path="cash-summary" element={<CashSummary />} />
                <Route path="receivables" element={<Receivables />} />
                <Route path="clients" element={<Clients />} />
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
              </Suspense>
              </ErrorBoundary>
              </Router>
            </AuthProvider>
          </ToastProvider>
        )}
      </ThemeProvider>
    </ViewportProvider>
  );
}
