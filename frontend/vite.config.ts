/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const api = process.env.VITE_API_PROXY ?? 'http://localhost:8000'

const proxy = { '/api': api, '/ws': { target: api, ws: true } }

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { host: true, proxy },
  preview: { host: true, port: 5173, proxy, allowedHosts: true },
  test: { environment: 'jsdom', globals: true, setupFiles: ['./src/setupTests.ts'] },
})
