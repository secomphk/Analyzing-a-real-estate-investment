import type { Config } from "tailwindcss";

// Scenario palettes mirror the spec — A: orange/rose, B: violet/indigo,
// C: emerald/teal. They're exposed as `bg-scenarioA-from`, `text-scenarioC-to`,
// etc. so components can pull them without re-typing hex codes.
const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        scenarioA: { from: "#fb923c", to: "#f43f5e" },
        scenarioB: { from: "#8b5cf6", to: "#6366f1" },
        scenarioC: { from: "#10b981", to: "#14b8a6" },
        brand: {
          starbucks: "#00704A",
          mcdonalds: "#FFC72C",
          dunkin: "#F37322",
          burgerKing: "#D62300",
          megacoffee: "#FFE600",
          twosome: "#7B2D26",
        },
      },
      fontFamily: {
        sans: [
          "Pretendard",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};

export default config;
