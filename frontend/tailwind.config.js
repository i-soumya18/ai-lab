/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        ailab: {
          bg: "#0f0f13",
          surface: "#1a1a24",
          border: "#2a2a3a",
          accent: "#7c3aed",
          "accent-hover": "#6d28d9",
          text: "#e2e8f0",
          muted: "#64748b",
          user: "#1e293b",
          assistant: "#1a1a24",
        },
      },
      fontFamily: {
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
    },
  },
  plugins: [],
};
