import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import RefDashboard from './pages/RefDashboard';

export default function App() {
  return (
    <Router>
      <Routes>
        <Route path="/admin" element={<RefDashboard />} />
        <Route path="*" element={<Navigate to="/admin" replace />} />
      </Routes>
    </Router>
  );
}
