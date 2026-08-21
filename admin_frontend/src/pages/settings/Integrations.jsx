import { useEffect, useState } from 'react';
import { RefreshCw, CheckCircle, XCircle, ExternalLink } from 'lucide-react';
import api from '../../api';
import { useToast } from '../../providers/ToastProvider.jsx';
import { Section } from './shared.jsx';

export default function SettingsIntegrations() {
  const { toast } = useToast();
  const [amo, setAmo] = useState(null);   // {configured, authorized, domain}
  const [loading, setLoading] = useState(true);

  useEffect(() => { loadStatus(); }, []);

  async function loadStatus() {
    setLoading(true);
    try {
      const res = await api.get('amo/status');
      setAmo(res.data);
    } catch {
      setAmo(null);
    } finally {
      setLoading(false);
    }
  }

  async function authorize() {
    try {
      const res = await api.get('amo/auth/url');
      const w = window.open(res.data.url, 'amo_oauth', 'width=600,height=720');
      if (!w) { toast('Разрешите всплывающие окна', 'warning'); return; }
      toast('Завершите авторизацию во всплывающем окне, затем обновите статус', 'success');
    } catch (err) {
      toast(err?.response?.data?.detail || 'Не удалось получить ссылку авторизации', 'error');
    }
  }

  const Dot = ({ ok }) => ok
    ? <CheckCircle size={16} className="text-[color:var(--color-success)]" />
    : <XCircle size={16} className="text-[color:var(--color-danger)]" />;

  return (
    <div className="space-y-6 max-w-3xl">
      <Section title="amoCRM">
        <p className="text-sm text-[color:var(--color-muted-foreground)]">
          Используется для расчёта ЗП менеджеров (выручка и конверсии воронок).
          Учётные данные задаются в <code>.env</code> (AMO_DOMAIN, AMO_CLIENT_ID, AMO_CLIENT_SECRET, AMO_REDIRECT_URI).
        </p>

        {loading ? (
          <div className="text-sm text-[color:var(--color-muted-foreground)] flex items-center gap-2">
            <RefreshCw size={14} className="animate-spin" /> Проверяю статус…
          </div>
        ) : (
          <div className="rounded-lg border border-[color:var(--color-border)] p-3 space-y-2 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-[color:var(--color-muted-foreground)]">Настроен (.env)</span>
              <span className="flex items-center gap-1.5"><Dot ok={amo?.configured} />{amo?.configured ? 'да' : 'нет'}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[color:var(--color-muted-foreground)]">Авторизован</span>
              <span className="flex items-center gap-1.5"><Dot ok={amo?.authorized} />{amo?.authorized ? 'да' : 'нет'}</span>
            </div>
            {amo?.domain && (
              <div className="flex items-center justify-between">
                <span className="text-[color:var(--color-muted-foreground)]">Домен</span>
                <span className="font-mono text-xs">{amo.domain}</span>
              </div>
            )}
          </div>
        )}

        {!loading && amo && !amo.configured && (
          <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-amber-50 border border-amber-200 text-sm text-amber-800">
            Заполните AMO_* в <code>.env</code> и перезапустите сервер. В интеграции amoCRM укажите Redirect URI:
            <span className="font-mono"> {`{хост}`}/api/amo/auth/callback</span>
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          <button className="btn btn--primary flex items-center gap-2" onClick={authorize} disabled={!amo?.configured}>
            <ExternalLink size={16} /> {amo?.authorized ? 'Переавторизовать' : 'Авторизовать'} amoCRM
          </button>
          <button className="btn btn--secondary flex items-center gap-2" onClick={loadStatus}>
            <RefreshCw size={15} /> Проверить статус
          </button>
        </div>
      </Section>
    </div>
  );
}
