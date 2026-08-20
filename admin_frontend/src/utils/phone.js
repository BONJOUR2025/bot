// Нормализация и форматирование телефонов.
//
// Номера приходят из Avito/HH/ручного ввода в разнобой: 79046393833,
// 89046393833, +7 (904) 639-38-33, 904-639-38-33 и т.п. Здесь приводим их к
// единому виду для показа и для ссылок (tel/Telegram/WhatsApp). Логика
// РФ-центрична (8→7, 10 цифр → +7), но не ломает иностранные номера.

// Только значащие цифры в канонической форме РФ:
//   8XXXXXXXXXX (11) → 7XXXXXXXXXX
//   XXXXXXXXXX  (10) → 7XXXXXXXXXX  (без кода страны)
//   иначе — как есть (иностранные/короткие/уже с 7).
export function phoneDigits(raw) {
  let d = String(raw ?? '').replace(/\D/g, '');
  if (!d) return '';
  if (d.length === 11 && d[0] === '8') d = '7' + d.slice(1);
  else if (d.length === 10) d = '7' + d;
  return d;
}

// E.164 для ссылок: '+7XXXXXXXXXX'. null, если это явно не номер (мало цифр).
export function phoneE164(raw) {
  const d = phoneDigits(raw);
  return d.length >= 7 ? '+' + d : null;
}

// Красивый показ. РФ 11-значный → '+7 904 639-38-33'. Иностранный/иной длины —
// хотя бы с ведущим '+'. Совсем не номер — исходная строка без изменений.
export function formatPhone(raw) {
  const d = phoneDigits(raw);
  if (d.length === 11 && d[0] === '7') {
    return `+7 ${d.slice(1, 4)} ${d.slice(4, 7)}-${d.slice(7, 9)}-${d.slice(9, 11)}`;
  }
  if (d.length >= 7) return '+' + d;
  return String(raw ?? '');
}

// href-ы. Возвращают null, если номера нет — тогда ссылку просто не рендерим.
export function telHref(raw) {
  const e = phoneE164(raw);
  return e ? `tel:${e}` : null;
}
export function tgHref(raw) {
  const d = phoneDigits(raw);
  return d.length >= 7 ? `https://t.me/+${d}` : null;
}
export function waHref(raw) {
  const d = phoneDigits(raw);
  return d.length >= 7 ? `https://wa.me/${d}` : null;
}
