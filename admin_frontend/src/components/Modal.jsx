import { createPortal } from 'react-dom';

export default function Modal({ children, isOpen }) {
  if (!isOpen) return null;

  return createPortal(
    <div className="modal-backdrop" style={{ zIndex: 9999 }}>
      {children}
    </div>,
    document.body
  );
}
