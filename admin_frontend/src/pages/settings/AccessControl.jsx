import { useEffect, useMemo, useState } from 'react';
import api from '../../api.js';
import { useViewport } from '../../providers/ViewportProvider.jsx';
import { useToast } from '../../providers/ToastProvider.jsx';
import ResponsiveTable from '../../components/ui/ResponsiveTable.jsx';

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
  limitByEmployees: false,
  limitByDepartments: false,
  allowed_employee_ids: [],
  allowed_departments: [],
  employee_id: '',
  hadLogin: false,
};

export default function AccessControl() {
  const { isMobile } = useViewport();
  const { toast } = useToast();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [data, setData] = useState(null);
  const [roleForm, setRoleForm] = useState(null);
  const [isRoleNew, setIsRoleNew] = useState(false);
  const [userForm, setUserForm] = useState(null);
  const [isUserNew, setIsUserNew] = useState(false);
  const [botUsers, setBotUsers] = useState([]);
  const [linkSelections, setLinkSelections] = useState({});
  const [vkBotUsers, setVkBotUsers] = useState([]);
  const [vkLinkSelections, setVkLinkSelections] = useState({});

  useEffect(() => {
    load();
    loadBotUsers();
    loadVkBotUsers();
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

  async function loadBotUsers() {
    try {
      const res = await api.get('bot-users/');
      setBotUsers(res.data);
    } catch (err) {
      console.error(err);
    }
  }

  function fmtDateTime(iso) {
    if (!iso) return '—';
    try {
      return new Date(iso).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' });
    } catch {
      return iso;
    }
  }

  async function linkBotUser(telegramId) {
    const employeeId = linkSelections[telegramId];
    if (!employeeId) return;
    try {
      await api.post(`bot-users/${telegramId}/link`, { employee_id: employeeId });
      setLinkSelections((prev) => ({ ...prev, [telegramId]: '' }));
      loadBotUsers();
    } catch (err) {
      console.error(err);
      toast('Не удалось привязать пользователя', 'error');
    }
  }

  async function loadVkBotUsers() {
    try {
      const res = await api.get('vk-bot-users/');
      setVkBotUsers(res.data);
    } catch (err) {
      console.error(err);
    }
  }

  async function linkVkBotUser(vkId) {
    const employeeId = vkLinkSelections[vkId];
    if (!employeeId) return;
    try {
      await api.post(`vk-bot-users/${vkId}/link`, { employee_id: employeeId });
      setVkLinkSelections((prev) => ({ ...prev, [vkId]: '' }));
      loadVkBotUsers();
    } catch (err) {
      console.error(err);
      toast('Не удалось привязать пользователя', 'error');
    }
  }

  async function unlinkVkBotUser(vkId) {
    try {
      await api.post(`vk-bot-users/${vkId}/unlink`);
      loadVkBotUsers();
    } catch (err) {
      console.error(err);
      toast('Не удалось отвязать пользователя', 'error');
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

  const employeesByDepartment = useMemo(() => {
    if (!data) return {};
    return data.available_employees.reduce((acc, employee) => {
      const key = employee.department || 'Без отдела';
      if (!acc[key]) acc[key] = [];
      acc[key].push(employee);
      return acc;
    }, {});
  }, [data]);

  const availableDepartments = useMemo(() => {
    if (!data) return [];
    return data.available_departments;
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
      toast('Не удалось сохранить роль', 'error');
    }
  }

  async function deleteRole(role) {
    if (!window.confirm(`Удалить роль «${role.name}»?`)) return;
    try {
      await api.delete(`auth/roles/${role.id}`);
      load();
    } catch (err) {
      console.error(err);
      toast('Не удалось удалить роль', 'error');
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
    const employeeScope = user.allowed_employee_ids ?? null;
    const departmentScope = user.allowed_departments ?? null;
    setUserForm({
      id: user.id,
      login: user.login,
      password: '',
      role_id: user.role_id || '',
      permissions: user.permissions ?? [],
      bot_buttons: user.bot_buttons ?? [],
      inheritPermissions: user.permissions === null || user.permissions === undefined,
      inheritButtons: user.bot_buttons === null || user.bot_buttons === undefined,
      limitByEmployees: Array.isArray(employeeScope) && employeeScope.length > 0,
      limitByDepartments: Array.isArray(departmentScope) && departmentScope.length > 0,
      allowed_employee_ids: Array.isArray(employeeScope) ? [...employeeScope] : [],
      allowed_departments: Array.isArray(departmentScope) ? [...departmentScope] : [],
      employee_id: user.employee_id || '',
      hadLogin: user.has_login,
    });
  }

  function cancelUserForm() {
    setUserForm(null);
  }

  function editBotUserAccess(employeeId) {
    const user = data.users.find((u) => String(u.employee_id) === String(employeeId));
    if (!user) return;
    startUserEdit(user);
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
      allowed_employee_ids: userForm.limitByEmployees
        ? userForm.allowed_employee_ids
        : null,
      allowed_departments: userForm.limitByDepartments
        ? userForm.allowed_departments
        : null,
      employee_id: userForm.employee_id || null,
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
      toast('Не удалось сохранить пользователя', 'error');
    }
  }

  async function deleteUser(user) {
    if (!window.confirm(`Удалить пользователя ${user.login}?`)) return;
    try {
      await api.delete(`auth/users/${user.id}`);
      load();
    } catch (err) {
      console.error(err);
      toast('Не удалось удалить пользователя', 'error');
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

  function handleEmployeeScopeChange(event) {
    const options = Array.from(event.target.selectedOptions || []);
    const selected = options.map((option) => option.value);
    setUserForm((prev) => ({ ...prev, allowed_employee_ids: selected }));
  }

  function handleDepartmentScopeChange(event) {
    const { value, checked } = event.target;
    setUserForm((prev) => {
      const next = new Set(prev.allowed_departments || []);
      if (checked) next.add(value);
      else next.delete(value);
      return { ...prev, allowed_departments: Array.from(next) };
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
        {isMobile ? (
          <div className="space-y-3">
            {data.roles.map((role) => (
              <div key={role.id} className="border rounded-xl bg-[color:var(--color-surface)] shadow-sm overflow-hidden">
                <div className="px-4 py-3 border-b bg-[color:var(--color-bg-subtle)] text-sm font-medium">{role.name}</div>
                <div className="px-4 py-2 space-y-1.5 text-sm">
                  <div className="flex justify-between"><span className="text-[color:var(--color-text-muted)]">ID</span><span>{role.id}</span></div>
                  <div className="flex justify-between"><span className="text-[color:var(--color-text-muted)]">Права</span><span className="text-right max-w-[60%]">{role.permissions.length ? role.permissions.join(', ') : 'Нет'}</span></div>
                  <div className="flex justify-between"><span className="text-[color:var(--color-text-muted)]">Кнопки бота</span><span className="text-right max-w-[60%]">{role.bot_buttons.length ? role.bot_buttons.join(', ') : 'По умолчанию'}</span></div>
                </div>
                <div className="px-4 py-2 border-t flex justify-end gap-3">
                  <button className="btn" onClick={() => startRoleEdit(role)}>Изменить</button>
                  <button className="btn btn--danger" onClick={() => deleteRole(role)}>Удалить</button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="grid gap-3">
            {data.roles.map((role) => (
              <div key={role.id} className="border rounded p-4 bg-[color:var(--color-surface)] shadow-sm">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h3 className="font-semibold text-lg">{role.name}</h3>
                    <p className="text-sm text-[color:var(--color-text-muted)]">ID: {role.id}</p>
                    <p className="text-sm mt-2">
                      Права: {role.permissions.length ? role.permissions.join(', ') : 'Нет'}
                    </p>
                    <p className="text-sm mt-1">
                      Кнопки бота: {role.bot_buttons.length ? role.bot_buttons.join(', ') : 'По умолчанию'}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <button className="btn" onClick={() => startRoleEdit(role)}>Изменить</button>
                    <button className="btn btn--danger" onClick={() => deleteRole(role)}>
                      Удалить
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
        {roleForm && (
          <form className="border rounded p-4 bg-[color:var(--color-surface)] space-y-4" onSubmit={submitRole}>
            <h3 className="text-lg font-semibold">
              {isRoleNew ? 'Новая роль' : `Редактирование роли «${roleForm.name}»`}
            </h3>
            <div className="grid md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="block text-sm font-medium text-[color:var(--color-text)]" htmlFor="role-id">
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
                <label className="block text-sm font-medium text-[color:var(--color-text)]" htmlFor="role-name">
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
                    <p className="text-sm font-semibold text-[color:var(--color-text-muted)] mb-1">
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
              <button className="btn bg-[color:var(--color-control-bg)] text-[color:var(--color-text)]" type="button" onClick={cancelRoleForm}>
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
        {isMobile ? (
          <div className="space-y-3">
            {data.users.map((user) => (
              <div key={user.id} className="border rounded-xl bg-[color:var(--color-surface)] shadow-sm overflow-hidden">
                <div className="px-4 py-3 border-b bg-[color:var(--color-bg-subtle)] text-sm font-medium flex items-center justify-between">
                  <span>{user.login || user.display_name || `#${user.id}`}</span>
                  {!user.has_login && (
                    <span className="text-xs font-normal text-[color:var(--color-text-muted)] bg-[color:var(--color-control-bg)] rounded px-2 py-0.5">Бот, без входа в админку</span>
                  )}
                </div>
                <div className="px-4 py-2 space-y-1.5 text-sm">
                  <div className="flex justify-between"><span className="text-[color:var(--color-text-muted)]">ID</span><span>{user.id}</span></div>
                  {user.display_name && (
                    <div className="flex justify-between"><span className="text-[color:var(--color-text-muted)]">Имя</span><span>{user.display_name}</span></div>
                  )}
                  <div className="flex justify-between"><span className="text-[color:var(--color-text-muted)]">Роль</span><span>{user.role_name || '—'}</span></div>
                  <div className="flex justify-between"><span className="text-[color:var(--color-text-muted)]">Права</span><span className="text-right max-w-[60%]">{user.resolved_permissions.length ? user.resolved_permissions.join(', ') : 'нет'}</span></div>
                  <div className="flex justify-between"><span className="text-[color:var(--color-text-muted)]">Кнопки</span><span className="text-right max-w-[60%]">{user.resolved_bot_button_labels.length ? user.resolved_bot_button_labels.join(', ') : 'по умолчанию'}</span></div>
                  <div className="flex justify-between">
                    <span className="text-[color:var(--color-text-muted)]">Сотрудники</span>
                    <span className="text-right max-w-[60%]">
                      {user.resolved_employee_names.length > 0
                        ? user.resolved_employee_names.join(', ')
                        : user.resolved_departments.length ? 'по отделам' : 'все'}
                    </span>
                  </div>
                  {user.resolved_departments.length > 0 && (
                    <div className="flex justify-between"><span className="text-[color:var(--color-text-muted)]">Отделы</span><span className="text-right max-w-[60%]">{user.resolved_departments.join(', ')}</span></div>
                  )}
                  {user.employee_id && (
                    <div className="flex justify-between"><span className="text-[color:var(--color-text-muted)]">Личный кабинет</span><span>сотрудник #{user.employee_id}</span></div>
                  )}
                </div>
                <div className="px-4 py-2 border-t flex justify-end gap-3">
                  <button className="btn" onClick={() => startUserEdit(user)}>Изменить</button>
                  {user.has_login && (
                    <button className="btn btn--danger" onClick={() => deleteUser(user)}>Удалить</button>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="grid gap-3">
            {data.users.map((user) => (
              <div key={user.id} className="border rounded p-4 bg-[color:var(--color-surface)] shadow-sm">
                <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
                  <div className="space-y-1">
                    <h3 className="text-lg font-semibold flex items-center gap-2">
                      {user.login || user.display_name || `#${user.id}`}
                      {!user.has_login && (
                        <span className="text-xs font-normal text-[color:var(--color-text-muted)] bg-[color:var(--color-control-bg)] rounded px-2 py-0.5">Бот, без входа в админку</span>
                      )}
                    </h3>
                    <p className="text-sm text-[color:var(--color-text-muted)]">ID: {user.id}</p>
                    {user.display_name && user.login && (
                      <p className="text-sm text-[color:var(--color-text-muted)]">{user.display_name}</p>
                    )}
                    <p className="text-sm">Роль: {user.role_name || '—'}</p>
                    <p className="text-sm">
                      Итоговые права: {user.resolved_permissions.length ? user.resolved_permissions.join(', ') : 'нет'}
                    </p>
                    <p className="text-sm">
                      Кнопки в боте: {user.resolved_bot_button_labels.length ? user.resolved_bot_button_labels.join(', ') : 'по умолчанию'}
                    </p>
                    {user.resolved_employee_names.length > 0 ? (
                      <p className="text-sm">
                        Доступ к сотрудникам: {user.resolved_employee_names.join(', ')}
                      </p>
                    ) : (
                      <p className="text-sm">
                        Доступ к сотрудникам: {user.resolved_departments.length ? 'по отделам' : 'все'}
                      </p>
                    )}
                    {user.resolved_departments.length > 0 && (
                      <p className="text-sm">
                        Доступные отделы: {user.resolved_departments.join(', ')}
                      </p>
                    )}
                    {user.employee_id && (
                      <p className="text-sm">
                        Личный кабинет: сотрудник #{user.employee_id}
                      </p>
                    )}
                  </div>
                  <div className="flex gap-2">
                    <button className="btn" onClick={() => startUserEdit(user)}>Изменить</button>
                    {user.has_login && (
                      <button className="btn btn--danger" onClick={() => deleteUser(user)}>
                        Удалить
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
        {userForm && (
          <div className="modal-backdrop" onClick={(e) => e.target === e.currentTarget && cancelUserForm()}>
            <form className="modal-card max-w-3xl space-y-4" onSubmit={submitUser}>
            <h3 className="text-lg font-semibold">
              {isUserNew
                ? 'Новый пользователь'
                : `Редактирование пользователя «${userForm.login || userForm.id}»`}
            </h3>
            <div className="grid md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="block text-sm font-medium text-[color:var(--color-text)]" htmlFor="user-id">
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
                <p className="text-xs text-[color:var(--color-text-muted)]">Используйте ID из Telegram для связи с ботом.</p>
              </div>
              <div className="space-y-2">
                <label className="block text-sm font-medium text-[color:var(--color-text)]" htmlFor="user-login">
                  Логин
                </label>
                <input
                  id="user-login"
                  className="input w-full"
                  value={userForm.login}
                  onChange={(e) => setUserForm((prev) => ({ ...prev, login: e.target.value }))}
                  placeholder={isUserNew ? '' : 'Без логина (только для бота)'}
                  required={isUserNew}
                />
                {!isUserNew && !userForm.login && (
                  <p className="text-xs text-[color:var(--color-text-muted)]">
                    Заполните логин и пароль, чтобы выдать доступ в админку.
                  </p>
                )}
              </div>
              <div className="space-y-2">
                <label className="block text-sm font-medium text-[color:var(--color-text)]" htmlFor="user-password">
                  Пароль
                </label>
                <input
                  id="user-password"
                  type="password"
                  className="input w-full"
                  value={userForm.password}
                  onChange={(e) => setUserForm((prev) => ({ ...prev, password: e.target.value }))}
                  placeholder={isUserNew ? '' : 'Оставьте пустым, чтобы не менять'}
                  required={isUserNew || (!userForm.hadLogin && !!userForm.login)}
                />
              </div>
              <div className="space-y-2">
                <label className="block text-sm font-medium text-[color:var(--color-text)]" htmlFor="user-role">
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
            <div className="space-y-2">
              <label className="block text-sm font-medium text-[color:var(--color-text)]" htmlFor="user-employee">
                Привязка к сотруднику (Личный кабинет)
              </label>
              <select
                id="user-employee"
                className="input w-full"
                value={userForm.employee_id}
                onChange={(e) => setUserForm((prev) => ({ ...prev, employee_id: e.target.value }))}
              >
                <option value="">Не привязан</option>
                {data.available_employees.map((emp) => (
                  <option key={emp.id} value={emp.id}>
                    {emp.name}{emp.department ? ` · ${emp.department}` : ''}
                  </option>
                ))}
              </select>
              <p className="text-xs text-[color:var(--color-text-muted)]">
                При входе в Личный кабинет (/employee) этот пользователь увидит данные указанного сотрудника.
              </p>
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
                  onChange={(e) =>
                    setUserForm((prev) => ({
                      ...prev,
                      inheritButtons: e.target.checked,
                    }))
                  }
                />
                <label htmlFor="inherit-buttons" className="text-sm">
                  Использовать настройки кнопок роли
                </label>
              </div>
              {!userForm.inheritButtons && (
                <div className="space-y-3">
                  {Object.entries(buttonGroups).map(([scope, buttons]) => (
                    <div key={scope}>
                      <p className="text-sm font-semibold text-[color:var(--color-text-muted)] mb-1">
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
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="limit-employees"
                  checked={userForm.limitByEmployees}
                  onChange={(e) =>
                    setUserForm((prev) => ({
                      ...prev,
                      limitByEmployees: e.target.checked,
                      allowed_employee_ids: e.target.checked ? prev.allowed_employee_ids : [],
                    }))
                  }
                />
                <label htmlFor="limit-employees" className="text-sm">
                  Ограничить доступ по конкретным сотрудникам
                </label>
              </div>
              {userForm.limitByEmployees && (
                <div className="space-y-2">
                  <select
                    multiple
                    className="input w-full h-40"
                    value={userForm.allowed_employee_ids}
                    onChange={handleEmployeeScopeChange}
                  >
                    {Object.entries(employeesByDepartment).map(([dept, employees]) => (
                      <optgroup key={dept} label={dept}>
                        {employees.map((employee) => (
                          <option key={employee.id} value={employee.id}>
                            {employee.name}
                            {employee.department ? ` · ${employee.department}` : ''}
                          </option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                  <p className="text-xs text-[color:var(--color-text-muted)]">
                    Выбранные сотрудники будут доступны во всех разделах интерфейса.
                  </p>
                </div>
              )}
            </div>
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="limit-departments"
                  checked={userForm.limitByDepartments}
                  onChange={(e) =>
                    setUserForm((prev) => ({
                      ...prev,
                      limitByDepartments: e.target.checked,
                      allowed_departments: e.target.checked ? prev.allowed_departments : [],
                    }))
                  }
                />
                <label htmlFor="limit-departments" className="text-sm">
                  Ограничить доступ по отделам
                </label>
              </div>
              {userForm.limitByDepartments && (
                <div className="grid md:grid-cols-2 gap-2">
                  {availableDepartments.map((dept) => (
                    <label key={dept} className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        value={dept}
                        checked={userForm.allowed_departments.includes(dept)}
                        onChange={handleDepartmentScopeChange}
                      />
                      {dept}
                    </label>
                  ))}
                </div>
              )}
            </div>
            <div className="flex gap-2">
              <button className="btn" type="submit">
                Сохранить
              </button>
              <button className="btn bg-[color:var(--color-control-bg)] text-[color:var(--color-text)]" type="button" onClick={cancelUserForm}>
                Отмена
              </button>
            </div>
            </form>
          </div>
        )}
      </section>

      <section className="space-y-4">
        <h2 className="text-xl font-semibold">Пользователи бота</h2>
        <p className="text-sm text-[color:var(--color-text-muted)]">
          Все, кто хотя бы раз запускал бота (/start), с указанием Telegram ID и юзернейма. Можно привязать
          запись к существующему сотруднику — бот начнёт узнавать его по этому Telegram ID.
        </p>
        <ResponsiveTable
          data={botUsers}
          keyFn={(u) => u.telegram_id}
          emptyText="Пока никто не запускал бота."
          columns={[
            { label: 'Telegram ID', key: 'telegram_id' },
            { label: 'Username', primary: true, render: (u) => (u.username ? `@${u.username}` : '—') },
            { label: 'Имя', render: (u) => [u.first_name, u.last_name].filter(Boolean).join(' ') || '—' },
            { label: 'Первый запуск', render: (u) => fmtDateTime(u.first_seen) },
            { label: 'Последний запуск', render: (u) => fmtDateTime(u.last_seen) },
            {
              label: 'Сотрудник',
              render: (u) =>
                u.employee_id ? (
                  u.employee_name || `#${u.employee_id}`
                ) : (
                  <span className="text-[color:var(--color-text-faint)]">Не привязан</span>
                ),
            },
            {
              label: '',
              isAction: true,
              render: (u) =>
                u.employee_id ? (
                  <button className="btn" onClick={() => editBotUserAccess(u.employee_id)}>
                    ⚙️ Права и меню
                  </button>
                ) : (
                  <div className="flex gap-2 items-center">
                    <select
                      className="input"
                      value={linkSelections[u.telegram_id] || ''}
                      onChange={(e) =>
                        setLinkSelections((prev) => ({ ...prev, [u.telegram_id]: e.target.value }))
                      }
                    >
                      <option value="">Сотрудник…</option>
                      {data.available_employees.map((emp) => (
                        <option key={emp.id} value={emp.id}>
                          {emp.name}{emp.department ? ` · ${emp.department}` : ''}
                        </option>
                      ))}
                    </select>
                    <button
                      className="btn"
                      disabled={!linkSelections[u.telegram_id]}
                      onClick={() => linkBotUser(u.telegram_id)}
                    >
                      Связать
                    </button>
                  </div>
                ),
            },
          ]}
        />
      </section>

      <section className="space-y-4">
        <h2 className="text-xl font-semibold">Пользователи ВКонтакте</h2>
        <p className="text-sm text-[color:var(--color-text-muted)]">
          Заготовка под будущего VK-бота: как только он появится, каждый написавший ему будет попадать сюда —
          так же, как в Telegram выше. Привязка не меняет Telegram-профиль сотрудника, а просто добавляет
          VK как второй канал того же профиля.
        </p>
        <ResponsiveTable
          data={vkBotUsers}
          keyFn={(u) => u.vk_id}
          emptyText="Пока никто не запускал VK-бота."
          columns={[
            { label: 'VK ID', key: 'vk_id' },
            { label: 'Screen name', primary: true, render: (u) => (u.screen_name ? `@${u.screen_name}` : '—') },
            { label: 'Имя', render: (u) => [u.first_name, u.last_name].filter(Boolean).join(' ') || '—' },
            { label: 'Первый запуск', render: (u) => fmtDateTime(u.first_seen) },
            { label: 'Последний запуск', render: (u) => fmtDateTime(u.last_seen) },
            {
              label: 'Сотрудник',
              render: (u) =>
                u.employee_id ? (
                  u.employee_name || `#${u.employee_id}`
                ) : (
                  <span className="text-[color:var(--color-text-faint)]">Не привязан</span>
                ),
            },
            {
              label: '',
              isAction: true,
              render: (u) =>
                u.employee_id ? (
                  <button className="btn" onClick={() => unlinkVkBotUser(u.vk_id)}>
                    Отвязать
                  </button>
                ) : (
                  <div className="flex gap-2 items-center">
                    <select
                      className="input"
                      value={vkLinkSelections[u.vk_id] || ''}
                      onChange={(e) =>
                        setVkLinkSelections((prev) => ({ ...prev, [u.vk_id]: e.target.value }))
                      }
                    >
                      <option value="">Сотрудник…</option>
                      {data.available_employees.map((emp) => (
                        <option key={emp.id} value={emp.id}>
                          {emp.name}{emp.department ? ` · ${emp.department}` : ''}
                        </option>
                      ))}
                    </select>
                    <button
                      className="btn"
                      disabled={!vkLinkSelections[u.vk_id]}
                      onClick={() => linkVkBotUser(u.vk_id)}
                    >
                      Связать
                    </button>
                  </div>
                ),
            },
          ]}
        />
      </section>
    </div>
  );
}
