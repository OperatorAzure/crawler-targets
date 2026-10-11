import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import * as client from './api.js';
import { Spinner } from './ui.jsx';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    client.restoreSession().then(setUser).catch(() => setUser(null)).finally(() => setReady(true));
  }, []);

  useEffect(() => {
    client.onSessionExpired(() => {
      setUser(null);
      const next = window.location.pathname + window.location.search;
      navigate(`/login?expired=1&next=${encodeURIComponent(next)}`, { replace: true });
    });
  }, [navigate]);

  const signIn = useCallback(async (username, password) => {
    setUser(await client.login(username, password));
  }, []);

  const signUp = useCallback(async (form) => {
    setUser(await client.register(form));
  }, []);

  const signOut = useCallback(async () => {
    await client.logout();
    setUser(null);
  }, []);

  const reload = useCallback(async () => setUser(await client.api('/api/me')), []);

  return <AuthContext.Provider value={{ user, ready, signIn, signUp, signOut, reload }}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);

export function RequireAuth({ roles, children }) {
  const { user, ready } = useAuth();
  const location = useLocation();
  if (!ready) return <div className="d-grid" style={{ minHeight: '100vh', placeItems: 'center' }}><Spinner /></div>;
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} replace />;
  if (roles && !roles.includes(user.role)) {
    return <Navigate to="/forbidden" replace />;
  }
  return children;
}
