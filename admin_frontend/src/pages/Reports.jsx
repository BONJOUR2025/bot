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
      <h2 className="text-2xl font-semibold tracking-tight text-gray-800 flex items-center gap-2">
        <Download size={24} /> Отчёты
      </h2>
      <button onClick={downloadReport} className="btn">
        📄 Скачать отчёт
      </button>
    </div>
  );
}




