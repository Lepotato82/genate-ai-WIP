import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        brutal: {
          bg: "#FAFAFA",
          yellow: "#FFDE21",
          orange: "#FF5733",
          green: "#22C55E",
          red: "#EF4444",
        },
      },
      boxShadow: {
        brutal: "4px 4px 0px #000000",
        "brutal-sm": "2px 2px 0px #000000",
        "brutal-lg": "6px 6px 0px #000000",
      },
      borderWidth: {
        "3": "3px",
      },
      fontFamily: {
        heading: ["var(--font-space-grotesk)", "sans-serif"],
        body: ["var(--font-inter)", "sans-serif"],
      },
      borderRadius: {
        DEFAULT: "0px",
        none: "0px",
        sm: "0px",
        md: "0px",
        lg: "0px",
        xl: "0px",
        "2xl": "0px",
        full: "0px",
      },
    },
  },
  plugins: [],
};

export default config;
