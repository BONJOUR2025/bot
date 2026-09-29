/** Кому и сколько по услуге из отчёта мастеров.
 *
 *  Обычно вся зарплата — мастеру выхода (out_description). Если старший
 *  мастер поделил услугу, бэкенд кладёт в строку `split` — доли с суммой и
 *  зарплатой каждого; тогда раскладываем по ним. Итог по услуге тот же. */
export function salaryParts(r) {
  if (r.master_salary == null) return [];
  if (Array.isArray(r.split) && r.split.length) {
    return r.split.map((p) => ({
      master: p.master || p.name || '—',
      salary: Number(p.salary) || 0,
      kredit: Number(p.kredit) || 0,
      share: Number(p.share) || 0,
    }));
  }
  return [{
    master: r.out_description || r.description || '—',
    salary: Number(r.master_salary) || 0,
    kredit: Number(r.kredit) || 0,
    share: 1,
  }];
}
