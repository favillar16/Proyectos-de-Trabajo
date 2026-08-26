import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      injectRegister: 'auto',
      includeAssets: ['favicon.ico'],
      manifest: {
        name: 'Oga Porã — Gestión Comercial',
        short_name: 'Oga Porã',
        description: 'Gestión comercial, stock y showroom — Oga Porã',
        lang: 'es',
        start_url: '/',
        scope: '/',
        display: 'standalone',
        orientation: 'any',
        background_color: '#0a0a0a',
        theme_color: '#0a0a0a',
        icons: [
          { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
          { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
          { src: '/icons/icon-512-maskable.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        // Los datos de stock/ventas/caja deben ser siempre frescos: la API
        // nunca se sirve desde caché, solo se cachea el "shell" de la app.
        navigateFallbackDenylist: [/^\/api\//],
        runtimeCaching: [
          {
            urlPattern: /\/api\//,
            handler: 'NetworkOnly',
          },
          {
            // Fotos de productos — sirven para el showroom aunque el wifi falle un instante
            urlPattern: /\/media\//,
            handler: 'StaleWhileRevalidate',
            options: { cacheName: 'media-images', expiration: { maxEntries: 200 } },
          },
        ],
      },
      devOptions: {
        // Habilita el service worker también con `npm run dev`, para poder
        // probar la instalación en la tablet sin tener que hacer build.
        enabled: true,
        type: 'module',
      },
    }),
  ],
  server: {
    // '::' escucha IPv4 e IPv6 a la vez (Node no activa ipv6Only por defecto).
    // Hace falta IPv6 porque los nombres de red resuelven primero a IPv6: con
    // '0.0.0.0', entrar por http://ogapora.local:5173 daba timeout.
    host: '::',           // Accesible desde otros equipos en la red WiFi
    port: 5173,
    // Vite 5.4.12+ rechaza con 403 cualquier Host que no sea una IP o
    // localhost. Sin esto, entrar por nombre (http://ogapora.local:5173)
    // da "Blocked request. This host is not allowed". Se abre igual que
    // ALLOWED_HOSTS='*' del backend y por la misma razón: es un appliance
    // de red local sin salida a internet, y el nombre del equipo puede
    // cambiar. Ver docs/descubrimiento_red.md.
    allowedHosts: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/media': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
  // VITE_API_URL se lee automáticamente desde frontend/.env
})
