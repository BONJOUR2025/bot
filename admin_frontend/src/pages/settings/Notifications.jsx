import { useEffect, useMemo, useState } from 'react';
import { BellOff, Plus, Save, Send, X } from 'lucide-react';
import api from '../../api';
import { useToast } from '../../providers/ToastProvider.jsx';

/** Кому и какие уведомления основного бота уходят.
 *
 *  Каждая группа — свой выключатель и свои получатели (Telegram ID или
 *  @username — см. notification_routing.resolve_username).
 *  Группа, которую ещё не настраивали, шлёт получателю по умолчанию — туда
 *  же, куда всё уходило до разделения (notification_chat_id). Сохранение
 *  действует сразу во всех процессах бота, перезапуск не нужен. */

function PersonPicker({ people, taken, onAdd }) {
  const [value, setValue] = useState('');
  const [error, setError] = useState('');
  const options = people.filter((p) => !taken.includes(p.id));
  const add = () => {
    const v = value.trim();
    if (!v) return;
    const fromList = options.find((p) => `${p.name} · ${p.hint}` === v || String(p.id) === v);
    // @username: кто уже писал боту, есть в списке с подсказкой «@…» —
    // берём его ID; иначе отдаём как есть, сервер сверит при сохранении.
    const uname = /^@[A-Za-z][A-Za-z0-9_]{3,31}$/.test(v) ? v.toLowerCase() : null;
    const byUsername = uname && options.find((p) => (p.hint || '').toLowerCase() === uname);
    const id = fromList ? fromList.id
      : byUsername ? byUsername.id
        : uname || (/^\d{5,}$/.test(v) ? Number(v) : null);
    if (!id) {
      setError('Выберите сотрудника из списка, впишите @username или числовой Telegram ID');
      return;
    }
    if (taken.includes(id)) {
      setError('Уже в списке');
      return;
    }
    onAdd(id);
    setValue('');
    setError('');
  };
  return (
    <div className="nr-pick">
      <input className="input" list="nr-people" value={value} placeholder="Сотрудник, @username или Telegram ID"
        onChange={(e) => { setValue(e.target.value); setError(''); }}
        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add(); } }} />
      <button type="button" className="btn btn--secondary btn--sm" onClick={add} disabled={!value.trim()}>
        <Plus size={14} /> Добавить
      </button>
      {error && <span className="nr-warn">{error}</span>}
    </div>
  );
}

export default function SettingsNotifications() {
  const { toast } = useToast();
  const [data, setData] = useState(null);
  const [groups, setGroups] = useState({});
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(null);

  const load = async () => {
    try {
      const r = await api.get('notification-routing');
      setData(r.data);
      setGroups(Object.fromEntries(r.data.groups.map((g) => [g.key, {
        enabled: g.enabled, recipients: g.recipients.map((p) => p.id), configured: g.configured,
      }])));
      setDirty(false);
    } catch (e) {
      toast(e?.response?.data?.detail || 'Не удалось загрузить настройки уведомлений', 'error');
    }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);

  const names = useMemo(() => {
    const m = {};
    (data?.people || []).forEach((p) => { m[p.id] = p; });
    (data?.groups || []).forEach((g) => g.recipients.forEach((p) => { if (!m[p.id]) m[p.id] = p; }));
    return m;
  }, [data]);

  const change = (key, patch) => {
    setGroups((gs) => ({ ...gs, [key]: { ...gs[key], ...patch, configured: true } }));
    setDirty(true);
  };

  const save = async () => {
    setSaving(true);
    try {
      await api.put('notification-routing', {
        groups: Object.fromEntries(Object.entries(groups)
          .filter(([, g]) => g.configured)
          .map(([k, g]) => [k, { enabled: g.enabled, recipients: g.recipients }])),
      });
      toast('Сохранено — уже действует', 'success');
      await load();
    } catch (e) {
      toast(e?.response?.data?.detail || 'Не удалось сохранить', 'error');
    } finally { setSaving(false); }
  };

  const test = async (key) => {
    setTesting(key);
    try {
      const r = await api.post(`notification-routing/test/${key}`);
      toast(`Отправлено: ${r.data.recipients.length} получ.`, 'success');
    } catch (e) {
      toast(e?.response?.data?.detail || 'Не удалось отправить тест', 'error');
    } finally { setTesting(null); }
  };

  if (!data) return <p className="text-sm text-[color:var(--color-muted-foreground)]">Загрузка…</p>;
  const def = data.default_recipient;

  return (
    <div className="space-y-4">
      <div className="nr-head">
        <p className="text-sm text-[color:var(--color-muted-foreground)] max-w-[70ch]">
          Уведомления бота разбиты на группы. У каждой — свой выключатель и свои получатели: например, запросы
          на выплаты одному человеку, сообщения кандидатов другому. Группа, которую ещё не настраивали, приходит
          получателю по умолчанию{def ? ` — ${def.name}` : ''}. Получатель должен хотя бы раз написать боту.
        </p>
        <button type="button" className="btn btn--primary" onClick={save} disabled={!dirty || saving}>
          <Save size={15} /> {saving ? 'Сохраняю…' : 'Сохранить'}
        </button>
      </div>

      <datalist id="nr-people">
        {data.people.map((p) => <option key={p.id} value={`${p.name} · ${p.hint}`} />)}
      </datalist>

      <div className="nr-list">
        {data.groups.map((g) => {
          const st = groups[g.key] || { enabled: true, recipients: [] };
          const off = !st.enabled;
          return (
            <section key={g.key} className={`app-card nr-group ${off ? 'is-off' : ''}`}>
              <div className="nr-group__top">
                <label className="nr-switch" aria-label={`${g.label}: ${off ? 'выключено' : 'включено'}`}>
                  <input type="checkbox" checked={st.enabled} onChange={(e) => change(g.key, { enabled: e.target.checked })} />
                  <span />
                </label>
                <div className="nr-group__text">
                  <b>{g.label}</b>
                  <span>{g.description}</span>
                </div>
                <button type="button" className="btn btn--secondary btn--sm" onClick={() => test(g.key)}
                  disabled={off || testing === g.key || dirty} title={dirty ? 'Сначала сохраните изменения' : 'Отправить тестовое уведомление'}>
                  <Send size={14} /> {testing === g.key ? '…' : 'Тест'}
                </button>
              </div>

              {off ? (
                <p className="nr-off"><BellOff size={14} /> Выключено — уведомления этой группы никому не приходят.</p>
              ) : (
                <div className="nr-recipients">
                  {st.recipients.length === 0 && <span className="nr-warn">Нет получателей — уведомления этой группы теряются.</span>}
                  {st.recipients.map((id) => {
                    const p = names[id] || (typeof id === 'string'
                      ? { name: id, hint: 'проверится при сохранении' }
                      : { name: `ID ${id}`, hint: 'нет в списке сотрудников' });
                    return (
                      <span key={id} className={`nr-chip ${p.pending ? 'nr-chip--pending' : ''}`}
                        title={p.pending ? 'Уведомления начнут приходить, когда человек нажмёт «Старт» в боте' : undefined}>
                        <b>{p.name}</b><small>{p.hint}</small>
                        <button type="button" aria-label={`Убрать ${p.name}`}
                          onClick={() => change(g.key, { recipients: st.recipients.filter((x) => x !== id) })}><X size={13} /></button>
                      </span>
                    );
                  })}
                  {!st.configured && <span className="nr-default">по умолчанию</span>}
                  <PersonPicker people={data.people} taken={st.recipients}
                    onAdd={(id) => change(g.key, { recipients: [...st.recipients, id] })} />
                </div>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}
