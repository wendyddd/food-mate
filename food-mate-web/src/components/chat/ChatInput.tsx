"use client";

import { useState, useRef, useCallback } from "react";
import { ArrowUp, Loader2 } from "lucide-react";
import { useApp } from "@/lib/store";
import { useT } from "@/lib/i18n";

export default function ChatInput() {
  const [text, setText] = useState("");
  const { sendMessage, isStreaming } = useApp();
  const t = useT();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const disabled = isStreaming;

  const handleSubmit = useCallback(() => {
    if (!text.trim() || disabled) return;
    sendMessage(text.trim());
    setText("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  }, [text, disabled, sendMessage]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleInput = () => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 160) + "px";
    }
  };

  return (
    <div className="px-4 py-3 shrink-0">
      <div className="max-w-4xl mx-auto">
        <div className="glass-input rounded-lg flex items-end gap-2 px-4 py-2.5 transition-shadow hover:shadow-md">
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              handleInput();
            }}
            onKeyDown={handleKeyDown}
            placeholder={t("chat.placeholder")}
            rows={1}
            className="flex-1 resize-none bg-transparent text-[14px] outline-none max-h-40 py-1 leading-relaxed"
            style={{ color: "var(--text-primary)" }}
          />
          <button
            onClick={handleSubmit}
            disabled={!text.trim() || disabled}
            className="shrink-0 w-8 h-8 flex items-center justify-center rounded-lg text-white disabled:opacity-25 transition-all active:scale-95"
            style={{ background: "var(--accent)" }}
          >
            {disabled ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <ArrowUp className="w-4 h-4" />
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
