import { createPortal } from 'react-dom';

export default function Modal({ children, isOpen, onClose }) {
  if (!isOpen) return null;

  return createPortal(
    <div className="modal-backdrop" style={{ zIndex: 9999 }} onClick={e => e.target === e.currentTarget && onClose?.()}>
      {children}
    </div>,
    document.body
  );
}
