import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["selector", "[data-theme=\"dark\"]"],
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        accent: "var(--accent)",
        "accent-hover": "var(--accent-hover)",
        "accent-bg": "var(--accent-bg)",
        "bg-page": "var(--bg-page)",
        "bg-surface": "var(--bg-surface)",
        "bg-sidebar": "var(--bg-sidebar)",
        "bg-editor": "var(--bg-editor)",
        "text-primary": "var(--text-primary)",
        "text-secondary": "var(--text-secondary)",
        "text-muted": "var(--text-muted)",
        "border-theme": "var(--border)",
        "border-accent": "var(--border-accent)",
        "bubble-user": "var(--bubble-user)",
        "bubble-ai": "var(--bubble-ai)",
      },
    },
  },
  plugins: [],
};

export default config;
