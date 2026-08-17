"use client";

import { AlertTriangle, Info } from "lucide-react";
import { useT } from "@/lib/i18n";

interface Props {
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ConfirmDialog({
  title,
  message,
  confirmText,
  cancelText,
  danger = false,
  onConfirm,
  onCancel,
}: Props) {
  const t = useT();
  const confirmLabel = confirmText ?? t("common.confirm");
  const cancelLabel = cancelText ?? t("common.cancel");
  return (
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center p-4 animate-fade-in"
      style={{ background: "rgba(0,0,0,0.45)", backdropFilter: "blur(4px)" }}
      onClick={onCancel}
    >
      <div
        className="w-full max-w-[360px] rounded-2xl shadow-2xl p-6 space-y-4 animate-fade-in-scale"
        style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Icon + Title */}
        <div className="flex items-start gap-3">
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
            style={{
              background: danger ? "rgba(239,68,68,0.1)" : "var(--accent-bg)",
            }}
          >
            {danger ? (
              <AlertTriangle className="w-5 h-5 text-red-500" />
            ) : (
              <Info className="w-5 h-5" style={{ color: "var(--accent)" }} />
            )}
          </div>
          <div>
            <h3
              className="text-[15px] font-semibold leading-tight"
              style={{ color: "var(--text-primary)" }}
            >
              {title}
            </h3>
            <p
              className="text-[13px] mt-1.5 leading-relaxed"
              style={{ color: "var(--text-secondary)" }}
            >
              {message}
            </p>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center justify-end gap-2 pt-2">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-[13px] font-medium rounded-xl transition-all hover:opacity-80"
            style={{
              color: "var(--text-secondary)",
              background: "var(--bg-page)",
              border: "1px solid var(--border)",
            }}
          >
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            className="px-4 py-2 text-[13px] font-medium text-white rounded-xl transition-all hover:opacity-90 active:scale-[0.98]"
            style={{
              background: danger ? "#ef4444" : "var(--accent)",
            }}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
