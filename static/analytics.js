async function loadSales() {
  try {
    const res = await axios.get('/api/analytics/sales');
    const d = res.data;
    const rows = [
      ['💸 Сумма по ремонту', `${d.repair_sum} ₽`],
      ['🔧 Кол-во оказанных услуг', `${d.repair_count} штук`],
      ['🧴 Сумма по косметике', `${d.cosmetics_sum} ₽`],
      ['📦 Кол-во проданных товаров', `${d.cosmetics_count} штук`],
    ];
    const tbody = document.getElementById('sales-data');
    tbody.innerHTML = rows.map(r => `<tr class='border-t'><td class='p-2'>${r[0]}</td><td class='p-2'>${r[1]}</td></tr>`).join('');
    document.getElementById('sales-updated').textContent = `Обновлено: ${new Date(d.updated_at).toLocaleString('ru-RU')}`;
  } catch (err) {
    console.error(err);
  }
}

async function refreshSales() {
  await axios.post('/api/analytics/sales/refresh');
  await loadSales();
}

window.onload = loadSales;
