/**
 * Configuración de tests del frontend.
 *
 * Va aparte de vite.config.js a propósito: ahí vive la config de build de
 * producción (PWA, Workbox, el bind 0.0.0.0 para las tablets) y no conviene
 * que un cambio de tests pueda tocarla.
 */
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['src/**/*.test.{js,jsx}'],
  },
})
