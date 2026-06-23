import { ArrowUp, ArrowDown, Trash2, Plus, CornerDownRight, RotateCcw, GripVertical } from 'lucide-react';

function slugify(title, existingIds, fallbackIdx) {
  const base = (title || '')
    .toLowerCase()
    .replace(/[^a-zа-яё0-9]+/gi, '_')
    .replace(/^_+|_+$/g, '') || `stage_${fallbackIdx + 1}`;
  let id = base, n = 2;
  while (existingIds.includes(id)) { id = `${base}_${n++}`; }
  return id;
}

export default function StageBuilder({ stages, onChange, onResetDefault }) {
  const ids = stages.map(s => s.id);
  const idCounts = ids.reduce((acc, id) => ({ ...acc, [id]: (acc[id] || 0) + 1 }), {});
  const reachesDone = stages.some(s => (s.transitions || []).some(t => t.next === 'done'));

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
    onChange([...stages, { id, title: 'Новый этап', instructions: '', transitions: [] }]);
  }

  function removeStage(idx) {
    const removedId = stages[idx].id;
    if (!window.confirm('Удалить этап? Переходы на него у других этапов тоже придётся исправить.')) return;
    onChange(stages.filter((_, i) => i !== idx).map(s => ({
      ...s,
      transitions: (s.transitions || []).filter(t => t.next !== removedId),
    })));
  }

  function move(idx, dir) {
    const j = idx + dir;
    if (j < 0 || j >= stages.length) return;
    const next = [...stages];
    [next[idx], next[j]] = [next[j], next[idx]];
    onChange(next);
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

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs text-[color:var(--color-muted-foreground)]">
          Каждый этап — это шаг разговора. ИИ ведёт диалог по инструкции текущего этапа и сам решает,
          когда условие перехода выполнено, переключаясь на следующий этап.
        </p>
        {onResetDefault && (
          <button type="button" onClick={onResetDefault}
            className="flex-shrink-0 text-xs text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-foreground)] flex items-center gap-1 ml-2">
            <RotateCcw size={12} /> Сбросить
          </button>
        )}
      </div>
      {!reachesDone && (
        <p className="text-xs text-red-500 -mt-1">
          Ни один переход не ведёт к «Завершить диалог» — интервью никогда не закончится.
        </p>
      )}

      {stages.map((s, idx) => (
        <div key={idx} className="rounded-xl border border-[color:var(--color-border)] p-3 space-y-2 bg-[color:var(--color-muted)]/30">
          <div className="flex items-center gap-2">
            <GripVertical size={14} className="text-[color:var(--color-muted-foreground)] flex-shrink-0" />
            <span className="text-xs font-mono text-[color:var(--color-muted-foreground)] flex-shrink-0 w-5">{idx + 1}.</span>
            <input
              className="input flex-1 text-sm font-medium"
              value={s.title}
              onChange={e => update(idx, { title: e.target.value })}
              placeholder="Название этапа"
            />
            <div className="flex items-center gap-0.5 flex-shrink-0">
              <button type="button" onClick={() => move(idx, -1)} disabled={idx === 0}
                className="w-6 h-6 flex items-center justify-center rounded hover:bg-[color:var(--color-muted)] disabled:opacity-30">
                <ArrowUp size={12} />
              </button>
              <button type="button" onClick={() => move(idx, 1)} disabled={idx === stages.length - 1}
                className="w-6 h-6 flex items-center justify-center rounded hover:bg-[color:var(--color-muted)] disabled:opacity-30">
                <ArrowDown size={12} />
              </button>
              <button type="button" onClick={() => removeStage(idx)}
                className="w-6 h-6 flex items-center justify-center rounded hover:bg-red-50 text-red-400">
                <Trash2 size={12} />
              </button>
            </div>
          </div>

          <div className="flex items-center gap-2 pl-6">
            <span className="text-[10px] text-[color:var(--color-muted-foreground)] flex-shrink-0">ID</span>
            <input
              className={`input text-xs font-mono py-1 w-40 ${idCounts[s.id] > 1 ? 'border-red-400' : ''}`}
              value={s.id}
              onChange={e => renameId(idx, e.target.value.trim())}
            />
            {idCounts[s.id] > 1 && (
              <span className="text-[10px] text-red-500">id повторяется у другого этапа</span>
            )}
          </div>

          <textarea
            className="input w-full min-h-[60px] resize-none text-sm pl-6"
            style={{ width: 'calc(100% - 0px)' }}
            value={s.instructions}
            onChange={e => update(idx, { instructions: e.target.value })}
            placeholder="Что ИИ должен сделать на этом этапе (что сказать, какие вопросы задать)"
          />

          <div className="pl-6 space-y-1.5">
            <p className="text-[10px] text-[color:var(--color-muted-foreground)]">Переходы дальше</p>
            {(s.transitions || []).length === 0 && (
              <p className="text-[11px] text-red-500">
                Нет ни одного перехода — разговор зависнет на этом этапе навсегда.
              </p>
            )}
            {(s.transitions || []).map((t, tIdx) => (
              <div key={tIdx} className="flex items-center gap-1.5">
                <CornerDownRight size={12} className="text-[color:var(--color-muted-foreground)] flex-shrink-0" />
                <input
                  className="input text-xs py-1 flex-1"
                  value={t.condition}
                  onChange={e => updateTransition(idx, tIdx, { condition: e.target.value })}
                  placeholder="Условие (например: кандидат согласен) — можно оставить пустым"
                />
                <span className="text-xs text-[color:var(--color-muted-foreground)] flex-shrink-0">→</span>
                <select
                  className="input text-xs py-1 flex-shrink-0 w-36"
                  value={t.next}
                  onChange={e => updateTransition(idx, tIdx, { next: e.target.value })}
                >
                  {stages.filter((_, i) => i !== idx).map(other => (
                    <option key={other.id} value={other.id}>{other.title || other.id}</option>
                  ))}
                  <option value="done">Завершить диалог</option>
                </select>
                <button type="button" onClick={() => removeTransition(idx, tIdx)}
                  className="w-6 h-6 flex items-center justify-center rounded hover:bg-red-50 text-red-400 flex-shrink-0">
                  <Trash2 size={11} />
                </button>
              </div>
            ))}
            <button type="button" onClick={() => addTransition(idx)}
              className="text-xs text-[color:var(--color-primary)] flex items-center gap-1 hover:underline">
              <Plus size={11} /> Добавить переход
            </button>
          </div>
        </div>
      ))}

      <button type="button" onClick={addStage}
        className="btn btn-secondary text-sm w-full flex items-center justify-center gap-1.5">
        <Plus size={14} /> Добавить этап
      </button>
    </div>
  );
}
