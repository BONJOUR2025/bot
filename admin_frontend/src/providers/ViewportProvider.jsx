import { createContext, useContext, useEffect, useMemo, useState } from 'react';

const defaultState = {
  width: 1440,
  height: 900,
  isMobile: false,
  isTablet: false,
  isDesktop: true,
  platform: 'desktop',
};

function detectPlatform(width) {
  if (typeof navigator === 'undefined') {
    return 'desktop';
  }

  const ua =
    navigator.userAgent ||
    navigator.vendor ||
    (typeof window !== 'undefined' && window.opera ? window.opera : '');
  const isIOS = /iPad|iPhone|iPod/.test(ua);
  const isAndroid = /Android/.test(ua);
  const isTabletUA = /iPad|Tablet/.test(ua);

  if (isIOS && width <= 834) {
    return 'iphone';
  }
  if (isIOS) {
    return 'ipad';
  }
  if (isAndroid && width >= 600 && width < 1024) {
    return 'android-tablet';
  }
  if (isAndroid && width < 600) {
    return 'android-phone';
  }
  if (isTabletUA) {
    return 'tablet';
  }
  return 'desktop';
}

function computeState() {
  if (typeof window === 'undefined') {
    return defaultState;
  }

  const width = window.innerWidth;
  const height = window.innerHeight;
  const platform = detectPlatform(width);

  const isMobileWidth = width < 768;
  const isTabletWidth = width >= 768 && width < 1180;

  const platformMobile = /iphone|phone/.test(platform);
  const platformTablet = /ipad|tablet/.test(platform);

  const isMobile = isMobileWidth || platformMobile;
  const isTablet = (!isMobile && isTabletWidth) || (!isMobile && platformTablet);
  const isDesktop = !isMobile && !isTablet;

  return {
    width,
    height,
    isMobile,
    isTablet,
    isDesktop,
    platform,
  };
}

const ViewportContext = createContext(defaultState);

export function ViewportProvider({ children }) {
  const [state, setState] = useState(() => computeState());

  useEffect(() => {
    const handler = () => {
      window.requestAnimationFrame(() => {
        setState(computeState());
      });
    };

    handler();
    window.addEventListener('resize', handler);
    window.addEventListener('orientationchange', handler);

    return () => {
      window.removeEventListener('resize', handler);
      window.removeEventListener('orientationchange', handler);
    };
  }, []);

  const value = useMemo(() => state, [state]);

  return <ViewportContext.Provider value={value}>{children}</ViewportContext.Provider>;
}

export function useViewport() {
  return useContext(ViewportContext);
}
