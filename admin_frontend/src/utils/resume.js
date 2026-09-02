/** Подписи к анкете резюме с площадки.
 *
 *  Живут отдельно от страниц, потому что нужны в двух местах сразу: в
 *  карточке кандидата и на экране «Прозвона», где та же строка отвечает на
 *  «звонить или нет» до того, как рекрутер снял трубку.
 */

/** Стаж в месяцах → «3 г. 10 мес.». Пустой стаж даёт пустую строку, а не «0 мес». */
export function experienceLabel(months) {
  if (!months) return '';
  const y = Math.floor(months / 12);
  const m = months % 12;
  return [y ? `${y} г.` : '', m ? `${m} мес.` : ''].filter(Boolean).join(' ');
}

/** Ожидания по зарплате → «75 000 ₽». */
export function salaryLabel(salary) {
  if (!salary?.amount) return '';
  const cur = { RUR: '₽', USD: '$', EUR: '€' }[salary.currency] || salary.currency || '';
  return `${Number(salary.amount).toLocaleString('ru-RU')} ${cur}`.trim();
}

/** Одна строка про кандидата: должность · стаж · ожидания. */
export function resumeHeadline(profile) {
  if (!profile) return '';
  return [profile.title, experienceLabel(profile.total_months), salaryLabel(profile.salary)]
    .filter(Boolean).join(' · ');
}

/** Вердикт ИИ: подпись и тон. null — если сводки нет или вердикта в ней нет. */
export function verdictBadge(profile) {
  return {
    invite:  { label: 'звонить',     tone: 'bg-emerald-100 text-emerald-800 border-emerald-200' },
    reserve: { label: 'в резерв',    tone: 'bg-amber-100 text-amber-800 border-amber-200' },
    reject:  { label: 'не подходит', tone: 'bg-red-100 text-red-700 border-red-200' },
  }[profile?.recommendation] || null;
}
