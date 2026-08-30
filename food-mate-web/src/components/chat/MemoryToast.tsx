"use client";

import { useEffect } from "react";
import { createPortal } from "react-dom";
import { Brain, X } from "lucide-react";

interface Props {
  message: string | null;
  onClose: () => void;
}

/** Toast auto-dismiss duration in milliseconds */
const AUTO_DISMISS_MS = 3000;

/**
 * Lightweight toast that memory was updated automatically.
 * Shown after the assistant reply fully finishes; portaled and fixed at the bottom center of the viewport.
 *
 * @param message - Toast copy; hidden when null
 * @param onClose - Close callback
 * @returns Toast node, or null
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
