import { defineConfig } from 'vite';
export default defineConfig({
  base: '/',
  build: { outDir: 'dist', emptyOutDir: true, rollupOptions: { input: { main: 'index.html', admin: 'admin.html', account: 'account.html', privacy: 'privacy.html' } } },
  server: { proxy: { '/api': 'http://127.0.0.1:8000', '/docs': 'http://127.0.0.1:8000', '/openapi.json': 'http://127.0.0.1:8000' } }
});
