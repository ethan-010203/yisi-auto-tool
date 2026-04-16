import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const bindHost = process.env.VITE_HOST || '0.0.0.0'
const proxyTarget = process.env.VITE_PROXY_TARGET || 'http://localhost:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    host: bindHost,
    port: 5173,
    proxy: {
      '/api': {
        target: proxyTarget,
        changeOrigin: true
      }
    }
  }
})
