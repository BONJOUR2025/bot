/** Выполнение плана продаж — кольцами.
 *
 *  Те же три числа, что в строках «Ремонт / Косметика / Обувь», но видно
 *  за секунду: сколько пройдено и сколько осталось до плана. Кольцо считается
 *  от плана, поэтому при перевыполнении оно замыкается и остаётся зелёным, а
 *  подпись показывает «+N ₽ сверх плана» — ради этого вопроса на экран и
 *  смотрят в конце месяца. */

const SIZE = 104;
const STROKE = 9;
const R = (SIZE - STROKE) / 2;
const C = 2 * Math.PI * R;

function money(n) {
  return Math.round(Number(n) || 0).toLocaleString('ru-RU') + ' ₽';
}

function Ring({ label, sales, plan }) {
  const done = Number(sales) || 0;
  const target = Number(plan) || 0;
  const share = target > 0 ? done / target : 0;
  const pct = target > 0 ? Math.round(share * 100) : null;
  const left = Math.max(0, target - done);
  const state = target === 0 ? 'none' : share >= 1 ? 'done' : share >= 0.8 ? 'close' : 'far';
  const dash = Math.min(1, share) * C;

  return (
    <div className="emp-ring">
      <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} role="img"
           aria-label={`${label}: ${money(done)} из ${money(target)}${pct != null ? `, ${pct}%` : ''}`}>
        <circle className="emp-ring__track" cx={SIZE / 2} cy={SIZE / 2} r={R} fill="none" strokeWidth={STROKE} />
        <circle
          className={`emp-ring__value emp-ring__value--${state}`}
          cx={SIZE / 2} cy={SIZE / 2} r={R} fill="none" strokeWidth={STROKE} strokeLinecap="round"
          strokeDasharray={`${dash} ${C}`}
          transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}
        />
        <text className="emp-ring__pct" x="50%" y="50%" dominantBaseline="central" textAnchor="middle">
          {pct != null ? `${pct}%` : '—'}
        </text>
      </svg>
      <div className="emp-ring__label">{label}</div>
      <div className="emp-ring__sub">
        {target === 0
          ? money(done)
          : left > 0
            ? `ещё ${money(left)}`
            : `+${money(done - target)} сверх`}
      </div>
    </div>
  );
}

export default function PlanRings({ payroll }) {
  const rows = [
    { label: 'Ремонт', sales: payroll.repair_sales, plan: payroll.repair_plan },
    { label: 'Косметика', sales: payroll.cosmetics_sales, plan: payroll.cosmetics_plan },
    { label: 'Обувь', sales: payroll.shoes_sales, plan: payroll.shoes_plan },
  ].filter((r) => (Number(r.plan) || 0) > 0 || (Number(r.sales) || 0) > 0);

  if (rows.length === 0) return null;

  const plan = rows.reduce((sum, r) => sum + (Number(r.plan) || 0), 0);
  const sales = rows.reduce((sum, r) => sum + (Number(r.sales) || 0), 0);
  const left = Math.max(0, plan - sales);
  // Сколько дней месяца осталось — чтобы «ещё 120 000 ₽» превратилось
  // в понятное «по 12 000 ₽ в день».
  const now = new Date();
  const daysLeft = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate() - now.getDate() + 1;

  return (
    <div className="emp-rings">
      <div className="emp-rings__row">
        {rows.map((r) => <Ring key={r.label} {...r} />)}
      </div>
      {plan > 0 && (
        <p className="emp-rings__total">
          {left > 0
            ? <>До общего плана {money(left)} — это {money(left / Math.max(1, daysLeft))} в день до конца месяца.</>
            : <>Общий план выполнен: {money(sales)} при плане {money(plan)}.</>}
        </p>
      )}
    </div>
  );
}
