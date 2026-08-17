"use client";

import { useEffect, useState } from "react";
import { X, Loader2, ChevronDown, ChevronRight, Terminal } from "lucide-react";
import { useApp } from "@/lib/store";
import { useT } from "@/lib/i18n";

interface Props {
  onClose: () => void;
}

/**
 * Trace 调试面板，展示发给 LLM 的 system prompt 与会话原始消息。
 */
export default function RawMessagesPanel({ onClose }: Props) {
  const { rawMessages, loadRawMessages } = useApp();
  const t = useT();

  useEffect(() => {
    loadRawMessages();
  }, [loadRawMessages]);

  return (
    <div
      className="flex flex-col h-full"
      style={{ background: "var(--bg-surface)" }}
    >
      {/* Header */}
      <div
        className="h-14 flex items-center justify-between px-4 shrink-0"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <span
          className="text-[14px] font-semibold"
          style={{ color: "var(--text-primary)" }}
        >
          {t("trace.title")}
        </span>
        <button
          onClick={onClose}
          className="p-1.5 rounded-md transition-colors hover:opacity-80"
          style={{ color: "var(--text-muted)" }}
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {!rawMessages ? (
          <div className="flex items-center justify-center h-32">
            <Loader2
              className="w-5 h-5 animate-spin"
              style={{ color: "var(--text-muted)" }}
            />
          </div>
        ) : rawMessages.length === 0 ? (
          <div
            className="flex items-center justify-center h-32 text-[12px]"
            style={{ color: "var(--text-muted)" }}
          >
            No messages yet
          </div>
        ) : (
          rawMessages.map((msg, i) => <RawMessageItem key={i} msg={msg} />)
        )}
      </div>

      {/* Footer */}
      <div
        className="shrink-0 flex items-center justify-end px-4 py-3"
        style={{ borderTop: "1px solid var(--border)" }}
      >
        <span
          className="text-[10px] font-mono"
          style={{ color: "var(--text-muted)" }}
        >
          {rawMessages ? `${rawMessages.length} messages` : ""}
        </span>
      </div>
    </div>
  );
}

/** 单条原始消息，含可选 tool_calls 展示 */
function RawMessageItem({
  msg,
}: {
  msg: {
    role: string;
    content: string;
    tool_calls?: Array<{ tool: string; input?: string; output?: string }>;
  };
}) {
  const [expanded, setExpanded] = useState(false);
  const roleColor =
    msg.role === "system"
      ? "var(--text-muted)"
      : msg.role === "user"
        ? "#3b82f6"
        : "var(--accent)";
  const hasToolCalls = msg.tool_calls && msg.tool_calls.length > 0;
  const isLong = msg.content.length > 500;
  const t = useT();
  const toolCallLabel =
    msg.tool_calls && msg.tool_calls.length > 1
      ? t("trace.toolCallsPlural", { count: msg.tool_calls.length })
      : t("trace.toolCalls", { count: msg.tool_calls?.length ?? 0 });

  return (
    <div>
      <div className="flex items-center gap-2 mb-1">
        <span
          className="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded"
          style={{ color: roleColor, background: "var(--accent-bg)" }}
        >
          {msg.role}
        </span>
        {hasToolCalls && (
          <span
            className="text-[10px] px-1.5 py-0.5 rounded"
            style={{ background: "var(--accent-bg)", color: "var(--accent)" }}
          >
            {toolCallLabel}
          </span>
        )}
      </div>

      <div
        className="raw-message-viewer"
        style={
          msg.role === "assistant"
            ? { borderLeft: `2px solid ${roleColor}`, paddingLeft: 8 }
            : {}
        }
      >
        <div className="msg-content !max-h-[200px]">
          {isLong && !expanded
            ? msg.content.slice(0, 500) + "\n...[truncated]"
            : msg.content}
        </div>
        {isLong && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-[10px] mt-1 flex items-center gap-0.5 transition-colors hover:opacity-80"
            style={{ color: "var(--accent)" }}
          >
            {expanded ? (
              <ChevronDown className="w-3 h-3" />
            ) : (
              <ChevronRight className="w-3 h-3" />
            )}
            {expanded ? t("trace.collapse") : t("trace.expandAll")}
          </button>
        )}
      </div>

      {hasToolCalls && (
        <div className="mt-2 space-y-1.5 ml-2.5">
          {msg.tool_calls!.map((tc, j) => (
            <ToolCallItem key={j} tc={tc} />
          ))}
        </div>
      )}
    </div>
  );
}

/** 可折叠的 tool call 详情 */
function ToolCallItem({
  tc,
}: {
  tc: { tool: string; input?: string; output?: string };
}) {
  const [open, setOpen] = useState(false);
  const t = useT();

  return (
    <div
      className="rounded-lg text-[11px] overflow-hidden"
      style={{
        border: "1px solid var(--border)",
        background: "var(--bg-page)",
      }}
    >
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-3 py-1.5 text-left transition-colors hover:opacity-80"
      >
        <Terminal
          className="w-3 h-3 shrink-0"
          style={{ color: "var(--accent)" }}
        />
        <span
          className="font-mono font-medium truncate"
          style={{ color: "var(--text-primary)" }}
        >
          {tc.tool}
        </span>
        {open ? (
          <ChevronDown
            className="w-3 h-3 ml-auto shrink-0"
            style={{ color: "var(--text-muted)" }}
          />
        ) : (
          <ChevronRight
            className="w-3 h-3 ml-auto shrink-0"
            style={{ color: "var(--text-muted)" }}
          />
        )}
      </button>
      {open && (
        <div
          className="px-3 pb-2 space-y-1.5"
          style={{ borderTop: "1px solid var(--border)" }}
        >
          {tc.input && (
            <div>
              <span
                className="text-[9px] font-semibold uppercase tracking-wider"
                style={{ color: "var(--text-muted)" }}
              >
                {t("trace.input")}
              </span>
              <pre
                className="mt-0.5 text-[10px] font-mono whitespace-pre-wrap p-2 rounded"
                style={{
                  background: "var(--accent-bg)",
                  color: "var(--text-secondary)",
                }}
              >
                {tc.input.length > 1000
                  ? tc.input.slice(0, 1000) + "\n...[truncated]"
                  : tc.input}
              </pre>
            </div>
          )}
          {tc.output && (
            <div>
              <span
                className="text-[9px] font-semibold uppercase tracking-wider"
                style={{ color: "var(--text-muted)" }}
              >
                {t("trace.output")}
              </span>
              <pre
                className="mt-0.5 text-[10px] font-mono whitespace-pre-wrap p-2 rounded"
                style={{
                  background: "var(--accent-bg)",
                  color: "var(--text-secondary)",
                }}
              >
                {tc.output.length > 1000
                  ? tc.output.slice(0, 1000) + "\n...[truncated]"
                  : tc.output}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
