"use client";

import { createPortal } from "react-dom";
import Link from "next/link";
import { ArrowUpRight, History, X } from "lucide-react";
import type { MemoryRevision } from "@/lib/types";
import { useAuth } from "@/lib/auth";
import { useT, type MessageKey } from "@/lib/i18n";
import { getSourceVisual } from "@/lib/memoryVisuals";
import type { MemoryCategory } from "@/lib/types";

interface Props {
  revisions: MemoryRevision[];
  onClose: () => void;
  /** 条目级来源会话，作修订记录缺省回退 */
  fallbackSessionId?: string | null;
  /** 条目级原话摘录，作修订记录缺省回退 */
  fallbackQuote?: string | null;
}

/**
 * 构造跳转到聊天页并定位原话的链接。
 *
 * 参数:
 * userSession (string): 当前用户会话路径段
 * sessionId (string | null | undefined): 来源会话 ID
 * quote (string | null | undefined): 原话摘录
 *
 * 返回:
 * string | null: 可跳转 href；信息不足则为 null
 */
function buildSessionHref(
  userSession: string | null | undefined,
  sessionId: string | null | undefined,
  quote: string | null | undefined,
): string | null {
  if (!userSession || !sessionId) return null;
  const params = new URLSearchParams({ session: sessionId });
  if (quote) params.set("quote", quote);
  return `/${userSession}?${params.toString()}`;
}

/**
 * 记忆修改记录弹层：展示每次修改的前后内容与时间。
 * 通过 Portal 挂到 body，避免被卡片 transform / 分区 overflow 裁切。
 * 「聊天记录」可点击跳转到触发该次修改的对话位置。
 */
export default function MemoryRevisionDialog({
  revisions,
  onClose,
  fallbackSessionId = null,
  fallbackQuote = null,
}: Props) {
  const t = useT();
  const { userSession } = useAuth();

  /**
   * 格式化时间戳为本地可读字符串。
   *
   * 参数:
   * ts (number): Unix 秒级时间戳
   *
   * 返回:
   * string: 本地化时间文案
   */
  const formatDate = (ts: number) =>
    new Date(ts * 1000).toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });

  // 新→旧展示
  const ordered = [...revisions].reverse();

  const dialog = (
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center p-4 animate-fade-in"
      style={{ background: "rgba(0,0,0,0.45)", backdropFilter: "blur(4px)" }}
      onClick={onClose}
    >
      <div
        className="w-full max-w-[420px] max-h-[80vh] rounded-2xl shadow-2xl flex flex-col animate-fade-in-scale"
        style={{
          background: "var(--bg-surface)",
          border: "1px solid var(--border)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          className="flex items-center justify-between gap-3 px-5 py-4 shrink-0"
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          <div className="flex items-center gap-2.5 min-w-0">
            <div
              className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
              style={{ background: "var(--accent-bg)" }}
            >
              <History
                className="w-4 h-4"
                style={{ color: "var(--accent)" }}
              />
            </div>
            <div className="min-w-0">
              <h3
                className="text-[15px] font-semibold truncate"
                style={{ color: "var(--text-primary)" }}
              >
                {t("memory.revisionTitle")}
              </h3>
              <p
                className="text-[11px] mt-0.5"
                style={{ color: "var(--text-muted)" }}
              >
                {t("memory.revisionCount", { count: revisions.length })}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg hover:opacity-80"
            style={{ color: "var(--text-muted)" }}
            aria-label={t("common.close")}
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
          {ordered.length === 0 ? (
            <p
              className="text-[13px] text-center py-8"
              style={{ color: "var(--text-muted)" }}
            >
              {t("memory.revisionEmpty")}
            </p>
          ) : (
            ordered.map((rev, index) => {
              const sourceVisual = getSourceVisual(rev.source_type);
              const SourceIcon = sourceVisual.icon;
              const contentChanged = rev.content !== rev.new_content;
              const categoryChanged = rev.category !== rev.new_category;
              const sessionHref = buildSessionHref(
                userSession,
                rev.source_session_id || fallbackSessionId,
                rev.source_quote || fallbackQuote,
              );
              return (
                <div
                  key={`${rev.changed_at}-${index}`}
                  className="rounded-xl p-3 space-y-2"
                  style={{
                    background: "var(--bg-page)",
                    border: "1px solid var(--border)",
                  }}
                >
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <span
                      className="text-[11px] font-medium"
                      style={{ color: "var(--text-secondary)" }}
                    >
                      {formatDate(rev.changed_at)}
                    </span>
                    {rev.source_type &&
                      (sessionHref ? (
                        <Link
                          href={sessionHref}
                          onClick={onClose}
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
                          <ArrowUpRight
                            className="w-3 h-3 opacity-80"
                            strokeWidth={2.25}
                          />
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
                      ))}
                  </div>

                  {contentChanged && (
                    <div className="space-y-1">
                      <p
                        className="text-[10px] font-medium uppercase tracking-wide"
                        style={{ color: "var(--text-muted)" }}
                      >
                        {t("memory.revisionContent")}
                      </p>
                      <p
                        className="text-[12px] leading-relaxed line-through opacity-70"
                        style={{ color: "var(--text-secondary)" }}
                      >
                        {rev.content}
                      </p>
                      <p
                        className="text-[13px] leading-relaxed"
                        style={{ color: "var(--text-primary)" }}
                      >
                        {rev.new_content}
                      </p>
                    </div>
                  )}

                  {categoryChanged && (
                    <div className="space-y-1">
                      <p
                        className="text-[10px] font-medium uppercase tracking-wide"
                        style={{ color: "var(--text-muted)" }}
                      >
                        {t("memory.revisionCategory")}
                      </p>
                      <p
                        className="text-[12px]"
                        style={{ color: "var(--text-secondary)" }}
                      >
                        {t(
                          `category.${rev.category as MemoryCategory}` as MessageKey,
                        )}
                        {" → "}
                        {t(
                          `category.${rev.new_category as MemoryCategory}` as MessageKey,
                        )}
                      </p>
                    </div>
                  )}

                  {!contentChanged && !categoryChanged && (
                    <p
                      className="text-[12px]"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {rev.new_content}
                    </p>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );

  if (typeof document === "undefined") return null;
  return createPortal(dialog, document.body);
}
