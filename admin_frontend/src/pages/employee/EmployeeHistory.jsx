import { useEffect, useState } from 'react';
import { Download } from 'lucide-react';
import { useAuth } from '../../providers/AuthProvider.jsx';
import api from '../../api.js';

const STATUS_LABELS = {
  'Ожидает': { label: 'Ожидает', cls: 'badge--warning' },
  'Одобрено': { label: 'Одобрено', cls: 'badge--info' },
  'Отклонено': { label: 'Отклонено', cls: 'badge--error' },
  'Выплачено': { label: 'Выплачено', cls: 'badge--success' },
};

function fmt(n) {
  return Number(n).toLocaleString('ru-RU') + ' ₽';
}

function fmtDate(ts) {
  if (!ts) return '';
  return new Date(ts).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

export default function EmployeeHistory() {
  const { user } = useAuth();
  const employeeId = user?.employee_id;

  const [payouts, setPayouts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    if (!employeeId) return;
    setLoading(true);
    api
      .get('/payouts/', { params: { employee_id: employeeId } })
      .then((res) => setPayouts(res.data || []))
      .finally(() => setLoading(false));
  }, [employeeId]);

  const handleDownload = async () => {
    setDownloading(true);
    try {
      const res = await api.get('/payouts/export.pdf', {
        params: { employee_id: employeeId },
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = 'payouts.pdf';
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch {
      // ignore — no data or export failed
    } finally {
      setDownloading(false);
    }
  };

  if (!employeeId) {
    return (
      <div className="emp-page">
        <h2 className="emp-page__title">История выплат</h2>
        <p className="emp-page__empty">Аккаунт не привязан к сотруднику. Обратитесь к администратору.</p>
      </div>
    );
  }

  const sorted = [...payouts].sort((a, b) => {
    const ta = a.timestamp ? new Date(a.timestamp).getTime() : 0;
    const tb = b.timestamp ? new Date(b.timestamp).getTime() : 0;
    return tb - ta;
  });

  return (
    <div className="emp-page">
      <div className="emp-page__head">
        <h2 className="emp-page__title">История выплат</h2>
        <button
          type="button"
          className="btn btn--secondary btn--sm"
          onClick={handleDownload}
          disabled={downloading || sorted.length === 0}
        >
          <Download size={16} />
          {downloading ? 'Скачивание…' : 'Скачать PDF'}
        </button>
      </div>

      {loading && <p className="emp-page__loading">Загрузка…</p>}

      {!loading && sorted.length === 0 && (
        <p className="emp-page__empty">Выплат пока нет</p>
      )}

      {sorted.length > 0 && (
        <div className="emp-list">
          {sorted.map((p) => {
            const st = STATUS_LABELS[p.status] || { label: p.status, cls: '' };
            return (
              <div key={p.id} className="emp-payout-item">
                <div className="emp-payout-item__top">
                  <span className="emp-payout-item__amount">{fmt(p.amount)}</span>
                  <span className={`badge ${st.cls}`}>{st.label}</span>
                </div>
                <div className="emp-payout-item__details">
                  <span>{p.payout_type} · {p.method}</span>
                  {p.timestamp && <span>{fmtDate(p.timestamp)}</span>}
                </div>
                {p.note && <div className="emp-payout-item__note">{p.note}</div>}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
