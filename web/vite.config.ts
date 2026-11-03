import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The Python server (`uv run python -m vshort.web`) listens on 8770: the dev server forwards the API and the video there.
const api = { target: 'http://127.0.0.1:8770', changeOrigin: true }

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(import.meta.dirname, './src') } },
  server: { proxy: { '/api': api, '/files': api } },
})
