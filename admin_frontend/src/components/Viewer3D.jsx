import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Canvas, useThree } from '@react-three/fiber';
import { Environment, Lightformer, OrbitControls, Html } from '@react-three/drei';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import * as THREE from 'three';
import { Download, Maximize2, Minimize2, RotateCcw } from 'lucide-react';
import { useViewport } from '../providers/ViewportProvider.jsx';

// Geometry arrives as base64-encoded GLB (see app/services/mesh_visualization_service.py —
// same "data URI" convention this codebase already uses for PNG overlays elsewhere),
// not a URL, so we parse it directly rather than using drei's useGLTF (which expects a URL).
function base64ToArrayBuffer(base64) {
  const binary = window.atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

function useGlbObject(base64) {
  const [object, setObject] = useState(null);
  useEffect(() => {
    if (!base64) { setObject(null); return undefined; }
    let cancelled = false;
    const loader = new GLTFLoader();
    try {
      loader.parse(base64ToArrayBuffer(base64), '', (gltf) => {
        if (!cancelled) setObject(gltf.scene);
      }, (err) => console.error('GLB parse failed', err));
    } catch (err) {
      console.error('GLB decode failed', err);
    }
    return () => { cancelled = true; };
  }, [base64]);
  return object;
}

// A "frosted glass" look (MeshPhysicalMaterial's transmission/thickness/ior)
// rather than the flat MeshStandardMaterial this used before -- transmission
// needs the renderer's own transmission pass, which three.js provides out of
// the box without requiring an environment map, though the <Environment>
// rig added below still meaningfully improves how the specular highlights
// read. When the geometry itself carries per-vertex heatmap colors (see
// app/services/surface_heatmap.py), `vertexColors` is enabled and the
// material's own `color` is left white so it doesn't tint/darken them --
// three.js multiplies vertex color by material color, so anything but white
// here would dull the gradient.
function SurfaceLayer({ base64, color, opacity, glass, onBounds }) {
  const object = useGlbObject(base64);
  const prepared = useMemo(() => {
    if (!object) return null;
    const clone = object.clone(true);
    clone.traverse((child) => {
      if (child.isMesh) {
        const hasVertexColors = Boolean(child.geometry?.attributes?.color);
        child.material = glass
          ? new THREE.MeshPhysicalMaterial({
            color: hasVertexColors ? 0xffffff : color,
            vertexColors: hasVertexColors,
            transparent: true, opacity, side: THREE.DoubleSide,
            depthWrite: opacity > 0.9,
            transmission: 0.55, thickness: 12, roughness: 0.2, ior: 1.4,
            clearcoat: 0.5, clearcoatRoughness: 0.25, envMapIntensity: 1.2,
          })
          : new THREE.MeshStandardMaterial({
            color: hasVertexColors ? 0xffffff : color,
            vertexColors: hasVertexColors,
            transparent: true, opacity, side: THREE.DoubleSide,
            depthWrite: opacity > 0.9,
          });
      }
    });
    return clone;
  }, [object, color, opacity, glass]);

  useEffect(() => {
    if (prepared && onBounds) onBounds(new THREE.Box3().setFromObject(prepared));
  }, [prepared, onBounds]);

  if (!prepared) return null;
  return <primitive object={prepared} />;
}

function PatchLayer({ patch }) {
  const object = useGlbObject(patch.mesh_glb_base64);
  const prepared = useMemo(() => {
    if (!object) return null;
    const clone = object.clone(true);
    clone.traverse((child) => {
      if (child.isMesh) {
        child.material = new THREE.MeshStandardMaterial({
          color: patch.color, transparent: true, opacity: 0.9, side: THREE.DoubleSide,
        });
      }
    });
    return clone;
  }, [object, patch.color]);
  if (!prepared) return null;
  return <primitive object={prepared} />;
}

// Callout card + a thin leader line from the surface anchor point to the
// floating label, closer to the reference "labeled medical illustration"
// style than the old plain bordered chip. `anchor` is optional (the
// heel/toe measurement lines reuse this same component with just a
// position, no separate surface point to connect from).
function LabelLayer({ label }) {
  const lineGeometry = useMemo(() => {
    if (!label.anchor) return null;
    const g = new THREE.BufferGeometry();
    g.setFromPoints([new THREE.Vector3(...label.anchor), new THREE.Vector3(...label.position)]);
    return g;
  }, [label.anchor, label.position]);

  return (
    <>
      {lineGeometry && (
        <line geometry={lineGeometry}>
          <lineBasicMaterial color={label.color || '#ffffff'} transparent opacity={0.8} />
        </line>
      )}
      {label.anchor && (
        <mesh position={label.anchor}>
          <sphereGeometry args={[1.2, 12, 12]} />
          <meshBasicMaterial color={label.color || '#ffffff'} />
        </mesh>
      )}
      <Html position={label.position} center style={{ pointerEvents: 'none' }}>
        <div
          style={{
            background: 'rgba(8,12,24,0.85)', color: '#f5f7fa',
            padding: '5px 10px', borderRadius: 8, fontSize: 11, whiteSpace: 'nowrap',
            borderLeft: `3px solid ${label.color || '#ffffff'}`,
            boxShadow: '0 3px 12px rgba(0,0,0,0.45)',
          }}
        >
          <span style={{ fontWeight: 600, color: label.color || '#ffffff' }}>{label.text}</span>
        </div>
      </Html>
    </>
  );
}

// last_bottom_curve: a thin polyline along the last's own sole profile —
// rendered as a tube (drei-less, plain three.js) so it stays visible at
// typical camera distances instead of a 1px Line.
function BottomCurveLayer({ points, color }) {
  const geometry = useMemo(() => {
    if (!points || points.length < 2) return null;
    const curve = new THREE.CatmullRomCurve3(points.map((p) => new THREE.Vector3(...p)));
    return new THREE.TubeGeometry(curve, Math.max(points.length, 2), 1.2, 6, false);
  }, [points]);
  if (!geometry) return null;
  return (
    <mesh geometry={geometry}>
      <meshStandardMaterial color={color} />
    </mesh>
  );
}

// pose_measurements: a heel-height / toe-spring dimension line (two points)
// with an mm label at the midpoint.
function MeasurementLineLayer({ line }) {
  const geometry = useMemo(() => {
    const g = new THREE.BufferGeometry();
    const pts = line.points.map((p) => new THREE.Vector3(...p));
    g.setFromPoints(pts);
    return g;
  }, [line]);
  const mid = useMemo(() => {
    const [a, b] = line.points;
    return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2];
  }, [line]);
  return (
    <>
      <line geometry={geometry}>
        <lineBasicMaterial color={line.color} linewidth={2} />
      </line>
      <LabelLayer label={{ text: line.label, position: mid, color: line.color }} />
    </>
  );
}

// Directions only -- CameraRig scales these by the scene's own bounding
// radius (computed from the loaded meshes), so this works for a last
// visualization regardless of the specific foot/last size.
//
// This codebase's mesh coordinate convention (stl_parser_service.py /
// scm_parser_service.py, consistent everywhere) is X = width, Y = length
// from the heel, Z = height above the ground -- NOT three.js's usual Y-up.
// The previous values here were written as if Y were "up" (top=[0,1,..],
// front/back=[0,0,±1]), which actually pointed "top" sideways along the
// foot's length and made "front"/"back" both look straight down from
// above/below -- exactly the "upside down / wrong angle" bug reported.
// Corrected so each preset points along the axis its name actually means
// in this data: top/bottom along Z, front (toe end) / back (heel end)
// along Y, side along X. Small (0.02-0.05) components on the two
// non-dominant axes keep the view a hair off pure-axis-aligned so
// lookAt()'s forward vector is never exactly parallel to camera.up (see
// below) -- an exact parallel there is a degenerate case three.js can't
// resolve into a stable orientation.
const CAMERA_DIRECTIONS = {
  iso: [0.9, 0.5, 0.8],
  top: [0.03, 0.03, 1],
  side: [1, 0.03, 0.03],
  front: [0.03, 1, 0.05],
  back: [0.03, -1, 0.05],
};

function CameraRig({ target, controlsRef, preset, resetKey }) {
  const { camera } = useThree();
  useEffect(() => {
    // The scene's true "up" is Z (height), not three.js's default Y -- set
    // once via the Canvas's own `camera={{ up: [0,0,1] }}` prop (applied
    // before OrbitControls ever mounts), NOT here. OrbitControls computes
    // an internal quaternion from `camera.up` exactly once, at construction
    // -- mutating `camera.up` again afterwards (as this effect used to do,
    // on every preset change) doesn't update that cached quaternion, it
    // just desyncs it from the camera's actual orientation. That mismatch
    // was the root cause of "drag-to-rotate and scroll-to-zoom do nothing":
    // OrbitControls' per-frame update() kept recomputing the camera pose
    // from its now-stale internal frame and overwriting whatever the user's
    // input had just done.
    if (!target) return;
    const dir = CAMERA_DIRECTIONS[preset] || CAMERA_DIRECTIONS.iso;
    const distance = target.radius * 2.2;
    camera.position.set(
      target.center.x + dir[0] * distance,
      target.center.y + dir[1] * distance,
      target.center.z + dir[2] * distance,
    );
    camera.lookAt(target.center.x, target.center.y, target.center.z);
    camera.updateProjectionMatrix();
    if (controlsRef.current) {
      controlsRef.current.target.set(target.center.x, target.center.y, target.center.z);
      controlsRef.current.update();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, preset, resetKey, camera]);
  return null;
}

const LAYER_LABELS = {
  foot: 'Стопа', last: 'Колодка', patches: 'Проблемные зоны', labels: 'Подписи',
  last_bottom_curve: 'Профиль следа колодки', pose_measurements: 'Размерные линии',
};
const PRESET_LABELS = { iso: 'Изо', top: 'Сверху', side: 'Сбоку', front: 'Спереди', back: 'Сзади' };

/** Interactive 3D overlay of a foot vs a last, with problem-zone patches —
 * `geometry` is the `visualization` object attached to a hybrid_v2
 * per-foot surface_result (only present when the match was requested with
 * include_geometry=true). See app/services/mesh_visualization_service.py
 * for the payload shape. */
export default function Viewer3D({ geometry, title }) {
  const [layers, setLayers] = useState({
    foot: true, last: true, patches: true, labels: true,
    last_bottom_curve: false, pose_measurements: false,
  });
  const [footPose, setFootPose] = useState('posed'); // 'posed' | 'flat'
  const [preset, setPreset] = useState('iso');
  const [resetKey, setResetKey] = useState(0);
  const [bounds, setBounds] = useState(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const controlsRef = useRef();
  const canvasWrapperRef = useRef();
  const { isMobile } = useViewport();

  // Fullscreen toggles CSS on this same wrapper (fixed, full-viewport)
  // rather than portalling/remounting the canvas elsewhere -- moving the
  // <Canvas> to a different DOM parent would tear down and recreate its
  // WebGL context, re-parsing the GLB meshes from scratch on every toggle.
  useEffect(() => {
    if (!isFullscreen) return undefined;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') setIsFullscreen(false);
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      document.body.style.overflow = prevOverflow;
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isFullscreen]);

  const target = useMemo(() => {
    if (!bounds) return null;
    const center = new THREE.Vector3();
    bounds.getCenter(center);
    const size = new THREE.Vector3();
    bounds.getSize(size);
    const radius = Math.max(size.x, size.y, size.z) / 2 || 150;
    return { center, radius };
  }, [bounds]);

  // Stable identity is required here: this is passed to SurfaceLayer as
  // `onBounds`, which sits in that component's own effect dependency array.
  // A plain function (recreated every render) would make that effect refire
  // on every Viewer3D render, not just when the mesh itself changes -- and
  // since firing it calls setBounds (producing a new Box3 reference even
  // when the union is a no-op), that becomes a self-sustaining render loop.
  // CameraRig's effect depends on the resulting `target`, so that loop kept
  // snapping the camera back to the current preset on every tick -- which
  // is exactly why OrbitControls' drag-to-rotate and scroll-to-zoom looked
  // completely unresponsive: the camera was being reset out from under the
  // user's input almost immediately after every frame.
  const handleBounds = useCallback((box) => {
    setBounds((prev) => (prev ? prev.clone().union(box) : box.clone()));
  }, []);

  function toggleLayer(key) {
    setLayers((l) => ({ ...l, [key]: !l[key] }));
  }

  function handleResetCamera() {
    setPreset('iso');
    setResetKey((k) => k + 1);
  }

  function handleScreenshot() {
    const canvas = canvasWrapperRef.current?.querySelector('canvas');
    if (!canvas) return;
    const link = document.createElement('a');
    link.download = `last-fit-3d-${Date.now()}.png`;
    link.href = canvas.toDataURL('image/png');
    link.click();
  }

  if (!geometry) return null;
  const { geometries, layers: dataLayers, legend, heatmap } = geometry;
  const hasFlatFoot = Boolean(geometries.foot_flat);
  const footGlb = footPose === 'flat' && hasFlatFoot ? geometries.foot_flat.data : geometries.foot.data;
  const bottomCurve = dataLayers.last_bottom_curve;
  const measurementLines = dataLayers.pose_measurements;

  return (
    <div
      className={
        isFullscreen
          ? 'fixed inset-0 z-[9999] flex flex-col gap-2 p-3 bg-[color:var(--color-modal-bg)]'
          : 'app-card p-3 flex flex-col gap-2'
      }
    >
      {title && <div className="font-medium text-sm">{title}</div>}

      <div className="flex flex-wrap items-center gap-3 text-xs">
        {Object.entries(LAYER_LABELS).map(([key, label]) => {
          if ((key === 'last_bottom_curve' && !bottomCurve?.length)
            || (key === 'pose_measurements' && !measurementLines?.length)) return null;
          return (
            <label key={key} className="flex items-center gap-1 cursor-pointer">
              <input type="checkbox" checked={layers[key]} onChange={() => toggleLayer(key)} />
              {label}
            </label>
          );
        })}
        {hasFlatFoot && (
          <div className="flex items-center gap-1">
            <button
              type="button"
              className={`btn text-xs ${footPose === 'posed' ? 'btn-primary' : ''}`}
              onClick={() => setFootPose('posed')}
              title="Стопа в позе колодки (каблук/носочный подъём применены)"
            >
              В позе колодки
            </button>
            <button
              type="button"
              className={`btn text-xs ${footPose === 'flat' ? 'btn-primary' : ''}`}
              onClick={() => setFootPose('flat')}
              title="Исходная (плоская) стопа, без деформации"
            >
              Исходная стопа
            </button>
          </div>
        )}
        <div className="flex items-center gap-1 ml-auto">
          {Object.keys(CAMERA_DIRECTIONS).map((p) => (
            <button
              key={p} type="button"
              className={`btn text-xs ${preset === p ? 'btn-primary' : ''}`}
              onClick={() => setPreset(p)}
            >
              {PRESET_LABELS[p]}
            </button>
          ))}
          <button type="button" className="btn text-xs" title="Сбросить камеру" onClick={handleResetCamera}>
            <RotateCcw size={14} />
          </button>
          <button type="button" className="btn text-xs" title="Скриншот" onClick={handleScreenshot}>
            <Download size={14} />
          </button>
          <button
            type="button"
            className="btn text-xs"
            title={isFullscreen ? 'Свернуть' : 'На весь экран'}
            onClick={() => setIsFullscreen((v) => !v)}
          >
            {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
        </div>
      </div>

      <div
        ref={canvasWrapperRef}
        className={`relative rounded border border-[color:var(--color-border)] overflow-hidden ${isFullscreen ? 'flex-1 min-h-0' : ''}`}
        style={isFullscreen ? undefined : { height: 420 }}
      >
        {isMobile && !isFullscreen && (
          <button
            type="button"
            onClick={() => setIsFullscreen(true)}
            title="Развернуть на весь экран"
            className="absolute bottom-2 right-2 z-10 rounded-full bg-black/60 text-white p-2 leading-none"
          >
            <Maximize2 size={18} />
          </button>
        )}
        <Canvas camera={{ fov: 45, near: 1, far: 5000, up: [0, 0, 1] }} gl={{ preserveDrawingBuffer: true }}>
          <color attach="background" args={['#0a0f1e']} />
          <ambientLight intensity={0.5} />
          <directionalLight position={[200, 300, 200]} intensity={0.5} />
          {/* Procedural (no network fetch) environment for the glass
              material's specular highlights/refraction -- a couple of soft
              light panels around the scene, not a photographic HDRI, so
              this doesn't depend on an external asset CDN being reachable
              from wherever this admin panel is deployed. */}
          <Environment resolution={128}>
            <Lightformer intensity={2} color="#dceeff" position={[0, 0, 200]} scale={[300, 300, 1]} />
            <Lightformer intensity={1.2} color="#ffffff" position={[200, 150, -100]} scale={[200, 200, 1]} />
            <Lightformer intensity={1} color="#88bfff" position={[-200, -100, -100]} scale={[200, 200, 1]} />
          </Environment>
          {layers.last && (
            <SurfaceLayer base64={geometries.last.data} color={legend.last} opacity={0.4} glass onBounds={handleBounds} />
          )}
          {layers.foot && (
            <SurfaceLayer base64={footGlb} color={legend.foot} opacity={0.72} glass onBounds={handleBounds} />
          )}
          {layers.patches && dataLayers.problem_patches.map((patch, i) => (
            <PatchLayer key={i} patch={patch} />
          ))}
          {layers.labels && dataLayers.labels.map((label, i) => (
            <LabelLayer key={i} label={label} />
          ))}
          {layers.last_bottom_curve && bottomCurve?.length > 1 && (
            <BottomCurveLayer points={bottomCurve} color={legend.last} />
          )}
          {layers.pose_measurements && measurementLines?.map((line, i) => (
            <MeasurementLineLayer key={i} line={line} />
          ))}
          <OrbitControls ref={controlsRef} makeDefault />
          <CameraRig target={target} controlsRef={controlsRef} preset={preset} resetKey={resetKey} />
        </Canvas>
      </div>

      <div className="flex flex-wrap items-center gap-3 text-[11px] text-[color:var(--color-text-muted)]">
        <LegendDot color={legend.last} label="Колодка" />
        {heatmap && (
          <span className="flex items-center gap-1.5">
            <span
              className="inline-block w-16 h-2.5 rounded-full"
              style={{ background: `linear-gradient(90deg, ${heatmap.tight_color}, ${heatmap.neutral_color}, ${heatmap.loose_color})` }}
            />
            <span>Теснота ↔ свобода (±{heatmap.range_mm} мм)</span>
          </span>
        )}
        <LegendDot color={legend.misallocated_volume} label="Объём не туда" />
        <LegendDot color={legend.forefoot_taper_too_fast} label="Носок сужается быстро" />
      </div>
    </div>
  );
}

function LegendDot({ color, label }) {
  return (
    <span className="flex items-center gap-1">
      <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ backgroundColor: color }} />
      {label}
    </span>
  );
}
