"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import Sidebar, {
  SIDEBAR_WIDTH_COLLAPSED,
  SIDEBAR_WIDTH_EXPANDED,
} from "@/components/layout/Sidebar";
import ChatPanel from "@/components/chat/ChatPanel";
import { useApp } from "@/lib/store";

/**
 * 用户会话下的聊天页面。
 */
export default function UserChatPage() {
  const searchParams = useSearchParams();
  const {
    sidebarOpen,
    sessionId,
    setSessionId,
  } = useApp();
  const [highlightQuote, setHighlightQuote] = useState<string | null>(null);
  /** 已处理的 session+quote 组合，避免重复切换；同 session 不同 quote 仍可重新定位 */
  const handledQueryRef = useRef<string | null>(null);

  /** 定位完成后清除 quote，避免重复触发 */
  const handleHighlightDone = useCallback(() => {
    setHighlightQuote(null);
  }, []);

  // 从记忆页跳转：/?session=session-xxx&quote=... 打开对应会话并定位原话
  useEffect(() => {
    const target = searchParams.get("session");
    if (!target) return;

    const quote = searchParams.get("quote");
    const queryKey = `${target}\0${quote ?? ""}`;
    if (queryKey === handledQueryRef.current) return;
    handledQueryRef.current = queryKey;

    // 同 session 仅换 quote 时不重复加载，避免闪烁
    if (target !== sessionId) {
      setSessionId(target);
    }
    setHighlightQuote(quote);
  }, [searchParams, sessionId, setSessionId]);

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
      <div className="flex-1 flex overflow-hidden">
        <div className="flex-1 overflow-hidden">
          <ChatPanel
            highlightQuote={highlightQuote}
            onHighlightDone={handleHighlightDone}
          />
        </div>
      </div>
    </div>
  );
}
