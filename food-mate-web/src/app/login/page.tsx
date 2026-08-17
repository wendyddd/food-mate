"use client";

import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import Logo from "@/components/shared/Logo";
import { login, setUserSession } from "@/lib/api";
import { useT } from "@/lib/i18n";

/**
 * 登录页：uid + 密码登录后跳转会话路由。
 */
export default function LoginPage() {
  const router = useRouter();
  const t = useT();
  const [uid, setUid] = useState("");
  const [pwd, setPwd] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const info = await login(uid.trim(), pwd);
      setUserSession(info.session);
      router.replace(`/${info.session}/`);
    } catch {
      setError(t("login.error"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="min-h-screen flex items-center justify-center px-4"
      style={{ background: "var(--bg-page)" }}
    >
      <div
        className="w-full max-w-sm rounded-2xl p-8 shadow-sm"
        style={{
          background: "var(--bg-surface)",
          border: "1px solid var(--border)",
        }}
      >
        <div className="flex flex-col items-center mb-8">
          <Logo size={48} className="rounded-2xl shadow-sm mb-4" />
          <h1
            className="text-xl font-bold tracking-tight"
            style={{ color: "var(--text-primary)" }}
          >
            FoodMate
          </h1>
          <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
            {t("login.subtitle")}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label
              htmlFor="uid"
              className="block text-xs font-medium mb-1.5"
              style={{ color: "var(--text-secondary)" }}
            >
              {t("login.uid")}
            </label>
            <input
              id="uid"
              type="text"
              autoComplete="username"
              required
              value={uid}
              onChange={(e) => setUid(e.target.value)}
              className="w-full px-3 py-2.5 text-sm rounded-lg border outline-none transition-colors focus:ring-2"
              style={{
                borderColor: "var(--border)",
                background: "var(--bg-page)",
                color: "var(--text-primary)",
              }}
              placeholder={t("login.uidPlaceholder")}
            />
          </div>

          <div>
            <label
              htmlFor="pwd"
              className="block text-xs font-medium mb-1.5"
              style={{ color: "var(--text-secondary)" }}
            >
              {t("login.password")}
            </label>
            <input
              id="pwd"
              type="password"
              autoComplete="current-password"
              required
              value={pwd}
              onChange={(e) => setPwd(e.target.value)}
              className="w-full px-3 py-2.5 text-sm rounded-lg border outline-none transition-colors focus:ring-2"
              style={{
                borderColor: "var(--border)",
                background: "var(--bg-page)",
                color: "var(--text-primary)",
              }}
              placeholder={t("login.passwordPlaceholder")}
            />
          </div>

          {error && <p className="text-sm text-red-500 text-center">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 text-sm font-medium rounded-lg text-white transition-opacity hover:opacity-90 disabled:opacity-60"
            style={{ background: "var(--accent)" }}
          >
            {loading ? t("login.submitting") : t("login.submit")}
          </button>
        </form>
      </div>
    </div>
  );
}
