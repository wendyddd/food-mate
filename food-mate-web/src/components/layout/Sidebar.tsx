"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Plus,
  MoreHorizontal,
  Pencil,
  Trash2,
  Check,
  X,
  Brain,
  PanelLeftClose,
} from "lucide-react";
import { useApp } from "@/lib/store";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";
import ConfirmDialog from "@/components/shared/ConfirmDialog";
import Logo from "@/components/shared/Logo";

/** 侧边栏展开 / 收起时的外层宽度 class */
export const SIDEBAR_WIDTH_EXPANDED = "w-64";
export const SIDEBAR_WIDTH_COLLAPSED = "w-14";

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { userSession, uid, logout, isShow } = useAuth();
  const t = useT();
  const {
    sessionId,
    setSessionId,
    sessions,
    createSession,
    renameSession,
    deleteSession,
    sidebarOpen,
    toggleSidebar,
  } = useApp();

  const chatBase = `/${userSession}`;
  const isChat = pathname === chatBase || pathname === `${chatBase}/`;
  const isMemory = pathname === `${chatBase}/memory`;

  /**
   * 跳转到对话页（若当前不在对话页）。
   *
   * 返回:
   * void
   */
  const goToChat = useCallback(() => {
    if (!isChat) {
      router.push(`${chatBase}/`);
    }
  }, [isChat, router, chatBase]);

  /**
   * 新建对话；若不在对话页则先跳转。
   *
   * 返回:
   * Promise<void>
   */
  const handleNewChat = useCallback(async () => {
    goToChat();
    await createSession();
  }, [goToChat, createSession]);

  /**
   * 选中最近会话；若不在对话页则跳转并加载该会话。
   *
   * 参数:
   * id (string): 会话 ID
   *
   * 返回:
   * void
   */
  const handleSelectSession = useCallback(
    (id: string) => {
      setSessionId(id);
      goToChat();
    },
    [setSessionId, goToChat],
  );

  return (
    <aside
      className="flex flex-col h-full w-64 shrink-0"
      style={{
        background: "var(--bg-sidebar)",
        borderRight: "1px solid var(--border)",
      }}
    >
      {/* Brand + collapse */}
      <div className="flex items-center justify-between px-4 pt-3 pb-2 shrink-0">
        <div className="flex items-center gap-2.5 min-w-0">
          {sidebarOpen ? (
            <Logo size={32} className="rounded-xl shadow-sm shrink-0" />
          ) : (
            <button
              onClick={toggleSidebar}
              className="rounded-xl transition-opacity hover:opacity-80 shrink-0"
              title={t("nav.expand")}
            >
              <Logo size={32} className="rounded-xl shadow-sm" />
            </button>
          )}
          <span
            className={`text-[15px] tracking-tight font-bold truncate whitespace-nowrap transition-opacity duration-200 ${
              sidebarOpen ? "opacity-100" : "opacity-0"
            }`}
            style={{ color: "var(--text-primary)" }}
          >
            FoodMate
          </span>
        </div>
        <button
          onClick={toggleSidebar}
          className={`p-1.5 rounded-lg transition-all duration-200 hover:opacity-80 shrink-0 ${
            sidebarOpen
              ? "opacity-100"
              : "opacity-0 pointer-events-none w-0 p-0 overflow-hidden"
          }`}
          style={{ color: "var(--text-muted)" }}
          title={t("nav.collapse")}
        >
          <PanelLeftClose className="w-4 h-4" />
        </button>
      </div>

      <div
        className={`flex flex-col flex-1 min-h-0 transition-opacity duration-200 ${
          sidebarOpen
            ? "opacity-100 delay-100"
            : "opacity-0 pointer-events-none"
        }`}
      >
        {/* New chat — always visible */}
        <div className="px-4 pb-1">
          <button
            onClick={handleNewChat}
            className="w-full flex items-center gap-2.5 px-3 py-2 text-[13px] font-medium rounded-lg transition-all hover:opacity-80"
            style={{ color: "var(--accent)" }}
          >
            <Plus className="w-4 h-4" />
            {t("nav.newChat")}
          </button>
        </div>

        {/* Memory navigation — 仅 Glass-box（记忆可见）时展示 */}
        {isShow && (
          <div className="px-4 pb-2">
            <Link
              href={`${chatBase}/memory`}
              className={`flex items-center gap-2.5 px-3 py-2 rounded-lg transition-all ${
                isMemory ? "font-bold shadow-sm" : "hover:opacity-80"
              }`}
              style={
                isMemory
                  ? {
                      background: "var(--bg-surface)",
                      color: "var(--accent)",
                    }
                  : { color: "var(--text-secondary)" }
              }
            >
              <Brain className="w-4 h-4 shrink-0" />
              <div className="flex items-baseline gap-1.5">
                <span className="text-[13px]">{t("nav.memory")}</span>
                <span
                  className="text-[10px] font-normal"
                  style={{
                    color: isMemory ? "var(--accent)" : "var(--text-muted)",
                    opacity: 0.7,
                  }}
                >
                  {t("nav.memorySub")}
                </span>
              </div>
            </Link>
          </div>
        )}

        <div className="mx-4 h-px" style={{ background: "var(--border)" }} />

        {/* Recent sessions — always visible */}
        <div className="flex-1 overflow-y-auto px-1.5 mt-1">
          {sessions.length > 0 && (
            <div className="space-y-0.5">
              <p
                className="px-3 pt-1 pb-1 text-[10px] font-semibold uppercase tracking-widest"
                style={{ color: "var(--text-muted)" }}
              >
                {t("nav.recent")}
              </p>
              {sessions.map((s) => (
                <SessionItem
                  key={s.id}
                  id={s.id}
                  title={s.title}
                  isActive={isChat && sessionId === s.id}
                  onSelect={() => handleSelectSession(s.id)}
                  onRename={(title) => renameSession(s.id, title)}
                  onDelete={() => deleteSession(s.id)}
                />
              ))}
            </div>
          )}
        </div>

        {/* uid / 退出 — pinned at bottom */}
        <div
          className="shrink-0 px-4 py-3"
          style={{ borderTop: "1px solid var(--border)" }}
        >
          <div className="flex items-center justify-between gap-2">
            <button
              type="button"
              onClick={logout}
              className="group flex items-center gap-1.5 text-[11px] min-w-0 transition-colors hover:opacity-80"
              style={{ color: "var(--text-muted)" }}
              title={t("nav.signOut")}
            >
              <span className="relative flex h-2 w-2 shrink-0">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500" />
              </span>
              <span className="truncate group-hover:hidden">{uid}</span>
              <span className="truncate hidden group-hover:inline">
                {t("nav.signOut")}
              </span>
            </button>
          </div>
        </div>
      </div>
    </aside>
  );
}

// ── Session Item ────────────────────────────────────────

function SessionItem({
  id,
  title,
  isActive,
  onSelect,
  onRename,
  onDelete,
}: {
  id: string;
  title: string;
  isActive: boolean;
  onSelect: () => void;
  onRename: (title: string) => void;
  onDelete: () => void;
}) {
  const t = useT();
  const [menuOpen, setMenuOpen] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState(title);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [menuOpen]);

  useEffect(() => {
    if (renaming && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [renaming]);

  const handleRenameSubmit = useCallback(() => {
    const trimmed = renameValue.trim();
    if (trimmed && trimmed !== title) {
      onRename(trimmed);
    }
    setRenaming(false);
  }, [renameValue, title, onRename]);

  const handleDelete = useCallback(() => {
    setMenuOpen(false);
    setShowDeleteConfirm(true);
  }, []);

  if (renaming) {
    return (
      <div className="flex items-center gap-1 px-2 py-1">
        <input
          ref={inputRef}
          className="flex-1 px-2 py-1 text-[13px] rounded-md border outline-none"
          style={{
            borderColor: "var(--border-accent)",
            background: "var(--bg-surface)",
            color: "var(--text-primary)",
          }}
          value={renameValue}
          onChange={(e) => setRenameValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleRenameSubmit();
            if (e.key === "Escape") setRenaming(false);
          }}
          onBlur={handleRenameSubmit}
        />
        <button
          onClick={handleRenameSubmit}
          className="p-1 text-green-600 hover:bg-green-50 rounded"
        >
          <Check className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={() => setRenaming(false)}
          className="p-1 rounded"
          style={{ color: "var(--text-muted)" }}
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    );
  }

  return (
    <div className="relative group" ref={menuRef}>
      <button
        onClick={onSelect}
        className={`w-full flex items-center gap-2 px-3 py-2 text-[13px] rounded-lg transition-all text-left relative pr-8 ${
          isActive ? "font-medium shadow-sm" : "hover:opacity-80"
        }`}
        style={
          isActive
            ? { background: "var(--bg-surface)", color: "var(--text-primary)" }
            : { color: "var(--text-secondary)" }
        }
      >
        {isActive && (
          <div
            className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 rounded-r-full"
            style={{ background: "var(--accent)" }}
          />
        )}
        <span className="truncate">{title}</span>
      </button>

      <div className="absolute right-1 top-1/2 -translate-y-1/2">
        <button
          onClick={(e) => {
            e.stopPropagation();
            setMenuOpen((v) => !v);
          }}
          className="p-1 rounded-md opacity-0 group-hover:opacity-100 transition-all"
          style={{ color: "var(--text-muted)" }}
        >
          <MoreHorizontal className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Dropdown menu — rendered as fixed position to escape overflow:hidden */}
      {menuOpen && (
        <SessionMenu
          onRename={() => {
            setMenuOpen(false);
            setRenameValue(title);
            setRenaming(true);
          }}
          onDelete={handleDelete}
          onClose={() => setMenuOpen(false)}
          menuRef={menuRef}
        />
      )}

      {/* Delete confirmation dialog */}
      {showDeleteConfirm && (
        <ConfirmDialog
          title={t("nav.deleteSession")}
          message={t("nav.deleteSessionMsg", { title })}
          confirmText={t("common.delete")}
          cancelText={t("common.cancel")}
          danger
          onConfirm={() => {
            setShowDeleteConfirm(false);
            onDelete();
          }}
          onCancel={() => setShowDeleteConfirm(false)}
        />
      )}
    </div>
  );
}

/** Fixed-position dropdown to escape sidebar overflow clipping */
function SessionMenu({
  onRename,
  onDelete,
  onClose,
  menuRef,
}: {
  onRename: () => void;
  onDelete: () => void;
  onClose: () => void;
  menuRef: React.RefObject<HTMLDivElement | null>;
}) {
  const t = useT();
  const dropdownRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ top: 0, left: 0 });

  useEffect(() => {
    if (menuRef.current) {
      const rect = menuRef.current.getBoundingClientRect();
      setPos({ top: rect.bottom + 4, left: rect.right - 128 });
    }
  }, [menuRef]);

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node) &&
        menuRef.current &&
        !menuRef.current.contains(e.target as Node)
      ) {
        onClose();
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [onClose, menuRef]);

  return (
    <div
      ref={dropdownRef}
      className="fixed w-32 rounded-lg shadow-lg py-1 animate-fade-in-scale"
      style={{
        top: pos.top,
        left: pos.left,
        zIndex: 9999,
        background: "var(--bg-surface)",
        border: "1px solid var(--border)",
      }}
    >
      <button
        onClick={onRename}
        className="w-full flex items-center gap-2 px-3 py-1.5 text-[12px] transition-colors hover:opacity-80"
        style={{ color: "var(--text-secondary)" }}
      >
        <Pencil className="w-3 h-3" />
        {t("common.rename")}
      </button>
      <button
        onClick={onDelete}
        className="w-full flex items-center gap-2 px-3 py-1.5 text-[12px] text-red-500 hover:bg-red-50 transition-colors"
      >
        <Trash2 className="w-3 h-3" />
        {t("common.delete")}
      </button>
    </div>
  );
}
