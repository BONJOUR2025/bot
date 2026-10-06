import { money } from './masterFormat.js';

/** Оплата заказа клиентом (app/services/order_payment.py).
 *
 *  В списках — маленькая метка обычным шрифтом в строке под услугой
 *  («… · предоплата 3 000 ₽»), а не ещё одна крупная плашка рядом со
 *  сроком: на телефоне две плашки шли друг под другом, и оплата спорила за
 *  внимание с «Просрочен». «Оплачен» — спокойным цветом: таких больше
 *  половины. В карточке заказа — плашка в шапке (variant="badge") и строка
 *  с суммами (paymentText). */
export default function PaymentBadge({ p, variant = 'tag' }) {
  if (!p) return null;
  const tone = p.state === 'unpaid' ? 'unpaid' : p.state === 'prepaid' ? 'prepaid' : 'paid';
  const label = p.state === 'unpaid'
    ? 'не оплачен'
    : p.state === 'prepaid' ? `предоплата ${money(p.paid)}` : 'оплачен';
  const title = p.state === 'prepaid'
    ? `Внесено ${money(p.paid)} из ${money(p.total)}, к доплате ${money(p.left)}`
    : p.state === 'unpaid' ? `К оплате ${money(p.total)}` : `Оплачено ${money(p.paid)}`;
  if (variant === 'badge') {
    const cls = { unpaid: 'badge--error', prepaid: 'badge--warning', paid: 'badge--success' }[tone];
    return <span className={`badge ${cls}`} title={title}>{label[0].toUpperCase() + label.slice(1)}</span>;
  }
  return <span className={`pay-tag pay-tag--${tone}`} title={title}>{label}</span>;
}

/** Строка для карточки заказа: сколько внесено и сколько осталось. */
export function paymentText(p) {
  if (!p) return '—';
  if (p.state === 'unpaid') return `не оплачен, к оплате ${money(p.total)}`;
  if (p.state === 'prepaid') return `предоплата ${money(p.paid)} из ${money(p.total)}, к доплате ${money(p.left)}`;
  return `оплачен полностью, ${money(p.paid)}`;
}
