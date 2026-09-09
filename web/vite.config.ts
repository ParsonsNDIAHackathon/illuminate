import { defineConfig, type Plugin } from 'vite'
import { viteStaticCopy } from 'vite-plugin-static-copy'
import vue from '@vitejs/plugin-vue'
import vuetify from 'vite-plugin-vuetify'
import fs from 'node:fs'
import path from 'node:path'

const SLIDES = path.resolve(import.meta.dirname, '../slides')

// The pitch deck lives at the repo root and has no build step, so it is not part of the Vue app
// — but the app links to it. Serve it at /slides/ in dev, and copy it into dist so a built bundle
// is self-contained. In the container the deck is bind-mounted over nginx instead (see
// docker-compose.yml), which is why a missing directory here is not an error.
const MIME: Record<string, string> = {
  '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
  '.gif': 'image/gif', '.webp': 'image/webp', '.mp4': 'video/mp4', '.webm': 'video/webm',
  '.woff': 'font/woff', '.woff2': 'font/woff2', '.ttf': 'font/ttf', '.eot': 'application/vnd.ms-fontobject',
}

function slides(): Plugin {
  return {
    name: 'illuminate-slides',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = (req.url || '').split('?')[0]
        if (url !== '/slides' && !url.startsWith('/slides/')) return next()
        let rel = decodeURIComponent(url.slice('/slides'.length)) || '/'
        if (rel.endsWith('/')) rel += 'index.html'
        const file = path.join(SLIDES, rel)
        // Refuse anything that climbs back out of the deck.
        if (!file.startsWith(SLIDES + path.sep)) return next()
        if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) return next()
        res.setHeader('Content-Type', MIME[path.extname(file).toLowerCase()] || 'application/octet-stream')
        fs.createReadStream(file).pipe(res)
      })
    },
    closeBundle() {
      if (!fs.existsSync(SLIDES)) return
      fs.cpSync(SLIDES, path.resolve(import.meta.dirname, 'dist/slides'), { recursive: true })
    },
  }
}

export default defineConfig({
  define: { CESIUM_BASE_URL: JSON.stringify('/cesium/') },
  plugins: [vue(), vuetify({ autoImport: true }), slides(), viteStaticCopy({ targets: ['Workers', 'ThirdParty', 'Assets', 'Widgets'].map(dir => ({ src: `node_modules/cesium/Build/Cesium/${dir}`, dest: 'cesium', rename: { stripBase: 4 } })) })],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/mcp': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
  build: { chunkSizeWarningLimit: 1500 },
})
