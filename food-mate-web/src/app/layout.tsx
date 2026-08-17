import type { Metadata } from "next";
import { Space_Grotesk } from "next/font/google";
import { AppI18nProvider } from "@/components/shared/LanguageSwitcher";
import "./globals.css";

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-space-grotesk",
});

export const metadata: Metadata = {
  title: "FoodMate",
  description: "Your home cooking assistant — recipes, steps, and kitchen tips",
  icons: {
    icon: [
      { url: "/favicon-32.png", type: "image/png", sizes: "32x32" },
      { url: "/favicon-192.png", type: "image/png", sizes: "192x192" },
    ],
    shortcut: "/favicon-32.png",
    apple: [
      { url: "/apple-touch-icon.png", type: "image/png", sizes: "180x180" },
    ],
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" data-theme="light" suppressHydrationWarning>
      <body
        className={`${spaceGrotesk.className} antialiased`}
        style={{
          fontFamily:
            "var(--font-space-grotesk), 'PingFang SC', 'Hiragino Sans GB', 'Noto Sans SC', 'Microsoft YaHei', sans-serif",
        }}
      >
        <AppI18nProvider>{children}</AppI18nProvider>
      </body>
    </html>
  );
}
