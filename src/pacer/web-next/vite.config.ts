import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

const API_TARGET = 'http://localhost:8001'
const API_PREFIXES = [
  '/auth', '/message', '/events', '/upload',
  '/profile', '/sessions', '/errors', '/plans', '/mastery',
]

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: Object.fromEntries(
      API_PREFIXES.map(p => [
        p,
        { target: API_TARGET, changeOrigin: true, ws: false },
      ]),
    ),
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    target: 'es2022',
  },
})
