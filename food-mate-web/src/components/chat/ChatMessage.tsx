"use client";

import { useState, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AlertTriangle, Key, Copy, Check } from "lucide-react";
import type { ChatMessage as ChatMessageType } from "@/lib/store";
import { useApp } from "@/lib/store";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";
import ThoughtChain from "./ThoughtChain";
import MemoryRefCard from "./MemoryRefCard";
import Logo from "@/components/shared/Logo";

function CodeBlock({
  className,
  children,
}: {
  className?: string;
  children?: React.ReactNode;
}) {
  const match = /language-(\w+)/.exec(className || "");
  const lang = match ? match[1] : "";
  const code = String(children).replace(/\n$/, "");
  const [copied, setCopied] = useState(false);
  const t = useT();

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [code]);

  if (!className) return <code>{children}</code>;

  return (
    <div className="code-block-wrapper">
      <div className="code-block-header">
        <span className="code-block-lang">{lang || "code"}</span>
        <button
          onClick={handleCopy}
          className="code-block-copy"
          title={t("chat.copyCode")}
        >
          {copied ? (
            <Check className="w-3.5 h-3.5" />
          ) : (
            <Copy className="w-3.5 h-3.5" />
          )}
        </button>
      </div>
      <pre>
        <code>{children}</code>
      </pre>
    </div>
  );
}

interface Props {
  message: ChatMessageType;
  /** 当前消息是否处于流式输出中（仅最后一条 assistant 消息为 true） */
  isActiveStreaming?: boolean;
  /** 本条回答下方展示的追问建议（仅最新完成轮次） */
  suggestedQuestions?: string[];
}

/**
 * 将消息时间戳格式化为「日期 + 时间」。
 *
 * 参数:
 *   ts (number): 毫秒级 Unix 时间戳
 *
 * 返回:
 *   string: 形如 `2026-08-14 20:24` 的本地时间文案
 */
function formatTime(ts: number): string {
  const d = new Date(ts);
  const pad = (n: number) => String(n).padStart(2, "0");
  const date = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const time = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  return `${date} ${time}`;
}

function isAuthError(content: string): boolean {
  return /401|authentication.?fail|invalid.*api.?key|api.?key.*invalid/i.test(
    content,
  );
}

export default function ChatMessage({
  message,
  isActiveStreaming = false,
  suggestedQuestions,
}: Props) {
  const isUser = message.role === "user";
  const t = useT();
  const { isShow } = useAuth();
  const { sendMessage, isStreaming } = useApp();
  const displayContent = isUser
    ? message.content
    : message.content
        .replace(/<food-mate-canvas>[\s\S]*?<\/food-mate-canvas>/g, "")
        .replace(/<food-mate-canvas>[\s\S]*$/g, "")
        .replace(/\[mem_[a-zA-Z0-9]+\]/g, "")
        .trim();
  const hasAuthError = !isUser && isAuthError(message.content);
  const followUps =
    !isUser &&
    !isActiveStreaming &&
    suggestedQuestions &&
    suggestedQuestions.length > 0
      ? suggestedQuestions
      : null;

  /** 工具调用已完成但无文本内容（new_response 前的中间态），不应展示加载动画 */
  const isToolOnlySegment =
    isShow &&
    !displayContent &&
    !!message.toolCalls?.length &&
    message.toolCalls.every((tc) => tc.status === "done");

  /** 仅在流式输出且等待内容时展示 typing 指示器 */
  const showTypingIndicator =
    isActiveStreaming && !displayContent && !isToolOnlySegment;

  return (
    <div
      id={`msg-${message.id}`}
      data-msg-id={message.id}
      className="animate-fade-in"
    >
      <div className="max-w-3xl mx-auto">
        {isUser ? (
          /* User message — right-aligned bubble */
          <div className="flex justify-end">
            <div className="max-w-[70%]">
              <div
                className="px-5 py-3 rounded-2xl rounded-tr-sm text-[14px] leading-relaxed shadow-sm"
                style={{
                  background: "var(--bubble-user)",
                  border: "1px solid var(--border-accent)",
                  color: "var(--text-primary)",
                }}
              >
                {message.content}
              </div>
              <div
                className="text-[10px] font-mono mt-1 text-right pr-1"
                style={{ color: "var(--text-muted)" }}
              >
                {formatTime(message.timestamp)}
              </div>
            </div>
          </div>
        ) : (
          /* Assistant message — left-aligned，Logo 与首行文本顶部对齐 */
          <div className="flex items-start gap-3 max-w-[85%]">
            <Logo
              size={32}
              className="shrink-0 rounded-full mt-0.5 shadow-sm"
            />
            <div className="flex-1 min-w-0">
              {/* Tool calls — 仅 is_show=1 时展示 */}
              {isShow && message.toolCalls && message.toolCalls.length > 0 && (
                <ThoughtChain toolCalls={message.toolCalls} />
              )}

              {/* Auth error alert */}
              {hasAuthError ? (
                <AuthErrorAlert content={message.content} />
              ) : displayContent ? (
                <div>
                  <div
                    className="px-5 py-3 rounded-2xl rounded-tl-sm text-[14px] leading-relaxed shadow-sm"
                    style={{
                      background: "var(--bubble-ai)",
                      border: "1px solid var(--border)",
                      color: "var(--text-primary)",
                    }}
                  >
                    {/* 流式阶段用纯文本，避免 ReactMarkdown 频繁拆建 DOM 触发 removeChild */}
                    <div className="markdown-content">
                      {isActiveStreaming ? (
                        <div className="whitespace-pre-wrap">
                          {displayContent}
                        </div>
                      ) : (
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm]}
                          components={{ code: CodeBlock }}
                        >
                          {displayContent}
                        </ReactMarkdown>
                      )}
                    </div>
                  </div>
                  {isShow &&
                    message.memoryRefs &&
                    message.memoryRefs.length > 0 && (
                      <MemoryRefCard refs={message.memoryRefs} />
                    )}
                  {followUps && (
                    <div className="mt-2">
                      <p
                        className="text-[12px] mb-2 pl-1"
                        style={{ color: "var(--text-muted)" }}
                      >
                        {t("chat.followUp")}
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {followUps.map((q) => (
                          <button
                            key={q}
                            type="button"
                            onClick={() => !isStreaming && sendMessage(q)}
                            className="px-3 py-1.5 rounded-full text-[12px] transition-all shadow-sm hover:shadow-md text-left"
                            style={{
                              color: "var(--text-secondary)",
                              background: "var(--bg-surface)",
                              border: "1px solid var(--border)",
                            }}
                          >
                            {q}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                  <div
                    className="text-[10px] font-mono mt-1 pl-1"
                    style={{ color: "var(--text-muted)" }}
                  >
                    {formatTime(message.timestamp)}
                  </div>
                </div>
              ) : showTypingIndicator ? (
                /* Typing indicator */
                <div
                  className="px-4 py-3 rounded-2xl rounded-tl-sm inline-flex items-center gap-1.5 shadow-sm"
                  style={{
                    background: "var(--bubble-ai)",
                    border: "1px solid var(--border)",
                  }}
                >
                  <span
                    className="typing-dot w-1.5 h-1.5 rounded-full"
                    style={{ background: "var(--accent)" }}
                  />
                  <span
                    className="typing-dot w-1.5 h-1.5 rounded-full"
                    style={{ background: "var(--accent)" }}
                  />
                  <span
                    className="typing-dot w-1.5 h-1.5 rounded-full"
                    style={{ background: "var(--accent)" }}
                  />
                </div>
              ) : null}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function AuthErrorAlert({ content }: { content: string }) {
  const t = useT();
  return (
    <div className="animate-fade-in-scale rounded-xl border border-red-200 bg-red-50/80 px-4 py-3 space-y-2">
      <div className="flex items-center gap-2">
        <AlertTriangle className="w-4 h-4 text-red-500 shrink-0" />
        <span className="text-[13px] font-semibold text-red-700">
          {t("chat.authErrorTitle")}
        </span>
      </div>
      <p className="text-[12px] text-red-600/80 leading-relaxed">
        {t("chat.authErrorBody")}
      </p>
      <div className="flex items-center gap-3 pt-1">
        <a
          href="http://localhost:8002/"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-[11px] font-medium text-red-600 hover:text-red-800 transition-colors"
        >
          <Key className="w-3 h-3" />
          {t("chat.authErrorLink")}
        </a>
        <span className="text-[10px] text-red-400">|</span>
        <span className="text-[10px] text-red-500 font-mono">
          {content.slice(0, 120)}...
        </span>
      </div>
    </div>
  );
}
