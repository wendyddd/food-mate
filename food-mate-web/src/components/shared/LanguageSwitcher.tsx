"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { LocaleProvider, useLocale, type Locale } from "@/lib/i18n";

/**
 * Root client shell: provides locale context.
 */
export function AppI18nProvider({ children }: { children: React.ReactNode }) {
  return <LocaleProvider>{children}</LocaleProvider>;
}

const OPTIONS: { value: Locale; labelKey: "common.lang.en" | "common.lang.zh" }[] =
  [
    { value: "en", labelKey: "common.lang.en" },
    { value: "zh", labelKey: "common.lang.zh" },
  ];

/**
 * Language switcher: click the current language to open a list and choose.
 *
 * @param compact - Compact sidebar style; login page can use the full style
 */
export function LanguageSwitcher({ compact = false }: { compact?: boolean }) {
  const { locale, setLocale, t } = useLocale();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const currentLabel =
    locale === "en" ? (compact ? "EN" : t("common.lang.en")) : t("common.lang.zh");

  useEffect(() => {
    if (!open) return;

    /**
     * Close the dropdown on outside click or Escape.
     */
    function handlePointerDown(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  /**
   * Select a locale and close the menu.
   *
   * @param next - Target locale
   */
  function selectLocale(next: Locale) {
    setLocale(next);
    setOpen(false);
  }

  return (
    <div
      ref={rootRef}
      className={`relative ${compact ? "" : "flex items-center justify-center gap-2"}`}
    >
      {!compact && (
        <span className="text-[12px]" style={{ color: "var(--text-muted)" }}>
          {t("common.language")}
        </span>
      )}
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        title={t("common.language")}
        onClick={() => setOpen((v) => !v)}
        className={`inline-flex items-center gap-0.5 rounded-md transition-all ${
          compact ? "px-1.5 py-0.5 text-[11px]" : "px-2.5 py-1 text-[12px]"
        }`}
        style={{
          color: "var(--text-muted)",
          border: compact ? "none" : "1px solid var(--border)",
          background: compact ? "transparent" : "var(--bg-page)",
        }}
      >
        <span style={{ fontWeight: 600, color: "var(--text-secondary)" }}>
          {currentLabel}
        </span>
        <ChevronDown
          className={`shrink-0 transition-transform ${compact ? "w-3 h-3" : "w-3.5 h-3.5"} ${
            open ? "rotate-180" : ""
          }`}
        />
      </button>

      {open && (
        <ul
          role="listbox"
          className={`absolute right-0 z-30 min-w-[88px] overflow-hidden rounded-lg py-1 shadow-md ${
            compact ? "bottom-full mb-1.5" : "top-full mt-1.5"
          }`}
          style={{
            background: "var(--bg-surface)",
            border: "1px solid var(--border)",
          }}
        >
          {OPTIONS.map((opt) => {
            const selected = locale === opt.value;
            const label =
              opt.value === "en"
                ? compact
                  ? "EN"
                  : t(opt.labelKey)
                : t(opt.labelKey);
            return (
              <li key={opt.value} role="option" aria-selected={selected}>
                <button
                  type="button"
                  onClick={() => selectLocale(opt.value)}
                  className={`w-full px-3 py-1.5 text-left transition-colors ${
                    compact ? "text-[11px]" : "text-[12px]"
                  }`}
                  style={{
                    color: selected ? "var(--accent)" : "var(--text-secondary)",
                    background: selected ? "var(--accent-bg)" : "transparent",
                    fontWeight: selected ? 600 : 400,
                  }}
                >
                  {label}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
