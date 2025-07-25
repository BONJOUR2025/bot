import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import FullDemo from './full/App.tsx';

export default function App() {
  return (
    <Router>
      <Routes>
        <Route path="/*" element={<FullDemo />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Router>
  );
}
