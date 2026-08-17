"use client";

import { useEffect } from "react";
import { createPortal } from "react-dom";
import { Brain, X } from "lucide-react";

interface Props {
  message: string | null;
  onClose: () => void;
}

/** Toast 自动关闭时长（毫秒） */
const AUTO_DISMISS_MS = 3000;

/**
 * 轻量 Toast，提示记忆已自动更新。
 * 在本轮助手回复完全输出后再展示；通过 Portal 固定于视口底部居中。
 *
 * 参数:
 *   message (string | null): 提示文案，null 时不展示
 *   onClose (() => void): 关闭回调
 *
 * 返回:
 *   JSX.Element | null: Toast 节点
 */
export default function MemoryToast({ message, onClose }: Props) {
  useEffect(() => {
    if (!message) return;
    const timer = setTimeout(onClose, AUTO_DISMISS_MS);
    return () => clearTimeout(timer);
  }, [message, onClose]);

  if (!message || typeof document === "undefined") {
    return null;
  }

  return createPortal(
    <div
      role="status"
      translate="no"
      className="fixed left-1/2 -translate-x-1/2 z-[200] animate-fade-in-scale"
      style={{ bottom: "calc(5.5rem + env(safe-area-inset-bottom, 0px))" }}
    >
      <div
        className="flex items-center gap-2 px-4 py-2.5 rounded-xl shadow-lg"
        style={{
          background: "var(--bg-surface)",
          border: "1px solid var(--border-accent)",
          color: "var(--text-primary)",
        }}
      >
        <Brain
          className="w-4 h-4 shrink-0"
          style={{ color: "var(--accent)" }}
        />
        <span className="text-[13px] whitespace-nowrap">{message}</span>
        <button
          type="button"
          onClick={onClose}
          className="ml-2 p-0.5 rounded hover:opacity-70"
          style={{ color: "var(--text-muted)" }}
          aria-label="Close"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>,
    document.body,
  );
}
