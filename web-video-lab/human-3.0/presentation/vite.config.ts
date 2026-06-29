import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // relative base so the built dist/ opens over file:// (used by the lab screenshotter)
  base: "./",
  server: {
    port: 5174,
    fs: { allow: [".."] },
  },
});
