/**
 * Auth context for uid, URL session, and memory UI visibility.
 *
 * is_show (account field) controls debug/memory UI:
 * 1 = show, 0 = hide; fixed per account after login and cannot be toggled in-session.
 */

"use client";

import React, {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
} from "react";
import { useRouter } from "next/navigation";
import { setUserSession, verifySession } from "./api";

export interface AuthState {
  uid: string;
  userSession: string;
  nickname: string;
  /** Whether to show debug/memory UI (from account is_show) */
  isShow: boolean;
}

interface AuthContextValue extends AuthState {
  loading: boolean;
  /** Clear auth state and navigate to the login page */
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/**
 * Provide auth context for protected routes.
 *
 * @param userSession - Session id from the URL
 * @param children - Child components
 * @returns JSX element
 */
export function AuthProvider({
  userSession,
  children,
}: {
  userSession: string;
  children: React.ReactNode;
}) {
  const router = useRouter();
  const [auth, setAuth] = useState<AuthState | null>(null);
  const [loading, setLoading] = useState(true);

  const bootstrap = useCallback(async () => {
    try {
      const info = await verifySession(userSession);
      setUserSession(info.session);
      setAuth({
        uid: info.uid,
        userSession: info.session,
        nickname: info.nickname || info.uid,
        isShow: info.is_show === 1,
      });
    } catch {
      setUserSession(null);
      router.replace("/login");
    } finally {
      setLoading(false);
    }
  }, [userSession, router]);

  /**
   * Sign out: clear the in-memory session and navigate to the login page.
   */
  const logout = useCallback(() => {
    setUserSession(null);
    setAuth(null);
    router.replace("/login");
  }, [router]);

  useEffect(() => {
    bootstrap();
  }, [bootstrap]);

  if (loading || !auth) {
    return (
      <div
        className="h-screen flex items-center justify-center"
        style={{ background: "var(--bg-page)", color: "var(--text-muted)" }}
      >
        <p className="text-sm">Loading...</p>
      </div>
    );
  }

  return (
    <AuthContext.Provider
      value={{
        ...auth,
        loading,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

/**
 * Get the current signed-in user.
 *
 * @returns AuthContextValue
 */
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}
