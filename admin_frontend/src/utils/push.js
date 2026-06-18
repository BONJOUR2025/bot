import api from '../api.js';

function urlB64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const rawData = atob(base64);
  return Uint8Array.from([...rawData].map((c) => c.charCodeAt(0)));
}

const SW_PATH = '/admin/sw.js';

export function isIosNonStandalone() {
  const isIos = /iP(hone|od|ad)/.test(navigator.userAgent) ||
    (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const isStandalone =
    window.navigator.standalone === true ||
    window.matchMedia('(display-mode: standalone)').matches;
  return isIos && !isStandalone;
}

export async function registerSW() {
  if (!('serviceWorker' in navigator)) return null;
  const reg = await navigator.serviceWorker.register(SW_PATH);
  await navigator.serviceWorker.ready;
  return reg;
}

export async function subscribePush(employeeId) {
  if (!('PushManager' in window)) throw new Error('Push не поддерживается браузером');

  const reg = await registerSW();
  if (!reg) throw new Error('Service Worker не зарегистрирован');

  const { data } = await api.get('/push/vapid-public-key');
  const applicationServerKey = urlB64ToUint8Array(data.key);

  const subscription = await reg.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey,
  });

  await api.post('/push/subscribe', {
    employee_id: employeeId,
    subscription: subscription.toJSON(),
  });

  return subscription;
}

export async function unsubscribePush(employeeId) {
  if (!('serviceWorker' in navigator)) return;

  const reg = await navigator.serviceWorker.getRegistration(SW_PATH);
  if (!reg) return;

  const subscription = await reg.pushManager.getSubscription();
  if (!subscription) return;

  const endpoint = subscription.endpoint;
  await subscription.unsubscribe();
  await api.post('/push/unsubscribe', { employee_id: employeeId, endpoint });
}

export async function getPushState(employeeId) {
  const iosNonStandalone = isIosNonStandalone();

  if (!window.isSecureContext) {
    return { supported: false, notSecure: true, subscribed: false, iosNonStandalone };
  }
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
    return { supported: false, subscribed: false, iosNonStandalone };
  }

  const permission = Notification.permission;
  if (permission === 'denied') {
    return { supported: true, subscribed: false, denied: true, iosNonStandalone };
  }

  const reg = await navigator.serviceWorker.getRegistration(SW_PATH);
  if (!reg) return { supported: true, subscribed: false, iosNonStandalone };

  const subscription = await reg.pushManager.getSubscription();
  return { supported: true, subscribed: !!subscription, iosNonStandalone };
}
