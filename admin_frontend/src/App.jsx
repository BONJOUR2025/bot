import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import RefDashboard from './pages/RefDashboard';
import FullDemo from './full/App.tsx';

export default function App() {
  return (
    <Router>
      <Routes>
        <Route path="/admin" element={<RefDashboard />} />
        <Route path="/demo/*" element={<FullDemo />} />
        <Route path="*" element={<Navigate to="/admin" replace />} />
      </Routes>
    </Router>
  );
}
