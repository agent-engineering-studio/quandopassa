import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Due pagine: l'app pubblica (index.html) e il backoffice (admin/index.html, servito su /admin/).
// In sviluppo le chiamate /api vanno al backend FastAPI su :8000.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://localhost:8000" } },
  build: {
    outDir: "dist",
    sourcemap: false,
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      input: { main: "index.html", admin: "admin/index.html" },
    },
  },
});
