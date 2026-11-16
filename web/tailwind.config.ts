import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: { DEFAULT: "#0d1f4f", soft: "#1a2c5e" },
        brand: { DEFAULT: "#f26511", dark: "#d9550a" },
        muted: "#5b6478",
        line: "#d5d9e2",
      },
      keyframes: {
        ring: {
          "0%": { boxShadow: "0 0 0 0 rgba(242,101,17,.45)" },
          "100%": { boxShadow: "0 0 0 18px rgba(242,101,17,0)" },
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        serif: ["var(--font-serif)", "Georgia", "serif"],
      },
    },
  },
  plugins: [],
};
export default config;
