import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  envDir: "../",      // Lee .env desde la raíz del proyecto
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 3000,
    open: true,
  },
  build: {
    rollupOptions: {
      input: {
        main: path.resolve(__dirname, "index.html"),
        skill: path.resolve(__dirname, "skill.html"),
        rag: path.resolve(__dirname, "rag.html"),
        tool: path.resolve(__dirname, "tool.html"),
        agent: path.resolve(__dirname, "agent.html"),
        workflow: path.resolve(__dirname, "workflow.html"),
      },
    },
  },
});
