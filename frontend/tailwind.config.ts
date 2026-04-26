import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Tier-aware semantic colors used across cards / badges / charts
        tier: {
          hot: "#ef4444",
          warm: "#f59e0b",
          cold: "#64748b",
        },
        brand: {
          primary: "#1e40af",
          accent: "#0ea5e9",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
} satisfies Config;
