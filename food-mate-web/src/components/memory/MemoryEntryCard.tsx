"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Pencil, Trash2, Check, X, ArrowUpRight, History } from "lucide-react";
import {
  MEMORY_CATEGORIES,
  type MemoryCategory,
  type MemoryEntry,
} from "@/lib/types";
import { useAuth } from "@/lib/auth";
import { useT, type MessageKey } from "@/lib/i18n";
import { getSourceVisual } from "@/lib/memoryVisuals";
import { splitMemoryKeywords } from "@/lib/memoryKeywords";
import MemoryRevisionDialog from "./MemoryRevisionDialog";

/** localStorage key prefix for the last-seen revision timestamp */
const SEEN_REVISION_KEY_PREFIX = "foodmate_memory_rev_seen_";

/**
 * Read the latest revision timestamp marked as seen for an entry.
 *
 * @param entryId - Memory entry ID
 * @returns Seen cutoff time in seconds; 0 if never seen
 */
function readSeenRevisionAt(entryId: string): number {
  if (typeof window === "undefined") return 0;
  try {
    const raw = localStorage.getItem(`${SEEN_REVISION_KEY_PREFIX}${entryId}`);
    const n = raw ? Number(raw) : 0;
    return Number.isFinite(n) ? n : 0;
  } catch {
    return 0;
  }
}

/**
 * Mark an entry as seen up to the given revision time.
 *
 * @param entryId - Memory entry ID
 * @param changedAt - Latest changed_at that has been seen
 */
function writeSeenRevisionAt(entryId: string, changedAt: number): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(
      `${SEEN_REVISION_KEY_PREFIX}${entryId}`,
      String(changedAt),
    );
  } catch {
    /* ignore */
  }
}

interface Props {
  entry: MemoryEntry;
  index?: number;
  /** Whether this card is the highlight target jumped to from a chat citation */
  highlighted?: boolean;
  onUpdate: (id: string, content: string, category: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
}

/**
 * Plain-card memory entry with inline edit, delete, revision history, and source tracing.
 */
export default function MemoryEntryCard({
  entry,
  index = 0,
  highlighted = false,
  onUpdate,
  onDelete,
}: Props) {
  const { userSession } = useAuth();
  const t = useT();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(entry.content);
  const [draftCategory, setDraftCategory] = useState(entry.category);
  const [saving, setSaving] = useState(false);
  const [showRevisions, setShowRevisions] = useState(false);
  const [seenRevisionAt, setSeenRevisionAt] = useState(0);

  const sourceVisual = getSourceVisual(entry.source_type);
  const SourceIcon = sourceVisual.icon;
  const revisions = entry.revisions ?? [];
  const latestRevisionAt =
    revisions.length > 0
      ? Math.max(...revisions.map((r) => r.changed_at || 0))
      : 0;
  const unreadCount = revisions.filter(
    (r) => (r.changed_at || 0) > seenRevisionAt,
  ).length;

  useEffect(() => {
    setSeenRevisionAt(readSeenRevisionAt(entry.id));
  }, [entry.id]);

  /**
   * Open revision history and clear the unread badge.
   */
  const openRevisions = () => {
    setShowRevisions(true);
    if (latestRevisionAt > 0) {
      writeSeenRevisionAt(entry.id, latestRevisionAt);
      setSeenRevisionAt(latestRevisionAt);
    }
  };

  const handleSave = async () => {
    if (!draft.trim()) {
      setEditing(false);
      return;
    }
    const contentChanged = draft !== entry.content;
    const categoryChanged = draftCategory !== entry.category;
    if (!contentChanged && !categoryChanged) {
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      await onUpdate(entry.id, draft.trim(), draftCategory);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm(t("memory.deleteConfirm"))) return;
    await onDelete(entry.id);
  };

  const formatDate = (ts: number) =>
    new Date(ts * 1000).toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });

  /**
   * Build a source-session link; include quote when present so chat can locate the extraction message.
   */
  const sessionHref = (() => {
    if (!userSession || !entry.source_session_id) return null;
    const params = new URLSearchParams({
      session: entry.source_session_id,
    });
    if (entry.source_quote) {
      params.set("quote", entry.source_quote);
    }
    return `/${userSession}?${params.toString()}`;
  })();

  return (
    <div
      id={entry.id}
      className={`memory-entry-card${highlighted ? " memory-entry-card--highlight" : ""}`}
      style={{ animationDelay: `${Math.min(index, 12) * 45}ms` }}
    >
      {editing ? (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <label
              className="text-[11px] shrink-0"
              style={{ color: "var(--text-muted)" }}
            >
              {t("memory.categoryLabel")}
            </label>
            <select
              value={draftCategory}
              onChange={(e) => setDraftCategory(e.target.value)}
              className="flex-1 text-[12px] px-2 py-1.5 rounded-lg outline-none"
              style={{
                background: "var(--bg-page)",
                border: "1px solid var(--border)",
                color: "var(--text-primary)",
              }}
            >
              {MEMORY_CATEGORIES.map((cat) => (
                <option key={cat} value={cat}>
                  {t(`category.${cat as MemoryCategory}` as MessageKey)}
                </option>
              ))}
            </select>
          </div>
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={3}
            className="w-full text-[13px] p-2 rounded-lg resize-none outline-none"
            style={{
              background: "var(--bg-page)",
              border: "1px solid var(--border-accent)",
              color: "var(--text-primary)",
            }}
            autoFocus
          />
          <div className="flex gap-2 justify-end">
            <button
              onClick={() => {
                setDraft(entry.content);
                setDraftCategory(entry.category);
                setEditing(false);
              }}
              className="p-1.5 rounded-lg hover:opacity-80"
              style={{ color: "var(--text-muted)" }}
            >
              <X className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="p-1.5 rounded-lg hover:opacity-80"
              style={{ color: "var(--accent)" }}
            >
              <Check className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      ) : (
        <div className="flex items-start gap-2 flex-1 min-h-0">
          <div className="flex-1 min-w-0" title={entry.content}>
            <span
              className="inline-flex max-w-full items-center px-2.5 py-1 rounded-md text-[13px] leading-snug font-medium"
              style={{
                background: "var(--accent-bg)",
                color: "var(--text-primary)",
                border:
                  "1px solid color-mix(in srgb, var(--accent) 22%, var(--border))",
              }}
            >
              {splitMemoryKeywords(entry.content, 1)[0] || entry.content}
            </span>
          </div>
          <div className="flex gap-0.5 shrink-0 -mt-0.5">
            <button
              type="button"
              onClick={openRevisions}
              className="p-1.5 rounded-lg hover:opacity-80 relative"
              style={{ color: "var(--text-muted)" }}
              title={t("memory.revisionButton")}
              aria-label={t("memory.revisionButton")}
            >
              <History className="w-3.5 h-3.5" />
              {unreadCount > 0 && (
                <span
                  className="absolute -top-0.5 -right-0.5 min-w-[14px] h-[14px] px-0.5 rounded-full text-[9px] font-semibold flex items-center justify-center"
                  style={{
                    background: "var(--accent)",
                    color: "#fff",
                  }}
                >
                  {unreadCount > 9 ? "9+" : unreadCount}
                </span>
              )}
            </button>
            <button
              onClick={() => {
                setDraft(entry.content);
                setDraftCategory(entry.category);
                setEditing(true);
              }}
              className="p-1.5 rounded-lg hover:opacity-80"
              style={{ color: "var(--text-muted)" }}
              title={t("common.edit")}
            >
              <Pencil className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={handleDelete}
              className="p-1.5 rounded-lg hover:opacity-80"
              style={{ color: "var(--text-muted)" }}
              title={t("common.delete")}
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}

      <div className="mt-auto pt-3 flex flex-wrap items-center gap-2">
        {sessionHref ? (
          <Link
            href={sessionHref}
            title={t("memory.viewSource")}
            aria-label={t("memory.viewSource")}
            className="inline-flex items-center gap-1 pl-1.5 pr-1 py-0.5 rounded-md text-[10px] font-medium hover:opacity-80 transition-opacity"
            style={{
              background: sourceVisual.bg,
              color: sourceVisual.color,
            }}
          >
            <SourceIcon className="w-3 h-3" />
            {t(sourceVisual.labelKey)}
            <ArrowUpRight className="w-3 h-3 opacity-80" strokeWidth={2.25} />
          </Link>
        ) : (
          <span
            className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[10px] font-medium"
            style={{
              background: sourceVisual.bg,
              color: sourceVisual.color,
            }}
          >
            <SourceIcon className="w-3 h-3" />
            {t(sourceVisual.labelKey)}
          </span>
        )}
      </div>

      <div
        className="flex items-center gap-2 mt-2 text-[10px]"
        style={{ color: "var(--text-muted)" }}
      >
        <span>{formatDate(entry.updated_at)}</span>
      </div>

      {showRevisions && (
        <MemoryRevisionDialog
          revisions={revisions}
          fallbackSessionId={entry.source_session_id}
          fallbackQuote={entry.source_quote}
          onClose={() => setShowRevisions(false)}
        />
      )}
    </div>
  );
}
