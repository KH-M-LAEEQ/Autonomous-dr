import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

// The dev server proxies /api, /health, /ready and /ws to the FastAPI process,
// so the frontend always talks to a same-origin URL and CORS never becomes a
// debugging session. The target port is read from API_PORT in the repo ROOT
// .env (the same file core/config.py's Settings.api_port reads) via Vite's
// loadEnv against the parent directory -- not a second hardcoded port number
// that can silently drift from the one the backend actually bound.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, path.resolve(__dirname, ".."), "");
  const apiPort = env.API_PORT || "8001";
  const apiTarget = `http://localhost:${apiPort}`;

  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: 3010,
      proxy: {
        "/api": { target: apiTarget, changeOrigin: true },
        "/health": { target: apiTarget, changeOrigin: true },
        "/ready": { target: apiTarget, changeOrigin: true },
        "/ws": { target: apiTarget.replace("http", "ws"), ws: true },
      },
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: "./src/test/setup.ts",
    },
  };
});
