import { useEffect, useState } from 'react';
import { CalendarDays, Gift } from 'lucide-react';
import api from '../api';
import { Badge, Card } from './ui';

export default function UpcomingBirthdays({ days = 30 }) {
  const [list, setList] = useState([]);

  useEffect(() => {
    load();
  }, []);

  async function load() {
    try {
      const res = await api.get('birthdays/', { params: { days } });
      setList(res.data);
    } catch (err) {
      console.error(err);
    }
  }

  function formatDateRu(value) {
    return new Date(value).toLocaleDateString('ru-RU', {
      day: 'numeric',
      month: 'long',
    });
  }

  if (!list.length) return null;

  return (
    <Card
      title="Ближайшие дни рождения"
      description={`В течение следующих ${days} дней`}
      actions={<Badge tone="info">{list.length}</Badge>}
      className="shadow-none"
    >
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {list.map((b) => (
          <article
            key={b.user_id}
            className="flex flex-col gap-2 rounded-2xl border border-border bg-[color:var(--color-input-background)] px-4 py-3 text-sm text-[color:var(--foreground)] shadow-sm"
          >
            <div className="flex items-center gap-2 font-medium">
              <Gift size={16} className="text-[color:var(--accent-foreground)]" />
              <span>{b.full_name}</span>
            </div>
            <div className="flex items-center gap-2 text-xs text-[color:var(--muted-foreground)]">
              <CalendarDays size={14} />
              <span>{formatDateRu(b.birthdate)}</span>
            </div>
          </article>
        ))}
      </div>
    </Card>
  );
}
