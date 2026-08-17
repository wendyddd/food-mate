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
 * 用户会话下的记忆管理页面（结构化条目编辑）。
 * 记忆 UI 隐藏（Black-box）时无法访问，会被重定向回聊天页。
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
