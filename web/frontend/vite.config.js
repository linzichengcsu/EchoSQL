import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 构建产物直接落到 Flask 的 static 目录：web/static/react/
// Flask 侧 web/templates/index.html 以 /static/react/assets/... 引用（base 决定前缀）。
export default defineConfig({
  plugins: [react()],
  base: '/static/react/',
  build: {
    outDir: '../static/react',
    emptyOutDir: true,
    // 合并为单个 CSS，产物文件名固定（无 hash），便于 Flask 模板直接引用
    cssCodeSplit: false,
    chunkSizeWarningLimit: 2500,
    rollupOptions: {
      output: {
        entryFileNames: 'assets/[name].js',
        chunkFileNames: 'assets/[name].js',
        assetFileNames: 'assets/[name][extname]',
      },
    },
  },
  server: {
    port: 5173,
    // 开发模式：把 API 请求代理到本地 Flask 后端（python -m web.app）
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
    },
  },
})
