import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/escalations": "http://localhost:8000",
      "/legal-qa": "http://localhost:8000",
      "/contracts": "http://localhost:8000"
    }
  }
});
