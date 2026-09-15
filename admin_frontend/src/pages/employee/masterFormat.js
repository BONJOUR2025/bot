/** Общие мелочи экранов мастера (Заработок, В работе, лимит аванса). */

export function money(n) {
  return Math.round(Number(n) || 0).toLocaleString('ru-RU') + ' ₽';
}

/** В названиях услуг Агбиса после «***» идёт приписка для клиента
 *  («ВНИМАНИЕ!!! Окончательная стоимость…») — мастеру она только мешает. */
export function serviceTitle(name) {
  return String(name || '').split('***')[0].trim() || '—';
}

/** Текст ошибки для /masters/me/*: 503/504 сервер уже формулирует по-русски. */
export function masterErrorText(err) {
  const status = err?.response?.status;
  const detail = err?.response?.data?.detail;
  if (status === 404) {
    return 'Раздел доступен только мастерам. Если вы мастер — попросите руководителя проставить в вашей карточке код Агбис.';
  }
  if ((status === 503 || status === 504) && typeof detail === 'string') {
    return detail;
  }
  return 'Не удалось загрузить данные. Попробуйте ещё раз.';
}
