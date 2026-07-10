import { Loader2, ShieldCheck, AlertTriangle } from 'lucide-react';

// Renders the AI pre-check button + result + confirm button.
// `gate` is the object returned by useAiCheckGate().
// `text`, `scope`, `vacancyId`, `fieldLabel` describe what is being checked.
// `onConfirm` is called only once isConfirmable(text) is true.
export default function AiCheckPanel({ gate, text, scope, vacancyId, fieldLabel, onConfirm, confirming, confirmLabel = 'Подтвердить и сохранить' }) {
  const { checking, result, error, check, isConfirmable } = gate;
  const confirmable = isConfirmable(text) && !!text.trim();

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => check(text, { scope, vacancyId, fieldLabel })}
          disabled={checking || !text.trim()}
          className="btn btn-secondary text-xs flex items-center gap-1.5 disabled:opacity-50"
        >
          {checking ? <Loader2 size={13} className="animate-spin" /> : <ShieldCheck size={13} />}
          {checking ? 'Проверяем через ИИ...' : 'Проверить через ИИ'}
        </button>
        {confirmable && (
          <span className="text-xs text-emerald-600 flex items-center gap-1">
            <ShieldCheck size={12} /> Проверено, можно сохранить
          </span>
        )}
      </div>

      {error && <p className="text-xs text-red-500">{error}</p>}

      {result && (
        <div className={`rounded-lg border px-3 py-2 text-xs space-y-1 ${
          result.scope_mismatch ? 'border-red-200 bg-red-50' : 'border-[color:var(--color-border)] bg-[color:var(--color-bg-secondary)]'
        }`}>
          {!result.ai_available && (
            <p className="text-[color:var(--color-muted-foreground)]">ИИ-проверка недоступна, но сохранение разрешено.</p>
          )}
          {result.summary && <p className="text-[color:var(--color-foreground)]">{result.summary}</p>}
          {result.scope_mismatch && (
            <p className="flex items-center gap-1.5 text-red-600 font-medium">
              <AlertTriangle size={12} /> Похоже на текст не для этой области видимости — проверьте перед сохранением
            </p>
          )}
          {result.concerns?.length > 0 && (
            <ul className="list-disc list-inside text-amber-700">
              {result.concerns.map((c, i) => <li key={i}>{c}</li>)}
            </ul>
          )}
        </div>
      )}

      <button
        type="button"
        onClick={onConfirm}
        disabled={!confirmable || confirming}
        className="btn btn--primary text-xs disabled:opacity-40"
        title={!confirmable ? 'Сначала выполните проверку через ИИ (после любого изменения текста нужна повторная проверка)' : ''}
      >
        {confirming ? 'Сохранение...' : confirmLabel}
      </button>
    </div>
  );
}
