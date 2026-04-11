import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const proxyTarget = process.env.VITE_PROXY_TARGET || 'http://192.168.1.40:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: proxyTarget,
        changeOrigin: true
      }
    }
  }
  
})
