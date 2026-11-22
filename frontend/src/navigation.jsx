import React, { createContext, useContext, useEffect, useState } from 'react';

const Navigation = createContext({ path: '/', navigate: () => {} });
export const useNavigation = () => useContext(Navigation);

export function createNavigator(browser, update) {
  const read = () => update(browser.location.pathname);
  browser.addEventListener('popstate', read);
  return {
    go(path) { if (browser.location.pathname !== path) browser.history.pushState(null, '', path); read(); browser.scrollTo(0, 0); },
    dispose() { browser.removeEventListener('popstate', read); },
  };
}

export function NavigationProvider({ children, initialPath }) {
  const [path, setPath] = useState(initialPath || (typeof window === 'undefined' ? '/' : window.location.pathname));
  useEffect(() => {
    const navigator = createNavigator(window, setPath);
    navigationRef.current = navigator;
    return () => { navigator.dispose(); navigationRef.current = null; };
  }, []);
  const navigationRef = React.useRef(null);
  const navigate = target => { if (navigationRef.current) navigationRef.current.go(target); else setPath(target); };
  return <Navigation.Provider value={{ path, navigate }}>{children}</Navigation.Provider>;
}

export function Link({ to, children, onClick, ...props }) {
  const { navigate } = useNavigation();
  return <a href={to} {...props} onClick={event => {
    onClick?.(event);
    if (!event.defaultPrevented && event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) {
      event.preventDefault(); navigate(to);
    }
  }}>{children}</a>;
}
