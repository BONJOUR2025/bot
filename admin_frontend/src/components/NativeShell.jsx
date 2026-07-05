import { useEffect, useState } from 'react';
import { WifiOff } from 'lucide-react';

// Everything here is a no-op in a plain browser tab — it only does
// something meaningful inside the Capacitor iOS shell (admin_frontend/ios).
export default function NativeShell() {
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    let removeListener = () => {};

    import('@capacitor/core').then(({ Capacitor }) => {
      // Hide the native splash screen once React has actually mounted and
      // painted something — launchAutoHide is off (see capacitor.config.json)
      // specifically so this fades in instead of a blank flash while the
      // remote page's JS bundle was still loading.
      if (Capacitor.isNativePlatform()) {
        import('@capacitor/splash-screen').then(({ SplashScreen }) => {
          SplashScreen.hide({ fadeOutDuration: 300 }).catch(() => {});
        });
      }

      import('@capacitor/network').then(({ Network }) => {
        Network.getStatus().then((s) => setOffline(!s.connected)).catch(() => {});
        Network.addListener('networkStatusChange', (s) => setOffline(!s.connected)).then((handle) => {
          removeListener = () => handle.remove();
        });
      });
    });

    return () => removeListener();
  }, []);

  if (!offline) return null;
  return (
    <div className="fixed top-0 inset-x-0 z-[9999] bg-[color:var(--color-danger)] text-white text-sm px-4 py-2 flex items-center justify-center gap-2"
         style={{ paddingTop: 'calc(0.5rem + env(safe-area-inset-top, 0px))' }}>
      <WifiOff size={15} /> Нет подключения к интернету
    </div>
  );
}
