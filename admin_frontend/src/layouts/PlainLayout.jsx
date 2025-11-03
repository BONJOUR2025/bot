import { Outlet } from 'react-router-dom';

import { useViewport } from '../providers/ViewportProvider.jsx';

export default function PlainLayout() {
  const { isMobile } = useViewport();

  return (
    <main className={`auth-layout ${isMobile ? 'auth-layout--mobile' : ''}`}>
      <div className="auth-layout__surface">
        <Outlet />
      </div>
    </main>
  );
}




