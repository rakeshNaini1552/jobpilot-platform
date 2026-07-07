/**
 * Session store. Access token lives in memory (not persisted — XSS-safe);
 * the refresh token is persisted so reloads can restore the session in
 * Phase 6 via POST /auth/refresh.
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface SessionUser {
  id: string;
  email: string;
  full_name: string;
  role: "USER" | "ADMIN";
}

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: SessionUser | null;
  setSession: (access: string, refresh: string, user: SessionUser) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      setSession: (accessToken, refreshToken, user) =>
        set({ accessToken, refreshToken, user }),
      logout: () => set({ accessToken: null, refreshToken: null, user: null }),
    }),
    {
      name: "jobpilot-auth",
      partialize: (s) => ({ refreshToken: s.refreshToken, user: s.user }),
    },
  ),
);
