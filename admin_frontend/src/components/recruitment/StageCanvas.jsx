import { useRef, useState, useLayoutEffect, useCallback } from 'react';
import {
  Trash2, Plus, CornerDownRight, RotateCcw, GripVertical, HelpCircle,
  MessageCircleQuestion, ChevronDown, ChevronUp, LayoutGrid, Flag, ArrowRight,
} from 'lucide-react';

const BLOCK_W = 320;
const CANVAS_W = 2600;
const CANVAS_H = 1400;
const DONE_ID = '__done__';

function slugify(title, existingIds, fallbackIdx) {
  const base = (title || '')
    .toLowerCase()
    .replace(/[^a-zа-яё0-9]+/gi, '_')
    .replace(/^_+|_+$/g, '') || `stage_${fallbackIdx + 1}`;
  let id = base, n = 2;
  while (existingIds.includes(id)) { id = `${base}_${n++}`; }
  return id;
}

/** BFS-layers stages by transition depth so freshly added/imported stages
 * without x/y land in a sensible spot instead of stacked at (0,0). */
function autoLayout(stages) {
  const idToIdx = new Map(stages.map((s, i) => [s.id, i]));
  const incoming = new Array(stages.length).fill(0);
  stages.forEach(s => (s.transitions || []).forEach(t => {
    const j = idToIdx.get(t.next);
    if (j != null) incoming[j]++;
  }));
  const depth = new Array(stages.length).fill(null);
  const roots = stages.map((_, i) => i).filter(i => incoming[i] === 0);
  const queue = (roots.length ? roots : [0]).map(i => ({ i, d: 0 }));
  const visited = new Set();
  while (queue.length) {
    const { i, d } = queue.shift();
    if (visited.has(i)) continue;
    visited.add(i);
    depth[i] = d;
    (stages[i].transitions || []).forEach(t => {
      const j = idToIdx.get(t.next);
      if (j != null && !visited.has(j)) queue.push({ i: j, d: d + 1 });
    });
  }
  stages.forEach((_, i) => { if (depth[i] == null) depth[i] = 0; });
  const colCounts = {};
  const positions = {};
  stages.forEach((s, i) => {
    const col = depth[i];
    const row = colCounts[col] || 0;
    colCounts[col] = row + 1;
    positions[i] = { x: 40 + col * 400, y: 40 + row * 260 };
  });
  return positions;
}

export default function StageCanvas({ stages, onChange, onResetDefault }) {
  const ids = stages.map(s => s.id);
  const idCounts = ids.reduce((acc, id) => ({ ...acc, [id]: (acc[id] || 0) + 1 }), {});
  const reachesDone = stages.some(s => (s.transitions || []).some(t => t.next === 'done'));
  const titleOf = targetId => targetId === 'done'
    ? 'Завершить диалог'
    : (stages.find(s => s.id === targetId)?.title || targetId);

  const [expanded, setExpanded] = useState(() => new Set());
  const [, setRectsVersion] = useState(0);
  const canvasRef = useRef(null);
  const blockRefs = useRef({});
  const dragRef = useRef(null);

  // Positions: explicit x/y on the stage win; otherwise auto-layout fills the gap.
  const layout = autoLayout(stages);
  const posOf = idx => {
    const s = stages[idx];
    if (typeof s.x === 'number' && typeof s.y === 'number') return { x: s.x, y: s.y };
    return layout[idx];
  };

  useLayoutEffect(() => {
    setRectsVersion(v => v + 1);
  }, [stages, expanded]);

  function update(idx, patch) {
    onChange(stages.map((s, i) => i === idx ? { ...s, ...patch } : s));
  }

  function renameId(idx, newId) {
    const oldId = stages[idx].id;
    if (!newId || newId === oldId) return;
    onChange(stages.map((s, i) => {
      const transitions = (s.transitions || []).map(t => t.next === oldId ? { ...t, next: newId } : t);
      return i === idx ? { ...s, id: newId, transitions } : { ...s, transitions };
    }));
  }

  function addStage() {
    const id = slugify('', ids, stages.length);
    const p = layout[stages.length] || { x: 40, y: 40 };
    onChange([...stages, { id, title: 'Новый этап', instructions: '', transitions: [], x: p.x, y: p.y }]);
  }

  function addQuestionsStage() {
    const id = slugify('Вопросы вакансии', ids, stages.length);
    const p = layout[stages.length] || { x: 40, y: 40 };
    onChange([...stages, {
      id,
      title: 'Вопросы вакансии',
      instructions: 'Задай кандидату вопросы вакансии ниже, по одному за раз. Дождись ответа на каждый.',
      ask_custom_questions: true,
      transitions: [],
      x: p.x, y: p.y,
    }]);
  }

  function removeStage(idx) {
    const removedId = stages[idx].id;
    if (!window.confirm('Удалить этап? Переходы на него у других этапов тоже придётся исправить.')) return;
    onChange(stages.filter((_, i) => i !== idx).map(s => ({
      ...s,
      transitions: (s.transitions || []).filter(t => t.next !== removedId),
    })));
  }

  function rearrange() {
    if (!window.confirm('Расставить все блоки автоматически по порядку переходов? Текущее расположение будет потеряно.')) return;
    const fresh = autoLayout(stages);
    onChange(stages.map((s, i) => ({ ...s, x: fresh[i].x, y: fresh[i].y })));
  }

  function addTransition(idx) {
    update(idx, { transitions: [...(stages[idx].transitions || []), { condition: '', next: 'done' }] });
  }

  function updateTransition(idx, tIdx, patch) {
    const transitions = stages[idx].transitions.map((t, i) => i === tIdx ? { ...t, ...patch } : t);
    update(idx, { transitions });
  }

  function removeTransition(idx, tIdx) {
    update(idx, { transitions: stages[idx].transitions.filter((_, i) => i !== tIdx) });
  }

  function toggleExpanded(idx) {
    setExpanded(prev => {
      const next = new Set(prev);
      next.has(idx) ? next.delete(idx) : next.add(idx);
      return next;
    });
  }

  const onHeaderPointerDown = useCallback((idx, e) => {
    if (e.button !== undefined && e.button !== 0) return;
    const p = posOf(idx);
    dragRef.current = { idx, startClientX: e.clientX, startClientY: e.clientY, origX: p.x, origY: p.y };
    e.currentTarget.setPointerCapture?.(e.pointerId);

    function onMove(ev) {
      const d = dragRef.current;
      if (!d) return;
      const dx = ev.clientX - d.startClientX;
      const dy = ev.clientY - d.startClientY;
      const x = Math.max(0, d.origX + dx);
      const y = Math.max(0, d.origY + dy);
      onChange(stages.map((s, i) => i === d.idx ? { ...s, x, y } : s));
    }
    function onUp() {
      dragRef.current = null;
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    }
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stages, onChange]);

  // Connector geometry, recomputed after layout/render via blockRefs + rectsVersion.
  const lines = [];
  const canvasRect = canvasRef.current?.getBoundingClientRect();
  if (canvasRect) {
    const doneTargets = [];
    stages.forEach((s, idx) => {
      const fromEl = blockRefs.current[s.id];
      if (!fromEl) return;
      const fromRect = fromEl.getBoundingClientRect();
      const fromX = fromRect.right - canvasRect.left;
      const fromY = fromRect.top + fromRect.height / 2 - canvasRect.top;
      (s.transitions || []).forEach((t, tIdx) => {
        if (t.next === 'done') { doneTargets.push({ fromX, fromY }); return; }
        const toEl = blockRefs.current[t.next];
        if (!toEl) return;
        const toRect = toEl.getBoundingClientRect();
        const toX = toRect.left - canvasRect.left;
        const toY = toRect.top + toRect.height / 2 - canvasRect.top;
        lines.push({ key: `${idx}-${tIdx}`, x1: fromX, y1: fromY, x2: toX, y2: toY, highlight: false });
      });
    });
    if (doneTargets.length) {
      const doneX = Math.max(...doneTargets.map(d => d.fromX)) + 140;
      const doneY = doneTargets.reduce((a, d) => a + d.fromY, 0) / doneTargets.length;
      doneTargets.forEach((d, i) => {
        lines.push({ key: `done-${i}`, x1: d.fromX, y1: d.fromY, x2: doneX, y2: doneY, highlight: true });
      });
      lines.push({ doneNode: true, x: doneX, y: doneY });
    }
  }
  const doneNode = lines.find(l => l.doneNode);
  const connectorLines = lines.filter(l => !l.doneNode);

  return (
    <div className="space-y-2">
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs text-[color:var(--color-muted-foreground)]">
          Перетаскивайте блоки за серую полоску с заголовком, чтобы расположить сценарий удобно.
          Стрелка <ArrowRight size={11} className="inline -mt-0.5" /> на блоке и в его шапке ведут к
          этапу, на который ИИ переключится дальше.
        </p>
        <div className="flex items-center gap-3 flex-shrink-0">
          <button type="button" onClick={rearrange}
            className="text-xs text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-foreground)] flex items-center gap-1">
            <LayoutGrid size={12} /> Авто-расстановка
          </button>
          {onResetDefault && (
            <button type="button" onClick={onResetDefault}
              className="text-xs text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-foreground)] flex items-center gap-1">
              <RotateCcw size={12} /> Сбросить
            </button>
          )}
        </div>
      </div>
      <div className="flex items-center gap-4 flex-wrap text-[11px] text-[color:var(--color-muted-foreground)] bg-[color:var(--color-muted)]/30 rounded-lg px-3 py-2">
        <span className="flex items-center gap-1.5"><GripVertical size={12} /> перетащить блок</span>
        <span className="flex items-center gap-1.5"><ChevronDown size={12} /> открыть редактирование этапа</span>
        <span className="flex items-center gap-1.5"><ArrowRight size={12} /> переход к другому этапу</span>
        <span className="flex items-center gap-1.5"><Flag size={12} /> этап завершает диалог</span>
      </div>
      {!reachesDone && (
        <p className="text-xs text-red-500">
          Ни один переход не ведёт к «Завершить диалог» — интервью никогда не закончится.
        </p>
      )}

      <div
        ref={canvasRef}
        className="relative rounded-xl border border-[color:var(--color-border)] overflow-auto bg-[color:var(--color-muted)]/20"
        style={{
          height: '60vh',
          backgroundImage: 'radial-gradient(circle, var(--color-border) 1px, transparent 1px)',
          backgroundSize: '20px 20px',
        }}
      >
        <div className="relative" style={{ width: CANVAS_W, height: CANVAS_H }}>
          <svg className="absolute inset-0 pointer-events-none" width={CANVAS_W} height={CANVAS_H}>
            <defs>
              <marker id="stage-arrow" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
                <path d="M0,0 L8,4 L0,8 Z" fill="var(--color-muted-foreground)" />
              </marker>
            </defs>
            {connectorLines.map(l => {
              const midX = (l.x1 + l.x2) / 2;
              return (
                <path
                  key={l.key}
                  d={`M${l.x1},${l.y1} C${midX},${l.y1} ${midX},${l.y2} ${l.x2},${l.y2}`}
                  fill="none"
                  stroke={l.highlight ? '#94a3b8' : 'var(--color-muted-foreground)'}
                  strokeWidth="1.5"
                  strokeDasharray={l.highlight ? '4 3' : undefined}
                  markerEnd="url(#stage-arrow)"
                  opacity="0.7"
                />
              );
            })}
          </svg>

          {doneNode && (
            <div
              className="absolute flex items-center gap-1.5 text-xs font-medium text-white bg-slate-500 rounded-full px-3 py-1.5 shadow-sm"
              style={{ left: doneNode.x, top: doneNode.y, transform: 'translateY(-50%)' }}
            >
              <Flag size={12} /> Завершить диалог
            </div>
          )}

          {stages.map((s, idx) => {
            const p = posOf(idx);
            const isExpanded = expanded.has(idx);
            return (
              <div
                key={idx}
                ref={el => { if (el) blockRefs.current[s.id] = el; else delete blockRefs.current[s.id]; }}
                className="absolute rounded-xl border border-[color:var(--color-border)] bg-[color:var(--color-background)] shadow-sm"
                style={{ left: p.x, top: p.y, width: BLOCK_W }}
              >
                <div
                  onPointerDown={e => onHeaderPointerDown(idx, e)}
                  className="flex items-center gap-1.5 px-2.5 py-2 cursor-grab active:cursor-grabbing select-none rounded-t-xl bg-[color:var(--color-muted)]/40"
                >
                  <GripVertical size={13} className="text-[color:var(--color-muted-foreground)] flex-shrink-0" />
                  <span className="flex items-center justify-center text-[11px] font-semibold flex-shrink-0 w-5 h-5 rounded-full bg-[color:var(--color-primary)]/10 text-[color:var(--color-primary)]">
                    {idx + 1}
                  </span>
                  <span className="text-sm font-medium truncate flex-1 min-w-0">{s.title || 'Без названия'}</span>
                  {s.ask_custom_questions && (
                    <MessageCircleQuestion size={13} className="text-[color:var(--color-primary)] flex-shrink-0" title="Вопросы вакансии" />
                  )}
                  <button type="button" onClick={() => toggleExpanded(idx)} title={isExpanded ? 'Свернуть' : 'Развернуть'}
                    className="w-6 h-6 flex items-center justify-center rounded hover:bg-[color:var(--color-muted)] flex-shrink-0">
                    {isExpanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                  </button>
                  <button type="button" onClick={() => removeStage(idx)} title="Удалить этап"
                    className="w-6 h-6 flex items-center justify-center rounded hover:bg-red-50 text-red-400 flex-shrink-0">
                    <Trash2 size={13} />
                  </button>
                </div>

                {!isExpanded ? (
                  <div className="px-2.5 py-2 space-y-2">
                    <p className="text-[11px] text-[color:var(--color-muted-foreground)] line-clamp-2">
                      {s.instructions || 'Нет инструкции'}
                    </p>
                    {(s.transitions || []).length === 0 ? (
                      <p className="text-[11px] text-red-500 flex items-center gap-1">
                        <ArrowRight size={11} /> нет переходов — диалог зависнет здесь
                      </p>
                    ) : (
                      <div className="flex flex-col gap-1">
                        {(s.transitions || []).map((t, tIdx) => (
                          <span key={tIdx}
                            className={`inline-flex items-center gap-1.5 text-[11px] rounded-full px-2 py-1 self-start ${
                              t.next === 'done' ? 'bg-slate-100 text-slate-600' : 'bg-[color:var(--color-primary)]/10 text-[color:var(--color-primary)]'
                            }`}
                            title={t.condition ? `Если: ${t.condition}` : 'Без условия — переход сразу'}
                          >
                            {t.next === 'done' ? <Flag size={11} /> : <ArrowRight size={11} />}
                            {titleOf(t.next)}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="p-2.5 space-y-2.5 border-t border-[color:var(--color-border)]">
                    <input
                      className="input text-sm font-medium"
                      value={s.title}
                      onChange={e => update(idx, { title: e.target.value })}
                      placeholder="Название этапа"
                    />
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="text-[11px] text-[color:var(--color-muted-foreground)] flex-shrink-0">ID</span>
                      <input
                        className={`input text-xs font-mono py-1 flex-1 min-w-0 ${idCounts[s.id] > 1 ? 'border-red-400' : ''}`}
                        value={s.id}
                        onChange={e => renameId(idx, e.target.value.trim())}
                      />
                      <span title="Технический идентификатор этапа. Используется внутри переходов — менять не обязательно, но должен быть уникальным.">
                        <HelpCircle size={12} className="text-[color:var(--color-muted-foreground)] flex-shrink-0" />
                      </span>
                    </div>
                    {idCounts[s.id] > 1 && (
                      <p className="text-[11px] text-red-500 font-medium">id повторяется у другого этапа</p>
                    )}
                    <div>
                      <label className="text-[11px] text-[color:var(--color-muted-foreground)] mb-1 block">Что ИИ делает на этом этапе</label>
                      <textarea
                        className="input w-full min-h-[80px] resize-y text-sm"
                        value={s.instructions}
                        onChange={e => update(idx, { instructions: e.target.value })}
                        placeholder="Что ИИ должен сделать на этом этапе"
                      />
                    </div>
                    {s.ask_custom_questions && (
                      <p className="text-[11px] text-[color:var(--color-muted-foreground)]">
                        Список вопросов настраивается в редакторе конкретной вакансии, не здесь.
                      </p>
                    )}
                    <div className="space-y-1.5">
                      <p className="text-[11px] font-medium">Переходы дальше</p>
                      {(s.transitions || []).length === 0 && (
                        <p className="text-[11px] text-red-500">Нет ни одного перехода — этап зависнет навсегда.</p>
                      )}
                      {(s.transitions || []).map((t, tIdx) => (
                        <div key={tIdx} className="rounded-lg border border-[color:var(--color-border)] p-1.5 space-y-1.5">
                          <div className="flex items-center gap-1.5">
                            <CornerDownRight size={11} className="text-[color:var(--color-muted-foreground)] flex-shrink-0" />
                            <input
                              className="input text-xs py-1 flex-1 min-w-0"
                              value={t.condition}
                              onChange={e => updateTransition(idx, tIdx, { condition: e.target.value })}
                              placeholder="условие, можно пусто"
                            />
                            <button type="button" onClick={() => removeTransition(idx, tIdx)}
                              className="w-5 h-5 flex items-center justify-center rounded hover:bg-red-50 text-red-400 flex-shrink-0">
                              <Trash2 size={11} />
                            </button>
                          </div>
                          <select
                            className="input text-xs py-1"
                            value={t.next}
                            onChange={e => updateTransition(idx, tIdx, { next: e.target.value })}
                          >
                            {stages.filter((_, i) => i !== idx).map(other => (
                              <option key={other.id} value={other.id}>{other.title || other.id}</option>
                            ))}
                            <option value="done">Завершить диалог</option>
                          </select>
                        </div>
                      ))}
                      <button type="button" onClick={() => addTransition(idx)}
                        className="text-xs text-[color:var(--color-primary)] flex items-center gap-1 hover:underline">
                        <Plus size={11} /> Добавить переход
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      <div className="flex gap-2">
        <button type="button" onClick={addStage}
          className="btn btn-secondary text-sm flex-1 flex items-center justify-center gap-1.5">
          <Plus size={14} /> Добавить этап
        </button>
        <button type="button" onClick={addQuestionsStage}
          title="Добавить этап, на котором ИИ задаст вопросы вакансии"
          className="btn btn-secondary text-sm flex-1 flex items-center justify-center gap-1.5">
          <MessageCircleQuestion size={14} /> Этап с вопросами вакансии
        </button>
      </div>
    </div>
  );
}
