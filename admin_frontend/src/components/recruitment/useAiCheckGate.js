import { useState, useCallback } from 'react';
import api from '../../api';

// Hard no-blind-save gate: text can only be confirmed/saved right after a
// successful AI check of the EXACT same text. Any edit after the check
// invalidates the gate again (checkedText !== current text -> must re-check).
export default function useAiCheckGate() {
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState(null); // {ai_available, summary, scope_mismatch, concerns}
  const [checkedText, setCheckedText] = useState(null);
  const [error, setError] = useState('');

  const check = useCallback(async (text, { scope, vacancyId, fieldLabel }) => {
    setChecking(true);
    setError('');
    try {
      const res = await api.post('/recruitment/ai/check-text', {
        text,
        scope,
        vacancy_id: vacancyId,
        field_label: fieldLabel,
      });
      setResult(res.data);
      setCheckedText(text);
      return res.data;
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
      setResult(null);
      setCheckedText(null);
      return null;
    } finally { setChecking(false); }
  }, []);

  // Call whenever the underlying text changes, to invalidate a stale check.
  const invalidate = useCallback(() => {
    setCheckedText(null);
    setResult(null);
  }, []);

  const reset = useCallback(() => {
    setCheckedText(null);
    setResult(null);
    setError('');
  }, []);

  const isConfirmable = (text) => checkedText !== null && checkedText === text && !checking;

  return { checking, result, error, check, invalidate, reset, isConfirmable, checkedText };
}
