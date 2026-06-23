import { ArrowUp, ArrowDown, Trash2, Plus, CornerDownRight, RotateCcw, GripVertical, HelpCircle, MessageCircleQuestion } from 'lucide-react';

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

  function addQuestionsStage() {
    const id = slugify('Вопросы вакансии', ids, stages.length);
    onChange([...stages, {
      id,
      title: 'Вопросы вакансии',
      instructions: 'Задай кандидату вопросы вакансии ниже, по одному за раз. Дождись ответа на каждый.',
      ask_custom_questions: true,
      transitions: [],
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
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs text-[color:var(--color-muted-foreground)]">
          Каждый этап — это шаг разговора. ИИ ведёт диалог по инструкции текущего этапа и сам решает,
          когда условие перехода выполнено, переключаясь на следующий этап.
        </p>
        {onResetDefault && (
          <button type="button" onClick={onResetDefault}
            className="flex-shrink-0 text-xs text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-foreground)] flex items-center gap-1">
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
        <div key={idx} className="rounded-xl border border-[color:var(--color-border)] p-3 md:p-4 space-y-3 bg-[color:var(--color-muted)]/30">
          <div className="flex items-center gap-2">
            <GripVertical size={14} className="text-[color:var(--color-muted-foreground)] flex-shrink-0" />
            <span className="flex items-center justify-center text-xs font-semibold flex-shrink-0 w-6 h-6 rounded-full bg-[color:var(--color-primary)]/10 text-[color:var(--color-primary)]">
              {idx + 1}
            </span>
            <input
              className="input flex-1 text-sm font-medium"
              value={s.title}
              onChange={e => update(idx, { title: e.target.value })}
              placeholder="Название этапа"
            />
            {s.ask_custom_questions && (
              <span
                className="flex-shrink-0 inline-flex items-center gap-1 text-[11px] font-medium text-[color:var(--color-primary)] bg-[color:var(--color-primary)]/10 rounded-full px-2 py-1"
                title="На этом этапе ИИ задаст вопросы вакансии, настроенные в редакторе вакансии">
                <MessageCircleQuestion size={12} /> Вопросы вакансии
              </span>
            )}
            <div className="flex items-center gap-0.5 flex-shrink-0">
              <button type="button" onClick={() => move(idx, -1)} disabled={idx === 0} title="Поднять"
                className="w-7 h-7 flex items-center justify-center rounded hover:bg-[color:var(--color-muted)] disabled:opacity-30">
                <ArrowUp size={13} />
              </button>
              <button type="button" onClick={() => move(idx, 1)} disabled={idx === stages.length - 1} title="Опустить"
                className="w-7 h-7 flex items-center justify-center rounded hover:bg-[color:var(--color-muted)] disabled:opacity-30">
                <ArrowDown size={13} />
              </button>
              <button type="button" onClick={() => removeStage(idx)} title="Удалить этап"
                className="w-7 h-7 flex items-center justify-center rounded hover:bg-red-50 text-red-400">
                <Trash2 size={13} />
              </button>
            </div>
          </div>

          <div className="pl-8 flex items-center gap-2 flex-wrap">
            <span className="text-[11px] text-[color:var(--color-muted-foreground)] flex-shrink-0">ID</span>
            <input
              className={`input text-xs font-mono py-1 w-44 ${idCounts[s.id] > 1 ? 'border-red-400' : ''}`}
              value={s.id}
              onChange={e => renameId(idx, e.target.value.trim())}
            />
            <span className="inline-flex items-center gap-1 text-[11px] text-[color:var(--color-muted-foreground)]" title="Технический идентификатор этапа. Используется внутри переходов — менять не обязательно, но должен быть уникальным.">
              <HelpCircle size={12} /> внутренний код этапа, не обязательно менять
            </span>
            {idCounts[s.id] > 1 && (
              <span className="text-[11px] text-red-500 font-medium">id повторяется у другого этапа</span>
            )}
          </div>

          <div className="pl-8">
            <label className="text-[11px] text-[color:var(--color-muted-foreground)] mb-1 block">Что ИИ делает на этом этапе</label>
            <textarea
              className="input w-full min-h-[90px] resize-y text-sm"
              value={s.instructions}
              onChange={e => update(idx, { instructions: e.target.value })}
              placeholder="Что ИИ должен сделать на этом этапе: что сказать, какие вопросы задать кандидату"
            />
          </div>

          {s.ask_custom_questions && (
            <p className="pl-8 text-[11px] text-[color:var(--color-muted-foreground)]">
              Список вопросов настраивается в редакторе конкретной вакансии (шаг «Вопросы для кандидата»),
              не здесь — стратегия общая для всех вакансий. Ответы попадут в финальное резюме кандидата.
            </p>
          )}

          <div className="pl-8 space-y-2">
            <div>
              <p className="text-[11px] font-medium text-[color:var(--color-foreground)]">Переходы дальше</p>
              <p className="text-[11px] text-[color:var(--color-muted-foreground)]">
                Когда условие выполнено, ИИ переключается на выбранный этап. Условие можно оставить пустым —
                тогда переход сработает сразу, как только ИИ закончит говорить на этом этапе.
              </p>
            </div>
            {(s.transitions || []).length === 0 && (
              <p className="text-[11px] text-red-500">
                Нет ни одного перехода — разговор зависнет на этом этапе навсегда.
              </p>
            )}
            {(s.transitions || []).map((t, tIdx) => (
              <div key={tIdx} className="rounded-lg border border-[color:var(--color-border)] bg-[color:var(--color-background)] p-2 space-y-1.5">
                <div className="flex items-center gap-1.5">
                  <CornerDownRight size={12} className="text-[color:var(--color-muted-foreground)] flex-shrink-0" />
                  <span className="text-[11px] text-[color:var(--color-muted-foreground)] flex-shrink-0">Если:</span>
                  <input
                    className="input text-xs py-1 flex-1 min-w-0"
                    value={t.condition}
                    onChange={e => updateTransition(idx, tIdx, { condition: e.target.value })}
                    placeholder="например: кандидат согласен — можно оставить пустым"
                  />
                  <button type="button" onClick={() => removeTransition(idx, tIdx)} title="Удалить переход"
                    className="w-6 h-6 flex items-center justify-center rounded hover:bg-red-50 text-red-400 flex-shrink-0">
                    <Trash2 size={11} />
                  </button>
                </div>
                <div className="flex items-center gap-1.5 pl-[18px]">
                  <span className="text-[11px] text-[color:var(--color-muted-foreground)] flex-shrink-0">→ перейти на:</span>
                  <select
                    className="input text-xs py-1 flex-1 min-w-0"
                    value={t.next}
                    onChange={e => updateTransition(idx, tIdx, { next: e.target.value })}
                  >
                    {stages.filter((_, i) => i !== idx).map(other => (
                      <option key={other.id} value={other.id}>{other.title || other.id}</option>
                    ))}
                    <option value="done">Завершить диалог</option>
                  </select>
                </div>
              </div>
            ))}
            <button type="button" onClick={() => addTransition(idx)}
              className="text-xs text-[color:var(--color-primary)] flex items-center gap-1 hover:underline">
              <Plus size={11} /> Добавить переход
            </button>
          </div>
        </div>
      ))}

      <div className="flex gap-2">
        <button type="button" onClick={addStage}
          className="btn btn-secondary text-sm flex-1 flex items-center justify-center gap-1.5">
          <Plus size={14} /> Добавить этап
        </button>
        <button type="button" onClick={addQuestionsStage}
          title="Добавить этап, на котором ИИ задаст вопросы вакансии (настраиваются в редакторе вакансии)"
          className="btn btn-secondary text-sm flex-1 flex items-center justify-center gap-1.5">
          <MessageCircleQuestion size={14} /> Этап с вопросами вакансии
        </button>
      </div>
    </div>
  );
}
