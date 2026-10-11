import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // `npm run dev` talks to a locally running backend on :8004
    proxy: { '/api': 'http://localhost:8004' },
    fs: { allow: ['../..'] },
  },
});
