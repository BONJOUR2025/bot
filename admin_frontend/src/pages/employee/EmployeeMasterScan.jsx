import { useCallback, useEffect, useRef, useState } from 'react';
import { ScanLine } from 'lucide-react';
import api from '../../api.js';
import { IN_MASTER_APP } from '../../utils/masterApp.js';
import { money, serviceTitle } from './masterFormat.js';

/** Вход и выход по бирке.
 *
 *  Мастер сканирует бирку камерой (сканер Google через мост приложения
 *  «BONJOUR Мастер» 1.1+) или вводит номер, видит услугу, выбирает вход или
 *  выход из цеха и подтверждает. Когда на сервере включена запись
 *  (dry_run: false), скан уходит в Агбис; иначе сервер отвечает тем, что
 *  записалось бы (master_scan_service.confirm).
 *
 *  Режим «Подряд» — для пачки изделий: действие берётся по порядку (после
 *  входа — выход), подтверждение одним касанием, и после записи камера сама
 *  открывается для следующей бирки. Всё, что требует внимания (запрет или
 *  предупреждение), останавливает поток и показывается как обычно. */

const ACTIONS = {
  in: { label: 'Вход в цех', confirm: 'Подтвердить вход', done: 'Вход' },
  out: { label: 'Выход из цеха', confirm: 'Подтвердить выход', done: 'Выход' },
};

const OP_LABELS = { insert: 'новая строка', update: 'изменение', upsert: 'найти или создать' };
const STREAK_KEY = 'masterScan.streak';
// Пауза перед повторным запуском камеры: мастер успевает увидеть «+758 ₽».
const STREAK_REOPEN_MS = 1200;

function canScanWithCamera() {
  return typeof window !== 'undefined' && typeof window.BonjourApp?.scanBarcode === 'function';
}

function readStreak() {
  try {
    return window.localStorage.getItem(STREAK_KEY) === '1';
  } catch {
    return false;
  }
}

function writeStreak(on) {
  try {
    window.localStorage.setItem(STREAK_KEY, on ? '1' : '0');
  } catch {
    // Без хранилища режим просто не запомнится до следующего раза.
  }
}

function timeText(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function clockText(date) {
  return date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
}

function valueText(value) {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(value)) {
    return new Date(value).toLocaleTimeString('ru-RU');
  }
  return String(value);
}

function errorText(err) {
  const detail = err?.response?.data?.detail;
  if (detail === 'not_a_master') {
    return 'Раздел доступен только мастерам. Если вы мастер — попросите руководителя проставить в вашей карточке код Агбис.';
  }
  if (typeof detail === 'string' && detail) return detail;
  return 'Не удалось связаться с сервером. Попробуйте ещё раз.';
}

function localDay(date = new Date()) {
  const pad = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** Заработано за сегодня: отчёт «Заработок» за месяц плюс только что сданная
 *  услуга, если отчёт (он прогревается раз в несколько минут) её ещё не видит. */
async function todayEarned(justDone) {
  const res = await api.get('/masters/me/earnings', { params: { period: 'month' } });
  const today = localDay();
  const rows = (res.data?.services || []).filter((row) => row.day === today);
  let total = rows.reduce((sum, row) => sum + (Number(row.salary) || 0), 0);
  const known = rows.some((row) => row.doc_num === justDone.doc_num && row.name === justDone.name);
  if (!known) total += Number(justDone.salary) || 0;
  return total;
}

export default function EmployeeMasterScan() {
  const [code, setCode] = useState('');
  const [action, setAction] = useState('in');
  const [info, setInfo] = useState(null);
  const [stage, setStage] = useState('idle'); // idle | looking | found | confirm | saving | done
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);
  // Режим (пишем ли в Агбис) узнаём при открытии: плашка «пробный режим» не
  // должна висеть до первой бирки, когда запись уже включена.
  const [dryRun, setDryRun] = useState(null);
  const [streak, setStreak] = useState(readStreak);
  const [log, setLog] = useState([]);
  const [today, setToday] = useState(null);
  const inputRef = useRef(null);
  const reopenTimer = useRef(null);
  const canScan = canScanWithCamera();

  const openCamera = useCallback(() => {
    if (canScanWithCamera()) window.BonjourApp.scanBarcode();
  }, []);

  const lookup = useCallback(async (raw, { keepError = false } = {}) => {
    const barcode = String(raw || '').replace(/\D/g, '');
    setCode(barcode);
    if (!keepError) setError('');
    setResult(null);
    setInfo(null);
    if (!barcode) return;
    setStage('looking');
    try {
      const res = await api.get('/masters/me/scan/lookup', { params: { barcode } });
      setInfo(res.data);
      setDryRun(res.data.dry_run);
      setAction(res.data.suggested_action || 'in');
      setStage('found');
    } catch (err) {
      setError(errorText(err));
      setStage('idle');
    }
  }, []);

  useEffect(() => {
    api
      .get('/masters/me/scan/mode')
      .then((res) => setDryRun(res.data.dry_run))
      .catch(() => setDryRun(null));
  }, []);

  // Результат нативного сканера приходит событием из приложения (MainActivity).
  useEffect(() => {
    const onScan = (event) => {
      const { value, error: scanError, cancelled } = event.detail || {};
      if (cancelled) return;
      if (scanError) {
        setError('Сканер не запустился. Введите номер бирки вручную.');
        return;
      }
      if (value) lookup(value);
    };
    window.addEventListener('bonjour-scan', onScan);
    return () => window.removeEventListener('bonjour-scan', onScan);
  }, [lookup]);

  useEffect(() => () => clearTimeout(reopenTimer.current), []);

  const toggleStreak = () => {
    setStreak((on) => {
      writeStreak(!on);
      return !on;
    });
  };

  const reset = () => {
    setCode('');
    setInfo(null);
    setResult(null);
    setError('');
    setStage('idle');
  };

  const confirm = async (chosen = action) => {
    setStage('saving');
    setError('');
    try {
      const res = await api.post('/masters/me/scan/confirm', { barcode: code, action: chosen });
      const data = res.data;
      if (!data.dry_run && !data.written) {
        // Проверка внутри записи не прошла — например, бирку уже отсканировали на терминале.
        setError(data.blockers?.join(' ') || 'Скан не записан.');
        lookup(code, { keepError: true });
        return;
      }
      setResult(data);
      setStage('done');
      setToday(null);

      if (data.written) {
        const salary = data.earning && !data.earning.reference_only ? data.earning.salary : null;
        setLog((prev) => [
          {
            key: `${Date.now()}-${code}`,
            time: clockText(new Date()),
            action: data.action,
            title: serviceTitle(data.service.name),
            docNum: data.service.doc_num,
            salary,
          },
          ...prev,
        ].slice(0, 20));
        if (salary != null) {
          todayEarned({ doc_num: data.service.doc_num, name: data.service.name, salary })
            .then(setToday)
            .catch(() => setToday(null));
        }
        if (streak && canScanWithCamera()) {
          reopenTimer.current = setTimeout(() => {
            reset();
            openCamera();
          }, STREAK_REOPEN_MS);
        }
      }
    } catch (err) {
      setError(errorText(err));
      setStage('found');
    }
  };

  const check = info?.checks?.[action];
  // Одно касание — только когда нечего взвешивать: действие по порядку,
  // разрешено и без предупреждений.
  const quick =
    streak &&
    (stage === 'found' || stage === 'saving') &&
    info &&
    action === info.suggested_action &&
    check?.allowed &&
    !check?.warnings?.length;

  return (
    <div className="emp-page">
      <div className="emp-page__head">
        <h2 className="emp-page__title">Вход и выход</h2>
        <label className="emp-scan-streak">
          <input type="checkbox" checked={streak} onChange={toggleStreak} />
          <span>Подряд</span>
        </label>
      </div>

      {dryRun === true && (
        <div className="emp-scan-banner" role="note">
          <b>Пробный режим.</b> В Агбис ничего не записывается — после подтверждения вы увидите, что записалось бы.
        </div>
      )}

      {streak && stage === 'idle' && log.length === 0 && (
        <p className="emp-scan-hint">
          Режим «Подряд»: сканируйте бирки одну за другой — вход или выход ставится по порядку, подтверждение одним
          касанием, камера откроется сама.
        </p>
      )}

      {stage !== 'done' && !quick && (
        <div className="emp-scan-get">
          {canScan ? (
            <button
              type="button"
              className="btn btn--primary emp-scan-camera"
              onClick={openCamera}
              disabled={stage === 'looking' || stage === 'saving'}
            >
              <ScanLine size={20} />
              Сканировать бирку
            </button>
          ) : IN_MASTER_APP ? (
            <p className="emp-scan-hint">
              Чтобы сканировать камерой, обновите приложение — кнопка «Обновить» вверху страницы.
              Пока можно ввести номер вручную.
            </p>
          ) : null}

          <form
            className="emp-scan-manual"
            onSubmit={(e) => {
              e.preventDefault();
              lookup(code);
            }}
          >
            <label className="form-field">
              <span>Номер бирки</span>
              <input
                ref={inputRef}
                inputMode="numeric"
                autoComplete="off"
                placeholder="18 цифр под штрихкодом"
                value={code}
                maxLength={24}
                onChange={(e) => setCode(e.target.value.replace(/[^\d\s-]/g, ''))}
              />
            </label>
            <button type="submit" className="btn btn--secondary" disabled={!code || stage === 'looking'}>
              {stage === 'looking' ? 'Ищу…' : 'Найти'}
            </button>
          </form>
        </div>
      )}

      {error && <p className="emp-page__error" role="alert">{error}</p>}

      {quick && (
        <div className="emp-salary-card emp-scan-quick">
          <div className="emp-scan-service">
            <div className="emp-scan-service__title">{serviceTitle(info.service.name)}</div>
            <div className="emp-scan-service__meta">
              Заказ {info.service.doc_num} · {money(info.service.kredit)}
            </div>
          </div>
          <button
            type="button"
            className="btn btn--primary emp-scan-quick__go"
            onClick={() => confirm(action)}
            disabled={stage === 'saving'}
          >
            {stage === 'saving' ? 'Записываю…' : `${ACTIONS[action].label} — подтвердить`}
          </button>
          <button type="button" className="btn btn--secondary" onClick={reset} disabled={stage === 'saving'}>
            Не эта бирка
          </button>
        </div>
      )}

      {info && stage !== 'done' && !quick && (
        <div className="emp-salary-card">
          <section className="emp-salary-section">
            <div className="emp-salary-section__title">Услуга</div>
            <div className="emp-scan-service">
              <div className="emp-scan-service__title">{serviceTitle(info.service.name)}</div>
              <div className="emp-scan-service__meta">
                Заказ {info.service.doc_num} · {money(info.service.kredit)}
              </div>
              <div className="emp-scan-service__meta">
                Статус: {info.service.status_name}
                {info.service.current_post ? ` · сейчас: ${info.service.current_post}` : ''}
              </div>
            </div>
          </section>

          {info.scans.length > 0 && (
            <section className="emp-salary-section">
              <div className="emp-salary-section__title">Сканы по бирке</div>
              <div className="emp-scan-history">
                {info.scans.map((s, i) => (
                  <div key={`${s.date}-${i}`} className="emp-scan-history__row">
                    <span>{timeText(s.date)}</span>
                    <span>{s.post_name}</span>
                    <span>{s.is_me ? 'вы' : s.master || '—'}</span>
                  </div>
                ))}
              </div>
            </section>
          )}

          <section className="emp-salary-section">
            <div className="emp-salary-section__title">Что отметить</div>
            <div className="emp-scan-posts" role="group" aria-label="Пост">
              {Object.entries(ACTIONS).map(([key, a]) => (
                <button
                  key={key}
                  type="button"
                  className="emp-scan-post"
                  aria-pressed={action === key}
                  onClick={() => {
                    setAction(key);
                    if (stage === 'confirm') setStage('found');
                  }}
                >
                  {a.label}
                  {info.suggested_action === key && <small>по порядку</small>}
                </button>
              ))}
            </div>

            {check?.blockers?.map((b) => (
              <p key={b} className="emp-scan-msg emp-scan-msg--block">{b}</p>
            ))}
            {check?.warnings?.map((w) => (
              <p key={w} className="emp-scan-msg emp-scan-msg--warn">{w}</p>
            ))}

            {stage === 'confirm' ? (
              <div className="emp-scan-confirm">
                <p>
                  {ACTIONS[action].label}: заказ {info.service.doc_num}, «{serviceTitle(info.service.name)}». Всё верно?
                </p>
                <div className="emp-scan-confirm__actions">
                  <button type="button" className="btn btn--primary" onClick={() => confirm(action)}>
                    Да, подтверждаю
                  </button>
                  <button type="button" className="btn btn--secondary" onClick={() => setStage('found')}>
                    Отмена
                  </button>
                </div>
              </div>
            ) : (
              <button
                type="button"
                className="btn btn--primary emp-scan-go"
                disabled={!check?.allowed || stage === 'saving'}
                onClick={() => setStage('confirm')}
              >
                {stage === 'saving' ? 'Записываю…' : ACTIONS[action].confirm}
              </button>
            )}
          </section>
        </div>
      )}

      {stage === 'done' && result && (
        <div className="emp-salary-card">
          <section className="emp-salary-section">
            <div className="emp-salary-section__title">
              {ACTIONS[result.action].label} · заказ {result.service.doc_num}
            </div>
            {result.dry_run ? (
              <p className="emp-scan-msg emp-scan-msg--info">
                Пробный режим: в Агбис ничего не записано. При включённой записи появилось бы:
              </p>
            ) : (
              <p className="emp-scan-msg emp-scan-msg--ok">
                Записано в Агбис: {ACTIONS[result.action].label.toLowerCase()}, «{serviceTitle(result.service.name)}».
              </p>
            )}

            {result.earning && (
              <div className="emp-scan-earned" aria-live="polite">
                <div className="emp-scan-earned__sum">
                  {result.dry_run ? '' : '+'}
                  {money(result.earning.salary)}
                </div>
                <div className="emp-scan-earned__meta">
                  {result.earning.reference_only
                    ? 'справочно — ученику идёт стипендия'
                    : `${Math.round(result.earning.rate * 100)}% от ${money(result.earning.kredit)}`}
                  {!result.dry_run && today != null && ` · за сегодня ${money(today)}`}
                </div>
              </div>
            )}

            {result.warnings.map((w) => (
              <p key={w} className="emp-scan-msg emp-scan-msg--warn">{w}</p>
            ))}
            {result.dry_run && (
              <ol className="emp-scan-writes">
                {result.writes.map((w, i) => (
                  <li key={`${w.table}-${i}`} className="emp-scan-write">
                    <div className="emp-scan-write__head">
                      <b>{w.label}</b>
                      <span>{w.table} · {OP_LABELS[w.op] || w.op}</span>
                    </div>
                    <dl className="emp-scan-write__fields">
                      {Object.entries({ ...(w.key || {}), ...w.fields }).map(([k, v]) => (
                        <div key={k}>
                          <dt>{k}</dt>
                          <dd>{valueText(v)}</dd>
                        </div>
                      ))}
                    </dl>
                    {w.note && <div className="emp-scan-write__note">{w.note}</div>}
                  </li>
                ))}
              </ol>
            )}
          </section>
          {streak && canScan && !result.dry_run ? (
            <p className="emp-scan-next">Камера откроется для следующей бирки…</p>
          ) : (
            <button
              type="button"
              className="btn btn--primary emp-scan-go"
              onClick={() => {
                reset();
                if (streak) openCamera();
              }}
            >
              Сканировать следующую
            </button>
          )}
        </div>
      )}

      {log.length > 0 && (
        <section className="emp-scan-log" aria-label="Отмечено за эту смену">
          <div className="emp-salary-section__title">Отмечено сейчас</div>
          {log.map((row) => (
            <div key={row.key} className="emp-scan-log__row">
              <span className="emp-scan-log__time">{row.time}</span>
              <span className="emp-scan-log__what">
                {ACTIONS[row.action].done} · {row.title}
                <small>{row.docNum}</small>
              </span>
              <span className="emp-scan-log__sum">{row.salary != null ? `+${money(row.salary)}` : ''}</span>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
