"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Sidebar, {
  SIDEBAR_WIDTH_COLLAPSED,
  SIDEBAR_WIDTH_EXPANDED,
} from "@/components/layout/Sidebar";
import MemoryEntryPanel from "@/components/memory/MemoryEntryPanel";
import { useApp } from "@/lib/store";
import { useAuth } from "@/lib/auth";

/**
 * Memory management page under a user session (structured entry editor).
 * Hidden (Black-box) memory UI cannot be accessed and redirects back to chat.
 */
export default function UserMemoryPage() {
  const { sidebarOpen } = useApp();
  const { isShow, userSession } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isShow) {
      router.replace(`/${userSession}`);
    }
  }, [isShow, userSession, router]);

  if (!isShow) {
    return null;
  }

  return (
    <div
      className="h-screen flex overflow-hidden"
      style={{ background: "var(--bg-page)" }}
    >
      <div
        className={`shrink-0 overflow-hidden transition-[width] duration-300 ease-in-out ${sidebarOpen ? SIDEBAR_WIDTH_EXPANDED : SIDEBAR_WIDTH_COLLAPSED}`}
      >
        <Sidebar />
      </div>
      <div className="flex-1 overflow-hidden">
        <MemoryEntryPanel />
      </div>
    </div>
  );
}
