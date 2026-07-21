import { useState } from 'react';
import { Scan, Upload, User, Phone, Calendar, Clock, Ruler, X } from 'lucide-react';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';
import Modal from '../components/Modal.jsx';

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

function ViewThumb({ src, alt, label, onOpen }) {
  return (
    <div>
      <button
        type="button"
        onClick={() => onOpen(src, alt)}
        className="block w-full cursor-zoom-in"
        title="Открыть в полном размере"
      >
        <img src={src} alt={alt} className="w-full rounded border border-[color:var(--color-border)] hover:opacity-80 transition-opacity" />
      </button>
      <div className="text-center text-xs text-[color:var(--color-text-muted)] mt-1">{label}</div>
    </div>
  );
}

function FootCard({ foot, index, onOpenImage }) {
  return (
    <div className="app-card p-4 space-y-3">
      <h3 className="font-semibold flex items-center gap-2">
        <Ruler size={16} /> Стопа {index + 1}
      </h3>
      <div className="grid grid-cols-3 gap-3 text-center">
        <div>
          <div className="text-xl font-bold">{foot.length_mm}</div>
          <div className="text-xs text-[color:var(--color-text-muted)]">длина, мм</div>
        </div>
        <div>
          <div className="text-xl font-bold">{foot.width_mm}</div>
          <div className="text-xs text-[color:var(--color-text-muted)]">ширина, мм</div>
        </div>
        <div>
          <div className="text-xl font-bold">{foot.height_mm}</div>
          <div className="text-xs text-[color:var(--color-text-muted)]">высота, мм</div>
        </div>
      </div>
      <div className="text-xs text-[color:var(--color-text-muted)]">
        {foot.point_count.toLocaleString('ru-RU')} точек облака
      </div>
      <div className="grid grid-cols-3 gap-2">
        <ViewThumb src={foot.views.top} alt={`Стопа ${index + 1} — вид сверху`} label="сверху" onOpen={onOpenImage} />
        <ViewThumb src={foot.views.side} alt={`Стопа ${index + 1} — вид сбоку`} label="сбоку" onOpen={onOpenImage} />
        <ViewThumb src={foot.views.front} alt={`Стопа ${index + 1} — вид спереди`} label="спереди" onOpen={onOpenImage} />
      </div>
    </div>
  );
}

export default function Scanner3D() {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const [lightbox, setLightbox] = useState(null); // { src, alt } | null

  async function handleFile(file) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.scm')) {
      toast('Ожидается файл .scm', 'error');
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
      <h2 className="flex items-center gap-2 text-2xl font-semibold">
        <Scan size={24} /> 3D сканер
      </h2>
      <p className="text-sm text-[color:var(--color-text-muted)]">
        Загрузите файл скана стопы (.scm) — покажем метаданные скана, замеры (длина/ширина/высота) и визуализацию.
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
        <div className="font-medium">Перетащите файл .scm сюда или нажмите, чтобы выбрать</div>
        <input
          type="file"
          accept=".scm"
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
            <div className="grid gap-4 lg:grid-cols-2">
              {result.feet.map((foot, i) => (
                <FootCard key={i} foot={foot} index={i} onOpenImage={(src, alt) => setLightbox({ src, alt })} />
              ))}
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
