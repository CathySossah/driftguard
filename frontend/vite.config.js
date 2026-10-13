import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['icons/icon-192.png', 'icons/icon-512.png'],
      manifest: {
        name: 'DriftGuard — Monitoring MLOps',
        short_name: 'DriftGuard',
        description: 'Monitoring et ré-entraînement automatisé pour la détection du data drift',
        theme_color: '#c9962c',
        background_color: '#faf8f3',
        display: 'standalone',
        start_url: '/',
        icons: [
          { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        // Ne met en cache que les assets statiques (JS/CSS/images) — pas les
        // appels API, qui doivent toujours refléter les données à jour.
        globPatterns: ['**/*.{js,css,html,ico,png,svg}'],
      },
    }),
  ],
  server: {
    host: true,
    port: 5173,
  },
})
