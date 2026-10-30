import react, { reactCompilerPreset } from '@vitejs/plugin-react'
import babel from '@rolldown/plugin-babel'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    babel({ presets: [reactCompilerPreset()] })
  ],
  // `vite preview` inherits both settings. `just serve` sets VIEWER_API_PORT.
  server: {
    // tailscale serve forwards the phone's *.ts.net Host header, which Vite blocks by default.
    allowedHosts: ['.ts.net'],
    proxy: { '/api': `http://127.0.0.1:${process.env.VIEWER_API_PORT ?? 41731}` },
  },
})
