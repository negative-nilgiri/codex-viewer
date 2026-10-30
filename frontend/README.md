# Viewer frontend

Minimal React and TypeScript client for the Codex Sessions Viewer API.

```bash
npm ci
npm run dev
npm run lint
npm run build
```

`just up` and `just serve` build it and serve `dist/` with `vite preview`, which
forwards `/api` to the backend on `VIEWER_API_PORT` (see `vite.config.ts`).
