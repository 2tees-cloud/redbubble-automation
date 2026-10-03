import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // 3D (three.js) — отдельный файл, грузится только на экранах с моделью.
  build: { chunkSizeWarningLimit: 600 },
});
