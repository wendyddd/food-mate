"use client";

import { useState } from "react";
import { Plus } from "lucide-react";
import { useT } from "@/lib/i18n";

interface Props {
  category: string;
  onSubmit: (category: string, content: string) => Promise<void>;
  /** Stagger entrance animation; defaults to after existing cards */
  index?: number;
}

/**
 * Add memory: appears at the end of the grid in the same card style as entries.
 */
export default function MemoryEntryForm({
  category,
  onSubmit,
  index = 0,
}: Props) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [content, setContent] = useState("");
  const [saving, setSaving] = useState(false);

  const handleSubmit = async () => {
    if (!content.trim()) return;
    setSaving(true);
    try {
      await onSubmit(category, content.trim());
      setContent("");
      setOpen(false);
    } finally {
      setSaving(false);
    }
  };

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="memory-entry-card memory-entry-card--add"
        style={{ animationDelay: `${Math.min(index, 12) * 45}ms` }}
      >
        <span className="flex flex-col items-center justify-center gap-2 flex-1">
          <span
            className="w-9 h-9 rounded-full flex items-center justify-center"
            style={{
              background: "var(--accent-bg)",
              color: "var(--accent)",
            }}
          >
            <Plus className="w-4 h-4" />
          </span>
          <span
            className="text-[12px] font-medium"
            style={{ color: "var(--text-secondary)" }}
          >
            {t("memory.add")}
          </span>
        </span>
      </button>
    );
  }

  return (
    <div
      className="memory-entry-card memory-entry-card--add-form"
      style={{ animationDelay: `${Math.min(index, 12) * 45}ms` }}
    >
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        placeholder={t("memory.contentPlaceholder")}
        rows={4}
        className="w-full flex-1 text-[13px] p-2 rounded-lg resize-none outline-none"
        style={{
          background: "var(--bg-page)",
          border: "1px solid var(--border)",
          color: "var(--text-primary)",
        }}
        autoFocus
      />
      <div className="flex gap-2 justify-end mt-auto pt-2">
        <button
          type="button"
          onClick={() => {
            setOpen(false);
            setContent("");
          }}
          className="px-3 py-1 text-[12px] rounded-lg"
          style={{ color: "var(--text-muted)" }}
        >
          {t("common.cancel")}
        </button>
        <button
          type="button"
          onClick={handleSubmit}
          disabled={saving || !content.trim()}
          className="px-3 py-1 text-[12px] rounded-lg font-medium"
          style={{
            background: "var(--accent)",
            color: "white",
            opacity: saving || !content.trim() ? 0.5 : 1,
          }}
        >
          {saving ? t("common.saving") : t("common.save")}
        </button>
      </div>
    </div>
  );
}
