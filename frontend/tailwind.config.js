/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#f4f1ea",
        mute: "#a39e92",
        lime: "#dff56a",
        coral: "#ff5c39",
        paper: "#10110e",
        panel: "#171910",
        line: "#2c2e26",
      },
      fontFamily: {
        sans: ["Outfit", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["Fraunces", "ui-serif", "Georgia", "serif"],
      },
      boxShadow: {
        phone: "0 24px 60px rgba(0,0,0,0.35)",
      },
    },
  },
  plugins: [],
};
