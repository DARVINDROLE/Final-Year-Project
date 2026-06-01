import { useState, useEffect, useCallback } from 'react';
import {
  getMe,
  login as apiLogin,
  register as apiRegister,
  logout as apiLogout,
  setOwnerSettings as apiSetOwnerSettings,
  type User,
} from '@/lib/api';

interface AuthState {
  user: User | null;
  loading: boolean;
  error: string | null;
}

export function useAuth() {
  const [state, setState] = useState<AuthState>({ user: null, loading: true, error: null });

  const checkAuth = useCallback(async () => {
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const user = await getMe();
      setState({ user, loading: false, error: null });
    } catch {
      setState({ user: null, loading: false, error: null });
    }
  }, []);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  const login = useCallback(async (username: string, password: string) => {
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const { user } = await apiLogin(username, password);
      setState({ user, loading: false, error: null });
      return true;
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Login failed';
      setState({ user: null, loading: false, error: msg });
      return false;
    }
  }, []);

  const register = useCallback(async (username: string, password: string, name: string) => {
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const { user } = await apiRegister(username, password, name);
      setState({ user, loading: false, error: null });
      return true;
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Registration failed';
      setState({ user: null, loading: false, error: msg });
      return false;
    }
  }, []);

  const logout = useCallback(async () => {
    await apiLogout();
    setState({ user: null, loading: false, error: null });
  }, []);

  const setVacationMode = useCallback(async (next: boolean) => {
    // Optimistic update — revert if the API call fails so the UI doesn't lie.
    setState((s) => (s.user ? { ...s, user: { ...s.user, vacation_mode: next } } : s));
    try {
      const settings = await apiSetOwnerSettings({ vacation_mode: next });
      setState((s) =>
        s.user ? { ...s, user: { ...s.user, vacation_mode: settings.vacation_mode } } : s,
      );
      return true;
    } catch (err) {
      setState((s) => (s.user ? { ...s, user: { ...s.user, vacation_mode: !next } } : s));
      const msg = err instanceof Error ? err.message : 'Failed to update vacation mode';
      setState((s) => ({ ...s, error: msg }));
      return false;
    }
  }, []);

  return {
    user: state.user,
    loading: state.loading,
    error: state.error,
    login,
    register,
    logout,
    setVacationMode,
    checkAuth,
    isAuthenticated: !!state.user,
  };
}
