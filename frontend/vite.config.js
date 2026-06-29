import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `--host` is also set in docker-compose; host:true here makes a bare
// `npm run dev` reachable from outside the container too.
export default defineConfig({
  plugins: [react()],
  server: { host: true, port: 5173 },
});
