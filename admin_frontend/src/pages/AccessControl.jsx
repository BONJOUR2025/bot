import { useEffect, useMemo, useState } from 'react';
import api from '../api.js';

const emptyRole = { id: '', name: '', permissions: [], bot_buttons: [] };
const emptyUser = {
  id: '',
  login: '',
  password: '',
  role_id: '',
  permissions: [],
  bot_buttons: [],
  inheritPermissions: true,
  inheritButtons: true,
};

export default function AccessControl() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [data, setData] = useState(null);
  const [roleForm, setRoleForm] = useState(null);
  const [isRoleNew, setIsRoleNew] = useState(false);
  const [userForm, setUserForm] = useState(null);
  const [isUserNew, setIsUserNew] = useState(false);

  useEffect(() => {
    load();
  }, []);

  async function load() {
    try {
      setLoading(true);
      const res = await api.get('auth/access');
      setData(res.data);
      setError('');
    } catch (err) {
      console.error(err);
      setError('Не удалось загрузить настройки доступа');
    } finally {
      setLoading(false);
    }
  }

  const buttonGroups = useMemo(() => {
    if (!data) return {};
    return data.available_bot_buttons.reduce((acc, btn) => {
      const scope = btn.scope || 'other';
      acc[scope] = acc[scope] || [];
      acc[scope].push(btn);
      return acc;
    }, {});
  }, [data]);

  function startRoleCreate() {
    setIsRoleNew(true);
    setRoleForm({ ...emptyRole });
  }

  function startRoleEdit(role) {
    setIsRoleNew(false);
    setRoleForm({ ...role });
  }

  function cancelRoleForm() {
    setRoleForm(null);
  }

  async function submitRole(event) {
    event.preventDefault();
    const payload = {
      id: roleForm.id || undefined,
      name: roleForm.name,
      permissions: roleForm.permissions,
      bot_buttons: roleForm.bot_buttons,
    };
    try {
      if (isRoleNew) {
        await api.post('auth/roles', payload);
      } else {
        await api.patch(`auth/roles/${roleForm.id}`, payload);
      }
      cancelRoleForm();
      load();
    } catch (err) {
      console.error(err);
      alert('Не удалось сохранить роль');
    }
  }

  async function deleteRole(role) {
    if (!window.confirm(`Удалить роль «${role.name}»?`)) return;
    try {
      await api.delete(`auth/roles/${role.id}`);
      load();
    } catch (err) {
      console.error(err);
      alert('Не удалось удалить роль');
    }
  }

  function toggleRolePermission(permission) {
    setRoleForm((prev) => {
      const list = new Set(prev.permissions || []);
      if (list.has(permission)) list.delete(permission);
      else list.add(permission);
      return { ...prev, permissions: Array.from(list) };
    });
  }

  function toggleRoleButton(buttonId) {
    setRoleForm((prev) => {
      const list = new Set(prev.bot_buttons || []);
      if (list.has(buttonId)) list.delete(buttonId);
      else list.add(buttonId);
      return { ...prev, bot_buttons: Array.from(list) };
    });
  }

  function startUserCreate() {
    setIsUserNew(true);
    setUserForm({ ...emptyUser });
  }

  function startUserEdit(user) {
    setIsUserNew(false);
    setUserForm({
      id: user.id,
      login: user.login,
      password: '',
      role_id: user.role_id || '',
      permissions: user.permissions ?? [],
      bot_buttons: user.bot_buttons ?? [],
      inheritPermissions: user.permissions === null || user.permissions === undefined,
      inheritButtons: user.bot_buttons === null || user.bot_buttons === undefined,
    });
  }

  function cancelUserForm() {
    setUserForm(null);
  }

  async function submitUser(event) {
    event.preventDefault();
    const payload = {
      id: userForm.id || undefined,
      login: userForm.login,
      password: userForm.password || undefined,
      role_id: userForm.role_id || undefined,
      permissions: userForm.inheritPermissions ? null : userForm.permissions,
      bot_buttons: userForm.inheritButtons ? null : userForm.bot_buttons,
    };
    try {
      if (isUserNew) {
        await api.post('auth/users', payload);
      } else {
        await api.patch(`auth/users/${userForm.id}`, payload);
      }
      cancelUserForm();
      load();
    } catch (err) {
      console.error(err);
      alert('Не удалось сохранить пользователя');
    }
  }

  async function deleteUser(user) {
    if (!window.confirm(`Удалить пользователя ${user.login}?`)) return;
    try {
      await api.delete(`auth/users/${user.id}`);
      load();
    } catch (err) {
      console.error(err);
      alert('Не удалось удалить пользователя');
    }
  }

  function toggleUserPermission(permission) {
    setUserForm((prev) => {
      const list = new Set(prev.permissions || []);
      if (list.has(permission)) list.delete(permission);
      else list.add(permission);
      return { ...prev, permissions: Array.from(list) };
    });
  }

  function toggleUserButton(buttonId) {
    setUserForm((prev) => {
      const list = new Set(prev.bot_buttons || []);
      if (list.has(buttonId)) list.delete(buttonId);
      else list.add(buttonId);
      return { ...prev, bot_buttons: Array.from(list) };
    });
  }

  if (loading) {
    return <div className="text-center">Загрузка настроек...</div>;
  }

  if (error) {
    return <div className="text-red-600 text-center">{error}</div>;
  }

  return (
    <div className="space-y-8">
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold">Роли</h2>
          <button className="btn" onClick={startRoleCreate}>Добавить роль</button>
        </div>
        <div className="grid gap-3">
          {data.roles.map((role) => (
            <div key={role.id} className="border rounded p-4 bg-white shadow-sm">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h3 className="font-semibold text-lg">{role.name}</h3>
                  <p className="text-sm text-gray-500">ID: {role.id}</p>
                  <p className="text-sm mt-2">
                    Права: {role.permissions.length ? role.permissions.join(', ') : 'Нет'}
                  </p>
                  <p className="text-sm mt-1">
                    Кнопки бота: {role.bot_buttons.length ? role.bot_buttons.join(', ') : 'По умолчанию'}
                  </p>
                </div>
                <div className="flex gap-2">
                  <button className="btn" onClick={() => startRoleEdit(role)}>Изменить</button>
                  <button className="btn bg-red-500 hover:bg-red-600" onClick={() => deleteRole(role)}>
                    Удалить
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
        {roleForm && (
          <form className="border rounded p-4 bg-white space-y-4" onSubmit={submitRole}>
            <h3 className="text-lg font-semibold">
              {isRoleNew ? 'Новая роль' : `Редактирование роли «${roleForm.name}»`}
            </h3>
            <div className="grid md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="block text-sm font-medium text-gray-700" htmlFor="role-id">
                  Идентификатор
                </label>
                <input
                  id="role-id"
                  className="input w-full"
                  value={roleForm.id}
                  onChange={(e) => setRoleForm((prev) => ({ ...prev, id: e.target.value }))}
                  disabled={!isRoleNew}
                  required={isRoleNew}
                />
              </div>
              <div className="space-y-2">
                <label className="block text-sm font-medium text-gray-700" htmlFor="role-name">
                  Название
                </label>
                <input
                  id="role-name"
                  className="input w-full"
                  value={roleForm.name}
                  onChange={(e) => setRoleForm((prev) => ({ ...prev, name: e.target.value }))}
                  required
                />
              </div>
            </div>
            <div className="space-y-2">
              <h4 className="font-medium">Права доступа</h4>
              <div className="grid md:grid-cols-2 gap-2">
                {data.available_permissions.map((perm) => (
                  <label key={perm.id} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={roleForm.permissions?.includes(perm.id) || false}
                      onChange={() => toggleRolePermission(perm.id)}
                    />
                    {perm.label}
                  </label>
                ))}
              </div>
            </div>
            <div className="space-y-2">
              <h4 className="font-medium">Кнопки в боте</h4>
              <div className="space-y-3">
                {Object.entries(buttonGroups).map(([scope, buttons]) => (
                  <div key={scope}>
                    <p className="text-sm font-semibold text-gray-600 mb-1">
                      {scope === 'user' ? 'Пользовательское меню' : scope === 'common' ? 'Обязательные' : scope}
                    </p>
                    <div className="grid md:grid-cols-2 gap-2">
                      {buttons.map((btn) => (
                        <label key={btn.id} className="flex items-center gap-2 text-sm">
                          <input
                            type="checkbox"
                            checked={roleForm.bot_buttons?.includes(btn.id) || false}
                            onChange={() => toggleRoleButton(btn.id)}
                            disabled={btn.fixed}
                          />
                          {btn.label}
                        </label>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div className="flex gap-2">
              <button className="btn" type="submit">
                Сохранить
              </button>
              <button className="btn bg-gray-200 text-gray-700" type="button" onClick={cancelRoleForm}>
                Отмена
              </button>
            </div>
          </form>
        )}
      </section>

      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold">Пользователи</h2>
          <button className="btn" onClick={startUserCreate}>Добавить пользователя</button>
        </div>
        <div className="grid gap-3">
          {data.users.map((user) => (
            <div key={user.id} className="border rounded p-4 bg-white shadow-sm">
              <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
                <div className="space-y-1">
                  <h3 className="text-lg font-semibold">{user.login}</h3>
                  <p className="text-sm text-gray-500">ID: {user.id}</p>
                  {user.display_name && (
                    <p className="text-sm text-gray-500">{user.display_name}</p>
                  )}
                  <p className="text-sm">Роль: {user.role_name || '—'}</p>
                  <p className="text-sm">
                    Итоговые права: {user.resolved_permissions.length ? user.resolved_permissions.join(', ') : 'нет'}
                  </p>
                  <p className="text-sm">
                    Кнопки в боте: {user.resolved_bot_button_labels.length ? user.resolved_bot_button_labels.join(', ') : 'по умолчанию'}
                  </p>
                </div>
                <div className="flex gap-2">
                  <button className="btn" onClick={() => startUserEdit(user)}>Изменить</button>
                  <button className="btn bg-red-500 hover:bg-red-600" onClick={() => deleteUser(user)}>
                    Удалить
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
        {userForm && (
          <form className="border rounded p-4 bg-white space-y-4" onSubmit={submitUser}>
            <h3 className="text-lg font-semibold">
              {isUserNew ? 'Новый пользователь' : `Редактирование пользователя «${userForm.login}»`}
            </h3>
            <div className="grid md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="block text-sm font-medium text-gray-700" htmlFor="user-id">
                  Идентификатор
                </label>
                <input
                  id="user-id"
                  className="input w-full"
                  value={userForm.id}
                  onChange={(e) => setUserForm((prev) => ({ ...prev, id: e.target.value }))}
                  required={isUserNew}
                  disabled={!isUserNew}
                />
                <p className="text-xs text-gray-500">Используйте ID из Telegram для связи с ботом.</p>
              </div>
              <div className="space-y-2">
                <label className="block text-sm font-medium text-gray-700" htmlFor="user-login">
                  Логин
                </label>
                <input
                  id="user-login"
                  className="input w-full"
                  value={userForm.login}
                  onChange={(e) => setUserForm((prev) => ({ ...prev, login: e.target.value }))}
                  required
                />
              </div>
              <div className="space-y-2">
                <label className="block text-sm font-medium text-gray-700" htmlFor="user-password">
                  Пароль
                </label>
                <input
                  id="user-password"
                  type="password"
                  className="input w-full"
                  value={userForm.password}
                  onChange={(e) => setUserForm((prev) => ({ ...prev, password: e.target.value }))}
                  placeholder={isUserNew ? '' : 'Оставьте пустым, чтобы не менять'}
                  required={isUserNew}
                />
              </div>
              <div className="space-y-2">
                <label className="block text-sm font-medium text-gray-700" htmlFor="user-role">
                  Роль
                </label>
                <select
                  id="user-role"
                  className="input w-full"
                  value={userForm.role_id}
                  onChange={(e) => setUserForm((prev) => ({ ...prev, role_id: e.target.value }))}
                >
                  <option value="">Без роли</option>
                  {data.roles.map((role) => (
                    <option key={role.id} value={role.id}>
                      {role.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="inherit-permissions"
                  checked={userForm.inheritPermissions}
                  onChange={(e) => setUserForm((prev) => ({ ...prev, inheritPermissions: e.target.checked }))}
                />
                <label htmlFor="inherit-permissions" className="text-sm">
                  Использовать права роли
                </label>
              </div>
              {!userForm.inheritPermissions && (
                <div className="grid md:grid-cols-2 gap-2">
                  {data.available_permissions.map((perm) => (
                    <label key={perm.id} className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={userForm.permissions.includes(perm.id)}
                        onChange={() => toggleUserPermission(perm.id)}
                      />
                      {perm.label}
                    </label>
                  ))}
                </div>
              )}
            </div>
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="inherit-buttons"
                  checked={userForm.inheritButtons}
                  onChange={(e) => setUserForm((prev) => ({ ...prev, inheritButtons: e.target.checked }))}
                />
                <label htmlFor="inherit-buttons" className="text-sm">
                  Использовать настройки кнопок роли
                </label>
              </div>
              {!userForm.inheritButtons && (
                <div className="space-y-3">
                  {Object.entries(buttonGroups).map(([scope, buttons]) => (
                    <div key={scope}>
                      <p className="text-sm font-semibold text-gray-600 mb-1">
                        {scope === 'user' ? 'Пользовательское меню' : scope === 'common' ? 'Обязательные' : scope}
                      </p>
                      <div className="grid md:grid-cols-2 gap-2">
                        {buttons.map((btn) => (
                          <label key={btn.id} className="flex items-center gap-2 text-sm">
                            <input
                              type="checkbox"
                              checked={userForm.bot_buttons.includes(btn.id)}
                              onChange={() => toggleUserButton(btn.id)}
                              disabled={btn.fixed}
                            />
                            {btn.label}
                          </label>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="flex gap-2">
              <button className="btn" type="submit">
                Сохранить
              </button>
              <button className="btn bg-gray-200 text-gray-700" type="button" onClick={cancelUserForm}>
                Отмена
              </button>
            </div>
          </form>
        )}
      </section>
    </div>
  );
}
