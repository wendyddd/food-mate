"use client";

import { AuthProvider } from "@/lib/auth";
import { AppProvider } from "@/lib/store";

/**
 * 用户会话路由布局：校验 session 并为子页面提供认证与全局状态。
 */
export default function UserSessionLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: { userSession: string };
}) {
  return (
    <AuthProvider userSession={params.userSession}>
      <AppProvider>{children}</AppProvider>
    </AuthProvider>
  );
}
