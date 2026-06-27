import { Download } from 'lucide-react';
import api from '../api';

export default function Reports() {
  async function downloadReport() {
    try {
      const res = await api.get('salary/report', { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'report.pdf');
      document.body.appendChild(link);
      link.click();
    } catch (err) {
      console.error(err);
    }
  }

  return (
    <div className="space-y-6 max-w-3xl mx-auto">
      <h2 className="text-2xl font-semibold tracking-tight text-[color:var(--color-text)] flex items-center gap-2">
        <Download size={24} /> Отчёты
      </h2>
      <div className="app-card p-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="font-medium">Зарплатный отчёт</div>
          <div className="text-sm text-[color:var(--color-text-muted)]">
            Сводный PDF по расчёту заработной платы.
          </div>
        </div>
        <button onClick={downloadReport} className="btn btn--primary flex items-center gap-2 shrink-0">
          <Download size={16} /> Скачать отчёт
        </button>
      </div>
    </div>
  );
}




