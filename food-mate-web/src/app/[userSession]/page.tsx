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
 * Chat page under a user session.
 */
export default function UserChatPage() {
  const searchParams = useSearchParams();
  const {
    sidebarOpen,
    sessionId,
    setSessionId,
  } = useApp();
  const [highlightQuote, setHighlightQuote] = useState<string | null>(null);
  /** Processed session+quote combo to avoid repeat switches; a new quote on the same session can still re-locate */
  const handledQueryRef = useRef<string | null>(null);

  /** Clear quote after locate finishes to avoid retriggering */
  const handleHighlightDone = useCallback(() => {
    setHighlightQuote(null);
  }, []);

  // Jump from memory page: /?session=session-xxx&quote=... opens that session and locates the original quote
  useEffect(() => {
    const target = searchParams.get("session");
    if (!target) return;

    const quote = searchParams.get("quote");
    const queryKey = `${target}\0${quote ?? ""}`;
    if (queryKey === handledQueryRef.current) return;
    handledQueryRef.current = queryKey;

    // Same session, new quote only: skip reload to avoid flicker
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
