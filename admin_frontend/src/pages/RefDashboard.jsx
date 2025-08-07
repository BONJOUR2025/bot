import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ref_ui/card';
import { Button } from '../ref_ui/button';
import { StatusBadge } from '../ref_ui/StatusBadge';
import api from '../api';

export default function RefDashboard() {
  const [count, setCount] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    load();
  }, []);

  async function load() {
    try {
      const res = await api.get('employees/');
      setCount(res.data.length);
    } catch (err) {
      console.error(err);
    }
  }

  async function refresh() {
    setLoading(true);
    await load();
    setLoading(false);
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Сотрудники</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center gap-2">
          {count === null ? 'Загрузка...' : <span>Всего сотрудников: {count}</span>}
          {loading && <StatusBadge status="processing" size="sm" />}
        </CardContent>
      </Card>
      <Button onClick={refresh}>Обновить</Button>
    </div>
  );
}
