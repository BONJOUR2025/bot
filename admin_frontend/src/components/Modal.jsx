import { createPortal } from 'react-dom';

export default function Modal({ children, isOpen }) {
  if (!isOpen) return null;

  return createPortal(
    <div
      className="fixed inset-0 flex items-center justify-center p-4 z-[9999]"
      style={{ backgroundColor: 'rgba(0,0,0,0.5)' }}
    >
      {children}
    </div>,
    document.body
  );
}
