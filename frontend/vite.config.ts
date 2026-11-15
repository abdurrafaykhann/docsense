/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import { defineConfig, loadEnv } from 'vite'

const here = fileURLToPath(new URL('.', import.meta.url))

export default defineConfig(({ mode }) => {
  // VITE_API_PROXY can come from the shell or a local .env file (e.g. .env.development.local).
  const env = { ...loadEnv(mode, here, ''), ...process.env }
  const api = env.VITE_API_PROXY ?? 'http://localhost:8000'
  const proxy = {
    '/api': { target: api, changeOrigin: true, secure: true },
    '/ws': { target: api, ws: true, changeOrigin: true },
  }
  return {
    plugins: [react(), tailwindcss()],
    server: { host: true, proxy },
    preview: { host: true, port: 5173, proxy, allowedHosts: true },
    test: { environment: 'jsdom', globals: true, setupFiles: ['./src/setupTests.ts'] },
  }
})
