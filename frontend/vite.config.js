/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `--host` is also set in docker-compose; host:true here makes a bare
// `npm run dev` reachable from outside the container too.
export default defineConfig({
  plugins: [react()],
  server: { host: true, port: 5173 },
  test: {
    // Component/hook tests need a DOM; jsdom is the lightweight option.
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.js",
    css: false,
    // Only pick up co-located *.test.* files, never anything in dist/.
    include: ["src/**/*.{test,spec}.{js,jsx}"],
  },
});
