import { useState } from 'react';
import { Scan, Upload, User, Phone, Calendar, Clock, X, Library, ArrowLeftRight } from 'lucide-react';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';
import Modal from '../components/Modal.jsx';
import { Tabs } from '../components/ui/SalaryUI.jsx';
import { FootCard } from '../components/FootScanCard.jsx';
import LastLibrary from './LastLibrary.jsx';

function MetaRow({ icon: Icon, label, value }) {
  if (!value) return null;
  return (
    <div className="flex items-center gap-2 text-sm">
      <Icon size={14} className="text-[color:var(--color-text-muted)] shrink-0" />
      <span className="text-[color:var(--color-text-muted)]">{label}:</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}

function ScanTab() {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const [lightbox, setLightbox] = useState(null); // { src, alt } | null

  async function handleFile(file) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.stl')) {
      toast('Ожидается файл .stl', 'error');
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await api.post('scanner/parse', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setResult(res.data);
      if (!res.data.feet.length) {
        toast('Файл разобран, но стопы в нём не найдены', 'error');
      }
    } catch (err) {
      console.error(err);
      toast(err.response?.data?.detail || 'Не удалось разобрать файл', 'error');
    } finally {
      setLoading(false);
    }
  }

  const meta = result?.metadata;

  return (
    <div className="space-y-6">
      <p className="text-sm text-[color:var(--color-text-muted)]">
        Загрузите файл скана стопы (.stl) — покажем метаданные скана, замеры (длина/ширина/высота) и визуализацию.
        Формат не документирован производителем сканера, поэтому данные извлекаются эвристически — сверяйте
        результат со здравым смыслом, а не считайте это метрологически точным измерением.
      </p>

      <label
        className={`app-card flex flex-col items-center justify-center gap-2 border-2 border-dashed p-10 text-center cursor-pointer transition-colors ${
          dragOver ? 'border-[color:var(--color-primary)] bg-[color:var(--color-bg-subtle)]' : 'border-[color:var(--color-border)]'
        }`}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          handleFile(e.dataTransfer.files?.[0]);
        }}
      >
        <Upload size={28} className="text-[color:var(--color-text-muted)]" />
        <div className="font-medium">Перетащите файл .stl сюда или нажмите, чтобы выбрать</div>
        <input
          type="file"
          accept=".stl"
          className="hidden"
          onChange={(e) => handleFile(e.target.files?.[0])}
        />
      </label>

      {loading && <p className="text-[color:var(--color-text-muted)]">Разбираю файл…</p>}

      {result && (
        <div className="space-y-6">
          <div className="app-card p-4 space-y-2">
            <h3 className="font-semibold mb-1">Метаданные скана</h3>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              <MetaRow icon={User} label="Клиент" value={meta.name} />
              <MetaRow icon={Phone} label="Телефон" value={meta.phone} />
              <MetaRow icon={Calendar} label="Дата скана" value={meta.scan_date} />
              <MetaRow icon={Clock} label="Время скана" value={meta.scan_time} />
              <MetaRow icon={Calendar} label="Дата рождения" value={meta.birth_date} />
              <MetaRow icon={Scan} label="ID скана" value={meta.scan_id} />
            </div>
            {!meta.name && !meta.phone && (
              <p className="text-xs text-[color:var(--color-text-muted)] mt-2">
                Метаданные не распознаны — либо файл от другой версии ПО сканера, либо повреждён.
              </p>
            )}
          </div>

          {result.feet.length === 0 ? (
            <div className="rounded border border-dashed border-[color:var(--color-border)] bg-[color:var(--color-surface)] p-6 text-center text-[color:var(--color-text-muted)]">
              Геометрия стопы не найдена в файле — либо формат отличается от ожидаемого, либо в файле нет данных скана.
            </div>
          ) : (
            <div className="space-y-2">
              {result.feet.length === 2 && (
                <div className="flex justify-end">
                  <button
                    type="button"
                    className="btn flex items-center gap-1.5 text-sm"
                    title="Если стороны определились неверно"
                    onClick={() => setResult(r => ({
                      ...r,
                      feet: [
                        { ...r.feet[0], side: r.feet[1].side },
                        { ...r.feet[1], side: r.feet[0].side },
                      ],
                    }))}
                  >
                    <ArrowLeftRight size={14} /> Поменять стороны местами
                  </button>
                </div>
              )}
              <div className="grid gap-4 lg:grid-cols-2">
                {result.feet.map((foot, i) => (
                  <FootCard key={i} foot={foot} index={i} onOpenImage={(src, alt) => setLightbox({ src, alt })} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <Modal isOpen={!!lightbox} onClose={() => setLightbox(null)}>
        {/* w-fit + max-w-[95vw]: size the card to the image's own aspect
            ratio instead of forcing it to a fixed wide box — these renders
            are portrait for "top" and landscape for "side"/"front", and a
            forced w-full on the <img> below previously stretched images
            *up* past their natural size to fill a fixed-width card, which
            could push the display height past modal-card's max-height and
            get silently clipped by its overflow-y:auto (no visible
            scrollbar in a screenshot) — max-h-[80vh] + max-w-full on the
            img itself means it only ever shrinks to fit, never stretches. */}
        <div className="modal-card w-fit max-w-[95vw] sm:mx-4 p-3">
          <div className="flex justify-end mb-1">
            <button type="button" className="btn" onClick={() => setLightbox(null)}>
              <X size={16} />
            </button>
          </div>
          {lightbox && (
            <img
              src={lightbox.src}
              alt={lightbox.alt}
              className="block max-w-full max-h-[80vh] mx-auto rounded"
            />
          )}
        </div>
      </Modal>
    </div>
  );
}

export default function Scanner3D() {
  const [tab, setTab] = useState('scan');
  return (
    <div className="space-y-6">
      <h2 className="flex items-center gap-2 text-2xl font-semibold">
        <Scan size={24} /> 3D сканер
      </h2>
      <Tabs
        tabs={[
          { key: 'scan', label: 'Сканер', icon: <Scan size={14} /> },
          { key: 'library', label: 'Библиотека колодок', icon: <Library size={14} /> },
        ]}
        active={tab}
        onChange={setTab}
      />
      {tab === 'scan' ? <ScanTab /> : <LastLibrary />}
    </div>
  );
}
