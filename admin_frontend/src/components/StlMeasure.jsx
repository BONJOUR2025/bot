import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Canvas } from '@react-three/fiber';
import { Html, Line, OrbitControls } from '@react-three/drei';
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js';
import * as THREE from 'three';
import { extractStlColors } from '../utils/stlColor.js';
import {
  Upload, Trash2, Ruler, Spline, MoveUpRight, CornerDownRight,
  MousePointerClick, Eye, EyeOff, RotateCcw,
} from 'lucide-react';

function useStl(file) {
  const [state, setState] = useState({ geometry: null, note: null, error: null, loading: false });
  useEffect(() => {
    if (!file) { setState({ geometry: null, note: null, error: null, loading: false }); return undefined; }
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));
    file.arrayBuffer().then((buffer) => {
      if (cancelled) return;
      try {
        const geometry = new STLLoader().parse(buffer);
        const { colors, note } = extractStlColors(buffer);
        if (colors && colors.length === geometry.getAttribute('position').count * 3) {
          geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
        }
        geometry.computeVertexNormals();
        geometry.computeBoundingBox();
        setState({ geometry, note, error: null, loading: false });
      } catch (err) {
        setState({ geometry: null, note: null, error: String(err), loading: false });
      }
    }).catch((err) => {
      if (!cancelled) setState({ geometry: null, note: null, error: String(err), loading: false });
    });
    return () => { cancelled = true; };
  }, [file]);
  return state;
}

// ---------------------------------------------------------------------------
// Geometry helpers. Distances are plain Euclidean in the file's own units
// (these scans are in mm), so they survive the "move to origin" toggle -- only
// the displayed coordinates shift, never a measurement.
// ---------------------------------------------------------------------------

const v3 = (p) => new THREE.Vector3(p[0], p[1], p[2]);
const dist = (a, b) => v3(a).distanceTo(v3(b));

function polylineLength(points) {
  let total = 0;
  for (let i = 1; i < points.length; i += 1) total += dist(points[i - 1], points[i]);
  return total;
}

/** Catmull-Rom through the placed points, sampled finely. A curve through the
 * same points is always longer than the chords between them -- both numbers are
 * shown so it is clear which one is being read. */
function splineLength(points, samples = 64) {
  if (points.length < 3) return null;
  const curve = new THREE.CatmullRomCurve3(points.map(v3));
  const pts = curve.getPoints(samples * (points.length - 1));
  let total = 0;
  for (let i = 1; i < pts.length; i += 1) total += pts[i - 1].distanceTo(pts[i]);
  return { length: total, points: pts.map((p) => [p.x, p.y, p.z]) };
}

/** Foot of the perpendicular from `p` onto the infinite line through a,b. */
function footOnLine(p, a, b) {
  const A = v3(a); const B = v3(b); const P = v3(p);
  const ab = B.clone().sub(A);
  const t = P.clone().sub(A).dot(ab) / ab.lengthSq();
  return A.clone().add(ab.multiplyScalar(t));
}

const fmt = (n) => (Math.abs(n) >= 100 ? n.toFixed(1) : n.toFixed(2));
const fmtPt = (p) => `X ${fmt(p[0])}  Y ${fmt(p[1])}  Z ${fmt(p[2])}`;

// ---------------------------------------------------------------------------
// Scene
// ---------------------------------------------------------------------------

function Model({ geometry, useVertexColors, onPick }) {
  const down = useRef(null);
  return (
    <mesh
      geometry={geometry}
      onPointerDown={(e) => { down.current = { x: e.clientX, y: e.clientY }; }}
      onPointerUp={(e) => {
        const d = down.current;
        down.current = null;
        // Ignore the pointer-up that ends an orbit drag; only a near-stationary
        // click places a point.
        if (!d || Math.hypot(e.clientX - d.x, e.clientY - d.y) > 4) return;
        e.stopPropagation();
        onPick([e.point.x, e.point.y, e.point.z]);
      }}
    >
      <meshStandardMaterial
        vertexColors={useVertexColors}
        color={useVertexColors ? '#ffffff' : '#c9ced6'}
        roughness={0.75}
        metalness={0.02}
        side={THREE.DoubleSide}
      />
    </mesh>
  );
}

function Marker({ position, index, radius, showLabel, selected, onClick }) {
  return (
    <group position={position}>
      <mesh onClick={(e) => { e.stopPropagation(); onClick?.(); }}>
        <sphereGeometry args={[radius, 16, 16]} />
        <meshBasicMaterial color={selected ? '#f59e0b' : '#2563eb'} />
      </mesh>
      {showLabel && (
        <Html distanceFactor={radius * 260} style={{ pointerEvents: 'none' }}>
          <div style={{
            background: 'rgba(17,24,39,0.85)', color: '#fff', padding: '2px 6px',
            borderRadius: 4, fontSize: 11, whiteSpace: 'nowrap', transform: 'translate(8px,-50%)',
          }}>
            P{index + 1}
          </div>
        </Html>
      )}
    </group>
  );
}

function Scene({ geometry, useVertexColors, points, shapes, radius, showLabels, selected, onPick, onPickPoint }) {
  const centre = useMemo(() => {
    if (!geometry?.boundingBox) return [0, 0, 0];
    const c = new THREE.Vector3();
    geometry.boundingBox.getCenter(c);
    return [c.x, c.y, c.z];
  }, [geometry]);
  const size = useMemo(() => {
    if (!geometry?.boundingBox) return 100;
    const s = new THREE.Vector3();
    geometry.boundingBox.getSize(s);
    return Math.max(s.x, s.y, s.z) || 100;
  }, [geometry]);

  return (
    <>
      <ambientLight intensity={0.65} />
      <directionalLight position={[size, size, size * 1.5]} intensity={1.6} />
      <directionalLight position={[-size, -size * 0.5, size]} intensity={0.5} />

      <axesHelper args={[size * 0.9]} />
      <gridHelper args={[size * 2.4, 24, '#94a3b8', '#e2e8f0']} rotation={[Math.PI / 2, 0, 0]} />

      {geometry && (
        <Model geometry={geometry} useVertexColors={useVertexColors} onPick={onPick} />
      )}

      {points.map((p, i) => (
        <Marker key={p.id} position={p.pos} index={i} radius={radius} showLabel={showLabels}
                selected={selected.includes(p.id)} onClick={() => onPickPoint(p.id)} />
      ))}

      {shapes.map((s) => (
        <Line key={s.id} points={s.points} color={s.color} lineWidth={2}
              dashed={Boolean(s.dashed)} dashScale={size / 40} />
      ))}

      <OrbitControls makeDefault target={centre} enableDamping dampingFactor={0.12} />
    </>
  );
}

// ---------------------------------------------------------------------------

const TOOLS = [
  { key: 'point', label: 'Точка', icon: MousePointerClick, hint: 'Клик по модели — поставить точку и увидеть её координаты.' },
  { key: 'line', label: 'Прямая', icon: Ruler, hint: 'Выберите 2 точки — прямая между ними и расстояние по прямой.' },
  { key: 'curve', label: 'Кривая', icon: Spline, hint: 'Выберите 3 и более точек по порядку — длина по ломаной и по сглаженной кривой.' },
  { key: 'parallel', label: 'Параллель', icon: MoveUpRight, hint: 'Выберите 2 точки (базовая прямая), затем 3-ю — через неё пройдёт параллель. Показывается расстояние между прямыми.' },
  { key: 'perpendicular', label: 'Перпендикуляр', icon: CornerDownRight, hint: 'Выберите 2 точки (базовая прямая), затем 3-ю — из неё опустится перпендикуляр. Показывается его длина.' },
];

let nextId = 1;
const newId = () => `id${nextId++}`;

export default function StlMeasure() {
  const [file, setFile] = useState(null);
  const { geometry, note, error, loading } = useStl(file);

  const [tool, setTool] = useState('point');
  const [points, setPoints] = useState([]);       // {id, pos:[x,y,z]}
  const [selected, setSelected] = useState([]);   // ids, in click order
  const [results, setResults] = useState([]);     // finished measurements
  const [showLabels, setShowLabels] = useState(true);
  const [toOrigin, setToOrigin] = useState(false);

  const size = useMemo(() => {
    if (!geometry?.boundingBox) return 100;
    const s = new THREE.Vector3();
    geometry.boundingBox.getSize(s);
    return Math.max(s.x, s.y, s.z) || 100;
  }, [geometry]);
  const markerRadius = size * 0.006;

  // Displayed coordinates only: every measurement is a distance, which a
  // translation cannot change.
  const originShift = useMemo(() => {
    if (!toOrigin || !geometry?.boundingBox) return [0, 0, 0];
    const m = geometry.boundingBox.min;
    return [m.x, m.y, m.z];
  }, [toOrigin, geometry]);
  const shown = useCallback(
    (p) => [p[0] - originShift[0], p[1] - originShift[1], p[2] - originShift[2]],
    [originShift],
  );

  const reset = useCallback(() => { setPoints([]); setSelected([]); setResults([]); }, []);
  useEffect(() => { reset(); }, [geometry, reset]);

  const byId = useCallback((id) => points.find((p) => p.id === id), [points]);

  const addPoint = useCallback((pos) => {
    const p = { id: newId(), pos };
    setPoints((prev) => [...prev, p]);
    if (tool !== 'point') setSelected((prev) => [...prev, p.id]);
  }, [tool]);

  const togglePoint = useCallback((id) => {
    if (tool === 'point') return;
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }, [tool]);

  // --- build the measurement once enough points are selected ---------------
  const commit = useCallback(() => {
    const pts = selected.map(byId).filter(Boolean).map((p) => p.pos);
    if (tool === 'line' && pts.length >= 2) {
      const [a, b] = pts;
      setResults((r) => [...r, {
        id: newId(), kind: 'Прямая', color: '#dc2626',
        value: dist(a, b), unit: 'мм', label: 'длина',
        shape: { points: [a, b], color: '#dc2626' },
      }]);
    } else if (tool === 'curve' && pts.length >= 3) {
      const chord = polylineLength(pts);
      const spline = splineLength(pts);
      setResults((r) => [...r, {
        id: newId(), kind: `Кривая (${pts.length} точек)`, color: '#7c3aed',
        value: chord, unit: 'мм', label: 'по ломаной',
        extra: spline ? `по сглаженной кривой ${fmt(spline.length)} мм` : null,
        segments: pts.slice(1).map((p, i) => dist(pts[i], p)),
        shape: { points: spline ? spline.points : pts, color: '#7c3aed' },
      }]);
    } else if (tool === 'parallel' && pts.length >= 3) {
      const [a, b, p] = pts;
      const dir = v3(b).sub(v3(a));
      const half = dir.clone().normalize().multiplyScalar(dir.length() / 2);
      const mid = v3(p);
      const s1 = mid.clone().sub(half); const s2 = mid.clone().add(half);
      const foot = footOnLine(p, a, b);
      setResults((r) => [...r, {
        id: newId(), kind: 'Параллель', color: '#059669',
        value: v3(p).distanceTo(foot), unit: 'мм', label: 'расстояние между прямыми',
        shapes: [
          { points: [a, b], color: '#059669' },
          { points: [[s1.x, s1.y, s1.z], [s2.x, s2.y, s2.z]], color: '#059669' },
          { points: [p, [foot.x, foot.y, foot.z]], color: '#059669', dashed: true },
        ],
      }]);
    } else if (tool === 'perpendicular' && pts.length >= 3) {
      const [a, b, p] = pts;
      const foot = footOnLine(p, a, b);
      setResults((r) => [...r, {
        id: newId(), kind: 'Перпендикуляр', color: '#ea580c',
        value: v3(p).distanceTo(foot), unit: 'мм', label: 'длина перпендикуляра',
        extra: `основание: ${fmtPt(shown([foot.x, foot.y, foot.z]))}`,
        shapes: [
          { points: [a, b], color: '#ea580c' },
          { points: [p, [foot.x, foot.y, foot.z]], color: '#ea580c' },
        ],
      }]);
    } else {
      return;
    }
    setSelected([]);
  }, [tool, selected, byId, shown]);

  const need = { line: 2, curve: 3, parallel: 3, perpendicular: 3 }[tool] || 0;
  const canCommit = need > 0 && selected.length >= need;

  // Straight lines and perpendiculars have a fixed point count, so they finish
  // themselves. A curve does not -- the user decides where it ends.
  useEffect(() => {
    if ((tool === 'line' && selected.length === 2)
      || ((tool === 'parallel' || tool === 'perpendicular') && selected.length === 3)) {
      commit();
    }
  }, [tool, selected, commit]);

  const shapes = useMemo(() => {
    const out = [];
    results.forEach((r) => {
      if (r.shape) out.push({ id: `${r.id}s`, ...r.shape });
      (r.shapes || []).forEach((s, i) => out.push({ id: `${r.id}s${i}`, ...s }));
    });
    // preview of the selection in progress
    const sel = selected.map(byId).filter(Boolean).map((p) => p.pos);
    if (sel.length >= 2) out.push({ id: 'preview', points: sel, color: '#f59e0b', dashed: true });
    return out;
  }, [results, selected, byId]);

  const activeTool = TOOLS.find((t) => t.key === tool);

  return (
    <div className="space-y-3">
      <div className="app-card p-4 space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <label className="btn flex cursor-pointer items-center gap-1.5">
            <Upload size={16} /> {file ? 'Другой файл' : 'Загрузить .stl'}
            <input type="file" accept=".stl" className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] || null)} />
          </label>
          {file && <span className="truncate text-sm">{file.name}</span>}
          {loading && <span className="text-sm text-[color:var(--color-text-muted)]">Читаю файл…</span>}
          {note && <span className="text-xs text-[color:var(--color-text-muted)]">({note})</span>}
        </div>
        {error && <p className="text-sm text-[color:var(--color-danger)]">Не удалось прочитать файл: {error}</p>}
        {geometry?.boundingBox && (
          <p className="text-xs text-[color:var(--color-text-muted)]">
            Габарит: {fmt(geometry.boundingBox.max.x - geometry.boundingBox.min.x)} ×{' '}
            {fmt(geometry.boundingBox.max.y - geometry.boundingBox.min.y)} ×{' '}
            {fmt(geometry.boundingBox.max.z - geometry.boundingBox.min.z)} мм ·{' '}
            {geometry.getAttribute('position').count / 3} треугольников
          </p>
        )}
      </div>

      {geometry && (
        <>
          <div className="app-card p-3 space-y-2">
            <div className="flex flex-wrap gap-1.5">
              {TOOLS.map((t) => {
                const Icon = t.icon;
                return (
                  <button key={t.key} type="button"
                    className={`btn flex items-center gap-1.5 text-sm ${tool === t.key ? 'btn-primary' : ''}`}
                    onClick={() => { setTool(t.key); setSelected([]); }}>
                    <Icon size={15} /> {t.label}
                  </button>
                );
              })}
              <div className="ml-auto flex gap-1.5">
                <button type="button" className="btn flex items-center gap-1.5 text-sm"
                        onClick={() => setShowLabels((v) => !v)}>
                  {showLabels ? <Eye size={15} /> : <EyeOff size={15} />} Подписи
                </button>
                <button type="button" className="btn flex items-center gap-1.5 text-sm" onClick={reset}>
                  <RotateCcw size={15} /> Сбросить
                </button>
              </div>
            </div>
            <p className="text-xs text-[color:var(--color-text-muted)]">{activeTool?.hint}</p>
            {need > 0 && (
              <div className="flex items-center gap-2 text-xs">
                <span className="text-[color:var(--color-text-muted)]">
                  Выбрано точек: {selected.length}{need ? ` / ${need}${tool === 'curve' ? '+' : ''}` : ''}
                </span>
                {tool === 'curve' && canCommit && (
                  <button type="button" className="btn btn-primary text-xs" onClick={commit}>
                    Замкнуть кривую и измерить
                  </button>
                )}
                {selected.length > 0 && (
                  <button type="button" className="btn text-xs" onClick={() => setSelected([])}>
                    Снять выделение
                  </button>
                )}
              </div>
            )}
          </div>

          <div className="app-card overflow-hidden" style={{ height: '60vh', minHeight: 380 }}>
            <Canvas camera={{ position: [size * 1.4, -size * 1.6, size * 1.2], fov: 45, near: size / 500, far: size * 40 }}>
              <color attach="background" args={['#f8fafc']} />
              <Scene
                geometry={geometry}
                useVertexColors={Boolean(geometry.getAttribute('color'))}
                points={points}
                shapes={shapes}
                radius={markerRadius}
                showLabels={showLabels}
                selected={selected}
                onPick={addPoint}
                onPickPoint={togglePoint}
              />
            </Canvas>
          </div>

          <div className="grid gap-3 lg:grid-cols-2">
            <div className="app-card p-3 space-y-2">
              <div className="flex items-center justify-between">
                <h4 className="text-sm font-semibold">Точки ({points.length})</h4>
                <label className="flex items-center gap-1.5 text-xs text-[color:var(--color-text-muted)]">
                  <input type="checkbox" checked={toOrigin} onChange={(e) => setToOrigin(e.target.checked)} />
                  от угла габарита
                </label>
              </div>
              {points.length === 0 ? (
                <p className="text-xs text-[color:var(--color-text-muted)]">
                  Кликните по модели, чтобы поставить точку.
                </p>
              ) : (
                <div className="max-h-56 space-y-1 overflow-y-auto">
                  {points.map((p, i) => (
                    <div key={p.id}
                      className={`flex items-center justify-between gap-2 rounded border px-2 py-1 text-xs ${
                        selected.includes(p.id)
                          ? 'border-amber-400 bg-amber-50'
                          : 'border-[color:var(--color-border)]'}`}>
                      <button type="button" className="flex-1 text-left font-mono"
                              onClick={() => togglePoint(p.id)}>
                        <span className="mr-2 font-semibold">P{i + 1}</span>{fmtPt(shown(p.pos))}
                      </button>
                      <button type="button" className="text-[color:var(--color-danger)]"
                        onClick={() => {
                          setPoints((prev) => prev.filter((x) => x.id !== p.id));
                          setSelected((prev) => prev.filter((x) => x !== p.id));
                        }}>
                        <Trash2 size={13} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="app-card p-3 space-y-2">
              <h4 className="text-sm font-semibold">Измерения ({results.length})</h4>
              {results.length === 0 ? (
                <p className="text-xs text-[color:var(--color-text-muted)]">
                  Выберите инструмент и отметьте точки — результат появится здесь.
                </p>
              ) : (
                <div className="max-h-56 space-y-1.5 overflow-y-auto">
                  {results.map((r) => (
                    <div key={r.id} className="rounded border border-[color:var(--color-border)] px-2 py-1.5 text-xs">
                      <div className="flex items-center justify-between gap-2">
                        <span className="flex items-center gap-1.5 font-medium">
                          <span className="inline-block h-2 w-2 rounded-full" style={{ background: r.color }} />
                          {r.kind}
                        </span>
                        <span className="flex items-center gap-2">
                          <span className="font-mono font-semibold">{fmt(r.value)} {r.unit}</span>
                          <button type="button" className="text-[color:var(--color-danger)]"
                                  onClick={() => setResults((prev) => prev.filter((x) => x.id !== r.id))}>
                            <Trash2 size={13} />
                          </button>
                        </span>
                      </div>
                      <div className="text-[color:var(--color-text-muted)]">{r.label}</div>
                      {r.extra && <div className="text-[color:var(--color-text-muted)]">{r.extra}</div>}
                      {r.segments && (
                        <div className="mt-1 font-mono text-[11px] text-[color:var(--color-text-muted)]">
                          {r.segments.map((s, i) => `${i + 1}→${i + 2}: ${fmt(s)}`).join('   ')}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
