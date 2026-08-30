"use client";

import { AuthProvider } from "@/lib/auth";
import { AppProvider } from "@/lib/store";

/**
 * User-session route layout: verify the session and provide auth plus global state for child pages.
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
