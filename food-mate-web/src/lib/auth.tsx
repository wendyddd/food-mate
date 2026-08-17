/**
 * 用户登录态 Context，管理 uid、URL session 与记忆 UI 可见性。
 *
 * is_show（账号字段）表示是否展示调试/记忆相关 UI：
 * 1 = 展示，0 = 隐藏；登录后按账号固定取值，不可在会话内切换。
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
  /** 是否展示调试/记忆相关 UI（由账号 is_show 决定） */
  isShow: boolean;
}

interface AuthContextValue extends AuthState {
  loading: boolean;
  /** 清除登录态并跳转到登录页 */
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/**
 * 为受保护路由提供用户认证上下文。
 *
 * 参数:
 * userSession (string): URL 中的 session 标识
 * children (React.ReactNode): 子组件
 *
 * 返回:
 * JSX.Element
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
   * 退出登录：清除内存中的 session，并跳转到登录页。
   *
   * 返回:
   * void
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
 * 获取当前登录用户信息。
 *
 * 返回:
 * AuthContextValue
 */
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}
